# The Duwamish Computer — Principles of Operation

*Report of the consulting committee to Universal Entropics, Seattle, 1967.*

> **A note on authorship.** The committee is imaginary. The design is
> written in the voice of a 1967 consultancy, and the ideas credited to
> each member are ones they really held (in print). But none of them
> wrote this document or designed this machine. Where the text says
> "Knuth argued", read "Knuth's published view is". Everything in this
> repository was built in 2026 as a demonstrator.

The committee: **Donald E. Knuth** (number systems, software), **I. J. Good**
(statistics, and the machine's purpose), **W. Ross Ashby** and **Stafford Beer**
(regulation and self-observation), **Gordon Pask** (the learning,
self-organising machine), **Seymour Cray** (the hardwired model),
**Frank Rosenblatt** (adaptive elements), **Theodore Nelson** (the operator's
view of the system).

---

## 1. Why ternary

Setun, built at Moscow State University in 1958, showed that a practical
computer could be ternary. We chose the same radix for three reasons.

* **Economy.** If the cost of a digit is proportional to its radix, the
  cheapest radix is *e*. Three is the closest integer.
* **Balance.** In *balanced* ternary the trits are −1, 0, +1 (written
  `T`, `0`, `1`). Negation is tritwise inversion, so there is no sign bit
  and no separate negative-zero. Truncation *is* rounding to nearest, so
  shifting never introduces bias. Knuth called it "perhaps the prettiest
  number system of all".
* **Trichotomy.** Every comparison has three outcomes. A binary machine
  must spend two flag bits and a pair of branches to say what one trit
  says. Throughout the design the condition code is a single trit, *C*.

The same trit gives three-valued logic, which Good and Pask both wanted. It
has *true* (+1), *unknown* (0) and *false* (−1). The tritwise minimum and
maximum are Kleene's strong *and* and *or*, and negation is *not*.

## 2. Words and notation

A word is **27 trits**. It holds every integer in ±3,812,798,742,493
(= ±(3²⁷−1)/2). We write words in balanced ternary (`1T0`), in decimal, or
in **heptavintimal**. Heptavintimal is balanced base 27, one letter per three
trits and nine letters per word: `0`, `A`…`M` = 1…13, `N`…`Z` = −13…−1.
Listings print heptavintimal.

## 3. Core memory

Core holds 3¹² = **531,441 words**, addressed *symmetrically* from −265,720
to +265,720. Address zero is in the middle. The negative half belongs to the
Executive and is **protected**: a user-mode program that reads, writes or
jumps below zero takes a protection trap. User programs are loaded at +100
and the user stack grows down from the top of core.

A core cycle is 1 µs, and one micro-cycle is 200 ns.

## 4. Registers and instruction format

Nine registers, **R0–R8**, are named by a 2-trit field (−4…+4, taken mod 9).
As on Cray's CDC 6600, R0 always reads as zero. By convention R7 is the
frame pointer `FP` and R8 the stack pointer `SP`.

```
 | op : 5 | r : 2 | x : 2 | m : 2 | addr : 16 |      27 trits
```

* **op**: 243 opcodes, −121…+121. The 46 factory opcodes are all positive.
  *The negative half of opcode space is deliberately left empty. It is for
  instructions the machine invents for itself (§8).*
* **r**: the register operand. **x**: the index register.
* **m**: addressing mode, one trit. −1 is indirect, 0 direct, +1 immediate.
* **addr**: a 16-trit signed address or immediate (±21,523,360).

The effective address is `EA = addr + X`. The operand is EA itself
(immediate), `M[EA]` (direct) or `M[M[EA]]` (indirect). A register can be
used as an operand with `#0(Rn)`.

### Instruction set

(Generated from `duwamish/isa.py`.)

| op | mnemonic | form | action |
|---:|---|---|---|
| 1 | `LD` | RE | R <- operand; C <- sign |
| 2 | `ST` | RE | M[EA] <- R |
| 3 | `LEA` | RE | R <- EA |
| 4 | `ADD` | RE | R <- R + operand; C <- sign |
| 5 | `SUB` | RE | R <- R - operand; C <- sign |
| 6 | `MUL` | RE | R <- R * operand (microcoded trit loop); C <- sign |
| 7 | `DIV` | RE | R <- R / operand, truncated; C <- sign |
| 8 | `MOD` | RE | R <- R rem operand; C <- sign |
| 9 | `NEG` | RE | R <- -operand; C <- sign |
| 10 | `CMP` | RE | C <- sign(R - operand) |
| 11 | `TST` | E | C <- sign(operand) |
| 12 | `AND` | RE | R <- tritwise min (Kleene and); C <- sign |
| 13 | `OR` | RE | R <- tritwise max (Kleene or); C <- sign |
| 14 | `EQV` | RE | R <- tritwise product (Kleene equivalence); C <- sign |
| 15 | `SHF` | RE | R <- R * 3^operand (negative: shift right, rounding) |
| 16 | `XTR` | RE | R <- trits [p, p+n) of R, operand = 27n + p |
| 17 | `TRT` | RE | C <- trit of R at position operand |
| 18 | `SEL` | RE | R <- trit (C+1) of operand: a 3-entry truth table |
| 19 | `NOP` | N | no operation |
| 20 | `JMP` | E | PC <- EA |
| 21 | `JN` | E | if C = -1: PC <- EA |
| 22 | `JZ` | E | if C = 0: PC <- EA |
| 23 | `JP` | E | if C = +1: PC <- EA |
| 24 | `JNN` | E | if C != -1: PC <- EA |
| 25 | `JNZ` | E | if C != 0: PC <- EA |
| 26 | `JNP` | E | if C != +1: PC <- EA |
| 27 | `J3` | E | PC <- EA + C   (three-way jump) |
| 28 | `CALL` | E | push PC; PC <- EA |
| 29 | `RET` | I | pop PC; SP <- SP + addr (discard arguments) |
| 30 | `PUSH` | R | SP <- SP - 1; M[SP] <- R |
| 31 | `POP` | R | R <- M[SP]; SP <- SP + 1; C <- sign |
| 32 | `JSR` | RE | R <- PC; PC <- EA |
| 33 | `SVC` | I | supervisor call (trap 6) |
| 34 | `RTI` | N | return from trap (privileged) |
| 35 | `IN` | RE | R <- input from device operand (privileged); C <- sign |
| 36 | `OUT` | RE | output R to device operand (privileged) |
| 37 | `HLT` | N | halt the machine (privileged) |
| 38 | `TIM` | R | R <- machine clock, in micro-cycles |
| 39 | `TAL` | RA | R <- tally (execution count) of the word at EA |
| 40 | `TCL` | N | clear all tallies |
| 41 | `RCS` | RA | R <- control-store half-word EA |
| 42 | `WCS` | RA | control-store half-word EA <- R |
| 43 | `RKS` | RA | R <- constant store K[EA] |
| 44 | `WKS` | RA | constant store K[EA] <- R |
| 45 | `RMAP` | RA | R <- dispatch map entry for opcode EA |
| 46 | `WMAP` | RA | dispatch map entry for opcode EA <- R |
| 47 | `FAD` | RE | R <- R + operand, floating; C <- sign |
| 48 | `FSB` | RE | R <- R - operand, floating; C <- sign |
| 49 | `FMP` | RE | R <- R * operand, floating; C <- sign |
| 50 | `FDV` | RE | R <- R / operand, floating; C <- sign |
| 51 | `FLT` | RE | R <- the integer operand as a float; C <- sign |
| 52 | `FIX` | RE | R <- the float operand rounded to an integer; C <- sign |
| 53 | `FCM` | RE | C <- sign(R - operand), floating |

Opcodes 47–53 belong to the floating-point feature (§7).

Two instructions exist *because* the machine is ternary.

* **`J3 L`** jumps to `L−1`, `L` or `L+1` as C is −, 0 or +. A three-way
  branch costs one instruction, which is FORTRAN's arithmetic IF in hardware.
* **`SEL R, #t`** loads trit number C+1 of the constant *t*. The three trits
  of *t* form a truth table indexed by the outcome of the last comparison.
  After `CMP`, `SEL R1,#-11` yields *true* iff "less than", `#-7` iff
  "equal", `#5` iff "greater", and so on. Every relational operator is one
  CMP and one SEL, with no branches.

## 5. Traps and the Executive

A trap stores the resume PC, trap code, previous mode, condition trit,
argument and faulting address at fixed protected locations −1…−7. It then
enters supervisor mode at the address held in −5. Codes: 1 illegal
instruction, 2 protection, 3 divide by zero, 4 address out of core,
5 privileged instruction, 6 supervisor call, 8 control store locked, 10 time
limit, 11 floating-point feature not installed. A trap *in supervisor mode* is a machine check and halts the machine.

The **Executive** (`duwamish/executive.tri`, about 150 words of TRIAD) lives
at −60000. It:

1. asks the satellite for the next job step over channel 5;
2. starts the step in user mode with a clean register file and an
   interval-timer limit;
3. services supervisor calls (0 exit, 1 print a character, 2 read a
   character from the card reader, 3 console typewriter, 4 configuration:
   +1 if the floating-point unit is fitted, −1 if not);
4. on EXIT or on a program check, prints a diagnostic, reports the outcome
   and the cycles used to the satellite, and loops.

## 6. Job control: the satellite

Following IBM's 7094/7044 Direct-Coupled System, a small **satellite**
computer stands between the operators and the Duwamish. It reads card
decks, runs the translators, spools the printer and feeds job steps to the
Executive (`duwamish/satellite.py`):

```
//JOB  name  TIME=cycles
//SALISH [FROM=file] [LIST]      compile the cards that follow (or a file)
//TRIAD  [FROM=file] [LIST]      assemble
//EXEC   [TRILISP]               run what was just translated, or a catalogued program
//DATA   [FROM=file]             cards for the program's card reader
//END
```

The translators run on the satellite. This is how the period built new
machines: cross-translators ran on an established computer. TRILISP's reader
and evaluator, however, run on the Duwamish itself.

## 7. Microprogramming: two models, one architecture

Following System/360, the architecture is realised twice.

* **Model 30** is **microprogrammed** (Pask, Beer, Knuth). Every instruction
  is interpreted by a microprogram in a 2,187-word **writable control
  store**. Timing is exact: one 200 ns cycle per microinstruction, plus four
  cycles of wait for each core reference.
* **Model 90** is **hardwired** (Cray). It executes the factory instructions
  directly. Any opcode whose microcode has been rewritten, or invented,
  drops into the micro-engine for that one instruction. The two models
  therefore compute identical results. A test runs 250 random programs,
  including faulting ones, on both and compares every register, flag and
  word of the data area.

### The microword

Microinstructions are *horizontal*: 54 trits in two halves.

```
half A (datapath)   a:3 b:3 alu:3 d:3 mem:1 setc:1 pcinc:1 lit:6
half B (sequencing) seq:3 sel:2 special:3 target:10
```

In one cycle a microinstruction may make one ALU transfer, one core
reference, one PC increment, one special action (I/O, trap, control-store
access…) and one sequencing order. The sequencer is ternary too.
**`CASE sel L`** goes to L−1, L or L+1 on a trit: the condition trit, the
sign of the ALU result, or the instruction's **addressing mode**. Operand
fetch is therefore a single three-way micro-branch:

```
OPND:   EA<-ADDR+X, CASE M OPND0
        MAR<-EA, READ, GOTO OPNDI       ; -1: indirect
OPND0:  MAR<-EA, READ, RET              ;  0: direct
        MDR<-EA, RET                    ; +1: immediate
```

Multiplication shows the ternary advantage best. Each multiplier trit is
−1, 0 or +1, so each pass subtracts, skips or adds the shifted multiplicand.
No Booth recoding is ever needed, and the loop stops as soon as the rest of
the multiplier is zero:

```
MUL:    CALL OPND
        U<-MDR
        T<-0
        CNT<-R, SETC, CASE C MULGO
        NUL<-LST CNT, SETC, CASE C MULADD       ; C=-1: more to do
MULGO:  R<-T, SETC, ENDI                        ; C= 0: finished
        NUL<-LST CNT, SETC, CASE C MULADD       ; C=+1: more to do
        T<-T-U                                  ; trit -1: subtract
MULADD: CNT<-SHR CNT, SETC, GOTO MULSH2         ; trit  0: skip
        T<-T+U                                  ; trit +1: add
        CNT<-SHR CNT, SETC
MULSH2: U<-SHL U, CASE C MULGO
```

`DISP L` dispatches on the opcode and records L as the *continuation*;
`ENDI` ends an instruction by jumping to it. Normally the continuation is
FETCH. That one indirection is what lets the machine chain instructions
together without fetching them (§8). The full microprogram is
`duwamish/microcode/model30.dmc` (156 words); list it with
`python -m duwamish micro`.

### The floating-point unit

Floating point is a **feature**, as it was on the System/360 and the
PDP-6. It is standard on the Model 90 and can be ordered for the Model 30
(`--fpu`). The unit is `duwamish/fpu.py`, and both models share it.

A float fills one word, and its fields are balanced:

```
| exponent : 5 trits | mantissa : 22 trits |      value = m × 3^(e − 21)
```

The fields need no sign bit, no bias and no complement. The exponent
runs from −121 to +121, which is about 10^±57. A normalised mantissa has
a non-zero leading trit, so 3²¹/2 < |m| ≤ 3²²/2. That is 22 trits, about
34.9 bits of precision (the 7600 carries 48). The word is a sum,
e·3²² + m, so **the sign of a float is the sign of its mantissa, not of
the word**. A small negative mantissa under a positive exponent makes a
positive word. The unit therefore sets C from the mantissa, and `FCM`
compares values, not words.

Every operation forms the exact result and rounds it once, to nearest.
In balanced ternary, rounding to nearest is simply dropping trits, and it
has no ties and no bias. An exponent above 121 saturates to the largest
magnitude. One below −121 gives zero. Dividing by zero takes trap 3.

| order | time in the unit |
|---|---|
| `FAD`, `FSB` | 3 cycles (0.6 µs) |
| `FMP` | 5 cycles (1.0 µs) |
| `FDV` | 15 cycles (3.0 µs) |
| `FLT`, `FIX`, `FCM` | 2 cycles (0.4 µs) |

On the Model 90 these times are added to the 1 µs instruction. On the
Model 30 the microcode fetches the operand as usual. One micro-order,
`FPU`, then hands R and MDR to the unit, whose time is added to the
clock. Without the feature, that micro-order takes program check 11. A
program can ask the Executive whether the unit is there (`SVC 4`, or
`hasfpu()` in SALISH) and fall back on the software library `tfloat`,
which uses the same format. The library rounds once, as the unit does,
and agrees with it to the trit; a test checks this on thousands of
operand pairs, including near-cancellations, overflow and underflow.

## 8. The writable control store, and the machine's own inventions

With the front-panel key at **WCS ENABLE**, six instructions let a program
read and write the control store (`RCS`/`WCS`), the 243-word fast constant
store (`RKS`/`WKS`) and the dispatch map (`RMAP`/`WMAP`). A program can
then:

1. copy a run of its own instructions into the constant store;
2. write microcode that loads each of them into IR and dispatches on it,
   chaining through the continuation, *with no core cycle to fetch them*;
3. point an unused negative opcode at that microcode;
4. overwrite the first word of the run with the new opcode.

The original words stay where they were, so a jump into the middle of the
run still works. This was Good's condition for the "ultraintelligent
machine": the machine can improve the machine. The demonstration is
`programs/good/explosion.sal`; see [DEMONSTRATOR.md](DEMONSTRATOR.md).

## 9. The Beer monitor

Beer held that a viable system must observe itself. Every instruction fetch
increments a **tally** for that word of core. `TAL R, a` reads the tally
for address *a* and `TCL` clears them all, so programs can profile
themselves. From the host, `duwamish/profile.py` attributes the tallies to
SALISH procedures. `TIM R` reads the cycle clock.

## 10. Software

| layer | what | where |
|---|---|---|
| microcode | the Model 30 microprogram | `duwamish/microcode/model30.dmc` |
| TRIAD | symbolic assembler, literal pools, listings | `duwamish/triad.py` |
| Executive | resident monitor | `duwamish/executive.tri` |
| SALISH | BCPL-like systems language, three-valued logic, BlooP certification | [SALISH.md](SALISH.md) |
| TRILISP | LISP 1.5-style interpreter written in SALISH, ternary-tagged | [TRILISP.md](TRILISP.md) |

## 11. Speed

The simulator runs the Model 90 at about 1.2 million instructions a
second, and the Model 30 at about 3 million micro-cycles a second. A typical
SALISH instruction costs 12–15 micro-cycles on the Model 30 (2.5–3 µs of
1967 time). A TRILISP evaluation costs 300–400 instructions.

## 12. Against the CDC 7600

How does the Duwamish compare with the fastest production computer of the
early 1970s, Seymour Cray's CDC 7600 (1969)? The Duwamish figures below are
**measured** on the simulator's cycle-exact Model 30. The Model 90's timing
is nominal (one instruction per 1 µs core cycle). They are design
parameters of an imaginary machine, not an engineered circuit; a real 1967
ternary machine would very likely have been slower. The 7600 figures are
commonly published values from memory, not checked against sources here.

### The machines

| | Duwamish Model 30 | Duwamish Model 90 | CDC 7600 |
|---|---|---|---|
| Cycle | 200 ns micro-cycle (5 MHz) | 1 µs per instruction (nominal) | 27.5 ns (36.4 MHz) |
| Organisation | microprogrammed, one micro-step at a time | hardwired, one instruction at a time | pipelined independent functional units, instruction buffer |
| Register add | 10 cycles = 2.0 µs | 1 µs | about 2 clocks, overlapped |
| Add from core | 14 cycles = 2.8 µs | 1 µs | overlapped |
| Full-width multiply | 102 cycles = 20.4 µs (microcoded, one trit per pass) | 1 µs | floating multiply in about 5 clocks, one started per clock |
| Typical instruction rate | about 0.4 MIPS (`hello.sal`: 47,329 instructions in 604,075 cycles) | about 1 MIPS | up to one instruction per clock |
| Floating point | optional feature; otherwise software (below) | standard: FAD 1.6 µs, FMP 2 µs, FDV 4 µs | 60-bit hardware, 48-bit mantissa; about 36 MFLOPS peak |
| Word | 27 trits, about 42.8 bits of information | same | 60 bits |
| Main memory | 531,441 words, about 22.7 Mbit | same | 65K words of small core plus 512K words of large core, about 34.4 Mbit |

### The Livermore loops

`programs/livermore.sal` runs six of McMahon's Livermore Fortran Kernels
(1, 3, 5, 7, 11 and 12, with n = 100). These are the loops by which the
7600 and its successors were judged. The Duwamish runs each kernel three
ways:

* **Fixed point**, with numbers scaled by 3¹². A product is rescaled by
  one ternary shift, which rounds correctly. This is what a programmer of
  an integer machine would really do.
* **Software floating point** (`duwamish/lib/tfloat.sal`), in the unit's
  format. The XTR instruction unpacks the fields. Products are formed
  from 11-trit halves so no partial product overflows, and sums carry
  four guard trits, so each operation rounds exactly once.
* **Hardware floating point**, with the unit (§7). This column is skipped
  on a machine without the feature. The program asks the Executive with
  `hasfpu()`.

Each loop is timed by the machine's own clock. The answers are checked
against double precision (`tools/livermore_reference.py`). Both float
columns agree with it to one unit in 3⁻¹², and with each other exactly.
Fixed point agrees to within about ten units.

| kernel | flops | M30 fixed | M30 soft float | M30 + FPU | M90 fixed | M90 soft float | M90 FPU |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 hydro fragment | 500 | 0.0363 | 0.0024 | 0.0509 | 0.1160 | 0.0065 | 0.1241 |
| 3 inner product | 200 | 0.0287 | 0.0026 | 0.0367 | 0.0865 | 0.0070 | 0.0921 |
| 5 tri-diagonal elimination | 198 | 0.0227 | 0.0023 | 0.0234 | 0.0664 | 0.0061 | 0.0593 |
| 7 equation of state | 1,600 | 0.0485 | 0.0027 | 0.0630 | 0.1582 | 0.0072 | 0.1511 |
| 11 first sum | 99 | 0.0173 | 0.0028 | 0.0157 | 0.0452 | 0.0073 | 0.0405 |
| 12 first difference | 100 | 0.0173 | 0.0019 | 0.0157 | 0.0452 | 0.0050 | 0.0405 |
| **harmonic mean** | | **0.0247** | **0.0024** | **0.0257** | **0.0699** | **0.0064** | **0.0653** |

(MFLOPS; for fixed point, arithmetic operations per microsecond counted as
the kernel's floating-point operations. Run `python -m duwamish run
jobs/livermore.job --model 90`, or `--model 30 --fpu`.)

### What the numbers say

* **Against the 7600's peak of 36 MFLOPS**, the Model 90 with its unit is
  about 550 times slower. Without the unit, the Model 30 is about 1,500
  times slower in fixed point and about 15,000 times slower in software
  floating point. Sustained 7600 performance on real codes was typically
  quoted at a fraction of its peak, perhaps 10 MFLOPS, which divides
  these ratios by three or four.
* **What the unit bought.** Floating point became about ten times faster
  than the software library (0.0653 against 0.0064 on the Model 90), and
  exact to the same trit. It became *as cheap as fixed point*, but no
  cheaper. An earlier version of this section predicted that a unit
  "would gain a factor of a hundred or more". Measurement shows ten,
  because arithmetic was never the bottleneck. On the Model 30 the unit
  also relieves the trit-serial multiply, so there it is slightly faster
  than fixed point.
* **Where the time goes now.** Here is the inner loop of kernel 3,
  `s := fadd(s, fmul(fz[k], fy[k]))`, as SALISH compiles it:

  ```
  L104: LD R1,-5(FP)   CMP R1,-6(FP)  JP L106        ; loop test
        LD R1,-5(FP)   ADD R1,G_fz    LD R1,0(R1)    PUSH R1   ; fz[k]
        LD R1,-5(FP)   ADD R1,G_fy    LD R1,0(R1)    PUSH R1   ; fy[k]
        POP R2         POP R1
        FMP R1,#0(R2)  FAD R1,-2(FP)  ST R1,-2(FP)   ; the arithmetic
        LD R1,-5(FP)   ADD R1,#1      ST R1,-5(FP)   JMP L104  ; k := k+1
  ```

  That is 20 instructions per pass, and two of them are floating point.
  At 1 µs an instruction, the loop runs at about a tenth of what the unit
  could do. The remaining gap is instruction issue: fetching and
  decoding one instruction at a time from core, with index arithmetic
  in memory, not registers. The 7600 attacked exactly this. It held the
  loop in an instruction buffer, kept operands in registers, and
  overlapped everything.
* **Why.** The 7600 was built for exactly these loops: independent
  pipelined functional units, and an instruction buffer that held a whole
  inner loop so it ran without fetching instructions from memory. The
  Duwamish was built for other things: symbolic computation (TRILISP),
  statistics in integers (decibans), games, and a writable control store
  that lets programs invent their own instructions. The explosion
  demonstration's fused instructions are a small version of the 7600's
  instruction buffer. They save fetches, but not the arithmetic.
* **What would close the gap next.** An optimising compiler would help:
  keeping `k` in a register, strength-reducing the subscripts and
  dropping the PUSH/POP pairs would take the loop from 20 instructions to
  about 7. That alone is worth more than the floating-point unit was.
  After that would come overlapping fetch with execution, as the IBM
  360/91 and the 7600 did. None of these touches what the machine is
  for, which is the point of the committee's choices.
