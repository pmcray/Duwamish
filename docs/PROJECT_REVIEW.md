# Duwamish: project review

*Written 12 November 2026.*

This review covers the one commit that existed when it was written (`b7c5f9c`
on `claude/optimistic-bohr-s9zd7f`), plus the research-topic proposal that
followed it. That commit had not been merged to `main`.

## 1. What the project is

Duwamish supports a novel by making one character's technical work real. Alan
Fredericks (born 21 June 1956) is a musician of Eno/Gabriel stature who writes
his own software on a VAXstation. The project builds that software so it
actually runs, and so the book's technical detail comes from measurement and
not invention.

**A gap to flag:** the project brief describes a demonstrator of "Goodian and
Hofstadterian principles set out in the documents in the repository". The
repository has never contained those documents, only a one-line README.
Everything so far serves the Alan storyline; none of it has been checked
against those principles.

## 2. Timelines

**In the fiction**

| When | Event |
|---|---|
| 1979 | Alan abandons his astrophysics PhD |
| 1985 | Buys a VAXstation; writes the music program in VAX MACRO |
| 1986 | Releases *A Lost Traveller* |
| 1986–89 | Resumes the PhD; writes star-formation and maximum-entropy code in VAX FORTRAN |

**In the project**

| When | Event |
|---|---|
| 12 Oct 2026 | Feasibility discussion; decision not to clone VMS wholesale |
| 12–13 Oct | Assembler, MiniVMS, CDGEN and two tracks built, tested and pushed |
| 13 Oct | Research topic proposed (L1551 IRS5, cloud collapse); awaiting a decision |
| 12 Nov | This review; no work in between |

## 3. Hardware and software philosophy

- **Real hardware, emulated.** The target is the KA630 processor board of the
  MicroVAX II / VAXstation II (1985), run on the open-simh emulator, with 5 MB
  of memory and an RD54 disk.
- **No DEC software.** VAX/VMS and its MACRO compiler can't be licensed, so
  everything that runs on the emulated machine was written for this project.
- **Build only what the story needs.** MiniVMS is "enough VMS" to run Alan's
  program convincingly, not a clone.
- **Period authenticity.** Alan's code is real VAX MACRO in 1985 idiom, using
  only techniques published by then. It calls the operating system the way a
  VMS program would.
- **Verify by measurement.** The audio was checked numerically, not by ear.

## 4. Outputs so far

About 8,500 lines in `vax/`:

| Deliverable | Size | What it does |
|---|---|---|
| CDGEN (`cdgen/CDGEN.MAR`) | 1,874 lines of MACRO | Manuscript in, CD audio stream out: six voice types, envelopes, reverb |
| MiniVMS (`minivms/`) | about 4,300 lines of MACRO | Login, DCL commands, disk driver, versioned files, system services, VMS-style errors |
| Assembler (`tools/macro32.py`) | about 1,900 lines of Python | Assembles the MACRO source without DEC tools |
| Host tools | about 440 lines of Python | Disk images; WAV and burnable CD image output |
| Album (`album/`) | 2 manuscripts | "Departure" (3:29) and "The Visibilities" (2:17), with MP3 previews |
| Build and docs | Makefile, scripts, README | `make album` runs the whole pipeline in about three minutes |

## 5. Quality assessment

**What is solid**

- **End-to-end pipeline:** it worked from a clean rebuild on 13 October.
- **Assembler:** its encodings match the emulator's disassembler on a test
  file, and it has since assembled about 6,000 lines that run correctly.
- **Audio:** pitch is within a cent, with no clipping or clicks.
- **Error handling:** bad file names, access violations and CTRL/Y abort all
  behave sensibly.

**What is weak**

- **No automated tests.** Everything was checked by scripted sessions read by
  eye. A regression would go unnoticed.
- **The music is unjudged.** Both tracks were composed as demonstrations and
  have not been listened to critically. Whether they sound like something Alan
  would release is the author's call; "competent ambient sketch" is the likely
  verdict.
- **MiniVMS is thin where the story doesn't look.**
  - It has one user and one directory, and the password is never checked.
  - Deleted file space is mostly not reclaimed.
  - System services don't validate addresses passed by programs.
  - It starts through the emulator's loader, not a real boot block.
- **Some "VMS" details are from memory.** A few status-code values and
  control-block layouts are approximations. They are self-consistent but would
  not match a real VMS binary.
- **CDGEN's musical limits:**
  - one note per voice;
  - no tempo changes within a piece;
  - no per-note expression beyond dynamics.
- **Historical claims are unverified.** The mastering route (Sony PCM-1610,
  U-matic), tape capacities and the 1¾-hour render estimate come from memory
  plus one instruction count. The MicroVAX II speed figure is rough and could
  be off by a factor of two.
- **Housekeeping:** one large commit, no licence file, no pull request, and
  the opcode table derived from open-simh needs an attribution note.

Overall, it is a convincing working demonstrator and good source material for
the novel, but it's a prototype.

## 6. Suggested future work

1. **Verify the history** in the "Notes for the novel" section of
   `vax/README.md` against sources before any of it reaches the book.
2. **Add a regression test:** render a short manuscript and compare a
   checksum, plus an assembler encoding test.
3. **Astrophysics code** in VAX FORTRAN, once the topic is settled.
4. **Authenticity extras:** tape output, a real boot block, the VAXstation
   screen.
5. **CDGEN improvements** driven by listening: polyphony, tempo changes, more
   voices.
6. **Tidy-up:** licence, attribution, merge to `main`.

## 7. Open questions

1. **Who is "Good"?** The research-topic proposal assumed Nelson Goodman
   ("grue", *Languages of Art*). "Goodian" more naturally means I. J. Good,
   Turing's Bletchley colleague, who wrote on Bayesian weight of evidence,
   maximum entropy and the intelligence explosion. If Good is meant, the
   Goodman remarks were off target, and Good would fit the maximum-entropy
   thread even better.
2. **Where are the principles documents?** They need adding to the repository.
3. **Research topic:** Cambridge, L1551 IRS5 and the collapsing-cloud model,
   or one of the alternatives?
4. **FORTRAN route:** a real compiler for the emulated VAX (months of work),
   or period-style source compiled with gfortran on the host (quick)?
5. **How much fidelity?** Is "looks and behaves like VMS" enough, or is closer
   compatibility wanted?
6. **The music:** are the two tracks placeholders, or the start of a real
   album to be shaped?
7. **Hardware in the book:** is Alan's machine fixed as a VAXstation II with
   an RD54 and TK50, and is the mastering-tape route an acceptable replacement
   for "written to a CD"?
