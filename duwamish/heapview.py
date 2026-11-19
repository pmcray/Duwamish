"""TRILISP's memory, made visible.

TRILISP (duwamish/lib/trilisp.sal) keeps its list cells in three vectors
in core -- car_, cdr_ and mark_ -- with the free cells chained through
cdr_ from `freelist`.  When the free list runs out, cons calls the
collector: it marks every cell reachable from the symbols and from any
word on the machine stack that looks like a pointer (a conservative
collector), then sweeps the heap from the top down, clearing the marks
and chaining every unmarked cell back onto the free list.

record_heap() runs a TRILISP job on the Model 90, a few hundred
instructions at a time, and after each slice reads the heap straight out
of core: which cells are free, which are in use, which are marked.  The
recording is replayed on an animated page: cells light as they are
allocated, turn green as the collector marks them, and go dark again as
the sweep reclaims them.  A smaller heap than TRILISP's usual 30,000
cells is used, so that the collections come often enough to watch.
"""

import json
import os

from . import isa
from . import machine as mach
from . import panel
from . import satellite

TRILISP = os.path.join(os.path.dirname(__file__), "lib", "trilisp.sal")

FREE, USED, MARKED = 0, 1, 2

WORKLOAD = """
(DEFINE BUILD (LAMBDA (N) (COND ((EQ N 0) NIL) (T (CONS N (BUILD (- N 1)))))))
(DEFINE KEPT NIL)
(DEFINE CHURN (LAMBDA (K)
  (COND ((EQ K 0) (LENGTH KEPT))
        (T (PROGN (SETQ KEPT (CONS (BUILD 8) KEPT))
                  (BUILD 120)
                  (CHURN (- K 1)))))))
(CHURN 14)
"""


class HeapRecording:
    def __init__(self, heap):
        self.heap = heap
        self.frames = []        # [instructions, [cell, state, cell, state...]]
        self.keyframes = {}     # frame number -> state of every cell
        self.stats = []         # per frame: [free, used, marked, gcs, conses, phase]
        self.output = ""


def record_heap(lisp=WORKLOAD, heap=2187, quiet=3000, busy=700,
                max_instructions=40_000_000):
    """Run TRILISP (with a heap of `heap` cells) on the cards `lisp`,
    sampling the heap every `quiet` instructions, or every `busy` while
    the collector is running."""
    with open(TRILISP) as f:
        src = f.read()
    src = src.replace("const HEAP = 30000,", f"const HEAP = {heap},")
    deck = ("//JOB HEAP\n//SALISH\n" + src + "\n//EXEC\n//DATA\n"
            + lisp.strip() + "\n")
    sat = satellite.Satellite([(deck, TRILISP)], model=90, out=lambda s: None)
    job = sat.jobs[0]
    if job.failed:
        raise RuntimeError("\n".join(job.log))
    obj = job.steps[0].obj
    sy = obj.symbols
    car, cdr, mark = sy["V_car_"], sy["V_cdr_"], sy["V_mark_"]
    g_free, g_ngc, g_cons = sy["G_freelist"], sy["G_ngc"], sy["G_nconses"]
    procs = sorted(v for k, v in sy.items() if k.startswith("P_"))

    def extent(name):
        a = sy[name]
        later = [p for p in procs if p > a]
        return a, (later[0] if later else obj.end)
    gc_lo, gc_hi = extent("P_gc")
    mk_lo, mk_hi = extent("P_markval")

    m = mach.Machine(model=90, satellite=sat)
    sat.machine = m
    ex = satellite.assemble_executive()
    m.load_image(ex.image())
    m.pc = ex.entry
    mem = m.mem
    off = mach.MEM_OFF
    rec = HeapRecording(heap)
    prev = [FREE] * heap
    started = False
    nframe = 0
    total = 0
    while not m.halted and total < max_instructions:
        pc = m.pc
        in_gc = gc_lo <= pc < gc_hi or mk_lo <= pc < mk_hi
        step = busy if in_gc else quiet
        m.run(max_instructions=step)
        total += step
        if sat.cur is None:
            if started:
                break                  # the job has ended
            continue
        started = True
        marks = mem[mark + off: mark + off + heap]
        free = set()
        f = mem[g_free + off]
        n = 0
        while f and n < heap:
            free.add(f)
            f = mem[cdr + off + f]
            n += 1
        cur = [FREE] * heap
        for i in range(1, heap):
            if marks[i] == 1:
                cur[i] = MARKED
            elif i not in free:
                cur[i] = USED
        delta = []
        for i in range(heap):
            if cur[i] != prev[i]:
                delta += [i, cur[i]]
        if not delta and nframe:
            continue
        if nframe % 200 == 0:
            rec.keyframes[nframe] = "".join(str(x) for x in cur)
        # the collector runs only when the free list is empty, so while
        # it marks the list's head is 0; once the sweep begins it is not
        pc = m.pc
        in_gc = gc_lo <= pc < gc_hi or mk_lo <= pc < mk_hi
        phase = ("running" if not in_gc else
                 "collecting: marking" if mem[g_free + off] == 0 else
                 "collecting: sweeping")
        rec.frames.append([total, delta])
        rec.stats.append([cur.count(FREE), cur.count(USED), cur.count(MARKED),
                          mem[g_ngc + off], mem[g_cons + off], phase])
        prev = cur
        nframe += 1
    step = job.steps[0]
    rec.output = m.text(m.printer[getattr(step, "out_start", 0):])
    return rec


_PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>TRILISP heap</title>
<style>
:root{--bg:#15171a;--panel:#1d2024;--edge:#33373e;--ink:#e8e2cc;--dim:#a9a18a;
 --amber:#ffb238;--green:#7ee787;--blue:#4fc3ff}
body{margin:0;background:var(--bg);color:var(--ink);
 font:12px 'DejaVu Sans Mono',Menlo,Consolas,monospace}
.top{display:flex;align-items:center;gap:10px;padding:8px 12px;flex-wrap:wrap;
 background:#101214;border-bottom:1px solid var(--edge)}
.top h1{font-size:14px;margin:0 12px 0 0;color:var(--amber);letter-spacing:2px}
button{background:#2b2f35;color:var(--ink);border:1px solid #444;border-radius:4px;
 padding:4px 9px;font:inherit;cursor:pointer}
.box{background:var(--panel);border:1px solid var(--edge);border-radius:6px;
 padding:8px 10px;margin:10px}
.box h2{font-size:11px;color:var(--dim);margin:0 0 6px 0;font-weight:normal;
 letter-spacing:1px;text-transform:uppercase}
canvas{display:block;image-rendering:pixelated;max-width:100%}
.key{display:inline-block;width:10px;height:10px;margin:0 4px 0 12px;vertical-align:-1px}
#stats b{font-weight:normal;color:var(--amber)}
</style></head><body>
<div class="top">
 <h1>TRILISP HEAP</h1>
 <button id="b0">&#9198;</button><button id="bp">&#9654; run</button>
 <span style="color:var(--dim)">speed</span>
 <input id="spd" type="range" min="1" max="60" value="12" style="width:110px">
 <input id="scrub" type="range" min="0" max="1" value="0" style="flex:1;min-width:160px">
</div>
<div class="box"><h2>the cons cells -- one square each</h2>
 <canvas id="grid"></canvas>
 <div style="margin-top:6px;color:var(--dim)">
  <span class="key" style="background:#2b2f35"></span>free
  <span class="key" style="background:#ffb238"></span>in use
  <span class="key" style="background:#7ee787"></span>marked by the collector
 </div>
 <div id="stats" style="margin-top:6px"></div>
</div>
<div class="box"><h2>cells in use, against instructions executed -- each drop is a collection</h2>
 <canvas id="spark" height="90" style="width:100%"></canvas></div>
<script>
const D = __DATA__;
const H = D.heap, N = D.frames.length, COLS = D.cols, ROWS = Math.ceil(H / COLS), S = D.cell;
const grid = document.getElementById("grid"), g = grid.getContext("2d");
grid.width = COLS * S; grid.height = ROWS * S;
const COL = ["#2b2f35", "#ffb238", "#7ee787"];
let state = new Array(H).fill(0), frame = 0, playing = false;
function paint(i){ g.fillStyle = COL[state[i]]; g.fillRect((i % COLS) * S, Math.floor(i / COLS) * S, S - 1, S - 1); }
function paintAll(){ for (let i = 0; i < H; i++) paint(i); }
function apply(f){ const d = D.frames[f][1]; for (let k = 0; k < d.length; k += 2){ state[d[k]] = d[k + 1]; paint(d[k]); } }
function seek(f){
  f = Math.max(0, Math.min(N - 1, f));
  if (f < frame || f - frame > 400){
    let k = 0; for (const key in D.keys){ if (+key <= f && +key > k) k = +key; }
    const s = D.keys[k]; for (let i = 0; i < H; i++) state[i] = +s[i];
    paintAll(); frame = k;
    for (let j = k + 1; j <= f; j++) apply(j);
  } else for (let j = frame + 1; j <= f; j++) apply(j);
  frame = f; show();
}
const spark = document.getElementById("spark"), sp = spark.getContext("2d");
function sparkDraw(){
  spark.width = spark.clientWidth || 800;
  const W = spark.width, Hh = spark.height;
  sp.fillStyle = "#1d2024"; sp.fillRect(0, 0, W, Hh);
  const T = D.frames[N - 1][0];
  const X = f => D.frames[f][0] / T * (W - 1);
  sp.strokeStyle = "#ffb238"; sp.beginPath();
  for (let f = 0; f < N; f++){
    const x = X(f), used = D.stats[f][1] + D.stats[f][2];
    const y = Hh - 4 - used / H * (Hh - 8);
    if (f) sp.lineTo(x, y); else sp.moveTo(x, y);
  }
  sp.stroke();
  const x = X(frame);
  sp.strokeStyle = "#4fc3ff"; sp.beginPath(); sp.moveTo(x, 0); sp.lineTo(x, Hh); sp.stroke();
}
const statsEl = document.getElementById("stats"), scrub = document.getElementById("scrub");
scrub.max = N - 1;
function show(){
  const s = D.stats[frame];
  statsEl.innerHTML = `instruction <b>${D.frames[frame][0].toLocaleString()}</b> &nbsp; ` +
    `free <b>${s[0]}</b> &nbsp; in use <b>${s[1]}</b> &nbsp; marked <b>${s[2]}</b> &nbsp; ` +
    `conses <b>${s[4].toLocaleString()}</b> &nbsp; collections <b>${s[3]}</b> &nbsp; <b>${s[5]}</b>`;
  scrub.value = frame; sparkDraw();
}
document.getElementById("b0").onclick = () => { playing = false; seek(0); };
const bp = document.getElementById("bp");
bp.onclick = () => { playing = !playing; bp.innerHTML = playing ? "&#10074;&#10074; pause" : "&#9654; run"; };
scrub.oninput = () => seek(+scrub.value);
const spd = document.getElementById("spd");
function tick(){
  if (playing){
    if (frame >= N - 1) { playing = false; bp.innerHTML = "&#9654; run"; }
    else seek(frame + +spd.value > N - 1 ? N - 1 : frame + Math.ceil(+spd.value / 4));
  }
  setTimeout(tick, 40);
}
seek(0); paintAll(); show(); tick();
</script></body></html>
"""


def page_html(rec, cols=81, cell=7):
    data = {"heap": rec.heap, "cols": cols, "cell": cell,
            "frames": rec.frames, "stats": rec.stats,
            "keys": {str(k): v for k, v in rec.keyframes.items()}}
    return _PAGE.replace("__DATA__", json.dumps(data, separators=(",", ":")))


def animate(rec, height=560):
    """Show the heap animation in a notebook cell."""
    return panel._display(panel._iframe(page_html(rec), height))


def save_html(rec, path):
    with open(path, "w") as f:
        f.write(page_html(rec))
