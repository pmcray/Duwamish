# Duwamish

**A balanced-ternary computer, designed as if in 1967, built as a
demonstrator of the ideas of I. J. Good and Douglas Hofstadter.**

Imagine that Universal Entropics of Seattle had hired Knuth, Good, Ashby,
Beer, Pask, Cray, Rosenblatt and Nelson to design a "billion-dollar
brain" on the lines of the Soviet Setun, using the best practice of 1967.
This repository contains the whole machine, and software that runs on it:

| layer | |
|---|---|
| **Architecture** | 27-trit words; symmetric core of 3¹² words; nine registers; one-trit condition code; three-way `J3` jumps; `SEL` truth-table instruction; Kleene logic in hardware |
| **Model 30** | microprogrammed: a 142-word horizontal microprogram in a *writable* control store, with ternary micro-branching, cycle-exact timing |
| **Model 90** | hardwired, fast, and checked equivalent to the Model 30 by randomized testing |
| **Executive** | a resident monitor in protected core: traps, supervisor calls, time limits, accounting |
| **Satellite** | job control from card decks (`//JOB`, `//SALISH`, `//EXEC`, `//DATA`) |
| **TRIAD** | the symbolic assembler |
| **SALISH** | a BCPL-like language with three-valued logic, three-way `sign … of`, and **BlooP certification** of termination |
| **TRILISP** | a LISP 1.5-style interpreter written in SALISH, with one-trit type tags, tail calls and garbage collection |

## Quick start

Needs only Python 3.8+ and no packages.

```
python -m duwamish run jobs/tour.job --model 90        # the machine and its languages
python -m duwamish run jobs/hofstadter.job --model 90  # Goedel, quines, MIU, BlooP, halting
python -m duwamish run jobs/good.job --wcs             # evidence, Good-Turing, the explosion
python -m duwamish run jobs/go.job --model 90          # go, learned by self-play (about two minutes)
python -m duwamish run jobs/tower.job --model 90       # LISP in LISP in LISP (about a minute)
python -m duwamish go programs/hello.sal               # run one program
python -m unittest discover -s tests -t .              # 32 tests
```

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

## Documentation

* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): principles of operation, as
  the committee's report
* [docs/SALISH.md](docs/SALISH.md) and [docs/TRILISP.md](docs/TRILISP.md): the
  language manuals
* [docs/DEMONSTRATOR.md](docs/DEMONSTRATOR.md): the principles and their
  demonstrations

## Layout

```
duwamish/            the machine: ternary.py isa.py microasm.py machine.py
                     triad.py salish.py satellite.py executive.tri profile.py
duwamish/microcode/  model30.dmc, the microprogram
duwamish/lib/        runtime.sal, disasm.sal, trilisp.sal
programs/            SALISH and TRILISP programs (good/, hofstadter/, trilisp/)
jobs/                card decks
data/                Genesis 1 (KJV), for Good-Turing
tests/               unittest suite
tools/make_quine.py  how the quine was built
```

*The committee and its report are fiction. The ideas credited to each
member are their real published views; the design and code are new.*
