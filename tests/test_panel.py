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
