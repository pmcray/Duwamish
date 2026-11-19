"""Pask's SAKI, animated.

programs/pask/saki.sal teaches a simulated trainee the ten numeric keys.
After every item, its teach() leaves in core the key, the delay before its
light, the trainee's answer (a trit) and the time of the answer, and then
counts the item.  record_saki() runs the program's own procedures under a
driver of its own -- one trainee, one machine -- and reads the machine
after every item: the item, SAKI's delay for each key (its model of the
trainee), and, as an observer that SAKI is not, the trainee's hidden
memory of each key and attention.  At the end the driver tests the
trainee with no lights.

The page shows the keyboard as a card punch's numeric keys, each with its
light: bright when it comes on at once, dark when it is held back.  The
key being asked is ringed and lit by the answer -- amber +1 found from
memory, grey 0 found by the light, blue -1 the wrong key.  Under each key
two bars set SAKI's model beside the trainee's memory.  A strip chart
follows the lesson: attention, the trainee's mean memory, and the share
of the last 50 answers found from memory and found wrongly.  Two runs can
be set side by side, item for item.
"""

import json
import os

from . import machine as mach
from . import panel
from . import satellite

HERE = os.path.dirname(__file__)
SAKI_SRC = os.path.join(HERE, "..", "programs", "pask", "saki.sal")
NK = 10
MACHINES = {"ALWAYS": 0, "FIXED": 1, "SAKI": 2}
KINDS = {700: "a slow trainee", 1000: "an average trainee",
         1500: "a fast trainee"}

DRIVER = """
global rec_done := 0

proc main()
begin
  seed := %(seed)d
  new_trainee(%(rate)d)
  teach(%(machine)d)
  test(100)
  rec_done := 1
  return 0
end
"""


class SakiRecording:
    def __init__(self, machine, rate):
        self.machine = machine
        self.rate = rate
        # per item: [n, key, delay, answer, time, attention,
        #            delay0..9, memory0..9, mastered0..9]
        self.frames = []
        self.tested = None            # (keys found of 100, mean time)

    @property
    def label(self):
        name = {"ALWAYS": "ALWAYS LIT", "FIXED": "FIXED", "SAKI": "SAKI"}
        return (f"{name[self.machine]}: "
                f"{KINDS.get(self.rate, f'learning rate {self.rate}')}")


def record_saki(machine="SAKI", rate=1000, seed=1101, chunk=60,
                max_instructions=20_000_000):
    """Teach one trainee with one machine, and record every item."""
    with open(SAKI_SRC) as f:
        src = f.read()
    src = src.replace("proc main()", "proc demo_main()") + DRIVER % {
        "seed": seed, "rate": rate, "machine": MACHINES[machine]}
    deck = "//JOB SAKI\n//SALISH OPT\n" + src + "\n//EXEC\n"
    sat = satellite.Satellite([(deck, SAKI_SRC)], model=90,
                              out=lambda s: None)
    job = sat.jobs[0]
    if job.failed:
        raise RuntimeError("\n".join(job.log))
    sy = job.steps[0].obj.symbols
    off = mach.MEM_OFF
    at = {k: sy[k] + off for k in (
        "G_obs_n", "G_obs_k", "G_obs_d", "G_obs_o", "G_obs_resp", "G_att",
        "G_rec_done", "G_t_right", "G_t_lat", "V_dk", "V_s", "V_mastered")}
    m = mach.Machine(model=90, satellite=sat)
    sat.machine = m
    ex = satellite.assemble_executive()
    m.load_image(ex.image())
    m.pc = ex.entry
    mem = m.mem
    rec = SakiRecording(machine, rate)
    seen = 0
    total = 0
    started = False
    while not m.halted and total < max_instructions:
        m.run(max_instructions=chunk)
        total += chunk
        if started and mem[at["G_rec_done"]] > 0:
            rec.tested = (mem[at["G_t_right"]], mem[at["G_t_lat"]])
            break
        if sat.cur is None:
            if started:
                break
            continue
        started = True
        n = mem[at["G_obs_n"]]
        if n == seen:
            continue
        if n != seen + 1:
            raise RuntimeError("an item was missed: use a smaller chunk")
        seen = n
        rec.frames.append(
            [n, mem[at["G_obs_k"]], mem[at["G_obs_d"]], mem[at["G_obs_o"]],
             mem[at["G_obs_resp"]], mem[at["G_att"]]]
            + [mem[at["V_dk"] + k] for k in range(NK)]
            + [mem[at["V_s"] + k] for k in range(NK)]
            + [1 if mem[at["V_mastered"] + k] > 0 else 0 for k in range(NK)])
    if rec.tested is None:
        raise RuntimeError("the lesson did not finish")
    return rec


_PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>SAKI</title>
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
#runs{display:flex;flex-wrap:wrap}
.box{background:var(--panel);border:1px solid var(--edge);border-radius:6px;
 padding:8px 10px;margin:8px;flex:1;min-width:300px}
.box h2{font-size:12px;color:var(--amber);margin:0 0 6px 0;font-weight:normal;
 letter-spacing:1px}
canvas{display:block;max-width:100%}
.stat{color:var(--dim);margin-top:6px;min-height:3.2em}
.stat b{font-weight:normal;color:var(--amber)}
.key{display:inline-block;width:10px;height:10px;margin:0 4px 0 12px;vertical-align:-1px}
#note{color:var(--dim);margin:0 10px 10px 10px;max-width:900px}
</style></head><body>
<div class="top">
 <h1>PASK'S SAKI</h1>
 <button id="b0">&#9198;</button><button id="bp">&#9654; run</button>
 <span style="color:var(--dim)">speed</span>
 <input id="spd" type="range" min="1" max="20" value="3" style="width:100px">
 <span id="item" style="color:var(--amber);min-width:90px"></span>
 <input id="scrub" type="range" min="0" max="1" value="0" style="flex:1;min-width:160px">
</div>
<div id="runs"></div>
<div style="margin:0 10px 6px;color:var(--dim)">
 answer: <span class="key" style="background:#ffb238"></span>from memory (+1)
 <span class="key" style="background:#8a8576"></span>by the light (0)
 <span class="key" style="background:#4fc3ff"></span>wrong key (&minus;1)
 &nbsp; bars: <span class="key" style="background:#ffb238"></span>the machine's delay
 <span class="key" style="background:#7ee787"></span>the trainee's memory (hidden)
</div>
<div id="note">__NOTE__</div>
<script>
const D = __DATA__, NK = 10;
const N = Math.max(...D.runs.map(r => r.frames.length));
const POS = {7:[0,0], 8:[1,0], 9:[2,0], 4:[0,1], 5:[1,1], 6:[2,1],
             1:[0,2], 2:[1,2], 3:[2,2], 0:[1,3]};
const ANS = {"1": "#ffb238", "0": "#8a8576", "-1": "#4fc3ff"};
const runs = document.getElementById("runs"), views = [];
D.runs.forEach(R => {
  const box = document.createElement("div"); box.className = "box";
  box.innerHTML = `<h2>${R.label}</h2>`;
  const kb = document.createElement("canvas"); kb.width = 300; kb.height = 330;
  const ch = document.createElement("canvas"); ch.width = 420; ch.height = 150;
  ch.style.width = "100%";
  const st = document.createElement("div"); st.className = "stat";
  box.appendChild(kb); box.appendChild(ch); box.appendChild(st);
  runs.appendChild(box);
  // the share of the last 50 answers from memory and wrong
  const mem50 = [], err50 = [], meanmem = [];
  let p = 0, e = 0;
  R.frames.forEach((f, i) => {
    if (f[3] > 0) p++; if (f[3] < 0) e++;
    if (i >= 50){ const o = R.frames[i - 50][3]; if (o > 0) p--; if (o < 0) e--; }
    const w = Math.min(i + 1, 50); mem50.push(p / w); err50.push(e / w);
    let s = 0; for (let k = 0; k < NK; k++) s += f[16 + k]; meanmem.push(s / NK / 1000);
  });
  views.push({R, kg: kb.getContext("2d"), ch, cg: ch.getContext("2d"), st,
              mem50, err50, meanmem});
});
function keyboard(v, f){
  const g = v.kg, S = 72, X0 = 30, Y0 = 18;
  g.fillStyle = "#1d2024"; g.fillRect(0, 0, 300, 330);
  for (let k = 0; k < NK; k++){
    const [c, r] = POS[k], x = X0 + c * (S + 12), y = Y0 + r * (S + 6);
    const delay = f[6 + k], lit = Math.max(0, Math.min(1, (3000 - delay) / 2700));
    // the light over the key: bright when it comes at once
    g.fillStyle = `rgba(255,178,56,${0.08 + 0.85 * lit})`;
    g.beginPath(); g.arc(x + S - 10, y + 10, 6, 0, 2 * Math.PI); g.fill();
    g.strokeStyle = "#3a3f46"; g.stroke();
    // the key
    const asked = f[1] == k;
    g.fillStyle = asked ? ANS[String(f[3])] : "#2b2f35";
    g.fillRect(x, y, S - 22, S - 30);
    g.strokeStyle = asked ? "#e8e2cc" : "#444"; g.lineWidth = asked ? 2 : 1;
    g.strokeRect(x, y, S - 22, S - 30);
    g.fillStyle = asked && f[3] > 0 ? "#15171a" : "#e8e2cc";
    g.font = "18px monospace"; g.fillText(String(k), x + 18, y + 28);
    if (f[26 + k]){ g.fillStyle = "#7ee787"; g.font = "11px monospace";
                    g.fillText("✓", x + S - 18, y + 36); }
    // the machine's model and the trainee's memory
    const bw = S - 22;
    g.fillStyle = "#33373e"; g.fillRect(x, y + S - 26, bw, 5); g.fillRect(x, y + S - 18, bw, 5);
    g.fillStyle = "#ffb238"; g.fillRect(x, y + S - 26, bw * Math.min(1, delay / 3000), 5);
    g.fillStyle = "#7ee787"; g.fillRect(x, y + S - 18, bw * f[16 + k] / 1000, 5);
  }
}
function chart(v, i){
  const c = v.ch; c.width = c.clientWidth || 420;
  const g = v.cg, W = c.width, H = c.height, X = j => j / Math.max(1, N - 1) * (W - 1);
  const Y = q => H - 4 - q * (H - 16);
  g.fillStyle = "#15171a"; g.fillRect(0, 0, W, H);
  const line = (arr, col) => { g.strokeStyle = col; g.lineWidth = 1.3; g.beginPath();
    arr.forEach((q, j) => j ? g.lineTo(X(j), Y(q)) : g.moveTo(X(j), Y(q))); g.stroke(); };
  line(v.R.frames.map(f => f[5] / 1000), "#e8e2cc");
  line(v.meanmem, "#7ee787");
  line(v.mem50, "#ffb238");
  line(v.err50, "#4fc3ff");
  g.fillStyle = "#a9a18a"; g.font = "10px monospace";
  g.fillText("attention", 4, 10); g.fillStyle = "#7ee787"; g.fillText("memory", 76, 10);
  g.fillStyle = "#ffb238"; g.fillText("from memory", 130, 10);
  g.fillStyle = "#4fc3ff"; g.fillText("wrong", 220, 10);
  const L = v.R.frames.length;
  if (L < N){ g.strokeStyle = "#555a60"; g.setLineDash([3, 3]); g.beginPath();
    g.moveTo(X(L - 1), 0); g.lineTo(X(L - 1), H); g.stroke(); g.setLineDash([]); }
  g.strokeStyle = "#e8e2cc"; g.beginPath(); g.moveTo(X(i), 12); g.lineTo(X(i), H); g.stroke();
}
let frame = 0, playing = false;
function show(){
  document.getElementById("item").textContent = "item " + (frame + 1);
  views.forEach(v => {
    const L = v.R.frames.length, i = Math.min(frame, L - 1), f = v.R.frames[i];
    keyboard(v, f); chart(v, i);
    let m = 0; for (let k = 0; k < NK; k++) m += f[26 + k];
    const ans = f[3] > 0 ? "found from memory" : f[3] < 0 ? "the wrong key" : "found by the light";
    let s = `item <b>${f[0]}</b>: key <b>${f[1]}</b>, light after <b>${(f[2] / 1000).toFixed(1)} s</b>,` +
            ` ${ans} in <b>${f[4]}</b> ms<br>attention <b>${Math.round(f[5] / 10)}%</b>`;
    if (v.R.machine == "SAKI") s += ` &nbsp; mastered <b>${m}</b> of 10`;
    if (frame >= L - 1) s += `<br>lesson over after <b>${L}</b> items; tested with no lights: ` +
                              `<b>${v.R.tested[0]}</b> keys of 100 found, in <b>${v.R.tested[1]}</b> ms`;
    v.st.innerHTML = s;
  });
  document.getElementById("scrub").value = frame;
}
const scrub = document.getElementById("scrub"); scrub.max = N - 1;
scrub.oninput = () => { frame = +scrub.value; show(); };
document.getElementById("b0").onclick = () => { playing = false; frame = 0; show(); };
const bp = document.getElementById("bp"), spd = document.getElementById("spd");
bp.onclick = () => { playing = !playing; bp.innerHTML = playing ? "&#10074;&#10074; pause" : "&#9654; run"; };
setInterval(() => {
  if (!playing) return;
  if (frame >= N - 1){ playing = false; bp.innerHTML = "&#9654; run"; return; }
  frame = Math.min(N - 1, frame + +spd.value); show();
}, 60);
show();
</script></body></html>
"""

_NOTE = ("Each key's light comes on after a delay: bright, it comes at once; "
         "dark, it is held back. SAKI moves each key's delay by the trainee's "
         "answers -- longer after an answer from memory, shorter after an "
         "error -- and gives more practice on the keys whose lights are still "
         "needed. Its delays are its model of the trainee; the green bars are "
         "the trainee's memory, which no machine sees. A fixed machine moves "
         "every light alike, on a schedule.")


def page_html(*recs, note=_NOTE):
    data = {"runs": [{"label": r.label, "machine": r.machine,
                      "frames": r.frames, "tested": r.tested} for r in recs]}
    return (_PAGE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
            .replace("__NOTE__", note))


def animate(*recs, height=None):
    """Show one or more runs, side by side, in a notebook cell."""
    return panel._display(panel._iframe(page_html(*recs), height or 640))


def save_html(path, *recs):
    with open(path, "w") as f:
        f.write(page_html(*recs))
    return path
