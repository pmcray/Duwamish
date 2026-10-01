# TRI-TRAN — the Duwamish FORTRAN

SALISH was written for systems programming. The laboratories expected to
buy the machine would arrive with their programs in FORTRAN, so the
committee's report gave the Duwamish a FORTRAN too. **TRI-TRAN** is a
dialect of the 1966 standard (USA Standard FORTRAN, X3.9-1966). Its
compiler (`duwamish/tritran.py`) runs on the satellite, as SALISH's does,
and produces TRIAD assembly. The run-time library (`duwamish/lib/tritran.sal`)
is written in SALISH and compiled by SALISH/O.

```
python -m duwamish go --model 90 program.ftn     # compile and run
python -m duwamish compile program.ftn           # show the TRIAD code
python -m duwamish run --model 90 jobs/tritran.job
```

```
//JOB  MYJOB
//TRITRAN [FROM=file] [LIST]     compile the cards that follow (or a file)
//EXEC
//DATA                           cards for READ
```

TRI-TRAN needs the floating-point unit, as FORTRAN needed the 704's: it is
standard on the Model 90, and `--fpu` fits it to a Model 30. Without the
unit, the satellite warns at compile time, and the first REAL operation
stops the job with program check 11.

## What is FORTRAN about it

This is a FORTRAN of 1966, and it has that FORTRAN's habits. None of these
is a mistake:

* **Cards.** A `C` or `*` in column 1 makes a comment. Columns 1–5 hold
  the statement number. Any character but blank or `0` in column 6 marks
  a continuation card. The statement is in columns 7–72, and columns
  73–80 are ignored: a statement that runs past column 72 loses its end
  without a word.
* **Blanks mean nothing** outside Hollerith and quoted text. `DO 10 I =
  1,10` begins a loop. `DO 10 I = 1.10` assigns 1.1 to the variable
  `DO10I`.
* **Implicit types.** Names beginning I–N are INTEGER, the rest REAL,
  unless declared. Names have at most six characters.
* **Static storage.** Every variable has a fixed place in core, and keeps
  its value between calls. Subprograms cannot be recursive.
* **Arguments by reference.** A subprogram receives addresses. Pass it the
  constant `1` and let it assign to its argument, and later uses of that
  literal `1` may see the new value. (A test in `tests/test_tritran.py`
  shows this.)
* **DO loops run at least once**, testing at the bottom, as the 1966
  standard's loops did in practice.
* **Numeric input fields treat blanks as zeros.** Data are punched
  right-justified, so `12` in an I5 field, punched as `12   `, reads as
  12000.
* **FORMAT is counted by hand.** `5HHELLO` is five characters of
  Hollerith text. Apostrophes are also accepted, as IBM's FORTRAN IV
  allowed. Miscounted Hollerith was the commonest error in writing the
  programs of `jobs/tritran.job`.
* **The first character of a printed line is carriage control.** Blank
  starts a new line. `0` skips a line first. `1` starts a new page, a
  blank line on this continuous paper. `+` would overprint; this printer
  cannot, so it starts a new line. Hence the usual `FORMAT (1X, ...)`.

Mixed-mode arithmetic (an INTEGER with a REAL) is allowed, and the INTEGER
is converted. So are FORTRAN 77's `NINT` and apostrophe strings, and IBM's
`END=` on READ.

## What is ternary about it

* **LOGICAL is three-valued.** `.TRUE.`, `.FALSE.` and `.UNKNOWN.` are
  +1, −1 and 0. `.AND.`, `.OR.` and `.EQV.` are Kleene's connectives,
  each a single instruction: AND, OR and EQV (tritwise minimum, maximum
  and product). `.NOT.` is negation. `.NEQV.` is `.NOT.` of `.EQV.`. A relation such as
  `A .LT. B` is one compare and one SEL. **A logical IF obeys its
  statement only when the condition is .TRUE.** Neither `IF (Q)` nor
  `IF (.NOT. Q)` does anything when `Q` is unknown.
* **The arithmetic IF is one instruction.** `IF (E) 10, 20, 30` goes to
  10, 20 or 30 as E is negative, zero or positive. A binary machine
  needs two conditional jumps; the Duwamish uses one J3 into a table of
  three. When E is `A - B`, the subtraction becomes a single CMP (or FCM
  for REAL). A LOGICAL expression may be tested the same way: false,
  unknown, true.
* **Two more FORMAT fields.** `Bw` writes an INTEGER in balanced ternary,
  with `T` for the trit −1. So 42 is `1TTT0` and −42 is `T1110`: no
  sign, and negation exchanges 1 and T. `Lw` writes T, F or U. On input,
  `Bw` reads 1, 0 and T (or −), and `Lw` reads T, F or U.
* **REAL is the unit's word**: a 5-trit exponent and a 22-trit mantissa,
  about ten decimal digits. The library uses the format directly (below).
* `ITRIT(N, K)` is trit K of N (0 is the least significant), and
  `ICLOCK()` is the machine's cycle clock.

## What is FORTRAN I about it: index registers

Backus's team held that FORTRAN would be used only if its object programs
were nearly as good as hand code. FORTRAN I (1957) put DO-loop indices in
the 704's index registers. TRI-TRAN does the same with R3–R6: each DO loop
whose index qualifies gets a register for the duration of the loop. An
index qualifies if it is a local INTEGER that nothing in the loop assigns,
and no statement inside the range is the target of a jump from outside it
(the standard's "extended range").

With the index in R3, the array element `A(K+1)` is the single operand
`A+0(R3)`, and a two-dimensional element with constant later subscripts is
still one operand. The inner product

```
      DO 10 K = 1, 100
   10 S = S + A(K)*B(K)
```

compiles to seven instructions a pass:

```
_MAIN._2:
_MAIN.10:
        LD   R1, _MAIN.A-1(R3)
        FMP  R1, _MAIN.B-1(R3)
        FAD  R1, _MAIN.S
        ST   R1, _MAIN.S
        ADD  R3, #1
        CMP  R3, #100
        JNP  _MAIN._2
        ST   R3, _MAIN.K
```

On leaving a loop, normally or by a GO TO out of it, the register is
stored in the variable, so `K` has its value afterwards. A subprogram
saves the registers it uses and restores them on return.

The listing's header names the assignments: `; main program   index
registers: R3=K`.

That is all the optimisation there is, as in 1957. The sum `S` stays in
core. SALISH/O's allocator, which works by usage counts as FORTRAN H did in
1969, keeps it in a register and saves an instruction a pass. The
difference shows in the Livermore loops below.

## The language

Program units: a main program (optionally headed `PROGRAM name`),
`SUBROUTINE name(args)`, and `[INTEGER|REAL|LOGICAL] FUNCTION name(args)`.
Each unit ends with `END`.

Specification statements come first: `INTEGER`, `REAL`, `LOGICAL` (with
array bounds), `DIMENSION`, `COMMON /name/ list` (and blank COMMON),
`EXTERNAL`, and statement functions such as `F(X) = X*X + 1.0`. `DATA`
may appear anywhere: `DATA A, B /1.0, 2.0/, K /10*0/`. Arrays have up to
three dimensions, stored by columns and subscripted from 1. An argument
array may have adjustable bounds (`DIMENSION A(N)`).

Executable statements: assignment; `GO TO n`; computed `GO TO (n1, n2,
...), I`; arithmetic and logical `IF`; `DO n I = e1, e2 [, e3]`;
`CONTINUE`; `CALL`; `RETURN`; `STOP [n]` (the number is typed on the
operator's console, and becomes the step's completion code); `PAUSE [n]`
(typed, and the operator presses START); `READ`, `WRITE`, `PRINT`, `PUNCH`;
`REWIND`, `BACKSPACE`, `ENDFILE`.

Input and output:

```
      READ (5, 10) list          READ 10, list     card reader
      READ (5, 10, END=99) list                    ... going to 99 at the end
      WRITE (6, 10) list         PRINT 10, list    line printer
      WRITE (7, 10) list         PUNCH 10, list    card punch
```

A list may contain whole arrays and implied DO loops: `(A(I), I = 1, N)`.

Tapes (units 1–4 and 8, mounted with `//TAPE` cards) take unformatted
records, as FORTRAN's binary tape statements did:

```
      WRITE (2) K, A             one record: K, then the whole array A
      READ (2) K, A              one record, taken word by word
      READ (2, END=99) K, A      ... going to 99 at a tape mark
      ENDFILE 2                  write a tape mark
      REWIND 2
      BACKSPACE 2                back over one record
```

The unit may be an INTEGER variable. A record holds up to 6,561 words,
one to each item of every type. Reading more items than the record holds
is a run-time error, and so are writing without a write ring and reading
past a tape mark without `END=`. Formatted input and output are for the
card reader, printer and punch only.

FORMAT fields: `Iw`, `Fw.d`, `Ew.d`, `Lw`, `Bw`, `nX`, `nH...`, `'...'`,
`/`, repeat counts (`3F10.4`), and groups (`2(I3, F8.2)`) nested to two
levels. When the list outlasts the format, a new record begins at the
last top-level group, or at the start. A number too wide for its field
prints as asterisks.

Intrinsic functions: `ABS IABS FLOAT IFIX INT NINT AINT MOD AMOD SIGN
ISIGN DIM IDIM MAX0 MIN0 AMAX1 AMIN1 AMAX0 AMIN0 MAX1 MIN1 SQRT EXP ALOG
ALOG10 SIN COS TANH ATAN ATAN2 ICLOCK ITRIT`. Their argument types are
checked, as FORTRAN's were: `SQRT(2)` is an error, `SQRT(2.0)` is not.
`**` accepts INTEGER and REAL powers.

The compiler sees every unit of the deck at once. So it can report what a
1966 compiler could not: a call to a subprogram that does not exist, the
wrong number of arguments, and an INTEGER FUNCTION used as REAL where the
caller forgot to declare it.

Not included: EQUIVALENCE, BLOCK DATA, ASSIGN, DOUBLE PRECISION, COMPLEX
and ENTRY.

## The library

The library is SALISH, compiled once by SALISH/O and loaded after the
program. TRI-TRAN calls it with SALISH's calling convention, passing
values.

* **FORMAT** is interpreted at run time, from a table the compiler makes
  out of each FORMAT statement, as IBM's IBCOM did. Output fields are
  converted exactly: F and E multiply by an exact power of ten, round
  once with FIX, and print the integer.
* **SQRT** starts from 3^(e/2), which it reads straight from the exponent
  field, and makes seven Newton steps.
* **EXP** writes e^x = 3^k · e^r with k the nearest integer to x/ln 3. The
  reduction is in two parts (Cody and Waite): k·ln3hi is exact because
  ln3hi has only 11 trits. The factor 3^k costs nothing, since k is added
  to the exponent field. What remains, |r| ≤ 0.55, is a Taylor series.
* **ALOG** takes the exponent e off the word: ln x = e·ln 3 + ln f, with f
  between 1/2 and 3/2, and ln f = 2 atanh((f−1)/(f+1)). On a ternary
  machine the natural logarithm's companion is ln 3, not ln 2.
* **SIN** and **COS** reduce by π/2 in two parts, then sum Taylor series.
  **ATAN** halves the angle twice before its series.
* **X\*\*I** works through I's balanced-ternary digits, most significant
  first: cube, then multiply by X for a 1, or by 1/X for a T. (This is
  the ternary cousin of the binary method, Knuth Vol. 2 §4.6.3.) A
  negative power costs one division, made once, where the binary method
  takes a reciprocal at the end.

The functions are good to a few units in the last trit (about 3×10⁻¹⁰):
`tests/test_tritran.py` checks them against Python's.

## Programs

`jobs/tritran.job` runs three:

* **`programs/tritran.ftn`**, a tour. It prints Kleene's truth tables from
  LOGICAL arithmetic, then shows that a logical IF ignores the unknown. It
  sorts numbers from data cards by sign with one J3 each, prints numbers
  and their negations in balanced ternary, and prints a table of
  functions, as every FORTRAN program once did.
* **`programs/livermore.ftn`**, the Livermore kernels in the language they
  were written in (below).
* **`programs/good/pfa.ftn`**, Good's prime-factor algorithm: see
  [DEMONSTRATOR.md](DEMONSTRATOR.md).

### The Livermore loops in TRI-TRAN

`programs/livermore.ftn` runs the same six kernels on the same data as
`programs/livermore.sal`'s hardware column, with the same floating-point
operations in the same order. Its checksums are **identical to the last
trit**; the test suite checks this. What differs is the code, and so the
time (harmonic mean MFLOPS):

| | Model 30 + FPU | Model 90 | Model 90 + look-ahead |
|---|---:|---:|---:|
| plain SALISH | 0.0257 | 0.0653 | 0.075 |
| **TRI-TRAN** | **0.0914** | **0.2153** | **0.2673** |
| SALISH/O | 0.0970 | 0.2163 | 0.3147 |

FORTRAN I's one idea, the index register, takes the language from plain
SALISH's speed to within 1% of the full optimiser on the Model 90. It wins
kernel 1 outright (0.290 against 0.274 MFLOPS), where SALISH/O spends
registers on things that matter less. With the look-ahead unit the gap
opens. An instruction from the stack that touches no core takes one cycle,
and TRI-TRAN's loops still load and store their sums in core on every
pass.
