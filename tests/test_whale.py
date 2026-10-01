"""WHALE: SALISH with an associative store of weighed, three-valued facts."""

import os
import re
import unittest

from duwamish import whale
from duwamish.salish import CompileError
from tests.helpers import ROOT, run_job


def run_whale(src, model=90):
    sat = run_job("//JOB W\n//WHALE\n" + src + "\n//EXEC\n", model)
    job = sat.jobs[0]
    if job.failed:
        raise AssertionError("\n".join(job.log))
    return job.steps[0].output


ITEMS = "item colour, red, green, on, likes, b1, b2, b3, yes\n"


class TestStore(unittest.TestCase):
    def test_three_values_and_erase(self):
        out = run_whale(ITEMS + """
proc main()
begin
  make colour of b1 is red
  deny colour of b1 is green
  print(fact colour of b1 is red); print(fact colour of b1 is green)
  print(fact colour of b2 is red)
  erase colour of b1 is red
  print(fact colour of b1 is red); newline()
  printitem(the colour of b1); printitem(the colour of b2); newline()
  return 0
end""")
        self.assertEqual(out, "1-100\n??\n")

    def test_evidence_adds_to_a_verdict(self):
        out = run_whale(ITEMS + """
proc main()
begin
  confirm colour of b2 is red by 800;  print(fact colour of b2 is red)
  confirm colour of b2 is red by 1200; print(fact colour of b2 is red)
  confirm colour of b2 is red by -4100; print(fact colour of b2 is red)
  newline(); printdb(weight colour of b2 is red); newline()
  make colour of b3 is red
  confirm colour of b3 is red by -5000; print(fact colour of b3 is red)
  wh_thresh := 500
  confirm colour of b1 is red by 600; print(fact colour of b1 is red)
  newline()
  return 0
end""")
        self.assertEqual(out, "01-1\n-21.0 db\n11\n")

    def test_foreach(self):
        out = run_whale(ITEMS + """
proc main()
begin
  make colour of b1 is red; make colour of b2 is green
  make colour of b3 is red
  make on of b1 is b2; make on of b3 is b1
  make likes of b1 is b1; make likes of b1 is b2
  foreach x such that colour of x is red do printitem(x)
  newline()
  -- a join: what stands on something red?
  foreach x, y such that on of x is y and colour of y is red do
    begin printitem(x); printitem(y) end
  newline()
  -- the attribute unbound: everything known of b1
  foreach a, v such that a of b1 is v do begin printitem(a); spaces(1) end
  newline()
  -- one variable twice in a triple
  foreach x such that likes of x is x do printitem(x)
  newline()
  -- a SALISH condition as a conjunct
  foreach x, y such that on of x is y and x <> b3 do printitem(x)
  newline()
  -- break leaves the loop
  foreach x such that colour of x is red do begin printitem(x); break end
  newline()
  return 0
end""")
        lines = out.splitlines()
        self.assertEqual(sorted(re.findall(r"b\d", lines[0])), ["b1", "b3"])
        self.assertEqual(lines[1], "b3b1")
        self.assertEqual(sorted(lines[2].split()), ["colour", "likes", "likes",
                                                    "on"])
        self.assertEqual(lines[3], "b1")
        self.assertEqual(lines[4], "b1")
        self.assertEqual(len(re.findall(r"b\d", lines[5])), 1)

    def test_ranked_and_possibly(self):
        out = run_whale(ITEMS + """
proc main()
begin
  confirm colour of b1 is red by 500
  confirm colour of b1 is green by 2500
  confirm colour of b1 is yes by -2500
  confirm colour of b2 is red by 3000
  foreach ranked c such that possibly colour of b1 is c do printitem(c)
  newline()
  foreach c such that colour of b1 is c do printitem(c)
  newline()
  foreach ranked x, c such that colour of x is c do printitem(x)
  newline()
  return 0
end""")
        self.assertEqual(out, "greenred\ngreen\nb2b1\n")

    def test_new_items_and_forget(self):
        out = run_whale(ITEMS + """
proc main()
begin
  var g := new, h := new
  make colour of g is red
  make on of g is h
  printitem(g); spaces(1); printitem(the on of g); newline()
  forget(g)
  printitem(the colour of g); newline()
  -- erased triples are used again: the store never fills
  for i := 1 to 5000 do begin
    make colour of h is green
    erase colour of h is green
  end
  print(wh_live); newline()
  return 0
end""")
        self.assertEqual(out, "G10 G11\n?\n0\n")

    def test_weights_of_evidence(self):
        out = run_whale(ITEMS + """
proc main()
begin
  print(woe(100, 1)); spaces(1); print(woe(1, 100)); spaces(1)
  print(woe(2, 1)); spaces(1); print(woe(1, 1)); spaces(1)
  print(woe(12345678, 1234)); newline()
  print(chance(0)); spaces(1); print(chance(2000)); spaces(1)
  print(chance(-2000)); spaces(1); print(chance(4771)); newline()
  return 0
end""")
        a, b = out.splitlines()
        w = [int(x) for x in a.split()]
        self.assertEqual(w[:2], [2000, -2000])
        self.assertAlmostEqual(w[2], 301, delta=1)
        self.assertEqual(w[3], 0)
        self.assertAlmostEqual(w[4], 4000, delta=2)
        c = [int(x) for x in b.split()]
        self.assertEqual(c[0], 50000)
        self.assertAlmostEqual(c[1], 99010, delta=30)
        self.assertAlmostEqual(c[2], 990, delta=10)
        self.assertAlmostEqual(c[3], 99998, delta=2)

    def test_compile_errors(self):
        with self.assertRaisesRegex(CompileError, "declared twice"):
            whale.compile_source("item a, a\nproc main() = 0\n", "t.whl")
        with self.assertRaisesRegex(CompileError, "expected 'is'"):
            whale.compile_source("item a, b\nproc main()\nbegin\n"
                                 "  make a of b\nend\n", "t.whl")


class TestDemos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "jobs", "whale.job")) as f:
            deck = f.read().replace("../", ROOT + "/")
        sat = run_job(deck)
        for job in sat.jobs:
            assert not job.failed, "\n".join(job.log)
        cls.out = {job.name: job.steps[0].output for job in sat.jobs}

    def test_tour(self):
        out = self.out["WHALE"]
        self.assertIn("colour of b1 is green: unknown", out)
        self.assertIn("colour of b1 is green: false", out)
        self.assertIn("b1 above b4", out)
        self.assertIn("b5: unknown", out)
        self.assertIn("b1 may be put on b5: true", out)
        self.assertIn("+21.0 db true   -21.0 db false", out)

    def test_diagnosis(self):
        out = self.out["DIAGNOSIS"]
        rows = dict(re.findall(r"\n   (in .*?|adding .*?|from .*?)\s{2,}"
                               r"(\d+\.\d\s+\d+\s+\d+\s+\d+)", out))
        q = {k: [float(x) for x in v.split()] for k, v in rows.items()}
        fixed, good = q["in a fixed order, 20 db"], q["in Good's order, 20 db"]
        # Good's order asks fewer questions and decides more
        self.assertLess(good[0], fixed[0] - 2)
        self.assertGreater(good[1], fixed[1])
        # Wald: a lower threshold, fewer questions and more mistakes
        lo, hi = q["in Good's order, 10 db"], q["in Good's order, 30 db"]
        self.assertLess(lo[0], good[0])
        self.assertGreater(lo[2], good[2])
        self.assertGreater(hi[3], good[3])
        # conditional weights are no worse than fixed ones
        self.assertLessEqual(good[2], q["adding fixed weights, 20 db"][2])
        self.assertIn("koplik_spots\n", out)
        self.assertIn("Diagnosis: measles", out)


if __name__ == "__main__":
    unittest.main()
