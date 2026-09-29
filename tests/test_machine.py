"""The ternary arithmetic, the assemblers, and the two machine models."""

import random
import unittest

from duwamish import isa, machine, microasm, triad
from duwamish import ternary as t


class TestTernary(unittest.TestCase):
    def test_roundtrip(self):
        for v in [0, 1, -1, 13, -13, 12345678, t.WMAX, t.WMIN]:
            self.assertEqual(t.from_trits(t.trits(v)), v)
            self.assertEqual(t.from_tstr(t.to_tstr(v)), v)
            self.assertEqual(t.from_hept(t.to_hept(v)), v)

    def test_negation_is_trit_inversion(self):
        for v in [5, -7, 1000, t.WMAX]:
            self.assertEqual(t.trits(-v), [-x for x in t.trits(v)])

    def test_shift_rounds_to_nearest(self):
        for v in range(-50, 51):
            self.assertEqual(t.shift(v, -1), round(v / 3))

    def test_wrap(self):
        self.assertEqual(t.wrap(t.WMAX + 1), t.WMIN)
        self.assertEqual(t.wrap(t.WMIN - 1), t.WMAX)

    def test_kleene(self):
        self.assertEqual(t.tmin(1, 0), 0)
        self.assertEqual(t.tmax(-1, 0), 0)
        self.assertEqual(t.teqv(-1, -1), 1)

    def test_encode_decode(self):
        rng = random.Random(1)
        for _ in range(500):
            op = rng.randint(-121, 121)
            r, x = rng.randint(0, 8), rng.randint(0, 8)
            m = rng.randint(-4, 4)
            a = rng.randint(-isa.ADDR_MAX, isa.ADDR_MAX)
            self.assertEqual(isa.decode(isa.encode(op, r, x, m, a)),
                             (op, r, x, m, a))


class TestMicroprogram(unittest.TestCase):
    def test_every_factory_opcode_has_a_routine(self):
        mp = microasm.default_microprogram()
        for op, name, form, _ in isa.OPCODES:
            self.assertIn(name, mp.labels, name)
            self.assertEqual(mp.dispatch[op + 121], mp.labels[name])

    def test_microword_encoding_roundtrip(self):
        mp = microasm.default_microprogram()
        for ha, hb in mp.cs:
            f = microasm.decode(ha, hb)
            names = ("a", "b", "alu", "d", "mem", "setc", "pcinc", "lit")
            self.assertEqual(microasm.encode_a(**dict(zip(names, f[:8]))), ha)


FACT = r'''
        ENTRY START
START:  LD   SP, #1000
        LD   R1, #12
        PUSH R1
        CALL FACT
        HLT
FACT:   PUSH FP
        LEA  FP, 0(SP)
        LD   R1, 2(FP)
        CMP  R1, #1
        JP   REC
        LD   R1, #1
        JMP  DONE
REC:    SUB  R1, #1
        PUSH R1
        CALL FACT
        MUL  R1, 2(FP)
DONE:   LEA  SP, 0(FP)
        POP  FP
        RET  1
'''


class TestModels(unittest.TestCase):
    def run_both(self, src):
        obj = triad.assemble(src)
        out = []
        for model in (30, 90):
            m = machine.Machine(model=model)
            m.load_image(obj.image())
            m.pc = obj.entry
            self.assertEqual(m.run(max_cycles=10 ** 7), "halt")
            out.append(m)
        return out

    def test_factorial_both_models(self):
        m30, m90 = self.run_both(FACT)
        self.assertEqual(m30.rf[1], 479001600)
        self.assertEqual(m30.rf, m90.rf)
        self.assertEqual(m30.icount, m90.icount)

    def test_random_programs_agree(self):
        """Random straight-line programs, including ones that trap, must
        leave identical state on the microprogrammed and hardwired models:
        two implementations, one architecture."""
        rng = random.Random(1967)
        names = ["LD", "ST", "LEA", "ADD", "SUB", "MUL", "DIV", "MOD", "NEG",
                 "CMP", "TST", "AND", "OR", "EQV", "SHF", "XTR", "TRT", "SEL",
                 "PUSH", "POP", "NOP", "J3", "JN", "JZ", "JP", "JNN", "JNZ",
                 "JNP"]
        for trial in range(250):
            words = {}
            base = 2000
            for i in range(60):          # data area
                words[base + i] = rng.choice(
                    [0, 1, -1, rng.randint(-100, 100),
                     rng.randint(-t.WMAX, t.WMAX), base + rng.randint(0, 59)])
            code = []
            for i in range(25):
                name = rng.choice(names)
                op, form = isa.BY_NAME[name]
                r = rng.randint(0, 8)
                x = rng.choice([0, 0, 0, 1, 2])
                m = rng.choice([0, 0, 1, 1, -1, 2])
                addr = rng.choice([base + rng.randint(0, 50),
                                   rng.randint(-30, 30)])
                if name.startswith("J"):
                    addr = 100 + len(code) + rng.randint(1, 3)
                    m, x = 0, 0
                code.append(isa.encode(op, r, x, m, addr))
            code.append(isa.encode(isa.BY_NAME["HLT"][0]))
            for i, w in enumerate(code):
                words[100 + i] = w
            results = []
            for model in (30, 90):
                mc = machine.Machine(model=model)
                mc.load_image(words)
                mc.poke(isa.LOC_TRAP_VEC, 100 + len(code) - 1)
                mc.rf = [0, 5, base, 7, -3, 11, 0, base + 10, 3000]
                # run in user mode so that faults trap instead of halting
                mc.mode = machine.USER
                mc.pc = 100
                mc.run(max_cycles=10 ** 6, max_instructions=1000)
                data = [mc.peek(a) for a in range(-10, 0)] + \
                       [mc.peek(base + i) for i in range(60)] + \
                       [mc.peek(2990 + i) for i in range(11)]
                results.append((mc.rf, mc.c, mc.mode, data, mc.halted))
            self.assertEqual(results[0], results[1], f"trial {trial}")


class TestAssembler(unittest.TestCase):
    def test_literals_and_data(self):
        obj = triad.assemble('''
            ENTRY S
S:          LD R1, =123456789
            HLT
MSG:        STR "AB"
T:          DATA 1, -2, 0t1T, 'x'
''')
        lit = obj.symbols[".LIT0"]
        self.assertEqual(obj.words[lit], 123456789)
        m = obj.symbols["MSG"]
        self.assertEqual([obj.words[m + i] for i in range(3)], [2, 65, 66])
        tt = obj.symbols["T"]
        self.assertEqual([obj.words[tt + i] for i in range(4)],
                         [1, -2, 2, ord("x")])


if __name__ == "__main__":
    unittest.main()
