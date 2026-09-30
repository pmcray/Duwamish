"""Conway's Life in Kleene's logic, animated.

programs/knuth/life.sal keeps its world in core, one word to a row of 27
cells: +1 alive, -1 dead, 0 unknown.  record_life() compiles it with a
driver of its own in place of its main: the program's setup_partial() and
setup_outside() build the worlds, its generation() runs them, and its
check() runs every world the unknown cells could stand for, leaving in
`agree` the cells that come out the same in all of them -- the truth.
After each generation the driver copies both into a buffer and counts a
frame; the recorder reads them straight out of core.

The pages show, generation by generation:

  scene 1  a world partly unseen: what Kleene's logic says, beside the
           truth.  Kleene is sound -- it never contradicts the truth --
           but it is far from complete.
  scene 2  the world beyond the edge unknown: ignorance comes in at one
           cell a generation.

Lamps as on the front panel: amber +1 (alive), blue -1 (dead), dark 0
(unknown).
"""

import json
import os

from . import machine as mach
from . import panel
from . import satellite
from . import ternary as t

HERE = os.path.dirname(__file__)
LIFE = os.path.join(HERE, "..", "programs", "knuth", "life.sal")
N = 27

DRIVER = """
global rec_frame := 0, rec_scene := 0, rec_gen := 0
global rec_k[29], rec_t[29]

proc rec_snap(scene, gen, truth)
begin
  for r := 1 to N do begin
    rec_k[r] := g[r]
    rec_t[r] := truth -> agree[r], g[r]
  end
  rec_scene := scene
  rec_gen := gen
  rec_frame := rec_frame + 1
end

proc main()
begin
  setup_partial()
  for r := 1 to N do agree[r] := start[r]
  rec_snap(1, 0, true)
  for gen := 1 to 16 do begin
    generation()
    check(gen)
    rec_snap(1, gen, true)
  end
  setup_outside()
  rec_snap(2, 0, false)
  for gen := 1 to 14 do begin
    generation()
    rec_snap(2, gen, false)
  end
  return 0
end
"""


class LifeRecording:
    def __init__(self):
        self.frames = {1: [], 2: []}     # scene -> [(gen, kleene, truth)]


def _row(word):
    return "".join("a" if t.trit_at(word, c) > 0 else
                   "d" if t.trit_at(word, c) < 0 else "u" for c in range(N))


def record_life(chunk=400, max_instructions=60_000_000):
    """Run the program's own procedures under a recording driver."""
    with open(LIFE) as f:
        src = f.read()
    src = src.replace("proc main()", "proc demo_main()") + DRIVER
    deck = "//JOB LIFE\n//SALISH OPT\n" + src + "\n//EXEC\n"
    sat = satellite.Satellite([(deck, LIFE)], model=90, out=lambda s: None)
    job = sat.jobs[0]
    if job.failed:
        raise RuntimeError("\n".join(job.log))
    sy = job.steps[0].obj.symbols
    off = mach.MEM_OFF
    frame_at, scene_at, gen_at = (sy[k] + off for k in
                                  ("G_rec_frame", "G_rec_scene", "G_rec_gen"))
    k_at, t_at = sy["V_rec_k"] + off, sy["V_rec_t"] + off
    m = mach.Machine(model=90, satellite=sat)
    sat.machine = m
    ex = satellite.assemble_executive()
    m.load_image(ex.image())
    m.pc = ex.entry
    mem = m.mem
    rec = LifeRecording()
    seen = 0
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
        n = mem[frame_at]
        if n == seen:
            continue
        if n != seen + 1:
            raise RuntimeError("a frame was missed: use a smaller chunk")
        seen = n
        kle = "".join(_row(mem[k_at + r]) for r in range(1, N + 1))
        tru = "".join(_row(mem[t_at + r]) for r in range(1, N + 1))
        rec.frames[mem[scene_at]].append((mem[gen_at], kle, tru))
    return rec


_PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>Kleene Life</title>
<style>
:root{--bg:#15171a;--panel:#1d2024;--edge:#33373e;--ink:#e8e2cc;--dim:#a9a18a;
 --amber:#ffb238;--blue:#4fc3ff}
body{margin:0;background:var(--bg);color:var(--ink);
 font:12px 'DejaVu Sans Mono',Menlo,Consolas,monospace}
.top{display:flex;align-items:center;gap:10px;padding:8px 12px;flex-wrap:wrap;
 background:#101214;border-bottom:1px solid var(--edge)}
.top h1{font-size:14px;margin:0 12px 0 0;color:var(--amber);letter-spacing:2px}
button{background:#2b2f35;color:var(--ink);border:1px solid #444;border-radius:4px;
 padding:4px 9px;font:inherit;cursor:pointer}
.row{display:flex;flex-wrap:wrap}
.box{background:var(--panel);border:1px solid var(--edge);border-radius:6px;
 padding:8px 10px;margin:10px}
.box h2{font-size:11px;color:var(--dim);margin:0 0 6px 0;font-weight:normal;
 letter-spacing:1px;text-transform:uppercase}
canvas{display:block}
.key{display:inline-block;width:10px;height:10px;margin:0 4px 0 12px;vertical-align:-1px}
.stat b{font-weight:normal;color:var(--amber)}
#note{color:var(--dim);margin:0 10px 10px 10px;max-width:760px}
</style></head><body>
<div class="top">
 <h1>__TITLE__</h1>
 <button id="b0">&#9198;</button><button id="bb">&#9664;</button>
 <button id="bp">&#9654; run</button><button id="bf">&#9654;|</button>
 <span id="gen" style="color:var(--amber);min-width:120px"></span>
 <input id="scrub" type="range" min="0" max="1" value="0" style="flex:1;min-width:160px">
</div>
<div class="row" id="panels"></div>
<div style="margin:0 10px;color:var(--dim)">
 <span class="key" style="background:#ffb238"></span>alive (+1)
 <span class="key" style="background:#1f4a63"></span>dead (&minus;1)
 <span class="key" style="background:#0b0c0e;border:1px solid #3a3f46"></span>unknown (0)
 <span class="key" style="background:#ff5f56"></span>Kleene contradicts the truth (never happens)
</div>
<div id="note">__NOTE__</div>
<script>
const D = __DATA__, S = 13, N = 27, F = D.frames.length;
const panels = document.getElementById("panels"), ctx = [], stats = [];
D.labels.forEach((lab, k) => {
  const box = document.createElement("div"); box.className = "box";
  box.innerHTML = `<h2>${lab}</h2>`;
  const c = document.createElement("canvas"); c.width = N * S; c.height = N * S;
  box.appendChild(c);
  const st = document.createElement("div"); st.className = "stat"; st.style.marginTop = "6px";
  box.appendChild(st); panels.appendChild(box);
  ctx.push(c.getContext("2d")); stats.push(st);
});
const COL = {a: "#ffb238", d: "#1f4a63", u: "#0b0c0e"};
let frame = 0, playing = false;
function draw(){
  const f = D.frames[frame];
  document.getElementById("gen").textContent = "generation " + f[0];
  f.slice(1).forEach((grid, k) => {
    const g = ctx[k], counts = {a: 0, d: 0, u: 0};
    for (let i = 0; i < N * N; i++){
      let ch = grid[i]; counts[ch]++;
      const x = (i % N) * S, y = Math.floor(i / N) * S;
      g.fillStyle = COL[ch];
      if (k == 0 && f.length > 2 && ch != "u" && f[2][i] != "u" && f[2][i] != ch)
        g.fillStyle = "#ff5f56";
      g.fillRect(x, y, S - 1, S - 1);
      if (ch == "u"){ g.fillStyle = "#2a2e34"; g.fillRect(x + 5, y + 5, 2, 2); }
    }
    stats[k].innerHTML = `alive <b>${counts.a}</b> &nbsp; dead <b>${counts.d}</b>` +
      ` &nbsp; unknown <b>${counts.u}</b>`;
  });
  document.getElementById("scrub").value = frame;
}
const scrub = document.getElementById("scrub"); scrub.max = F - 1;
scrub.oninput = () => { frame = +scrub.value; draw(); };
document.getElementById("b0").onclick = () => { playing = false; frame = 0; draw(); };
document.getElementById("bb").onclick = () => { if (frame > 0) frame--; draw(); };
document.getElementById("bf").onclick = () => { if (frame < F - 1) frame++; draw(); };
const bp = document.getElementById("bp");
bp.onclick = () => { playing = !playing; bp.innerHTML = playing ? "&#10074;&#10074; pause" : "&#9654; run"; };
setInterval(() => {
  if (!playing) return;
  if (frame >= F - 1){ playing = false; bp.innerHTML = "&#9654; run"; return; }
  frame++; draw();
}, 600);
draw();
</script></body></html>
"""

_SCENES = {
    1: ("KLEENE LIFE: A WORLD PARTLY UNSEEN",
        ["what Kleene's logic says", "the truth: all 16 worlds run"],
        "Four cells begin unknown (dark). On the left, one generation at a "
        "time, is what the tritwise AND, OR and EQV can say about the world; "
        "on the right, the truth -- the machine has run every one of the 16 "
        "worlds the unknown cells could stand for, and a cell is known if it "
        "comes out the same in all of them. The left never contradicts the "
        "right (such a cell would show red): Kleene's logic is sound. But it "
        "loses far more than the facts require: it cannot see that x or "
        "not-x is true when x is unknown."),
    2: ("KLEENE LIFE: THE WORLD BEYOND UNKNOWN",
        ["what Kleene's logic says"],
        "Here everything beyond the edge of the 27 x 27 world is unknown. "
        "Ignorance comes in from every side at one cell a generation -- the "
        "speed of light, as Conway called it -- until nothing can be said."),
}


def page_html(rec, scene=1):
    title, labels, note = _SCENES[scene]
    frames = [[g, k, tr] if scene == 1 else [g, k]
              for g, k, tr in rec.frames[scene]]
    data = {"labels": labels, "frames": frames}
    return (_PAGE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
            .replace("__TITLE__", title).replace("__NOTE__", note))


def animate(rec, scene=1, height=520):
    """Show one scene in a notebook cell."""
    return panel._display(panel._iframe(page_html(rec, scene), height))


def save_html(rec, path, scene=1):
    with open(path, "w") as f:
        f.write(page_html(rec, scene))
    return path
