"""The WHALE clinic, animated.

programs/whale/diagnosis.whl examines patients one question at a time.
After each step its examine() leaves in core the question asked, the
answer, and the weight of evidence for each of the five diagnoses, and
then counts the step.  record_clinic() runs the program's own procedures
under a driver of its own: it learns from the records as the program
does, then examines each of several patients twice, asking in Good's
order and in a fixed order.  The driver also leaves each patient's true
disease and each examination's verdict where the recorder can read them.

The page shows each examination as Wald saw a sequential test: the
weight of evidence for each diagnosis, question by question, between the
boundaries at +20 db (the diagnosis is made) and -20 db (it is ruled
out).  The two orders of asking are side by side, step for step, with
the questions and answers, and each diagnosis's chance.
"""

import json
import os
import re

from . import machine as mach
from . import panel
from . import satellite

HERE = os.path.dirname(__file__)
CLINIC = os.path.join(HERE, "..", "programs", "whale", "diagnosis.whl")

DRIVER = """
global rec_pat := 0, rec_good := 0, rec_truth := 0, rec_verdict := 0
global rec_done := 0, rec_end := 0

proc main()
begin
  patient := new
  seed := 1950
  learn(400)
  seed := %(seed)d
  for k := 1 to %(n)d do begin
    sample()
    rec_pat := k
    rec_truth := case_d
    rec_good := 1
    rec_verdict := examine(patient, true, false)
    forget(patient)
    rec_done := rec_done + 1
    rec_good := 0
    rec_verdict := examine(patient, false, false)
    forget(patient)
    rec_done := rec_done + 1
  end
  rec_end := 1
  return 0
end
"""


def _table(src, name):
    m = re.search(r"global " + name + r" := table\(([^)]*)\)", src)
    return [w.strip() for w in m.group(1).split(",")]


class ClinicRecording:
    def __init__(self, diseases, findings):
        self.diseases = diseases
        self.findings = findings
        # one per examination: {"patient", "good", "truth", "verdict",
        #   "steps": [[question (-1 first), answer (+1/-1/0), w1..w5]]}
        self.exams = []


def record_clinic(patients=6, seed=4242, chunk=200,
                  max_instructions=40_000_000):
    """Examine the patients both ways, and record every step."""
    with open(CLINIC) as f:
        src = f.read()
    diseases = _table(src, "dl")
    findings = _table(src, "fl")
    items = [n.strip() for line in re.findall(r"^item (.*)$", src, re.M)
             for n in line.split(",")]
    present = items.index("present") + 1
    text = src.replace("proc main()", "proc demo_main()") + DRIVER % {
        "seed": seed, "n": patients}
    deck = "//JOB CLINIC\n//WHALE OPT\n" + text + "\n//EXEC\n"
    sat = satellite.Satellite([(deck, CLINIC)], model=90,
                              out=lambda s: None)
    job = sat.jobs[0]
    if job.failed:
        raise RuntimeError("\n".join(job.log))
    sy = job.steps[0].obj.symbols
    off = mach.MEM_OFF
    at = {k: sy[k] + off for k in (
        "G_obs_n", "G_obs_j", "G_obs_ans", "V_obs_w", "G_rec_pat",
        "G_rec_good", "G_rec_truth", "G_rec_verdict", "G_rec_done",
        "G_rec_end")}
    m = mach.Machine(model=90, satellite=sat)
    sat.machine = m
    ex = satellite.assemble_executive()
    m.load_image(ex.image())
    m.pc = ex.entry
    mem = m.mem
    rec = ClinicRecording(diseases, findings)
    seen = done = 0
    cur = None
    total = 0
    started = False
    nd = len(diseases)

    def finish():
        cur["verdict"] = (mem[at["G_rec_verdict"]] - (items.index(diseases[0])
                                                       + 1)
                          if mem[at["G_rec_verdict"]] else -1)
        rec.exams.append(cur)

    while not m.halted and total < max_instructions:
        m.run(max_instructions=chunk)
        total += chunk
        if started:
            d = mem[at["G_rec_done"]]
            if d != done:
                if d != done + 1 or cur is None:
                    raise RuntimeError("an examination was missed")
                done = d
                finish()
                cur = None
            if mem[at["G_rec_end"]] > 0:
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
            raise RuntimeError("a step was missed: use a smaller chunk")
        seen = n
        j = mem[at["G_obs_j"]]
        if j < 0:
            cur = {"patient": mem[at["G_rec_pat"]],
                   "good": mem[at["G_rec_good"]] > 0,
                   "truth": mem[at["G_rec_truth"]], "steps": []}
        ans = 0 if j < 0 else (1 if mem[at["G_obs_ans"]] == present else -1)
        cur["steps"].append([j, ans] + [mem[at["V_obs_w"] + i]
                                        for i in range(nd)])
    if not rec.exams or mem[at["G_rec_end"]] <= 0:
        raise RuntimeError("the clinic did not finish")
    return rec


_PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>WHALE clinic</title>
<style>
:root{--bg:#15171a;--panel:#1d2024;--edge:#33373e;--ink:#e8e2cc;--dim:#a9a18a;
 --amber:#ffb238;--blue:#4fc3ff;--green:#7ee787}
body{margin:0;background:var(--bg);color:var(--ink);
 font:12px 'DejaVu Sans Mono',Menlo,Consolas,monospace}
.top{display:flex;align-items:center;gap:8px;padding:8px 12px;flex-wrap:wrap;
 background:#101214;border-bottom:1px solid var(--edge)}
.top h1{font-size:14px;margin:0 12px 0 0;color:var(--amber);letter-spacing:2px}
button{background:#2b2f35;color:var(--ink);border:1px solid #444;border-radius:4px;
 padding:4px 9px;font:inherit;cursor:pointer}
button.on{border-color:var(--amber);color:var(--amber)}
#exams{display:flex;flex-wrap:wrap}
.box{background:var(--panel);border:1px solid var(--edge);border-radius:6px;
 padding:8px 10px;margin:8px;flex:1;min-width:330px}
.box h2{font-size:12px;color:var(--amber);margin:0 0 6px 0;font-weight:normal;
 letter-spacing:1px}
canvas{display:block;width:100%}
.qa{color:var(--dim);margin-top:6px;min-height:7.5em;line-height:1.45}
.qa b{font-weight:normal;color:var(--ink)}
.verdict{margin-top:4px;min-height:1.5em}
.chances{margin-top:6px}
.bar{display:flex;align-items:center;gap:6px;margin:2px 0}
.bar span.n{width:80px}
.bar div{height:8px;border-radius:2px}
#note{color:var(--dim);margin:0 10px 10px 10px;max-width:900px}
</style></head><body>
<div class="top">
 <h1>THE WHALE CLINIC</h1>
 <span style="color:var(--dim)">patient</span><span id="pats"></span>
 <button id="bb">&#9664;</button><button id="bp">&#9654; examine</button>
 <button id="bf">&#9654;|</button>
 <span id="stepno" style="color:var(--amber)"></span>
</div>
<div id="exams"></div>
<div id="note">__NOTE__</div>
<script>
const D = __DATA__, ND = D.diseases.length;
const COL = ["#ffb238", "#4fc3ff", "#ff7b72", "#7ee787", "#c678dd"];
const pats = [...new Set(D.exams.map(e => e.patient))];
let pat = pats[0], step = 0, playing = false;
const bar = document.getElementById("pats");
pats.forEach(p => { const b = document.createElement("button"); b.textContent = p;
  b.onclick = () => { pat = p; step = 0; playing = false; build(); show(); }; bar.appendChild(b); });
let views = [];
function build(){
  const host = document.getElementById("exams"); host.innerHTML = "";
  [...bar.children].forEach(b => b.className = +b.textContent == pat ? "on" : "");
  views = D.exams.filter(e => e.patient == pat).sort((a, b) => b.good - a.good).map(e => {
    const box = document.createElement("div"); box.className = "box";
    box.innerHTML = `<h2>${e.good ? "in Good's order: the question expected to tell most" : "in a fixed order"}</h2>`;
    const c = document.createElement("canvas"); c.height = 230; box.appendChild(c);
    const ch = document.createElement("div"); ch.className = "chances"; box.appendChild(ch);
    const qa = document.createElement("div"); qa.className = "qa"; box.appendChild(qa);
    const v = document.createElement("div"); v.className = "verdict"; box.appendChild(v);
    host.appendChild(box);
    return {e, c, g: c.getContext("2d"), ch, qa, v};
  });
}
const S = Math.max(...D.exams.map(e => e.steps.length));
function chance(w){ return 1 / (1 + Math.pow(10, -w / 1000)); }
function draw(V, k){
  const c = V.c; c.width = c.clientWidth || 400;
  const g = V.g, W = c.width, H = c.height, L = 36;
  const X = i => L + i / 12 * (W - L - 8), Y = w => H / 2 - Math.max(-45, Math.min(45, w / 100)) / 45 * (H / 2 - 10);
  g.fillStyle = "#15171a"; g.fillRect(0, 0, W, H);
  g.fillStyle = "#1f2a20"; g.fillRect(L, 0, W - L, Y(2000));
  g.fillStyle = "#1a2530"; g.fillRect(L, Y(-2000), W - L, H - Y(-2000));
  g.strokeStyle = "#555a60"; g.setLineDash([4, 3]);
  for (const b of [2000, -2000]){ g.beginPath(); g.moveTo(L, Y(b)); g.lineTo(W, Y(b)); g.stroke(); }
  g.setLineDash([]); g.strokeStyle = "#3a3f46"; g.beginPath(); g.moveTo(L, Y(0)); g.lineTo(W, Y(0)); g.stroke();
  g.fillStyle = "#a9a18a"; g.font = "10px monospace";
  g.fillText("+20 db", 0, Y(2000) + 3); g.fillText("  0", 0, Y(0) + 3); g.fillText("-20 db", 0, Y(-2000) + 3);
  g.fillText("diagnosis", L + 4, 12); g.fillText("ruled out", L + 4, H - 4);
  const st = V.e.steps, n = Math.min(k, st.length - 1);
  for (let d = 0; d < ND; d++){
    g.strokeStyle = COL[d]; g.lineWidth = d == V.e.truth ? 2.6 : 1.4; g.beginPath();
    for (let i = 0; i <= n; i++){ const y = Y(st[i][2 + d]); if (i) g.lineTo(X(i), y); else g.moveTo(X(i), y); }
    g.stroke();
    g.fillStyle = COL[d]; g.beginPath(); g.arc(X(n), Y(st[n][2 + d]), 3, 0, 2 * Math.PI); g.fill();
  }
  for (let i = 1; i <= 12; i++){ g.fillStyle = "#555a60"; g.fillRect(X(i), H / 2 - 2, 1, 4); }
}
function show(){
  document.getElementById("stepno").textContent = step ? "after question " + step : "before any question";
  views.forEach(V => {
    const st = V.e.steps, n = Math.min(step, st.length - 1);
    draw(V, step);
    V.ch.innerHTML = D.diseases.map((name, d) => {
      const w = st[n][2 + d], p = chance(w), mark = w >= 2000 ? " *" : w <= -2000 ? " x" : "";
      return `<div class="bar"><span class="n" style="color:${COL[d]}">${name}${d == V.e.truth ? "&#8224;" : ""}</span>` +
             `<div style="width:${Math.max(1, p * 160)}px;background:${COL[d]}"></div>` +
             `<span>${(w / 100).toFixed(1)} db${mark} &nbsp;${(100 * p).toFixed(p < 0.1 || p > 0.99 ? 2 : 0)}%</span></div>`;
    }).join("");
    V.qa.innerHTML = st.slice(1, n + 1).map(s =>
      `<span style="white-space:nowrap">${D.findings[s[0]].replace(/_/g, " ")}? ` +
      `<b>${s[1] > 0 ? "yes" : "no"}</b></span>`).join(" &nbsp; ") || "&nbsp;";
    let vt = "";
    if (step >= st.length - 1){
      const truth = D.diseases[V.e.truth];
      vt = V.e.verdict < 0 ? `undecided after ${st.length - 1} questions: <b style="color:#a9a18a">referred</b> (in truth ${truth})` :
        `diagnosis <b style="color:${COL[V.e.verdict]}">${D.diseases[V.e.verdict]}</b> after ${st.length - 1} questions: ` +
        (V.e.verdict == V.e.truth ? `<b style="color:#7ee787">right</b>` : `<b style="color:#ff5f56">wrong</b> (in truth ${truth})`);
    }
    V.v.innerHTML = vt;
  });
}
document.getElementById("bb").onclick = () => { if (step > 0) step--; show(); };
document.getElementById("bf").onclick = () => { if (step < S - 1) step++; show(); };
const bp = document.getElementById("bp");
bp.onclick = () => { if (step >= S - 1) step = 0; playing = !playing;
  bp.innerHTML = playing ? "&#10074;&#10074; pause" : "&#9654; examine"; show(); };
setInterval(() => {
  if (!playing) return;
  if (step >= S - 1){ playing = false; bp.innerHTML = "&#9654; examine"; return; }
  step++; show();
}, 900);
build(); show();
</script></body></html>
"""

_NOTE = ("Each line is one diagnosis's weight of evidence against the rest, "
         "question by question; the patient's true disease (&#8224;) is drawn "
         "thicker. Each answer adds its weight, worked out against the "
         "diagnoses as they then stand (Good's conditional weight). The "
         "examination stops when a line crosses +20 db -- odds of 100 to 1 -- "
         "and a line below -20 db is ruled out: Wald's sequential test. If no "
         "line reaches the top before the questions run out, the patient is "
         "referred. On the left the next question is the one with the greatest "
         "expected weight of evidence about the leading diagnosis; on the "
         "right the questions come in a fixed order.")


def page_html(rec, note=_NOTE):
    data = {"diseases": rec.diseases, "findings": rec.findings,
            "exams": rec.exams}
    return (_PAGE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
            .replace("__NOTE__", note))


def animate(rec, height=640):
    return panel._display(panel._iframe(page_html(rec), height))


def save_html(rec, path):
    with open(path, "w") as f:
        f.write(page_html(rec))
    return path
