"""SALISH/S, the SALISH compiler written in SALISH, and the card punch
and punched-deck job control that let the Duwamish compile its own
compiler."""

import os
import unittest

from duwamish import salish
from tests.helpers import ROOT, run_job

COMPILER = os.path.join(ROOT, "programs/selfhost/salish.sal")
RUNTIME = os.path.join(ROOT, "duwamish/lib/runtime.sal")


def compile_on_the_duwamish(path, optimise=False):
    """Generation 0 compiles one program; returns (the punched deck, step)."""
    sat = run_job(f"//JOB S\n//SALISH FROM={COMPILER}\n//EXEC\n"
                  + ("//DATA\n-- OPT\n" if optimise else "")
                  + f"//DATA FROM={path}\n//DATA FROM={RUNTIME}\n")
    step = sat.jobs[0].steps[0]
    return step.punched, step


class TestSalishS(unittest.TestCase):
    def test_same_code_as_the_satellite(self):
        """For an ordinary program, the punched deck is exactly what the
        satellite's compiler produces."""
        for name in ("programs/kleene.sal", "programs/hofstadter/miu.sal"):
            path = os.path.join(ROOT, name)
            deck, step = compile_on_the_duwamish(path)
            with open(path) as f:
                want, _ = salish.compile_source(f.read(), path)
            self.assertEqual(step.result[0], 0, step.output)
            self.assertEqual(deck, want, name)

    def test_optimising_like_the_satellite(self):
        """With -- OPT on its first card, SALISH/S punches what SALISH/O
        prints: the register plan, the peephole pass and all."""
        for name in ("programs/kleene.sal", "programs/good/banburismus.sal"):
            path = os.path.join(ROOT, name)
            deck, step = compile_on_the_duwamish(path, optimise=True)
            with open(path) as f:
                want, _ = salish.compile_source(f.read(), path, optimise=True)
            self.assertEqual(deck, want, name)

    def test_random_programs_both_ways(self):
        import tempfile
        from tests.test_optimise import RandomProgram
        for seed in (3, 17, 29):
            src = RandomProgram(seed).program()
            with tempfile.NamedTemporaryFile("w", suffix=".sal",
                                             delete=False) as f:
                f.write(src)
            try:
                for o in (False, True):
                    deck, _ = compile_on_the_duwamish(f.name, optimise=o)
                    want, _ = salish.compile_source(src, f.name, optimise=o)
                    self.assertEqual(deck, want, f"seed {seed} opt={o}")
            finally:
                os.unlink(f.name)

    def test_generation_one_is_the_optimised_compiler(self):
        """The plain compiler, optimising itself, punches exactly the
        satellite's optimised compilation of it (jobs/improve.job, step 1)."""
        deck, step = compile_on_the_duwamish(COMPILER, optimise=True)
        with open(COMPILER) as f:
            want, _ = salish.compile_source(f.read(), COMPILER, optimise=True)
        self.assertEqual(deck, want)

    def test_errors_are_reported(self):
        sat = run_job(f"//JOB S\n//SALISH FROM={COMPILER}\n//EXEC\n"
                      "//DATA\nproc main()\nbegin\n  x := 1\nend\n")
        step = sat.jobs[0].steps[0]
        self.assertIn("undeclared name x", step.output)
        self.assertEqual(step.result[:2], (0, 2))       # EXIT 2
        self.assertNotIn("CODE_END", step.punched)     # no complete deck

    def test_the_bootstrap_closes_on_itself(self):
        """jobs/bootstrap.job: generation 0 compiles the compiler; the deck
        it punches is the satellite's own compilation, card for card, so
        generation 1 is the same program; it compiles the compiler again,
        identically, and generation 2 compiles and runs hello."""
        with open(os.path.join(ROOT, "jobs/bootstrap.job")) as f:
            deck = f.read().replace("../", ROOT + "/")
        sat = run_job(deck)
        steps = sat.jobs[0].steps
        self.assertEqual([s.result[0] for s in steps], [0, 0, 0, 0])
        self.assertIn("identical, card for card, to the satellite's own "
                      "compilation", steps[1].messages[0])
        self.assertIn("identical, card for card, to the deck of step 1",
                      steps[2].messages[0])
        self.assertIn("HELLO FROM THE DUWAMISH", steps[3].output)


class TestPunch(unittest.TestCase):
    def test_a_program_that_writes_a_program(self):
        """A SALISH program punches a TRIAD program; the next step runs it."""
        src = '''
proc card(s)
begin
  for i := 1 to s[0] do punch(s[i])
  punch('\\n')
end
proc main()
begin
  card("        ENTRY GO")
  card("GO:     LD   R1, #'*'")
  card("        SVC  1")
  card("        SVC  0")
end'''
        sat = run_job("//JOB P\n//SALISH\n" + src + "\n//EXEC\n"
                      "//TRIAD PUNCHED\n//EXEC\n")
        a, b = sat.jobs[0].steps
        self.assertEqual(a.punched.count("\n"), 4)
        self.assertIn("4 cards", b.messages[0])
        self.assertEqual(b.output, "*")

    def test_nothing_punched(self):
        sat = run_job("//JOB P\n//SALISH\nproc main() = 0\n//EXEC\n"
                      "//TRIAD PUNCHED\n//EXEC\n")
        b = sat.jobs[0].steps[1]
        self.assertIsNone(b.result)
        self.assertIn("punched no cards", b.messages[0])


if __name__ == "__main__":
    unittest.main()
