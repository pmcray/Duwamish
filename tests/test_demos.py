"""The demonstration programs: each must run and its in-machine checks pass."""

import os
import unittest

from tests.helpers import ROOT, run_file, run_job, run_lisp


class TestHofstadter(unittest.TestCase):
    def test_quine_reproduces_itself(self):
        out, res = run_file("programs/hofstadter/quine.sal")
        with open(os.path.join(ROOT, "programs/hofstadter/quine.sal")) as f:
            self.assertEqual(out, f.read())

    def test_selfref_becomes_true(self):
        out, _ = run_file("programs/hofstadter/selfref.sal")
        self.assertIn("-- false", out)
        self.assertIn("-- TRUE", out.split("4. reading myself again")[1])

    def test_miu_invariant(self):
        out, _ = run_file("programs/hofstadter/miu.sal")
        self.assertIn("MU found?  no", out)
        self.assertIn("was 0 in 0 of", out)

    def test_bloop_certifies_and_refuses(self):
        sat = run_job("//JOB A\n//SALISH FROM=programs/hofstadter/sequences.sal"
                      "\n//EXEC\n//JOB B\n//SALISH\nbloop\n"
                      'get "programs/hofstadter/floop"\n//EXEC\n')
        a, b = sat.jobs
        self.assertTrue(any("BlooP certificate" in m for m in a.log))
        self.assertIn("confirmed", a.steps[0].output)
        self.assertTrue(b.failed)
        self.assertTrue(any("while loop in steps" in m for m in b.log))

    def test_lisp_quine_and_tags(self):
        out = run_lisp("""
(define q '((lambda (x) (list x (list 'quote x))) '(lambda (x) (list x (list 'quote x)))))
(equal (eval q) q)
(list (tag 1) (tag 'a) (tag '(a)))
(word 42)""")
        self.assertIn("  T\n", out)
        self.assertIn("(1 -1 0)", out)
        self.assertIn("  127\n", out)


class TestGood(unittest.TestCase):
    def test_goodturing_estimate_is_close(self):
        out, _ = run_file("programs/good/goodturing.sal", data="data/genesis.txt")
        est = float(out.split("N1/N         = ")[1].split("= ")[1].split()[0])
        truth = float(out.split("unseen species' mass)  = ")[1].split()[0])
        self.assertLess(abs(est - truth), 0.02)

    def test_explosion_preserves_answers(self):
        out, res = run_file("programs/good/explosion.sal", wcs=True, model=90)
        self.assertEqual(res[0], 0, out[-500:])
        self.assertIn("invented OP-1", out)
        self.assertNotIn("DIFFERENT ANSWER", out)

    def test_go_learns_and_shows_its_evidence(self):
        import re
        from tests.helpers import run_salish
        with open(os.path.join(ROOT, "programs/good/go.sal")) as f:
            src = f.read()
        src = re.sub(r"const ROUNDS = 3, TRAIN = 100, TEST = 10",
                     "const ROUNDS = 1, TRAIN = 20, TEST = 2", src)
        out, res = run_salish(src)
        self.assertEqual(res[0], 0, out[-500:])
        self.assertIn("filling its own eye", out)
        self.assertRegex(out, r"area score -?\d+")

    def test_draughts_learns_and_reports(self):
        import re
        from tests.helpers import run_salish
        with open(os.path.join(ROOT, "programs/good/draughts.sal")) as f:
            src = f.read()
        src = re.sub(r"const TRAIN = 20, TEST = 20",
                     "const TRAIN = 2, TEST = 1", src)
        src = re.sub(r"const DEPTH = 2, OPENING = 4, MAXPLY = 100",
                     "const DEPTH = 2, OPENING = 4, MAXPLY = 30", src)
        out, res = run_salish(src)
        self.assertEqual(res[0], 0, out[-500:])
        self.assertIn("settled judgement", out)
        self.assertRegex(out, r"won \d+, drew \d+, lost \d+")

    def test_chess_move_generation_perft(self):
        import re
        from tests.helpers import run_salish
        with open(os.path.join(ROOT, "programs/good/chess.sal")) as f:
            src = f.read()
        src = re.sub(r"const PERFT = 0 ", "const PERFT = 3 ", src)
        out, res = run_salish(src)
        # checked against an independent implementation of the rules
        self.assertIn("perft 1 10\nperft 2 100\nperft 3 1212\n", out)

    def test_backgammon_learns_and_reports(self):
        import re
        from tests.helpers import run_salish
        with open(os.path.join(ROOT, "programs/good/backgammon.sal")) as f:
            src = f.read()
        src = re.sub(r"const TRAIN = 30, EVERY = 15, TEST = 8",
                     "const TRAIN = 2, EVERY = 2, TEST = 1", src)
        out, res = run_salish(src)
        self.assertEqual(res[0], 0, out[-500:])
        self.assertIn("what it learned", out)

    def test_explosion_needs_the_key(self):
        sat = run_job("//JOB E KEY=WCS\n//SALISH FROM=programs/good/"
                      "explosion.sal\n//EXEC\n")
        self.assertTrue(sat.jobs[0].failed)


if __name__ == "__main__":
    unittest.main()
