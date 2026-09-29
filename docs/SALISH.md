# SALISH — reference manual

SALISH is the Duwamish systems language. It is named for the peoples of
Puget Sound, whose river the machine is named after. Like BCPL (Richards,
1967) it is **typeless**: every value is one 27-trit word, which may be
used as a number, a truth value, a character or an address. The compiler
(`duwamish/salish.py`) runs on the satellite and produces TRIAD assembly.

```
python -m duwamish go program.sal          # compile and run
python -m duwamish compile program.sal     # show the TRIAD code
```

## Lexical matters

* Comments run from `--` to the end of the line.
* Numbers: decimal `123`, balanced ternary `0t1T0` (= 6), characters `'a'`
  and `'\n'`.
* Strings: `"text"`, with escapes `\n \t \" \\`. A string's value is the
  address of a length-prefixed vector: `s[0]` is the length and `s[1]`…
  are the characters.
* **Newlines matter in one way.** An expression ends at a newline wherever
  it could end there. To continue a long expression, break the line
  *after* an operator, never before one. (BCPL has the same rule.)

## Declarations

```
get "disasm"                      -- include a library (or "microkit", "isakit")
const N = 100, M = N * 2          -- compile-time constants
global count := 0, name := "x"    -- static variables, with constant initialisers
global table[100]                 -- a static vector; `table` holds its address
global primes := table(2, 3, 5)   -- a static initialised vector
proc f(a, b) begin ... end        -- a procedure
proc sq(x) = x * x                -- a procedure whose body is one expression
inline proc tag(v) = xtr(v, 0, 1) -- expanded at each call site
bloop                             -- certify that this program terminates
```

The program starts at `proc main()`. Its result is the job's completion
code.

## Statements

```
x := e          v[i] := e          x +:= e         x -:= e
var a, b := 1, buf[80]                              -- locals, anywhere in a block
begin ... end
if c then s [else s]
while c do s
repeat s ... until c
for i := a to b [by step] do s                      -- bounds fixed on entry
sign e of  - : s   0 : s   + : s  end               -- three-way branch (J3)
return [e]      break      next
f(args)                                             -- call as a statement
```

In `sign … of` the arms may also be labelled `neg/zero/pos` or
`false/unknown/true`, and any arm may be omitted. When `e` is `a - b` the
compiler emits a single CMP.

## Expressions and three-valued logic

Truth is three-valued: **`true` = +1, `unknown` = 0, `false` = −1**. A
condition succeeds **only when its value is positive**.

| operator | meaning |
|---|---|
| `+ - * / mod` | arithmetic. `/` truncates toward zero; `mod` has the sign of the dividend |
| `<< >>` | multiply / divide by a power of **3** (ternary shift) |
| `= <> < <= > >=` | comparisons, yielding `true` or `false` (one CMP and one SEL) |
| `&` `\|` | tritwise min / max: **Kleene's** strong *and* / *or* |
| `and` `or` | **McCarthy's** sequential connectives: the left operand decides first, and an `unknown` there stays unknown |
| `not e`, `-e` | negation (the same thing in balanced ternary) |
| `c -> a, b` | conditional expression |
| `v[i]` | the word at address `v + i` |
| `@x` | the address of a variable |
| `f(a, b)` | call. If `f` is a variable, the call goes through it |
| `table(a, b, …)` | address of a static vector |

Precedence, loosest first: `->`, `or`, `and`, `not`, comparisons, `|`, `&`,
shifts, `+ -`, `* / mod`, unary.

**A caution for C programmers:** `if p then` is *not* taken when `p = 0`,
and `not 0` is `0` (unknown). Test pointers with `p <> 0`.

## Built-in procedures (compiled inline)

| call | effect |
|---|---|
| `putc(c)`, `getc()` | line printer / card reader (−1 at end of cards) |
| `ttyc(c)` | operator's console typewriter |
| `exit(n)` | end the job step |
| `peek(a)`, `poke(a, v)` | read / write any word of (user) core |
| `xtr(v, pos, len)` | the balanced value of trits pos … pos+len−1 |
| `trit(v, i)` | trit i of v |
| `clock()` | the cycle clock |
| `tally(a)`, `tclear()` | Beer-monitor execution counts |
| `rcs`, `wcs`, `rks`, `wks`, `rmap`, `wmap` | the writable control store (key permitting) |
| `codebase()`, `codeend()`, `heapbase()`, `stackptr()` | where the program lives |
| `catchpoint(buf)`, `throw(buf, v)` | non-local exit (setjmp/longjmp); `buf` is 3 words |

## The runtime library (always included)

`print(n)`, `printw(n, width)`, `printt(n)` (balanced ternary),
`printtw(n, w)`, `printh(n)` (heptavintimal), `printfix(n, places)`,
`prints(s)`, `printsw(s, w)`, `newline()`, `space()`, `spaces(n)`,
`truthname(v)`, `tritchar(t)`, `abs`, `min`, `max`, `alloc(n)`,
`streq(a, b)`, `readline(buf, max)`. Every routine is written with bounded
loops, so BlooP programs may call them.

Other libraries: `disasm` (read and disassemble machine code), `isakit`
(the instruction set as constants and tables) and `microkit` (the
microword format). The last two are generated from the assembler's own
tables at compile time.

## BlooP and FlooP

A program that contains the word `bloop` is accepted only if every
procedure reachable from `main` passes three checks:

* no `while` or `repeat` loops (a `for` loop's bounds and step are fixed
  on entry, and its variable may not be assigned in the body);
* no recursion, direct or mutual (the call graph must be acyclic);
* no calls through variables, and no `catchpoint`/`throw`.

These are Hofstadter's BlooP restrictions (*Gödel, Escher, Bach*, ch. XIII).
Every such program terminates, and the compiler prints a certificate saying
so. Everything else is FlooP: the compiler will run it, but promises nothing.

## Calling convention

Arguments are pushed left to right; `CALL`; the callee does
`PUSH FP; LEA FP,0(SP); LEA SP,-n(SP)`. Argument *i* of *n* is at
`FP + 2 + (n − i)` and locals are at `FP − 1, FP − 2, …`. The result comes
back in R1, and `RET n` pops the arguments.
