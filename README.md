# Duwamish

![Universal Entropics, Special Systems Section](docs/images/ue-logo.svg)

**A balanced-ternary computer, designed as if in 1967, built as a
demonstrator of the ideas of I. J. Good and Douglas Hofstadter.**

Imagine that the Special Systems Section of Universal Entropics, Seattle,
had hired Knuth, Good, Ashby, Beer, Pask, Cray, Rosenblatt and Nelson to
design a "billion-dollar brain" on the lines of the Soviet Setun, using the
best practice of 1967 (the Section's house style is in
[docs/IDENTITY.md](docs/IDENTITY.md)).
This repository contains the whole machine, and software that runs on it:

| layer | |
|---|---|
| **Architecture** | 27-trit words; symmetric core of 3¹² words; nine registers; one-trit condition code; three-way `J3` jumps; `SEL` truth-table instruction; Kleene logic in hardware |
| **Model 30** | microprogrammed: a 156-word horizontal microprogram in a *writable* control store, with ternary micro-branching, cycle-exact timing |
| **Model 90** | hardwired, fast, and checked equivalent to the Model 30 by randomized testing; a balanced-ternary **floating-point unit** as standard (a feature on the Model 30) |
| **Executive** | a resident monitor in protected core: traps, supervisor calls, time limits, accounting |
| **Satellite** | job control from card decks (`//JOB`, `//SALISH`, `//EXEC`, `//DATA`) |
| **TRIAD** | the symbolic assembler |
| **SALISH** | a BCPL-like language with three-valued logic, three-way `sign … of`, and **BlooP certification** of termination |
| **SALISH/O** | the optimising compiler: registers allocated by usage counts, index-register addressing, loop rotation, a peephole pass |
| **TRILISP** | a LISP 1.5-style interpreter written in SALISH, with one-trit type tags, tail calls and garbage collection |

## Quick start

Needs only Python 3.8+ and no packages.

```
python -m duwamish run jobs/tour.job --model 90        # the machine and its languages
python -m duwamish run jobs/hofstadter.job --model 90  # Goedel, quines, MIU, BlooP, halting
python -m duwamish run jobs/good.job --wcs             # evidence, Good-Turing, the explosion
python -m duwamish run jobs/go.job --model 90          # go, learned by self-play (about two minutes)
python -m duwamish run jobs/draughts.job --model 90    # Samuel's draughts learner (about four minutes)
python -m duwamish run jobs/chess.job --model 90       # Los Alamos chess (about a minute)
python -m duwamish run jobs/backgammon.job --model 90  # backgammon by self-play (about two minutes)
python -m duwamish run jobs/tower.job --model 90       # LISP in LISP in LISP (about a minute)
python -m duwamish run jobs/livermore.job              # Livermore loops (exact timing on Model 30)
python -m duwamish run jobs/livermore.job --model 90   # ... with the floating-point unit
python -m duwamish compile --opt programs/livermore.sal  # see what the optimiser does
python -m duwamish go programs/hello.sal               # run one program
python -m unittest discover -s tests -t .              # the test suite
```

Options for `run` and `go`: `--model 30|90` (default 30); `--wcs` to turn
the writable-control-store key; `--fpu` or `--no-fpu` to fit or remove the
floating-point unit (by default the Model 90 has one and the Model 30 does
not); `--opt` to compile every SALISH step with the optimising compiler
(or put `OPT` on a `//SALISH` card); `--list` for listings.

## Inside the machine: the front-panel notebook

![The Duwamish front panel](docs/images/front-panel.png)

[`notebooks/duwamish.ipynb`](notebooks/duwamish.ipynb) opens up the machine.
It runs the real Model 30 micro-engine one micro-cycle at a time, records
everything the console would show, and replays it on an animated front
panel.
* **Lamps:** a ternary lamp for every trit of every register (amber +1,
  blue −1, dark 0), plus the condition trit, the mode, the
  micro-program counter and the control lines.
* **Datapath:** a diagram showing which registers drive the buses each
  cycle.
* **Listings:** the microprogram and the program, with the current line
  highlighted.
* **Core map:** flashes each word as it is fetched, read or written.
* **Controls:** run, pause, step one micro-cycle, step one instruction,
  scrub, and speed from 1 to 10,000 cycles a second.

Because it is a recording, the lamps light in exactly the order the
machine lit them. The notebook walks through:
1. trits and words;
2. the instruction format;
3. a ternary multiplication, microstep by microstep;
4. the layout of core;
5. a whole job, from Executive boot through supervisor calls and traps;
6. the two models and the Beer monitor;
7. the machine writing new microcode for itself;
8. a cell to load and watch your own program.

```
pip install notebook          # or jupyterlab; nothing else is needed
jupyter notebook notebooks/duwamish.ipynb
```

From Python, `duwamish.panel.save_html(recording, "panel.html")` writes a
front panel that opens in any browser.

## The demonstrations

See **[docs/DEMONSTRATOR.md](docs/DEMONSTRATOR.md)** for what each one
shows, and what it does not.

**Good**
* `explosion.sal`: the machine profiles itself, invents new microcoded
  instructions for its hottest code, *including the code of the improver
  itself*, and rewrites itself to use them. The gains converge to a fixed
  point, which shows exactly which premise of the intelligence-explosion
  argument is missing.
* `go.sal`: Good's game. The program learns 5×5 go by self-play, using
  randomized experiments and weights of evidence over 729 six-trit
  patterns. It goes from 8 to 20 wins in 20 against a random player, and
  shows the evidence for what it learned.
* `draughts.sal`: after Strachey and Samuel. Alpha-beta search plus an
  evaluation polynomial that learns by self-play, using Samuel's
  "generalization" and Alpha/Beta scheme. It discovers for itself which
  positional terms matter.
* `chess.sal`: Los Alamos chess (6×6, no bishops), as MANIAC I played it
  in 1956. It counts minimax against alpha-beta (85% saved at four plies,
  same answer), and a three-ply searcher mates a one-ply player.
* `backgammon.sal`: a game of chance, learned by temporal-difference
  self-play with a single layer of ten weights. It goes from 0 to 7 wins
  in 16 against a hand-written evaluation.
* `banburismus.sal`: Turing and Good's weight of evidence in decibans, in a
  sequential test for messages "in depth"; the machine computes its own
  logarithms.
* `goodturing.sal`: estimating the probability of the unseen, checked
  against a known population (0.2280 estimated, 0.2292 true), and an
  honest failure on a text that violates the assumptions.

**Hofstadter**
* `selfref.sal`: Gödel's diagonal lemma, *executed*. A program solves for,
  writes and verifies a true statement of its own Gödel number.
* `quine.sal`: prints its own source, byte for byte.
* `miu.sal`: the MU puzzle. The invariant is one trit.
* `sequences.sal` / `floop.sal`: BlooP certified, FlooP refused.
* `metacircular.lsp`: a tower of interpreters with a strange loop at the top.
* `diagonal.lsp`: Contracrostipunctus. A halting oracle and the record it
  cannot play.

## How fast is it?

`programs/livermore.sal` runs six of the Livermore Fortran Kernels, the
loops by which the CDC 7600 was judged. It runs them three ways: in fixed
point, in a software ternary floating point (`duwamish/lib/tfloat.sal`),
and on the hardware floating-point unit, with answers checked against
double precision. The job compiles it twice, plainly and with SALISH/O.

| Model 90, harmonic mean MFLOPS | fixed point | software float | FPU |
|---|---:|---:|---:|
| plain SALISH | 0.070 | 0.0064 | 0.065 |
| SALISH/O | 0.184 | 0.0078 | 0.216 |

The unit made floating point ten times faster, but under the plain
compiler no faster than fixed point: the machine was limited by issuing
one instruction at a time. The optimiser cut the inner product from 20
instructions a pass to 6, which gains another factor of 3.3. The 7600's
peak was about 36 MFLOPS, about 170 times faster than the best Duwamish.
See [docs/ARCHITECTURE.md §12](docs/ARCHITECTURE.md) for the full
comparison.

## Documentation

* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): principles of operation, as
  the committee's report
* [docs/SALISH.md](docs/SALISH.md) and [docs/TRILISP.md](docs/TRILISP.md): the
  language manuals
* [docs/DEMONSTRATOR.md](docs/DEMONSTRATOR.md): the principles and their
  demonstrations
* [docs/IDENTITY.md](docs/IDENTITY.md): the house style of the Special
  Systems Section, which built the machine

## Layout

```
duwamish/            the machine: ternary.py isa.py microasm.py machine.py
                     triad.py salish.py optimise.py satellite.py fpu.py
                     executive.tri profile.py
                     panel.py (the recorder and animated front panel)
notebooks/           duwamish.ipynb, the machine made visible
duwamish/microcode/  model30.dmc, the microprogram
duwamish/lib/        runtime.sal, disasm.sal, trilisp.sal, tfloat.sal
docs/images/         the Section's mark and signature (ue-mark.svg, ue-logo.svg)
programs/            SALISH and TRILISP programs (good/, hofstadter/, trilisp/)
jobs/                card decks
data/                Genesis 1 (KJV), for Good-Turing
tests/               unittest suite
tools/               make_quine.py (how the quine was built),
                     make_notebook.py (how the notebook is generated)
```

*The committee and its report are fiction. The ideas credited to each
member are their real published views; the design and code are new.*
