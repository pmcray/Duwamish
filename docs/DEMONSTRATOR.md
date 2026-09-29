# The Demonstrator: Good and Hofstadter on the Duwamish

Every program here runs *on* the simulated machine: under its Executive, in
its core, on its microcode. Each illustrates one principle of I. J. Good or
Douglas Hofstadter. Every result it prints is computed by the machine, and
where possible **checked** by it. The tables below say what to run, what
to look for, and what the output does and does not show.

```
python -m duwamish run jobs/good.job --wcs     # Good (the explosion needs the WCS key)
python -m duwamish run jobs/hofstadter.job     # Hofstadter
python -m duwamish run jobs/go.job --model 90  # go, learned by self-play (about two minutes)
python -m duwamish run jobs/draughts.job --model 90  # Samuel's draughts learner (about four minutes)
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

### 2. Go, learned by self-play — `programs/good/go.sal`

Good learned go at Bletchley and did much to bring it to the West. His
article "The Mystery of Go" (*New Scientist*, 1965) argued it would be far
harder to program than chess. This program learns 5×5 go from nothing but
the rules and the results of games against itself.

* **The board is ternary.** A point is a trit: black +1, empty 0, white −1.
  The position seen from the other side is its negation.
* **Knowledge is a table of patterns**, and a pattern is exactly one
  6-trit number (3⁶ = 729 patterns). Four trits are the move's neighbours
  from the mover's side, one says centre, edge or corner, and one says
  whether the move captures (+1), puts itself in atari (−1) or neither.
* **Learning is by randomized experiment.** Half the self-play moves are
  chosen at random. Each pattern's value is Good's weight of evidence, in
  decibans, that *choosing* it goes with winning, over and above merely
  having it *available*. Good's flattening constant of 1 means no evidence,
  no opinion. The program plays the move with the most evidence in its
  favour, and passes when every move has evidence against it.

**What to look for.** After 300 games of self-play it beats a random
player 20 games in 20, up from 8 when untrained. It then *shows its
evidence*: the patterns it came to prefer and to fear, each with the
count of winners and losers who chose it. It was never told that filling
its own eye is bad. It found something subtler: filling an eye is harmless
(+0.69 db) while the group keeps other liberties, and bad (−4.45 db) when
the move leaves the group in atari.

**Why randomization matters.** The naive rule credits every move with its
game's result, as Michie's MENACE (1961) did. Set `CREDIT = 0` to try it:
it reaches only 15 in 20 on the same budget. The naive rule confuses cause
with circumstance, because a losing side plays desperate moves *because* it
is losing. Choosing experimental moves at random (Fisher's device) breaks
that confusion, so the evidence measures what a move does.

**What it does not show.** Four neighbours cannot see a whole group, let
alone the board. The program is a beginner that exploits a random
opponent's blunders. That limitation is the "mystery of go" Good wrote
about.

### 3. Draughts, after Samuel — `programs/good/draughts.sal`

Christopher Strachey's draughts program (1951–52, for the Pilot ACE and
the Ferranti Mark 1) was among the first game programs ever run. Arthur
Samuel's checkers program at IBM, begun in 1952 and described in "Some
Studies in Machine Learning Using the Game of Checkers" (1959), *learned*
by self-play to play better than Samuel himself. A machine surpassing its
maker at an intellectual task is the step on which Good's intelligence
explosion rests. This program follows Samuel's method, and it complements
the Go program. Go learns local patterns with no lookahead. Draughts uses
**search plus a learned evaluation**.

* **Search:** minimax with alpha-beta pruning, two moves deep, extended
  while captures are pending. Captures are compulsory, and multiple jumps
  are generated by a recursive search. Pieces are +1/+2 for black man/king
  and −1/−2 for white, so the sign is the colour.
* **Evaluation:** Samuel's scoring polynomial. Material is fixed (a man
  100, a king 150), plus six learned terms: mobility, men in the centre,
  advancement, kings in the centre, back-row guards and threats.
* **Learning by generalization:** after each move, the learner nudges
  each coefficient to close the gap between the position's static score
  and the score its lookahead backed up. This is Samuel's rule in Widrow
  and Hoff's normalized least-mean-squares form, and it anticipates
  TD-Gammon and AlphaZero.
* **Alpha and Beta:** the learning player plays a frozen copy, which
  adopts the learner's coefficients whenever the learner wins. The final
  program uses the learner's coefficients averaged over all its learning.

**What to look for.** Starting from material alone, it discovers that a
capture in hand, a king in the centre and a back-row guard are good, and
that a man in the centre (easily taken) or advanced too soon is bad. Every
sign agrees with separate experiments that tested each term alone. Against
the material-only program it grew from, the recorded run won 11, drew 1
and lost 8 of 20 games.

**How much to trust that.** Twenty games cannot establish an 11–8
margin. In 40-game trials of the same method across eight random seeds
(on a Python prototype of the same engine), every seed improved on
material-only play, averaging about a 64% score. Two naive versions
failed first: plain least-mean-squares steps drifted, and a mobility count
that included compulsory captures taught the program to *avoid* having
moves. Normalizing the steps and averaging the coefficients made the
learning reliable. It is a small brain (six terms, two moves of lookahead)
and the gain is modest. Samuel's program had 38 terms and years of play.

### 4. Weight of evidence — `programs/good/banburismus.sal`

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

### 5. The probability of the unseen — `programs/good/goodturing.sal`

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

### 6. Self-reference by arithmetic — `programs/hofstadter/selfref.sal`

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

### 7. Quining — `programs/hofstadter/quine.sal`

A SALISH program whose output is exactly its own source text, byte for
byte. The test suite checks this on every run. It follows Hofstadter's
"quining": a text that contains its own quotation plus instructions for
using it. `tools/make_quine.py` shows how the text was constructed. TRILISP's
tour includes the LISP version, checked in-machine by `(equal (eval q) q)`.

### 8. The MU puzzle — `programs/hofstadter/miu.sal`

This separates Hofstadter's **mechanical mode** from his **intelligent
mode**. Working inside the MIU system, the machine derives all 216
theorems up to length 12 and never finds MU, but it can only ever say
"not yet". Stepping outside, the invariant is that the number of I's is
never a multiple of 3. On a ternary machine "a multiple of 3" means "the
last trit is 0", and the machine checks that trit on every theorem it
derives. The table shows the count of I's in balanced ternary: the last
trit is always 1 or T.

### 9. BlooP, FlooP and GlooP — `sequences.sal`, `floop.sal`

With the word `bloop`, the SALISH compiler *certifies termination*. It
accepts only bounded `for` loops, no recursion and no indirect calls, and
prints a certificate. Hofstadter's tangled recursive sequences from GEB
chapter V (G, H, the married F and M, the chaotic Q, Figure-Figure) are
computed in BlooP, and G's closed form ⌊(n+1)/φ⌋ is confirmed. The
wondrous-numbers (Collatz) program is **refused** certification, with each
unbounded loop named, and then runs as FlooP. Whether *every* number is
wondrous is a GlooP question that no bounded loop can answer.

### 10. Levels, and the strange loop — `metacircular.lsp` (the `tower` job)

The tower of interpreters: Python → microcode → TRIAD → SALISH (the TRILISP
interpreter) → M-EVAL, McCarthy's LISP-in-LISP → M-EVAL again, running its
own source → `(FACT 2)`. Each level knows nothing of the trits beneath it
(Hofstadter's "levels of description", like Aunt Hillary's ant colony).
Each costs about 100–160 times the level below. The top interpreter is the
same *text* as the one below it, read as data: the program has become its
own subject.

### 11. Contracrostipunctus — `diagonal.lsp`

The Crab's record players and the Tortoise's records. `HALTS?` is an honest
would-be oracle: it runs a program in M-EVAL with a step budget. It is right
about `(FACT 3)` and right about an endless loop. `CONTRARY` asks the oracle
about *itself* and does the opposite. The oracle says "runs forever";
`CONTRARY` then halts. Raising the budget changes nothing. This is Turing's
halting theorem, the engine of Gödel's.

### 12. The tangled hierarchy — the machine as a whole

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
