"""The front-panel recorder and the notebook."""

import ast
import json
import os
import unittest

from duwamish import panel
from tests.helpers import ROOT

MUL_DEMO = '''
        ENTRY START
START:  LD   R1, #12
        LD   R2, #-5
        MUL  R1, #0(R2)
        ST   R1, RESULT
        HLT
RESULT: DATA 0
'''

LOOP = '''
        ENTRY START
START:  LD   R1, #0
        LD   R2, #10
LOOP:   ADD  R1, #0(R2)
        SUB  R2, #1
        JP   LOOP
        HLT
'''


class TestRecorder(unittest.TestCase):
    def test_recording_is_exact(self):
        r = panel.record_triad(MUL_DEMO)
        rec = r.rec
        self.assertEqual(r.machine.rf[1], -60)
        # replaying the register deltas reproduces the machine's final state
        regs = rec.keyframes[0][:]
        for d in rec.deltas:
            for k in range(0, len(d), 2):
                regs[d[k]] = d[k + 1]
        self.assertEqual(regs, panel._state(r.machine))
        self.assertEqual(rec.clock[-1], r.machine.clock)
        # the write of the result appears as a memory write
        writes = [(a, v) for op, a, v in zip(rec.memop, rec.memaddr, rec.memval)
                  if op == 2]
        self.assertIn((r.obj.symbols["RESULT"], -60), writes)
        names = [row[0] for row in panel.instruction_costs(r)]
        self.assertIn("MUL", names)

    def test_page_is_self_contained(self):
        page = panel.page_html(panel.record_triad(MUL_DEMO))
        self.assertNotIn("__DATA__", page)
        # no external resources: everything is inline
        self.assertNotIn("<script src", page)
        self.assertNotIn("<link", page)
        blob = page.split("const D = ", 1)[1].split(";\nconst N", 1)[0]
        data = json.loads(blob)
        self.assertEqual(len(data["upc"]), len(data["deltas"]))

    def test_fused_instruction_saves_cycles(self):
        before = panel.record_triad(LOOP)
        after = panel.record_triad(
            LOOP, wcs=True,
            setup=lambda m, obj: panel.fuse(m, obj.symbols["LOOP"], 3))
        self.assertEqual(before.machine.rf[1], 55)
        self.assertEqual(after.machine.rf[1], 55)
        self.assertLess(after.machine.clock, before.machine.clock)
        self.assertTrue(any(c["invented"] for c in after.rec.cs))

    def test_whole_job_with_executive(self):
        r = panel.record_salish(
            'proc main() begin prints("OK"); newline() end', max_frames=40000)
        text = "".join(chr(c) for f, c in r.rec.output)
        self.assertIn("OK\n", text)
        self.assertTrue(any("SUPERVISOR CALL" in e for f, e in r.rec.events))


class TestHeapView(unittest.TestCase):
    def test_heap_recording(self):
        """The recorded heap agrees with what TRILISP itself reports, and
        the sweep leaves no marks behind."""
        from duwamish import heapview
        lisp = ("(DEFINE BUILD (LAMBDA (N) (COND ((EQ N 0) NIL) "
                "(T (CONS N (BUILD (- N 1)))))))\n" + "(BUILD 300)\n" * 12)
        r = heapview.record_heap(lisp, heap=729)
        gcs = r.stats[-1][3]
        self.assertGreater(gcs, 0)
        self.assertIn(f"{gcs} GARBAGE COLLECTIONS", r.output)
        self.assertTrue(any(s[2] > 0 for s in r.stats))        # marks seen
        self.assertEqual(r.stats[-1][2], 0)                     # none left
        # replaying the deltas from any keyframe reproduces the next one
        keys = sorted(r.keyframes)
        state = [int(c) for c in r.keyframes[keys[0]]]
        for f in range(keys[0] + 1, keys[1] + 1):
            d = r.frames[f][1]
            for k in range(0, len(d), 2):
                state[d[k]] = d[k + 1]
        self.assertEqual("".join(map(str, state)), r.keyframes[keys[1]])
        page = heapview.page_html(r)
        self.assertNotIn("http", page.split("<script>")[1])


class TestLifeView(unittest.TestCase):
    def test_recording(self):
        from duwamish import lifeview
        rec = lifeview.record_life()
        one, two = rec.frames[1], rec.frames[2]
        self.assertEqual([f[0] for f in one], list(range(17)))
        self.assertEqual([f[0] for f in two], list(range(15)))
        # sound: where both know a cell, they agree
        for gen, kleene, truth in one:
            for a, b in zip(kleene, truth):
                self.assertTrue(a == "u" or b == "u" or a == b, gen)
        # and incomplete: the program's own table, at generation 8
        self.assertEqual(one[8][1].count("u"), 124)
        self.assertEqual(one[8][2].count("u"), 7)
        self.assertEqual(two[-1][1].count("u"), 729)
        page = lifeview.page_html(rec, 1)
        self.assertNotIn("http", page.split("<script>")[1])


class TestHomeoView(unittest.TestCase):
    def test_recording(self):
        from duwamish import homeoview
        rec = homeoview.record_homeostat()
        parts = [f[1] for f in rec.frames]
        self.assertEqual(sorted(set(parts)), [1, 2, 3])
        self.assertEqual(parts, sorted(parts))
        ts = [f[0] for f in rec.frames]
        self.assertEqual(ts, list(range(ts[0], ts[0] + len(ts))))
        moves = {p: sum(sum(f[14:18]) for f in rec.frames if f[1] == p)
                 for p in (1, 2, 3)}
        self.assertEqual(moves[2], 0)
        self.assertGreater(moves[1], 0)
        self.assertGreater(moves[3], 0)
        # the switches stop moving once the field is stable
        self.assertEqual(rec.frames[0][18], 0)
        for p in (1, 2, 3):
            self.assertEqual([f[18] for f in rec.frames if f[1] == p][-1], 1)
        self.assertIsNotNone(rec.reversed)
        page = homeoview.page_html(rec)
        self.assertNotIn("http", page.split("<script>")[1])


class TestNotebook(unittest.TestCase):
    def test_notebook_is_valid(self):
        path = os.path.join(ROOT, "notebooks", "duwamish.ipynb")
        with open(path) as f:
            nb = json.load(f)
        self.assertEqual(nb["nbformat"], 4)
        for cell in nb["cells"]:
            if cell["cell_type"] == "code":
                ast.parse("".join(cell["source"]))
                self.assertEqual(cell["outputs"], [])


if __name__ == "__main__":
    unittest.main()
