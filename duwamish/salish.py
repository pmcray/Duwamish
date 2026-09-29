"""SALISH: a systems language for the Duwamish computer.

SALISH is typeless in the manner of BCPL: every value is one 27-trit word.
Its ternary character shows in three places:

  * Truth is three-valued.  true = +1, unknown = 0, false = -1.  A condition
    succeeds only when its value is positive.  `&` and `|` are the machine's
    tritwise min and max, i.e. Kleene's strong connectives; `and` and `or`
    are McCarthy's sequential connectives (the left operand decides first);
    `not` is negation.  Comparisons yield true or false.
  * `sign e of - : S  0 : S  + : S end` is a three-way branch compiled into
    a single J3 instruction.
  * A module that begins with the word `bloop` is certified by the compiler
    to terminate: no while/repeat loops, no recursion, no calls through
    variables -- Hofstadter's BlooP, where every loop has a bound fixed on
    entry.  Everything else is FlooP.

A newline ends an expression wherever an expression may end, so a long
expression must break after an operator, never before one.

See docs/SALISH.md for the full manual.
"""

import os
import re

from . import isa
from . import microasm

LIB_DIR = os.path.join(os.path.dirname(__file__), "lib")


class CompileError(Exception):
    pass


KEYWORDS = {
    "global", "const", "proc", "get", "bloop", "begin", "end", "var", "if",
    "then", "else", "while", "do", "repeat", "until", "for", "to", "by",
    "sign", "of", "return", "break", "next", "and", "or", "not", "mod",
    "true", "false", "unknown", "table", "inline",
}

TOKEN_RE = re.compile(r"""
    (?P<ws>[ \t\r]+)
  | (?P<nl>\n)
  | (?P<comment>--[^\n]*)
  | (?P<tnum>0t[T01]+)
  | (?P<num>\d+)
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<str>"(?:\\.|[^"\\\n])*")
  | (?P<char>'(?:\\.|[^'\\\n])')
  | (?P<op>\+:=|-:=|:=|->|<>|<=|>=|<<|>>|[-+*/=<>()\[\],;:&|@])
""", re.X)

ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"', "'": "'", "0": "\0",
           "e": "\x1b"}


def unescape(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            out.append(ESCAPES.get(s[i + 1], s[i + 1]))
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


class Tok:
    __slots__ = ("kind", "val", "line", "nl", "file")

    def __init__(self, kind, val, line, nl, file):
        self.kind, self.val, self.line, self.nl, self.file = \
            kind, val, line, nl, file

    def __repr__(self):
        return f"{self.kind}:{self.val!r}@{self.line}"


def tokenize(text, fname):
    toks = []
    pos, line, nl = 0, 1, True
    while pos < len(text):
        m = TOKEN_RE.match(text, pos)
        if not m:
            raise CompileError(f"{fname}:{line}: unexpected character "
                               f"{text[pos]!r}")
        kind = m.lastgroup
        val = m.group(kind)
        pos = m.end()
        if kind == "nl":
            line += 1
            nl = True
            continue
        if kind in ("ws", "comment"):
            continue
        if kind == "name" and val in KEYWORDS:
            kind = "kw"
        elif kind == "num":
            val = int(val)
        elif kind == "tnum":
            from .ternary import from_tstr
            kind, val = "num", from_tstr(val[2:])
        elif kind == "str":
            val = unescape(val[1:-1])
        elif kind == "char":
            kind, val = "num", ord(unescape(val[1:-1]))
        toks.append(Tok(kind, val, line, nl, fname))
        nl = False
    toks.append(Tok("eof", None, line, True, fname))
    return toks


# ----------------------------------------------------------------------
# Parser.  The AST is made of tuples whose first element names the node.
# Expression and statement nodes carry their source line as element 1.
# ----------------------------------------------------------------------

class Parser:
    def __init__(self, toks):
        self.toks = toks
        self.i = 0

    @property
    def tok(self):
        return self.toks[self.i]

    def err(self, msg, tok=None):
        tok = tok or self.tok
        raise CompileError(f"{tok.file}:{tok.line}: {msg}")

    def at(self, kind, val=None):
        t = self.tok
        return t.kind == kind and (val is None or t.val == val)

    def at_op(self, *vals):
        return self.tok.kind == "op" and self.tok.val in vals

    def at_kw(self, *vals):
        return self.tok.kind == "kw" and self.tok.val in vals

    def next(self):
        t = self.tok
        self.i += 1
        return t

    def expect(self, kind, val=None):
        if not self.at(kind, val):
            want = val if val is not None else kind
            got = self.tok.val if self.tok.val is not None else self.tok.kind
            self.err(f"expected {want!r}, found {got!r}")
        return self.next()

    def name(self):
        return self.expect("name").val

    # ---------------- declarations ----------------
    def module(self):
        decls = []
        bloop = False
        while not self.at("eof"):
            t = self.tok
            if self.at_kw("bloop"):
                self.next()
                bloop = True
            elif self.at_kw("get"):
                self.next()
                decls.append(("get", t.line, self.expect("str").val, t))
            elif self.at_kw("global"):
                self.next()
                while True:
                    decls.append(self.global_decl())
                    if not self.at_op(","):
                        break
                    self.next()
            elif self.at_kw("const"):
                self.next()
                while True:
                    line = self.tok.line
                    n = self.name()
                    self.expect("op", "=")
                    decls.append(("const", line, n, self.expr()))
                    if not self.at_op(","):
                        break
                    self.next()
            elif self.at_kw("proc"):
                decls.append(self.proc())
            elif self.at_kw("inline"):
                self.next()
                d = self.proc()
                if d[4][0] != "return" or d[4][2] is None:
                    self.err("an inline proc must be written  proc f(..) = expr")
                decls.append(d + (True,))
            elif self.at_op(";"):
                self.next()
            else:
                self.err(f"expected a declaration, found {t.val!r}")
        return decls, bloop

    def global_decl(self):
        line = self.tok.line
        n = self.name()
        size = None
        init = None
        if self.at_op("["):
            self.next()
            size = self.expr()
            self.expect("op", "]")
        if self.at_op(":="):
            self.next()
            init = self.expr()
        return ("global", line, n, size, init)

    def proc(self):
        t = self.expect("kw", "proc")
        n = self.name()
        self.expect("op", "(")
        params = []
        if not self.at_op(")"):
            params.append(self.name())
            while self.at_op(","):
                self.next()
                params.append(self.name())
        self.expect("op", ")")
        if self.at_op("="):
            self.next()
            e = self.expr()
            body = ("return", e[1], e)
        else:
            body = self.stmt()
        return ("proc", t.line, n, params, body, t.file)

    # ---------------- statements ----------------
    def stmt(self):
        t = self.tok
        line = t.line
        if t.kind == "kw":
            k = t.val
            if k == "begin":
                self.next()
                body = []
                while not self.at_kw("end"):
                    if self.at("eof"):
                        self.err("missing 'end'", t)
                    if self.at_op(";"):
                        self.next()
                        continue
                    body.append(self.stmt())
                self.next()
                return ("block", line, body)
            if k == "var":
                self.next()
                decls = []
                while True:
                    vl = self.tok.line
                    n = self.name()
                    size = init = None
                    if self.at_op("["):
                        self.next()
                        size = self.expr()
                        self.expect("op", "]")
                    if self.at_op(":="):
                        self.next()
                        init = self.expr()
                    decls.append((n, size, init, vl))
                    if not self.at_op(","):
                        break
                    self.next()
                return ("var", line, decls)
            if k == "if":
                self.next()
                c = self.expr()
                self.expect("kw", "then")
                a = self.stmt()
                b = None
                if self.at_kw("else"):
                    self.next()
                    b = self.stmt()
                return ("if", line, c, a, b)
            if k == "while":
                self.next()
                c = self.expr()
                self.expect("kw", "do")
                return ("while", line, c, self.stmt())
            if k == "repeat":
                self.next()
                body = []
                while not self.at_kw("until"):
                    if self.at("eof"):
                        self.err("missing 'until'", t)
                    if self.at_op(";"):
                        self.next()
                        continue
                    body.append(self.stmt())
                self.next()
                return ("repeat", line, ("block", line, body), self.expr())
            if k == "for":
                self.next()
                v = self.name()
                self.expect("op", ":=")
                a = self.expr()
                self.expect("kw", "to")
                b = self.expr()
                step = ("num", line, 1)
                if self.at_kw("by"):
                    self.next()
                    step = self.expr()
                self.expect("kw", "do")
                return ("for", line, v, a, b, step, self.stmt())
            if k == "sign":
                self.next()
                e = self.expr()
                self.expect("kw", "of")
                arms = {}
                while not self.at_kw("end"):
                    if self.at_op(";"):
                        self.next()
                        continue
                    lt = self.next()
                    key = None
                    if lt.kind == "op" and lt.val in ("-", "+"):
                        key = -1 if lt.val == "-" else 1
                    elif lt.kind == "num" and lt.val == 0:
                        key = 0
                    elif lt.val in ("neg", "false"):
                        key = -1
                    elif lt.val in ("zero", "unknown"):
                        key = 0
                    elif lt.val in ("pos", "true"):
                        key = 1
                    if key is None:
                        self.err("expected an arm label - 0 + ", lt)
                    if key in arms:
                        self.err("duplicate arm", lt)
                    self.expect("op", ":")
                    arms[key] = self.stmt()
                self.next()
                return ("sign", line, e, arms)
            if k == "return":
                self.next()
                e = None
                if not self.tok.nl and not self.at_kw("end", "else") \
                        and not self.at_op(";") and not self.at("eof"):
                    e = self.expr()
                return ("return", line, e)
            if k == "break":
                self.next()
                return ("break", line)
            if k == "next":
                self.next()
                return ("next", line)
        e = self.expr()
        if self.at_op(":=", "+:=", "-:="):
            op = self.next().val
            if e[0] not in ("name", "index"):
                self.err("cannot assign to this expression", t)
            rhs = self.expr()
            if op != ":=":
                rhs = ("bin", line, op[0], e, rhs)
            return ("assign", line, e, rhs)
        if e[0] != "call":
            self.err("an expression statement must be a call or assignment",
                     t)
        return ("expr", line, e)

    # ---------------- expressions ----------------
    def cont(self):
        """A binary operator continues the expression only on the same line."""
        return not self.tok.nl

    def expr(self):
        c = self.or_expr()
        if self.at_op("->") and self.cont():
            line = self.next().line
            a = self.expr()
            self.expect("op", ",")
            b = self.expr()
            return ("cond", line, c, a, b)
        return c

    def or_expr(self):
        e = self.and_expr()
        while self.at_kw("or") and self.cont():
            line = self.next().line
            e = ("or", line, e, self.and_expr())
        return e

    def and_expr(self):
        e = self.not_expr()
        while self.at_kw("and") and self.cont():
            line = self.next().line
            e = ("and", line, e, self.not_expr())
        return e

    def not_expr(self):
        if self.at_kw("not"):
            line = self.next().line
            return ("neg", line, self.not_expr())
        return self.cmp_expr()

    def cmp_expr(self):
        e = self.bor_expr()
        if self.at_op("=", "<>", "<", "<=", ">", ">=") and self.cont():
            t = self.next()
            e = ("cmp", t.line, t.val, e, self.bor_expr())
        return e

    def bor_expr(self):
        e = self.band_expr()
        while self.at_op("|") and self.cont():
            line = self.next().line
            e = ("bin", line, "|", e, self.band_expr())
        return e

    def band_expr(self):
        e = self.shift_expr()
        while self.at_op("&") and self.cont():
            line = self.next().line
            e = ("bin", line, "&", e, self.shift_expr())
        return e

    def shift_expr(self):
        e = self.add_expr()
        while self.at_op("<<", ">>") and self.cont():
            t = self.next()
            e = ("bin", t.line, t.val, e, self.add_expr())
        return e

    def add_expr(self):
        e = self.mul_expr()
        while self.at_op("+", "-") and self.cont():
            t = self.next()
            e = ("bin", t.line, t.val, e, self.mul_expr())
        return e

    def mul_expr(self):
        e = self.unary()
        while (self.at_op("*", "/") or self.at_kw("mod")) and self.cont():
            t = self.next()
            e = ("bin", t.line, t.val, e, self.unary())
        return e

    def unary(self):
        t = self.tok
        if self.at_op("-"):
            self.next()
            return ("neg", t.line, self.unary())
        if self.at_op("+"):
            self.next()
            return self.unary()
        if self.at_op("@"):
            self.next()
            return ("addr", t.line, self.name())
        return self.postfix()

    def postfix(self):
        e = self.primary()
        while True:
            if self.at_op("(") and self.cont():
                if e[0] != "name":
                    self.err("only a name can be called")
                self.next()
                args = []
                if not self.at_op(")"):
                    args.append(self.expr())
                    while self.at_op(","):
                        self.next()
                        args.append(self.expr())
                self.expect("op", ")")
                e = ("call", e[1], e[2], args)
            elif self.at_op("[") and self.cont():
                self.next()
                i = self.expr()
                self.expect("op", "]")
                e = ("index", e[1], e, i)
            else:
                return e

    def primary(self):
        t = self.next()
        if t.kind == "num":
            return ("num", t.line, t.val)
        if t.kind == "str":
            return ("str", t.line, t.val)
        if t.kind == "name":
            return ("name", t.line, t.val)
        if t.kind == "kw":
            if t.val == "true":
                return ("num", t.line, 1)
            if t.val == "false":
                return ("num", t.line, -1)
            if t.val == "unknown":
                return ("num", t.line, 0)
            if t.val == "table":
                self.expect("op", "(")
                items = [self.expr()]
                while self.at_op(","):
                    self.next()
                    items.append(self.expr())
                self.expect("op", ")")
                return ("table", t.line, items)
        if t.kind == "op" and t.val == "(":
            e = self.expr()
            self.expect("op", ")")
            return e
        self.err(f"unexpected {t.val!r} in expression", t)


# ----------------------------------------------------------------------
# Code generator
# ----------------------------------------------------------------------

ARITH = {"+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV", "mod": "MOD",
         "&": "AND", "|": "OR", "<<": "SHF"}
# SEL tables: the trit selected by C+1 is the truth value of the comparison.
SEL_TABLE = {"=": -7, "<>": 7, "<": -11, "<=": -5, ">": 5, ">=": 11}
JUMP_FALSE = {"=": "JNZ", "<>": "JZ", "<": "JNN", "<=": "JP", ">": "JNP",
              ">=": "JN"}
JUMP_TRUE = {"=": "JZ", "<>": "JNZ", "<": "JN", "<=": "JNP", ">": "JP",
             ">=": "JNN"}

# name: (number of arguments, description)
INTRINSICS = {
    "peek": 1, "poke": 2, "putc": 1, "getc": 0, "exit": 1, "ttyc": 1,
    "xtr": 3, "trit": 2, "clock": 0, "tally": 1, "tclear": 0,
    "rcs": 1, "wcs": 2, "rks": 1, "wks": 2, "rmap": 1, "wmap": 2,
    "heapbase": 0, "stackptr": 0, "svc": 2, "codebase": 0,
    "catchpoint": 1, "throw": 2, "codeend": 0,
}


def fits_imm(v):
    return -isa.ADDR_MAX <= v <= isa.ADDR_MAX


class Scope:
    def __init__(self, parent=None):
        self.names = {}
        self.parent = parent

    def lookup(self, n):
        s = self
        while s:
            if n in s.names:
                return s.names[n]
            s = s.parent
        return None


class ProcInfo:
    def __init__(self, name, params, body, line, file, module):
        self.name = name
        self.params = params
        self.body = body
        self.line = line
        self.file = file
        self.module = module
        self.calls = set()
        self.inline = False
        self.indirect = False
        self.loops = []


class Compiler:
    def __init__(self, include_path=None):
        self.include_path = list(include_path or []) + [LIB_DIR]
        self.out = []
        self.data = []
        self.nlabel = 0
        self.globals = Scope()
        self.procs = {}
        self.strings = {}
        self.included = set()
        self.bloop_modules = set()
        self.warnings = []

    # ---------------- utilities ----------------
    def label(self):
        self.nlabel += 1
        return f"L{self.nlabel}"

    def emit(self, s):
        self.out.append("        " + s)

    def place(self, lab):
        self.out.append(f"{lab}:")

    def err(self, node, msg):
        raise CompileError(f"{self.cur_file}:{node[1]}: {msg}")

    # ---------------- front end ----------------
    def read_module(self, name, from_dir=None):
        if name == "microkit":
            return microasm.microkit_source(), "microkit"
        if name == "isakit":
            return isakit_source(), "isakit"
        cands = []
        if from_dir:
            cands.append(os.path.join(from_dir, name))
        cands += [os.path.join(d, name) for d in self.include_path]
        for c in cands:
            for p in (c, c + ".sal"):
                if os.path.isfile(p):
                    with open(p) as f:
                        return f.read(), p
        raise CompileError(f"cannot find module {name!r}")

    def collect(self, text, fname, into):
        decls, bloop = Parser(tokenize(text, fname)).module()
        if bloop:
            self.bloop_modules.add(fname)
        base = os.path.dirname(fname) if os.path.sep in fname else None
        for d in decls:
            if d[0] == "get":
                src, path = self.read_module(d[2], base)
                key = (path if path in ("microkit", "isakit")
                       else os.path.abspath(path))
                if key not in self.included:
                    self.included.add(key)
                    self.collect(src, path, into)
            else:
                into.append((fname, d))

    def fold(self, e, scope=None):
        """Evaluate a constant expression, or return None."""
        k = e[0]
        if k == "num":
            return e[2]
        if k == "name":
            s = (scope or self.globals).lookup(e[2])
            if s and s[0] == "const":
                return s[1]
            return None
        if k == "neg":
            v = self.fold(e[2], scope)
            return None if v is None else -v
        if k == "bin":
            a, b = self.fold(e[3], scope), self.fold(e[4], scope)
            if a is None or b is None:
                return None
            op = e[2]
            from .ternary import trunc_div, trunc_mod, wrap, shift, tmin, tmax
            if op == "+":
                return wrap(a + b)
            if op == "-":
                return wrap(a - b)
            if op == "*":
                return wrap(a * b)
            if op == "/":
                return trunc_div(a, b) if b else None
            if op == "mod":
                return trunc_mod(a, b) if b else None
            if op == "<<":
                return shift(a, b)
            if op == ">>":
                return shift(a, -b)
            if op == "&":
                return tmin(wrap(a), wrap(b))
            if op == "|":
                return tmax(wrap(a), wrap(b))
        if k == "cmp":
            a, b = self.fold(e[3], scope), self.fold(e[4], scope)
            if a is None or b is None:
                return None
            return {"=": a == b, "<>": a != b, "<": a < b, "<=": a <= b,
                    ">": a > b, ">=": a >= b}[e[2]] and 1 or -1
        return None

    def compile(self, text, fname="<source>"):
        items = []
        self.included.add(os.path.abspath(fname) if os.path.exists(fname)
                          else fname)
        self.collect(text, fname, items)
        rt, rtpath = self.read_module("runtime")
        if os.path.abspath(rtpath) not in self.included:
            self.included.add(os.path.abspath(rtpath))
            self.collect(rt, rtpath, items)

        # declarations: constants first, in order, then globals and procs
        gdecls = []
        for fname_, d in items:
            self.cur_file = fname_
            kind, name = d[0], d[2]
            if kind in ("const", "global", "proc") and \
                    self.globals.lookup(name):
                self.err(d, f"{name} is declared twice")
            if kind == "const":
                v = self.fold(d[3])
                if v is None:
                    self.err(d, f"constant {name} is not a constant "
                                "expression")
                self.globals.names[name] = ("const", v)
            elif kind == "global":
                self.globals.names[name] = ("global", f"G_{name}")
                gdecls.append((fname_, d))
            elif kind == "proc":
                if name in INTRINSICS:
                    self.err(d, f"{name} is a built-in and cannot be "
                                "redefined")
                self.globals.names[name] = ("proc", f"P_{name}", len(d[3]))
                self.procs[name] = ProcInfo(name, d[3], d[4], d[1], fname_,
                                            fname_)
                self.procs[name].inline = len(d) > 6 and d[6]
        if "main" not in self.procs:
            raise CompileError("no proc main")

        self.out = ["; SALISH compiler output", "        ENTRY START",
                    "START:  CALL P_main", "        SVC  0"]
        for fname_, d in gdecls:
            self.cur_file = fname_
            self.gen_global(d)
        for p in self.procs.values():
            self.gen_proc(p)
        self.out.append("CODE_END:")
        self.out += self.data
        self.bloop_report = self.check_bloop()
        return "\n".join(self.out) + "\n"

    # ---------------- globals and static data ----------------
    def static_value(self, e):
        """Operand text for a static initialiser."""
        v = self.fold(e)
        if v is not None:
            return str(v)
        if e[0] == "str":
            return self.string_label(e[2])
        if e[0] == "table":
            return self.table_label(e)
        if e[0] == "name":
            s = self.globals.lookup(e[2])
            if s and s[0] == "proc":
                return s[1]
        if e[0] == "addr":
            s = self.globals.lookup(e[2])
            if s and s[0] == "global":
                return s[1]
        self.err(e, "initialiser must be a constant, string, table or proc")

    def string_label(self, s):
        if s not in self.strings:
            lab = f"S{len(self.strings) + 1}"
            self.strings[s] = lab
            codes = ", ".join(str(ord(c)) for c in s)
            self.data.append(f"{lab}:  DATA {len(s)}" +
                             (f", {codes}" if codes else ""))
        return self.strings[s]

    def table_label(self, e):
        lab = self.label()
        vals = [self.static_value(x) for x in e[2]]
        self.data.append(f"{lab}:  DATA {', '.join(vals)}")
        return lab

    def gen_global(self, d):
        _, line, name, size, init = d
        lab = f"G_{name}"
        if size is not None:
            n = self.fold(size)
            if n is None or n < 0:
                self.err(d, "vector size must be a non-negative constant")
            if init is not None:
                self.err(d, "a global vector cannot have an initialiser")
            self.data.append(f"{lab}:  DATA V_{name}")
            self.data.append(f"V_{name}:  BSS {n}")
        else:
            val = self.static_value(init) if init is not None else "0"
            self.data.append(f"{lab}:  DATA {val}")

    # ---------------- procedures ----------------
    def gen_proc(self, p):
        self.cur_file = p.file
        self.cur_proc = p
        self.nlocals = 0
        self.loop_stack = []
        scope = Scope(self.globals)
        n = len(p.params)
        for i, pn in enumerate(p.params):
            if pn in scope.names:
                raise CompileError(f"{p.file}:{p.line}: parameter {pn} "
                                   "repeated")
            scope.names[pn] = ("local", 2 + (n - 1 - i))
        self.ret_label = self.label()
        self.out.append(f"; proc {p.name}({', '.join(p.params)})")
        self.place(f"P_{p.name}")
        self.emit("PUSH FP")
        self.emit("LEA  FP, 0(SP)")
        frame_at = len(self.out)
        self.emit("")                     # placeholder for frame allocation
        self.gen_stmt(p.body, scope)
        self.emit("LD   R1, #0")
        self.place(self.ret_label)
        self.emit("LEA  SP, 0(FP)")
        self.emit("POP  FP")
        self.emit(f"RET  {n}" if n else "RET")
        if self.nlocals:
            self.out[frame_at] = f"        LEA  SP, -{self.nlocals}(SP)"
        else:
            del self.out[frame_at]

    def new_slot(self, size=1):
        self.nlocals += size
        return -self.nlocals

    # ---------------- statements ----------------
    def gen_stmt(self, s, scope):
        k = s[0]
        getattr(self, "s_" + k)(s, scope)

    def s_block(self, s, scope):
        inner = Scope(scope)
        for st in s[2]:
            self.gen_stmt(st, inner)

    def s_var(self, s, scope):
        for name, size, init, line in s[2]:
            if name in scope.names:
                self.err(s, f"{name} is already declared in this block")
            if size is not None:
                n = self.fold(size, scope)
                if n is None or n < 0:
                    self.err(s, "local vector size must be a constant")
                base = self.new_slot(n)
                slot = self.new_slot()
                scope.names[name] = ("local", slot)
                self.emit(f"LEA  R1, {base}(FP)")
                self.emit(f"ST   R1, {slot}(FP)")
            else:
                slot = self.new_slot()
                scope.names[name] = ("local", slot)
                if init is not None:
                    self.gen_expr(init, scope)
                    self.emit(f"ST   R1, {slot}(FP)")
                else:
                    self.emit(f"ST   R0, {slot}(FP)")

    def s_expr(self, s, scope):
        self.gen_expr(s[2], scope)

    def s_assign(self, s, scope):
        target, rhs = s[2], s[3]
        if target[0] == "name":
            op = self.var_operand(target, scope, store=True)
            self.gen_expr(rhs, scope)
            self.emit(f"ST   R1, {op}")
            return
        vec, idx = target[2], target[3]
        ci = self.fold(idx, scope)
        vop = self.simple(vec, scope)
        if ci is not None and vop is not None and fits_imm(ci):
            self.gen_expr(rhs, scope)
            self.emit(f"LD   R2, {vop}")
            self.emit(f"ST   R1, {ci}(R2)")
            return
        rop = self.simple(rhs, scope)
        if rop is not None:
            self.gen_index_addr(vec, idx, scope)
            self.emit(f"LD   R2, {rop}")
            self.emit("ST   R2, 0(R1)")
            return
        self.gen_expr(rhs, scope)
        self.emit("PUSH R1")
        self.gen_index_addr(vec, idx, scope)
        self.emit("POP  R2")
        self.emit("ST   R2, 0(R1)")

    def s_if(self, s, scope):
        _, line, c, a, b = s
        lelse = self.label()
        self.gen_cond(c, lelse, scope)
        self.gen_stmt(a, Scope(scope))
        if b is not None:
            lend = self.label()
            self.emit(f"JMP  {lend}")
            self.place(lelse)
            self.gen_stmt(b, Scope(scope))
            self.place(lend)
        else:
            self.place(lelse)

    def s_while(self, s, scope):
        self.cur_proc.loops.append(("while", s[1]))
        top, end = self.label(), self.label()
        self.place(top)
        self.gen_cond(s[2], end, scope)
        self.loop_stack.append((end, top))
        self.gen_stmt(s[3], Scope(scope))
        self.loop_stack.pop()
        self.emit(f"JMP  {top}")
        self.place(end)

    def s_repeat(self, s, scope):
        self.cur_proc.loops.append(("repeat", s[1]))
        top, test, end = self.label(), self.label(), self.label()
        self.place(top)
        self.loop_stack.append((end, test))
        self.gen_stmt(s[2], Scope(scope))
        self.loop_stack.pop()
        self.place(test)
        self.gen_cond(s[3], top, scope)
        self.place(end)

    def s_for(self, s, scope):
        _, line, v, a, b, step, body = s
        st = self.fold(step, scope)
        if st == 0:
            self.err(s, "the step of a for loop must not be zero")
        inner = Scope(scope)
        slot = self.new_slot()
        lim = self.new_slot()
        stslot = None
        self.gen_expr(a, scope)
        self.emit(f"ST   R1, {slot}(FP)")
        self.gen_expr(b, scope)
        self.emit(f"ST   R1, {lim}(FP)")
        if st is None:
            # a step computed at run time is fixed on entry to the loop
            stslot = self.new_slot()
            self.gen_expr(step, scope)
            self.emit(f"ST   R1, {stslot}(FP)")
        inner.names[v] = ("local", slot, "loopvar")
        top, cont, end = self.label(), self.label(), self.label()
        self.place(top)
        if st is not None:
            self.emit(f"LD   R1, {slot}(FP)")
            self.emit(f"CMP  R1, {lim}(FP)")
            self.emit(f"{'JP ' if st > 0 else 'JN '}  {end}")
        else:
            up, go = self.label(), self.label()
            self.emit(f"TST  {stslot}(FP)")
            self.emit(f"JZ   {end}")
            self.emit(f"JP   {up}")
            self.emit(f"LD   R1, {slot}(FP)")
            self.emit(f"CMP  R1, {lim}(FP)")
            self.emit(f"JN   {end}")
            self.emit(f"JMP  {go}")
            self.place(up)
            self.emit(f"LD   R1, {slot}(FP)")
            self.emit(f"CMP  R1, {lim}(FP)")
            self.emit(f"JP   {end}")
            self.place(go)
        self.loop_stack.append((end, cont))
        self.gen_stmt(body, inner)
        self.loop_stack.pop()
        self.place(cont)
        self.emit(f"LD   R1, {slot}(FP)")
        self.emit(f"ADD  R1, {self.imm(st) if st is not None else f'{stslot}(FP)'}")
        self.emit(f"ST   R1, {slot}(FP)")
        self.emit(f"JMP  {top}")
        self.place(end)

    def s_sign(self, s, scope):
        _, line, e, arms = s
        self.gen_test(e, scope)
        tbl, end = self.label(), self.label()
        labs = {k: (self.label() if k in arms else end) for k in (-1, 0, 1)}
        self.emit(f"J3   {tbl}")
        self.emit(f"JMP  {labs[-1]}")
        self.place(tbl)
        self.emit(f"JMP  {labs[0]}")
        self.emit(f"JMP  {labs[1]}")
        for k in (-1, 0, 1):
            if k in arms:
                self.place(labs[k])
                self.gen_stmt(arms[k], Scope(scope))
                self.emit(f"JMP  {end}")
        self.place(end)

    def s_return(self, s, scope):
        if s[2] is not None:
            self.gen_expr(s[2], scope)
        else:
            self.emit("LD   R1, #0")
        self.emit(f"JMP  {self.ret_label}")

    def s_break(self, s, scope):
        if not self.loop_stack:
            self.err(s, "break outside a loop")
        self.emit(f"JMP  {self.loop_stack[-1][0]}")

    def s_next(self, s, scope):
        if not self.loop_stack:
            self.err(s, "next outside a loop")
        self.emit(f"JMP  {self.loop_stack[-1][1]}")

    # ---------------- conditions ----------------
    def gen_test(self, e, scope):
        """Set C to the sign of e."""
        if e[0] == "bin" and e[2] == "-":
            self.gen_compare(e[3], e[4], scope)
        elif e[0] == "cmp":
            self.gen_expr(e, scope)
            self.emit("TST  #0(R1)")
        else:
            self.gen_expr(e, scope)
            self.emit("TST  #0(R1)")

    def gen_compare(self, a, b, scope):
        op = self.simple(b, scope)
        if op is not None:
            self.gen_expr(a, scope)
            self.emit(f"CMP  R1, {op}")
        else:
            self.gen_expr(b, scope)
            self.emit("PUSH R1")
            self.gen_expr(a, scope)
            self.emit("POP  R2")
            self.emit("CMP  R1, #0(R2)")

    def gen_cond(self, e, false_lab, scope):
        """Jump to false_lab unless e is true (positive)."""
        while e[0] == "call":
            s = scope.lookup(e[2])
            if not (s and s[0] == "proc" and self.procs[e[2]].inline):
                break
            e = self.expand_inline(e, scope)
        k = e[0]
        v = self.fold(e, scope)
        if v is not None:
            if v <= 0:
                self.emit(f"JMP  {false_lab}")
            return
        if k == "cmp":
            self.gen_compare(e[3], e[4], scope)
            self.emit(f"{JUMP_FALSE[e[2]]:4} {false_lab}")
        elif k == "and":
            self.gen_cond(e[2], false_lab, scope)
            self.gen_cond(e[3], false_lab, scope)
        elif k == "or":
            true_lab = self.label()
            if e[2][0] == "cmp":
                a = e[2]
                self.gen_compare(a[3], a[4], scope)
                self.emit(f"{JUMP_TRUE[a[2]]:4} {true_lab}")
            else:
                self.gen_expr(e[2], scope)
                self.emit("TST  #0(R1)")
                self.emit(f"JP   {true_lab}")
                self.emit(f"JZ   {false_lab}")
            self.gen_cond(e[3], false_lab, scope)
            self.place(true_lab)
        elif k == "neg" and self.inline_cmp(e[2], scope) is not None:
            a = self.inline_cmp(e[2], scope)
            self.gen_compare(a[3], a[4], scope)
            self.emit(f"{JUMP_TRUE[a[2]]:4} {false_lab}")
        else:
            self.gen_expr(e, scope)
            self.emit("TST  #0(R1)")
            self.emit(f"JNP  {false_lab}")

    # ---------------- expressions ----------------
    def imm(self, v):
        return f"#{v}" if fits_imm(v) else f"={v}"

    def var_operand(self, e, scope, store=False):
        n = e[2]
        s = scope.lookup(n)
        if s is None:
            self.err(e, f"undeclared name {n}")
        if s[0] == "local":
            if store and len(s) > 2 and self.cur_file in self.bloop_modules:
                self.err(e, f"BlooP: loop variable {n} may not be assigned")
            return f"{s[1]}(FP)"
        if s[0] == "global":
            return s[1]
        self.err(e, f"cannot assign to {n}")

    def simple(self, e, scope):
        """Operand text if e can be a direct instruction operand."""
        v = self.fold(e, scope)
        if v is not None:
            return self.imm(v)
        k = e[0]
        if k == "name":
            s = scope.lookup(e[2])
            if s is None:
                self.err(e, f"undeclared name {e[2]}")
            if s[0] == "local":
                return f"{s[1]}(FP)"
            if s[0] == "global":
                return s[1]
            if s[0] == "proc":
                return f"#{s[1]}"
        if k == "str":
            return f"#{self.string_label(e[2])}"
        if k == "table":
            return f"#{self.table_label(e)}"
        return None

    def gen_expr(self, e, scope):
        op = self.simple(e, scope)
        if op is not None:
            self.emit(f"LD   R1, {op}")
            return
        k = e[0]
        if k == "neg":
            a = self.simple(e[2], scope)
            if a is not None:
                self.emit(f"NEG  R1, {a}")
            else:
                self.gen_expr(e[2], scope)
                self.emit("NEG  R1, #0(R1)")
        elif k == "addr":
            s = scope.lookup(e[2])
            if s is None:
                self.err(e, f"undeclared name {e[2]}")
            if s[0] == "local":
                self.emit(f"LEA  R1, {s[1]}(FP)")
            elif s[0] in ("global", "proc"):
                self.emit(f"LD   R1, #{s[1]}")
            else:
                self.err(e, "cannot take the address of a constant")
        elif k == "bin":
            self.gen_binary(e, scope)
        elif k == "cmp":
            self.gen_compare(e[3], e[4], scope)
            self.emit(f"SEL  R1, #{SEL_TABLE[e[2]]}")
        elif k == "and" or k == "or":
            end = self.label()
            self.gen_expr(e[2], scope)
            self.emit("TST  #0(R1)")
            self.emit(f"{'JNP' if k == 'and' else 'JNN'}  {end}")
            self.gen_expr(e[3], scope)
            self.place(end)
        elif k == "cond":
            lelse, lend = self.label(), self.label()
            self.gen_cond(e[2], lelse, scope)
            self.gen_expr(e[3], scope)
            self.emit(f"JMP  {lend}")
            self.place(lelse)
            self.gen_expr(e[4], scope)
            self.place(lend)
        elif k == "call":
            self.gen_call(e, scope)
        elif k == "index":
            vec, idx = e[2], e[3]
            ci = self.fold(idx, scope)
            vop = self.simple(vec, scope)
            if ci is not None and vop is not None and fits_imm(ci):
                self.emit(f"LD   R2, {vop}")
                self.emit(f"LD   R1, {ci}(R2)")
            else:
                self.gen_index_addr(vec, idx, scope)
                self.emit("LD   R1, 0(R1)")
        else:
            self.err(e, f"cannot compile expression {k}")

    def gen_index_addr(self, vec, idx, scope):
        vop = self.simple(vec, scope)
        if vop is not None:
            self.gen_expr(idx, scope)
            self.emit(f"ADD  R1, {vop}")
        else:
            iop = self.simple(idx, scope)
            if iop is not None:
                self.gen_expr(vec, scope)
                self.emit(f"ADD  R1, {iop}")
            else:
                self.gen_expr(idx, scope)
                self.emit("PUSH R1")
                self.gen_expr(vec, scope)
                self.emit("POP  R2")
                self.emit("ADD  R1, #0(R2)")

    def gen_binary(self, e, scope):
        _, line, op, a, b = e
        if op == ">>":
            cb = self.fold(b, scope)
            if cb is not None:
                self.gen_expr(a, scope)
                self.emit(f"SHF  R1, {self.imm(-cb)}")
                return
            self.gen_expr(b, scope)
            self.emit("NEG  R1, #0(R1)")
            self.emit("PUSH R1")
            self.gen_expr(a, scope)
            self.emit("POP  R2")
            self.emit("SHF  R1, #0(R2)")
            return
        ins = ARITH[op]
        bop = self.simple(b, scope)
        if bop is not None:
            self.gen_expr(a, scope)
            self.emit(f"{ins:4} R1, {bop}")
        else:
            self.gen_expr(b, scope)
            self.emit("PUSH R1")
            self.gen_expr(a, scope)
            self.emit("POP  R2")
            self.emit(f"{ins:4} R1, #0(R2)")

    def gen_args_to_regs(self, args, scope):
        """Evaluate args; leave the last in R1 and the others in R2, R3..."""
        n = len(args)
        for a in args:
            self.gen_expr(a, scope)
            self.emit("PUSH R1")
        for i in range(n, 0, -1):
            self.emit(f"POP  R{i}")

    def gen_call(self, e, scope):
        _, line, name, args = e
        s = scope.lookup(name)
        if s is None and name in INTRINSICS:
            return self.gen_intrinsic(e, scope)
        if s is None:
            self.err(e, f"undeclared procedure {name}")
        if s[0] == "proc" and self.procs[name].inline:
            return self.gen_expr(self.expand_inline(e, scope), scope)
        for a in args:
            self.gen_expr(a, scope)
            self.emit("PUSH R1")
        if s[0] == "proc":
            if s[2] != len(args):
                self.err(e, f"{name} takes {s[2]} arguments, "
                            f"given {len(args)}")
            self.cur_proc.calls.add(name)
            self.emit(f"CALL {s[1]}")
        else:
            self.cur_proc.indirect = True
            op = self.var_operand(("name", line, name), scope)
            self.emit(f"LD   R2, {op}")
            self.emit("CALL 0(R2)")          # the callee pops its arguments

    def inline_cmp(self, e, scope):
        """If e is (or inlines to) a comparison, return the comparison."""
        while e[0] == "call":
            s = scope.lookup(e[2])
            if not (s and s[0] == "proc" and self.procs[e[2]].inline):
                return None
            e = self.expand_inline(e, scope)
        return e if e[0] == "cmp" else None

    def expand_inline(self, e, scope):
        """Return the body of an inline proc with its parameters replaced.
        A simple argument (a constant or variable) is substituted directly;
        any other argument is first evaluated into a fresh local."""
        _, line, name, args = e
        p = self.procs[name]
        if len(args) != len(p.params):
            self.err(e, f"{name} takes {len(p.params)} arguments, "
                        f"given {len(args)}")
        self.inline_depth = getattr(self, "inline_depth", 0) + 1
        if self.inline_depth > 20:
            self.err(e, f"inline expansion of {name} does not terminate")
        self.cur_proc.calls.add(name)
        subst = {}
        for pn, a in zip(p.params, args):
            if self.fold(a, scope) is not None or a[0] == "name":
                subst[pn] = a
            else:
                slot = self.new_slot()
                tmp = f".t{slot}"
                scope.names[tmp] = ("local", slot)
                self.gen_expr(a, scope)
                self.emit(f"ST   R1, {slot}(FP)")
                subst[pn] = ("name", line, tmp)

        def rewrite(n):
            if isinstance(n, tuple):
                if n and n[0] == "name" and n[2] in subst:
                    return subst[n[2]]
                if n and n[0] == "addr" and n[2] in subst:
                    self.err(e, "cannot take the address of an inline "
                                "parameter")
                return tuple(rewrite(x) for x in n)
            if isinstance(n, list):
                return [rewrite(x) for x in n]
            return n
        body = rewrite(p.body[2])
        self.inline_depth -= 1
        return body

    def gen_intrinsic(self, e, scope):
        _, line, name, args = e
        if INTRINSICS[name] != len(args):
            self.err(e, f"{name} takes {INTRINSICS[name]} arguments")
        if name == "peek":
            self.gen_expr(args[0], scope)
            self.emit("LD   R1, 0(R1)")
        elif name == "poke":
            self.gen_args_to_regs(args, scope)      # R1 = address, R2 = value
            self.emit("ST   R2, 0(R1)")
        elif name == "putc":
            self.gen_expr(args[0], scope)
            self.emit("SVC  1")
        elif name == "getc":
            self.emit("SVC  2")
        elif name == "exit":
            self.gen_expr(args[0], scope)
            self.emit("SVC  0")
        elif name == "ttyc":
            self.gen_expr(args[0], scope)
            self.emit("SVC  3")
        elif name == "svc":
            n = self.fold(args[0], scope)
            if n is None:
                self.err(e, "svc number must be constant")
            self.gen_expr(args[1], scope)
            self.emit(f"SVC  {n}")
        elif name == "xtr":
            p, n = self.fold(args[1], scope), self.fold(args[2], scope)
            if p is not None and n is not None:
                self.gen_expr(args[0], scope)
                self.emit(f"XTR  R1, #{27 * n + p}")
            else:
                self.gen_expr(args[2], scope)
                self.emit("MUL  R1, #27")
                self.emit("PUSH R1")
                self.gen_expr(args[1], scope)
                self.emit("POP  R2")
                self.emit("ADD  R2, #0(R1)")
                self.emit("PUSH R2")
                self.gen_expr(args[0], scope)
                self.emit("POP  R2")
                self.emit("XTR  R1, #0(R2)")
        elif name == "trit":
            self.gen_args_to_regs(args, scope)       # R1 = value, R2 = pos
            self.emit("TRT  R1, #0(R2)")
            self.emit("SEL  R1, #8")
        elif name == "clock":
            self.emit("TIM  R1")
        elif name == "tally":
            self.gen_expr(args[0], scope)
            self.emit("TAL  R1, 0(R1)")
        elif name == "tclear":
            self.emit("TCL")
        elif name in ("rcs", "rks", "rmap"):
            self.gen_expr(args[0], scope)
            self.emit(f"{name.upper():4} R1, 0(R1)")
        elif name in ("wcs", "wks", "wmap"):
            self.gen_args_to_regs(args, scope)       # R1 = addr, R2 = value
            self.emit(f"{name.upper():4} R2, 0(R1)")
        elif name == "heapbase":
            self.emit("LD   R1, #END_OF_PROGRAM")
        elif name == "codebase":
            self.emit("LD   R1, #START")
        elif name == "codeend":
            self.emit("LD   R1, #CODE_END")
        elif name == "stackptr":
            self.emit("LD   R1, #0(SP)")
        elif name == "catchpoint":
            # save FP, SP and a resume address; returns 0 now, and later
            # returns again with the value given to throw
            self.cur_proc.indirect = True
            resume = self.label()
            self.gen_expr(args[0], scope)
            self.emit("ST   FP, 0(R1)")
            self.emit("ST   SP, 1(R1)")
            self.emit(f"LD   R2, #{resume}")
            self.emit("ST   R2, 2(R1)")
            self.emit("LD   R1, #0")
            self.place(resume)
        elif name == "throw":
            self.cur_proc.indirect = True
            self.gen_args_to_regs(args, scope)       # R1 = buffer, R2 = value
            self.emit("LD   FP, 0(R1)")
            self.emit("LD   SP, 1(R1)")
            self.emit("LD   R3, 2(R1)")
            self.emit("LD   R1, #0(R2)")
            self.emit("JMP  0(R3)")

    # ---------------- BlooP certification ----------------
    def check_bloop(self):
        """For each bloop module, verify its procedures (and everything they
        call) are free of unbounded loops, recursion and indirect calls."""
        if not self.bloop_modules:
            return None
        problems = []
        # recursion: find cycles in the call graph
        state = {}

        def visit(n, path):
            state[n] = 1
            for m in sorted(self.procs[n].calls):
                if state.get(m) == 1:
                    cyc = path[path.index(m):] + [m] if m in path else [n, m]
                    problems.append(f"recursion: {' -> '.join(cyc)}")
                elif m not in state:
                    visit(m, path + [m])
            state[n] = 2

        # "bloop" certifies the whole program: everything main can reach
        roots = ["main"]
        reach = set()
        stack = list(roots)
        while stack:
            n = stack.pop()
            if n in reach:
                continue
            reach.add(n)
            stack.extend(self.procs[n].calls)
        for n in sorted(reach):
            if n not in state:
                visit(n, [n])
            p = self.procs[n]
            for kind, line in p.loops:
                problems.append(f"{kind} loop in {n} ({p.file}:{line})")
            if p.indirect:
                problems.append(f"call through a variable in {n}")
        if problems:
            raise CompileError("BlooP certification failed:\n  " +
                               "\n  ".join(problems))
        return (f"BlooP certificate: {len(reach)} procedures reachable, "
                "all loops bounded on entry, no recursion, no indirect "
                "calls.  Every run of this program terminates.")


def isakit_source():
    """A SALISH include file describing the instruction set, generated from
    the same table the assembler uses, so that programs can read (and
    write) their own machine code."""
    lines = ["-- isakit: generated from duwamish/isa.py"]
    for k in ("OP_POS", "R_POS", "X_POS", "M_POS"):
        lines.append(f"const I_{k} = {getattr(isa, k)}")
    top = max(isa.BY_OP)
    lines.append(f"const I_MAXOP = {top}")
    for op, name, form, _ in isa.OPCODES:
        lines.append(f"const OP_{name} = {op}")
    forms = {"RE": 1, "E": 2, "R": 3, "RA": 4, "I": 5, "N": 6}
    names = ", ".join('"' + isa.BY_OP.get(i, ("?", ""))[0] + '"'
                      for i in range(top + 1))
    fcodes = ", ".join(str(forms.get(isa.BY_OP.get(i, ("", ""))[1], 0))
                       for i in range(top + 1))
    lines.append(f"global op_names := table({names})")
    lines.append(f"global op_forms := table({fcodes})")
    enders = ", ".join(str(1 if i in isa.BLOCK_ENDERS else 0)
                       for i in range(top + 1))
    lines.append(f"global op_ends_block := table({enders})")
    return "\n".join(lines) + "\n"


def compile_source(text, fname="<source>", include_path=None):
    """Compile SALISH text to TRIAD assembly.  Returns (asm_text, compiler)."""
    c = Compiler(include_path)
    asm = c.compile(text, fname)
    return asm, c
