"""The satellite: job control for the Duwamish.

As with IBM's 7094/7044 Direct Coupled System, a smaller satellite computer
stands between the operators and the Duwamish.  It reads card decks, runs
the translators (SALISH compiler, TRIAD assembler), spools the line
printer, and feeds job steps to the Duwamish Executive over a channel.

A job deck is a sequence of cards (lines).  Control cards begin with //:

    //JOB name [TIME=cycles]        start a job
    //SALISH [FROM=path] [LIST]     compile SALISH (the following cards, or a
                                    file); LIST prints the TRIAD listing
    //TRIAD [FROM=path] [LIST]      assemble TRIAD source
    //EXEC [name]                   run the program just translated, or a
                                    catalogued program (e.g. TRILISP)
    //DATA [FROM=path]              the cards that follow (or a file) are
                                    read by the program through SVC 2
    //END                           end of job (optional)

Anything after `--` on a control card is a comment.
"""

import os
import re
import shlex
import time

from . import isa
from . import machine as mach
from . import salish
from . import triad

HERE = os.path.dirname(__file__)
EXECUTIVE_SRC = os.path.join(HERE, "executive.tri")
USER_ORIGIN = 100
USER_STACK = mach.MEM_MAX + 1
CYCLE_NS = 200

CATALOGUE = {
    "TRILISP": os.path.join(HERE, "lib", "trilisp.sal"),
}


class JobError(Exception):
    pass


def assemble_executive():
    with open(EXECUTIVE_SRC) as f:
        return triad.assemble(f.read())


def translate_salish(text, fname, include_path=None):
    asm, comp = salish.compile_source(text, fname, include_path)
    obj = triad.assemble(asm, origin=USER_ORIGIN)
    return obj, asm, comp


_catalogue_cache = {}


def catalogued(name):
    name = name.upper()
    if name not in CATALOGUE:
        raise JobError(f"no program {name} in the catalogue")
    if name not in _catalogue_cache:
        path = CATALOGUE[name]
        with open(path) as f:
            obj, asm, comp = translate_salish(f.read(), path)
        _catalogue_cache[name] = obj
    return _catalogue_cache[name]


class Step:
    def __init__(self, job, kind, name):
        self.job = job
        self.kind = kind          # 'EXEC'
        self.name = name
        self.obj = None
        self.data = []
        self.result = None
        self.out_start = 0
        self.messages = []


class Job:
    def __init__(self, name, opts):
        self.name = name
        self.time_limit = int(opts.get("TIME", "0"))
        self.steps = []
        self.log = []
        self.failed = False


def parse_control(card):
    body = card[2:].split("--", 1)[0]
    parts = shlex.split(body)
    if not parts:
        return None, [], {}
    verb = parts[0].upper()
    args, opts = [], {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            opts[k.upper()] = v
        else:
            args.append(p)
    return verb, args, opts


class Satellite:
    def __init__(self, decks, model=30, wcs=False, listing=False,
                 out=None, base_dir=None, trace=False):
        self.model = model
        self.wcs = wcs
        self.listing = listing
        self.out = out or (lambda s: print(s, end=""))
        self.base_dir = base_dir or os.getcwd()
        self.jobs = []
        self.queue = []            # (job, step) awaiting execution
        self.cur = None
        self.responses = []
        self.cmd = []
        self.trace = trace
        for text, fname in decks:
            self.read_deck(text, fname)

    # ------------------------------------------------------------------
    # card reading and translation
    # ------------------------------------------------------------------
    def resolve(self, path, deck_dir):
        for base in (deck_dir, self.base_dir):
            p = os.path.join(base, path)
            if os.path.exists(p):
                return p
        raise JobError(f"file not found: {path}")

    def read_deck(self, text, fname):
        deck_dir = os.path.dirname(os.path.abspath(fname))
        cards = text.splitlines()
        job = None
        i = 0
        pending_obj = None
        while i < len(cards):
            card = cards[i]
            i += 1
            if not card.startswith("//"):
                continue
            verb, args, opts = parse_control(card)
            if verb is None:
                continue
            body = []
            while i < len(cards) and not cards[i].startswith("//"):
                body.append(cards[i])
                i += 1
            if verb == "JOB":
                job = Job(args[0] if args else "NONAME", opts)
                self.jobs.append(job)
                pending_obj = None
                continue
            if job is None:
                job = Job("NONAME", {})
                self.jobs.append(job)
            if job.failed:
                continue
            try:
                if verb in ("SALISH", "TRIAD"):
                    if "FROM" in opts:
                        path = self.resolve(opts["FROM"], deck_dir)
                        with open(path) as f:
                            src = f.read()
                        sname = opts["FROM"]
                    else:
                        src = "\n".join(body) + "\n"
                        path = os.path.join(deck_dir, f"{job.name}.inline")
                        sname = f"{job.name} (inline)"
                    t0 = time.time()
                    if verb == "SALISH":
                        pending_obj, asm, comp = translate_salish(src, path)
                        msg = (f"SALISH: {sname}: {len(pending_obj.words)}"
                               f" words, {len(comp.procs)} procedures")
                        job.log.append(msg)
                        if comp.bloop_report:
                            job.log.append(comp.bloop_report)
                        if "LIST" in args or self.listing:
                            job.log.append(pending_obj.listing_text())
                    else:
                        pending_obj = triad.assemble(src, origin=USER_ORIGIN)
                        job.log.append(f"TRIAD: {sname}: "
                                       f"{len(pending_obj.words)} words")
                        if "LIST" in args or self.listing:
                            job.log.append(pending_obj.listing_text())
                    del t0
                elif verb == "EXEC":
                    step = Step(job, "EXEC", args[0] if args else "GO")
                    step.obj = catalogued(args[0]) if args else pending_obj
                    if step.obj is None:
                        raise JobError("//EXEC with nothing to execute")
                    job.steps.append(step)
                    self.queue.append((job, step))
                elif verb == "DATA":
                    if not job.steps:
                        raise JobError("//DATA before //EXEC")
                    if "FROM" in opts:
                        with open(self.resolve(opts["FROM"], deck_dir)) as f:
                            body = f.read().splitlines()
                    data = []
                    for line in body:
                        data.extend(ord(c) for c in line)
                        data.append(10)
                    job.steps[-1].data.extend(data)
                elif verb == "END":
                    job = None
                else:
                    raise JobError(f"unknown control card //{verb}")
            except (salish.CompileError, triad.AsmError, JobError,
                    OSError) as e:
                job.log.append(f"*** {verb} FAILED: {e}")
                job.failed = True
                self.queue = [(j, s) for j, s in self.queue if j is not job]

    # ------------------------------------------------------------------
    # the channel to the Executive
    # ------------------------------------------------------------------
    def channel_out(self, m, v):
        self.cmd.append(v)
        c = self.cmd
        if c[0] == 1:
            self.cmd = []
            self.start_next(m)
        elif c[0] == 2 and len(c) == 5:
            self.cmd = []
            self.end_step(m, c[1], c[2], c[3], c[4])
        elif c[0] not in (1, 2):
            self.cmd = []

    def channel_in(self, m):
        return self.responses.pop(0) if self.responses else -1

    def start_next(self, m):
        if not self.queue:
            self.responses = [-1]
            return
        job, step = self.queue.pop(0)
        self.cur = (job, step)
        mem = m.mem
        for i in range(mach.MEM_OFF, mach.MEM_SIZE):
            mem[i] = 0
        m.load_image(step.obj.image())
        m.reader = step.data
        m.reader_pos = 0
        m.tally_clear()
        step.out_start = len(m.printer)
        step.i0 = m.icount
        step.t0 = time.time()
        entry = step.obj.entry if step.obj.entry is not None else USER_ORIGIN
        self.responses = [entry, USER_STACK, job.time_limit]

    def end_step(self, m, how, value, where, cycles):
        job, step = self.cur
        step.result = (how, value, where, cycles, m.icount - step.i0,
                       time.time() - step.t0)
        step.output = m.text(m.printer[step.out_start:])
        self.cur = None

    # ------------------------------------------------------------------
    def run(self):
        m = mach.Machine(model=self.model, wcs_enabled=self.wcs,
                         satellite=self)
        self.machine = m
        ex = assemble_executive()
        self.executive = ex
        m.load_image(ex.image())
        m.pc = ex.entry
        reason = m.run()
        self.report(m, reason)
        return m

    def report(self, m, reason):
        w = self.out
        line = "=" * 72
        w(f"{line}\nDUWAMISH MODEL {self.model}"
          f"{'  (WRITABLE CONTROL STORE ENABLED)' if self.wcs else ''}"
          f"   -- satellite job log\n")
        tty = m.text(m.tty)
        if tty:
            w("CONSOLE: " + tty.replace("\n", "\n         ").rstrip() + "\n")
        for job in self.jobs:
            w(f"{line}\nJOB {job.name}\n")
            for msg in job.log:
                w(f"  {msg}\n")
            for step in job.steps:
                w(f"{'-' * 72}\nSTEP //EXEC {step.name}\n{'-' * 72}\n")
                if step.result is None:
                    w("  (not run)\n")
                    continue
                w(step.output)
                if step.output and not step.output.endswith("\n"):
                    w("\n")
                how, value, where, cycles, instrs, secs = step.result
                w(f"{'-' * 72}\n")
                if how == 0:
                    status = f"EXIT {value}"
                else:
                    status = (f"PROGRAM CHECK {how} "
                              f"({isa.TRAP_NAMES.get(how, '?')}) AT {where}")
                us = cycles * CYCLE_NS / 1000
                w(f"END OF STEP: {status}.  {instrs:,} instructions, "
                  f"{cycles:,} cycles = {us / 1000:,.3f} ms of Duwamish "
                  f"time ({secs:.1f} s simulated)\n")
        w(f"{line}\n")
        if reason != "halt":
            w(f"MACHINE STOPPED: {reason} "
              f"{getattr(m, 'check_message', '')}\n")


def run_decks(paths, **kw):
    decks = []
    for p in paths:
        with open(p) as f:
            decks.append((f.read(), p))
    sat = Satellite(decks, **kw)
    sat.run()
    return sat


def run_program(path, data=None, model=30, wcs=False, listing=False,
                time_limit=0, out=None):
    """Convenience: wrap one SALISH/TRIAD source file into a job."""
    kind = "TRIAD" if path.endswith(".tri") else "SALISH"
    name = re.sub(r"\W", "", os.path.splitext(os.path.basename(path))[0])
    deck = [f"//JOB {name.upper()} TIME={time_limit}",
            f"//{kind} FROM={os.path.abspath(path)}"
            + (" LIST" if listing else ""),
            "//EXEC"]
    if data:
        deck.append(f"//DATA FROM={os.path.abspath(data)}")
    sat = Satellite([("\n".join(deck), path)], model=model, wcs=wcs, out=out)
    sat.run()
    return sat
