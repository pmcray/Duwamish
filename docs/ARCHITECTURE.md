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
limit. A trap *in supervisor mode* is a machine check and halts the machine.

The **Executive** (`duwamish/executive.tri`, about 150 words of TRIAD) lives
at −60000. It:

1. asks the satellite for the next job step over channel 5;
2. starts the step in user mode with a clean register file and an
   interval-timer limit;
3. services supervisor calls (0 exit, 1 print a character, 2 read a
   character from the card reader, 3 console typewriter);
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
`duwamish/microcode/model30.dmc` (142 words); list it with
`python -m duwamish micro`.

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
