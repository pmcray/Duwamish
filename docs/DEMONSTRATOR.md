# The Demonstrator: Good and Hofstadter on the Duwamish

Every program here runs *on* the simulated machine: under its Executive, in
its core, on its microcode. Each illustrates one principle of I. J. Good or
Douglas Hofstadter. Every result it prints is computed by the machine, and
where possible **checked** by it. The tables below say what to run, what
to look for, and what the output does and does not show.

```
python -m duwamish run jobs/good.job --wcs     # Good (the explosion needs the WCS key)
python -m duwamish run jobs/hofstadter.job     # Hofstadter
python -m duwamish run jobs/tower.job          # LISP in LISP in LISP (about a minute)
python -m duwamish run jobs/tour.job           # the machine and its languages
```

Add `--model 90` for the fast hardwired model (the explosion needs the
Model 30, the default, to show exact micro-cycle timing).

---

## I. J. Good

### 1. The intelligence explosion — `programs/good/explosion.sal`

> "Let an ultraintelligent machine be defined as a machine that can far
> surpass all the intellectual activities of any man however clever. Since
> the design of machines is one of these intellectual activities, an
> ultraintelligent machine could design even better machines; there would
> then unquestionably be an 'intelligence explosion'."
> — Good, *Speculations Concerning the First Ultraintelligent Machine*, 1965

**What the program does.** Each generation, the program:

1. **profiles** itself with the Beer-monitor tallies, *including its own
   improver*;
2. **designs** a new machine instruction: microcode that executes the
   most valuable straight-line run of its code without fetching it from
   core;
3. **builds** it: it writes the control store and the dispatch map,
   claims an unused *negative* opcode, and patches its own code.

After each generation it checks that the work's answer is unchanged.

**What to look for.** In generation 1 the hottest code is *the improver's
own search loop*, so the machine improves its designer first. That is
Good's recursion in miniature. Over twelve generations the work speeds up
about 1.3× and the improver about 1.4×.

**What it does not show, and why that matters.** The gains shrink and stop:
each invention removes fetches from one run, and there are only so many
runs. The program prints this conclusion. Its improvement operator has a
*fixed point*. Good's argument needs each generation to widen the space of
designs available to the next, to improve how it improves and not just
what it runs. The demonstration makes that premise concrete, testable and
visibly unmet.

### 2. Weight of evidence — `programs/good/banburismus.sal`

Turing and Good at Bletchley measured evidence in **decibans**: *W* = 10
log₁₀ of the likelihood ratio, which *adds* across independent
observations. The program asks whether pairs of enciphered messages are
"in depth" (share a key stream). It adds +2.32 db for each coinciding
letter and −0.12 db for each non-coincidence, and stops, as Wald's
sequential test does, at ±20 db (odds of 100:1). The machine derives these
weights itself from English letter frequencies, computing its own
logarithms by repeated squaring. It plots the evidence letter by letter and
reports its verdicts. A pair that fails to reach the threshold is reported
as undecided, not guessed.

### 3. The probability of the unseen — `programs/good/goodturing.sal`

Good's 1953 paper (crediting Turing): the chance that the next specimen is
of a *new* species is about *N₁/N*, the fraction of the sample seen exactly
once. A species seen *r* times deserves the adjusted count
*r\** = (*r*+1)*N*ᵣ₊₁/*N*ᵣ.

* **Part 1** samples from a population whose true frequencies the machine
  knows. The Good–Turing estimate (0.2280) lands almost on the true unseen
  mass (0.2292), and *r\** tracks the true expected counts where the naive
  *r* does not.
* **Part 2** applies it to Genesis 1 (KJV), learning from the odd verses
  and testing on the even ones. Here the estimate falls well short (0.13
  against an actual 0.30). The program explains why: a narrative is not a
  fixed population. This is kept in deliberately. Knowing when an
  estimator's assumptions fail is part of Good's lesson.

---

## Douglas Hofstadter

### 4. Self-reference by arithmetic — `programs/hofstadter/selfref.sal`

Gödel's diagonal lemma says that a sentence can state a property of its
*own* Gödel number. The program's "sentence" is its own machine code.
`claimed()` holds a constant: the program's claim about its own Gödel
number (its code read as a base-3²⁷ numeral, mod a prime). As written the
claim is false. The program then

1. reads its own code and computes its number;
2. solves the fixed-point equation *v = G(v)*, which has exactly one
   solution because *G* is linear in the constant;
3. writes *v* into its own instruction (`LD R1, #257230`);
4. reads itself again and verifies that the claim is now **true**.

Nothing is assumed: the true self-description is *computed*, as Gödel's is.

### 5. Quining — `programs/hofstadter/quine.sal`

A SALISH program whose output is exactly its own source text, byte for
byte. The test suite checks this on every run. It follows Hofstadter's
"quining": a text that contains its own quotation plus instructions for
using it. `tools/make_quine.py` shows how the text was constructed. TRILISP's
tour includes the LISP version, checked in-machine by `(equal (eval q) q)`.

### 6. The MU puzzle — `programs/hofstadter/miu.sal`

This separates Hofstadter's **mechanical mode** from his **intelligent
mode**. Working inside the MIU system, the machine derives all 216
theorems up to length 12 and never finds MU, but it can only ever say
"not yet". Stepping outside, the invariant is that the number of I's is
never a multiple of 3. On a ternary machine "a multiple of 3" means "the
last trit is 0", and the machine checks that trit on every theorem it
derives. The table shows the count of I's in balanced ternary: the last
trit is always 1 or T.

### 7. BlooP, FlooP and GlooP — `sequences.sal`, `floop.sal`

With the word `bloop`, the SALISH compiler *certifies termination*. It
accepts only bounded `for` loops, no recursion and no indirect calls, and
prints a certificate. Hofstadter's tangled recursive sequences from GEB
chapter V (G, H, the married F and M, the chaotic Q, Figure-Figure) are
computed in BlooP, and G's closed form ⌊(n+1)/φ⌋ is confirmed. The
wondrous-numbers (Collatz) program is **refused** certification, with each
unbounded loop named, and then runs as FlooP. Whether *every* number is
wondrous is a GlooP question that no bounded loop can answer.

### 8. Levels, and the strange loop — `metacircular.lsp` (the `tower` job)

The tower of interpreters: Python → microcode → TRIAD → SALISH (the TRILISP
interpreter) → M-EVAL, McCarthy's LISP-in-LISP → M-EVAL again, running its
own source → `(FACT 2)`. Each level knows nothing of the trits beneath it
(Hofstadter's "levels of description", like Aunt Hillary's ant colony).
Each costs about 100–160 times the level below. The top interpreter is the
same *text* as the one below it, read as data: the program has become its
own subject.

### 9. Contracrostipunctus — `diagonal.lsp`

The Crab's record players and the Tortoise's records. `HALTS?` is an honest
would-be oracle: it runs a program in M-EVAL with a step budget. It is right
about `(FACT 3)` and right about an endless loop. `CONTRARY` asks the oracle
about *itself* and does the opposite. The oracle says "runs forever";
`CONTRARY` then halts. Raising the budget changes nothing. This is Turing's
halting theorem, the engine of Gödel's.

### 10. The tangled hierarchy — the machine as a whole

The deepest Hofstadterian feature is architectural. The writable control
store lets software rewrite the microcode that runs it (§1). TRILISP can
`PEEK` at the words that *are* its objects, and `(WORD 42)` is 127 because
42 is stored as 3·42+1. The disassembler lets any SALISH program read its own
machine code. Every level can reach the level beneath it, and in the
explosion demonstration it reaches the bottom and alters it.

---

## Also from the committee

* **Kleene and McCarthy logic** (`programs/kleene.sal`): three-valued
  truth tables, each connective a single ternary instruction.
* **Beer**: every run can be profiled from the tallies
  (`duwamish/profile.py`); the explosion uses them to watch itself.
* **Cray / System/360**: two implementations of one architecture, checked
  equivalent by randomized testing (`tests/test_machine.py`).
