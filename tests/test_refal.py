"""Refal on the Duwamish: Turchin's language, interpreted in SALISH."""

import os
import unittest

from tests.helpers import ROOT, run_job


def refal(program, model=90):
    sat = run_job("//JOB R\n//EXEC REFAL\n//DATA\n" + program + "\n", model)
    job = sat.jobs[0]
    if job.failed:
        raise AssertionError("\n".join(job.log))
    return job.steps[0].output


def value(program):
    """The lines a program prints, without the closing statistics."""
    out = refal(program)
    return [l for l in out.splitlines() if l and not l.startswith("*** REFAL:")]


class TestPatterns(unittest.TestCase):
    def test_basics(self):
        self.assertEqual(value("""
$ENTRY Go { = <Prout <Reverse 'abc'>> <Prout <Pal 'abba'> <Pal 'ab'>>; }
Reverse { t.1 e.2 = <Reverse e.2> t.1; = ; }
Pal { = True; s.1 = True; s.1 e.2 s.1 = <Pal e.2>; e.1 = False; }
"""), ["cba", "True False"])

    def test_terms_and_structure(self):
        self.assertEqual(value("""
$ENTRY Go { = <Prout <F (a b) c>> <Prout <G ((x)) y>>; }
F { t.1 t.2 = t.2 t.1; }
G { ((s.1)) s.2 = s.2 s.1; }
"""), ["c(a b)", "y x"])

    def test_repeated_variables(self):
        self.assertEqual(value("""
$ENTRY Go { = <Prout <D 'abccd'> <D 'abcd'>> <Prout <Same (a b) (a b)> <Same (a) (b)>>; }
D { e.1 s.X s.X e.2 = s.X; e.1 = 'none'; }
Same { (e.1) (e.1) = True; e.1 = False; }
"""), ["cnone", "True False"])

    def test_condition_backtracks(self):
        self.assertEqual(value("""
$ENTRY Go { = <Prout <Split ',abc,de'>>; }
Split { e.1 ',' e.2, <Lenw e.1> : s.N e.3, <Compare s.N 0> : '+' = (e.1) (e.2); }
"""), ["(,abc)(de)"])

    def test_backtracking_through_brackets(self):
        # e.1 must be found inside the bracket for the rest to match
        self.assertEqual(value("""
$ENTRY Go { = <Prout <F (a b c) c>>; }
F { (e.1 s.X) s.X = e.1; }
"""), ["a b"])


class TestBuiltins(unittest.TestCase):
    def test_arithmetic_and_compare(self):
        self.assertEqual(value("""
$ENTRY Go { = <Prout <Add 2 3> <Sub 2 3> <Mul 6 7> <Div 7 2> <Mod 7 2>>
              <Prout <Compare 1 2> <Compare 2 2> <Compare 3 2>>
              <Prout <Numb '-42'> <Symb 1967>>; }
"""), ["5 -1 42 3 1", "-0+", "-421967"])

    def test_words_store_and_mu(self):
        self.assertEqual(value("""
$ENTRY Go { = <Br 'k' '=' 'v1'> <Prout <Cp 'k'> <Dg 'k'> <Dg 'k'> '.'>
              <Prout <Explode Turchin> <Mu Rev 1 2 3>>
              <Prout <Implode 'abc'>> <Prout <Lenw a b c>> <Prout <Type 'x'> <Type 7>>; }
Rev { t.1 e.2 = <Rev e.2> t.1; = ; }
"""), ["v1v1.", "Turchin3 2 1", "abc", "3 a b c", "LxN7"])


class TestMachine(unittest.TestCase):
    def test_storage_is_reclaimed(self):
        out = refal("""
$ENTRY Go { = <Prout <Count <Primes <Upto 2 800>>>>; }
Count { e.1 = <Count1 0 e.1>; }
Count1 { s.N = s.N; s.N t.1 e.2 = <Count1 <Add s.N 1> e.2>; }
Upto { s.A s.B, <Compare s.A s.B> : '+' = ; s.A s.B = s.A <Upto <Add s.A 1> s.B>; }
Primes { s.P e.Rest = s.P <Primes <Strike s.P e.Rest>>; = ; }
Strike { s.P s.N e.Rest, <Mod s.N s.P> : 0 = <Strike s.P e.Rest>;
         s.P s.N e.Rest = s.N <Strike s.P e.Rest>; s.P = ; }
""")
        self.assertTrue(out.startswith("139\n"))         # primes below 800
        n = int(out.split(" steps, ")[1].split(" collections")[0])
        self.assertGreater(n, 0)

    def test_tail_calls_run_in_constant_stack(self):
        self.assertEqual(value("""
$ENTRY Go { = <Prout <Loop 20000 0>>; }
Loop { 0 s.A = s.A; s.N s.A = <Loop <Sub s.N 1> <Add s.A 1>>; }
"""), ["20000"])

    def test_errors(self):
        out = refal("$ENTRY Go { = <F 1>; } F { 2 = 3; }")
        self.assertIn("RECOGNITION IMPOSSIBLE: <F 1>", out)
        out = refal("$ENTRY Go { = <F e.1>; }")
        self.assertIn("SYNTAX ERROR", out)

    def test_tour(self):
        with open(os.path.join(ROOT, "jobs", "refal.job")) as f:
            deck = f.read().replace("../", ROOT + "/")
        out = run_job(deck).jobs[0].steps[0].output
        for line in ("gfedcba", "True False", "6227020800",
                     "m0sc0w t0 n0v0sibirsk", "(,abc)(de)", "((x+x)+3)",
                     "4 5 26 26 31 32 32 35 38 38 43 46 50 79 79 89 159",
                     "Akademgorodok"):
            self.assertIn(line, out)
        self.assertIn("2 3 5 7 11 13", out)
        self.assertIn("193 197 199", out)


if __name__ == "__main__":
    unittest.main()
