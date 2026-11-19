"""Backing store for the Duwamish: magnetic tape, drum and disc.

All three hang on one data channel (device 8).  The Executive hands the
channel a six-word command -- device, unit, operation, core address,
count, position -- and the channel moves the words between core and the
device by itself, then returns a status.  The program waits while the
device works: the time the device takes (start and stop, seek, waiting
for the drum or the disc to come round, transfer, rewind) is added to the
machine's clock, so it shows in every step's running time.

The devices are the committee's, sized and timed after their binary
contemporaries.

  TAPE  nine-track tape, recording one trit to a track: + and - flux for
        +1 and -1, no flux for 0, so a frame is a tryte of nine trits and
        a word three frames.  800 frames to the inch at 112.5 inches a
        second (as the IBM 729 and 2401 ran): 30,000 words a second.
        Records are separated by gaps of 0.6 inch, which cost 5 ms to
        cross from a standing start.  A 2400-foot reel.  Rewinding goes
        at reading speed until there are more than 450 feet on the
        take-up reel, and beyond that at 500 inches a second.  A reel
        can be written only with its write ring fitted.
  DRUM  fixed heads, 243 tracks of 729 words (3^11 words), turning at
        1800 a minute: 33.3 ms a turn, 21,870 words a second.  A transfer
        waits for its first word to come under the heads.
  DISC  a removable pack of 243 cylinders, 9 surfaces, 9 sectors of 81
        words to a track (3^13 words), turning at 2400 a minute: 25 ms a
        turn.  Moving the arm costs 25 ms plus 0.45 ms a cylinder (25 to
        134 ms, as the IBM 2311).

Tape operations (status in brackets):

    0 SENSE           the number of the record the tape is at
    1 READ            the next record into core, at most count words
                      [words read; -1 a tape mark; -2 no more on the tape]
    2 WRITE           a record of count words; what followed is lost
                      [count; -2 past the end of the reel; -3 no ring]
    3 WRITE MARK      a tape mark (end of file) [0; -3 no ring]
    4 REWIND          to the load point [0]
    5 BACKSPACE       back over one record [0; -1 it was a tape mark;
                      -2 already at the load point]
    6 READ BACKWARD   the record before, reading toward the load point;
                      the words land in core in their written order
                      [words read; -1 a tape mark; -2 at the load point]
    7 SKIP            forward over one record [0; -1 a tape mark;
                      -2 no more on the tape]

Drum and disc operations: 1 READ and 2 WRITE count words at the
position -- a word address on the drum, a sector (81 words) on the disc
-- [count; -2 beyond the end].

Every device: -4 a core address outside the program's half of core or
a bad count; -5 no such unit, or nothing mounted on it.
"""

import json
import os

CYCLES_PER_SECOND = 5_000_000          # 200 ns cycles
MS = CYCLES_PER_SECOND // 1000

TAPE, DRUM, DISC = 1, 2, 3
DEVICE_NAMES = {TAPE: "TAPE", DRUM: "DRUM", DISC: "DISC"}

# tape
FRAMES_PER_WORD = 3
FRAMES_PER_INCH = 800
INCHES_PER_SECOND = 112.5
GAP_INCHES = 0.6
GAP_TIME = 5 * MS
REEL_INCHES = 2400 * 12
REWIND_SPEED = 500.0                   # inches a second, at high speed
SLOW_REWIND = 450 * 12                 # inches rewound at reading speed
MARK_FRAMES = 1

# drum
DRUM_TRACK = 729
DRUM_TRACKS = 243
DRUM_WORDS = DRUM_TRACK * DRUM_TRACKS
DRUM_TURN = CYCLES_PER_SECOND * 60 // 1800

# disc
SECTOR = 81
SECTORS_PER_TRACK = 9
SURFACES = 9
CYLINDERS = 243
TRACK_WORDS = SECTOR * SECTORS_PER_TRACK
CYL_WORDS = TRACK_WORDS * SURFACES
DISC_WORDS = CYL_WORDS * CYLINDERS
DISC_SECTORS = DISC_WORDS // SECTOR
DISC_TURN = CYCLES_PER_SECOND * 60 // 2400
SEEK_START = 25 * MS
SEEK_PER_CYL = 450 * MS // 1000

TM = None                              # a tape mark, in a reel's records

OK, MARK, END, PROTECT, BADADDR, NOTREADY = 0, -1, -2, -3, -4, -5


class Stats:
    def __init__(self):
        self.ops = 0
        self.words = 0
        self.cycles = 0

    def add(self, words, cycles):
        self.ops += 1
        self.words += words
        self.cycles += cycles


class Volume:
    """Something mounted: a reel, a pack, the drum."""

    def __init__(self, path=None, writable=True):
        self.path = path
        self.writable = writable
        self.dirty = False
        self.stats = Stats()

    def save(self):
        if self.path and self.dirty and self.writable:
            with open(self.path, "w") as f:
                json.dump(self.dump(), f, separators=(",", ":"))
            self.dirty = False
            return True
        return False


class Reel(Volume):
    def __init__(self, path=None, ring=True, records=None):
        super().__init__(path, ring)
        self.records = list(records or [])
        self.pos = 0                   # the record the heads are before
        if path and os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            self.records = [TM if r == "TM" else list(r)
                            for r in data["records"]]
        self.cum = [0.0]               # where each record begins, inches
        for r in self.records:
            self.cum.append(self.cum[-1] + self.length(r))

    def dump(self):
        return {"kind": "tape",
                "records": ["TM" if r is TM else r for r in self.records]}

    @staticmethod
    def frames(rec):
        return MARK_FRAMES if rec is TM else FRAMES_PER_WORD * len(rec)

    @classmethod
    def length(cls, rec):
        return cls.frames(rec) / FRAMES_PER_INCH + GAP_INCHES

    def inches(self, upto):
        """Where record `upto` begins, in inches from the load point."""
        return self.cum[upto]

    @classmethod
    def motion(cls, rec):
        """Cycles to move over one record from a standing start."""
        return GAP_TIME + int(cls.frames(rec) / FRAMES_PER_INCH
                              / INCHES_PER_SECOND * CYCLES_PER_SECOND)

    def op(self, op, words_in, count):
        """One tape operation: (status, words read, cycles)."""
        recs = self.records
        if op == 0:
            return self.pos, None, 0
        if op in (1, 7):                                   # READ, SKIP
            if self.pos >= len(recs):
                return END, None, GAP_TIME
            rec = recs[self.pos]
            self.pos += 1
            t = self.motion(rec)
            if rec is TM:
                return MARK, None, t
            if op == 7:
                return OK, None, t
            got = rec[:count]
            return len(got), got, t
        if op in (2, 3):                                   # WRITE, MARK
            if not self.writable:
                return PROTECT, None, 0
            rec = TM if op == 3 else list(words_in)
            del recs[self.pos:]                            # what followed is lost
            del self.cum[self.pos + 1:]
            recs.append(rec)
            self.cum.append(self.cum[-1] + self.length(rec))
            self.pos += 1
            self.dirty = True
            t = self.motion(rec)
            if self.inches(self.pos) > REEL_INCHES:
                return END, None, t
            return (0 if op == 3 else len(rec)), None, t
        if op == 4:                                        # REWIND
            dist = self.inches(self.pos)
            self.pos = 0
            if dist == 0:
                return OK, None, 0
            slow = min(dist, SLOW_REWIND)
            secs = slow / INCHES_PER_SECOND + (dist - slow) / REWIND_SPEED
            return OK, None, GAP_TIME + int(secs * CYCLES_PER_SECOND)
        if op in (5, 6):                                   # BACKSPACE, READ BACKWARD
            if self.pos == 0:
                return END, None, GAP_TIME
            self.pos -= 1
            rec = recs[self.pos]
            t = self.motion(rec)
            if rec is TM:
                return MARK, None, t
            if op == 5:
                return OK, None, t
            got = rec[-count:] if count < len(rec) else rec[:]
            if count == 0:
                got = []
            return len(got), got, t
        return BADADDR, None, 0


class Drum(Volume):
    def __init__(self, path=None):
        super().__init__(path, True)
        self.words = {}
        if path and os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            self.words = {int(k): v for k, v in data["words"].items()}

    def dump(self):
        return {"kind": "drum", "words": {str(k): v for k, v in
                                          sorted(self.words.items()) if v}}

    def op(self, op, words_in, count, pos, clock):
        if op not in (1, 2):
            return BADADDR, None, 0
        if pos < 0 or pos + count > DRUM_WORDS:
            return END, None, 0
        word_time = DRUM_TURN / DRUM_TRACK
        under = int((clock % DRUM_TURN) / word_time)       # under the heads now
        wait = (pos % DRUM_TRACK - under) % DRUM_TRACK
        t = int((wait + count) * word_time)
        if op == 1:
            return count, [self.words.get(pos + i, 0)
                           for i in range(count)], t
        for i, w in enumerate(words_in):
            self.words[pos + i] = w
        self.dirty = True
        return count, None, t


class Pack(Volume):
    def __init__(self, path=None, writable=True):
        super().__init__(path, writable)
        self.words = {}
        self.cyl = 0
        if path and os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            self.words = {int(k): v for k, v in data["words"].items()}

    def dump(self):
        return {"kind": "disc", "words": {str(k): v for k, v in
                                          sorted(self.words.items()) if v}}

    def op(self, op, words_in, count, pos, clock):
        if op not in (1, 2):
            return BADADDR, None, 0
        start = pos * SECTOR
        if pos < 0 or start + count > DISC_WORDS:
            return END, None, 0
        if op == 2 and not self.writable:
            return PROTECT, None, 0
        t = 0
        cyl = start // CYL_WORDS
        if cyl != self.cyl:
            t += SEEK_START + SEEK_PER_CYL * abs(cyl - self.cyl)
        word_time = DISC_TURN / TRACK_WORDS
        under = int(((clock + t) % DISC_TURN) / word_time)
        wait = (start % TRACK_WORDS - under) % TRACK_WORDS
        t += int((wait + count) * word_time)
        # a transfer that runs on into the next cylinder moves the arm
        last_cyl = (start + max(count, 1) - 1) // CYL_WORDS
        t += (SEEK_START + SEEK_PER_CYL) * (last_cyl - cyl)
        self.cyl = last_cyl
        if op == 1:
            return count, [self.words.get(start + i, 0)
                           for i in range(count)], t
        for i, w in enumerate(words_in):
            self.words[start + i] = w
        self.dirty = True
        return count, None, t


class Channel:
    """The data channel: device 8.  OUT six words, then IN the status."""

    def __init__(self):
        self.tapes = {}                # unit -> Reel
        self.packs = {}                # unit -> Pack
        self.drum = Drum()
        self.cmd = []
        self.log = []                  # (device, unit, op, status, cycles)

    def out(self, v):
        self.cmd.append(v)
        if len(self.cmd) > 6:
            self.cmd = self.cmd[-6:]

    def execute(self, m, mem_off, mem_max):
        if len(self.cmd) != 6:
            self.cmd = []
            return BADADDR
        dev, unit, op, addr, count, pos = self.cmd
        self.cmd = []
        if count < 0 or addr < 0 or addr + count - 1 > mem_max:
            return BADADDR
        if dev == TAPE:
            vol = self.tapes.get(unit)
        elif dev == DISC:
            vol = self.packs.get(unit)
        elif dev == DRUM:
            vol = self.drum if unit in (0, 1) else None
        else:
            vol = None
        if vol is None:
            return NOTREADY
        mem = m.mem
        writing = (dev == TAPE and op == 2) or (dev != TAPE and op == 2)
        words_in = mem[addr + mem_off:addr + mem_off + count] if writing else None
        if dev == TAPE:
            status, got, cycles = vol.op(op, words_in, count)
        else:
            status, got, cycles = vol.op(op, words_in, count, pos, m.clock)
        if got:
            mem[addr + mem_off:addr + mem_off + len(got)] = got
        moved = len(got) if got else (count if writing and status >= 0 else 0)
        vol.stats.add(moved, cycles)
        m.clock += cycles
        m.io_cycles += cycles
        return status
