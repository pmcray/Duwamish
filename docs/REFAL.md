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
on. Loops written as accumulating tail calls have no limit. The
interpreter runs about a thousand Refal steps a second of Duwamish time.

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
