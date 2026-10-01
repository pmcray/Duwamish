"""The satellite: job control for the Duwamish.

As with IBM's 7094/7044 Direct Coupled System, a smaller satellite computer
stands between the operators and the Duwamish.  It reads card decks, runs
the translators (SALISH compiler, TRIAD assembler), spools the line
printer, and feeds job steps to the Duwamish Executive over a channel.

A job deck is a sequence of cards (lines).  Control cards begin with //:

    //JOB name [TIME=cycles] [KEY=WCS]  start a job (KEY=WCS: the job
                                    needs the writable control store)
    //SALISH [FROM=path] [LIST] [OPT]
                                    compile SALISH (the following cards, or a
                                    file); LIST prints the TRIAD listing,
                                    OPT runs the optimising compiler
    //TRITRAN [FROM=path] [LIST]    compile TRI-TRAN, the Duwamish FORTRAN;
                                    LIST prints the TRIAD code of the
                                    program (without its library)
    //WHALE [FROM=path] [LIST] [OPT]
                                    compile WHALE, SALISH with an
                                    associative store of weighed facts
    //TRIAD [FROM=path] [LIST]      assemble TRIAD source
    //TRIAD PUNCHED [LIST]          assemble the cards punched by the job's
                                    last step (SVC 5), when this step runs:
                                    a compiler's output becomes a program
    //EXEC [name]                   run the program just translated, or a
                                    catalogued program (e.g. TRILISP)
    //DATA [FROM=path]              the cards that follow (or a file) are
                                    read by the program through SVC 2
    //TAPE unit [FILE=path] [RING] [CARDS]
                                    mount a reel on a tape unit (1-8) for
                                    the job: a scratch reel, or the reel
                                    kept in a file.  RING fits the write
                                    ring (a scratch reel always has one);
                                    CARDS writes the cards that follow on
                                    the reel, a record to a card
    //DISC unit [FILE=path] [PROTECT]
                                    mount a disc pack (units 1-4)
    //DRUM FILE=path                load the drum from a file, and save it
                                    there when the job ends (otherwise the
                                    drum keeps what earlier jobs left)
    //END                           end of job (optional)

Anything after `--` on a control card is a comment.
"""

import os
import re
import shlex
import time

from . import devices
from . import isa
from . import machine as mach
from . import salish
from . import triad
from . import tritran
from . import whale

HERE = os.path.dirname(__file__)
EXECUTIVE_SRC = os.path.join(HERE, "executive.tri")
USER_ORIGIN = 100
USER_STACK = mach.MEM_MAX + 1
CYCLE_NS = 200

CATALOGUE = {
    "TRILISP": os.path.join(HERE, "lib", "trilisp.sal"),
}


class JobError(Exception):
    pass


def _n(k, noun):
    return f"{k:,} {noun}{'' if k == 1 else 's'}"


def assemble_executive():
    with open(EXECUTIVE_SRC) as f:
        return triad.assemble(f.read())


def translate_tritran(text, fname):
    asm, comp = tritran.compile_source(text, fname)
    obj = triad.assemble(asm, origin=USER_ORIGIN)
    return obj, asm, comp


def translate_whale(text, fname, optimise=False):
    asm, comp = whale.compile_source(text, fname, optimise=optimise)
    obj = triad.assemble(asm, origin=USER_ORIGIN)
    return obj, asm, comp


def translate_salish(text, fname, include_path=None, optimise=False):
    asm, comp = salish.compile_source(text, fname, include_path, optimise)
    obj = triad.assemble(asm, origin=USER_ORIGIN)
    return obj, asm, comp


_catalogue_cache = {}


def catalogued(name, optimise=False):
    name = name.upper()
    if name not in CATALOGUE:
        raise JobError(f"no program {name} in the catalogue")
    key = (name, optimise)
    if key not in _catalogue_cache:
        path = CATALOGUE[name]
        with open(path) as f:
            obj, asm, comp = translate_salish(f.read(), path,
                                              optimise=optimise)
        _catalogue_cache[key] = obj
    return _catalogue_cache[key]


class PunchedDeck:
    """The object deck a step will punch: assembled only when needed."""

    def __init__(self, source, listing):
        self.source = source        # the Step whose punched cards these are
        self.listing = listing


class Step:
    def __init__(self, job, kind, name):
        self.job = job
        self.kind = kind          # 'EXEC'
        self.name = name
        self.obj = None
        self.data = []
        self.result = None
        self.out_start = 0
        self.messages = []
        self.punched = ""


class Job:
    def __init__(self, name, opts):
        self.name = name
        self.time_limit = int(opts.get("TIME", "0"))
        self.steps = []
        self.translations = []     # (source name, TRIAD text) from //SALISH
        self.log = []
        self.failed = False
        self.volumes = []          # (kind, unit, path, writable, records)
        self.after = []            # what the satellite says after the steps


def parse_control(card):
    body = card[2:].split("--", 1)[0]
    parts = shlex.split(body)
    if not parts:
        return None, [], {}
    verb = parts[0].upper()
    args, opts = [], {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            opts[k.upper()] = v
        else:
            args.append(p)
    return verb, args, opts


class Satellite:
    def __init__(self, decks, model=30, wcs=False, listing=False,
                 out=None, base_dir=None, trace=False, fpu=None,
                 optimise=False, lookahead=False):
        self.model = model
        self.lookahead = lookahead  # the Model 90's look-ahead unit
        self.optimise = optimise    # compile every SALISH step with OPT
        self.wcs = wcs
        self.fpu = (model == 90) if fpu is None else fpu
        self.listing = listing
        self.out = out or (lambda s: print(s, end=""))
        self.base_dir = base_dir or os.getcwd()
        self.jobs = []
        self.queue = []            # (job, step) awaiting execution
        self.cur = None
        self.responses = []
        self.cmd = []
        self.trace = trace
        self.channel = devices.Channel()
        self.mounted = None        # the job whose volumes are mounted
        for text, fname in decks:
            self.read_deck(text, fname)

    # ------------------------------------------------------------------
    # card reading and translation
    # ------------------------------------------------------------------
    def resolve(self, path, deck_dir):
        for base in (deck_dir, self.base_dir):
            p = os.path.join(base, path)
            if os.path.exists(p):
                return p
        raise JobError(f"file not found: {path}")

    def read_deck(self, text, fname):
        deck_dir = os.path.dirname(os.path.abspath(fname))
        cards = text.splitlines()
        job = None
        i = 0
        pending_obj = None
        while i < len(cards):
            card = cards[i]
            i += 1
            if not card.startswith("//"):
                continue
            verb, args, opts = parse_control(card)
            if verb is None:
                continue
            body = []
            while i < len(cards) and not cards[i].startswith("//"):
                body.append(cards[i])
                i += 1
            if verb == "JOB":
                job = Job(args[0] if args else "NONAME", opts)
                self.jobs.append(job)
                pending_obj = None
                if opts.get("KEY", "").upper() == "WCS" and not self.wcs:
                    job.log.append("*** JOB NEEDS THE CONTROL-STORE KEY AT WCS "
                                   "ENABLE (run with --wcs); job flushed")
                    job.failed = True
                continue
            if job is None:
                job = Job("NONAME", {})
                self.jobs.append(job)
            if job.failed:
                continue
            try:
                if verb in ("SALISH", "TRIAD", "TRITRAN", "WHALE"):
                    if verb == "TRIAD" and "PUNCHED" in args:
                        if not job.steps:
                            raise JobError("//TRIAD PUNCHED before any //EXEC")
                        pending_obj = PunchedDeck(job.steps[-1], "LIST" in args
                                                  or self.listing)
                        continue
                    if "FROM" in opts:
                        path = self.resolve(opts["FROM"], deck_dir)
                        with open(path) as f:
                            src = f.read()
                        sname = opts["FROM"]
                    else:
                        src = "\n".join(body) + "\n"
                        path = os.path.join(deck_dir, f"{job.name}.inline")
                        sname = f"{job.name} (inline)"
                    t0 = time.time()
                    if verb in ("SALISH", "WHALE"):
                        o = "OPT" in args or self.optimise
                        tr = (translate_salish if verb == "SALISH"
                              else translate_whale)
                        pending_obj, asm, comp = tr(src, path, optimise=o)
                        job.translations.append(
                            (sname + (" with OPT" if o else ""), asm))
                        msg = (f"{verb}{'/O' if o else ''}: {sname}: "
                               f"{len(pending_obj.words)}"
                               f" words, {len(comp.procs)} procedures")
                        job.log.append(msg)
                        if comp.bloop_report:
                            job.log.append(comp.bloop_report)
                        if "LIST" in args or self.listing:
                            job.log.append(pending_obj.listing_text())
                    elif verb == "TRITRAN":
                        pending_obj, asm, comp = translate_tritran(src, path)
                        job.translations.append((sname, asm))
                        units = len(comp.units)
                        job.log.append(
                            f"TRI-TRAN: {sname}: {len(pending_obj.words)} "
                            f"words with its library, {units} program "
                            f"unit{'s' if units != 1 else ''}")
                        if not self.fpu:
                            job.log.append(
                                "TRI-TRAN: note: this machine has no "
                                "floating-point unit, and REAL arithmetic "
                                "will stop the job")
                        if "LIST" in args or self.listing:
                            job.log.append(asm.split(
                                "; SALISH compiler output")[0].rstrip())
                    else:
                        pending_obj = triad.assemble(src, origin=USER_ORIGIN)
                        job.log.append(f"TRIAD: {sname}: "
                                       f"{len(pending_obj.words)} words")
                        if "LIST" in args or self.listing:
                            job.log.append(pending_obj.listing_text())
                    del t0
                elif verb == "EXEC":
                    step = Step(job, "EXEC", args[0] if args else "GO")
                    step.obj = (catalogued(args[0], self.optimise) if args
                                else pending_obj)
                    if step.obj is None:
                        raise JobError("//EXEC with nothing to execute")
                    job.steps.append(step)
                    self.queue.append((job, step))
                elif verb == "DATA":
                    if not job.steps:
                        raise JobError("//DATA before //EXEC")
                    if "FROM" in opts:
                        with open(self.resolve(opts["FROM"], deck_dir)) as f:
                            body = f.read().splitlines()
                    data = []
                    for line in body:
                        data.extend(ord(c) for c in line)
                        data.append(10)
                    job.steps[-1].data.extend(data)
                elif verb in ("TAPE", "DISC", "DRUM"):
                    self.volume_card(job, verb, args, opts, body, deck_dir)
                elif verb == "END":
                    job = None
                else:
                    raise JobError(f"unknown control card //{verb}")
            except (salish.CompileError, tritran.CompileError,
                    triad.AsmError, JobError, OSError) as e:
                job.log.append(f"*** {verb} FAILED: {e}")
                job.failed = True
                self.queue = [(j, s) for j, s in self.queue if j is not job]

    # ------------------------------------------------------------------
    # tapes, drum and discs
    # ------------------------------------------------------------------
    def volume_card(self, job, verb, args, opts, body, deck_dir):
        if verb == "DRUM":
            if "FILE" not in opts:
                raise JobError("//DRUM needs FILE=")
            unit = 1
        else:
            if not args or not args[0].isdigit():
                raise JobError(f"//{verb} needs a unit number")
            unit = int(args[0])
            top = 8 if verb == "TAPE" else 4
            if not 1 <= unit <= top:
                raise JobError(f"there is no {verb.lower()} unit {unit}")
        path = opts.get("FILE")
        if path:
            path = os.path.join(deck_dir, path)
        flags = {a.upper() for a in args[1:]}
        if verb == "TAPE":
            writable = "RING" in flags or not path
        else:
            writable = "PROTECT" not in flags
        records = None
        if "CARDS" in flags:
            if verb != "TAPE":
                raise JobError("only a tape can be written from cards")
            records = [[ord(c) for c in line] for line in body]
        for v in job.volumes:
            if v[0] == verb and v[1] == unit:
                raise JobError(f"{verb} {unit} is mounted twice")
        job.volumes.append((verb, unit, path, writable, records))

    def mount(self, job):
        ch = self.channel
        for verb, unit, path, writable, records in job.volumes:
            name = f"{verb} {unit}" if verb != "DRUM" else "DRUM"
            where = f"the reel in {os.path.basename(path)}" if path else ""
            if verb == "TAPE":
                reel = devices.Reel(path, writable)
                if records is not None:
                    reel.records = records + [devices.TM]
                    reel.cum = [0.0]
                    for r in reel.records:
                        reel.cum.append(reel.cum[-1] + reel.length(r))
                    reel.dirty = True
                ch.tapes[unit] = reel
                n = sum(1 for r in reel.records if r is not devices.TM)
                if records is not None:
                    desc = (f"{where or 'a scratch reel'}, written from "
                            f"{_n(len(records), 'card')}")
                elif path and os.path.exists(path):
                    desc = f"{where}, {_n(n, 'record')}"
                elif path:
                    desc = f"a new reel, to be kept in {os.path.basename(path)}"
                else:
                    desc = "a scratch reel"
                ring = "with" if writable else "without"
                job.log.append(f"{name}: mounted {desc}, {ring} the write "
                               "ring")
            elif verb == "DISC":
                pack = devices.Pack(path, writable)
                ch.packs[unit] = pack
                job.log.append(f"{name}: mounted "
                               f"{'the pack in ' + os.path.basename(path) if path else 'a scratch pack'}"
                               f"{', write-protected' if not writable else ''}")
            else:
                ch.drum = devices.Drum(path)
                job.log.append(f"DRUM: loaded from {os.path.basename(path)}")
        self.mounted = job

    def dismount(self):
        job = self.mounted
        if job is None:
            return
        ch = self.channel
        for verb, unit, path, writable, records in job.volumes:
            vol = (ch.tapes.pop(unit, None) if verb == "TAPE" else
                   ch.packs.pop(unit, None) if verb == "DISC" else ch.drum)
            if vol is None:
                continue
            st = vol.stats
            name = f"{verb} {unit}" if verb != "DRUM" else "DRUM"
            msg = (f"{name}: {_n(st.ops, 'operation')}, "
                   f"{_n(st.words, 'word')}, "
                   f"{st.cycles / devices.CYCLES_PER_SECOND:,.1f} s")
            if verb == "TAPE":
                n = sum(1 for r in vol.records if r is not devices.TM)
                msg += f"; {_n(n, 'record')} on the reel"
            if vol.save():
                msg += f"; saved in {os.path.basename(path)}"
            job.after.append(msg)
        self.mounted = None

    # ------------------------------------------------------------------
    # the channel to the Executive
    # ------------------------------------------------------------------
    def channel_out(self, m, v):
        self.cmd.append(v)
        c = self.cmd
        if c[0] == 1:
            self.cmd = []
            self.start_next(m)
        elif c[0] == 2 and len(c) == 5:
            self.cmd = []
            self.end_step(m, c[1], c[2], c[3], c[4])
        elif c[0] not in (1, 2):
            self.cmd = []

    def channel_in(self, m):
        return self.responses.pop(0) if self.responses else -1

    def start_next(self, m):
        if not self.queue:
            self.responses = [-1]
            return
        job, step = self.queue.pop(0)
        if isinstance(step.obj, PunchedDeck) and not self.assemble_punched(
                job, step):
            return self.start_next(m)
        if self.mounted is not job:
            self.dismount()
            self.mount(job)
        self.cur = (job, step)
        mem = m.mem
        for i in range(mach.MEM_OFF, mach.MEM_SIZE):
            mem[i] = 0
        m.load_image(step.obj.image())
        m.reader = step.data
        m.reader_pos = 0
        m.tally_clear()
        step.out_start = len(m.printer)
        step.punch_start = len(m.punch)
        step.i0 = m.icount
        step.s0 = (m.stack_hits, m.stack_fetches)
        step.t0 = time.time()
        step.io0 = m.io_cycles
        entry = step.obj.entry if step.obj.entry is not None else USER_ORIGIN
        self.responses = [entry, USER_STACK, job.time_limit]

    def end_step(self, m, how, value, where, cycles):
        job, step = self.cur
        step.result = (how, value, where, cycles, m.icount - step.i0,
                       time.time() - step.t0)
        step.output = m.text(m.printer[step.out_start:])
        step.punched = m.text(m.punch[step.punch_start:])
        step.stack = (m.stack_hits - step.s0[0], m.stack_fetches - step.s0[1])
        step.io = m.io_cycles - step.io0
        self.cur = None

    def assemble_punched(self, job, step):
        """Assemble the deck an earlier step punched; False if it cannot."""
        deck = step.obj
        src = deck.source
        k = job.steps.index(src) + 1
        text = src.punched
        cards = text.count("\n")
        if src.result is None or not text:
            step.messages.append(f"TRIAD: step {k} punched no cards; "
                                 "nothing to run")
            step.obj = None
            return False
        try:
            obj = triad.assemble(text, origin=USER_ORIGIN)
        except triad.AsmError as e:
            step.messages.append(f"*** TRIAD FAILED on the deck punched by "
                                 f"step {k}: {e}")
            step.obj = None
            return False
        msg = (f"TRIAD: the deck punched by step {k}: {cards:,} cards, "
               f"{len(obj.words):,} words")
        for j, other in enumerate(job.steps[:k - 1]):
            if other.punched == text:
                msg += f"; identical, card for card, to the deck of step {j + 1}"
                break
        for name, asm in job.translations:
            if asm == text:
                msg += (f"; identical, card for card, to the satellite's own "
                        f"compilation of {name}")
                break
        step.messages.append(msg)
        if deck.listing:
            step.messages.append(obj.listing_text())
        step.obj = obj
        return True

    # ------------------------------------------------------------------
    def run(self):
        m = mach.Machine(model=self.model, wcs_enabled=self.wcs,
                         satellite=self, fpu=self.fpu,
                         lookahead=self.lookahead)
        m.channel = self.channel
        self.machine = m
        ex = assemble_executive()
        self.executive = ex
        m.load_image(ex.image())
        m.pc = ex.entry
        reason = m.run()
        self.dismount()
        self.report(m, reason)
        return m

    def report(self, m, reason):
        w = self.out
        line = "=" * 72
        w(f"{line}\nDUWAMISH MODEL {self.model}"
          f"{'  WITH FLOATING-POINT UNIT' if self.fpu else ''}"
          f"{'  AND LOOK-AHEAD UNIT' if self.lookahead else ''}"
          f"{'  (WRITABLE CONTROL STORE ENABLED)' if self.wcs else ''}"
          f"   -- satellite job log\n")
        tty = m.text(m.tty)
        if tty:
            w("CONSOLE: " + tty.replace("\n", "\n         ").rstrip() + "\n")
        for job in self.jobs:
            w(f"{line}\nJOB {job.name}\n")
            for msg in job.log:
                w(f"  {msg}\n")
            for step in job.steps:
                w(f"{'-' * 72}\nSTEP //EXEC {step.name}\n{'-' * 72}\n")
                for msg in step.messages:
                    w(f"  {msg}\n")
                if step.result is None:
                    w("  (not run)\n")
                    continue
                w(step.output)
                if step.output and not step.output.endswith("\n"):
                    w("\n")
                how, value, where, cycles, instrs, secs = step.result
                w(f"{'-' * 72}\n")
                if how == 0:
                    status = f"EXIT {value}"
                else:
                    status = (f"PROGRAM CHECK {how} "
                              f"({isa.TRAP_NAMES.get(how, '?')}) AT {where}")
                us = cycles * CYCLE_NS / 1000
                w(f"END OF STEP: {status}.  {instrs:,} instructions, "
                  f"{cycles:,} cycles = {us / 1000:,.3f} ms of Duwamish "
                  f"time ({secs:.1f} s simulated)\n")
                if getattr(step, "io", 0):
                    w(f"  of which {step.io * CYCLE_NS / 1e9:,.1f} s waiting "
                      "for tape, drum and disc\n")
                if step.punched:
                    w(f"  punched {step.punched.count(chr(10)):,} cards\n")
                hits, fetches = getattr(step, "stack", (0, 0))
                if self.lookahead and fetches:
                    w(f"  instruction stack: {hits:,} of {fetches:,} "
                      f"instructions ({100 * hits / fetches:.0f}%) came from "
                      f"the stack, not from core\n")
            if job.after:
                w(f"{'-' * 72}\n")
                for msg in job.after:
                    w(f"  {msg}\n")
        w(f"{line}\n")
        if reason != "halt":
            w(f"MACHINE STOPPED: {reason} "
              f"{getattr(m, 'check_message', '')}\n")


def run_decks(paths, **kw):
    decks = []
    for p in paths:
        with open(p) as f:
            decks.append((f.read(), p))
    sat = Satellite(decks, **kw)
    sat.run()
    return sat


def run_program(path, data=None, model=30, wcs=False, listing=False,
                time_limit=0, out=None, fpu=None, optimise=False,
                lookahead=False):
    """Convenience: wrap one SALISH/TRIAD source file into a job."""
    kind = ("TRIAD" if path.endswith(".tri") else
            "TRITRAN" if path.endswith((".ftn", ".f")) else
            "WHALE" if path.endswith(".whl") else "SALISH")
    name = re.sub(r"\W", "", os.path.splitext(os.path.basename(path))[0])
    deck = [f"//JOB {name.upper()} TIME={time_limit}",
            f"//{kind} FROM={os.path.abspath(path)}"
            + (" LIST" if listing else ""),
            "//EXEC"]
    if data:
        deck.append(f"//DATA FROM={os.path.abspath(data)}")
    sat = Satellite([("\n".join(deck), path)], model=model, wcs=wcs, out=out,
                    fpu=fpu, optimise=optimise, lookahead=lookahead)
    sat.run()
    return sat
