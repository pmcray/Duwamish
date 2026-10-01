# The Demonstrator: Good, Hofstadter and the committee on the Duwamish

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
python -m duwamish run jobs/tritran.job --model 90   # FORTRAN, and Good's prime-factor FFT (about half a minute)
python -m duwamish run jobs/perceptron.job --model 90  # Rosenblatt's perceptron v. Good's evidence (half a minute)
python -m duwamish run jobs/whale.job --model 90       # WHALE: the tour, and a clinic that weighs evidence (40 seconds)
python -m duwamish run jobs/homeostat.job --model 90   # Ashby's homeostat (ten seconds)
python -m duwamish run jobs/saki.job --model 90        # Pask's SAKI, the teaching machine (ten seconds)
python -m duwamish run jobs/knuth.job --model 90       # Kleene Life, sorting, ternary trees, radix 3 (half a minute)
python -m duwamish run jobs/eliza.job --model 90       # ELIZA and the DOCTOR (ten seconds)
python -m duwamish run jobs/gps.job --model 90         # GPS on the Tower of Hanoi (twenty seconds)
python -m duwamish run jobs/strips.job --model 90      # STRIPS plans for Shakey (about a minute)
python -m duwamish run jobs/shrdlu.job --model 90      # micro-SHRDLU (half a minute)
python -m duwamish run jobs/prolog.job --model 90      # a three-valued Prolog (about a minute)
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

### 9. The interaction algorithm — `programs/good/pfa.ftn`

A Fourier transform of length *N* = *N*₁*N*₂, with *N*₁ and *N*₂ prime to
each other, is a two-dimensional transform of *N*₁ by *N*₂, provided the
data are taken in the right order. This was Good's observation in "The
interaction algorithm and practical Fourier analysis" (1958). The order
going in is *n* = *N*₂*n*₁ + *N*₁*n*₂ (mod *N*); coming out, *k* is read by
the Chinese remainder theorem. The two sets of short transforms then need
nothing between them. Cooley and Tukey (1965) cited the paper. Their
method works for any factors, but pays "twiddle factors" to join the
pieces.

The program is written in TRI-TRAN ([TRITRAN.md](TRITRAN.md)). A ternary
machine's own fast transform is radix 3, with the data in trit-reversed
order, so the program transforms a signal of length 108 = 27 × 4 three
ways. It counts the real multiplications and times each way by the clock:

| method | multiplications | cycles (Model 90) |
|---|---:|---:|
| the direct sum | 46,656 | 3,536,148 |
| Cooley–Tukey, 27 × 4, with twiddles | 1,192 | 177,119 |
| Good, 27 × 4, no twiddles | 880 | 172,701 |

All three agree to about 2×10⁻⁸ on values of 54, and the spectrum is
exactly where the two tones put it.

**What it shows:** the idea, and the machine doing Good's arithmetic.
Good's maps save 312 multiplications, 26% of them. **What it does not:**
that this matters much here. The same maps save only 2.5% of the time.
In 1958 the multiplications were the work, done on desk calculators. On a
machine with a floating-point unit, moving and indexing the data cost more
than multiplying it. The program works this out from its own counts and
clock and prints it. The fast transforms themselves, not Good's refinement
of them, are what take the time from 3.5 million cycles to under 0.2
million.

### 10. The perceptron, and the weight of evidence — `programs/good/perceptron.sal`

Rosenblatt's perceptron (1958; the Mark I, 1960) had a retina of
photocells, a layer of **association units** wired to the retina at
random, some connections excitatory and some inhibitory, and a
**response unit** whose weights were corrected whenever it answered
wrongly. On the Duwamish every part of it is three-valued:

| part | +1 | −1 | 0 |
|---|---|---|---|
| retina point | ink | paper | not seen |
| connection | excitatory | inhibitory | none |
| A-unit | its points match its connections | they match the opposite | neither |
| response | vertical | horizontal | "I do not know" |

The retina is 7 × 7. There are 3⁵ = 243 A-units, each wired to three
nearby points. The task is to tell a vertical bar of four from a
horizontal one, anywhere on the retina, with one point in 25 wrong.

**1. Learning.** Two perceptrons learn by Rosenblatt's error correction
from 800 new patterns. When the answer is not right, the A-units'
outputs, times the right answer, are added to the weights. One answers
whenever its sum is not zero. The "cautious" one answers only when the sum
passes a threshold of 12. The corrections per hundred patterns fall from
38 to 19.

**2. What Good would have done.** The same A-units, read as witnesses.
Count, in one pass over the same 800 patterns, how often each unit says
+1, 0 or −1 for each class. Its weight of evidence for "vertical" is then
10 log₁₀ of the ratio of those frequencies, in decibans, computed as in
Banburismus (§7). Add the weights, and answer only past ±20 db, odds of
100 to 1; otherwise say "don't know". This is a sequential test that has
run out of evidence. Tested on 200 new patterns (Model 90):

| | right | wrong | don't know |
|---|---:|---:|---:|
| *the whole retina seen* | | | |
| perceptron | 176 | 19 | 5 |
| cautious perceptron | 150 | 7 | 43 |
| Good's weight of evidence | 167 | 8 | 25 |
| *a third of the retina unseen* | | | |
| perceptron | 121 | 77 | 2 |
| cautious perceptron | 104 | 53 | 43 |
| Good's weight of evidence | 122 | 19 | 59 |

Counting evidence once does about as well as 800 corrections. When a
third of the retina is hidden, the perceptron that must answer is wrong
77 times in 200. The weight of evidence is wrong 19 times, and says it
does not know 59 times: an unseen point is 0, and 0 carries no evidence.
But the evidence **overstates its case**. Its surest wrong answer claimed
+65 db, odds of three million to one. Good's rule adds evidence from
*independent* witnesses, and A-units that share retina points are not
independent.

**3. The limit.** Is the number of ink spots among five points odd? Minsky
and Papert proved in 1969 that this predicate, parity, has *order* 5: a
perceptron can compute it only if some A-unit looks at all five points.
The program trains 81 A-units of each order *k* from 1 to 5 on all 32
patterns, up to 100 passes:

| k | outcome | right | wrong | don't know |
|---|---|---:|---:|---:|
| 1–4 | not learned | 0 | 0 | 32 |
| 5 | learned in 2 passes | 32 | 0 | 0 |

Units of lower order do worse than fail. After every pass, the corrections
have cancelled: the perceptron answers all 32 patterns 0, "I do not
know". The program checks this after each pass. A binary perceptron would be forced to guess, and would be
right half the time by chance. The ternary one reports that it has
learned nothing.

**What it shows:** the perceptron learning, and an honest comparison of
error correction with Good's counting of evidence. Both are linear
threshold rules over the same witnesses, with their weights got in
different ways. The third output, "don't know", appears in all three
parts: as caution, as a verdict the evidence has not reached, and as the
answer to a question the machine cannot learn. **What it does not show:**
a Mark I, which had 400 photocells and 512 A-units; any claim that one
rule is better in general; or anything the committee could have known in
1967 about Minsky and Papert's book of 1969.

---

## Douglas Hofstadter

### 11. Self-reference by arithmetic — `programs/hofstadter/selfref.sal`

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

### 12. Quining — `programs/hofstadter/quine.sal`

A SALISH program whose output is exactly its own source text, byte for
byte. The test suite checks this on every run. It follows Hofstadter's
"quining": a text that contains its own quotation plus instructions for
using it. `tools/make_quine.py` shows how the text was constructed. TRILISP's
tour includes the LISP version, checked in-machine by `(equal (eval q) q)`.

### 13. The MU puzzle — `programs/hofstadter/miu.sal`

This separates Hofstadter's **mechanical mode** from his **intelligent
mode**. Working inside the MIU system, the machine derives all 216
theorems up to length 12 and never finds MU, but it can only ever say
"not yet". Stepping outside, the invariant is that the number of I's is
never a multiple of 3. On a ternary machine "a multiple of 3" means "the
last trit is 0", and the machine checks that trit on every theorem it
derives. The table shows the count of I's in balanced ternary: the last
trit is always 1 or T.

### 14. Copycat: analogy as perception — `programs/hofstadter/copycat.sal`

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

### 15. BlooP, FlooP and GlooP — `sequences.sal`, `floop.sal`

With the word `bloop`, the SALISH compiler *certifies termination*. It
accepts only bounded `for` loops, no recursion and no indirect calls, and
prints a certificate. Hofstadter's tangled recursive sequences from GEB
chapter V (G, H, the married F and M, the chaotic Q, Figure-Figure) are
computed in BlooP, and G's closed form ⌊(n+1)/φ⌋ is confirmed. The
wondrous-numbers (Collatz) program is **refused** certification, with each
unbounded loop named, and then runs as FlooP. Whether *every* number is
wondrous is a GlooP question that no bounded loop can answer.

### 16. Levels, and the strange loop — `metacircular.lsp` (the `tower` job)

The tower of interpreters: Python → microcode → TRIAD → SALISH (the TRILISP
interpreter) → M-EVAL, McCarthy's LISP-in-LISP → M-EVAL again, running its
own source → `(FACT 2)`. Each level knows nothing of the trits beneath it
(Hofstadter's "levels of description", like Aunt Hillary's ant colony).
Each costs about 100–160 times the level below. The top interpreter is the
same *text* as the one below it, read as data: the program has become its
own subject.

### 17. The compiler that compiles itself, and improves itself once — `programs/selfhost/salish.sal`

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
form: a program whose output, one level up, is itself. (The quine, §12,
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

### 18. Contracrostipunctus — `diagonal.lsp`

The Crab's record players and the Tortoise's records. `HALTS?` is an honest
would-be oracle: it runs a program in M-EVAL with a step budget. It is right
about `(FACT 3)` and right about an endless loop. `CONTRARY` asks the oracle
about *itself* and does the opposite. The oracle says "runs forever";
`CONTRARY` then halts. Raising the budget changes nothing. This is Turing's
halting theorem, the engine of Gödel's.

### 19. The tangled hierarchy — the machine as a whole

The deepest Hofstadterian feature is architectural. The writable control
store lets software rewrite the microcode that runs it (§1). TRILISP can
`PEEK` at the words that *are* its objects, and `(WORD 42)` is 127 because
42 is stored as 3·42+1. The disassembler lets any SALISH program read its own
machine code. Every level can reach the level beneath it, and in the
explosion demonstration it reaches the bottom and alters it.

---

## The rest of the committee

### 20. Ultrastability: Ashby's homeostat — `programs/ashby/homeostat.sal`

Ashby's homeostat (1948; *Design for a Brain*, 1952) was four units, each a
magnet swinging in water and driven by currents from all four. Each
needle is an *essential variable* that must stay within bounds. When one
does not, a relay steps that unit's **uniselector**, a stepping switch
that rewires the unit's inputs at random. The machine never knows which
wirings are stable. It only knows when a needle is out of bounds, and it
changes something when one is. That is enough.

On the Duwamish:
- **The needles:** x′ = Ax, integrated in steps of 1/27.
- **A uniselector:** it has **27 positions**, one for each 3-trit word giving the signs of the unit's three inputs. Ashby's had 25, wired from a table of random numbers.
- **The relay:** it reads a **trit**: +1 above the bound, −1 below, 0 within. A `sign … of` statement (one J3) steps the switch when the trit is not 0.

The program, not the homeostat, checks each field for stability, by the
Routh–Hurwitz test on the characteristic polynomial. It draws a strip
chart of the four needles, time running down the page:

1. **Switched on** in an unstable field, the uniselectors move 20 times,
   and the needles settle in a stable one.
2. **Disturbed**: when a needle is pushed aside, the needles return
   without any switch moving. That is homeostasis.
3. **The environment changed**: the experimenter reverses a connection,
   as Ashby did, choosing one that makes the field unstable. The
   uniselectors move 4 times and find a new stable field. That is
   adaptation.
4. **The statistics**: 136 of 729 random fields are stable, about 1 in 5.
   Switched on 20 times, the homeostat rests 18 times in a stable field,
   after 7.6 moves on average. Only the units whose needles go out of
   bounds move their switches, so what already works is kept. The other
   2 came to rest in unstable fields whose needles had not yet left their
   bounds. The homeostat can find out only through its needles. The
   program says so.

Section 17 of the notebook animates parts 1 to 3 (`duwamish/homeoview.py`):
- four meters with their bounds;
- each unit's relay trit and its uniselector's three trit lamps;
- a strip chart of the needles, with a tick at every move.

### 21. Conway's Life in Kleene's logic — `programs/knuth/life.sal`

Let a live cell be +1 and a dead one −1. Then the tritwise instructions
form a Boolean algebra:

| operation | instruction |
|---|---|
| *and* | AND (the minimum) |
| *or* | OR (the maximum) |
| *not* | negation |
| *same* | EQV (the product) |
| exclusive or | −EQV |
| parity of three | eqv(eqv(a, b), c) |

A row of 27 cells is one word. A generation is full adders built from
these operations, about 40 cycles a cell on the Model 90. The third value
is the point: a cell of **0 is unknown**. Kleene's logic is *sound*:
whatever it calls alive or dead is so in every world the unknown cells
could stand for.

1. **The ordinary game**, with nothing unknown. The test suite checks
   that it is exactly Conway's rule.
2. **A world partly unseen.** A blinker beside one unseen cell, a glider,
   and a block two cells from another. The program runs all 16 worlds the
   four unknown cells could stand for, and checks at every generation that
   every cell Kleene called alive or dead was so in all of them. Then it
   shows the other side: **the logic is sound but far from complete**. At
   generation 8 it leaves 124 cells unknown, where in truth only 7 are.
   It cannot see that *x* or not *x* is true when *x* is unknown, and
   ignorance spreads through that blind spot faster than the facts
   require. Both pictures are printed side by side.
3. **The world beyond the edge unknown.** Ignorance comes in from every
   side at one cell a generation, Conway's "speed of light", until the
   whole world is fog at generation 14.

Section 16 of the notebook animates both scenes, generation by
generation, from the machine's core (`duwamish/lifeview.py`). Kleene's
fog is on the left and the truth on the right. A cell where Kleene
contradicted the truth would show red, and none ever does.

### 22. Sorting when a comparison has three outcomes — `programs/knuth/sorting.sal`

A comparison has three outcomes, and on the Duwamish one CMP and one J3
branch on all three. With 3,000 keys, on the Model 90:

| keys | Hoare (two-way) | Dijkstra (three-way) | Bentley–McIlroy (three-way) |
|---|---:|---:|---:|
| distinct | 48,766 comparisons, **3,258k cycles** | 40,256, 4,526k | 43,921, 4,716k |
| ten values | 44,600, 3,469k | 9,800, **826k** | 11,953, 1,456k |
| three values (trits) | 42,159, 3,474k | 6,062, **472k** | 6,062, 1,006k |
| already sorted | 37,903, **2,391k** | 33,261, 3,841k | 32,869, 3,570k |

Three-way partitioning is a large win when keys repeat: seven times
faster on trit-valued keys. Hoare's tight two-way scans still win on
distinct keys. In Bentley and McIlroy's partition the three-way branch
does something real: the scan's own comparison has already said whether
a key equals the pivot, so the extra equality tests a binary machine
needs cost nothing.

Heapsort with d-ary heaps: the ternary heap makes the fewest comparisons
(58,269, against 60,286 for binary and 62,393 for 4-ary), as the cost
d / ln d, least at *e*, predicts. The 4-ary heap moves the fewest words
and takes the fewest cycles here. The program prints all three results
and does not pick the one it likes.

### 23. Ternary search trees, and radix 3 — `programs/knuth/tst.sal`, `programs/knuth/fft23.ftn`

A **ternary search tree** stores strings a character at a time, with
links for lower, equal and higher. Its search is one CMP and one J3 a
node. Built from the 797 words of Genesis 1, it makes 6,665 character
comparisons against a binary tree's 8,108. It finds all 797 words again in
6,665 comparisons and 1.37M cycles, against 8,987 and 2.23M. It also lists
words by prefix and by pattern ("l.ght", ".a."), which the program checks
against Python. (The structure was named by Bentley and Sedgewick in
1997, long after the committee.)

**Radix 3 or radix 2?** It is often said that a ternary machine should use
a radix-3 FFT because the butterflies need fewer multiplications. The
program tests the claim, in TRI-TRAN. It transforms 256 points by radix 2
and 243 by radix 3, counts real multiplications, times both, and divides
by N log₂ N. The claim is wrong: radix 3 needs **1.35 times** the
multiplications for the same work. But it takes **0.86 times** the cycles
on every model, because it makes log₃ N passes over the data instead of
log₂ N. So the advice is right for the wrong reason.

---

## The AI of the period, in TRILISP

The committee met in 1967. These are the programs the field was writing
around then, run on the Duwamish in its LISP. They share a small prelude
(`programs/ai/prelude.lsp`). TRILISP interprets at about 7,000
evaluations a second of simulated time, which kept each program small.

### 24. ELIZA — `programs/ai/eliza.lsp` (the `eliza` job)

Weizenbaum's program (1966), with the DOCTOR script. It finds the
highest-ranked keyword, decomposes the sentence with that keyword's
patterns, and reassembles it with "I" and "you" exchanged, using each
decomposition's reassemblies in turn. It cuts a sentence at a comma, a
full stop or BUT, and it remembers what was said after MY for later. The
script is a reconstruction of the part of DOCTOR needed for **the
conversation printed in Weizenbaum's paper, which it reproduces word for
word**, from "MEN ARE ALL ALIKE." / "IN WHAT WAY" to "BULLIES." / "DOES
THAT HAVE ANYTHING TO DO WITH THE FACT THAT YOUR BOYFRIEND MADE YOU COME
HERE". The test suite checks every reply. That it can be done with so
little is Weizenbaum's point.

### 25. GPS — `programs/ai/gps.lsp`

Newell, Shaw and Simon's General Problem Solver (1959) on the Tower of
Hanoi, by means-ends analysis:
- find the most important difference between the state and the goal: the largest misplaced disk;
- reduce it with the operator the table of connections names;
- when the operator does not yet apply, make that a subgoal.

A state is an *n*-trit word, since each disk is on one of three pegs. It
solves 3 to 6 disks in 2ⁿ − 1 moves, the fewest possible, and never
searches: the ordering of the differences does all the work.

### 26. STRIPS — `programs/ai/strips.lsp`

Fikes and Nilsson's planner for Shakey (1971): operators with
preconditions, a delete list and an add list, and a planner that works
backwards from the goal. Shakey is in room 3, a box in room 1, and the
light switch in room 2 is too high to reach. The goal is the light on.
The plan has ten steps: through two doors, push the box back through
one, push it under the switch, climb on it, turn the light on. The
program then carries the plan out on a copy of the world, checking every
precondition as it goes.

### 27. Micro-SHRDLU — `programs/ai/shrdlu.lsp`

Winograd's blocks world (1970–72), in miniature. The program parses a
handful of sentence patterns, works out what the noun phrases refer to,
and then answers or plans and carries out moves.
- **Reference:** "the pyramid" is resolved by what was just said, as are "it" and "them".
- **Descriptions** can nest: "a block which is taller than the one you are holding".
- **Moves** are shown in brackets.

The world is built so that the first dozen exchanges of the dialogue in
*Understanding Natural Language* come out as printed:
- "GRASP THE PYRAMID." / "I DON'T UNDERSTAND WHICH PYRAMID YOU MEAN."
- "BY 'IT', I ASSUME YOU MEAN THE BLOCK WHICH IS TALLER THAN THE ONE I AM HOLDING."
- "HOW MANY BLOCKS ARE NOT IN THE BOX?" / "FOUR OF THEM."
- "CAN A PYRAMID SUPPORT A PYRAMID?" / **"I DON'T KNOW."**

That last answer is Winograd's three-valued rule: *yes* if the world shows
an example, *no* if the program knows a reason, and otherwise "I don't
know". Asked to STACK UP TWO PYRAMIDS it says "I CAN'T". One exchange is
ours, not Winograd's: asked again after trying, it answers "NO -- I HAVE
TRIED." The unknown became false by experiment.

### 28. A three-valued Prolog — `programs/ai/prolog.lsp`

Horn clauses and SLD resolution (Colmerauer and Kowalski, 1972), with
three answers instead of two:
- **TRUE:** proved.
- **FALSE:** the negation is proved, or the predicate is declared closed.
- **UNKNOWN:** neither, or the search went past its depth bound.

`NOT` is Kleene's negation and a body is Kleene's conjunction. Each
answer is printed beside the one Prolog's negation as failure gives:

| question | three values | Prolog |
|---|---|---|
| (GRANDPARENT TOM ANN) | TRUE | YES |
| (PARENT ANN TOM), PARENT closed | FALSE | NO |
| (FLIES OPUS), a penguin | FALSE | NO |
| (FLIES TWEETY), nothing known of penguins | UNKNOWN | YES |
| (PENGUIN TWEETY) | UNKNOWN | NO |
| (LIKES BOB CAROL), with LIKES symmetric | UNKNOWN | no answer: it loops |

Where Prolog says Tweety flies, it has assumed that what it cannot prove
is false. Where the search goes round in circles, the bounded prover says
UNKNOWN, because it cannot tell *not yet* from *never*. That is the lesson
of FlooP (§15) in another form.

---

## Good's evidence as a language: WHALE

### 29. A clinic that weighs its evidence — `programs/whale/diagnosis.whl`

WHALE ([docs/WHALE.md](WHALE.md)) is SALISH with an associative store, as
SAIL was ALGOL with LEAP. Its facts are triples, and each one carries a
weight of evidence, so that it is true (at least +20 db), false (−20 db
or below), or unknown. The tour (`programs/whale/tour.whl`) shows the
language: an open world, where what has not been stated is unknown rather
than false; questions in every direction; rules run to a fixed point; a
move that is neither allowed nor forbidden until someone looks; and
glimpses in poor light that add up to a verdict.

The clinic puts three of Good's ideas to work together:

* **Learning the weights.** From 400 records of a world it is never shown
  (five diseases, twelve findings), the program counts and computes the
  weight of evidence of each finding, present or absent, for each disease
  against the field. Every count is flattened by a half, so a finding
  never seen with a disease counts strongly against it but not infinitely.
  Ten counts were 0, or every case. The learned weights come close to the
  true ones (rash for measles: +12.8 db learned, +14.3 db true). The
  store can answer "which findings settle measles by themselves?" with
  the true triples: Koplik's spots.
* **Weighing sequentially.** A patient is examined one question at a
  time. Each answer's weight goes onto every diagnosis, and the
  examination stops when one reaches 20 db (Wald). When the questions run
  out first, the verdict is "unknown" and the patient is referred. The
  weights are **conditional**, W(H : F | E), taken against the remaining
  diagnoses as they stand after the earlier answers. This is the form in
  which Good showed that weights add exactly. Adding fixed weights learned
  against the whole field ("naive") gives 2 wrong diagnoses in 100, where
  the conditional weights give none.
* **Choosing the question.** Good's quasi-utility of an experiment is its
  expected weight of evidence. Asking the question expected to tell most
  about the leading diagnosis takes 7.4 questions on average against 10.3
  in a fixed order, and diagnoses 73 patients rather than 62.

Wald's trade-off is visible directly: at 10 db the clinic asks 3.1
questions and makes 8 mistakes; at 30 db it asks 11.4 and refers 83
patients. Learning from 25, 100, 400 and 1600 records diagnoses 57, 81,
73 and 76 patients (77 with the true weights), with none wrong.

**What it shows:** weights of evidence as the currency of a reasoning
program. It learns them, adds them, decides on them, chooses its next
question by their expected value, and does all of this in a store where
"unknown" is a value of its own. **What it does not show:** medicine.
The world is invented, and its findings are independent given the
disease. That is exactly the assumption the weights need, so the clean
result here is the best case.

The notebook (§20) animates the clinic. It shows each diagnosis's weight
between Wald's boundaries, question by question, with Good's order beside
a fixed one for the same patient.

## Pask's teaching machine

### 30. SAKI, the Self-Adaptive Keyboard Instructor — `programs/pask/saki.sal`

Gordon Pask and Robin McKinnon-Wood built SAKI in the 1950s to train
card-punch operators. A light over the keyboard could show the trainee
the right key. SAKI recorded how quickly and how accurately each item
was answered, held the light back on items the trainee had learned, and
gave more practice on the ones the trainee found hard. Pask's argument
was cybernetic. The trainee and the machine are a coupled system, like
two units of Ashby's homeostat. A task that is too easy loses the
trainee's attention, and one that is too hard breaks the trainee down.
A machine that cannot tell which is happening cannot teach everyone.

On the Duwamish a simulated trainee learns the ten numeric keys. Its
memory of each key, its attention and its learning rate are hidden from
the machines. Each item's answer is a trit: **+1** the key was found from
memory, before the light; **0** it was found by the light; **−1** the
wrong key. SAKI's rule for adjusting a key's light is a single three-way
jump on that trit: +1 holds the light back 0.2 s longer; 0 holds it back
a little longer if the trainee answered quickly after it came on, or
brings it a little sooner if the trainee needed it; −1 halves the delay.
SAKI judges a key mastered when it has been found from memory three
times running with the light held back as far as it goes. It ends the
lesson when every key is mastered.

Fifteen trainees (slow, average and fast) are taught by three machines
and then tested with no lights:

| machine | trainee | keys found | items in the lesson | errors | attention |
|---|---|---|---|---|---|
| always lit | slow / average / fast | 31% / 36% / 38% | 800 | 0 | 43% |
| fixed fading, set for the average trainee | slow / average / fast | 55% / 96% / 97% | 800 | 133 / 20 / 7 | 65% / 80% / 82% |
| SAKI | slow / average / fast | 94% / 96% / 96% | 1363 / 836 / 561 | 55 / 26 / 9 | 97% / 96% / 96% |

A light that is always on teaches the trainee to follow lights, not the
keyboard, and the trainee gets bored. A fixed schedule suits the trainee
it was set for. It outpaces the slow ones, who make errors, lose their
attention and do not recover, and it keeps the fast ones at work long
after they have learned. SAKI gives each trainee the lesson that trainee
needs. In part 1 its delays, which are its model of the trainee, are
printed beside the trainee's hidden memory.

**What it shows:** Pask's adaptive teaching, and the requisite variety
behind it. The teacher has to be able to vary as much as its pupils do.
**What it does not show:** a real trainee. The learner is a simple model
with Pask's claims built into it (memory learned through retrieval,
boredom, distress). The program shows that a machine that adapts gets
these effects under control, not that people work this way.

The notebook (§19) animates one slow trainee taught by SAKI and by the
fixed schedule, side by side. Each key's light fades as SAKI holds it
back, and SAKI's model of the trainee is drawn beside the trainee's hidden
memory. Under the schedule the trainee's memory still grows, but attention
collapses.

---

## Also from the committee

* **Rosenblatt**: the perceptron, in ternary, against Good's weight of
  evidence, and up against Minsky and Papert's limit (§10).
* **Ashby** (§20), **Knuth** (§21–23) and **Pask** (§30) are above.
* **Kleene and McCarthy logic** (`programs/kleene.sal`): three-valued
  truth tables, each connective a single ternary instruction.
* **Beer**: every run can be profiled from the tallies
  (`duwamish/profile.py`); the explosion uses them to watch itself.
* **Cray / System/360**: two implementations of one architecture, checked
  equivalent by randomized testing (`tests/test_machine.py`).
