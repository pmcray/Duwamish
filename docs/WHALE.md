# WHALE — the Woodworth Heuristic Associative Learning Evaluator

Stanford's Artificial Intelligence Laboratory had SAIL, ALGOL 60 with
Feldman and Rovner's associative store (LEAP, 1969). In the Duwamish
fiction, the Artificial Intelligence Laboratory of Woodworth University
(WAIL), one of the first places to take delivery of a Duwamish, had
**WHALE**: SALISH with an associative store, where each fact carries a
weight of evidence.

* **Associative**: facts are triples, *attribute* `of` *object* `is`
  *value*, as in LEAP (`A ⊗ O ≡ V`), and the program can ask about any of
  the three.
* **Evaluator**: each triple has a weight of evidence, in Turing's and
  Good's decibans, and Wald's sequential test turns the weight into a
  three-valued verdict.
* **Learning**: evidence adds up. `confirm` adds the weight of a new
  observation, and the program's beliefs follow.
* **Heuristic**: `foreach ranked` looks at the best-supported
  possibilities first.

```
python -m duwamish go --model 90 programs/whale/tour.whl   # compile and run
python -m duwamish compile programs/whale/tour.whl          # show the TRIAD code
python -m duwamish run --model 90 jobs/whale.job            # the tour and the clinic
```

```
//JOB  MYJOB
//WHALE [FROM=file] [LIST] [OPT]   compile the cards that follow (or a file)
//EXEC
```

The compiler (`duwamish/whale.py`) extends the SALISH parser with the
forms below and rewrites them as SALISH: calls on the run-time store in
`duwamish/lib/whale.sal`. Every SALISH program is also a WHALE program,
except one that uses the new keywords as names: `item make deny erase
confirm foreach such that is fact weight the ranked new possibly`. Library
modules that a WHALE program gets with `get` are parsed as plain SALISH.

## Truth

Every triple has a weight *w*, held as hundredths of a deciban
(centidecibans): 1000 log₁₀ of the odds. Its truth is

| | weight | |
|---|---|---|
| **true** (+1) | *w* ≥ 20 db | odds of at least 100 to 1 for it |
| **unknown** (0) | −20 db < *w* < 20 db | |
| **false** (−1) | *w* ≤ −20 db | odds of at least 100 to 1 against it |

A triple that was never stated is unknown, not false: the store
describes an *open* world. A program can change the threshold (Wald's
*A* and *B*) through `wh_thresh`, which is in centidecibans and is 2000
by default. Truth values combine as everywhere in SALISH: `&` and `|`
are Kleene's connectives, so *unknown and false* is false, and `not` of
unknown is unknown.

## Declarations

```
item red, green, b1, b2, colour
```

Items are the things the store relates. Each one is a constant, numbered
from 1, and the program can print its name with `printitem(x)`. `new`
makes a fresh item while the program runs, as SAIL's `NEW` did. It
prints as `G` followed by its number. A program may have several `item`
declarations.

## Statements

| statement | effect |
|---|---|
| `make A of O is V` | true, with certainty |
| `deny A of O is V` | false, with certainty |
| `erase A of O is V` | forgotten: unknown again |
| `confirm A of O is V by w` | add *w* centidecibans of evidence; *w* < 0 is evidence against. A certainty is not moved. |
| `foreach x, y such that C₁ and C₂ … do S` | *S* for every binding of the variables for which the conjuncts hold |

Each of *A*, *O* and *V* is an expression whose value is an item.

In a `foreach`, each conjunct is either a triple or any SALISH condition.
In a triple, a variable that is not yet bound matches any item, and it is
bound to the item it matched for the conjuncts that follow. A variable
can appear twice in one triple (`likes of x is x`). A triple matches when
it is **true**. Written `possibly A of O is V`, it matches a stored
triple that is **true or unknown** (not false). `foreach ranked` takes
the matches of each triple in order of weight, best first.

```
foreach x, y such that on of x is y and colour of y is red do ...
foreach a, v such that a of b3 is v do ...           -- all that is known of b3
foreach ranked c such that possibly colour of b5 is c do ...
```

The matches for each triple are collected when its loop begins, so the
body may `make` and `erase` freely. (An erased triple's slot is reused
by the next one made, so a body that erases triples should not rely on
matches it has not reached yet.) `break` and `next` act on the
innermost triple of a `foreach`, which is the whole loop when there is
only one triple. A triple can match at most 128 triples per loop.

## Expressions

| expression | value |
|---|---|
| `fact A of O is V` | +1 true, 0 unknown, −1 false |
| `weight A of O is V` | its weight of evidence, in centidecibans (0 if never stated) |
| `the A of O` | the value best supported as true, or 0 |
| `new` | a fresh item |

## The library

`duwamish/lib/whale.sal` provides, besides the store:

| procedure | |
|---|---|
| `woe(p, q)` | the weight of evidence of the ratio *p*/*q*, in centidecibans, computed with a table of the hundredth powers of ten, as Banburismus was worked from tables of decibans |
| `chance(w)` | the probability, × 10⁵, of a hypothesis whose log-odds are *w* |
| `forget(x)` | erase every triple whose object is *x* |
| `printitem(x)`, `printitemw(x, n)` | an item's name (padded to *n*) |
| `printdb(w)`, `printdbw(w, n)` | a weight as `+12.3 db` |
| `printtruth(v)` | `true`, `false` or `unknown` |

The store holds up to 3000 triples and 1000 items. A triple can be found
by hashing on all three of its parts. The triples of one attribute are
also chained together, so a question that names the attribute looks only
at those triples. A question with the attribute unbound looks at every
triple.

## The programs

**`programs/whale/tour.whl`**: a few blocks, some of them seen only in poor
light.
1. In an open world, what has not been stated is unknown. A rule ("a
   thing has one colour") produces denials, but only for blocks whose
   colour is known.
2. Questions in every direction, and joins of several triples.
3. Rules run to a fixed point (*above* as the closure of *on*). Then a
   conclusion that has to wait: whether something may be put on b5 is
   unknown until someone looks at b5's top. A planner that treated
   unknown as false would never use b5. One that treated it as true might
   bury something.
4. Glimpses in poor light add up to a verdict: +8, +7, −3, +9 db.

**`programs/whale/diagnosis.whl`**: Good's weight of evidence applied to
a clinic.
1. *Learning.* From 400 hospital records, drawn from a world whose
   numbers the program never sees, the program learns the weight of
   evidence of each finding for each disease. Every count is flattened by
   a half, so the 10 counts of 0 (or of every case) do not produce
   infinite weights.
2. *Evaluation.* Patients are examined one question at a time, and each
   answer's weight is added. A diagnosis at 20 db stops the examination
   (Wald). If the questions run out first, the patient is referred.
3. *Heuristic.* The next question is the one with the greatest expected
   weight of evidence about the leading diagnosis, which is Good's
   "quasi-utility" of an experiment.

The weights add correctly only when each is *conditional*, taken against
the remaining diagnoses as they stand at that point:
W(H : E∧F) = W(H : E) + W(H : F | E). A clinic that adds fixed weights
learned against the whole field gets this wrong. On the hundred test
patients:

| | questions | right | wrong | referred |
|---|---|---|---|---|
| in a fixed order, 20 db | 10.3 | 62 | 0 | 38 |
| in Good's order, 20 db | 7.4 | 73 | 0 | 27 |
| in Good's order, 10 db | 3.1 | 89 | 8 | 3 |
| in Good's order, 30 db | 11.4 | 17 | 0 | 83 |
| adding fixed weights, 20 db | 8.1 | 61 | 2 | 37 |

Learning from 25, 100, 400 and 1600 records, and from the true weights,
gives 57, 81, 73, 76 and 77 right, with none wrong. The flattening means
that even 25 records (with one case of measles in them, or none) never
rule a disease out on one answer.

What this does **not** show: the world here is invented, and its
findings are independent given the disease, which is exactly the
assumption the weights need. Real findings are not independent, and
Good spent much of his later work on the "interactions" between them.
