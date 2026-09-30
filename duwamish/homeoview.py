"""Ashby's homeostat, animated.

programs/ashby/homeostat.sal keeps its machine in core: the needles x[4],
the connection matrix a[16], and each unit's uniselector position pos[4]
into its table uni[] of 3-trit words.  record_homeostat() runs the
program's own parts 1 to 3 -- switched on, disturbed, a connection
reversed -- under a driver of its own, and reads the machine after every
step of its integration (the step counter t).  The recorder, as an
observer, also applies the Routh-Hurwitz test to each field, as the
program does; the homeostat itself never knows.

The page shows four meters with their bounds, each unit's relay (its
critical trit) and uniselector (three trit lamps: the signs of the unit's
three input connections), and a strip chart of all four needles, with a
tick wherever a uniselector moved.
"""

import itertools
import json
import os

from . import machine as mach
from . import panel
from . import satellite
from . import ternary as t

HERE = os.path.dirname(__file__)
HOMEOSTAT = os.path.join(HERE, "..", "programs", "ashby", "homeostat.sal")
S = 6561                     # 1.0 in the program's fixed point

DRIVER = """
proc main()
begin
  build()
  part1()
  part2()
  part3()
  part := 9
  return 0
end
"""


def _det(m):
    if len(m) == 1:
        return m[0][0]
    return sum((-1) ** c * m[0][c] * _det([r[:c] + r[c + 1:] for r in m[1:]])
               for c in range(len(m)))


def stable(a):
    """Routh-Hurwitz for the 4 x 4 matrix a (a list of 16)."""
    A = [a[4 * i:4 * i + 4] for i in range(4)]

    def minor(idx):
        return _det([[A[r][c] for c in idx] for r in idx])
    c1 = -sum(A[i][i] for i in range(4))
    c2 = sum(minor(p) for p in itertools.combinations(range(4), 2))
    c3 = -sum(minor(p) for p in itertools.combinations(range(4), 3))
    c4 = _det(A)
    return (c1 > 0 and c2 > 0 and c3 > 0 and c4 > 0 and c1 * c2 > c3
            and c1 * c2 * c3 > c3 * c3 + c1 * c1 * c4)


class HomeostatRecording:
    def __init__(self):
        # per step: [t, part, x1..x4, pos1..4, word1..4, moved1..4, stable]
        self.frames = []
        self.reversed = None         # (into, from), units counted from 1
        self.output = ""


def record_homeostat(chunk=40, max_instructions=20_000_000):
    with open(HOMEOSTAT) as f:
        src = f.read()
    src = src.replace("proc main()", "proc demo_main()") + DRIVER
    deck = "//JOB HOMEOSTAT\n//SALISH OPT\n" + src + "\n//EXEC\n"
    sat = satellite.Satellite([(deck, HOMEOSTAT)], model=90,
                              out=lambda s: None)
    job = sat.jobs[0]
    if job.failed:
        raise RuntimeError("\n".join(job.log))
    sy = job.steps[0].obj.symbols
    off = mach.MEM_OFF
    at = {k: sy[k] + off for k in ("G_t", "G_part", "G_reversed_i",
                                   "G_reversed_j", "V_x", "V_a", "V_pos",
                                   "V_uni", "V_moved")}
    m = mach.Machine(model=90, satellite=sat)
    sat.machine = m
    ex = satellite.assemble_executive()
    m.load_image(ex.image())
    m.pc = ex.entry
    mem = m.mem
    rec = HomeostatRecording()
    last_t = None
    total = 0
    started = False
    while not m.halted and total < max_instructions:
        m.run(max_instructions=chunk)
        total += chunk
        if sat.cur is None:
            if started:
                break
            continue
        started = True
        part = mem[at["G_part"]]
        if part == 9:
            break
        tt = mem[at["G_t"]]
        # t = 0 is before the needles are pushed off centre
        if part == 0 or tt == 0 or tt == last_t:
            continue
        if last_t is not None and tt != last_t + 1:
            raise RuntimeError("a step was missed: use a smaller chunk")
        last_t = tt
        x = [mem[at["V_x"] + i] for i in range(4)]
        a = [mem[at["V_a"] + i] for i in range(16)]
        pos = [mem[at["V_pos"] + i] for i in range(4)]
        words = [mem[at["V_uni"] + 27 * i + pos[i]] for i in range(4)]
        moved = [1 if mem[at["V_moved"] + i] > 0 else 0 for i in range(4)]
        rec.frames.append([tt, part] + [round(v / S, 4) for v in x] + pos
                          + ["".join("+" if t.trit_at(w, k) > 0 else
                                     "-" if t.trit_at(w, k) < 0 else "0"
                                     for k in range(3)) for w in words]
                          + moved + [1 if stable(a) else 0])
        ri = mem[at["G_reversed_i"]]
        if ri >= 0:
            rec.reversed = (ri + 1, mem[at["G_reversed_j"]] + 1)
    step = job.steps[0]
    rec.output = m.text(m.printer[getattr(step, "out_start", 0):])
    return rec


_PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>Homeostat</title>
<style>
:root{--bg:#15171a;--panel:#1d2024;--edge:#33373e;--ink:#e8e2cc;--dim:#a9a18a;
 --amber:#ffb238;--blue:#4fc3ff;--green:#7ee787}
body{margin:0;background:var(--bg);color:var(--ink);
 font:12px 'DejaVu Sans Mono',Menlo,Consolas,monospace}
.top{display:flex;align-items:center;gap:10px;padding:8px 12px;flex-wrap:wrap;
 background:#101214;border-bottom:1px solid var(--edge)}
.top h1{font-size:14px;margin:0 12px 0 0;color:var(--amber);letter-spacing:2px}
button{background:#2b2f35;color:var(--ink);border:1px solid #444;border-radius:4px;
 padding:4px 9px;font:inherit;cursor:pointer}
.row{display:flex;flex-wrap:wrap}
.box{background:var(--panel);border:1px solid var(--edge);border-radius:6px;
 padding:6px 8px;margin:6px}
.box h2{font-size:11px;color:var(--dim);margin:0 0 6px 0;font-weight:normal;
 letter-spacing:1px;text-transform:uppercase}
canvas{display:block}
#units{display:grid;grid-template-columns:repeat(4,minmax(0,1fr))}
#units canvas{margin:0 auto}
#units .cap{font-size:11px;white-space:nowrap}
.lamp{display:inline-block;width:11px;height:11px;border-radius:50%;margin:0 2px;
 border:1px solid #444;vertical-align:-3px}
.cap{color:var(--dim);margin-top:5px}
.cap b{font-weight:normal;color:var(--amber)}
#status{padding:4px 12px;color:var(--dim)}
#status b{font-weight:normal;color:var(--amber)}
</style></head><body>
<div class="top">
 <h1>ASHBY'S HOMEOSTAT</h1>
 <button id="b0">&#9198;</button><button id="bp">&#9654; run</button>
 <span style="color:var(--dim)">speed</span>
 <input id="spd" type="range" min="1" max="12" value="3" style="width:100px">
 <input id="scrub" type="range" min="0" max="1" value="0" style="flex:1;min-width:160px">
</div>
<div id="status"></div>
<div id="units"></div>
<div class="box"><h2>the four needles against time -- a tick where a uniselector moved</h2>
 <canvas id="chart" height="220" style="width:100%"></canvas></div>
<div class="cap" style="margin:0 10px 10px">Each meter's needle is an essential
variable; the dashed marks are its bounds. The relay lamp is the unit's critical
trit: amber above the bound, blue below, dark within. The three lamps under it are
the uniselector: the signs of the connections into the unit from the other three
(amber +1, blue &minus;1, dark 0) -- one of 27 positions. The field's stability is
the observer's verdict (Routh&ndash;Hurwitz); the homeostat knows only its needles.</div>
<script>
const D = __DATA__, F = D.frames.length;
const UC = ["#ffb238", "#4fc3ff", "#7ee787", "#c678dd"];
const PART = {1: "1. switched on: hunting", 2: "2. a disturbance: needle 1 pushed aside",
              3: "3. a connection reversed by hand"};
const units = document.getElementById("units"), meters = [], caps = [];
for (let i = 0; i < 4; i++){
  const box = document.createElement("div"); box.className = "box";
  box.innerHTML = `<h2 style="color:${UC[i]}">unit ${i + 1}</h2>`;
  const c = document.createElement("canvas"); c.width = 170; c.height = 96;
  box.appendChild(c);
  const cap = document.createElement("div"); cap.className = "cap"; box.appendChild(cap);
  units.appendChild(box); meters.push(c.getContext("2d")); caps.push(cap);
}
function lamp(v){ const col = v > 0 ? "#ffb238" : v < 0 ? "#4fc3ff" : "#0b0c0e";
  return `<span class="lamp" style="background:${col}"></span>`; }
function meter(g, x, col, crit){
  const W = 170, H = 96, cx = W / 2, cy = H - 10, r = 72;
  g.fillStyle = "#15171a"; g.fillRect(0, 0, W, H);
  g.strokeStyle = "#3a3f46"; g.lineWidth = 2;
  g.beginPath(); g.arc(cx, cy, r, Math.PI, 2 * Math.PI); g.stroke();
  const ang = v => Math.PI + (v + 2) / 4 * Math.PI;
  g.setLineDash([4, 3]); g.strokeStyle = "#a9a18a";
  for (const b of [-1, 1]){ const a = ang(b);
    g.beginPath(); g.moveTo(cx + (r - 14) * Math.cos(a), cy + (r - 14) * Math.sin(a));
    g.lineTo(cx + (r + 6) * Math.cos(a), cy + (r + 6) * Math.sin(a)); g.stroke(); }
  g.setLineDash([]);
  const a = ang(Math.max(-2, Math.min(2, x)));
  g.strokeStyle = crit ? "#ff5f56" : col; g.lineWidth = 3;
  g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + (r - 4) * Math.cos(a), cy + (r - 4) * Math.sin(a)); g.stroke();
  g.fillStyle = "#e8e2cc"; g.beginPath(); g.arc(cx, cy, 4, 0, 2 * Math.PI); g.fill();
}
const chart = document.getElementById("chart"), cg = chart.getContext("2d");
const moves = new Array(F).fill(0);
for (let f = 0, n = 0; f < F; f++){ const r = D.frames[f];
  n += r[14] + r[15] + r[16] + r[17]; moves[f] = n; }
function drawChart(frame){
  chart.width = chart.clientWidth || 900;
  const W = chart.width, H = chart.height, X = f => f / (F - 1) * (W - 1);
  const Y = v => H / 2 - v / 2.2 * (H / 2 - 6);
  cg.fillStyle = "#1d2024"; cg.fillRect(0, 0, W, H);
  for (let f = 1; f < F; f++){                 // shade by part
    const p = D.frames[f][1];
    cg.fillStyle = p == 2 ? "#1c2a22" : p == 3 ? "#2a2020" : "#1d2024";
    cg.fillRect(X(f - 1), 0, X(f) - X(f - 1) + 1, H);
  }
  cg.setLineDash([4, 3]); cg.strokeStyle = "#555a60";
  for (const b of [-1, 1]){ cg.beginPath(); cg.moveTo(0, Y(b)); cg.lineTo(W, Y(b)); cg.stroke(); }
  cg.setLineDash([]);
  for (let i = 0; i < 4; i++){
    cg.strokeStyle = UC[i]; cg.lineWidth = 1.2; cg.beginPath();
    for (let f = 0; f < F; f++){ const y = Y(D.frames[f][2 + i]);
      if (f) cg.lineTo(X(f), y); else cg.moveTo(X(f), y); }
    cg.stroke();
    for (let f = 0; f < F; f++) if (D.frames[f][14 + i]){
      cg.fillStyle = UC[i]; cg.fillRect(X(f) - 1, H - 10 - 2 * i, 3, 8); }
  }
  cg.fillStyle = "#a9a18a"; cg.font = "11px monospace";
  for (let f = 0, p = 0; f < F; f++) if (D.frames[f][1] != p){
    p = D.frames[f][1];
    cg.fillText({1: "1 switched on", 2: "2 disturbed", 3: "3 reversed"}[p] || "",
                X(f) + 4, p == 2 ? 26 : 12);
  }
  cg.strokeStyle = "#e8e2cc"; cg.beginPath(); cg.moveTo(X(frame), 0); cg.lineTo(X(frame), H); cg.stroke();
}
let frame = 0, playing = false;
function show(){
  const r = D.frames[frame];
  for (let i = 0; i < 4; i++){
    const x = r[2 + i], crit = x > 1 ? 1 : x < -1 ? -1 : 0;
    meter(meters[i], x, UC[i], crit);
    const w = r[10 + i];
    caps[i].innerHTML = `relay ${lamp(crit)} &nbsp;switch ` +
      [...w].map(ch => lamp(ch == "+" ? 1 : ch == "-" ? -1 : 0)).join("") +
      ` <b>${r[6 + i] + 1}</b>/27`;
  }
  let note = PART[r[1]] || "";
  if (r[1] == 3 && D.reversed) note += ` (from unit ${D.reversed[1]} into unit ${D.reversed[0]})`;
  document.getElementById("status").innerHTML =
    `time <b>${(r[0] / 27).toFixed(1)}</b> &nbsp; <b>${note}</b> &nbsp; ` +
    `uniselector moves so far <b>${moves[frame]}</b> &nbsp; the field is ` +
    (r[18] ? `<b style="color:#7ee787">stable</b>` : `<b style="color:#ff5f56">unstable</b>`);
  document.getElementById("scrub").value = frame; drawChart(frame);
}
const scrub = document.getElementById("scrub"); scrub.max = F - 1;
scrub.oninput = () => { frame = +scrub.value; show(); };
document.getElementById("b0").onclick = () => { playing = false; frame = 0; show(); };
const bp = document.getElementById("bp"), spd = document.getElementById("spd");
bp.onclick = () => { playing = !playing; bp.innerHTML = playing ? "&#10074;&#10074; pause" : "&#9654; run"; };
setInterval(() => {
  if (!playing) return;
  if (frame >= F - 1){ playing = false; bp.innerHTML = "&#9654; run"; return; }
  frame = Math.min(F - 1, frame + +spd.value); show();
}, 50);
show();
</script></body></html>
"""


def page_html(rec):
    data = {"frames": rec.frames, "reversed": rec.reversed}
    return _PAGE.replace("__DATA__", json.dumps(data, separators=(",", ":")))


def animate(rec, height=640):
    return panel._display(panel._iframe(page_html(rec), height))


def save_html(rec, path):
    with open(path, "w") as f:
        f.write(page_html(rec))
    return path
