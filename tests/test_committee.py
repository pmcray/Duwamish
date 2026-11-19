"""The rest of the committee's programs: Ashby's homeostat, Pask's SAKI,
Knuth's algorithms (Kleene Life, three-way sorting, ternary search trees, radix-3
FFT), and the AI programs of the period in TRILISP."""

import os
import re
import unittest

from tests.helpers import ROOT, run_job


def run_deck(name, model=90):
    with open(os.path.join(ROOT, "jobs", name)) as f:
        deck = f.read().replace("../", ROOT + "/")
    sat = run_job(deck, model)
    for job in sat.jobs:
        assert not job.failed, "\n".join(job.log)
    return sat


def life_step(grid):
    n = len(grid)
    out = []
    for r in range(n):
        row = ""
        for c in range(n):
            k = sum(grid[rr][cc] == "#" for rr in range(r - 1, r + 2)
                    for cc in range(c - 1, c + 2)
                    if (rr, cc) != (r, c) and 0 <= rr < n and 0 <= cc < n)
            alive = grid[r][c] == "#"
            row += "#" if k == 3 or (alive and k == 2) else "."
        out.append(row)
    return out


class TestKnuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sat = run_deck("knuth.job")
        cls.out = {job.name: job.steps[0].output for job in sat.jobs}

    def pictures(self, text):
        """The side-by-side worlds under the first header in text."""
        lines = text.splitlines()
        i = next(k for k, l in enumerate(lines) if "generation" in l
                 and l.strip().startswith(("generation", "in truth")))
        rows = [l for l in lines[i + 1:i + 28]]
        n = len(rows[0].split())
        return [[r.split()[k] for r in rows] for k in range(n)]

    def test_life_is_life(self):
        """With nothing unknown, the word-parallel Kleene adder is exactly
        Conway's rule: generations 4 and 8 follow from generation 0."""
        part = self.out["LIFE"].split("1. THE ORDINARY")[1].split("2. A WORLD")[0]
        g0, g4, g8 = self.pictures(part)
        g = g0
        for i in range(8):
            g = life_step(g)
            if i == 3:
                self.assertEqual(g, g4)
        self.assertEqual(g, g8)

    def test_kleene_life_is_sound_but_incomplete(self):
        part = self.out["LIFE"].split("2. A WORLD")[1].split("3. THE WORLD")[0]
        self.assertIn("every cell Kleene's logic called alive or dead was so",
                      part)
        rows = [l.split() for l in part.splitlines()
                if re.match(r"\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+$", l)]
        self.assertTrue(rows)
        for gen, alive, dead, unknown, truly in (map(int, r) for r in rows):
            self.assertEqual(alive + dead + unknown, 729)
            self.assertLessEqual(truly, unknown)
        self.assertLess(int(rows[-1][4]), int(rows[-1][3]))

    def test_ignorance_spreads_at_the_speed_of_light(self):
        part = self.out["LIFE"].split("3. THE WORLD")[1]
        unknown = [int(l.split()[3]) for l in part.splitlines()
                   if re.match(r"\s+\d+\s+\d+\s+\d+\s+\d+$", l)]
        self.assertEqual(unknown[0], 0)
        self.assertEqual(unknown, sorted(unknown))
        self.assertEqual(unknown[-1], 729)

    def test_sorting(self):
        out = self.out["SORTING"]
        self.assertNotIn("NOT SORTED", out)
        trits = [l for l in out.splitlines() if "three values" in l][0].split()
        # Hoare, Dijkstra, Bentley-McIlroy: comparisons, moves, cycles
        hoare_cmp, dijkstra_cmp = int(trits[3]), int(trits[6])
        self.assertLess(dijkstra_cmp * 5, hoare_cmp)
        self.assertTrue(trits[-1] == "Dijkstra")
        self.assertIn("Fewest comparisons: the 3-ary heap", out)

    def test_ternary_search_tree(self):
        out = self.out["TST"]
        self.assertIn("797 words, 150 different", out)
        self.assertIn("that the their them there thing third", out)
        self.assertIn("day had man may saw was", out)
        self.assertNotIn("LOST", out)

    def test_radix_three(self):
        out = self.out["FFT23"]
        rows = [l.split() for l in out.splitlines()
                if re.match(r"\s+[23]\s+\d+", l)]
        self.assertEqual([r[1] for r in rows], ["256", "243"])
        for r in rows:
            self.assertLess(float(r[-1].replace("E", "e")), 1e-6)
        self.assertGreater(int(rows[1][2]) / 243, int(rows[0][2]) / 256)
        self.assertIn("RADIX 3 IS THE FASTER FFT", out)


class TestHomeostat(unittest.TestCase):
    def test_ultrastability(self):
        out = run_deck("homeostat.job").jobs[0].steps[0].output
        parts = out.split("\n1. ")[1].split("\n2. ")[0], \
            out.split("\n2. ")[1].split("\n3. ")[0], \
            out.split("\n3. ")[1].split("\n4. ")[0]
        switched_on, disturbed, reversed_ = parts
        self.assertIn("the field is unstable", switched_on.splitlines()[2])
        self.assertTrue(switched_on.rstrip().endswith("the field is stable"))
        self.assertIn("moved 0 times", disturbed)
        self.assertIn("the field is unstable", reversed_)
        self.assertTrue(reversed_.rstrip().endswith("the field is stable"))


class TestSAKI(unittest.TestCase):
    def test_adaptive_teaching(self):
        out = run_deck("saki.job").jobs[0].steps[0].output
        self.assertRegex(out, r"judged the trainee ready after \d+ items")
        rows = {}
        machine = None
        for line in out.split("\n2. ")[1].split("\n3. ")[0].splitlines():
            m = re.match(r"   (ALWAYS LIT|FIXED|SAKI)?\s*(slow|average|fast)"
                         r"\s+(\d+)%\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)%", line)
            if m:
                machine = m.group(1) or machine
                rows[machine, m.group(2)] = [int(m.group(i))
                                             for i in range(3, 8)]
        self.assertEqual(len(rows), 9)
        kinds = ("slow", "average", "fast")
        # found, time, items, errors, attention
        for k in kinds:
            # lights always on teach the lights
            self.assertLess(rows["ALWAYS LIT", k][0], 50)
            self.assertEqual(rows["ALWAYS LIT", k][3], 0)
            # SAKI teaches every kind of trainee
            self.assertGreaterEqual(rows["SAKI", k][0], 90)
            self.assertGreater(rows["SAKI", k][4], rows["ALWAYS LIT", k][4])
        # the fixed schedule outpaces the slow trainees
        self.assertLess(rows["FIXED", "slow"][0], 70)
        self.assertGreater(rows["FIXED", "slow"][3], rows["SAKI", "slow"][3])
        # and SAKI's lessons are as long as each trainee needs
        items = [rows["SAKI", k][2] for k in kinds]
        self.assertEqual(items, sorted(items, reverse=True))


class TestAI(unittest.TestCase):
    def lisp(self, job):
        out = run_deck(job).jobs[0].steps[0].output
        self.assertNotIn("*** ERROR", out)
        return out

    def test_eliza_reproduces_weizenbaum(self):
        out = self.lisp("eliza.job")
        for reply in ("IN WHAT WAY", "CAN YOU THINK OF A SPECIFIC EXAMPLE",
                      "YOUR BOYFRIEND MADE YOU COME HERE",
                      "I AM SORRY TO HEAR YOU ARE DEPRESSED",
                      "DO YOU THINK COMING HERE WILL HELP YOU NOT TO BE UNHAPPY",
                      "WHAT WOULD IT MEAN TO YOU IF YOU GOT SOME HELP",
                      "TELL ME MORE ABOUT YOUR FAMILY",
                      "WHO ELSE IN YOUR FAMILY TAKES CARE OF YOU",
                      "YOUR FATHER", "WHAT RESEMBLANCE DO YOU SEE",
                      "WHAT MAKES YOU THINK I AM NOT VERY AGGRESSIVE",
                      "WHY DO YOU THINK I DON'T ARGUE WITH YOU",
                      "DOES IT PLEASE YOU TO BELIEVE I AM AFRAID OF YOU",
                      "WHAT ELSE COMES TO YOUR MIND WHEN YOU THINK OF YOUR FATHER",
                      "DOES THAT HAVE ANYTHING TO DO WITH THE FACT THAT YOUR "
                      "BOYFRIEND MADE YOU COME HERE"):
            self.assertIn("\n" + reply + "\n", out)

    def test_gps(self):
        out = self.lisp("gps.job")
        for n in range(3, 7):
            self.assertIn(f"{n} DISKS: {2 ** n - 1} MOVES", out)
        self.assertIn("MOVE 1 FROM A TO C GIVING 111", out)

    def test_strips(self):
        out = self.lisp("strips.job")
        self.assertIn("10 TURNON LS2 BOX1", out)
        self.assertIn("THE LIGHT IS ON.", out)
        self.assertNotIn("PRECONDITION DOES NOT HOLD", out)

    def test_three_valued_prolog(self):
        out = self.lisp("prolog.job")
        rows = {}
        for l in out.splitlines():
            m = re.match(r"\s+(\(.*?\))\s{2,}(.*?)\s{2,}(.*)$", l)
            if m:
                rows[m.group(1)] = (m.group(2).strip(), m.group(3).strip())
        self.assertEqual(rows["(GRANDPARENT TOM ANN)"], ("TRUE", "YES"))
        self.assertEqual(rows["(PARENT ANN TOM)"], ("FALSE", "NO"))
        self.assertEqual(rows["(FLIES POLLY)"], ("TRUE", "YES"))
        self.assertEqual(rows["(FLIES OPUS)"], ("FALSE", "NO"))
        self.assertEqual(rows["(FLIES TWEETY)"], ("UNKNOWN", "YES"))
        self.assertEqual(rows["(PENGUIN TWEETY)"], ("UNKNOWN", "NO"))
        self.assertEqual(rows["(LIKES BOB CAROL)"],
                         ("UNKNOWN", "NO ANSWER -- IT LOOPS"))
        self.assertEqual(set(rows["(ANCESTOR TOM ?WHO)"][0].split()),
                         {"BOB", "LIZ", "ANN", "PAT", "JIM"})

    def test_shrdlu(self):
        out = self.lisp("shrdlu.job")
        for q, a in (("GRASP THE PYRAMID.",
                      "I DON'T UNDERSTAND WHICH PYRAMID YOU MEAN."),
                     ("WHAT DOES THE BOX CONTAIN?",
                      "THE BLUE PYRAMID AND THE BLUE BLOCK."),
                     ("WHAT IS THE PYRAMID SUPPORTED BY?", "THE BOX."),
                     ("HOW MANY BLOCKS ARE NOT IN THE BOX?", "FOUR OF THEM."),
                     ("IS IT SUPPORTED?", "YES, BY THE TABLE."),
                     ("CAN A PYRAMID SUPPORT A PYRAMID?", "I DON'T KNOW."),
                     ("STACK UP TWO PYRAMIDS.", "I CAN'T.")):
            self.assertIn(q + "\n" + a, out)
        self.assertIn("I PUT THE BLUE BLOCK INTO THE BOX", out)
        self.assertIn("NO -- I HAVE TRIED.", out)


if __name__ == "__main__":
    unittest.main()
