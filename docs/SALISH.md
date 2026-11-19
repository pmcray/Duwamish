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
| `eqv(a, b)` | tritwise product: Kleene's equivalence (a built-in, one EQV instruction) |
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
| `fadd(a, b)`, `fsub(a, b)`, `fmul(a, b)`, `fdiv(a, b)` | the floating-point unit (one instruction each) |
| `fcmp(a, b)` | −1, 0 or +1 as the float a is less than, equal to or greater than b |
| `float(n)`, `fix(x)` | integer to float, and float to integer, rounded |
| `hasfpu()` | +1 if the floating-point unit is fitted, −1 if not (asks the Executive) |
| `punch(c)` | punch a character on the card punch (10 ends a card); a later `//TRIAD PUNCHED` step assembles the deck |
| `catchpoint(buf)`, `throw(buf, v)` | non-local exit (setjmp/longjmp); `buf` is 3 words |

## The runtime library (always included)

`print(n)`, `printw(n, width)`, `printt(n)` (balanced ternary),
`printtw(n, w)`, `printh(n)` (heptavintimal), `printfix(n, places)`,
`prints(s)`, `printsw(s, w)`, `newline()`, `space()`, `spaces(n)`,
`truthname(v)`, `tritchar(t)`, `abs`, `min`, `max`, `alloc(n)`,
`streq(a, b)`, `readline(buf, max)`. Every routine is written with bounded
loops, so BlooP programs may call them.

The floating-point intrinsics compile to single instructions. On a
Model 30 without the feature they stop the job with program check 11. A
program that must run anywhere tests `hasfpu()` and falls back on the
`tfloat` library, whose numbers are the same words.

Other libraries: `tfloat` (ternary floating point in software, in the
unit's format: a 5-trit exponent and 22-trit mantissa in one word, with
`tf_add`, `tf_sub`, `tf_mul`, `tf_norm`, `tf_from_int`, `tf_from_ratio`,
`tf_to_fixed`; each rounds once and agrees with the unit to the trit),
`devices` (tape, drum and disc through the data channel: `tread(u, buf,
max)`, `twrite(u, buf, n)`, `tmark(u)`, `rewind(u)`, `backspace(u)`,
`treadback(u, buf, max)`, `tskip(u)`, `tpos(u)`, `drumread(addr, buf, n)`,
`drumwrite(addr, buf, n)`, `discread(u, sector, buf, n)`,
`discwrite(u, sector, buf, n)`, each returning a word count or an `IO_`
status; see ARCHITECTURE.md §6), `disasm` (read and disassemble machine
code), `isakit`
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

In optimised code R3–R6 hold register variables. They are **callee
saved**: a procedure that uses them stores them in its frame on entry and
reloads them before `RET`. R1 and R2 remain scratch registers.

## The optimising compiler, SALISH/O

`//SALISH OPT` on the control card, `--opt` on the command line, or
`optimise=True` from Python compiles with SALISH/O
(`duwamish/optimise.py`). It works in the manner of FORTRAN I's index
registers, the usage counts of FORTRAN H (Lowry and Medlock, 1969), and
Allen and Cocke's program-optimisation work at IBM. The same program
computes the same answers either way. A test runs hundreds of random
programs, and the demonstrations, both ways and compares what they print.

* **Register allocation by usage counts.** Before generating a procedure,
  the compiler counts every use of each local, parameter and loop control.
  A use inside *k* loops counts 10ᵏ. The heaviest candidates get R3–R6,
  and two variables whose scopes do not overlap may share a register. A
  variable must earn about one use inside a loop, or it stays in core.
  Straight-line procedures therefore pay nothing for saving registers.
  The listing names each assignment: `; proc main()   registers: R3=k,
  R4=s`.
* **Index-register addressing.** A global vector that the program never
  reassigns, and whose address it never takes, stays at the address the
  loader gave it. So `v[k + 3]`, with `k` in a register, is the single
  operand `V_v+3(R3)`, as FORTRAN addressed its arrays.
* **Updates in place.** `x := x + e`, `x +:= e`, `x := fadd(x, e)` and
  similar, with `x` in a register, become one instruction on that
  register. Compares and tests take register and memory operands
  directly.
* **Loop rotation.** A counted loop tests once on entry and then at the
  bottom of each pass. A pass therefore costs one conditional jump and no
  unconditional one.
* **A peephole pass** over the generated TRIAD: jumps to jumps are
  threaded, jumps to the next instruction and unreachable code are
  removed, and a load of a word just stored is dropped. A test of a value
  just computed is dropped, and a stack temporary becomes a register move
  when nothing in between needs R2. `python -m duwamish compile --opt`
  prints how many of each it made.

Two built-ins cooperate with the register allocator:

* `stackptr()` first stores R3–R6 in the procedure's frame. TRILISP's
  conservative collector scans the stack for roots, so everything live
  must be on the stack when it looks.
* A procedure that calls `catchpoint` saves all four registers on entry.
  It restores them where a `throw` lands, because the throw arrives
  carrying its thrower's registers.

What it buys, in the Livermore inner product
`s := fadd(s, fmul(fz[k], fy[k]))`:

```
plain SALISH, 20 instructions a pass       SALISH/O, 6 instructions a pass
L104: LD R1,-5(FP)  CMP R1,-6(FP)  JP L106  L104: LD   R1, V_fz+0(R3)
      LD R1,-5(FP)  ADD R1,G_fz  LD R1,0(R1)      FMP  R1, V_fy+0(R3)
      PUSH R1  LD R1,-5(FP)  ADD R1,G_fy           FAD  R4, #0(R1)
      LD R1,0(R1)  PUSH R1  POP R2  POP R1         ADD  R3, #1
      FMP R1,#0(R2)  FAD R1,-2(FP)  ST R1,-2(FP)   CMP  R3, #99
      LD R1,-5(FP)  ADD R1,#1  ST R1,-5(FP)        JNP  L104
      JMP L104
```

See [ARCHITECTURE.md §12](ARCHITECTURE.md) for what that does to the
benchmark.

## SALISH/S: the compiler written in SALISH

`programs/selfhost/salish.sal` is a SALISH compiler written in SALISH.
It runs on the Duwamish, reads a program from the card reader, and
punches TRIAD code on the card punch. Its output is the same, card for
card, as the satellite's compiler. If the first card is `-- OPT`, it is the
same as SALISH/O's. It follows those compilers part for part:

* a tokenizer that reads the cards as they come, with three characters of
  lookahead;
* a recursive-descent parser that builds the tree in the heap;
* a pass over the declarations;
* a plain code generator that punches as it goes. It counts each
  procedure's frame first, so that no card has to be held back.
* the optimiser:
  * the register plan by usage counts, and the search for vectors at
    fixed addresses;
  * the optimising code generator;
  * the peephole pass. It holds one procedure's lines at a time, since
    none of its rules reaches across a procedure.

The cards are the program followed by `duwamish/lib/runtime.sal`, which
the satellite's compiler includes by itself. It accepts all of SALISH
except `get` (the modules come on the cards instead) and `inline`
procedures. BlooP programs compile, but are not certified.

```
//JOB SELF
//SALISH FROM=programs/selfhost/salish.sal
//EXEC
//DATA FROM=myprogram.sal
//DATA FROM=duwamish/lib/runtime.sal
//TRIAD PUNCHED
//EXEC
```

Put a card reading `-- OPT` before the program to have it optimise.

`jobs/bootstrap.job` has it compile itself. The deck it punches is
identical to the satellite's own compilation, so the next generation is
the same program. `jobs/improve.job` has the plain compiler compile an
optimised copy of itself. That copy is 16% faster, punches exactly the
same cards, and so rebuilds itself unchanged: see
[DEMONSTRATOR.md](DEMONSTRATOR.md).
