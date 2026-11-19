"""Byurakan 1971: the weight of evidence that a signal is artificial,
and the message that builds its receiver."""

import os
import unittest

from tests.helpers import ROOT, run_job


class TestByurakan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "jobs", "byurakan.job")) as f:
            deck = f.read().replace("../", ROOT + "/")
        sat = run_job(deck)
        for job in sat.jobs:
            if job.failed:
                raise AssertionError("\n".join(job.log))
        cls.listen, cls.line, cls.plane = [j.steps[-1].output for j in sat.jobs]

    def test_messages_are_what_the_tool_writes(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "make_message", os.path.join(ROOT, "tools", "make_message.py"))
        mm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mm)
        text = mm.message([[1, 1, 2], [2, 1]], [1])
        with open(os.path.join(ROOT, "data", "byurakan1.msg")) as f:
            self.assertEqual(f.read().replace("\n", ""), text)

    def test_only_the_transmission_is_artificial(self):
        verdicts = [l.split()[-1] for l in self.listen.splitlines()
                    if "with the prior" in l]
        self.assertEqual(verdicts, ["NATURAL", "NATURAL", "NATURAL", "ARTIFICIAL"])
        # the pulsar: far from noise, and no nearer to artifice
        blocks = self.listen.split("\n\n")
        pulsar = next(b for b in blocks if "LGM-1" in b)
        self.assertIn("clockwork against noise:   +", pulsar)
        self.assertIn("natural account:   -", pulsar)

    def test_decided_at_the_eighth_prime(self):
        rows = [l for l in self.listen.splitlines() if "<- 100 to 1 on" in l]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].split()[:2], ["8", "19"])
        self.assertIn("(the primes)", self.listen)

    def test_the_alga(self):
        for line in ("1. The frame message: the primes, in order, none missing",
                     "   1 -> 1 2", "   2 -> 1",
                     "   4  #.##.#.#",
                     "   lengths: 1 2 3 5 8 13 21 34 55",
                     "   each is the sum of the two before"):
            self.assertIn(line, self.line)

    def test_the_carpet(self):
        self.assertIn("writes a square of 3 by 3", self.plane)
        self.assertIn("   things of the first kind: 1 8 64 512", self.plane)
        self.assertIn("   each is 8 times the one before", self.plane)
        # the last generation, against the ternary digits of each cell:
        # a cell is empty when a row digit and a column digit are both 1
        lines = self.plane.split("generation 3\n")[1].splitlines()[:27]
        for i, l in enumerate(lines):
            l = l[3:].ljust(54)
            for j in range(27):
                a, b, hole = i, j, False
                for _ in range(3):
                    hole = hole or (a % 3 == 1 and b % 3 == 1)
                    a //= 3
                    b //= 3
                self.assertEqual(l[2 * j:2 * j + 2], "  " if hole else "##")


if __name__ == "__main__":
    unittest.main()
