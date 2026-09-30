"""Build notebooks/duwamish.ipynb (no outputs; run it in Jupyter)."""

import json
import os

cells = []


def md(text):
    cells.append({"cell_type": "markdown", "metadata": {},
                  "source": text.strip("\n").splitlines(True)})


def code(text):
    cells.append({"cell_type": "code", "metadata": {}, "execution_count": None,
                  "outputs": [], "source": text.strip("\n").splitlines(True)})


md(r"""
# The Duwamish Computer — inside the machine

This notebook opens up the Duwamish, the balanced-ternary computer in this
repository, and shows it working, cycle by cycle.

Every animation here is **exact**. The notebook runs the real Model 30
micro-engine one micro-cycle at a time and records everything the console
would have shown: every register, the condition trit, the mode, the
micro-program counter, the control lines asserted, every read and write of
core, traps and the printer. The front panel then replays that recording,
so the lamps light in exactly the order the machine lit them.

**How to use the front panels.** Run each cell (or *Run All*). In a panel:

| control | does |
|---|---|
| **▶ run** / **❚❚ pause** | play the recording at the chosen speed |
| **step µ** | one micro-cycle |
| **step instr** | on to the start of the next instruction |
| **◀◀** / **⏮** | back one micro-cycle / back to the start |
| slider | scrub anywhere in the recording |
| speed | from 1 to 10,000 micro-cycles a second |

Lamps: **amber is +1, blue is −1, dark is 0**, which are the three values of a
trit. A register's row label turns amber when its value changed in the
micro-cycle just shown.

Needs only Python 3 and Jupyter (Notebook, Lab or VS Code); no extra packages.
""")

code(r"""
import os, sys
# make the duwamish package importable from the repository
here = os.path.abspath(os.getcwd())
while here != os.path.dirname(here) and not os.path.isdir(os.path.join(here, "duwamish")):
    here = os.path.dirname(here)
sys.path.insert(0, here)
os.chdir(here)

from duwamish import panel, ternary, isa, microasm, machine, satellite, salish, triad, fpu
print("Duwamish loaded from", here)
""")

md(r"""
## 1. Trits and words

A **trit** is −1, 0 or +1 (written `T`, `0`, `1`). A **word** is 27 trits,
holding every integer from −3,812,798,742,493 to +3,812,798,742,493.
Balanced ternary has no sign bit: a number is negative when its leading
non-zero trit is −1, and **negation is trit-by-trit inversion**. That
is why swapping the colours of the lamps negates the number.

Each row below shows the lamps, the decimal value, the balanced-ternary
digits and the *heptavintimal* notation (base 27, one letter per three
trits, nine letters per word) that the listings use.
""")

code(r"""
panel.show_words([("1", 1), ("-1", -1), ("2 = 1T", 2), ("13", 13), ("-13", -13),
                  ("1967", 1967), ("-1967", -1967), ("3^13", 3**13),
                  ("largest", ternary.WMAX), ("smallest", ternary.WMIN)])
""")

md(r"""
Truncating trits **rounds to the nearest integer**; it never chops toward
zero or toward minus infinity as binary does. Here is 1967 shifted right one
trit at a time: each step divides by 3, rounded.
""")

code(r"""
panel.show_words([(f">> {k}", ternary.shift(1967, -k)) for k in range(8)])
""")

md(r"""
## 2. The instruction word

An instruction is one word:

```
| op : 5 | r : 2 | x : 2 | m : 2 | addr : 16 |
```

These are an opcode, a register, an index register, an addressing mode
(−1 indirect, 0 direct, +1 immediate) and a 16-trit address. The factory
opcodes are all positive; the negative half is left free for instructions
the machine invents for itself (section 7).
""")

code(r"""
for text in ["LD   R1, #12", "ADD  R1, 2(FP)", "ST   R2, @X", "J3   Y", "SEL  R1, #-11"]:
    display(panel.show_instruction(text))
""")

md(r"""
## 3. The micro-engine at work: a ternary multiplication

The Model 30 has no multiplier. `MUL` is a *microprogram* that walks the
multiplier one trit at a time. Each trit is −1, 0 or +1, so each pass
**subtracts, skips or adds** the shifted multiplicand. The multiplier is
never recoded, and the loop stops as soon as what remains of it is zero.

The program below computes 12 × −5. In the panel, press **step instr**
until the `MUL` is executing (the program listing highlights it), then
**step µ** through it and watch:

* **CNT** holds the multiplier, 12 = `110` in balanced ternary. It loses
  one trit per pass: 12 → 4 → 1 → 0.
* **U** holds the multiplicand, and triples each pass: −5, −15, −45.
* **T** accumulates the product: skip, add, add, according to the trits of
  12 read from the right (0, then 1, then 1).
* The microprogram listing jumps three ways at each `CASE C`: the
  sequencer itself is ternary.
* The datapath shows which register drives the **A bus** (green) and the
  **B bus** (blue), what the ALU does, and where the **D bus** (amber)
  delivers the result. Core reads flash green, writes red.
""")

code(r"""
MUL_DEMO = '''
        ENTRY START
START:  LD   R1, #12        ; multiplier
        LD   R2, #-5        ; multiplicand
        MUL  R1, #0(R2)     ; R1 <- 12 x -5, by the microprogram
        ST   R1, RESULT
        PUSH R1
        POP  R3
        HLT
RESULT: DATA 0
'''
mul = panel.record_triad(MUL_DEMO, title="12 x -5 on the Model 30")
print("R1 =", mul.machine.rf[1], "  micro-cycles recorded:", len(mul.rec.upc))
panel.animate(mul, speed=30)
""")

md(r"""
What each instruction cost, measured from the recording. A core
reference adds four cycles of wait, which is why the fetch alone costs six.
""")

code(r"""
panel.show_costs(mul)
""")

md(r"""
## 4. Where things live in core

Core holds 3¹² = 531,441 words, addressed **symmetrically** from
−265,720 to +265,720. The negative half belongs to the Executive, the
resident operating system, and is protected: a user program that touches
it takes a protection trap. A compiled SALISH program is laid out like
this:

* the **code**, from word 100;
* the **globals, strings and literals**;
* the **heap**, which grows upward from the end of the program;
* the **stack**, which grows downward from the top of core.
""")

code(r"""
FACTORIAL = '''
-- factorials, printed in decimal and in balanced ternary
global facts[8]
proc fact(n) = n <= 1 -> 1, n * fact(n - 1)
proc main()
begin
  for i := 1 to 6 do begin
    facts[i] := fact(i)
    print(i); prints("! = "); print(facts[i]); prints(" = "); printt(facts[i]); newline()
  end
end
'''
asm, comp = salish.compile_source(FACTORIAL, "factorial.sal")
obj = triad.assemble(asm, origin=satellite.USER_ORIGIN)
panel.show_memory_map(obj)
""")

md(r"""
The first lines of the machine code the compiler produced:
""")

code(r"""
print("\n".join(obj.listing[:24]))
""")

md(r"""
## 5. A whole job: the Executive, a supervisor call, and back

Now the full system. The recording starts at the Executive's first
micro-cycle and runs to the halt. Things to find in the panel (the events
box lists the traps, and the slider jumps straight to them):

1. **Boot.** The Executive writes its greeting to the operator's console
   typewriter.
2. **The job arrives.** The Executive asks the satellite for work. The
   channel loads the program into core, and the *program* map fills.
3. **Into user mode.** An `RTI` starts the program. The **MODE** lamp turns
   blue (user), and `CALL P_main` pushes a return address onto the stack.
4. **Recursion.** `fact` calls itself. Watch **SP** walk down and the
   stack window fill with frames.
5. **A supervisor call.** To print, the program executes `SVC 1`. The
   micro-engine takes a trap: it writes the resume address, trap code and
   mode into the protected **trap words** (they flash red), switches MODE
   to supervisor and jumps into the Executive. The Executive saves the
   registers, sends the character to the printer with `OUT`, restores the
   registers and returns with `RTI`.
6. **Exit.** `SVC 0` reports the result to the satellite, and the Executive
   halts when there is no more work.

It is about 66,000 micro-cycles. Use the slider, or a high speed.
""")

code(r"""
job = panel.record_salish(FACTORIAL, title="factorial job, Executive and all", max_frames=80000)
print("micro-cycles:", len(job.rec.upc), "  printer output:")
print("".join(chr(c) for f, c in job.rec.output))
panel.animate(job, speed=60)
""")

md(r"""
### The same job, measured

The trap events, and what the instructions cost across the whole job:
""")

code(r"""
for f, e in job.rec.events[:6]:
    print(f"{f:7}  {e}")
print("...")
panel.show_costs(job)
""")

md(r"""
## 6. Two models of one architecture, and the Beer monitor

As with IBM's System/360, the architecture exists twice.

* The **Model 30** interprets every instruction with its microprogram.
* The **Model 90**, Cray's hardwired design, executes instructions
  directly.

They compute identical results; only the time differs. Every instruction
fetch also increments a hardware **tally** for its word of core: Stafford
Beer's idea that a system should watch itself. Here the tallies are read
out per procedure.
""")

code(r"""
def run(model):
    sat = satellite.run_program("programs/hello.sal", model=model, out=lambda s: None)
    return sat
m30, m90 = run(30), run(90)
for name, sat in (("Model 30", m30), ("Model 90", m90)):
    how, value, where, cycles, instrs, secs = sat.jobs[0].steps[0].result
    print(f"{name}: {instrs:,} instructions, {cycles:,} cycles = {cycles*0.2/1000:.1f} ms of 1967 time")
print("same printout:", m30.jobs[0].steps[0].output == m90.jobs[0].steps[0].output)
panel.show_tally(m90.machine, m90.jobs[0].steps[0].obj)
""")

md(r"""
## 7. The machine that rewrites its own microcode

This is the hardware behind the intelligence-explosion demonstration
(`programs/good/explosion.sal`). With the control-store key turned, a
program may write microcode. The loop below adds 10 + 9 + … + 1. We then
do what the explosion program does:

* copy the loop's three instructions into the fast **constant store**;
* write three microinstructions. Each is `IR <- K[k], PC+1, DISP next`: it
  loads a remembered instruction straight into IR and dispatches on it, as
  if it had just been fetched, but **without a core cycle**;
* point unused opcode **−1** at them, and patch the loop to use it.

In the second panel, step through a pass of the loop. The datapath shows
the **K store** driving IR, and no READ lamp lights for the second and
third instructions of the fused run. The microprogram listing shows the
invented microinstructions in green.
""")

code(r"""
LOOP = '''
        ENTRY START
START:  LD   R1, #0
        LD   R2, #10
LOOP:   ADD  R1, #0(R2)
        SUB  R2, #1
        JP   LOOP
        HLT
'''
before = panel.record_triad(LOOP, title="the loop, as written")
after = panel.record_triad(LOOP, title="the loop, as a new instruction", wcs=True,
                           setup=lambda m, obj: panel.fuse(m, obj.symbols["LOOP"], 3))
for name, r in (("as written", before), ("fused", after)):
    print(f"{name:10}  R1 = {r.machine.rf[1]}   {r.machine.clock} micro-cycles")
display(panel.show_costs(after))
panel.animate(after, speed=20)
""")

md(r"""
## 8. The floating-point feature

The Model 90 has a floating-point unit as standard, and the Model 30 can
be fitted with one. A float fills one word: a 5-trit exponent over a
22-trit mantissa, value = m × 3^(e−21). Both fields are balanced, so there
is no sign bit and no bias. The word is the sum e·3²² + m, which means **the
sign of a float is the sign of its mantissa, not of the word**. Here −2.0
is stored as a *positive* word, because its exponent is positive, and 1/3
as a *negative* one:
""")

code(r"""
for x in (2.0, -2.0, 1/3, -1e-6):
    w = fpu.from_float(x)
    m, e = fpu.unpack(w)
    print(f"{x:>8.4g}   exponent {e:4}   mantissa {m:15,}   word {w:18,}")
panel.show_words([("2.0", fpu.from_float(2.0)), ("-2.0", fpu.from_float(-2.0)),
                  ("1/3", fpu.from_float(1/3)), ("-1e-6", fpu.from_float(-1e-6))])
""")

md(r"""
On the Model 30 each floating-point order is two lines of microcode: fetch
the operand as usual, then one micro-order, `FPU`, hands R and MDR to the
unit. Watch the **FPU** control lamp. Without the feature, that micro-order
takes program check 11 instead.
""")

code(r"""
CIRCLE = '''
proc main()
begin
  var r := float(7), pi := fdiv(float(355), float(113))
  print(fix(fmul(fmul(pi, r), r))); newline()    -- the area of a circle
end
'''
fp = panel.record_salish(CIRCLE, title="Model 30 with the floating-point feature", fpu=True)
print("".join(chr(c) for f, c in fp.rec.output))
panel.animate(fp, speed=60)
""")

code(r"""
bare = panel.record_salish(CIRCLE, title="Model 30 without it")
print("".join(chr(c) for f, c in bare.rec.output))
""")

md(r"""
## 9. The compiler that compiles itself

`programs/selfhost/salish.sal` is SALISH/S: the SALISH compiler, written in
SALISH. It reads a program from the card reader and punches TRIAD code on
the card punch. The code is the same, card for card, as the compiler
that runs on the satellite. `jobs/bootstrap.job` runs four steps:

1. **Generation 0**, compiled by the satellite, compiles SALISH/S itself.
2. The cards it punched are assembled into **generation 1**, which
   compiles SALISH/S again.
3. **Generation 2** compiles a small program.
4. The small program runs.

Because generation 0 punches exactly the code it was made from,
generation 1 *is* generation 0, and the loop closes on itself at once.
This is Hofstadter's strange loop, a program that reproduces itself one
level up. It is also Good's machine that can build its own successor. It
takes about a minute and a half.
""")

code(r"""
boot = satellite.run_decks(["jobs/bootstrap.job"], model=90, out=lambda s: None)
for i, st in enumerate(boot.jobs[0].steps, 1):
    for m in st.messages:
        print(f"step {i}: {m}")
panel.show_bootstrap(boot)
""")

md(r"""
The first cards generation 0 punched for itself:
""")

code(r"""
print("\n".join(boot.jobs[0].steps[0].punched.splitlines()[:24]))
""")

md(r"""
### The compiler improves itself, once

SALISH/S also carries the optimiser. With `-- OPT` on its first card it
compiles exactly as SALISH/O does: registers by usage counts, fixed
vectors, rotated loops, the peephole pass. So the plain generation 0 can
compile an *optimised* generation 1 of itself. `jobs/improve.job` does
that on the Duwamish (about four minutes):

| step | compiler | instructions to compile SALISH/S | its deck |
|---|---|---:|---|
| 1 | generation 0 (plain) | 104.0 million | 13,378 cards, the satellite's optimised compilation, card for card |
| 2 | generation 1 (optimised) | 87.2 million | identical |
| 3 | generation 2 | 87.2 million | identical |

Generation 1 is 16% faster and thinks exactly the same thoughts, so its
successor is itself. The improvement happens once and stops: a fixed
point. The cell below shows the same thing in seconds. Generation 1 is
taken from the satellite (the tests check it is identical to what
generation 0 punches). Then both generations compile a few programs.
""")

code(r"""
def compile_with(generation_opt, program):
    deck = ("//JOB G\n//SALISH FROM=programs/selfhost/salish.sal"
            + (" OPT" if generation_opt else "") + "\n//EXEC\n//DATA\n-- OPT\n"
            + f"//DATA FROM={program}\n//DATA FROM=duwamish/lib/runtime.sal\n")
    sat = satellite.Satellite([(deck, "g.job")], model=90, out=lambda s: None)
    sat.run()
    st = sat.jobs[0].steps[0]
    return st.punched, st.result[4]
rows = []
for prog in ("programs/hello.sal", "programs/kleene.sal", "programs/hofstadter/miu.sal"):
    d0, n0 = compile_with(False, prog)
    d1, n1 = compile_with(True, prog)
    print(f"{prog:32} same deck: {d0 == d1}   generation 0: {n0:,}   generation 1: {n1:,}"
          f"   ({100 * (n0 - n1) / n0:.0f}% fewer)")
    rows.append((prog.split("/")[-1], [n0, n1]))
panel.show_bars("instructions to compile, optimising", rows,
                ["generation 0 (plain)", "generation 1 (optimised)"])
""")

md(r"""
## 10. Copycat: analogy as perception

"If abc changes to abd, what does ijk change to?" Hofstadter and
Mitchell's Copycat answers such questions with many small, random agents
(codelets). The agents notice bonds between letters, group alike letters,
describe the change as a rule, and map it across, letting concepts
*slip*: rightmost into leftmost, successor into predecessor, letter into
group. A *temperature* measures how incoherent the current understanding
is. `programs/hofstadter/copycat.sal` is a cut-down version on the
Duwamish. Each problem is run 30 times. The bars show how often each
answer came up, coloured by the average temperature at which it was
found. A cool answer is one the program itself found coherent. Look at
xyz: z has no successor, and the snag leads some runs to the mirror
answer wyz. It is rarer than the literal xyd, and cooler. The run takes
about half a minute.
""")

code(r"""
cc = satellite.run_program("programs/hofstadter/copycat.sal", model=90,
                           optimise=True, out=lambda s: None)
panel.show_copycat(cc.jobs[0].steps[0].output)
""")

md(r"""
## 11. Good's five-year plan: where the search goes

Shannon's chess program looks the same distance down every line. Good
wanted a program to follow the lines that are *likely to be played* and
cut the unlikely ones short. `programs/good/fiveyear.sal` gives every
move a plausibility and follows a line while its probability stays above
a threshold. Here is one move's search from an opening. Shannon's player
cuts every line at the second ply. Good's player cuts implausible lines
at the first and follows plausible ones four or five plies deep, for
about the same number of positions. `jobs/fiveyear.job` plays the full
match.
""")

code(r"""
FIVE = open("programs/good/fiveyear.sal").read()
FIVE = FIVE.replace('get "chessbase"', 'get "programs/good/chessbase.sal"')
FIVE = FIVE[:FIVE.index("proc main()")] + '''
proc main()
begin
  var col := 1
  setup()
  seed := 1975
  for j := 1 to 4 do begin random_move(col); col := -col end
  think(1, col)
  prints("shannon "); print(nodes); newline()
  think(2, col)
  prints("good "); print(nodes); newline()
  for p := 1 to 12 do begin print(cutoff[p]); space() end
  newline()
end
'''
import tempfile
with tempfile.NamedTemporaryFile("w", suffix=".sal", dir=".", delete=False) as f:
    f.write(FIVE)
fy = satellite.run_program(f.name, model=90, optimise=True, out=lambda s: None)
os.unlink(f.name)
lines = fy.jobs[0].steps[0].output.split("\n")
print(lines[0], "positions;", lines[1], "positions")
cuts = [int(x) for x in lines[2].split()]
panel.show_bars("lines cut off, by ply (Shannon's player: all at ply 2)",
                [(f"ply {p}", [c]) for p, c in enumerate(cuts, 1) if c],
                ["Good's player"])
""")

md(r"""
## 12. The look-ahead unit

The Model 90 issues one instruction per 1 µs core cycle. The optional
look-ahead unit adds a 32-word **instruction stack**, after the CDC 6600:
a loop that fits in it runs without fetching instructions from core. An
instruction from the stack that makes no data reference to core takes
one 200 ns cycle. Here are the Livermore kernels, compiled by SALISH/O
and run with the floating-point unit, without and with the look-ahead
unit. The answers are identical; only the time changes.
""")

code(r"""
import re
def livermore(lookahead):
    sat = satellite.run_decks(["jobs/livermore.job"], model=90,
                              lookahead=lookahead, out=lambda s: None)
    out = sat.jobs[1].steps[0].output          # the job compiled by SALISH/O
    rows = re.findall(r"^\s*(\d+)\s+(\S.*?\S)\s+\d+\s+\d+\s+[\d.]+\s+\d+\s+[\d.]+"
                      r"\s+\d+\s+([\d.]+)", out, re.M)
    return {f"{k} {name}": float(v) for k, name, v in rows}
plain, fast = livermore(False), livermore(True)
panel.show_bars("Livermore kernels, hardware float, SALISH/O (MFLOPS)",
                [(k, [plain[k], fast[k]]) for k in plain],
                ["Model 90", "Model 90 + look-ahead"], fmt="{:.3f}")
""")

md(r"""
## 13. TRILISP's memory: allocation and garbage collection

TRILISP keeps its list cells in three vectors in core: `car_`, `cdr_` and
`mark_`. The free cells are chained through `cdr_`. When the chain runs
out, `cons` calls the collector, which works in two phases.

* **Mark.** It marks every cell reachable from the symbols, and from any
  word on the machine stack that looks like a pointer. This is a
  *conservative* collector.
* **Sweep.** It sweeps the heap from the top down, clearing the marks
  and chaining every unmarked cell back onto the free list.

Here TRILISP runs with a heap of 3⁷ = 2,187 cells, so that collections
come often, on a program that builds lists and throws most of them away.
It keeps a few in `KEPT`, which survive every collection. The recorder
reads the heap straight out of core every few hundred instructions:
* cells light **amber** as `cons` hands them out;
* they turn **green** as the collector marks the live ones;
* the sweep reclaims the rest, and they go dark.

The lower plot is the number of cells in use, against instructions
executed. It is a sawtooth: each drop is one collection. The recording
takes a few seconds.
""")

code(r"""
from duwamish import heapview
print(heapview.WORKLOAD)
heap = heapview.record_heap()
print(heap.output.strip().splitlines()[-1])
heapview.animate(heap)
""")

md(r"""
## 14. Load your own program

Edit the SALISH source below and run the cell. `record_salish` also accepts
a path, for example `"programs/hofstadter/selfref.sal"`, but long
programs make long recordings. Keep `max_frames` to a few hundred thousand.

`panel.save_html(recording, "panel.html")` writes the front panel as a
stand-alone page that any browser can open.
""")

code(r"""
MY_PROGRAM = '''
proc main()
begin
  var x := 1
  for i := 1 to 5 do begin
    x := x * 3
    printt(x); newline()        -- powers of three: 1, 10, 100, ... in ternary
  end
end
'''
mine = panel.record_salish(MY_PROGRAM, title="my program", max_frames=100000)
print("".join(chr(c) for f, c in mine.rec.output))
panel.animate(mine, speed=80)
""")

md(r"""
---
*See `docs/ARCHITECTURE.md` for the machine, `docs/SALISH.md` and
`docs/TRILISP.md` for the languages, and `docs/DEMONSTRATOR.md` for the
demonstrations of Good's and Hofstadter's ideas.*
""")

nb = {"cells": cells,
      "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python",
                                  "name": "python3"},
                   "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 5}
for i, c in enumerate(nb["cells"]):
    c["id"] = f"cell-{i:02d}"
here = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(here, "..", "notebooks", "duwamish.ipynb")
with open(out, "w") as f:
    json.dump(nb, f, indent=1)
print("wrote", os.path.normpath(out))
