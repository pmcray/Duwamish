# REFAL on the Duwamish

Valentin Turchin designed **Refal** (*Recursive Functions Algorithmic
Language*) in Moscow from 1966. It was a language for working on programs
and texts by pattern matching, and it became the ground for his later work
on *metasystem transitions*, in which programs run, examine and transform
other programs. Turchin's supercompiler of the 1970s and 1980s, and the
"mixed computation" studied in Ershov's school at Novosibirsk, both grew
from this ground. Refal was used across the Soviet Union, and versions ran
on the BESM-6 and the ES machines.

On the Duwamish, Refal is an interpreter written in SALISH
(`duwamish/lib/refal.sal`) and catalogued like TRILISP. It reads a
program from the cards and evaluates `<Go>`, or the first `$ENTRY`
function.

```
//JOB  MYJOB
//EXEC REFAL
//DATA FROM=program.ref
```

```
python -m duwamish run --model 90 jobs/refal.job      # the tour
```

## The language

This Refal follows Refal-5, the version Turchin described in his *Refal-5
Programming Guide and Reference Manual*.

```
* a line beginning with * is a comment; so is /* ... */
$ENTRY Go { = <Prout 'Hello, world'>; }

Reverse { t.1 e.2 = <Reverse e.2> t.1; = ; }
Pal     { = True; s.1 = True; s.1 e.2 s.1 = <Pal e.2>; e.1 = False; }
```

**Data.** An expression is a sequence of terms. A term is a *symbol* or a
parenthesised expression `( ... )`. Symbols are characters (`'abc'` is
three of them), words (`True`, `Akademgorodok`, or `"any text"` in double
quotes) and numbers (`42`). The structure brackets `( )` are the only
structure.

**Programs.** A function is a list of sentences, `pattern = result;`,
tried in order. The first whose pattern matches the argument gives the
result. In patterns:

| variable | matches |
|---|---|
| `s.X` | one symbol |
| `t.X` | one term: a symbol, or a whole parenthesis |
| `e.X` | any expression, empty or not |

A variable that appears twice must match the same thing both times
(`s.1 e.2 s.1` is a string whose ends agree). An e-variable takes the
shortest piece that lets the rest of the pattern match. If the rest
fails, it takes one term more.

**Calls.** In results, `<F e>` calls `F` on `e`. The argument is evaluated
before the call.

**Conditions** (Refal-5's *where-clauses*):

```
Split { e.1 ',' e.2, <Lenw e.1> : s.N e.3, <Compare s.N 0> : '+' = (e.1) (e.2); }
```

After the pattern matches, each condition `, expr : pattern` is evaluated
and matched in turn, and may bind new variables. If a condition fails,
matching goes back into the pattern and tries the e-variables longer.
Here `Split` finds the first comma that has something before it:
`<Split ',abc,de'>` gives `(,abc)(de)`.

## Built-in functions

| function | |
|---|---|
| `<Prout e>` / `<Print e>` | print `e` and a new line; Print also returns `e` |
| `<Card>` | the next card, as characters; the number 0 at the end |
| `<Add s.1 s.2>` `Sub` `Mul` `Div` `Mod` | arithmetic on numbers (either may be in parentheses) |
| `<Compare s.1 s.2>` | `'-'`, `'0'` or `'+'`: a three-way answer, one J3 on the Duwamish |
| `<Numb e>` / `<Symb s.N>` | characters to a number, and back |
| `<Chr e>` / `<Ord e>` | numbers to characters, and back |
| `<Explode s.W>` / `<Implode e>` | a word to its characters, and back |
| `<Lenw e>` | the length of `e`, then `e` |
| `<Type e>` | `'L'` letter, `'D'` digit, `'W'` word, `'N'` number, `'B'` bracket, `'O'` other, `'*'` empty; then `e` |
| `<Br e.name '=' e.value>` / `<Dg e.name>` / `<Cp e.name>` | the store: bury a value, dig it up (removing it), or copy it |
| `<Mu s.F e>` | call the function named by the word `s.F` |
| `<Step>` | the number of steps so far |

Numbers are single words and may be negative. Refal-5 has unbounded
numbers, which are written as sequences of "macrodigits"; this one does
not.

## How it is made

* **Expressions** are lists of nodes in a heap of 30,000. Data are never
  changed once built, so lists can share their tails. An e-variable that
  matched the tail of its argument, written last in a result, is linked
  rather than copied.
* **Evaluation** builds a result and evaluates its calls in the same pass.
  A result that is a single call is followed in a loop, so a Refal loop
  runs in constant stack. When a result ends in a call (`s.P <Primes
  ...>`), the interpreter lets go of the current level's bindings and
  argument before calling, so a long recursion holds only what is still
  to be written.
* **Matching** backtracks through the e-variables and into structure
  brackets, using a stack of continuations, and goes back from a failed
  condition into the pattern.
* **Storage** is reclaimed by mark and sweep, scanning the machine stack
  for anything that looks like a node, as TRILISP does. Nodes are numbered
  from 1,000,000, so that nothing else on the stack looks like one.

A classical Refal machine keeps the whole computation in one "view field"
and needs no stack. This interpreter recurses where results nest calls
inside other terms, so such nesting is limited to about 2,000 levels.
Beyond that it stops with "RECURSION TOO DEEP", where Refal-5 would go
on. Loops written as accumulating tail calls have no limit.

Copying has a cost too. Data here are never changed in place, so a
variable written anywhere but at the end of a result is copied. A
function that grows an accumulator, such as the quicksort's partition
`(e.L s.X)`, copies the whole accumulator at every step. Refal-5 relinks
in place instead. The interpreter runs about a thousand simple Refal steps
a second of Duwamish time, fewer where accumulators grow: sorting 200
numbers takes about 11,000 steps and a minute and a half.

**A bug worth recording.** In SALISH, 0 is *unknown*, not false. The
collector's first version tested its mark bits with `if not nmark[i]`.
For an unmarked node that is "not unknown", which is still unknown, so
the sweep never freed anything. Kleene's logic, enforced by the language,
caught a programmer treating 0 as false.

## The programs

`programs/refal/tour.ref` covers:

* patterns: reversal, palindromes, substitution, a repeated symbol;
* a condition that sends an e-variable back to grow;
* differentiation with simplification;
* the primes below 200 by the sieve;
* a quicksort that partitions on `Compare`'s three answers;
* calling by name;
* the store.

`programs/refal/mix.ref` (the `mix` job, about twenty seconds) is mixed
computation, below.

## Mixed computation

Suppose a program's input comes in two parts, one known now and one known
later. Mixed computation does all the work that depends only on the known
part. What is left is written out as a *residual program* that waits for
the rest. Ershov's school at Novosibirsk gave it this name. Futamura
(1971) and Turchin, with supercompilation, reached the same idea. Futamura
saw the consequence. Specialise an *interpreter* to a *program* and the
residual program does what the program does, without the interpreter: it
is the program **compiled**. This is Futamura's first projection.

```
python -m duwamish run --model 90 jobs/mix.job
```

`mix.ref` holds a small flowchart language of the kind Ershov's school
studied as program schemes: blocks of assignments, each ending in `goto`,
`if` or `return`. It also holds its interpreter, `Run`, and a specialiser,
`Mix`, all written in Refal.

* **Binding times.** Every variable is *static* (known now) or *dynamic*
  (known later). A binding-time analysis sweeps the program until it
  settles. A variable is dynamic if it is a parameter with no value yet,
  or if it is ever given a value that depends on a dynamic variable.
* **Driving.** `Mix` starts from the first block, with the static values.
  Static assignments are done. Dynamic ones are written out, with every
  static part replaced by its value. A `goto`, or an `if` on a static
  condition, is followed at once.
* **Polyvariance.** An `if` on a dynamic condition is written out. Each
  branch becomes a residual block, one for each pair of (label, static
  values), made the first time it is reached. When the same pair is
  reached again, the residual program jumps back to the block already
  made, and that is how the residual program comes to have loops. `Mix`
  keeps the table of pairs and the queue of blocks still to be made in
  Refal's store (`Br`, `Dg`, `Cp`).

**Power**, with n = 5 known, unrolls into straight-line code:

```
   program (X N)
     Init: P := 1; goto Test
     Test: if Eq(N, 0) then Done else Loop
     Loop: P := Mul(P, X); N := Sub(N, 1); goto Test
     Done: return P

   program (X)
     B1: P := 1; P := Mul(P, X); P := Mul(P, X); P := Mul(P, X); P := Mul(P, X); P := Mul(P, X); return P
```

**The first projection.** A Turing-machine interpreter is written as a
flowchart, 13 blocks long. Its program `Q` is static; the tape, `L` and
`R`, is dynamic. The Turing machine finds the first 0 on the tape and
writes 1 there:

```
     0 If 0 3
     1 Right
     2 Goto 0
     3 Write 1
```

Specialising the interpreter to that program gives:

```
   program (R)
     B1: L := (); if Eq(0, First(R)) then B2 else B3
     B2: R := Cons(1, Rest(R)); return Join(L, R)
     B3: L := Cons(First(R), L); R := Rest(R); if Eq(0, First(R)) then B2 else B3
```

The interpreter's work is gone: fetching instructions, decoding them,
finding the target of a jump. What is left is the Turing machine's own
work, and its loop has become a loop of the residual program, B3 to B3.
The output is a program in the flowchart language, and the same `Run`
runs it:

| run | result | Refal steps |
|---|---|---|
| power, interpreted, x = 3, n = 5 | 243 | 266 |
| power, residual, x = 3 | 243 | 86 |
| Turing machine interpreted, tape 1 1 0 1 0 1 | 1 1 1 1 0 1 | 1,116 |
| Turing machine compiled, tape 1 1 0 1 0 1 | 1 1 1 1 0 1 | 150 |
| Turing machine interpreted, tape 1 1 1 1 1 0 | 1 1 1 1 1 1 | 2,268 |
| Turing machine compiled, tape 1 1 1 1 1 0 | 1 1 1 1 1 1 | 288 |

The compiled program is 7½ times faster on the shorter tape and 8 times
on the longer. The saving is the cost of interpretation, which is paid
again at every step of the Turing machine.

The flowchart language, the Turing-machine example and the shape of `Mix`
(a pending queue, a table of what has been made, a `goto` followed at
once) are those of Jones, Gomard and Sestoft's *Partial Evaluation and
Automatic Program Generation* (1993). That book came long after the
period. The ideas it set out came from Moscow, Novosibirsk and Tokyo in
the 1970s.

**What it does not do.** There are two further projections. Specialising
the specialiser to the interpreter gives a *compiler*. Specialising the
specialiser to itself gives a *compiler generator*. For either, `Mix`
would have to be written in the flowchart language it specialises, so
that it can be its own subject. Jones's group in Copenhagen first made
that work, in the mid-1980s. This `Mix` is written in Refal, so it stops at the first
projection. It also trusts its input: a static loop that never meets a
dynamic `if` would be followed for ever.
