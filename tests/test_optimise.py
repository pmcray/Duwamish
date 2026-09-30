"""SALISH/O, the optimising compiler: it must never change what a program
computes, and it must actually make the code better."""

import random
import re
import unittest

from duwamish import salish
from tests.helpers import run_file, run_lisp, run_salish


def both(src, **kw):
    plain = run_salish(src, **kw)
    fast = run_salish(src, optimise=True, **kw)
    return plain, fast


class RandomProgram:
    """A random SALISH program that uses everything the optimiser touches:
    locals and parameters, counted loops up and down with break and next,
    while loops, fixed and local vectors, updates in place, nested calls,
    recursion, three-way sign statements."""

    def __init__(self, seed):
        self.r = random.Random(seed)
        self.nproc = 0
        self.vecs = ["gv", "lv"]

    def expr(self, names, depth, procs):
        r = self.r
        if depth <= 0 or r.random() < 0.3:
            c = r.random()
            if c < 0.35 or not names:
                return str(r.randint(-40, 40))
            if c < 0.8:
                return r.choice(names)
            vec = r.choice(self.vecs)
            return f"{vec}[{self.index(names)}]"
        c = r.random()
        a = self.expr(names, depth - 1, procs)
        b = self.expr(names, depth - 1, procs)
        if c < 0.45:
            return f"({a} {r.choice(['+', '-', '*', '&', '|'])} {b})"
        if c < 0.55:
            return f"({a} {r.choice(['/', 'mod'])} {r.choice([2, 3, 7, -5])})"
        if c < 0.62:
            return f"({a} {r.choice(['<<', '>>'])} {r.randint(0, 3)})"
        if c < 0.70:
            return f"(- {a})"         # not "--": that begins a comment
        if c < 0.78:
            return f"({a} {r.choice(['<', '<=', '=', '<>', '>', '>='])} {b})"
        if c < 0.86:
            return f"({a} < {b} -> {a}, {b})"
        if c < 0.92 and procs:
            p = r.choice(procs)
            return f"{p}({a}, {b})"
        return f"rec({a} mod 6)"

    def index(self, names):
        r = self.r
        if names and r.random() < 0.6:
            v = r.choice(names)
            return f"(({v}) mod 5 + 5 + {r.randint(0, 2)})"
        return str(r.randint(0, 11))

    def stmts(self, names, depth, procs, loopvars, n):
        r = self.r
        out = []
        for _ in range(n):
            c = r.random()
            e = self.expr(names, 2, procs)
            assignable = [v for v in names if v not in loopvars]
            if c < 0.25 and assignable:
                v = r.choice(assignable)
                op = r.choice([":=", ":=", "+:=", "-:="])
                out.append(f"{v} {op} {e}")
            elif c < 0.35:
                out.append(f"{r.choice(['gv', 'lv'])}[{self.index(names)}] := {e}")
            elif c < 0.42:
                out.append(f"gs := gs + {e}")
            elif c < 0.60 and depth > 0:
                k = f"k{depth}{r.randint(0, 9)}"
                lo, hi = r.randint(-3, 3), r.randint(-2, 8)
                step = r.choice(["", "", " by 2", " by -1", " by -2"])
                if "-" in step:
                    lo, hi = hi, lo
                if r.random() < 0.3 and assignable:
                    hi = f"({r.choice(assignable)} mod 4 + 4)" if "-" not in \
                        step else f"(-({r.choice(assignable)} mod 3))"
                body = self.stmts(names + [k], depth - 1, procs,
                                  loopvars + [k], r.randint(1, 3))
                if r.random() < 0.2:
                    body.append(f"if {k} = 2 then next")
                if r.random() < 0.2:
                    body.append(f"if {k} = 5 then break")
                out.append(f"for {k} := {lo} to {hi}{step} do begin "
                           + "; ".join(body) + " end")
            elif c < 0.68 and depth > 0:
                w = f"w{depth}"
                body = self.stmts(names, depth - 1, procs, loopvars, 2)
                out.append(f"begin var {w} := 0; while {w} < {r.randint(1, 4)}"
                           f" do begin {w} := {w} + 1; "
                           + "; ".join(body) + " end end")
            elif c < 0.78 and depth > 0:
                a = self.stmts(names, depth - 1, procs, loopvars, 1)
                b = self.stmts(names, depth - 1, procs, loopvars, 1)
                out.append(f"if {self.expr(names, 1, procs)} < "
                           f"{self.expr(names, 1, procs)} then begin "
                           f"{'; '.join(a)} end else begin {'; '.join(b)} end")
            elif c < 0.85 and depth > 0:
                arms = [self.stmts(names, depth - 1, procs, loopvars, 1)
                        for _ in range(3)]
                out.append(f"sign {e} of - : begin {'; '.join(arms[0])} end "
                           f"0 : begin {'; '.join(arms[1])} end "
                           f"+ : begin {'; '.join(arms[2])} end end")
            else:
                out.append(f"print({e}); space()")
        return out

    def proc(self, procs):
        name = f"f{self.nproc}"
        self.nproc += 1
        names = ["a", "b", "x", "y", "z"]
        body = self.stmts(names, 2, procs, [], self.r.randint(3, 6))
        self.vecs = ["gv"]                 # lv is not declared yet
        init = self.expr(["a", "b"], 2, procs)
        self.vecs = ["gv", "lv"]
        return (f"proc {name}(a, b)\nbegin\n"
                f"  var x := {init}, y := a, z, "
                f"lv[12]\n"
                f"  for i := 0 to 11 do lv[i] := i * {self.r.randint(-5, 5)} + a\n"
                + "".join(f"  {s}\n" for s in body)
                + f"  return {self.expr(names, 2, procs)}\nend\n"), name

    def program(self):
        procs = []
        text = ("global gv[12], gs\n"
                "proc rec(n) = n <= 0 -> 1, n + rec(n - 1)\n")
        for _ in range(3):
            t, name = self.proc(procs)
            text += t
            procs.append(name)
        text += "proc main()\nbegin\n"
        for i in range(4):
            text += (f"  print({self.r.choice(procs)}({self.r.randint(-9, 9)}, "
                     f"{self.r.randint(-9, 9)})); newline()\n")
        text += ("  for i := 0 to 11 do begin print(gv[i]); space() end\n"
                 "  newline(); print(gs); newline()\nend\n")
        return text


class TestSameResults(unittest.TestCase):
    def test_random_programs(self):
        """Random programs print the same, optimised or not."""
        for seed in range(60):
            src = RandomProgram(seed).program()
            (o1, r1), (o2, r2) = both(src)
            self.assertEqual((o1, r1[:2]), (o2, r2[:2]), f"seed {seed}:\n{src}")

    def test_registers_survive_calls_and_recursion(self):
        src = """
proc fib(n)
begin
  var a := 0, b := 1, t
  for i := 1 to n do begin t := a + b; a := b; b := t end
  return a
end
proc deep(n, acc)
begin
  var s := 0
  for i := 1 to 3 do s := s + fib(i + n)
  if n = 0 then return acc + s
  return deep(n - 1, acc + s)
end
proc main()
begin
  var total := 0
  for k := 1 to 5 do total := total + deep(k, 0) * k
  print(total); newline()
end"""
        (o1, _), (o2, _) = both(src)
        self.assertEqual(o1, o2)
        self.assertTrue(o1.strip())

    def test_throw_restores_registers(self):
        """A throw passes through procedures holding registers; the catcher
        and its callers must find theirs as they left them."""
        src = """
global buf[3]
proc thrower(n)
begin
  var s := 0
  for i := 1 to n do s := s + i
  if n > 3 then throw(buf, s)
  return s
end
proc middle(n)
begin
  var t := 100
  for j := 1 to 2 do t := t + thrower(n + j)
  return t
end
proc catcher(n)
begin
  var r
  r := catchpoint(buf)
  if r <> 0 then return r * 1000
  return middle(n)
end
proc main()
begin
  var acc := 0
  for k := 0 to 4 do begin
    acc := acc + catcher(k)
    print(acc); space()
  end
  newline()
end"""
        (o1, _), (o2, _) = both(src)
        self.assertEqual(o1, o2)

    def test_trilisp_collects_garbage_when_optimised(self):
        """TRILISP's collector scans the stack for roots; register variables
        must be spilled there first, or live cells would be swept."""
        prog = ("(DEFINE BUILD (LAMBDA (N) (COND ((EQ N 0) NIL) "
                "(T (CONS N (BUILD (- N 1)))))))\n"
                "(DEFINE LEN (LAMBDA (L) (COND ((NULL L) 0) "
                "(T (+ 1 (LEN (CDR L)))))))\n"
                + "(LEN (BUILD 200))\n" * 25)
        plain = run_lisp(prog)
        fast = run_lisp(prog, optimise=True)
        self.assertEqual(plain, fast)
        m = re.search(r"(\d+) GARBAGE COLLECTIONS", fast)
        self.assertTrue(m and int(m.group(1)) > 0, fast[-300:])

    def test_demonstrations(self):
        for path in ("programs/hello.sal", "programs/kleene.sal",
                     "programs/hofstadter/miu.sal",
                     "programs/hofstadter/sequences.sal",
                     "programs/good/goodturing.sal"):
            data = "data/genesis.txt" if "goodturing" in path else None
            plain = run_file(path, data=data)
            fast = run_file(path, data=data, optimise=True)
            self.assertEqual(plain[0], fast[0], path)
            self.assertLess(fast[1][4], plain[1][4], path)   # instructions


class TestBetterCode(unittest.TestCase):
    def loop_body(self, src, marker):
        asm, comp = salish.compile_source(src, optimise=True)
        lines = asm.splitlines()
        i = next(k for k, x in enumerate(lines) if marker in x)
        # from the loop's top label to its closing conditional jump
        top = next(k for k in range(i, len(lines)) if re.match(r"L\d+:", lines[k]))
        end = next(k for k in range(top, len(lines))
                   if lines[k].split()[0:1] == ["JNP"])
        return [x.split()[0] for x in lines[top + 1:end + 1]
                if x.startswith("        ")]

    def test_inner_product_is_six_instructions(self):
        src = """
global x[100], y[100]
proc main()
begin
  var s := 0
  x[0] := 1
  for k := 0 to 99 do s := fadd(s, fmul(x[k], y[k]))
  print(s)
end"""
        body = self.loop_body(src, "LD   R4, #0")
        self.assertEqual(body, ["LD", "FMP", "FAD", "ADD", "CMP", "JNP"])

    def test_listing_names_the_registers(self):
        src = "proc main()\nbegin\n  var s := 0\n  for i := 1 to 10 do s := s + i\n  print(s)\nend"
        asm, _ = salish.compile_source(src, optimise=True)
        self.assertRegex(asm, r"; proc main\(\)   registers: R3=\w+, R4=\w+")

    def test_plain_compiler_unchanged(self):
        """Without OPT the compiler emits what it always did."""
        src = "proc main()\nbegin\n  var s := 0\n  for i := 1 to 10 do s := s + i\n  print(s)\nend"
        asm, _ = salish.compile_source(src)
        self.assertNotIn("R3", asm.split("CODE_END")[0].split("; proc main")[1])
        self.assertIn("JMP  L", asm)


if __name__ == "__main__":
    unittest.main()
