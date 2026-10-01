"""Tape, drum and disc: the devices, the channel, the Executive's SVC 6,
the job-control cards, SALISH's devices library and TRI-TRAN's tape
statements; and Knuth's tape sorts."""

import json
import os
import re
import tempfile
import unittest

from duwamish import devices
from tests.helpers import ROOT, run_job


def run(deck):
    sat = run_job(deck)
    job = sat.jobs[0]
    if job.failed:
        raise AssertionError("\n".join(job.log))
    return job, job.steps[0].output


class TestReel(unittest.TestCase):
    def test_records_marks_and_motion(self):
        r = devices.Reel()
        self.assertEqual(r.op(2, [1, 2, 3], 3)[0], 3)
        self.assertEqual(r.op(2, [4] * 243, 243)[0], 243)
        self.assertEqual(r.op(3, None, 0)[0], 0)
        st, _, t = r.op(4, None, 0)
        self.assertEqual(r.pos, 0)
        self.assertGreater(t, 0)
        st, got, t = r.op(1, None, 100)
        self.assertEqual((st, got), (3, [1, 2, 3]))
        # a block of 243 words: the gap, and 729 frames at 90,000 a second
        st, got, t = r.op(1, None, 1000)
        self.assertEqual(st, 243)
        self.assertEqual(t, devices.GAP_TIME + int(729 / 90000 * 5_000_000))
        self.assertEqual(r.op(1, None, 10)[0], devices.MARK)
        self.assertEqual(r.op(1, None, 10)[0], devices.END)
        # backward: the mark, then the block, in its written order
        self.assertEqual(r.op(6, None, 10)[0], devices.MARK)
        st, got, _ = r.op(6, None, 1000)
        self.assertEqual((st, got[:2]), (243, [4, 4]))
        # writing in the middle loses what followed
        r.op(2, [9], 1)
        self.assertEqual(len(r.records), 2)
        self.assertEqual(r.op(5, None, 0)[0], 0)
        self.assertEqual(r.op(5, None, 0)[0], 0)
        self.assertEqual(r.op(5, None, 0)[0], devices.END)

    def test_write_ring(self):
        r = devices.Reel(ring=False)
        self.assertEqual(r.op(2, [1], 1)[0], devices.PROTECT)
        self.assertEqual(r.op(3, None, 0)[0], devices.PROTECT)

    def test_rewind_speeds(self):
        r = devices.Reel()
        for _ in range(100):
            r.op(2, [0] * 2400, 2400)
        dist = r.inches(r.pos)
        t = r.op(4, None, 0)[2] / devices.CYCLES_PER_SECOND
        slow = min(dist, devices.SLOW_REWIND)
        want = slow / 112.5 + (dist - slow) / 500
        self.assertAlmostEqual(t, want, places=2)


class TestDrumAndDisc(unittest.TestCase):
    def test_drum_waits_for_its_word(self):
        d = devices.Drum()
        turn = devices.DRUM_TURN
        d.op(2, [7] * 10, 10, 100, 0)
        st, got, t = d.op(1, None, 10, 100, 0)
        self.assertEqual(got, [7] * 10)
        word = turn / devices.DRUM_TRACK
        self.assertEqual(t, int(110 * word))
        # just after the word has passed: nearly a whole turn
        st, got, t = d.op(1, None, 1, 100, int(101.5 * word))
        self.assertGreater(t, 0.99 * turn)
        self.assertEqual(d.op(1, None, 2, devices.DRUM_WORDS - 1, 0)[0],
                         devices.END)

    def test_disc_seeks(self):
        p = devices.Pack()
        near = p.op(1, None, 81, 0, 0)[2]
        far = p.op(1, None, 81, devices.DISC_SECTORS - 1, 0)[2]
        self.assertLess(near, devices.DISC_TURN + 81 * devices.DISC_TURN // 729 + 1)
        self.assertGreaterEqual(far, devices.SEEK_START
                                + devices.SEEK_PER_CYL * 242)
        self.assertEqual(devices.Pack(writable=False).op(2, [1], 1, 0, 0)[0],
                         devices.PROTECT)


IO_PROGRAM = """
get "devices"
global buf[300], back[300]
proc main()
begin
  for i := 0 to 99 do buf[i] := i * i
  for r := 1 to 5 do begin buf[0] := r; twrite(1, buf, 100) end
  tmark(1)
  print(tpos(1)); spaces(1); print(rewind(1)); newline()
  print(tread(1, back, 300)); spaces(1); print(back[99]); newline()
  for r := 2 to 6 do begin printio(tread(1, back, 300)); spaces(1) end
  newline()
  printio(treadback(1, back, 300)); spaces(1)
  printio(treadback(1, back, 300)); spaces(1); print(back[0]); newline()
  printio(twrite(4, buf, 5)); spaces(1); printio(twrite(1, -5, 5)); spaces(1)
  printio(twrite(2, buf, 5)); newline()
  print(drumwrite(1000, buf, 100)); spaces(1); print(drumread(1000, back, 100))
  spaces(1); print(back[99]); newline()
  print(discwrite(1, 500, buf, 100)); spaces(1)
  print(discread(1, 500, back, 100)); spaces(1); print(back[50]); spaces(1)
  printio(discread(1, DISC_SECTORS, back, 1)); newline()
  return 0
end
"""


class TestChannel(unittest.TestCase):
    def test_salish_devices(self):
        job, out = run("//JOB IO\n//TAPE 1\n//TAPE 2 FILE=/nonexistent.json"
                       "\n//DISC 1\n//SALISH\n" + IO_PROGRAM + "\n//EXEC\n")
        self.assertEqual(out.splitlines(), [
            "6 0", "100 9801", "100 100 100 100 tape mark ",
            "tape mark 100 5", "not ready bad address no write ring",
            "100 100 9801", "100 100 2500 end"])
        self.assertIn("TAPE 2: mounted a new reel, to be kept in "
                      "nonexistent.json, without the write ring", job.log)
        # the time the tapes took is in the step's time
        self.assertGreater(job.steps[0].io, 0)

    def test_reels_kept_in_files(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "reel.json")
            write = ("//JOB W\n//TAPE 3 FILE=" + path + " RING\n//SALISH\n"
                     "get \"devices\"\nglobal b[3]\nproc main()\nbegin\n"
                     "  b[0] := 1; b[1] := -2; b[2] := 3\n"
                     "  twrite(3, b, 3); tmark(3)\n  return 0\nend\n//EXEC\n")
            job, _ = run(write)
            self.assertTrue(any("saved in reel.json" in m for m in job.after))
            with open(path) as f:
                self.assertEqual(json.load(f)["records"], [[1, -2, 3], "TM"])
            read = ("//JOB R\n//TAPE 3 FILE=" + path + "\n//SALISH\n"
                    "get \"devices\"\nglobal b[3]\nproc main()\nbegin\n"
                    "  print(tread(3, b, 3)); print(b[1])\n"
                    "  printio(twrite(3, b, 1))\n  return 0\nend\n//EXEC\n")
            job, out = run(read)
            self.assertEqual(out, "3-2no write ring")

    def test_tape_from_cards(self):
        job, out = run("//JOB C\n//TAPE 2 CARDS\nHELLO\nWORLD\n//SALISH\n"
                       "get \"devices\"\nglobal b[80]\nproc main()\nbegin\n"
                       "  var n := tread(2, b, 80)\n"
                       "  for i := 0 to n - 1 do putc(b[i])\n"
                       "  printio(tread(2, b, 80)); printio(tread(2, b, 80))\n"
                       "  return 0\nend\n//EXEC\n")
        self.assertEqual(out, "HELLO5tape mark")

    def test_unknown_unit_card(self):
        sat = run_job("//JOB X\n//TAPE 9\n//SALISH\nproc main() = 0\n//EXEC\n")
        self.assertTrue(sat.jobs[0].failed)


FORTRAN = """
      DIMENSION A(5)
      INTEGER N, K, I, U
      REAL X
      U = 2
      DO 10 K = 1, 10
      DO 5 I = 1, 5
    5 A(I) = FLOAT(K * I)
      WRITE (U) K, A
   10 CONTINUE
      ENDFILE 2
      REWIND 2
      N = 0
   20 READ (2, END=30) K, A
      N = N + 1
      GO TO 20
   30 WRITE (6, 100) N
  100 FORMAT (1X, I3, 8H RECORDS)
      BACKSPACE 2
      BACKSPACE 2
      READ (2) K, X
      WRITE (6, 101) K, X
  101 FORMAT (1X, 4HLAST, I4, F8.2)
      STOP
      END
"""


class TestTritranTape(unittest.TestCase):
    def test_tape_statements(self):
        job, out = run("//JOB F\n//TAPE 2\n//TRITRAN\n" + FORTRAN
                       + "//EXEC\n")
        self.assertEqual(out.split(), ["10", "RECORDS", "LAST", "10",
                                       "10.00"])

    def test_not_a_tape(self):
        from duwamish import tritran
        with self.assertRaisesRegex(tritran.CompileError, "not a tape"):
            tritran.compile_source("      REWIND 6\n      END\n", "t.ftn")


class TestTapeSorts(unittest.TestCase):
    def test_polyphase(self):
        with open(os.path.join(ROOT, "jobs", "polyphase.job")) as f:
            deck = f.read().replace("../", ROOT + "/")
        job, out = run(deck)
        rows = {}
        for line in out.splitlines():
            m = re.match(r"   (balanced|read backward|polyphase)\s+(\d+)\s+"
                         r"(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)"
                         r"\s+([\d.]+)\s+(yes|NO)$", line)
            if m:
                rows[m.group(1)] = [float(m.group(i)) for i in range(2, 9)] \
                    + [m.group(9)]
        self.assertEqual(len(rows), 3)
        for r in rows.values():
            self.assertEqual(r[-1], "yes")             # sorted, checked
            self.assertEqual(r[0], rows["balanced"][0])  # the same runs
        # runs, phases, passes, tape, rewinding, computing, total
        self.assertLess(rows["polyphase"][2], rows["balanced"][2])
        self.assertLess(rows["polyphase"][3], rows["balanced"][3])
        self.assertLess(rows["read backward"][4], rows["balanced"][4] / 2)
        self.assertLess(rows["read backward"][6], rows["balanced"][6])
        # replacement selection: runs of about twice the keys in core
        m = re.search(r"([\d.]+) times\n   the keys in core", out)
        self.assertAlmostEqual(float(m.group(1)), 2.0, delta=0.2)
        # Knuth's perfect distribution for four tapes, level 5: 13, 11, 7
        self.assertRegex(out, r"start\s+13 \(\d+\)\s+11 \(\d+\)\s+7 \(\d+\)")


if __name__ == "__main__":
    unittest.main()
