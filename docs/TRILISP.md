# TRILISP — reference manual

TRILISP is a LISP in the style of LISP 1.5, written in SALISH
(`duwamish/lib/trilisp.sal`, about 700 lines) and running *on* the
Duwamish. Run it with `//EXEC TRILISP`; the cards that follow `//DATA` are
read, evaluated and printed. Input is folded to upper case.

## One trit, three types

Every object is one word, and its **least significant trit** says what it is:

| last trit | object | word |
|---:|---|---|
| +1 | number *n* | 3*n* + 1 |
| 0 | cons cell *i* | 3*i* |
| −1 | symbol *j* | 3*j* − 1 |

`NIL` is symbol 0 (the word −1) and `T` is symbol 1 (the word 2). `(TAG x)`
shows the tag trit and `(WORD x)` the raw word. Numbers have 26 trits,
±1,270,932,914,164, and wrap silently beyond that.

## Special forms

`QUOTE` (and `'x`), `IF`, `COND` (with `ELSE`), `LAMBDA`,
`DEFINE` (`(define x v)` or `(define (f . args) body…)`),
`DEFMACRO` (`(defmacro (m . args) body…)` — the body computes the
expansion), `LET`, `SETQ`, `PROGN`, `AND`, `OR`.

`EVAL` is properly **tail-recursive**. `IF`, `COND`, `PROGN`, `LET`, `AND`, `OR`
and closure application all loop instead of recursing, so a loop written
as tail recursion runs in constant machine stack. `(lambda (a . rest) …)`
takes a variable number of arguments.

## Primitives

`CAR CDR CONS ATOM EQ NULL NOT NUMBERP SYMBOLP CONSP LIST EQUAL LENGTH
+ - * / MOD < > <= >= = PRINT PRIN1 TERPRI RPLACA RPLACD APPLY EVAL SET
ERROR EXPLODE IMPLODE GC ECHO`, and, reaching beneath the language:
`WORD TAG PEEK POKE CLOCK EVALS TPRINT`.

A string `"like this"` reads as a symbol that evaluates to itself, which is
useful for messages. `(explode "...")` turns one into its characters,
punctuation included (`"."` is a symbol, not a dot), which is how the AI
programs in `programs/ai/` read sentences. `(ECHO NIL)` stops the reader echoing each form and
its value.

## Storage

30,000 cons cells, with mark-and-sweep collection. The marker uses an
explicit stack. The roots are the symbol values and **every word of the
machine stack that looks like a cons pointer**. Plain SALISH keeps all
its temporaries in memory. Under SALISH/O some live in registers, and
`stackptr()` stores the registers on the stack before the collector
scans it. Either way, a conservative scan of the stack finds every live
object.

Section 13 of the notebook (`duwamish/heapview.py`) runs TRILISP with a
small heap and replays its memory cell by cell: allocation, the mark
phase and the sweep.

Errors print `*** ERROR:` and return to the top level through
`catchpoint`/`throw`.
