"""TRI-TRAN, the Duwamish FORTRAN: the language, its library, and random
programs checked against a model of the machine's arithmetic."""

import math
import os
import random
import unittest
from fractions import Fraction

from duwamish import fpu, tritran
from duwamish import ternary as t
from tests.helpers import ROOT, run_job


def run_tritran(src, data=None, model=90):
    deck = "//JOB T\n//TRITRAN\n" + src + "\n//EXEC\n"
    if data is not None:
        deck += "//DATA\n" + data + "\n"
    sat = run_job(deck, model)
    job = sat.jobs[0]
    if job.failed:
        raise AssertionError("\n".join(job.log))
    step = job.steps[0]
    return step.output, step.result, sat


def compile_error(src):
    try:
        tritran.compile_source(src, "T")
    except tritran.CompileError as e:
        return str(e)
    raise AssertionError("no error")


def card(s):
    return "      " + s


class TestLanguage(unittest.TestCase):
    def test_cards(self):
        src = "\n".join([
            "C     A COMMENT",
            "*     ANOTHER",
            "      I = 1",
            "      J = 2 +",
            "     1    3",
            "      PRINT 10, I, J",
            "   10 FORMAT (1X, 2I3)",
            "      END"])
        out, res, _ = run_tritran(src)
        self.assertEqual(out, "  1  5\n")

    def test_blanks_mean_nothing(self):
        # DO 10 I = 1.10 is an assignment to DO10I; DO 10 I = 1,10 a loop
        src = "\n".join([
            card("D O 1 0 I = 1.10"),
            card("N = 0"),
            card("DO 20 I = 1,10"),
            "   20 N = N + 1",
            card("PRINT 30, N, DO10I"),
            "   30 FORMAT (1X, I3, F6.2)",
            card("END")])
        out, _, _ = run_tritran(src)
        self.assertEqual(out, " 10  1.10\n")

    def test_columns_73_to_80_are_ignored(self):
        src = "\n".join([card("I = 12").ljust(72) + "345678",
                         card("PRINT 1, I"), "    1 FORMAT (1X, I8)",
                         card("END")])
        self.assertEqual(run_tritran(src)[0], "      12\n")

    def test_do_runs_at_least_once(self):
        src = "\n".join([card("N = 0"), card("DO 10 I = 5, 1"),
                         "   10 N = N + 1", card("PRINT 1, N, I"),
                         "    1 FORMAT (1X, 2I3)", card("END")])
        self.assertEqual(run_tritran(src)[0], "  1  6\n")

    def test_three_valued_logic(self):
        src = "\n".join([
            card("LOGICAL T, F, U, V(9)"),
            card("T = .TRUE."), card("F = .FALSE."), card("U = .UNKNOWN."),
            card("V(1) = T .AND. U"), card("V(2) = F .AND. U"),
            card("V(3) = T .OR. U"), card("V(4) = F .OR. U"),
            card("V(5) = .NOT. U"), card("V(6) = U .EQV. F"),
            card("V(7) = T .EQV. F"), card("V(8) = 1 .LT. 2"),
            card("V(9) = U .NEQV. U"),
            card("PRINT 1, V"), "    1 FORMAT (1X, 9L2)",
            card("IF (U) PRINT 2"), card("IF (.NOT. U) PRINT 2"),
            card("IF (U .OR. T) PRINT 3"),
            card("IF (U) 4, 5, 6"),
            "    4 PRINT 7", card("STOP"),
            "    5 PRINT 8", card("STOP"),
            "    6 PRINT 7",
            "    2 FORMAT (4H NO!)", "    3 FORMAT (4H YES)",
            "    7 FORMAT (6H WRONG)", "    8 FORMAT (8H UNKNOWN)",
            card("END")])
        out, _, _ = run_tritran(src)
        self.assertEqual(out, " U F T U U U F T U\nYES\nUNKNOWN\n")

    def test_arithmetic_if_is_one_j3(self):
        src = "\n".join([card("I = 2"), card("IF (I - 3) 10, 20, 30"),
                         "   10 STOP 1", "   20 STOP 2", "   30 STOP 3",
                         card("END")])
        asm, _ = tritran.compile_source(src)
        self.assertEqual(asm.split("; SALISH")[0].count("J3   "), 1)
        _, res, sat = run_tritran(src)
        self.assertEqual(res[:2], (0, 1))
        self.assertIn("STOP 1", sat.machine.text(sat.machine.tty))

    def test_index_registers(self):
        """FORTRAN I's index registers: the inner product is one loop of
        seven instructions."""
        src = "\n".join([card("DIMENSION A(100), B(100)"), card("S = 0.0"),
                         card("DO 10 K = 1, 100"),
                         "   10 S = S + A(K)*B(K)", card("END")])
        asm, _ = tritran.compile_source(src)
        body = asm.split("_MAIN._2:")[1].split("ST   R3")[0]
        ops = [l.split()[0] for l in body.splitlines()
               if l.startswith("        ") and l.strip()]
        self.assertEqual(ops, ["LD", "FMP", "FAD", "ST", "ADD", "CMP", "JNP"])
        self.assertIn("LD   R1, _MAIN.A-1(R3)", asm)

    def test_subprograms(self):
        src = """      DIMENSION V(4)
      COMMON /C/ N
      EXTERNAL TWICE
      DATA V /1.0, 2.0, 3.0, 4.0/
      N = 0
      CALL SCALE(V, 4, 2.5)
      PRINT 1, V, N, APPLY(TWICE, 7.0)
    1 FORMAT (1X, 4F6.2, I3, F6.1)
      END
      SUBROUTINE SCALE(A, M, F)
      DIMENSION A(M)
      COMMON /C/ NCALLS
      DO 10 I = 1, M
   10 A(I) = A(I) * F
      NCALLS = NCALLS + 1
      END
      FUNCTION APPLY(G, X)
      APPLY = G(X) + 1.0
      END
      FUNCTION TWICE(Y)
      TWICE = 2.0 * Y
      RETURN
      END"""
        self.assertEqual(run_tritran(src)[0],
                         "  2.50  5.00  7.50 10.00  1  15.0\n")

    def test_arguments_by_reference(self):
        """A constant passed to a subroutine that changes its argument is
        changed, as on the machines of 1966."""
        src = """      CALL BUMP(1)
      I = 1
      PRINT 10, I
   10 FORMAT (1X, I3)
      J = 5
      CALL BUMP(J)
      PRINT 10, J
      END
      SUBROUTINE BUMP(K)
      K = K + 1
      END"""
        out, _, _ = run_tritran(src)
        # I = 1 loads 1 as an immediate, so only the literal pool changed
        self.assertEqual(out, "  1\n  6\n")

    def test_jump_out_of_a_loop_keeps_the_index(self):
        src = "\n".join([card("DO 10 I = 1, 100"),
                         card("IF (I*I .GT. 50) GO TO 20"),
                         "   10 CONTINUE", "   20 PRINT 1, I",
                         "    1 FORMAT (1X, I3)", card("END")])
        self.assertEqual(run_tritran(src)[0], "  8\n")

    def test_errors(self):
        cases = [
            ([card("GO TO 99"), card("END")], "no statement number 99"),
            ([card("X = SQRT(2)"), card("END")], "must be REAL"),
            ([card("CALL NOSUCH"), card("END")], "no subprogram NOSUCH"),
            ([card("I = LONGNAME1"), card("END")], "longer than six"),
            ([card("DO 10 I = 1, 2"), card("DO 20 J = 1, 2"),
              "   10 CONTINUE", "   20 CONTINUE", card("END")], "overlap"),
            ([card("PRINT 5"), "    5 FORMAT (5HABC)", card("END")],
             "Hollerith runs off the card"),
            ([card("I = 1")], "no END"),
            ([card("X = F(1.0)"), card("END"), card("INTEGER FUNCTION F(Y)"),
              card("F = 1"), card("END")], "declare it INTEGER"),
            ([card("CALL S(1)"), card("END"), card("SUBROUTINE S(A, B)"),
              card("END")], "takes 2 arguments"),
            ([card("EQUIVALENCE (A, B)"), card("END")], "no EQUIVALENCE"),
        ]
        for lines, msg in cases:
            self.assertIn(msg, compile_error("\n".join(lines)), lines)


class TestFormat(unittest.TestCase):
    def out(self, fmt, *values, decl=""):
        items = ", ".join(values)
        src = "\n".join(([card(decl)] if decl else []) +
                        [card(f"PRINT 1{', ' + items if items else ''}"),
                         f"    1 FORMAT ({fmt})", card("END")])
        return run_tritran(src)[0]

    def test_fields(self):
        self.assertEqual(self.out("1X, I5, I3, I2", "42", "-7", "123"),
                         "   42 -7**\n")
        # (2.25 is not a ternary fraction: -2.26 has no tie to round)
        self.assertEqual(self.out("1X, F8.3, F6.1, F5.3, F4.3, F4.2",
                                  "3.14159", "-2.26", "0.5", "0.5", "123.0"),
                         "   3.142  -2.30.500.500****\n")
        self.assertEqual(self.out("1X, E12.4, E11.3, E12.4",
                                  "6.02E23", "-1.6E-19", "0.0"),
                         "  0.6020E+24 -0.160E-18  0.0000E+00\n")
        self.assertEqual(self.out("1X, 3B6", "42", "-42", "0"),
                         " 1TTT0 T1110     0\n")
        self.assertEqual(self.out("1X, 3L2", ".TRUE.", ".FALSE.",
                                  ".UNKNOWN."), " T F U\n")
        self.assertEqual(self.out("1X, 'IT''S', 3X, 4HDONE"), "IT'S   DONE\n")

    def test_carriage_control_and_slash(self):
        self.assertEqual(self.out("1H0, I2 / 1X, I2", "1", "2"),
                         "\n 1\n 2\n")

    def test_reversion(self):
        # the list outlasts the format: a new record, from the last group
        self.assertEqual(self.out("5H LIST/ (1X, 2I3)", "1", "2", "3", "4",
                                  "5"), "LIST\n  1  2\n  3  4\n  5\n")
        # a group does not start a record by itself
        self.assertEqual(self.out("5H LIST, (1X, 2I3)", "1", "2", "3"),
                         "LIST   1  2\n  3\n")

    def test_input(self):
        src = """      DIMENSION X(4)
      LOGICAL L
      READ 1, I, J, X, L, K
    1 FORMAT (2I4 / 4F6.2 / L3, B6)
      PRINT 2, I, J, X, L, K
    2 FORMAT (1X, 2I5, 4F8.3, L2, I5)
   10 READ (5, 3, END=20) M
    3 FORMAT (I5)
      N = N + M
      GO TO 10
   20 PRINT 4, N
    4 FORMAT (1X, I5)
      END"""
        data = ("  12  -3\n"
                "  1.25  -2.5    75   1E2\n"
                "  T   1T1\n"
                "   10\n   20\n   30")
        out, _, _ = run_tritran(src, data)
        # 75 has no point, so F6.2 reads it as 0.75; and 1E2 as 0.01 E2
        self.assertEqual(out, "   12   -3   1.250  -2.500   0.750   1.000"
                              " T    7\n   60\n")

    def test_blanks_are_zeros(self):
        src = """      READ 1, I
    1 FORMAT (I5)
      PRINT 2, I
    2 FORMAT (1X, I6)
      END"""
        self.assertEqual(run_tritran(src, "12")[0], " 12000\n")


class TestLibrary(unittest.TestCase):
    def test_functions(self):
        args = [0.3, 1.0, 2.5, 10.0, -1.7, 0.05]
        funcs = {"SQRT": math.sqrt, "EXP": math.exp, "ALOG": math.log,
                 "ALOG10": math.log10, "SIN": math.sin, "COS": math.cos,
                 "ATAN": math.atan, "TANH": math.tanh}
        lines = []
        want = []
        for name, f in funcs.items():
            for a in args:
                if name in ("SQRT", "ALOG", "ALOG10") and a <= 0:
                    continue
                lines.append(card(f"PRINT 1, {name}({a!r})"))
                want.append(f(a))
        lines += ["    1 FORMAT (1X, E18.10)", card("END")]
        out, _, _ = run_tritran("\n".join(lines))
        got = [float(x.replace("E", "e")) for x in out.split()]
        for g, w in zip(got, want):
            # ten significant digits are printed
            self.assertLess(abs(g - w), 1e-9 * max(1.0, abs(w)), (g, w))

    def test_powers(self):
        src = """      PRINT 1, 3**5, 2**20, (-2)**3, 5**0, 7**(-1), 1**(-5)
      PRINT 2, 2.0**10, 1.5**(-3), 2.0**0.5, 10.0**(-2)
    1 FORMAT (1X, 6I8)
    2 FORMAT (1X, 4F12.6)
      END"""
        out, _, _ = run_tritran(src)
        self.assertEqual(out, "     243 1048576      -8       1       0       1\n"
                              " 1024.000000    0.296296    1.414214    0.010000\n")


class TestLivermore(unittest.TestCase):
    def test_same_words_as_salish(self):
        """The TRI-TRAN kernels compute exactly the words the SALISH
        program computes on the floating-point unit."""
        sat = run_job("//JOB L\n//TRITRAN FROM="
                      + os.path.join(ROOT, "programs/livermore.ftn")
                      + "\n//EXEC\n//SALISH OPT FROM="
                      + os.path.join(ROOT, "programs/livermore.sal")
                      + "\n//EXEC\n")
        a, b = sat.jobs[0].steps
        mine = [int(l.split()[-1]) for l in a.output.splitlines()
                if l.strip()[:2].strip().isdigit() and len(l.split()) == 5]
        theirs = [int(l.split()[-1]) for l in b.output.splitlines()
                  if l.startswith(" kernel ") and "hardware" in l]
        self.assertEqual(len(mine), 6)
        self.assertEqual(mine, theirs)


class TestPrograms(unittest.TestCase):
    def test_tour(self):
        with open(os.path.join(ROOT, "jobs/tritran.job")) as f:
            deck = f.read().replace("../", ROOT + "/")
        deck = deck.split("//JOB LIVERMORE")[0]
        out = run_job(deck).jobs[0].steps[0].output
        self.assertIn("      U   F U U          U   U U T          U   U U U",
                      out)
        self.assertNotIn("NEVER", out)
        self.assertIn("2 NEGATIVE,  2 ZERO,  3 POSITIVE", out)
        self.assertIn("     60               1T1T0      -60               T1T10",
                      out)
        self.assertIn("   1.00    1.00000000    2.71828183    0.84147098", out)

    def test_goods_prime_factor_algorithm(self):
        sat = run_job("//JOB PFA\n//TRITRAN FROM="
                      + os.path.join(ROOT, "programs/good/pfa.ftn")
                      + "\n//EXEC\n")
        out = sat.jobs[0].steps[0].output
        rows = {l.split()[0]: l.split() for l in out.splitlines()
                if l.strip().startswith(("DIRECT", "COOLEY", "GOOD 27"))}
        self.assertEqual(rows["DIRECT"][2], "46656")
        self.assertEqual(rows["COOLEY-TUKEY"][3], "1192")
        self.assertEqual(rows["GOOD"][4], "880")
        for r in ("COOLEY-TUKEY", "GOOD"):
            self.assertLess(float(rows[r][-1].replace("E", "e")), 1e-7)
        # the spectrum: 54 at 7 and 101, -27i at 30, +27i at 78, else 0
        peaks = [l.split() for l in out.splitlines()
                 if len(l.split()) == 4 and l.split()[0].isdigit()]
        self.assertEqual([(p[0], p[3]) for p in peaks],
                         [("7", "54.00000"), ("30", "27.00000"),
                          ("78", "27.00000"), ("101", "54.00000")])
        self.assertIn("SAVE  312 MULTIPLICATIONS", out)


# ----------------------------------------------------------------------
#  random programs
# ----------------------------------------------------------------------
def ifix(w):
    return int(fpu.value(w))          # truncation toward zero


class RandomProgram:
    """A random TRI-TRAN program of INTEGER and REAL arithmetic, subscripts,
    DO loops (whose indices go into registers), logical and arithmetic IFs,
    with a Python model of what it must print.  The REAL results are
    printed as words, through COMMON, so they are compared exactly."""

    IV = ["IA", "IB", "IC", "ID"]
    XV = ["XA", "XB", "XC"]

    def __init__(self, seed):
        self.r = random.Random(seed)
        self.env = {}
        self.lab = 100

    def label(self):
        self.lab += 10
        return self.lab

    # expressions: (fortran text, python function of env)
    def iexpr(self, depth, idx=()):
        r = self.r
        if depth <= 0 or r.random() < 0.3:
            c = r.random()
            if c < 0.3:
                v = r.randint(-30, 30)
                return (f"({v})" if v < 0 else str(v)), (lambda e, v=v: v)
            if c < 0.6 or not idx:
                n = r.choice(self.IV + list(idx))
                return n, (lambda e, n=n: e[n])
            k = r.choice(idx)
            off = r.randint(0, 2)
            text = f"IV({k}+{off})" if off else f"IV({k})"
            return text, (lambda e, k=k, o=off: e["IV"][e[k] + o - 1])
        c = r.random()
        a, fa = self.iexpr(depth - 1, idx)
        b, fb = self.iexpr(depth - 1, idx)
        if c < 0.5:
            op = r.choice("+-*")
            f = {"+": lambda x, y: t.wrap(x + y), "-": lambda x, y: t.wrap(x - y),
                 "*": lambda x, y: t.wrap(x * y)}[op]
            return f"({a}{op}{b})", (lambda e: f(fa(e), fb(e)))
        if c < 0.62:
            d = r.choice([2, 3, 7, -5])
            return f"({a}/({d}))", (lambda e: t.trunc_div(fa(e), d))
        if c < 0.72:
            d = r.choice([2, 3, 7, -5])
            return f"MOD({a},{d})", (lambda e: t.trunc_mod(fa(e), d))
        if c < 0.8:
            return f"(-{a})", (lambda e: -fa(e))
        if c < 0.88:
            m = r.choice(["MAX0", "MIN0"])
            f = max if m == "MAX0" else min
            return f"{m}({a},{b})", (lambda e: f(fa(e), fb(e)))
        return f"IABS({a})", (lambda e: abs(fa(e)))

    def rexpr(self, depth, idx=()):
        r = self.r
        if depth <= 0 or r.random() < 0.3:
            c = r.random()
            if c < 0.3:
                v = r.choice(["0.5", "1.25", "3.0", "0.1", "7.5", "100.0"])
                w = tritran.real_word(v)
                return v, (lambda e, w=w: w)
            if c < 0.45:
                a, fa = self.iexpr(1, idx)
                return f"FLOAT({a})", (lambda e: fpu.flt(fa(e)))
            if c < 0.75 or not idx:
                n = r.choice(self.XV)
                return n, (lambda e, n=n: e[n])
            k = r.choice(idx)
            return f"XV({k})", (lambda e, k=k: e["XV"][e[k] - 1])
        c = r.random()
        a, fa = self.rexpr(depth - 1, idx)
        b, fb = self.rexpr(depth - 1, idx)
        if c < 0.7:
            op = r.choice("+-*")
            f = {"+": fpu.fadd, "-": fpu.fsub, "*": fpu.fmul}[op]
            return f"({a}{op}{b})", (lambda e: f(fa(e), fb(e)))
        if c < 0.8:
            d = r.choice(["2.0", "3.0", "0.25", "5.0"])
            w = tritran.real_word(d)
            return f"({a}/{d})", (lambda e: fpu.fdiv(fa(e), w))
        if c < 0.9:
            # mixed mode: the INTEGER is converted
            i, fi = self.iexpr(1, idx)
            return f"({a}+{i})", (lambda e: fpu.fadd(fa(e), fpu.flt(fi(e))))
        return f"ABS({a})", (lambda e: fpu.normalise(abs(fpu.value(fa(e)))))

    def cond(self, idx=()):
        r = self.r
        rel = r.choice(["LT", "LE", "EQ", "NE", "GT", "GE"])
        fr = {"LT": lambda d: d < 0, "LE": lambda d: d <= 0,
              "EQ": lambda d: d == 0, "NE": lambda d: d != 0,
              "GT": lambda d: d > 0, "GE": lambda d: d >= 0}[rel]
        if r.random() < 0.5:
            a, fa = self.iexpr(1, idx)
            b, fb = self.iexpr(1, idx)
            one = (f"{a}.{rel}.{b}", lambda e: 1 if fr(fa(e) - fb(e)) else -1)
        else:
            a, fa = self.rexpr(1, idx)
            b, fb = self.rexpr(1, idx)
            one = (f"{a}.{rel}.{b}",
                   lambda e: 1 if fr(fpu.fcm(fa(e), fb(e))) else -1)
        c = r.random()
        if c < 0.2:
            return f".NOT.({one[0]})", (lambda e: -one[1](e))
        if c < 0.35:
            return f"({one[0]}).AND.LU", (lambda e: min(one[1](e), e["LU"]))
        if c < 0.5:
            return f"({one[0]}).OR.LU", (lambda e: max(one[1](e), e["LU"]))
        return one

    def assign(self, idx=()):
        """One assignment statement: (text, python action)."""
        r = self.r
        c = r.random()
        if c < 0.4:
            n = r.choice(self.IV)
            a, fa = self.iexpr(2, idx)

            def act(e, n=n, fa=fa):
                e[n] = fa(e)
            return f"{n} = {a}", act
        if c < 0.7:
            n = r.choice(self.XV)
            a, fa = self.rexpr(2, idx)

            def act(e, n=n, fa=fa):
                e[n] = fa(e)
            return f"{n} = {a}", act
        if c < 0.85:
            # a REAL assigned to an INTEGER is truncated
            n = r.choice(self.IV)
            a, fa = self.rexpr(1, idx)

            def act(e, n=n, fa=fa):
                e[n] = ifix(fa(e))
            return f"{n} = {a}", act
        if idx:
            k = idx[-1]
            a, fa = self.rexpr(2, idx)

            def act(e, k=k, fa=fa):
                e["XV"][e[k] - 1] = fa(e)
            return f"XV({k}) = {a}", act
        a, fa = self.iexpr(2, idx)
        s = r.randint(1, 10)

        def act(e, s=s, fa=fa):
            e["IV"][s - 1] = fa(e)
        return f"IV({s}) = {a}", act

    def program(self):
        r = self.r
        lines, acts = [], []
        env = {"IA": 3, "IB": -2, "IC": 5, "ID": 1, "LU": 0,
               "IV": [r.randint(-20, 20) for _ in range(12)]}
        for n, v in zip(self.XV, ["1.5", "-0.75", "2.0"]):
            env[n] = tritran.real_word(v)
        env["XV"] = [tritran.real_word(str(k + 0.5)) for k in range(12)]
        self.env = env
        lines.append("      COMMON /W/ XA, XB, XC, XV(12)")
        lines.append("      INTEGER IV(12)")
        lines.append("      LOGICAL LU")
        lines.append("      DATA IV /" + ", ".join(str(v) for v in env["IV"])
                     + "/")
        lines.append("      IA = 3")
        lines.append("      IB = -2")
        lines.append("      IC = 5")
        lines.append("      ID = 1")
        lines.append("      LU = .UNKNOWN.")
        lines.append("      XA = 1.5")
        lines.append("      XB = -0.75")
        lines.append("      XC = 2.0")
        lines.append("      DO 10 K = 1, 12")
        lines.append("   10 XV(K) = FLOAT(K) - 0.5")
        for _ in range(r.randint(6, 12)):
            c = r.random()
            if c < 0.35:
                text, act = self.assign()
                lines.append("      " + text)
                acts.append(act)
            elif c < 0.55:
                lab = self.label()
                hi = r.randint(1, 4)
                inner = [self.assign(("K",)) for _ in range(r.randint(1, 3))]
                lines.append(f"      DO {lab} K = 1, {hi}")
                for text, _ in inner[:-1]:
                    lines.append("      " + text)
                lines.append(f"{lab:5} " + inner[-1][0])

                def act(e, hi=hi, inner=inner):
                    for k in range(1, hi + 1):
                        e["K"] = k
                        for _, a in inner:
                            a(e)
                acts.append(act)
            elif c < 0.7:
                lab = self.label()
                inner = self.assign(("K", "L"))
                lines.append(f"      DO {lab} L = 1, 3")
                lines.append(f"      DO {lab} K = 1, 2")
                lines.append(f"{lab:5} " + inner[0])

                def act(e, inner=inner):
                    for l in range(1, 4):
                        for k in range(1, 3):
                            e["L"], e["K"] = l, k
                            inner[1](e)
                acts.append(act)
            elif c < 0.77:
                # a dummy array with an adjustable bound, and an
                # expression passed by reference through a temporary
                n = r.randint(1, 12)
                a, fa = self.iexpr(1)
                lines.append(f"      CALL ACC(IV, {n}, {a})")

                def act(e, n=n, fa=fa):
                    x = fa(e)
                    for i in range(1, n + 1):
                        e["IV"][i - 1] = t.wrap(e["IV"][i - 1] + x * i)
                acts.append(act)
            elif c < 0.85:
                cond, fc = self.cond()
                text, a = self.assign()
                lines.append(f"      IF ({cond}) {text}")

                def act(e, fc=fc, a=a):
                    if fc(e) == 1:
                        a(e)
                acts.append(act)
            else:
                isreal = r.random() < 0.5
                x, fx = self.rexpr(2) if isreal else self.iexpr(2)
                l1, l2, l3, out = (self.label() for _ in range(4))
                arms = [self.assign() for _ in range(3)]
                lines.append(f"      IF ({x}) {l1}, {l2}, {l3}")
                for lab, (text, _) in zip((l1, l2, l3), arms):
                    lines.append(f"{lab:5} {text}")
                    lines.append(f"      GO TO {out}")
                lines.append(f"{out:5} CONTINUE")

                def act(e, fx=fx, arms=arms, isreal=isreal):
                    v = fpu.value(fx(e)) if isreal else fx(e)
                    arms[(v > 0) - (v < 0) + 1][1](e)
                acts.append(act)
        lines.append("      PRINT 900, IA, IB, IC, ID, IV")
        lines.append("  900 FORMAT (1X, 4I16 / (1X, 4I16))")
        lines.append("      CALL DUMP")
        lines.append("      END")
        lines.append("      SUBROUTINE ACC(M, N, IX)")
        lines.append("      DIMENSION M(N)")
        lines.append("      DO 10 I = 1, N")
        lines.append("   10 M(I) = M(I) + IX*I")
        lines.append("      END")
        lines.append("      SUBROUTINE DUMP")
        lines.append("      COMMON /W/ JW(15)")
        lines.append("      PRINT 900, JW")
        lines.append("  900 FORMAT (1X, 5I16)")
        lines.append("      END")
        return lines, acts


def fold(line):
    """A statement longer than a card goes on continuation cards."""
    cards = [line[:72]]
    rest = line[72:]
    while rest:
        cards.append("     1" + rest[:66])
        rest = rest[66:]
    return cards


class TestRandomPrograms(unittest.TestCase):
    def expected(self, prog, acts):
        e = prog.env
        e["XV"] = [fpu.fsub(fpu.flt(k), tritran.real_word("0.5"))
                   for k in range(1, 13)]
        for a in acts:
            a(e)
        ints = [e[n] for n in RandomProgram.IV] + e["IV"]
        words = [e[n] for n in RandomProgram.XV] + e["XV"]
        return ints, words

    def test_random_programs(self):
        done = 0
        for seed in range(60):
            prog = RandomProgram(seed)
            lines, acts = prog.program()
            try:
                ints, words = self.expected(prog, acts)
            except (ZeroDivisionError, fpu.FPUDivideByZero):
                continue
            if any(abs(fpu.value(w)) > 10 ** 9 for w in words) or \
                    any(abs(i) > 10 ** 12 for i in ints):
                continue
            src = "\n".join(c for line in lines for c in fold(line))
            out, res, _ = run_tritran(src)
            got = [int(x) for x in out.split()]
            self.assertEqual(res[:2], (0, 0), src)
            self.assertEqual(got[:16], ints, src)
            self.assertEqual(got[16:], words, src)
            done += 1
        self.assertGreater(done, 40)


if __name__ == "__main__":
    unittest.main()
