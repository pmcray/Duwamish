"""The SALISH compiler, run through the Executive on the machine."""

import unittest

from duwamish import salish
from tests.helpers import run_salish


def out(src, **kw):
    return run_salish(src, **kw)[0]


class TestSalish(unittest.TestCase):
    def test_arithmetic_and_printing(self):
        self.assertEqual(out('''
proc main()
begin
  print(7 * 6); newline()
  print(-17 / 5); space(); print(-17 mod 5); newline()
  print(1 << 5); space(); print(100 >> 2); newline()
  printt(-8); newline()
end'''), "42\n-3 -2\n243 11\n0T1\n".replace("0T1", "T01"))

    def test_three_valued_logic(self):
        self.assertEqual(out('''
proc main()
begin
  truthname(true & unknown); space()
  truthname(false | unknown); space()
  truthname(not unknown); space()
  truthname(unknown and false); space()   -- McCarthy: left decides first
  truthname(false and unknown); space()
  truthname(3 < 4); space(); truthname(3 = 4)
end'''), "unknown unknown unknown unknown false true false")

    def test_sign_of(self):
        self.assertEqual(out('''
proc cls(x)
begin
  sign x - 10 of
    -: prints("below ")
    0: prints("equal ")
    +: prints("above ")
  end
end
proc main()
begin
  cls(3); cls(10); cls(99)
end'''), "below equal above ")

    def test_loops_vectors_recursion(self):
        self.assertEqual(out('''
global v[10]
proc fib(n) = n < 2 -> n, fib(n - 1) + fib(n - 2)
proc main()
begin
  var s := 0, i := 0, step := -3
  for k := 0 to 9 do v[k] := k * k
  for k := 9 to 0 by step do s := s + v[k]
  while i < 5 do i := i + 1
  repeat i := i - 2 until i < 0
  print(s); space(); print(i); space(); print(fib(15))
end'''), "126 -1 610")

    def test_strings_tables_pointers(self):
        self.assertEqual(out('''
global t := table(10, 20, 30)
global msg := "ternary"
proc apply2(f, x) = f(f(x))
proc inc(x) = x + 1
proc main()
begin
  var x := 5, p
  p := @x
  poke(p, 9)
  prints(msg); space(); print(t[2] + x); space(); print(apply2(inc, 40))
end'''), "ternary 39 42")

    def test_catch_and_throw(self):
        self.assertEqual(out('''
global env[3]
proc deep(n)
begin
  if n = 0 then throw(env, 7)
  deep(n - 1)
end
proc main()
begin
  var r := catchpoint(env)
  if r = 0 then begin prints("go "); deep(50) end
  else begin prints("caught "); print(r) end
end'''), "go caught 7")

    def test_inline(self):
        self.assertEqual(out('''
inline proc sq(x) = x * x
inline proc pos(x) = x > 0
proc main()
begin
  var n := 0
  for i := -3 to 3 do if pos(i) then n := n + sq(i)
  print(n)
end'''), "14")

    def test_read_cards(self):
        self.assertEqual(out('''
proc main()
begin
  var buf[80]
  while readline(buf, 79) do begin prints(buf); putc('/') end
end''', data="alpha\nbeta"), "alpha/beta/")

    def test_program_check_is_reported(self):
        o, res = run_salish('''
proc main()
begin
  prints("before ")
  poke(-5, 0)
end''')
        self.assertTrue(o.startswith("before "))
        self.assertEqual(res[0], 2)          # protection violation

    def test_models_agree(self):
        src = '''
proc main()
begin
  var f := 1
  for i := 1 to 20 do begin f := f * i; printt(f); newline() end
end'''
        self.assertEqual(run_salish(src, model=30)[0],
                         run_salish(src, model=90)[0])


class TestBloop(unittest.TestCase):
    def test_certified(self):
        asm, c = salish.compile_source('''
bloop
proc tri(n)
begin
  var s := 0
  for i := 1 to n do s := s + i
  return s
end
proc main() = print(tri(10))''')
        self.assertIn("terminates", c.bloop_report)

    def test_rejects_while_and_recursion(self):
        for body in ('''proc main() begin var n := 1  while n > 0 do n := n + 1 end''',
                     '''proc f(n) = f(n)
proc main() = f(1)''',
                     '''proc main() begin for i := 1 to 3 do i := 1 end'''):
            with self.assertRaises(salish.CompileError):
                salish.compile_source("bloop\n" + body)


if __name__ == "__main__":
    unittest.main()
