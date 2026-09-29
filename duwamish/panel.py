"""The Duwamish front panel: exact, cycle-by-cycle visualisations for Jupyter.

A Recorder drives the Model 30 micro-engine one micro-cycle at a time and
records everything a 1967 operator could have watched on the console:
every register, the condition trit, the mode, the micro-program counter,
the control lines asserted, each core-memory read and write, traps, and the
printer.  `animate()` turns the recording into a self-contained HTML/JS
front panel -- ternary lamps (amber +1, blue -1, dark 0), a datapath
diagram showing which registers drive the buses, the microprogram and
program listings, and a map of core that flashes as words are fetched,
read and written.  The animation replays the recording, so the lamps light
in exactly the order the machine lit them.

Nothing here needs more than Python and a browser: in Jupyter the panel is
shown in an iframe; `save_html()` writes a page that opens anywhere.
"""

import html
import json
import os

from . import isa
from . import machine as mach
from . import microasm
from . import salish
from . import satellite
from . import ternary as t
from . import triad

REG_NAMES = ["PC", "IR", "MAR", "MDR", "T", "U", "EA", "CNT",
             "R0", "R1", "R2", "R3", "R4", "R5", "R6", "FP", "SP",
             "C", "MODE", "IPC"]
NREG = len(REG_NAMES)
KEYFRAME = 500
STACK_WINDOW = 400

_SRC = {v: k for k, v in microasm.SRC.items()}
_DST = {v: k for k, v in microasm.DST.items()}
_ALU = {v: k for k, v in microasm.ALU.items()}
_SEQ = {v: k for k, v in microasm.SEQ.items()}
_SEL = {v: k for k, v in microasm.SEL.items()}
_SPECIAL = {v: k for k, v in microasm.SPECIAL.items()}


def _state(m):
    return m.ur[1:9] + m.rf[:] + [m.c, m.mode, m.ipc]


# ----------------------------------------------------------------------
# recording
# ----------------------------------------------------------------------
class Recording:
    """Everything the animation needs, as plain lists (JSON-ready)."""

    def __init__(self):
        self.upc = []          # micro-address executed in each frame
        self.deltas = []       # [reg, value, reg, value, ...] per frame
        self.memop = []        # 0 none, 1 read, 2 write, 3 instruction fetch
        self.memaddr = []
        self.memval = []
        self.clock = []
        self.icount = []
        self.keyframes = {}    # frame -> full register state (before frame)
        self.writes = []       # [frame, addr, value]: DMA, traps, ...
        self.output = []       # [frame, char]
        self.events = []       # [frame, text]
        self.initial = {}      # addr -> value at the start
        self.listing = []      # [addr, text]
        self.regions = []      # [name, lo, hi, css class]
        self.words = {}        # instruction word -> disassembly
        self.title = ""


class Recorder:
    """Run a machine on its micro-engine, recording every micro-cycle."""

    def __init__(self, m, title=""):
        self.m = m
        self.rec = Recording()
        self.rec.title = title
        self.fetch_addr = m.fetch_addr

    def snapshot_region(self, lo, hi):
        for a in range(lo, hi + 1):
            v = self.m.peek(a)
            if v:
                self.rec.initial[a] = v

    def dma(self, image):
        """Words written into core by the channel (the satellite loading a
        program) are recorded as a burst of writes in the current frame."""
        n = len(self.rec.upc)
        for a, w in image:
            self.rec.writes.append([n, a, w])

    def run(self, max_frames=20000, until=None):
        m, rec = self.m, self.rec
        prev = _state(m)
        nprint = len(m.printer)
        ntty = len(m.tty)
        trap_words = list(range(isa.LOC_TRAP_IPC, 0))
        while len(rec.upc) < max_frames and not m.halted:
            n = len(rec.upc)
            if n % KEYFRAME == 0:
                rec.keyframes[n] = prev[:]
            upc = m.upc
            uw = m.ucode[upc]
            mem, special = uw[4], uw[10]
            event = None
            trapped = False
            try:
                m.ustep()
            except mach.Trap as tr:
                trapped = True
                event = (f"TRAP {tr.code} ({isa.TRAP_NAMES.get(tr.code, '?')})"
                         f" at {m.ipc}, argument {tr.arg}")
                try:
                    m.take_trap(tr.code, tr.arg)
                except mach.MachineCheck as mc:
                    event = str(mc)
            cur = _state(m)
            d = []
            for i in range(NREG):
                if cur[i] != prev[i]:
                    d += [i, cur[i]]
            rec.upc.append(upc)
            rec.deltas.append(d)
            op = 0
            if mem and not trapped:
                op = 3 if special == 1 else (1 if mem < 0 else 2)
            rec.memop.append(op)
            rec.memaddr.append(m.ur[mach.MAR] if op else 0)
            rec.memval.append(m.ur[mach.MDR] if op else 0)
            rec.clock.append(m.clock)
            rec.icount.append(m.icount)
            if trapped:
                for a in trap_words:
                    rec.writes.append([n, a, m.peek(a)])
            if event:
                rec.events.append([n, event])
            if special == 3 and m.halted:
                rec.events.append([n, "HALT"])
            for ch in m.printer[nprint:]:
                rec.output.append([n, ch])
            for ch in m.tty[ntty:]:
                rec.output.append([n, ch])
            nprint, ntty = len(m.printer), len(m.tty)
            ir = m.ur[mach.IR]
            if ir not in rec.words:
                rec.words[ir] = isa.disassemble(ir)
            prev = cur
            if until and until(m):
                break
        return rec

    # static information for the display
    def add_listing(self, obj):
        for line in obj.listing:
            head = line[:8].strip()
            if head.lstrip("-").isdigit():
                a = int(head)
                self.rec.listing.append([a, obj.words.get(a, 0),
                                         line[8:].rstrip()])
        self.rec.listing.sort(key=lambda x: x[0])

    def finish(self):
        """Remember how to read every word the listings may show, including
        words the program wrote over its own code."""
        m = self.m
        for a, _, _ in self.rec.listing:
            w = m.peek(a)
            if w not in self.rec.words:
                self.rec.words[w] = isa.disassemble(w)
        self.rec.cs = _control_store(m)

    def add_region(self, name, lo, hi, css):
        self.rec.regions.append([name, lo, hi, css])
        self.snapshot_region(lo, hi)


def _control_store(m):
    cs = []
    labels = {}
    for k, v in m.mp.labels.items():
        labels.setdefault(v, k)
    used = max(m.mp.free, max((i for i, (a, b) in enumerate(m.cs) if a or b),
                              default=0) + 1)
    for i in range(used):
        a, b, alu, d, mem, setc, pcinc, lit, seq, sel, special, target = \
            m.ucode[i]
        text = m.mp.source_lines[i] if i < len(m.mp.source_lines) else \
            _describe_microword(m.ucode[i])
        cs.append({"a": _SRC.get(a, "?") if (d or setc) else "",
                   "b": _SRC.get(b, "?") if (d or setc) and b else "",
                   "alu": _ALU.get(alu, "?") if (d or setc) else "",
                   "d": _DST.get(d, "?") if d else "",
                   "mem": mem, "setc": setc, "pcinc": pcinc, "lit": lit,
                   "seq": _SEQ.get(seq, "?"), "sel": _SEL.get(sel, ""),
                   "special": _SPECIAL.get(special, ""), "target": target,
                   "text": text, "label": labels.get(i, ""),
                   "invented": i >= m.mp.free})
    return cs


def _describe_microword(u):
    """Render a microword that the machine wrote for itself."""
    a, b, alu, d, mem, setc, pcinc, lit, seq, sel, special, target = u
    parts = []
    if d or setc:
        src = _SRC.get(a, "?")
        if src == "LIT":
            src = f"#{lit}"
        elif src == "KS":
            src = f"K[{lit}]"
        rhs = src if alu == 0 else f"{_ALU.get(alu, '?')} {src}"
        parts.append(f"{_DST.get(d, 'NUL')}<-{rhs}")
    if mem:
        parts.append("READ" if mem < 0 else "WRITE")
    if setc:
        parts.append("SETC")
    if pcinc:
        parts.append("PC+1")
    s = _SEQ.get(seq, "?")
    if s in ("GOTO", "CALL", "DISP"):
        parts.append(f"{s} {target}")
    elif s != "NEXT":
        parts.append(s)
    return ", ".join(parts) + "      ; written by the program"


# ----------------------------------------------------------------------
# convenience: set up and record common situations
# ----------------------------------------------------------------------
def record_triad(source, max_frames=20000, origin=100, title="TRIAD program",
                 wcs=False, setup=None, fpu=False):
    """Assemble TRIAD source and run it in supervisor mode from its entry,
    with no Executive, recording every micro-cycle.  End it with HLT.
    fpu=True fits the floating-point feature to the Model 30."""
    obj = triad.assemble(source, origin=origin)
    m = mach.Machine(model=30, wcs_enabled=wcs, fpu=fpu)
    m.load_image(obj.image())
    m.pc = obj.entry if obj.entry is not None else origin
    m.rf[8] = mach.MEM_MAX + 1
    if setup:
        setup(m, obj)
    r = Recorder(m, title)
    r.add_listing(obj)
    r.add_region("program", obj.low, obj.end + 20, "prog")
    r.add_region("stack", mach.MEM_MAX - STACK_WINDOW + 1, mach.MEM_MAX, "stack")
    r.run(max_frames)
    r.finish()
    r.machine, r.obj = m, obj
    return r


class _RecordingSatellite(satellite.Satellite):
    recorder = None

    def start_next(self, m):
        super().start_next(m)
        if self.cur and self.recorder:
            self.recorder.dma(self.cur[1].obj.image())


def record_salish(source, data="", max_frames=40000, title="SALISH job",
                  wcs=False, fpu=False):
    """Compile SALISH (text, or a path to a .sal file), then boot the
    Executive and run the job exactly as the satellite would, recording
    from the first micro-cycle of the Executive."""
    fname = "<notebook>"
    if "\n" not in source and source.endswith(".sal") and os.path.exists(source):
        fname = source
        with open(source) as f:
            source = f.read()
    deck = "//JOB NOTEBOOK\n//SALISH\n" + source + "\n//EXEC\n"
    if data:
        deck += "//DATA\n" + data + "\n"
    sat = _RecordingSatellite([(deck, os.path.join(os.getcwd(), "nb.job"))],
                              model=30, wcs=wcs, fpu=fpu,
                              out=lambda s: None)
    job = sat.jobs[0]
    if job.failed:
        raise RuntimeError("\n".join(job.log))
    obj = job.steps[0].obj
    m = mach.Machine(model=30, wcs_enabled=wcs, satellite=sat, fpu=fpu)
    ex = satellite.assemble_executive()
    m.load_image(ex.image())
    m.pc = ex.entry
    r = Recorder(m, title)
    sat.recorder = r
    r.add_listing(ex)
    r.add_listing(obj)
    r.rec.listing.sort(key=lambda x: x[0])
    r.add_region("Executive", ex.low, ex.high, "exec")
    r.add_region("trap words", isa.LOC_TRAP_IPC, -1, "trap")
    heap = obj.end + 200
    r.add_region("program", obj.low, heap, "prog")
    r.add_region("stack", mach.MEM_MAX - STACK_WINDOW + 1, mach.MEM_MAX, "stack")
    r.run(max_frames)
    r.finish()
    r.machine, r.obj, r.executive, r.satellite = m, obj, ex, sat
    r.source_name = fname
    return r


def instruction_costs(recorder):
    """Micro-cycles taken by each kind of instruction in a recording,
    measured from the recording itself: [(mnemonic, count, average cycles,
    fewest, most)]."""
    rec = recorder.rec if isinstance(recorder, Recorder) else recorder
    fetch = microasm.default_microprogram().labels["FETCH"]
    starts = [i for i, u in enumerate(rec.upc) if u == fetch]
    costs = {}
    for a, b in zip(starts, starts[1:]):
        # the first word loaded into IR after a fetch is the instruction
        ir = None
        for j in range(a, b):
            d = rec.deltas[j]
            for k in range(0, len(d), 2):
                if d[k] == 1 and ir is None:
                    ir = d[k + 1]
        if ir is None:
            continue
        name = isa.disassemble(ir).split()[0]
        cyc = rec.clock[b - 1] - (rec.clock[a - 1] if a else 0)
        costs.setdefault(name, []).append(cyc)
    rows = [(k, len(v), sum(v) / len(v), min(v), max(v))
            for k, v in costs.items()]
    return sorted(rows, key=lambda r: -r[1])


def show_costs(recorder):
    rows = instruction_costs(recorder)
    tab = ("<table><tr><th>instruction</th><th>executed</th>"
           "<th>micro-cycles (average)</th><th>fewest</th><th>most</th></tr>")
    for name, n, avg, lo, hi in rows:
        tab += (f"<tr><td>{name}</td><td>{n}</td><td>{avg:.1f}</td>"
                f"<td>{lo}</td><td>{hi}</td></tr>")
    return _display(_LAMP_CSS + f'<div class="dw">{tab}</table></div>')


def fuse(m, at, n, opcode=-1, kslot=0, uaddr=None):
    """Invent a new instruction, as programs/good/explosion.sal does: copy
    the n instruction words starting at `at` into the constant store, write
    one microinstruction per word (IR <- K[k], PC+1, DISP next) into free
    control store, point the unused `opcode` at it, and patch the first
    word to use it.  The machine's WCS key must be on."""
    mp = m.mp
    fetch = mp.labels["FETCH"]
    uaddr = mp.free if uaddr is None else uaddr
    for j in range(n):
        m.kstore[kslot + j] = m.peek(at + j)
        nxt = fetch if j == n - 1 else uaddr + j + 1
        half_a = microasm.encode_a(a=microasm.SRC["KS"], alu=microasm.ALU["PASS"],
                                   d=microasm.DST["IR"], pcinc=1 if j else 0,
                                   lit=kslot + j)
        half_b = microasm.encode_b(seq=microasm.SEQ["DISP"], target=nxt)
        m.cs_write(2 * (uaddr + j), half_a)
        m.cs_write(2 * (uaddr + j) + 1, half_b)
    m.map_write(opcode, uaddr)
    m.poke(at, isa.encode(opcode))
    return uaddr


# ----------------------------------------------------------------------
# rendering
# ----------------------------------------------------------------------
def _display(markup, height=None):
    try:
        from IPython.display import HTML
    except ImportError:            # pragma: no cover - outside Jupyter
        return markup
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")          # "consider IFrame": we mean it
        return HTML(markup)


def _iframe(page, height):
    return (f'<iframe srcdoc="{html.escape(page, quote=True)}" '
            f'style="width:100%;height:{height}px;border:0;'
            f'background:#15171a" sandbox="allow-scripts"></iframe>')


def page_html(recording, speed=40):
    """The complete front-panel page for a recording."""
    rec = recording.rec if isinstance(recording, Recorder) else recording
    data = {
        "title": rec.title,
        "regs": REG_NAMES,
        "upc": rec.upc, "deltas": rec.deltas, "memop": rec.memop,
        "memaddr": rec.memaddr, "memval": rec.memval,
        "clock": rec.clock, "icount": rec.icount,
        "keyframes": rec.keyframes, "writes": rec.writes,
        "output": rec.output, "events": rec.events,
        "initial": rec.initial, "listing": rec.listing,
        "regions": rec.regions,
        "words": {str(k): v for k, v in rec.words.items()},
        "cs": getattr(rec, "cs", []),
        "fetch": microasm.default_microprogram().labels["FETCH"],
        "memwait": mach.MEM_WAIT, "cycle_ns": satellite.CYCLE_NS,
        "speed": speed,
    }
    return _PAGE.replace("__DATA__", json.dumps(data, separators=(",", ":")))


def animate(recording, height=1330, speed=40):
    """Show the front panel for a recording in a notebook cell."""
    return _display(_iframe(page_html(recording, speed), height))


def save_html(recording, path, speed=40):
    """Write the front panel as a stand-alone web page."""
    with open(path, "w") as f:
        f.write(page_html(recording, speed))
    return path


# ---------------- static pictures ----------------
_LAMP_CSS = """
<style>
.dw{font-family:'DejaVu Sans Mono',Menlo,Consolas,monospace;color:#d8d2c0;
 background:#1d2024;padding:10px 14px;border-radius:6px;display:inline-block}
.dw .row{display:flex;align-items:center;gap:10px;margin:3px 0}
.dw .lab{width:84px;text-align:right;color:#a9a18a;font-size:12px}
.dw .lamps{display:flex;gap:3px}
.dw .g{margin-left:6px}
.dw .l{width:11px;height:11px;border-radius:50%;background:#2b2f35;
 box-shadow:inset 0 0 2px #000}
.dw .l.p{background:#ffb238;box-shadow:0 0 6px #ffb238}
.dw .l.n{background:#4fc3ff;box-shadow:0 0 6px #4fc3ff}
.dw .val{font-size:12px;color:#e8e2cc;min-width:260px}
.dw table{border-collapse:collapse;font-size:12px}
.dw td,.dw th{padding:3px 8px;border-bottom:1px solid #333;text-align:left}
.dw th{color:#a9a18a;font-weight:normal}
</style>"""


def _lamps(v, n=27, groups=3, breaks=None):
    ts = t.trits(t.wrap(v, n), n)[::-1]
    out = []
    for i, x in enumerate(ts):
        cls = "p" if x > 0 else "n" if x < 0 else ""
        gap = ""
        pos = n - i
        if breaks is not None:
            gap = " g" if i and pos in breaks else ""
        elif i and i % groups == 0:
            gap = " g"
        out.append(f'<span class="l {cls}{gap}"></span>')
    return '<span class="lamps">' + "".join(out) + "</span>"


def show_word(v, label="word"):
    """One 27-trit word as lamps, with its notations."""
    v = t.wrap(v)
    row = (f'<div class="row"><span class="lab">{html.escape(label)}</span>'
           f'{_lamps(v)}<span class="val">{v:,} &nbsp; {t.to_tstr(v, strip=True)}'
           f' &nbsp; {t.to_hept(v)}</span></div>')
    return _display(_LAMP_CSS + f'<div class="dw">{row}</div>')


def show_words(pairs):
    """Several (label, value) words, one row each."""
    rows = "".join(
        f'<div class="row"><span class="lab">{html.escape(str(k))}</span>'
        f'{_lamps(v)}<span class="val">{t.wrap(v):,} &nbsp; '
        f'{t.to_tstr(t.wrap(v), strip=True)}</span></div>'
        for k, v in pairs)
    return _display(_LAMP_CSS + f'<div class="dw">{rows}</div>')


def show_instruction(text):
    """Assemble one TRIAD instruction and show its fields."""
    obj = triad.assemble(f"X = 1000\nY = 2000\n        {text}\n")
    w = obj.words[0]
    op, r, x, m, addr = isa.decode(w)
    fields = [("op", op, 5, isa.BY_OP.get(op, ("?",))[0]),
              ("r", isa.reg_field(r), 2, isa.reg_name(r)),
              ("x", isa.reg_field(x), 2, isa.reg_name(x) if x else "none"),
              ("m", m, 2, {-1: "indirect", 0: "direct", 1: "immediate"}.get(m)),
              ("addr", addr, 16, str(addr))]
    row = (f'<div class="row"><span class="lab">{html.escape(text)}</span>'
           f'{_lamps(w, breaks={22, 20, 18, 16})}</div>')
    tab = "<table><tr><th>field</th><th>trits</th><th>value</th>" \
          "<th>meaning</th></tr>"
    for name, val, n, meaning in fields:
        tab += (f"<tr><td>{name}</td><td>{t.to_tstr(val, n)}</td>"
                f"<td>{val}</td><td>{html.escape(str(meaning))}</td></tr>")
    tab += "</table>"
    return _display(_LAMP_CSS + f'<div class="dw">{row}{tab}</div>')


def show_memory_map(obj, machine=None, executive=None):
    """Where everything lives in core, drawn to two scales."""
    from .satellite import USER_STACK, USER_ORIGIN
    ex = executive or satellite.assemble_executive()
    sym = obj.symbols
    code_end = sym.get("CODE_END", obj.end)
    end = obj.end
    sp = machine.rf[8] if machine else USER_STACK
    heap = None
    if machine and "G_heap_ptr" in sym:
        heap = machine.peek(sym["G_heap_ptr"]) or None
    rows = [
        ("trap words", isa.LOC_TRAP_IPC, -1, "#c678dd",
         "PC, code, mode, C, vector, argument, faulting address"),
        ("Executive", ex.low, ex.high, "#e06c75", "resident monitor (protected)"),
        ("Executive stack", -2000, -100, "#9b4d55", "grows down from -100"),
        ("program code", USER_ORIGIN, code_end - 1, "#ffb238",
         f"{code_end - USER_ORIGIN} words of machine code"),
        ("globals, strings, literals", code_end, end - 1, "#98c379",
         f"{end - code_end} words"),
        ("heap", end, heap or end, "#61afef",
         "grows up from here" + (f" (now to {heap})" if heap else "")),
        ("stack", sp, USER_STACK - 1, "#4fc3ff",
         f"grows down from {USER_STACK - 1}"),
    ]
    width = 760
    lo_all, hi_all = -mach.MEM_MAX, mach.MEM_MAX

    def x(a):
        return 20 + (a - lo_all) * width / (hi_all - lo_all)
    svg = [f'<svg width="{width + 40}" height="{70 + 24 * len(rows)}" '
           f'style="background:#1d2024;font:12px monospace">']
    svg.append(f'<rect x="20" y="18" width="{width}" height="18" fill="#2b2f35"/>')
    svg.append(f'<line x1="{x(0)}" y1="12" x2="{x(0)}" y2="42" stroke="#888"/>')
    svg.append(f'<text x="20" y="12" fill="#a9a18a">-265,720</text>')
    svg.append(f'<text x="{x(0) - 4}" y="54" fill="#a9a18a">0</text>')
    svg.append(f'<text x="{width - 40}" y="12" fill="#a9a18a">+265,720</text>')
    for name, a, b, col, note in rows:
        w = max(2, x(b + 1) - x(a))
        svg.append(f'<rect x="{x(a)}" y="18" width="{w}" height="18" '
                   f'fill="{col}"/>')
    y = 76
    for name, a, b, col, note in rows:
        svg.append(f'<rect x="20" y="{y - 10}" width="12" height="12" fill="{col}"/>')
        svg.append(f'<text x="40" y="{y}" fill="#e8e2cc">{html.escape(name):28}'
                   f'</text><text x="240" y="{y}" fill="#a9a18a">{a:>9,} .. '
                   f'{b:>9,}   {html.escape(note)}</text>')
        y += 24
    svg.append("</svg>")
    return _display("".join(svg))


def show_tally(machine, obj, top=12):
    """The Beer monitor read out: instructions executed per procedure."""
    from . import profile
    rows = profile.by_procedure(machine, obj, top)
    if not rows:
        return _display("<p>no tallies</p>")
    width, bh = 420, 18
    peak = rows[0][1]
    svg = [f'<svg width="{width + 330}" height="{bh * len(rows) + 16}" '
           f'style="background:#1d2024;font:12px monospace">']
    for i, (name, n, pct) in enumerate(rows):
        y = 8 + i * bh
        w = max(1, width * n / peak)
        svg.append(f'<text x="8" y="{y + 12}" fill="#e8e2cc">{html.escape(name)}</text>')
        svg.append(f'<rect x="160" y="{y + 2}" width="{w}" height="{bh - 5}" '
                   f'fill="#ffb238"/>')
        svg.append(f'<text x="{170 + w}" y="{y + 12}" fill="#a9a18a">'
                   f'{n:,}  ({pct:.1f}%)</text>')
    svg.append("</svg>")
    return _display("".join(svg))


# ----------------------------------------------------------------------
# the front-panel page (HTML + JavaScript, no external dependencies)
# ----------------------------------------------------------------------
_PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>Duwamish front panel</title>
<style>
:root{--bg:#15171a;--panel:#1d2024;--edge:#33373e;--ink:#e8e2cc;--dim:#a9a18a;
 --amber:#ffb238;--blue:#4fc3ff;--green:#7ee787;--red:#ff6b6b;--violet:#c678dd}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:12px 'DejaVu Sans Mono',Menlo,Consolas,monospace}
.top{display:flex;align-items:center;gap:10px;padding:8px 12px;
 background:#101214;border-bottom:1px solid var(--edge);flex-wrap:wrap}
.top h1{font-size:14px;margin:0 12px 0 0;color:var(--amber);letter-spacing:2px}
button{background:#2b2f35;color:var(--ink);border:1px solid #444;border-radius:4px;
 padding:4px 9px;font:inherit;cursor:pointer}
button:hover{border-color:var(--amber)}
input[type=range]{accent-color:var(--amber)}
.grid{display:grid;grid-template-columns:640px 1fr;gap:10px;padding:10px}
.box{background:var(--panel);border:1px solid var(--edge);border-radius:6px;padding:8px 10px}
.box h2{font-size:11px;color:var(--dim);margin:0 0 6px 0;font-weight:normal;
 letter-spacing:1px;text-transform:uppercase}
.row{display:flex;align-items:center;gap:8px;height:17px}
.lab{width:40px;text-align:right;color:var(--dim)}
.lamps{display:flex;gap:2px}
.l{width:10px;height:10px;border-radius:50%;background:#2b2f35;box-shadow:inset 0 0 2px #000}
.l.p{background:var(--amber);box-shadow:0 0 5px var(--amber)}
.l.n{background:var(--blue);box-shadow:0 0 5px var(--blue)}
.g{margin-left:5px}
.val{color:var(--ink);white-space:pre;min-width:120px}
.chg .lab{color:var(--amber)}
.ctl{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}
.sig{padding:1px 5px;border:1px solid #3a3f46;border-radius:3px;color:#666}
.sig.on{color:#111;background:var(--amber);border-color:var(--amber)}
.sig.rd.on{background:var(--green);border-color:var(--green)}
.sig.wr.on{background:var(--red);border-color:var(--red)}
.list{white-space:pre;overflow:hidden;line-height:15px;height:258px}
.list div{padding:0 4px}
.list .cur{background:#3a3120;color:var(--amber)}
.list .lbl{color:var(--violet)}
.list .inv{color:var(--green)}
#out{white-space:pre-wrap;height:120px;overflow:auto;background:#0e1012;
 padding:6px;color:#e8e2cc;border:1px solid var(--edge)}
#events{height:60px;overflow:auto;color:var(--violet);white-space:pre}
svg text{font:11px 'DejaVu Sans Mono',Menlo,monospace}
.stat{color:var(--dim)} .stat b{color:var(--ink);font-weight:normal}
canvas{display:block;image-rendering:pixelated}
.legend span{margin-right:12px}
.key{display:inline-block;width:9px;height:9px;margin-right:4px}
</style></head><body>
<div class="top">
 <h1>DUWAMISH MODEL 30</h1>
 <button id="b0" title="back to the start">&#9198;</button>
 <button id="bb" title="back one micro-cycle">&#9664;&#9664;</button>
 <button id="bp" title="play / pause">&#9654; run</button>
 <button id="bs" title="one micro-cycle">step &#181;</button>
 <button id="bi" title="to the next instruction">step instr</button>
 <span class="stat">speed</span>
 <input id="spd" type="range" min="0" max="100" value="40" style="width:110px">
 <span id="spdv" class="stat"></span>
 <input id="scrub" type="range" min="0" max="1" value="0" style="flex:1;min-width:160px">
</div>
<div class="top stat" id="stats" style="border-top:0"></div>
<div class="grid">
 <div>
  <div class="box"><h2>console lamps -- amber +1, blue -1, dark 0</h2><div id="lamps"></div>
   <div class="ctl" id="sigs"></div></div>
  <div class="box" style="margin-top:10px"><h2>datapath -- this micro-cycle</h2>
   <svg id="dp" width="616" height="250"></svg></div>
 </div>
 <div>
  <div class="box"><h2>microprogram (control store)</h2><div id="ulist" class="list"></div></div>
  <div class="box" style="margin-top:10px"><h2>program in core</h2><div id="plist" class="list"></div></div>
 </div>
</div>
<div class="grid" style="padding-top:0">
 <div class="box"><h2>core -- each word a cell; flashes as it is used</h2>
  <div class="legend stat"><span><i class="key" style="background:#ffb238"></i>instruction fetch</span>
  <span><i class="key" style="background:#7ee787"></i>read</span>
  <span><i class="key" style="background:#ff6b6b"></i>write</span>
  <span><i class="key" style="background:#4b5260"></i>non-zero word</span></div>
  <div id="maps"></div></div>
 <div>
  <div class="box"><h2>stack (top of user core)</h2><div id="stack" class="list" style="height:150px"></div></div>
  <div class="box" style="margin-top:10px"><h2>line printer / console</h2><div id="out"></div></div>
  <div class="box" style="margin-top:10px"><h2>events</h2><div id="events"></div></div>
 </div>
</div>
<script>
const D = __DATA__;
const N = D.upc.length;
const R = D.regs, NR = R.length;
const IDX = {}; R.forEach((r,i)=>IDX[r]=i);
const HEPT = "NOPQRSTUVWXYZ0ABCDEFGHIJKLM";
const W3 = [];
function trits(v,n){ const out=[]; for(let i=0;i<n;i++){ let r=((v%3)+3)%3; if(r===2) r=-1; out.push(r); v=(v-r)/3; } return out; }
function hept(v){ let s=""; for(let i=0;i<9;i++){ let r=((v%27)+27)%27; if(r>13) r-=27; s=HEPT[r+13]+s; v=(v-r)/27; } return s; }
// ---------------- state reconstruction ----------------
let frame = 0, regs = null, mem = new Map();
const kf = {}; for (const k in D.keyframes) kf[+k] = D.keyframes[k];
const writesAt = new Map();
for (const [f,a,v] of D.writes){ if(!writesAt.has(f)) writesAt.set(f,[]); writesAt.get(f).push([a,v]); }
const eventsAt = new Map(); for (const [f,t] of D.events) eventsAt.set(f,t);
function resetMem(){ mem = new Map(); for (const a in D.initial) mem.set(+a, D.initial[a]); }
function applyFrame(i){           // effects of frame i on regs and memory
  const d = D.deltas[i]; for (let k=0;k<d.length;k+=2) regs[d[k]] = d[k+1];
  const w = writesAt.get(i); if (w) for (const [a,v] of w) mem.set(a,v);
  if (D.memop[i]===2) mem.set(D.memaddr[i], D.memval[i]);
}
// state "at frame f" = after frame f-1 executed; frame f is the one about to show
function seek(f){
  f = Math.max(0, Math.min(N, f));
  if (regs===null || f < frame){ resetMem(); regs = kf[0].slice(); frame = 0; }
  while (frame < f){ applyFrame(frame); frame++; }
}
// ---------------- lamps ----------------
const LAMPROWS = ["PC","IR","MAR","MDR","T","U","EA","CNT","R1","R2","R3","R4","R5","R6","FP","SP"];
const lampEls = {}, valEls = {}, rowEls = {};
const lampsDiv = document.getElementById("lamps");
function mkRow(name, n, breaks){
  const row = document.createElement("div"); row.className="row";
  const lab = document.createElement("span"); lab.className="lab"; lab.textContent=name; row.appendChild(lab);
  const ls = document.createElement("span"); ls.className="lamps"; const arr=[];
  for (let i=0;i<n;i++){ const s=document.createElement("span"); s.className="l";
    const pos = n-i; if (i && (breaks ? breaks.includes(pos) : (i%3===0))) s.style.marginLeft="5px";
    ls.appendChild(s); arr.push(s); }
  row.appendChild(ls);
  const v = document.createElement("span"); v.className="val"; row.appendChild(v);
  lampsDiv.appendChild(row); lampEls[name]=arr; valEls[name]=v; rowEls[name]=row;
}
LAMPROWS.forEach(r=> mkRow(r, 27, r==="IR" ? [22,20,18,16] : null));
mkRow("uPC", 8, []); mkRow("C", 1, []); mkRow("MODE",1,[]);
function setLamps(name, v, n){
  const ts = trits(v, n).reverse(), arr = lampEls[name];
  for (let i=0;i<n;i++){ const c = ts[i]>0?"l p":ts[i]<0?"l n":"l"; if (arr[i].className!==c) arr[i].className=c; if (arr[i].style.marginLeft) {} }
}
const SIGS = ["READ","WRITE","IFETCH","SETC","PC+1","CASE","CALL","RET","DISP","ENDI","TRAP","IOIN","IOOUT","RTI","WCS","FPU"];
const sigEls = {};
const sigDiv = document.getElementById("sigs");
SIGS.forEach(s=>{ const e=document.createElement("span"); e.className="sig"+(s==="READ"?" rd":s==="WRITE"?" wr":""); e.textContent=s; sigDiv.appendChild(e); sigEls[s]=e; });
const aluLab = document.createElement("span"); aluLab.className="sig on"; sigDiv.appendChild(aluLab);
// ---------------- datapath diagram ----------------
const dp = document.getElementById("dp");
const NS = "http://www.w3.org/2000/svg";
function el(tag, attrs, parent){ const e=document.createElementNS(NS,tag); for (const k in attrs) e.setAttribute(k, attrs[k]); (parent||dp).appendChild(e); return e; }
const BOX = {}; const topRow = ["PC","IR","MAR","MDR","T","U","EA","CNT"];
topRow.forEach((n,i)=>{ BOX[n] = {x:8+i*62, y:8, w:56, h:26}; });
const lower = ["R","X","SP","ADDR","LIT","KS","CV","0"];
const lowerLab = {R:"R (reg r)",X:"X (index)",SP:"SP",ADDR:"ADDR",LIT:"literal",KS:"K store",CV:"C trit","0":"zero"};
lower.forEach((n,i)=>{ BOX[n] = {x:8+i*62, y:206, w:56, h:26}; });
BOX.ALU = {x:220, y:104, w:120, h:44}; BOX.CORE = {x:470, y:92, w:130, h:70};
BOX.NUL = {x:370, y:112, w:60, h:26};
const boxEls = {};
for (const n in BOX){ const b=BOX[n];
  const r = el("rect",{x:b.x,y:b.y,width:b.w,height:b.h,rx:4,fill:"#23272c",stroke:"#3a3f46"});
  const tx = el("text",{x:b.x+b.w/2,y:b.y+b.h/2+4,"text-anchor":"middle",fill:"#a9a18a"});
  tx.textContent = n==="CORE" ? "core memory" : n==="NUL" ? "C only" : (lowerLab[n]||n);
  boxEls[n] = {r, tx}; }
const aluText = el("text",{x:280,y:162,"text-anchor":"middle",fill:"#ffb238"});
const memText = el("text",{x:535,y:178,"text-anchor":"middle",fill:"#a9a18a"});
const coreText = el("text",{x:535,y:196,"text-anchor":"middle",fill:"#a9a18a"});
const pA = el("path",{fill:"none",stroke:"#7ee787","stroke-width":3});
const pB = el("path",{fill:"none",stroke:"#4fc3ff","stroke-width":3});
const pD = el("path",{fill:"none",stroke:"#ffb238","stroke-width":3});
const pM = el("path",{fill:"none",stroke:"#7ee787","stroke-width":3,"stroke-dasharray":"6 4"});
const pInc = el("text",{x:36,y:52,"text-anchor":"middle",fill:"#ffb238"});
el("text",{x:230,y:98,fill:"#7ee787"}).textContent="A bus";
el("text",{x:300,y:98,fill:"#4fc3ff"}).textContent="B bus";
el("text",{x:350,y:100,fill:"#ffb238"}).textContent="D bus";
function mid(b, side){ const B=BOX[b]; if(!B) return null;
  if (side==="bot") return [B.x+B.w/2, B.y+B.h]; if (side==="top") return [B.x+B.w/2, B.y];
  if (side==="left") return [B.x, B.y+B.h/2]; return [B.x+B.w, B.y+B.h/2]; }
function route(src, dstX, dstY){ const s = BOX[src]; if(!s) return "";
  const from = s.y < 100 ? mid(src,"bot") : mid(src,"top");
  const my = s.y < 100 ? 70 : 180;
  return `M${from[0]},${from[1]} L${from[0]},${my} L${dstX},${my} L${dstX},${dstY}`; }
// ---------------- listings ----------------
const ulist = document.getElementById("ulist"), plist = document.getElementById("plist");
function showMicro(u){
  let s = ""; const lo = Math.max(0, u-7), hi = Math.min(D.cs.length-1, lo+16);
  for (let i=lo;i<=hi;i++){ const c=D.cs[i]; if(!c) continue;
    const lab = c.label ? `<span class="lbl">${(c.label+":").padEnd(8)}</span>` : "        ";
    const cls = i===u ? "cur" : c.invented ? "inv" : "";
    s += `<div class="${cls}">${String(i).padStart(4)}  ${lab}${escapeHtml(c.text)}</div>`; }
  ulist.innerHTML = s;
}
const LA = D.listing.map(x=>x[0]);
function lowerBound(arr, x){ let lo=0, hi=arr.length; while(lo<hi){ const m=(lo+hi)>>1; if(arr[m]<x) lo=m+1; else hi=m; } return lo; }
function showProgram(pc){
  if (!LA.length){ plist.textContent=""; return; }
  let k = lowerBound(LA, pc); const lo = Math.max(0, k-7), hi = Math.min(LA.length-1, lo+16);
  let s=""; for (let i=lo;i<=hi;i++){ const [a,w,t]=D.listing[i];
    const now = mem.has(a) ? mem.get(a) : 0;
    const note = (w !== now && /^\s+\S{9}\s/.test(t)) ? `   <span class="inv">now ${escapeHtml(D.words[String(now)]||hept(now))} -- rewritten</span>` : "";
    s += `<div class="${a===pc?'cur':''}">${String(a).padStart(7)} ${escapeHtml(t)}${note}</div>`; }
  plist.innerHTML = s;
}
function escapeHtml(s){ return s.replace(/&/g,"&amp;").replace(/</g,"&lt;"); }
// ---------------- core maps ----------------
const maps = [], mapsDiv = document.getElementById("maps");
for (const [name, lo, hi, css] of D.regions){
  const n = hi-lo+1;
  const CW = n <= 100 ? 14 : n <= 400 ? 8 : n <= 1500 ? 5 : 3, COLS = Math.floor(600/CW), rows = Math.ceil(n/COLS);
  const lab = document.createElement("div"); lab.className="stat"; lab.style.margin="6px 0 2px";
  lab.textContent = `${name}: words ${lo.toLocaleString()} .. ${hi.toLocaleString()}`; mapsDiv.appendChild(lab);
  const cv = document.createElement("canvas"); cv.width = COLS*CW; cv.height = rows*CW; cv.style.width=(COLS*CW)+"px";
  mapsDiv.appendChild(cv);
  maps.push({name, lo, hi, cv, CW, COLS, ctx: cv.getContext("2d"), heat: new Float32Array(n), kind: new Uint8Array(n)});
}
function touch(addr, kind){ for (const m of maps){ if (addr>=m.lo && addr<=m.hi){ m.heat[addr-m.lo]=1; m.kind[addr-m.lo]=kind; } } }
const KCOL = [null,[126,231,135],[255,107,107],[255,178,56]];
function drawMaps(decay){
  for (const m of maps){ const ctx=m.ctx, n=m.hi-m.lo+1, CW=m.CW, COLS=m.COLS;
    const img = ctx.createImageData(COLS*CW, Math.ceil(n/COLS)*CW);
    for (let i=0;i<n;i++){ const x=(i%COLS)*CW, y=Math.floor(i/COLS)*CW;
      let r=38,g=41,b=46; const v = mem.get(m.lo+i); if (v) { r=75; g=82; b=96; }
      const h=m.heat[i]; if (h>0.02){ const c=KCOL[m.kind[i]]; r=r+(c[0]-r)*h; g=g+(c[1]-g)*h; b=b+(c[2]-b)*h; m.heat[i]*=decay; }
      for (let dy=0;dy<CW-1;dy++) for (let dx=0;dx<CW-1;dx++){ const o=((y+dy)*COLS*CW+(x+dx))*4; img.data[o]=r; img.data[o+1]=g; img.data[o+2]=b; img.data[o+3]=255; } }
    ctx.putImageData(img,0,0); }
}
// ---------------- stack window ----------------
const stackDiv = document.getElementById("stack");
function showStack(sp, fp){
  let s=""; for (let a=Math.max(sp-2, 0); a<Math.min(sp+10, 265721); a++){
    const v = mem.get(a)||0; const mark = (a===sp?"SP>":a===fp?"FP>":"   ");
    s += `<div class="${a===sp?'cur':''}">${mark} ${String(a).padStart(7)}  ${hept(v)}  ${String(v).padStart(12)}</div>`; }
  stackDiv.innerHTML = s;
}
// ---------------- output & events ----------------
const outDiv = document.getElementById("out"), evDiv = document.getElementById("events");
function showOutput(){ let s=""; for (const [f,c] of D.output){ if (f>=frame) break; s += String.fromCharCode(c); }
  if (outDiv.textContent !== s){ outDiv.textContent = s; outDiv.scrollTop = outDiv.scrollHeight; } }
function showEvents(){ let s=""; for (const [f,t] of D.events){ if (f>=frame) break; s += `${String(f).padStart(7)}  ${t}\n`; }
  if (evDiv.textContent !== s){ evDiv.textContent = s; evDiv.scrollTop = evDiv.scrollHeight; } }
// ---------------- render one frame ----------------
const statsEl = document.getElementById("stats"), scrub = document.getElementById("scrub");
scrub.max = N;
let prevRegs = null;
function render(){
  const i = Math.min(frame, N-1);          // the micro-cycle just executed
  const shown = frame>0 ? frame-1 : 0;
  for (const r of LAMPROWS){ const v = regs[IDX[r]]; setLamps(r, v, 27);
    let txt = String(v).padStart(14) + "  " + hept(v);
    if (r==="IR") txt = "  " + (D.words[String(v)]||"");
    valEls[r].textContent = txt;
    rowEls[r].classList.toggle("chg", prevRegs!==null && prevRegs[IDX[r]]!==v); }
  const u = frame>0 ? D.upc[frame-1] : D.upc[0];
  setLamps("uPC", u, 8); valEls["uPC"].textContent = String(u).padStart(14) + "  " + (D.cs[u]?D.cs[u].label:"");
  setLamps("C", regs[IDX.C], 1); valEls["C"].textContent = ["  -1  (negative, or less)","   0  (zero, or equal)","  +1  (positive, or greater)"][regs[IDX.C]+1];
  setLamps("MODE", regs[IDX.MODE], 1); valEls["MODE"].textContent = regs[IDX.MODE]>0 ? "  supervisor" : "  user";
  // control signals of the micro-cycle just executed
  const c = D.cs[u] || {};
  const on = {READ:c.mem<0, WRITE:c.mem>0, IFETCH:c.special==="IFETCH", SETC:!!c.setc, "PC+1":!!c.pcinc,
    CASE:c.seq==="CASE", CALL:c.seq==="CALL", RET:c.seq==="RET", DISP:c.seq==="DISP", ENDI:c.seq==="ENDI",
    TRAP:c.special==="TRAP", IOIN:c.special==="IOIN", IOOUT:c.special==="IOOUT", RTI:c.special==="RTI",
    WCS:["WCS","WKS","WMAP","RCS","RKS","RMAP"].includes(c.special), FPU:c.special==="FPU"};
  for (const s of SIGS) sigEls[s].classList.toggle("on", frame>0 && !!on[s]);
  aluLab.textContent = frame>0 && c.alu ? "ALU " + c.alu + (c.seq==="CASE" ? "  CASE "+c.sel : "") : "ALU idle";
  // datapath
  for (const n in boxEls){ boxEls[n].r.setAttribute("stroke","#3a3f46"); boxEls[n].r.setAttribute("fill","#23272c"); }
  pA.setAttribute("d",""); pB.setAttribute("d",""); pD.setAttribute("d",""); pM.setAttribute("d",""); pInc.textContent="";
  memText.textContent=""; coreText.textContent="";
  if (frame>0){
    if (c.a){ pA.setAttribute("d", route(c.a, 250, 104)); hi(c.a,"#7ee787"); }
    if (c.b){ pB.setAttribute("d", route(c.b, 310, 104)); hi(c.b,"#4fc3ff"); }
    if (c.a || c.b) hi("ALU","#ffb238");
    if (c.d && BOX[c.d]){ const t = BOX[c.d]; const tx = t.x+t.w/2;
      pD.setAttribute("d", t.y<100 ? `M280,104 L280,86 L${tx},86 L${tx},${t.y+t.h}` : `M280,148 L280,194 L${tx},194 L${tx},${t.y}`); hi(c.d,"#ffb238"); }
    else if (c.setc){ pD.setAttribute("d","M340,126 L370,126"); hi("NUL","#ffb238"); }
    aluText.textContent = c.alu ? c.alu : "";
    const op = D.memop[frame-1];
    if (op){ hi("CORE", op===2?"#ff6b6b":op===3?"#ffb238":"#7ee787"); hi("MAR","#a9a18a"); hi("MDR", op===2?"#ff6b6b":"#7ee787");
      pM.setAttribute("stroke", op===2?"#ff6b6b":op===3?"#ffb238":"#7ee787");
      pM.setAttribute("d", "M258,34 L258,56 L535,56 L535,92");
      memText.textContent = (op===2?"write ":op===3?"fetch ":"read ") + D.memaddr[frame-1];
      coreText.textContent = "= " + D.memval[frame-1] + "  (+" + D.memwait + " wait cycles)"; }
    if (c.pcinc) pInc.textContent = "+1";
  } else aluText.textContent = "";
  showMicro(u); showProgram(regs[IDX.IPC]); showStack(regs[IDX.SP], regs[IDX.FP]);
  showOutput(); showEvents(); drawMaps(0.82);
  const clk = frame>0 ? D.clock[frame-1] : 0, ic = frame>0 ? D.icount[frame-1] : 0;
  statsEl.innerHTML = `${escapeHtml(D.title)} &nbsp; micro-cycle <b>${frame.toLocaleString()}</b> of ${N.toLocaleString()} &nbsp;|&nbsp; clock <b>${clk.toLocaleString()}</b> cycles = <b>${(clk*D.cycle_ns/1000).toFixed(1)}</b> &micro;s &nbsp;|&nbsp; instructions <b>${ic.toLocaleString()}</b> &nbsp;|&nbsp; executing at <b>${regs[IDX.IPC]}</b>: <b>${escapeHtml(D.words[String(regs[IDX.IR])]||"")}</b>`;
  scrub.value = frame;
  prevRegs = regs.slice();
}
function hi(n, col){ if (boxEls[n]){ boxEls[n].r.setAttribute("stroke", col); boxEls[n].r.setAttribute("fill","#2e2a20"); } }
// ---------------- controls ----------------
let playing = false, acc = 0, last = 0;
const spd = document.getElementById("spd"), spdv = document.getElementById("spdv");
spd.value = D.speed;
function rate(){ const x = +spd.value; return Math.round(Math.pow(10, x/25)); }   // 1 .. 10,000 cycles/s
function showRate(){ spdv.textContent = rate().toLocaleString() + " cycles/s"; }
spd.oninput = showRate; showRate();
function step(k){ const target = Math.min(N, frame + k);
  while (frame < target){ applyFrame(frame); const op=D.memop[frame]; if (op) touch(D.memaddr[frame], op);
    const w = writesAt.get(frame); if (w) for (const [a] of w) touch(a,2); frame++; } }
function tick(ts){ if (!playing) return; if (!last) last = ts; acc += (ts-last)/1000*rate(); last = ts;
  const k = Math.floor(acc); if (k>0){ acc -= k; step(k); render(); }
  if (frame >= N){ playing=false; document.getElementById("bp").innerHTML="&#9654; run"; return; }
  requestAnimationFrame(tick); }
document.getElementById("bp").onclick = ()=>{ playing=!playing; last=0; acc=0;
  document.getElementById("bp").innerHTML = playing ? "&#10074;&#10074; pause" : "&#9654; run"; if (playing) requestAnimationFrame(tick); };
document.getElementById("bs").onclick = ()=>{ step(1); render(); };
document.getElementById("bi").onclick = ()=>{ step(1); while (frame<N && D.upc[frame]!==D.fetch) step(1); render(); };
document.getElementById("bb").onclick = ()=>{ seek(frame-1); render(); };
document.getElementById("b0").onclick = ()=>{ seek(0); render(); };
scrub.oninput = ()=>{ seek(+scrub.value); render(); };
seek(0); render();
</script></body></html>
"""
