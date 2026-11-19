# The Duwamish: project review

*As of 19 November 2026. A self-review, written with Claude Code; the working copy is a shared document, and this file is a snapshot of it.*

## Summary

The Duwamish is a complete, working simulation of a balanced-ternary computer, designed as though in 1967. More than 40 programs run on it, and each demonstrates an idea of I. J. Good, Douglas Hofstadter or another member of the fictional design committee. Most of it was built in four days (29 September to 2 October 2026), and the Byurakan demonstration followed on 12 November. It is about 34,600 lines: 10,700 of Python, 3,600 of system code for the machine, 13,800 of programs, 3,100 of tests and 3,400 of documentation. All 153 tests pass.

My overall verdict: as a demonstrator, it is strong. Every claim a demonstration makes is computed on the simulated machine, and usually checked there too. Each demonstration says plainly what it does *not* show. The weaknesses are of scope and polish, not of correctness. Its relation to the novels is still undecided, and the timeline has stretched from 1967 into the early 1970s. A first-time visitor also has no single guided path through it.

- **What exists:**
  - the machine, in two models;
  - an operating system (the Executive) and job control;
  - tape, drum, disc and Atlas-style paging;
  - seven languages: TRIAD, SALISH, SALISH/S, TRILISP, TRI-TRAN, WHALE and Refal;
  - a Jupyter notebook with 21 sections and animated front panels;
  - ten documents in `docs/` (this review among them) plus the README.
- **Where it is:** branch `claude/focused-tesla-k23wgv` of `pmcray/duwamish`, proposed for merge into `main` by pull request.

## Motivation

The project's purpose is to show Good's and Hofstadter's ideas *working*, on a machine that could plausibly have existed in their time, rather than to describe them. The README puts it in one line: "a balanced-ternary computer, designed as if in 1967, built as a demonstrator of the ideas of I. J. Good and Douglas Hofstadter."

Three aims run through it:

- **Good's principles made computable.** These are the weight of evidence in decibans, the Good–Turing estimate of the unseen, randomised experiment as a way to learn, and the "ultraintelligent machine" that improves itself. Each appears as a program whose numbers can be checked: Banburismus, Colossus, go, backgammon, the five-year-plan chess, the perceptron and WHALE's clinic.
- **Hofstadter's principles made literal.** These are self-reference, quining, levels of description, BlooP against FlooP, strange loops and analogy as perception. The machine is built so that each level can reach the one beneath it. Software can rewrite its own microcode, a compiler compiles itself to a fixed point, and an interpreter is specialised into a compiler.
- **A setting for the fiction.** Universal Entropics, its Special Systems Section in Seattle and the imagined 1967 committee give the machine a history. Some names and threads belong to *The Visibilities* and *The Lamps are Going Out*, among them Woodworth (in WHALE's name), Akademgorodok and the Soviet line from Setun to Refal. The repository says plainly that the committee is imaginary and that all of it was built in 2026.

A fourth aim came in through the work: to be honest about limits. Each demonstration in `docs/DEMONSTRATOR.md` ends with "What it does not show". Several of the most interesting results are negative ones, such as the intelligence explosion that reaches a fixed point, or the measurement that showed the floating-point unit's gain as ten times, not a hundred.

## Timelines

The fiction is set in 1967, but the software now reaches from 1944 (Colossus) to the early 1970s (STRIPS, Prolog, Futamura, Byurakan). Several sources it draws on came later still (Copycat 1988, Refal-5 1989, Jones, Gomard and Sestoft 1993). The second table shows the build itself: four days of work, and a fifth six weeks later.

### The period the machine draws on

These are years of first publication or first running. They are from memory and have not been checked against sources here.

| year | what | on the Duwamish |
| --- | --- | --- |
| 1944 | Colossus breaks Tunny at Bletchley | `colossus.sal` |
| 1948 | Ashby's homeostat | `homeostat.sal` |
| 1956 | Los Alamos chess on MANIAC I; Pask's SAKI | `chess.sal`, `saki.sal` |
| 1958 | Setun, the Moscow ternary computer; Rosenblatt's perceptron | the radix; `perceptron.sal` |
| 1959 | Samuel's draughts; GPS | `draughts.sal`, `gps.lsp` |
| 1962 | Atlas's one-level store | `//STORE`, `pager.sal` |
| 1965 | Good, *Speculations Concerning the First Ultraintelligent Machine*; Sholomitskii's variable CTA-102, taken for a beacon | `explosion.sal`; `listen.sal` |
| 1966 | ELIZA; Turchin's Refal; FORTRAN 66 | `eliza.lsp`, Refal, TRI-TRAN |
| **1967** | **The fictional committee reports**; Bell and Hewish's pulsar, "LGM-1" | the architecture; `listen.sal` |
| 1968 | Good's "Five-Year Plan for Automatic Chess"; Lindenmayer's rewriting systems | `fiveyear.sal`; `receive.ref` |
| 1969 | CDC 7600 | the comparison in ARCHITECTURE §12 |
| 1970–72 | SHRDLU, STRIPS, Prolog; Futamura (1971); the Byurakan CETI conference (1971) | `shrdlu.lsp`, `strips.lsp`, `prolog.lsp`, `mix.ref`; the `byurakan` job |
| 1973 | Sagan (ed.), *Communication with Extraterrestrial Intelligence*, the Byurakan proceedings | cited in DEMONSTRATOR §33 |
| 1979 | *Gödel, Escher, Bach*, chapter VI: frame, outer and inner messages | the Hofstadter demonstrations; `receive.ref` |
| 1988–95 | Copycat | `copycat.sal` |

### How the project was built

| date | work |
| --- | --- |
| 12 Nov 2026 | Byurakan 1971: weighing signals in decibans; a Refal receiver that builds the machine a message describes; Refal's `$END` card |
| 2 Oct 2026 | Refal; mixed computation and Futamura's first projection |
| 1 Oct 2026 | WHALE; SAKI; notebook views for both; tape, drum and disc; polyphase sort; Colossus; Atlas paging |
| 30 Sep 2026 | SALISH/O; self-hosting compiler; Copycat; five-year plan; look-ahead unit; TRI-TRAN and Good's FFT; perceptron; homeostat; Knuth's algorithms; Kleene Life; five AI programs in TRILISP |
| 29 Sep 2026 | The machine (ISA, both models, TRIAD, SALISH, Executive, satellite); TRILISP; the first Good and Hofstadter demonstrations; go, draughts, chess, backgammon; front-panel notebook; Livermore loops; floating-point unit |

## Hardware philosophy

The hardware follows one rule: *every comparison has three outcomes, and the machine should say so in one trit.* Most of the design follows from it.

- **Balanced ternary, after Setun.** Trits are −1, 0 and +1. A word is 27 trits, about ±3.8 × 10¹². Negation is tritwise inversion, so there is no sign bit and no negative zero, and truncation is rounding. Core is 3¹² = 531,441 words, addressed symmetrically about zero. The negative half is the Executive's, and it is protected.
- **Trichotomy in the instruction set.** The condition code is one trit. `J3` jumps three ways in one instruction. `SEL` is a truth-table instruction, and `EQV` is a tritwise product, so on ±1 values exclusive-or is multiplication.
- **Kleene logic in hardware.** Minimum and maximum are Kleene's strong *and* and *or*, and 0 means *unknown*. This was a principle, not a convenience: it caught a real bug in the Refal collector, where a programmer had treated 0 as false.
- **One architecture, two models, after System/360.**
  - The **Model 30** is microprogrammed. It has a 156-word horizontal microprogram in a *writable* control store, and its timing is exact to the cycle.
  - The **Model 90** is hardwired. It has a floating-point unit, and an optional look-ahead unit with a 32-word instruction stack, after the CDC 6600 and 7600.
  - Randomised testing checks that the two models give the same results.
- **Self-modification as a feature.** Under the WCS key, programs can write microcode and claim new opcodes. Every fetch increments a tally (the "Beer monitor"), so programs can profile themselves. These two features are what the intelligence-explosion demonstration needs.
- **Period peripherals, with period timing.**
  - Cards, a printer and a card punch.
  - Tape (timed as the IBM 729 and 2401, readable backward), a drum of 3¹¹ words, and disc packs of 3¹³ words timed as the IBM 2311.
  - Atlas-style paging: 729-word pages on the drum, serviced by a pager written in SALISH that runs in protected core.

**A known tension.** The documents admit that the speeds are design parameters, not engineering. A real ternary machine in 1967 "would very likely have been slower." The CDC 7600 figures in the comparison are quoted from memory and have not been checked against sources.

## Software philosophy

The software is built as a stack of levels, each written in the one below and able to reach down into it. That is Hofstadter's "tangled hierarchy" made into architecture.

```
  Programs ............................ demonstrations, games, AI, Mix, the tower  --+
  Languages written in SALISH ......... TRILISP, Refal, WHALE, TRI-TRAN; SALISH/S --+ |
  SALISH, TRIAD and the Executive ..... compilers, protected core, paging        <-+ |  SALISH/S compiles itself
  The instruction set ................. 27-trit words, J3, SEL, Kleene logic          |
  Model 30 microcode / Model 90 ....... a writable control store of 156 words   <----+  explosion.sal writes the
  The simulator ....................... Python, with the satellite's job control         microcode it runs on
```

*Every level of the Duwamish can reach the level beneath it* (from ARCHITECTURE.md §10 and DEMONSTRATOR.md §1, §17, §19).

The accented loop is the deepest one. A program at the top profiles itself, invents a new instruction, and writes the microcode for it at the bottom.

- **Period practice.** The Executive is a resident monitor, and work arrives as card decks (`//JOB`, `//EXEC`, `//DATA`) through a satellite, as on a 1960s installation. SALISH is BCPL-like, TRI-TRAN is FORTRAN 66, and TRILISP is LISP 1.5.
- **Ternary all the way up.** SALISH has three-valued conditions, in which 0 is *unknown* and not false, and a three-way `sign ... of`. TRI-TRAN's arithmetic IF is one `J3` instruction, and TRILISP tags its types with one trit.
- **Termination as a language feature.** A SALISH program marked `bloop` is certified to halt, or refused with each unbounded loop named. This is Hofstadter's BlooP and FlooP as a compiler pass.
- **Self-hosting as specification.** SALISH/S, the compiler written in SALISH, must agree card for card with the satellite's Python compilers, with and without optimisation. Each compiler is the other's test, and that agreement found a real bug in the optimiser.
- **Languages as subjects.** Interpreters run interpreters (the M-EVAL tower), a quine prints itself, Mix specialises an interpreter into a compiler, and the Byurakan receiver builds the machine a message describes. Programs are data at every level.

## Outputs so far

There are 33 numbered demonstrations in `docs/DEMONSTRATOR.md`, each with a job deck, and most are checked by the test suite. The table gives each one's headline result as the machine prints it.

| principle | program | headline result |
| --- | --- | --- |
| **Good:** self-improvement | `explosion.sal` | Invents microcoded instructions, improving its own improver first; gains converge to a fixed point (work 1.3×, improver 1.4×) |
| **Good:** self-improvement | `selfhost/salish.sal` | Compiles itself to 15,154 identical cards; the optimised copy is 16% faster and builds itself, so the improvement happens once |
| **Good:** weight of evidence | `banburismus.sal` | Sequential test in decibans, with logarithms computed by the machine |
| **Good:** weight of evidence | `colossus.sal` | Sets all five chi wheels as the operators did; the right setting stands 115 db clear |
| **Good:** weight of evidence | `whale/diagnosis.whl` | Asking by expected weight of evidence takes 7.4 questions, against 10.3 in fixed order |
| **Good:** weight of evidence | `perceptron.sal` | Counting each unit once matches 800 error corrections; abstains where the perceptron errs |
| **Good:** the unseen | `goodturing.sal` | Estimates 0.2280 against a true 0.2292, with an honest failure on a text that breaks the assumptions |
| **Good:** randomised learning | `go.sal` | 5×5 go: 8 to 20 wins in 20 against random; randomisation beats MENACE-style credit (15 in 20) |
| **Good:** game search | `fiveyear.sal` | Probability-guided search scores 3½ of 6 against Shannon's full width; fallible-opponent backup 1 of 6 |
| **Good:** game search | `chess.sal`, `draughts.sal`, `backgammon.sal` | Alpha-beta saves 85% at four plies; Samuel-style learning; TD self-play goes from 0 to 7 wins in 16 |
| **Good:** FFT | `pfa.ftn` | Good's prime-factor maps save 26% of multiplications but only 2.5% of the time |
| **Hofstadter:** self-reference | `selfref.sal`, `quine.sal` | A computed, verified statement of its own Gödel number; a byte-exact quine |
| **Hofstadter:** two modes of thought | `miu.sal` | 216 theorems derived, MU never; the invariant is one trit |
| **Hofstadter:** BlooP and FlooP | `sequences.sal`, `floop.sal` | GEB's sequences certified to halt; Collatz refused, its loops named |
| **Hofstadter:** levels | `metacircular.lsp` | M-EVAL runs its own source inside TRILISP inside SALISH, each level costing 100 to 160 times the level below it |
| **Hofstadter:** diagonal argument | `diagonal.lsp` | `CONTRARY` defeats the halting oracle at any budget |
| **Hofstadter:** analogy | `copycat.sal` | ijl 29 in 30; deep answers (mrrjjjj, wyz) found at the lowest temperatures |
| **Hofstadter:** programs about programs | `refal/mix.ref` | A Turing-machine interpreter specialised to a compiled program, about 8× faster |
| **Good and Hofstadter:** a message between the stars | `ceti/listen.sal`, `ceti/receive.ref` | Noise, CTA-102 and the pulsar are natural (the pulsar is +126 db against noise, −393 db for artifice); a transmission counting the primes is artificial at the eighth prime. A Refal receiver builds the machine the message describes and grows its seed: Fibonacci lengths, then a 27×27 carpet |
| **Ashby** | `homeostat.sal` | Ultrastability by uniselector, and re-adaptation after a connection is reversed |
| **Pask** | `saki.sal` | Every trainee reaches 94–96%; a fixed schedule suits only the slow ones (55%) |
| **Knuth** | `life.sal`, `sorting.sal`, `tst.sal`, `fft23.ftn`, `polyphase.sal` | Kleene Life is sound but incomplete (124 unknowns against 7 true ones); polyphase merging takes 32.6 s against balanced merging's 42.9 s |
| **Systems** | `atlas/workload.sal` | Atlas's learning pager takes 295 faults, against 362 (LRU), 398 (FIFO) and 214 (Belady's optimum) |
| **AI of the period** | `eliza.lsp`, `gps.lsp`, `strips.lsp`, `shrdlu.lsp`, `prolog.lsp` | ELIZA's 1966 transcript word for word; Shakey's ten-step plan; Winograd's dialogue; a Prolog that answers UNKNOWN |
| **Cray** | `livermore.sal` | 0.315 MFLOPS at best, about 115 times slower than the CDC 7600's peak |

Around the programs are:

- the documents: README, ARCHITECTURE, DEMONSTRATOR, IDENTITY, and manuals for SALISH, TRILISP, TRI-TRAN, WHALE and Refal;
- the Universal Entropics house identity, with SVG marks;
- a notebook of 21 sections, with cycle-exact front panels, the TRILISP heap, Kleene Life, the homeostat, SAKI and the WHALE clinic, all animated from the machine's core.

## Quality assessment

The core deliverable is good: it is correct, measured and honest. What holds it back from being excellent lies outside the code: no way in for a newcomer, unchecked history, and no project infrastructure. I wrote all of this, so treat my assessment as a well-informed self-review, not an independent audit.

| area | rating | evidence | what would raise it |
| --- | --- | --- | --- |
| Correctness | Strong | 153 tests pass. The two models are checked alike by random programs, and SALISH/S agrees card for card with the Python compilers. Quine, MU and Colossus results are checked in the machine itself | Run the tests automatically on every push |
| Honesty of claims | Strong | Every demonstration has a "what it does not show". Wrong predictions are left on record, such as the floating-point unit's ten times against the hundred predicted | Keep the rule as the project grows |
| Illustrating Good | Strong | Decibans, Good–Turing, randomisation, the explosion and quasi-utility are each shown with numbers that can be checked | A single Good walkthrough, in the order a reader should meet them |
| Illustrating Hofstadter | Strong | Self-reference, quining, levels, BlooP, the strange loop, Copycat, Mix, and now GEB's frame, outer and inner messages (Byurakan) | The second Futamura projection would close the last loop (below) |
| Historical fidelity | Fair | The period is real, but several sources are later (Refal-5, Copycat, Jones–Gomard–Sestoft). The CDC 7600 figures and the dates in this review are from memory | Check dates and figures against sources; label each anachronism in place |
| Documentation | Good, but long | About 3,200 lines across ten files. DEMONSTRATOR.md alone is over 1,100 lines | A short guided tour: ten demonstrations, an hour, in order |
| Accessibility | Fair | You need Python and a terminal, and some jobs take minutes. The notebook helps, but it is committed without outputs | A static web page of results and panels; a published notebook with its outputs |
| Performance | Fair | The simulator runs the Model 90 at about 1.2 million instructions a second. Refal manages about 1,000 steps a second, and a 200-number sort takes a minute and a half | Profile the fast path; relink Refal's accumulators in place |
| Project hygiene | Weak | No licence, no CI, one long-lived branch of 32 large commits, only now proposed for merge | A licence, a CI workflow, and a merge to the main branch |
| Link to the fiction | Undecided | Universal Entropics, Woodworth and the Soviet line are present, and Byurakan gives the Soviet 1970s a scene. Kelvanov is still deliberately left out | The decisions in Open questions |

Two specific risks:

- **The simulator is the only witness.** Every number depends on Python code written in a few days. The cross-checks between the models and between the compilers reduce this risk, but no one has reviewed the code independently.
- **Size against attention.** At 40-odd demonstrations, the strongest ones (the explosion's fixed point, the self-hosting compiler, Colossus, Mix) are easy to miss among the rest.

## Suggestions for future work

My first recommendation is to make what exists easy to see before building more. Then I would add demonstrations that tie the Soviet thread to Good and Hofstadter; the first of these, Byurakan, is now built. They are ranked below by value to the demonstrator, with my estimate of effort.

1. **A guided tour, published.** Pick the ten strongest demonstrations and put them in a one-hour order. Publish them as a static page of results and front-panel animations, plus a notebook with its outputs kept. *Small to medium.* This does more for a reader than any new program.
2. **Project hygiene.** Merge the branch, add a licence and run the suite on every push. *Small.*
3. **Byurakan, the next step: a message that builds the sender.** *Done in its first form, 12 November 2026 (DEMONSTRATOR §33).* The listener weighs four signals, and the Refal receiver builds the machine a message describes and grows its seed. Three follow-ons would take it further:
   - a third transmission whose machine draws the sender, which is the "computer that builds the alien" idea itself;
   - shrinking the receiver's guesses, for example by learning the separators from the frame instead of knowing them;
   - a Kelvanov thread, if you decide he appears (Open questions).

   *Medium.*
4. **Bongard problems.** Bongard published them in Moscow in 1967, and GEB chapter XIX takes them up. Perception as the search for a description fits Copycat's machinery and the Soviet thread. *Medium.*
5. **The second Futamura projection.** Rewrite Mix in its own flowchart language, so that it can specialise itself to the interpreter and produce a compiler. This closes the last strange loop. *Large:* several hundred blocks of flowchart, and probably tens of minutes of machine time.
6. **Turchin's supercompiler.** It drives Refal directly and finds loops by generalising configurations. *Large.* It is the most "Soviet" idea in the project, and the hardest.
7. **Check the history.** Check dates, the CDC 7600 figures and attributions against sources, now including CTA-102, the pulsar and Lindenmayer. Mark each anachronism where it appears. *Small.*
8. **Speed.** Make Refal relink accumulators in place, as Refal-5 does, and profile the Model 90's fast path. *Medium.* This matters only if larger Refal programs (items 3, 5 and 6) are wanted.
9. **More of the period's labs, if wanted.** Edinburgh's Freddy robot and Michie's BOXES, or Stanford's MYCIN certainty factors (1974) set against Good's weights of evidence. That pairing would make a sharp contrast. *Medium each.*

## Open questions

These decisions are yours, and several of the suggestions above wait on them. Each item gives my recommendation; tick it off once it is settled.

- [ ] **Who is the demonstrator for?**

  Readers of the novels, technical readers, or both? This decides between a story-led tour and a reference. My recommendation: both, with the guided tour written for a curious general reader.
- [ ] **What year is it?**

  Is the machine strictly of 1967, or does it live on into the early 1970s, as the AI programs and Mix already suggest? My recommendation: let the Duwamish have a service life from 1967 to about 1975, with each program dated within it.
- [ ] **How do the novels appear in the repository?**

  Universal Entropics, Woodworth and the Soviet line are present. Should *The Visibilities* and *The Lamps are Going Out* be named at all? My recommendation: no in-fiction documents until you decide, as now.
- [ ] **Does Kelvanov appear, and how?**

  He could be an author of record on the CETI or Refal work, a name only in comments, or absent. The internal-exile and parallel-lives themes suggest a "parallel" Soviet machine or archive. That would be a larger, deliberate choice.
- [ ] **How strict are we about anachronism?**

  Some sources date from later than the setting: Refal-5 syntax, Copycat, and Jones, Gomard and Sestoft's flowchart Mix. Do they stay, labelled as now, or get replaced with period equivalents where these exist?
- [ ] **Is the repository to be public?**

  If it is, it needs a licence. Is the house identity (the UE mark) to be shared under the same licence as the code?
- [ ] **What comes next?**

  Byurakan is done. My recommendation now is items 1 and 2, the tour and hygiene, before more demonstrations. After them: Bongard problems, the Byurakan follow-ons, or the second Futamura projection.
