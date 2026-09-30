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
python -m duwamish run jobs/chess.job --model 90     # Los Alamos chess (about a minute)
python -m duwamish run jobs/backgammon.job --model 90  # backgammon by self-play (about two minutes)
python -m duwamish run jobs/tower.job          # LISP in LISP in LISP (about a minute)
python -m duwamish run jobs/fiveyear.job --model 90  # Good's five-year plan v. Shannon (about six minutes)
python -m duwamish run jobs/copycat.job --model 90   # Copycat's analogies (about half a minute)
python -m duwamish run jobs/bootstrap.job --model 90 # the compiler compiles itself (a minute and a half)
python -m duwamish run jobs/improve.job --model 90   # ... and makes a faster copy of itself (four minutes)
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

### 4. Chess, and the arithmetic of lookahead — `programs/good/chess.sal`

Chess was the first great target of machine intelligence.
* Turing designed a chess machine on paper.
* Shannon's "Programming a Computer for Playing Chess" (1950) set out the
  plan every later program followed: search the tree of moves, score the
  end positions, and back the scores up by minimax.
* In 1956 the MANIAC I at Los Alamos played a reduced game on a 6×6 board
  without bishops. That game is **Los Alamos chess**, and it is what this
  program plays: rooks, knights, a queen and a king, pawns that move one
  square, no castling or en passant.
* Good wrote "A Five-Year Plan for Automatic Chess" (1968).

The program shows two things.

1. **The arithmetic.** From the opening position it counts the positions
   that full minimax examines and those alpha-beta pruning needs for the
   same answer. At four plies that is 16,192 against 2,535, an 85% saving
   with an identical score. Alpha-beta never changes the result, and its
   saving grows with depth. Knuth and Moore's later analysis (1975)
   showed that with perfect move ordering it can search about twice as
   deep for the same work.
2. **What lookahead is worth.** A three-ply searcher plays a one-ply
   player that, like Turing's paper machine, follows captures further. In
   the recorded game the deeper searcher mates on move 14.

The move generator is checked against an independent implementation of
the rules by counting move trees (10, 100, 1,212 and 14,332 positions at
depths 1–4). The test suite checks the first three.

*Hofstadter's footnote.* In *Gödel, Escher, Bach* (1979) Hofstadter
speculated that a program able to beat anyone at chess would have to be a
general intelligence, not a mere chess player. Deep Blue's 1997 victory
by search refuted that, and Hofstadter said so. It is a useful caution
about predicting which abilities need a mind.

### 5. The five-year plan — `programs/good/fiveyear.sal`

Good's "A Five-Year Plan for Automatic Chess" (*Machine Intelligence 2*,
1968) did not want a program to look the same distance down every line.
A strong player follows the lines likely to be played, and follows
"agitated" positions (captures, checks) until they are quiet. Good also
argued that a position's value is a probability of winning, judged by a
fallible player. `fiveyear.sal` is **our reading** of two of those
proposals, on the chess engine above (now `chessbase.sal`, shared by both
programs):

* **Plausibility.** Every move gets a weight for how likely a player is to
  choose it: captures by the value taken, promotions, checks, moves to the
  centre. A line is followed while the product of its moves'
  probabilities stays above a threshold. Likely lines are searched deep
  and unlikely ones shallow. A side in check is agitated, and its replies
  divide the probability less.
* **Fallible backing up.** Where the opponent replies to the move being
  considered, the backed-up value is three parts minimax and one part the
  plausibility-weighted average of all the replies. It prefers moves that
  give the opponent ways to go wrong.

Each Good player plays Shannon's (two plies full width, then captures),
with each colour, from three openings. The threshold is adjusted after
every move so that Good's players search about as many positions as
Shannon's. In the recorded match (about six minutes, Model 90):

| player | score against Shannon | positions per move |
|---|---|---|
| Good, plausibility | 3½ of 6 | 470 (Shannon 423) |
| Good, plausibility + fallible backing up | 1 of 6 | 524 |

Plausibility-guided search did slightly better on slightly more work.
Assuming a fallible opponent did clearly worse: it chose moves that invite
mistakes, and a player that searches every reply does not make them. Six
games are a small sample, and the program says so. History's verdict came
later. Selective search was the hope of the 1960s (Greenblatt's MacHack VI
pruned by plausibility too). In 1973 Slate and Atkin's Chess 4.0 went
over to full width, and brute force won the decades after. The notebook
draws where Good's search cuts its lines off: most at the first ply, a
few four or five plies deep.

### 6. Backgammon, learned by self-play — `programs/good/backgammon.sal`

Backgammon is a game of expectation, not certainty, which is the
probabilist's world. Michie's "Game-playing and game-learning automata"
(1966) showed how minimax extends to games of chance. The program sees
the board from the side to move. Handing it to the other player is a
reversal and a negation, the ternary machine's favourite operation.
Moves are generated by searching every order of dice and checkers, under
the standard rules: use as many dice as possible, and the larger die if
only one of two can be played.

* **Evaluation:** a single layer of ten weights, in the manner of
  Rosenblatt: the race, blots, home-board points, prime, hits, checkers
  borne off and anchors.
* **Learning:** Samuel's idea on a game of chance. The program plays
  itself. After each move it nudges its evaluation of its previous
  position towards its evaluation of the new one, and at the end towards
  the result. This is temporal-difference learning, with Widrow–Hoff
  normalization. The dice provide all the exploration it needs. It is
  the method of Tesauro's TD-Gammon (1992), which used a multi-layer
  network and reached world-class strength.

**What to look for.** It starts unable to tell one move from another,
winning 0 of 16 against an evaluation written by hand, as a 1967
programmer would write one. After 15 games of self-play it wins 4 of 16,
and after 30 games 7 of 16. It also prints its learned weights beside the
hand-written ones: it trusts the race and bearing off far more than its
programmer did, and home-board points far less.

**How much to trust that.** Sixteen games is a small test. In a Python
prototype of the same learner, three seeds tested over 200 games each
reached 46–59% against the hand-written evaluation after 30–60 games, and
then stopped improving. That plateau is the honest lesson: ten linear
features can match their programmer's judgement but not go far beyond it.
TD-Gammon needed a hidden layer.

### 7. Weight of evidence — `programs/good/banburismus.sal`

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

### 8. The probability of the unseen — `programs/good/goodturing.sal`

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

### 9. Self-reference by arithmetic — `programs/hofstadter/selfref.sal`

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

### 10. Quining — `programs/hofstadter/quine.sal`

A SALISH program whose output is exactly its own source text, byte for
byte. The test suite checks this on every run. It follows Hofstadter's
"quining": a text that contains its own quotation plus instructions for
using it. `tools/make_quine.py` shows how the text was constructed. TRILISP's
tour includes the LISP version, checked in-machine by `(equal (eval q) q)`.

### 11. The MU puzzle — `programs/hofstadter/miu.sal`

This separates Hofstadter's **mechanical mode** from his **intelligent
mode**. Working inside the MIU system, the machine derives all 216
theorems up to length 12 and never finds MU, but it can only ever say
"not yet". Stepping outside, the invariant is that the number of I's is
never a multiple of 3. On a ternary machine "a multiple of 3" means "the
last trit is 0", and the machine checks that trit on every theorem it
derives. The table shows the count of I's in balanced ternary: the last
trit is always 1 or T.

### 12. Copycat: analogy as perception — `programs/hofstadter/copycat.sal`

"If abc changes to abd, what does ijk change to?" Hofstadter and Melanie
Mitchell's Copycat (1988–1993; *Fluid Concepts and Creative Analogies*,
1995) treats analogy as perception, and perception as the work of many
small, independent, randomly chosen agents: **codelets**.

* **The workspace.** Bond scouts notice that neighbouring letters are the
  same, successors or predecessors. Group scouts gather runs of alike
  letters. A rule scout describes the change ("replace the rightmost
  letter by its successor"). A correspondence scout maps the changed
  letter into the target.
* **The slipnet.** Concepts (sameness, successor, leftmost, group,
  opposite, first/last, ...) grow active as they are used, and each has a
  conceptual depth. A concept may **slip** into a neighbour when the
  situation presses it: rightmost into leftmost, successor into
  predecessor, letter into group, the successorship of letters into that
  of lengths.
* **Temperature.** Temperature measures how incoherent the understanding
  is: unnoticed relations, ungrouped runs and weak structures keep it
  high. Hot, and choices are nearly random; cold, and the strongest
  structures win. An answer the program cannot build (the successor of z)
  is a **snag**. The temperature jumps, structures are broken, and idle
  concepts are woken.

It is a cut-down reconstruction, not Mitchell's code: one changed letter
in the source, sameness groups only, eleven concepts. Run 30 times per
problem (half a minute, Model 90):

| target | answers (count, average final temperature) |
|---|---|
| ijk | **ijl** 29 (27), ijd 1 (42) |
| iijjkk | **iijjll** 23 (31), iijjkl 6 (49), iijjkj 1 |
| kji | **lji** 14 (24), **kjh** 12 (25), kjj 4 (35) |
| mrrjjj | **mrrkkk** 24 (23), mrrjjk 4 (53), **mrrjjjj** 2 (19) |
| xyz | xyd 16 (29), **wyz** 12 (20), xyy 1, dyz 1 |

The shape is Copycat's. Grouping wins where the target is grouped (iijjll,
mrrkkk). kji divides between slipping the position (lji) and slipping the
direction (kjh). And the rare, deep answers are the coolest: mrrjjjj
(the lengths 1, 2, 3 seen as a successor sequence) and wyz. wyz is xyz
seen as abc's mirror: the snag at z wakes "a is first, z is last", and
rightmost slips to leftmost with successor to predecessor. One difference
is honest to record: in Mitchell's runs xyd was far commoner than wyz.
Here wyz comes up more often than that, though still less often than xyd,
and still at the lowest temperature.

### 13. BlooP, FlooP and GlooP — `sequences.sal`, `floop.sal`

With the word `bloop`, the SALISH compiler *certifies termination*. It
accepts only bounded `for` loops, no recursion and no indirect calls, and
prints a certificate. Hofstadter's tangled recursive sequences from GEB
chapter V (G, H, the married F and M, the chaotic Q, Figure-Figure) are
computed in BlooP, and G's closed form ⌊(n+1)/φ⌋ is confirmed. The
wondrous-numbers (Collatz) program is **refused** certification, with each
unbounded loop named, and then runs as FlooP. Whether *every* number is
wondrous is a GlooP question that no bounded loop can answer.

### 14. Levels, and the strange loop — `metacircular.lsp` (the `tower` job)

The tower of interpreters: Python → microcode → TRIAD → SALISH (the TRILISP
interpreter) → M-EVAL, McCarthy's LISP-in-LISP → M-EVAL again, running its
own source → `(FACT 2)`. Each level knows nothing of the trits beneath it
(Hofstadter's "levels of description", like Aunt Hillary's ant colony).
Each costs about 100–160 times the level below. The top interpreter is the
same *text* as the one below it, read as data: the program has become its
own subject.

### 15. The compiler that compiles itself, and improves itself once — `programs/selfhost/salish.sal`

SALISH/S is the SALISH compiler written in SALISH: about 2,800 lines,
following the satellite's compilers part for part. It reads a program from
the card reader and punches TRIAD code on the card punch (SVC 5). The
control card `//TRIAD PUNCHED` assembles the cards a step punched, so one
job deck can feed a compiler's output to the next step.

**The fixed point** (`jobs/bootstrap.job`, about a minute and a half):

1. **Generation 0**, compiled by the satellite, compiles SALISH/S on the
   Duwamish: 44 million instructions, 15,154 cards.
2. The satellite assembles those cards into **generation 1**, and reports
   that they are *identical, card for card, to its own compilation*.
   Generation 1 compiles SALISH/S again: the same 15,154 cards.
3. **Generation 2** compiles a small program, and step 4 runs it.

Because generation 0 reproduces exactly the code it was made from,
generation 1 *is* generation 0. The loop closes on itself at once, a
**fixed point** of compilation. It is the strange loop in its most literal
form: a program whose output, one level up, is itself. (The quine, §10,
does it at one level; this does it across two.)

**The improvement** (`jobs/improve.job`, about four minutes). SALISH/S
also carries the optimiser. With `-- OPT` on its first card it compiles
exactly as SALISH/O does: the register plan by usage counts, fixed
vectors, rotated loops and the peephole pass, card for card. So the
machine can build a *better* successor:

| step | compiler | instructions to compile SALISH/S, optimising | its deck |
|---|---|---:|---|
| 1 | generation 0 (plain) | 104.0 million | 13,378 cards: the satellite's optimised compilation, card for card |
| 2 | generation 1 (optimised) | 87.2 million | identical |
| 3 | generation 2 | 87.2 million | identical |

This is Good's condition for an intelligence explosion, in miniature: a
machine that improves the machine that improves machines. And it shows
where the argument needs one more premise. Generation 1 is 16% faster,
but it is the *same compiler*: it makes the same decisions and punches the
same cards. So its successor is itself, and the improvement happens
exactly once. A faster mind that thinks the same thoughts builds the same
successor. Explosion needs each generation to be better at *designing*,
not just quicker at it, and nothing here supplies that. The
microcode-inventing demonstration (§1) reaches the same fixed point from
the other side: its gains, too, converge.

The tests check that SALISH/S agrees card for card with the satellite's
compilers, with and without OPT, on the demonstration programs, on random
programs and on itself. That makes the compilers each other's
specification. Mirroring the peephole pass found a real flaw in the
Python one: removing an unused label did not count as a change, so a
procedure could stop one step short of its best form, depending on what
its neighbours were doing. Both are now fixed the same way.

### 16. Contracrostipunctus — `diagonal.lsp`

The Crab's record players and the Tortoise's records. `HALTS?` is an honest
would-be oracle: it runs a program in M-EVAL with a step budget. It is right
about `(FACT 3)` and right about an endless loop. `CONTRARY` asks the oracle
about *itself* and does the opposite. The oracle says "runs forever";
`CONTRARY` then halts. Raising the budget changes nothing. This is Turing's
halting theorem, the engine of Gödel's.

### 17. The tangled hierarchy — the machine as a whole

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
