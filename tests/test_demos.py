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


class TestLivermore(unittest.TestCase):
    def test_answers_match_double_precision(self):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        from livermore_reference import reference
        out, res = run_file("programs/livermore.sal")
        self.assertEqual(res[0], 0, out[-500:])
        ref = reference()
        seen = 0
        for line in out.splitlines():
            if line.startswith(" kernel") and "fixed" in line and "float" in line:
                parts = line.split()
                k, fixed, flt = int(parts[1]), int(parts[3]), int(parts[5])
                self.assertLessEqual(abs(fixed - ref[k]), 30, (k, fixed, ref[k]))
                self.assertLessEqual(abs(flt - ref[k]), 2, (k, flt, ref[k]))
                # the Model 90 has the floating-point unit
                self.assertEqual(parts[6], "hardware")
                self.assertLessEqual(abs(int(parts[7]) - ref[k]), 2, (k, parts[7]))
                seen += 1
        self.assertEqual(seen, 6)


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
        with open(os.path.join(ROOT, "programs/good/chessbase.sal")) as f:
            base = f.read()
        base, n = re.subn(r"const PERFT = 0 ", "const PERFT = 3 ", base)
        self.assertEqual(n, 1)
        src = src.replace('get "chessbase"', base)
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


def run_variant(path, replacements):
    """Run a demonstration with some of its constants changed."""
    with open(os.path.join(ROOT, path)) as f:
        src = f.read()
    for a, b in replacements:
        assert a in src, a
        src = src.replace(a, b)
    base = os.path.dirname(os.path.join(ROOT, path))
    src = src.replace('get "chessbase"', f'get "{base}/chessbase.sal"')
    sat = run_job("//JOB V\n//SALISH OPT\n" + src + "\n//EXEC\n")
    job = sat.jobs[0]
    if job.failed:
        raise AssertionError("\n".join(job.log))
    return job.steps[0].output, job.steps[0].result


class TestCopycat(unittest.TestCase):
    def test_answers(self):
        out, res = run_variant("programs/hofstadter/copycat.sal", [
            ("const RUNS = 30 ", "const RUNS = 12 "),
            ('  problem("iijjkk")\n', ""), ('  problem("mrrjjj")\n', ""),
            ('  problem("xyz")\n', "")])
        self.assertEqual(res[:2], (0, 0), out)
        ijk = out.split("ijk -> ?")[1].split("kji -> ?")[0].split()
        self.assertEqual(ijk[0], "ijl")                 # the commonest answer
        kji = out.split("kji -> ?")[1]
        self.assertIn("kjh", kji)                       # the change slips
        self.assertIn("lji", kji)                       # the position slips


class TestFiveYearPlan(unittest.TestCase):
    def test_a_short_match(self):
        out, res = run_variant("programs/good/fiveyear.sal", [
            ("const GAMEPLIES = 80 ", "const GAMEPLIES = 6 "),
            ("const OPENINGS = 3", "const OPENINGS = 1")])
        self.assertEqual(res[:2], (0, 0), out)
        self.assertEqual(out.count("result:"), 2)
        self.assertIn("positions searched per move", out)


class TestPerceptron(unittest.TestCase):
    def test_learning_evidence_and_the_limit(self):
        out, res = run_file("programs/good/perceptron.sal", optimise=True)
        self.assertEqual(res[:2], (0, 0), out)
        seen, unseen = out.split("the whole retina seen")[1].split(
            "a third of the retina unseen")
        def row(text, name):
            line = [l for l in text.splitlines() if name in l][0]
            return [int(x) for x in line.split()[-3:]]
        p, c, g = (row(seen, n) for n in ("perceptron   ", "cautious",
                                          "Good's"))
        self.assertGreater(p[0], 160)             # learned: over 80% right
        self.assertLess(c[1], p[1])               # caution: fewer wrong ...
        self.assertGreater(c[2], p[2])            # ... more "don't know"
        self.assertGreater(g[0], 150)             # evidence counted in one pass
        # half-seen patterns: the forced choice errs, the evidence abstains
        p2, g2 = row(unseen, "perceptron   "), row(unseen, "Good's")
        self.assertLess(g2[1], p2[1])
        self.assertGreater(g2[2], p2[2])
        # Minsky and Papert: only order 5 learns the parity of five points
        self.assertIn("learned in", out.split("\n         5")[1].split("\n")[0])
        for k in "1234":
            self.assertIn("not learned", out.split(f"\n         {k}")[1]
                          .split("\n")[0])
        self.assertIn("After every pass", out)
