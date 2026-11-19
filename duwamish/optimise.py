"""The SALISH optimiser: the parts that are not code generation.

SALISH/O is the committee's optimising compiler, after FORTRAN I's index
registers, the usage counts of FORTRAN H (Lowry and Medlock, 1969) and the
program-optimisation work of Allen and Cocke at IBM.  It adds four things
to the plain compiler, each of which can be seen in the listing:

  * Register allocation.  Registers R3-R6 are given to the local
    variables, parameters and loop controls that the counts say are worth
    most.  A reference counts ten times more for each loop it is inside.
    Two variables whose scopes do not overlap may share a register.  A
    procedure saves the registers it uses and restores them on return
    (callee saves), so a call never disturbs its caller's registers.
  * Index-register addressing.  A global vector that the program never
    reassigns lies at a fixed address, so v[k] with k in a register is one
    operand, V_v(R3), as FORTRAN addressed its arrays.
  * Loop rotation.  A counted loop tests at the bottom, so each pass costs
    one conditional jump and no unconditional one.
  * A peephole pass over the generated TRIAD (below).

Nothing here changes what a program computes: tests/test_optimise.py runs
the demonstration programs both ways and compares what they print.
"""

import re

REGS = ("R3", "R4", "R5", "R6")
# a variable must earn this much before it is worth a register: about one
# use inside a loop.  Straight-line procedures keep their variables in core
# and pay nothing for saving registers.
THRESHOLD = 10


def weight(depth):
    return 10 ** min(depth, 6)


class RegisterPlan:
    """Usage counts and scopes for one procedure, taken before its code is
    generated, and the registers they earn.

    Candidates are keyed by their declaration:
        ("param", i)          the i-th parameter
        ("var", id(stmt), i)  the i-th name of a var statement
        ("for", id(stmt))     a for loop's control variable
        ("lim", id(stmt))     a for loop's limit, when it is not a constant
    """

    def __init__(self, comp, proc):
        self.comp = comp
        self.cand = {}          # key -> [weight, start, end, eligible]
        self.pos = 0
        self.catch = False      # the procedure calls catchpoint
        env = {}
        for i, pn in enumerate(proc.params):
            key = ("param", i)
            self.cand[key] = [0, 0, None, True]
            env[pn] = key
        self.stmt(proc.body, env, 0)
        self.pos += 1
        for c in self.cand.values():
            if c[2] is None:
                c[2] = self.pos
        self.assign = {} if self.catch else self.allocate()
        # a procedure with a catchpoint saves every register, and restores
        # them all when a throw lands there
        self.saved = list(REGS) if self.catch else \
            [r for r in REGS if r in self.assign.values()]

    # ---------------- the walk ----------------
    def close(self, keys):
        for k in keys:
            self.cand[k][2] = self.pos

    def declare(self, st, env, depth):
        keys = []
        for i, (name, size, init, line) in enumerate(st[2]):
            if init is not None:
                self.expr(init, env, depth)
            key = ("var", id(st), i)
            self.pos += 1
            self.cand[key] = [weight(depth), self.pos, None, True]
            env[name] = key
            keys.append(key)
        return keys

    def stmt(self, s, env, d):
        self.pos += 1
        k = s[0]
        if k == "block":
            inner = dict(env)
            declared = []
            for st in s[2]:
                if st[0] == "var":
                    declared += self.declare(st, inner, d)
                else:
                    self.stmt(st, inner, d)
            self.close(declared)
        elif k == "var":
            self.close(self.declare(s, dict(env), d))
        elif k == "expr":
            self.expr(s[2], env, d)
        elif k == "assign":
            self.expr(s[2], env, d)
            self.expr(s[3], env, d)
        elif k == "if":
            self.expr(s[2], env, d)
            self.stmt(s[3], env, d)
            if s[4] is not None:
                self.stmt(s[4], env, d)
        elif k == "while":
            self.expr(s[2], env, d + 1)
            self.stmt(s[3], env, d + 1)
        elif k == "repeat":
            self.stmt(s[2], env, d + 1)
            self.expr(s[3], env, d + 1)
        elif k == "for":
            _, line, v, a, b, step, body = s
            for e in (a, b, step):
                self.expr(e, env, d)
            self.pos += 1
            key = ("for", id(s))
            # the increment and the test use it on every pass
            self.cand[key] = [3 * weight(d + 1), self.pos, None, True]
            keys = [key]
            if self.comp.fold(b) is None:
                lk = ("lim", id(s))
                self.cand[lk] = [weight(d + 1), self.pos, None, True]
                keys.append(lk)
            inner = dict(env)
            inner[v] = key
            self.stmt(body, inner, d + 1)
            self.pos += 1
            self.close(keys)
        elif k == "sign":
            self.expr(s[2], env, d)
            for arm in s[3].values():
                self.stmt(arm, env, d)
        elif k == "return":
            if s[2] is not None:
                self.expr(s[2], env, d)

    def expr(self, e, env, d):
        if not isinstance(e, tuple) or not e:
            return
        k = e[0]
        if k == "name":
            key = env.get(e[2])
            if key:
                self.cand[key][0] += weight(d)
        elif k == "addr":
            key = env.get(e[2])
            if key:
                self.cand[key][3] = False      # it must live in core
        elif k == "call":
            key = env.get(e[2])
            if key:
                self.cand[key][0] += weight(d)
            elif e[2] == "catchpoint" and e[2] not in self.comp.procs:
                self.catch = True
            for a in e[3]:
                self.expr(a, env, d)
        elif k in ("num", "str"):
            return
        elif k == "table":
            for x in e[2]:
                self.expr(x, env, d)
        else:
            for x in e[2:]:
                if isinstance(x, tuple):
                    self.expr(x, env, d)

    # ---------------- allocation ----------------
    def allocate(self):
        order = sorted((k for k, c in self.cand.items()
                        if c[3] and c[0] >= THRESHOLD),
                       key=lambda k: -self.cand[k][0])
        assign = {}
        for k in order:
            w, s, e, _ = self.cand[k]
            busy = {assign[o] for o in assign
                    if self.cand[o][1] <= e and s <= self.cand[o][2]}
            for r in REGS:
                if r not in busy:
                    assign[k] = r
                    break
        return assign


def static_vectors(gdecls, procs):
    """Global vectors that the program never reassigns and whose address it
    never takes: they stay where the loader put them, so their elements
    can be addressed directly."""
    vecs = {d[2] for _, d in gdecls if d[3] is not None}
    gone = set()

    def walk(n):
        if isinstance(n, tuple) and n:
            if n[0] == "assign" and n[2][0] == "name":
                gone.add(n[2][2])
            elif n[0] == "addr":
                gone.add(n[2])
            for x in n:
                walk(x)
        elif isinstance(n, (list, dict)):
            for x in (n.values() if isinstance(n, dict) else n):
                walk(x)
    for _, d in gdecls:
        walk(d)
    for p in procs.values():
        walk(p.body)
    return vecs - gone


# ----------------------------------------------------------------------
# The peephole pass
# ----------------------------------------------------------------------
_LABEL = re.compile(r"^([A-Za-z_][\w.]*):\s*$")
_INSTR = re.compile(r"^        (\S+)\s*(.*)$")
_LREF = re.compile(r"\bL\d+\b")
# orders whose next instruction may read the condition trit
_READS_C = {"JN", "JZ", "JP", "JNN", "JNZ", "JNP", "J3", "SEL"}
_CONDJ = {"JN", "JZ", "JP", "JNN", "JNZ", "JNP"}
# orders that set C to the sign of the register they write
_SETS_C = {"LD", "ADD", "SUB", "MUL", "DIV", "MOD", "NEG", "AND", "OR",
           "EQV", "SHF", "XTR", "SEL", "POP"}


def _parse(line):
    """('label', name) | ('op', opcode, operands) | ('other',)"""
    m = _LABEL.match(line)
    if m:
        return ("label", m.group(1))
    m = _INSTR.match(line)
    if m and m.group(1)[0] != ";":
        return ("op", m.group(1), m.group(2).strip())
    return ("other",)


def _fmt(op, args):
    return f"        {op:4} {args}".rstrip()


def peephole(lines):
    """Improve the generated code, pass after pass, until nothing changes.
    Returns (lines, counts of each improvement)."""
    counts = {}

    def note(what):
        counts[what] = counts.get(what, 0) + 1

    lines = list(lines)
    changed = True
    while changed:
        changed = False
        p = [_parse(x) for x in lines]
        n = len(lines)
        dead = [False] * n

        # J3 dispatch tables are positional: never touch their jumps
        labelpos = {x[1]: i for i, x in enumerate(p) if x[0] == "label"}
        protect = set()
        for x in p:
            if x[0] == "op" and x[1] == "J3" and x[2] in labelpos:
                t = labelpos[x[2]]
                protect.update({t - 1, t + 1, t + 2})

        def nxt(i):
            """Index of the next instruction after i, skipping comments;
            None if a label or anything else intervenes."""
            j = i + 1
            while j < n and p[j][0] == "other" and \
                    lines[j].lstrip().startswith(";"):
                j += 1
            return j if j < n and p[j][0] == "op" else None

        # 1. unreferenced compiler labels.  Removing one counts as a change:
        # it can expose more dead code, and each procedure must reach its
        # own fixed point whatever its neighbours do
        refs = set()
        for x in p:
            if x[0] == "op":
                refs.update(_LREF.findall(x[2]))
        for i, x in enumerate(p):
            if x[0] == "label" and re.fullmatch(r"L\d+", x[1]) \
                    and x[1] not in refs:
                dead[i] = True
                note("unused labels")
                changed = True

        # jump threading: a jump to a jump goes straight to the end
        first = {}
        for i, x in enumerate(p):
            if x[0] == "label":
                j = i + 1
                while j < n and p[j][0] == "label":
                    j += 1
                if j < n and p[j][0] == "op" and j not in protect:
                    first[x[1]] = p[j]
        for i, x in enumerate(p):
            if x[0] == "op" and (x[1] == "JMP" or x[1] in _CONDJ) \
                    and i not in protect and x[2] in first:
                tgt = first[x[2]]
                if tgt[1] == "JMP" and re.fullmatch(r"[A-Za-z_]\w*", tgt[2]) \
                        and tgt[2] != x[2]:
                    lines[i] = _fmt(x[1], tgt[2])
                    note("jumps threaded")
                    changed = True

        i = 0
        while i < n:
            x = p[i]
            if x[0] != "op" or dead[i]:
                i += 1
                continue
            op, args = x[1], x[2]
            # 2. unreachable code after an unconditional transfer
            if op in ("JMP", "RET") and i not in protect:
                j = i + 1
                while j < n and p[j][0] == "op" and j not in protect:
                    dead[j] = True
                    note("unreachable instructions")
                    changed = True
                    j += 1
            # 3. a jump to the very next instruction
            if op == "JMP" and i not in protect:
                j = i + 1
                while j < n and (p[j][0] == "label" or dead[j]):
                    if p[j][0] == "label" and p[j][1] == args:
                        dead[i] = True
                        note("jumps to the next instruction")
                        changed = True
                        break
                    j += 1
            j = nxt(i)
            if j is not None and not dead[j]:
                y = p[j]
                k = nxt(j)
                after = p[k][1] if k is not None else None
                # 4. a load of what was just stored
                if op == "ST" and args.startswith("R1,") and y[1] == "LD" \
                        and y[2] == args and after not in _READS_C:
                    dead[j] = True
                    note("loads after stores")
                    changed = True
                m = re.fullmatch(r"(R[3-6]), #0\(R1\)", args)
                if op == "LD" and m and y[1] == "LD" and \
                        y[2] == f"R1, #0({m.group(1)})" and after not in _READS_C:
                    dead[j] = True
                    note("loads after stores")
                    changed = True
                # 5. a test of what was just computed
                if y[1] == "TST" and y[2] == "#0(R1)" and op in _SETS_C \
                        and args.startswith("R1,") or \
                        (y[1] == "TST" and y[2] == "#0(R1)" and op == "POP"
                         and args == "R1"):
                    dead[j] = True
                    note("redundant tests")
                    changed = True
            # 6. PUSH R1 ... POP R2 becomes a register move
            if op == "PUSH" and args == "R1":
                j = i + 1
                ok = True
                while j < n:
                    if dead[j]:
                        j += 1
                        continue
                    y = p[j]
                    if y[0] != "op":
                        ok = False
                        break
                    if y[1] == "POP":
                        break
                    if y[1] in ("PUSH", "CALL", "RET", "SVC", "JSR", "JMP",
                                "J3") or y[1] in _CONDJ or \
                            re.search(r"\b(R2|SP)\b", y[2]):
                        ok = False
                        break
                    j += 1
                if ok and j < n and p[j][0] == "op" and p[j][1] == "POP" \
                        and p[j][2] == "R2":
                    k = nxt(j)
                    if k is None or p[k][1] not in _READS_C:
                        lines[i] = _fmt("LD", "R2, #0(R1)")
                        dead[j] = True
                        note("stack temporaries kept in R2")
                        changed = True
            i += 1
        lines = [x for i, x in enumerate(lines) if not dead[i]]
    return lines, counts
