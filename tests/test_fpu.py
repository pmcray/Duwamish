"""The floating-point unit: its arithmetic, both models, and the software
library that shares its format."""

import random
import unittest

from duwamish import fpu, isa, machine, triad
from duwamish import ternary as t
from tests.helpers import run_salish

ULP = 1 / 3 ** 21


class TestArithmetic(unittest.TestCase):
    def test_round_trip_and_sign(self):
        rng = random.Random(7)
        for _ in range(2000):
            x = rng.uniform(-1, 1) * 10 ** rng.randint(-20, 20)
            w = fpu.from_float(x)
            self.assertLessEqual(abs(fpu.to_float(w) - x), abs(x) * ULP)
            _, c = fpu.operate("FAD", w, 0)
            self.assertEqual(c, (x > 0) - (x < 0))

    def test_operations_round_once(self):
        rng = random.Random(8)
        for _ in range(1000):
            a = fpu.from_float(rng.uniform(-50, 50))
            b = fpu.from_float(rng.uniform(-50, 50))
            fa, fb = fpu.to_float(a), fpu.to_float(b)
            for name, f in (("FAD", fa + fb), ("FSB", fa - fb),
                            ("FMP", fa * fb), ("FDV", fa / fb)):
                v, _ = fpu.operate(name, a, b)
                self.assertLessEqual(abs(fpu.to_float(v) - f),
                                     abs(f) * ULP * 1.0001, name)

    def test_conversions(self):
        self.assertEqual(fpu.fix(fpu.flt(1967)), 1967)
        self.assertEqual(fpu.fix(fpu.from_float(-2.6)), -3)
        self.assertEqual(fpu.fcm(fpu.flt(2), fpu.flt(3)), -1)
        with self.assertRaises(fpu.FPUDivideByZero):
            fpu.fdiv(fpu.flt(1), 0)


class TestModels(unittest.TestCase):
    def test_random_programs_agree_with_fpu(self):
        """With the unit fitted, the microprogrammed and hardwired models
        must still agree exactly, floating-point instructions included."""
        rng = random.Random(1972)
        names = ["LD", "ST", "ADD", "FAD", "FSB", "FMP", "FDV", "FLT", "FIX",
                 "FCM", "JN", "JZ", "JP"]
        for trial in range(150):
            words = {}
            base = 2000
            for i in range(40):
                words[base + i] = rng.choice(
                    [0, rng.randint(-1000, 1000),
                     fpu.from_float(rng.uniform(-1e3, 1e3)),
                     rng.randint(-t.WMAX, t.WMAX)])
            code = []
            for i in range(20):
                name = rng.choice(names)
                op, form = isa.BY_NAME[name]
                m = rng.choice([0, 0, 1])
                addr = base + rng.randint(0, 39) if m == 0 else rng.randint(-40, 40)
                x = 0
                if name.startswith("J"):
                    addr, m = 100 + len(code) + rng.randint(1, 2), 0
                if name == "ST":
                    m = 0
                code.append(isa.encode(op, rng.randint(1, 6), x, m, addr))
            code.append(isa.encode(isa.BY_NAME["HLT"][0]))
            for i, w in enumerate(code):
                words[100 + i] = w
            results = []
            for model in (30, 90):
                mc = machine.Machine(model=model, fpu=True)
                mc.load_image(words)
                mc.poke(isa.LOC_TRAP_VEC, 100 + len(code) - 1)
                mc.rf = [0, 5, 7, -3, fpu.flt(3), fpu.from_float(0.25), 0, 0, 3000]
                mc.mode = machine.USER
                mc.pc = 100
                mc.run(max_cycles=10 ** 6, max_instructions=1000)
                data = [mc.peek(a) for a in range(-7, 0)] + \
                       [mc.peek(base + i) for i in range(40)]
                results.append((mc.rf, mc.c, data))
            self.assertEqual(results[0], results[1], f"trial {trial}")

    def test_unfitted_machine_takes_program_check_11(self):
        obj = triad.assemble("        ENTRY S\nS:      FLT R1, #3\n        HLT\n")
        for model in (30, 90):
            m = machine.Machine(model=model, fpu=False)
            m.load_image(obj.image())
            m.poke(isa.LOC_TRAP_VEC, 5000)
            m.poke(5000, isa.encode(isa.BY_NAME["HLT"][0]))
            m.mode = machine.USER
            m.pc = obj.entry
            m.run(max_cycles=10000, max_instructions=100)
            self.assertEqual(m.peek(isa.LOC_TRAP_CODE), isa.TRAP_FPU)


class TestSoftwareAgreesWithHardware(unittest.TestCase):
    def test_tfloat_matches_the_unit(self):
        src = '''
get "tfloat"
global vals := table(1, -2, 7, 1967, -729, 13, 100000, -3)
proc main()
begin
  var a, b, s, h
  for i := 0 to 7 do
    for j := 0 to 7 do begin
      a := tf_from_ratio(vals[i], 7)
      b := tf_from_ratio(vals[j], 11)
      s := tf_add(a, b); h := fadd(a, b)
      print(tf_mant(s) - tf_mant(h)); space(); print(tf_exp(s) - tf_exp(h)); space()
      s := tf_mul(a, b); h := fmul(a, b)
      print(tf_mant(s) - tf_mant(h)); space(); print(tf_exp(s) - tf_exp(h)); newline()
    end
end'''
        out, res = run_salish(src, model=90)
        self.assertEqual(res[0], 0, out)
        for line in out.split("\n"):
            if line.strip():
                dm1, de1, dm2, de2 = map(int, line.split())
                self.assertEqual((de1, de2), (0, 0), line)
                self.assertEqual(dm1, 0, line)            # add: exact
                self.assertEqual(dm2, 0, line)            # multiply: exact

    def test_tfloat_agrees_to_the_trit_at_the_extremes(self):
        """Random operands, near-cancelling pairs, and exponents at the
        limits (overflow saturates, underflow gives zero)."""
        rng = random.Random(1967)
        ws = []
        for k in range(18):
            ws.append(fpu.from_float(rng.uniform(-1, 1) * 10 ** rng.randint(-8, 8)))
            if k % 3 == 0:
                m, e = fpu.unpack(ws[-1])
                ws.append(fpu.pack(-m + rng.randint(-40, 40), e))
        for e in (121, 120, -120, -121):
            m, _ = fpu.unpack(fpu.from_float(rng.uniform(-1, 1)))
            ws.append(fpu.pack(m, e))
        n = len(ws)
        src = f'''get "tfloat"
global vals := table({", ".join(map(str, ws))})
proc main()
begin
  var a, b, bad := 0
  for i := 0 to {n - 1} do
    for j := 0 to {n - 1} do begin
      a := vals[i]; b := vals[j]
      if tf_add(a, b) <> fadd(a, b) then bad := bad + 1
      if tf_sub(a, b) <> fsub(a, b) then bad := bad + 1
      if tf_mul(a, b) <> fmul(a, b) then bad := bad + 1
    end
  print(bad); newline()
end'''
        out, res = run_salish(src, model=90)
        self.assertEqual(res[0], 0, out)
        self.assertEqual(out.strip(), "0")


if __name__ == "__main__":
    unittest.main()
