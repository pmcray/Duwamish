"""TRI-TRAN: the Duwamish FORTRAN.

A compiler for a dialect of FORTRAN (USA Standard X3.9-1966), running on
the satellite and producing TRIAD assembly, as the SALISH compiler does.
The committee's view (docs/TRITRAN.md) was that SALISH is for writing
systems, and that the laboratories who were to buy the machine would
arrive with their programs in FORTRAN.  So the Duwamish has a FORTRAN,
and it is a FORTRAN of 1966: fixed-form cards, blanks that mean nothing,
implicit types, static storage, arguments by reference, DO loops that
always run at least once, and FORMAT.

What is ternary about it:

* LOGICAL is three-valued.  .TRUE., .FALSE. and .UNKNOWN. are +1, -1 and
  0; .AND., .OR., .NOT. and .EQV. are Kleene's, one instruction each.
  A logical IF obeys its statement only when the condition is .TRUE.
* The arithmetic IF, IF (e) n1, n2, n3, is the Duwamish's J3
  instruction: one three-way jump, where a binary machine needs two.
* REAL is the floating-point unit's 27-trit word: TRI-TRAN needs the
  unit, as FORTRAN needed the 704's.
* FORMAT has two descriptors more: Bw writes an integer in balanced
  ternary, and Lw writes T, F or U.

What is FORTRAN I about it: every DO loop's index is kept in an index
register, R3 to R6, when the loop allows it, so A(I) is one operand,
A-1(R3).  (Backus's team built that into the first compiler; they held
that FORTRAN would be used only if its object programs were nearly as good
as hand-coded ones.)

The run-time library -- FORMAT, the mathematical functions -- is written
in SALISH (duwamish/lib/tritran.sal) and compiled by SALISH/O.  TRI-TRAN
calls it with SALISH's calling convention.

    compile_source(text, fname) -> (TRIAD text, Compiler)
"""

import os
import re
from fractions import Fraction

from . import fpu
from . import isa
from . import salish
from . import ternary as t

HERE = os.path.dirname(__file__)
LIBRARY = os.path.join(HERE, "lib", "tritran.sal")
ADDR_MAX = isa.ADDR_MAX
WMAX = t.WMAX
REGS = ("R3", "R4", "R5", "R6")
MAIN = "_MAIN"


class CompileError(Exception):
    pass


# ======================================================================
#  Cards
# ======================================================================
class Statement:
    def __init__(self, label, text, raw, line):
        self.label = label        # statement number, or None
        self.text = text          # upper case, blanks removed (not in '...')
        self.raw = raw            # columns 7-72, blanks kept
        self.line = line          # card number of its first card
        self.kind = None
        self.args = None


def _squeeze(s):
    """Upper case with the blanks removed, except inside '...'."""
    out, q = [], False
    for ch in s:
        if ch == "'":
            q = not q
            out.append(ch)
        elif q:
            out.append(ch)
        elif ch not in " \t":
            out.append(ch.upper())
    return "".join(out)


def read_cards(text, fname):
    """Fixed form: C or * in column 1 is a comment; columns 1-5 hold the
    statement number; anything but a blank or 0 in column 6 continues the
    card before; the statement is in columns 7-72.  (Columns 73-80 were
    for sequence numbers, and are ignored.)  A tab in the first six
    columns skips to column 7, as DEC's compilers allowed."""
    stmts = []
    for n, card in enumerate(text.splitlines(), 1):
        if card[:1] in ("C", "c", "*"):
            continue
        if not card.strip():
            continue
        if "\t" in card[:6]:
            i = card.index("\t")
            head = card[:i]
            rest = card[i + 1:]
            if rest[:1].isdigit() and rest[:1] != "0" and not head.strip():
                card = " " * 5 + rest[0] + rest[1:]
            else:
                card = head.ljust(6) + rest
        card = card[:72]
        lab, cont, body = card[:5], card[5:6], card[6:]
        if cont.strip() and cont != "0":
            if not stmts:
                raise CompileError(f"{fname}:{n}: continuation card with "
                                   "nothing to continue")
            if lab.strip():
                raise CompileError(f"{fname}:{n}: a continuation card "
                                   "cannot have a statement number")
            stmts[-1].raw += body
            continue
        label = None
        if lab.strip():
            if not lab.strip().isdigit():
                raise CompileError(f"{fname}:{n}: bad statement number "
                                   f"{lab.strip()!r}")
            label = int(lab.strip())
            if label == 0:
                raise CompileError(f"{fname}:{n}: statement number 0")
        stmts.append(Statement(label, "", body, n))
    for s in stmts:
        s.text = _squeeze(s.raw)
    return stmts


# ======================================================================
#  Tokens and expressions
# ======================================================================
DOTOPS = ("EQ", "NE", "LT", "LE", "GT", "GE", "AND", "OR", "NOT", "EQV",
          "NEQV", "TRUE", "FALSE", "UNKNOWN")
_DOT = re.compile(r"\.(" + "|".join(DOTOPS) + r")\.")
_NUM = re.compile(r"\d*\.?\d*")


class Tok:
    def __init__(self, kind, val):
        self.kind = kind          # name int real dot op log
        self.val = val

    def __repr__(self):
        return f"{self.kind}:{self.val}"


def tokenize(s, err):
    toks = []
    i = 0
    while i < len(s):
        c = s[i]
        if c.isalpha():
            j = i
            while j < len(s) and s[j].isalnum():
                j += 1
            toks.append(Tok("name", s[i:j]))
            i = j
        elif c.isdigit() or (c == "." and i + 1 < len(s) and s[i + 1].isdigit()):
            j = i
            while j < len(s) and s[j].isdigit():
                j += 1
            real = False
            if j < len(s) and s[j] == "." and not _DOT.match(s, j):
                real = True
                j += 1
                while j < len(s) and s[j].isdigit():
                    j += 1
            if j < len(s) and s[j] in "ED":
                k = j + 1
                if k < len(s) and s[k] in "+-":
                    k += 1
                if k < len(s) and s[k].isdigit():
                    real = True
                    while k < len(s) and s[k].isdigit():
                        k += 1
                    j = k
            text = s[i:j].replace("D", "E")
            if real:
                toks.append(Tok("real", text))
            else:
                toks.append(Tok("int", int(text)))
            i = j
        elif c == ".":
            m = _DOT.match(s, i)
            if not m:
                err(f"cannot understand {s[i:i + 8]!r}")
            w = m.group(1)
            if w in ("TRUE", "FALSE", "UNKNOWN"):
                toks.append(Tok("log", {"TRUE": 1, "FALSE": -1,
                                        "UNKNOWN": 0}[w]))
            else:
                toks.append(Tok("dot", w))
            i = m.end()
        elif s.startswith("**", i):
            toks.append(Tok("op", "**"))
            i += 2
        elif c in "+-*/(),=":
            toks.append(Tok("op", c))
            i += 1
        elif c == "'":
            err("a quoted string may appear only in a FORMAT")
        else:
            err(f"unexpected character {c!r}")
    return toks


class Parser:
    """Expressions, by precedence (loosest first): .EQV. .NEQV., .OR.,
    .AND., .NOT., relations, + -, * /, **, unary."""

    def __init__(self, toks, err):
        self.toks = toks
        self.i = 0
        self.err = err

    def peek(self, k=0):
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else None

    def at(self, kind, val=None):
        tk = self.peek()
        return tk is not None and tk.kind == kind and (val is None
                                                       or tk.val == val)

    def take(self):
        tk = self.peek()
        if tk is None:
            self.err("statement ends too soon")
        self.i += 1
        return tk

    def expect(self, kind, val=None):
        if not self.at(kind, val):
            tk = self.peek()
            self.err(f"expected {val or kind}, found "
                     f"{tk.val if tk else 'the end of the statement'}")
        return self.take()

    def done(self):
        return self.i >= len(self.toks)

    def end(self):
        if not self.done():
            self.err(f"unexpected {self.peek().val!r}")

    def name(self):
        return self.expect("name").val

    def expr(self):
        a = self.or_()
        while self.at("dot", "EQV") or self.at("dot", "NEQV"):
            op = self.take().val
            a = ("logop", op, a, self.or_())
        return a

    def or_(self):
        a = self.and_()
        while self.at("dot", "OR"):
            self.take()
            a = ("logop", "OR", a, self.and_())
        return a

    def and_(self):
        a = self.not_()
        while self.at("dot", "AND"):
            self.take()
            a = ("logop", "AND", a, self.not_())
        return a

    def not_(self):
        if self.at("dot", "NOT"):
            self.take()
            return ("not", self.not_())
        return self.rel()

    def rel(self):
        a = self.add()
        if self.peek() and self.peek().kind == "dot" and self.peek().val in (
                "EQ", "NE", "LT", "LE", "GT", "GE"):
            op = self.take().val
            return ("rel", op, a, self.add())
        return a

    def add(self):
        if self.at("op", "-") or self.at("op", "+"):
            sign = self.take().val
            a = self.mul()
            if sign == "-":
                a = ("neg", a)
        else:
            a = self.mul()
        while self.at("op", "+") or self.at("op", "-"):
            op = self.take().val
            a = ("arith", op, a, self.mul())
        return a

    def mul(self):
        a = self.power()
        while self.at("op", "*") or self.at("op", "/"):
            op = self.take().val
            a = ("arith", op, a, self.power())
        return a

    def power(self):
        a = self.primary()
        if self.at("op", "**"):
            self.take()
            if self.at("op", "-") or self.at("op", "+"):
                sign = self.take().val
                b = self.power()
                if sign == "-":
                    b = ("neg", b)
            else:
                b = self.power()
            return ("pow", a, b)
        return a

    def primary(self):
        tk = self.take()
        if tk.kind == "int":
            return ("int", tk.val)
        if tk.kind == "real":
            return ("real", tk.val)
        if tk.kind == "log":
            return ("log", tk.val)
        if tk.kind == "op" and tk.val == "(":
            e = self.expr()
            self.expect("op", ")")
            return e
        if tk.kind == "op" and tk.val in "+-":
            e = self.power()
            return ("neg", e) if tk.val == "-" else e
        if tk.kind == "name":
            if self.at("op", "("):
                self.take()
                args = []
                if not self.at("op", ")"):
                    args.append(self.expr())
                    while self.at("op", ","):
                        self.take()
                        args.append(self.expr())
                self.expect("op", ")")
                return ("ref", tk.val, args)
            return ("name", tk.val)
        self.err(f"unexpected {tk.val!r} in an expression")


# ======================================================================
#  Symbols and program units
# ======================================================================
class Sym:
    def __init__(self, name, type_):
        self.name = name
        self.type = type_          # 'I', 'R', 'L'
        self.explicit = False
        self.dims = None           # list of int or ('var', name)
        self.dummy = None          # argument index, or None
        self.common = None         # (block, offset)
        self.external = False      # named in EXTERNAL
        self.result = False        # a function's result variable
        self.used = False
        self.data = {}             # offset -> word, from DATA

    @property
    def is_array(self):
        return self.dims is not None

    def size(self):
        n = 1
        for d in self.dims or []:
            if not isinstance(d, int):
                return None
            n *= d
        return n


def implicit(name):
    return "I" if name[0] in "IJKLMN" else "R"


# intrinsic functions: name -> (argument type, result type, arity or -2 for
# two or more, library routine or None for in-line)
INTRINSICS = {
    "ABS": ("R", "R", 1, None), "IABS": ("I", "I", 1, None),
    "FLOAT": ("I", "R", 1, None), "IFIX": ("R", "I", 1, "tt_ifix"),
    "INT": ("R", "I", 1, "tt_ifix"), "NINT": ("R", "I", 1, None),
    "AINT": ("R", "R", 1, "tt_aint"),
    "MOD": ("I", "I", 2, None), "AMOD": ("R", "R", 2, "tt_amod"),
    "SIGN": ("R", "R", 2, "tt_sign"), "ISIGN": ("I", "I", 2, "tt_isign"),
    "DIM": ("R", "R", 2, "tt_dim"), "IDIM": ("I", "I", 2, "tt_idim"),
    "MAX0": ("I", "I", -2, None), "MIN0": ("I", "I", -2, None),
    "AMAX1": ("R", "R", -2, None), "AMIN1": ("R", "R", -2, None),
    "AMAX0": ("I", "R", -2, None), "AMIN0": ("I", "R", -2, None),
    "MAX1": ("R", "I", -2, None), "MIN1": ("R", "I", -2, None),
    "SQRT": ("R", "R", 1, "tt_sqrt"), "EXP": ("R", "R", 1, "tt_exp"),
    "ALOG": ("R", "R", 1, "tt_alog"), "ALOG10": ("R", "R", 1, "tt_alog10"),
    "SIN": ("R", "R", 1, "tt_sin"), "COS": ("R", "R", 1, "tt_cos"),
    "TANH": ("R", "R", 1, "tt_tanh"), "ATAN": ("R", "R", 1, "tt_atan"),
    "ATAN2": ("R", "R", 2, "tt_atan2"),
    # Duwamish additions
    "ICLOCK": (None, "I", 0, None),      # the cycle clock
    "ITRIT": ("I", "I", 2, None),        # ITRIT(N, K): trit K of N
}

# CMP, then SEL with one of these: trit C+1 of the table is the answer
SEL_TABLE = {"LT": -11, "LE": -5, "EQ": -7, "NE": 7, "GT": 5, "GE": 11}
JUMP_FALSE = {"EQ": "JNZ", "NE": "JZ", "LT": "JNN", "LE": "JP", "GT": "JNP",
              "GE": "JN"}
JUMP_TRUE = {"EQ": "JZ", "NE": "JNZ", "LT": "JN", "LE": "JNP", "GT": "JP",
             "GE": "JNN"}
INVERSE = {"JN": "JNN", "JNN": "JN", "JZ": "JNZ", "JNZ": "JZ", "JP": "JNP",
           "JNP": "JP"}
REL_SWAP = {"LT": "GT", "LE": "GE", "GT": "LT", "GE": "LE", "EQ": "EQ",
            "NE": "NE"}


def real_word(text):
    """The Duwamish float nearest a decimal constant."""
    m = re.fullmatch(r"([+-]?)(\d*)(?:\.(\d*))?(?:E([+-]?\d+))?", text)
    ip, fp, ex = m.group(2) or "0", m.group(3) or "", int(m.group(4) or 0)
    v = Fraction(int(ip + fp or "0"), 10 ** len(fp)) * Fraction(10) ** ex
    return fpu.normalise(-v if m.group(1) == "-" else v)


class Unit:
    def __init__(self, kind, name, params, type_=None, line=0):
        self.kind = kind           # 'main', 'sub', 'func'
        self.name = name
        self.params = params
        self.line = line
        self.syms = {}
        self.stmts = []            # executable statements
        self.formats = {}          # label -> encoded words
        self.stfuncs = {}          # name -> (params, expr)
        self.commons = {}          # block -> [names]
        self.type = type_
        self.prefix = MAIN if kind == "main" else name
        self.entry = MAIN if kind == "main" else f"F_{name}"


# ======================================================================
#  FORMAT
# ======================================================================
F_END, F_I, F_F, F_E, F_X, F_H, F_SLASH, F_L, F_B, F_GROUP, F_ENDGROUP = \
    range(11)


def parse_format(raw, err):
    """FORMAT (...) from the raw card text (blanks matter in Hollerith).
    Returns the encoded words: word 0 is where reversion restarts."""
    i = raw.upper().index("FORMAT") + 6
    s = raw

    def skip():
        nonlocal i
        while i < len(s) and s[i] in " \t":
            i += 1

    def number():
        nonlocal i
        skip()
        j = i
        while i < len(s) and s[i].isdigit():
            i += 1
            skip()
        digits = s[j:i].replace(" ", "")
        return int(digits) if digits else None

    codes = []
    top_groups = []

    def items(depth):
        nonlocal i
        while True:
            skip()
            if i >= len(s):
                err("FORMAT: missing )")
            c = s[i]
            if c == ")":
                i += 1
                return
            if c == ",":
                i += 1
                continue
            if c == "/":
                codes.append(F_SLASH)
                i += 1
                continue
            if c == "'":
                j = i + 1
                text = ""
                while True:
                    if j >= len(s):
                        err("FORMAT: unterminated string")
                    if s[j] == "'":
                        if j + 1 < len(s) and s[j + 1] == "'":
                            text += "'"
                            j += 2
                            continue
                        break
                    text += s[j]
                    j += 1
                i = j + 1
                codes.extend([F_H, len(text)] + [ord(ch) for ch in text])
                continue
            r = number()
            skip()
            if i >= len(s):
                err("FORMAT: missing )")
            c = s[i].upper()
            i += 1
            if c == "(":
                if depth == 0:
                    top_groups.append(len(codes) + 1)
                codes.extend([F_GROUP, r or 1])
                items(depth + 1)
                codes.append(F_ENDGROUP)
                continue
            if c == "H":
                if not r:
                    err("FORMAT: H needs a count")
                text = s[i:i + r]
                if len(text) < r:
                    err("FORMAT: Hollerith runs off the card")
                i += r
                codes.extend([F_H, r] + [ord(ch) for ch in text])
                continue
            if c == "X":
                codes.extend([F_X, r or 1])
                continue
            if c in "IFELB":
                w = number()
                if not w:
                    err(f"FORMAT: {c} needs a width")
                d = 0
                skip()
                if c in "FE":
                    if i >= len(s) or s[i] != ".":
                        err(f"FORMAT: {c}{w} needs .d")
                    i += 1
                    d = number()
                    if d is None:
                        err(f"FORMAT: {c}{w}. needs d")
                code = {"I": F_I, "F": F_F, "E": F_E, "L": F_L, "B": F_B}[c]
                one = [code, w] + ([d] if c in "FE" else [])
                if r and r > 1:
                    codes.extend([F_GROUP, r] + one + [F_ENDGROUP])
                else:
                    codes.extend(one)
                continue
            err(f"FORMAT: cannot understand {c!r}")

    skip()
    if i >= len(s) or s[i] != "(":
        err("FORMAT needs (")
    i += 1
    items(0)
    skip()
    if i < len(s):
        err("FORMAT: junk after )")
    codes.append(F_END)
    rev = top_groups[-1] if top_groups else 1
    return [rev] + codes


# ======================================================================
#  The compiler
# ======================================================================
class Loop:
    def __init__(self, var, reg, lo, hi, term):
        self.var = var
        self.reg = reg
        self.lo = lo               # statement index of the DO
        self.hi = hi               # statement index of its terminal statement
        self.term = term
        self.body = None
        self.limit = None
        self.step = None
        self.home = None


class Compiler:
    def __init__(self):
        self.units = []
        self.out = []
        self.data = []
        self.nlabel = 0
        self.calls = []            # (unit, name, nargs, kind, line)
        self.common_size = {}
        self.fname = "<source>"

    # ---------------- utilities ----------------
    def err(self, msg, line=None):
        raise CompileError(f"{self.fname}:{line or self.cur_line}: {msg}")

    def emit(self, s):
        # a load of the word just stored is dropped (the condition trit
        # is never taken from a plain load)
        if s.startswith("LD   R1, ") and self.out and \
                self.out[-1] == "        ST   R1, " + s[9:]:
            return
        self.out.append("        " + s)

    def place(self, lab):
        self.out.append(f"{lab}:")

    def newlab(self):
        self.nlabel += 1
        return f"{self.unit.prefix}._{self.nlabel}"

    def stlab(self, n):
        return f"{self.unit.prefix}.{n}"

    # ---------------- front end ----------------
    def compile(self, text, fname="<source>"):
        self.fname = fname
        stmts = read_cards(text, fname)
        if not stmts:
            raise CompileError(f"{fname}: no statements")
        unit_stmts = []
        cur = []
        for s in stmts:
            cur.append(s)
            if s.text == "END":
                unit_stmts.append(cur)
                cur = []
        if cur:
            raise CompileError(f"{fname}:{cur[-1].line}: the last program "
                               "unit has no END")
        for us in unit_stmts:
            self.units.append(self.parse_unit(us))
        names = {}
        mains = [u for u in self.units if u.kind == "main"]
        if len(mains) != 1:
            raise CompileError(f"{fname}: there must be exactly one main "
                               f"program (found {len(mains)})")
        for u in self.units:
            if u.kind != "main":
                if u.name in names:
                    raise CompileError(f"{fname}:{u.line}: {u.name} is "
                                       "defined twice")
                names[u.name] = u
        self.subprograms = names
        self.out = ["; TRI-TRAN compiler output",
                    "        ENTRY START",
                    "START:  CALL P_tt_init",
                    f"        CALL {MAIN}",
                    "        LD   R1, #0",
                    "        SVC  0"]
        for u in self.units:
            self.gen_unit(u)
        self.check_calls()
        for block, size in self.common_size.items():
            self.data.append(f"C.{block}:  BSS {size}")
        return "\n".join(self.out + self.data) + "\n"

    def check_calls(self):
        tname = {"I": "INTEGER", "R": "REAL", "L": "LOGICAL"}
        for unit, name, nargs, kind, line, ty in self.calls:
            sub = self.subprograms.get(name)
            if sub is None:
                raise CompileError(f"{self.fname}:{line}: no subprogram "
                                   f"{name}")
            if kind == "call" and sub.kind != "sub":
                raise CompileError(f"{self.fname}:{line}: {name} is a "
                                   "FUNCTION, not a SUBROUTINE")
            if kind == "func" and sub.kind != "func":
                raise CompileError(f"{self.fname}:{line}: {name} is a "
                                   "SUBROUTINE, not a FUNCTION")
            if ty is not None and ty != sub.type:
                raise CompileError(
                    f"{self.fname}:{line}: {name} is {'an' if sub.type == 'I' else 'a'} {tname[sub.type]} "
                    f"FUNCTION, but is {tname[ty]} here (declare it "
                    f"{tname[sub.type]})")
            if nargs is not None and nargs != len(sub.params):
                raise CompileError(f"{self.fname}:{line}: {name} takes "
                                   f"{len(sub.params)} arguments, not "
                                   f"{nargs}")

    def sym(self, name, create=True):
        u = self.unit
        s = u.syms.get(name)
        if s is None and create:
            if len(name) > 6:
                self.err(f"name {name} is longer than six characters")
            s = Sym(name, implicit(name))
            u.syms[name] = s
        return s

    def parse_unit(self, stmts):
        first = stmts[0]
        self.cur_line = first.line
        head = first.text
        unit = None
        m = re.fullmatch(r"(INTEGER|REAL|LOGICAL)?FUNCTION([A-Z][A-Z0-9]*)"
                         r"\((.*)\)", head)
        if m:
            unit = Unit("func", m.group(2), self.namelist(m.group(3)),
                        {"INTEGER": "I", "REAL": "R",
                         "LOGICAL": "L"}.get(m.group(1)), first.line)
        m2 = re.fullmatch(r"SUBROUTINE([A-Z][A-Z0-9]*)(?:\((.*)\))?", head)
        if m2:
            unit = Unit("sub", m2.group(1),
                        self.namelist(m2.group(2) or ""), None, first.line)
        if unit:
            body = stmts[1:]
            if len(unit.name) > 6:
                self.err(f"name {unit.name} is longer than six characters")
        else:
            m3 = re.fullmatch(r"PROGRAM([A-Z][A-Z0-9]*)", head)
            unit = Unit("main", m3.group(1) if m3 else "MAIN", [], None,
                        first.line)
            body = stmts[1:] if m3 else stmts
        self.unit = unit
        for i, p in enumerate(unit.params):
            s = self.sym(p)
            if s.dummy is not None:
                self.err(f"argument {p} repeated")
            s.dummy = i
        if unit.kind == "func":
            s = self.sym(unit.name)
            s.result = True
            if unit.type:
                s.type = unit.type
                s.explicit = True
        executable = False
        for st in body:
            self.cur_line = st.line
            kind, args = self.classify(st, executable)
            if kind in ("TYPE", "DIMENSION", "COMMON", "EXTERNAL", "DATA",
                        "STFUNC"):
                if executable and kind not in ("DATA",):
                    what = "statement function" if kind == "STFUNC" else kind
                    self.err(f"{what} after the first executable statement")
                if st.label is not None and kind != "DATA":
                    self.err("a specification statement cannot have a "
                             "statement number")
                continue
            if kind == "FORMAT":
                if st.label is None:
                    self.err("FORMAT needs a statement number")
                if st.label in unit.formats:
                    self.err(f"statement number {st.label} used twice")
                unit.formats[st.label] = args
                continue
            executable = True
            st.kind, st.args = kind, args
            unit.stmts.append(st)
        if unit.kind == "func":
            unit.type = unit.syms[unit.name].type
        self.layout_commons(unit)
        # statement numbers
        unit.labels = {}
        for i, st in enumerate(unit.stmts):
            if st.label is not None:
                if st.label in unit.labels or st.label in unit.formats:
                    self.err(f"statement number {st.label} used twice",
                             st.line)
                unit.labels[st.label] = i
        for i, st in enumerate(unit.stmts):
            for n in self.targets(st):
                if n not in unit.labels:
                    if n in unit.formats:
                        self.err(f"{n} is a FORMAT, not a statement to go "
                                 "to", st.line)
                    self.err(f"no statement number {n}", st.line)
            for n in self.format_refs(st):
                if n not in unit.formats:
                    self.err(f"no FORMAT statement {n}", st.line)
        return unit

    def namelist(self, text):
        if not text:
            return []
        names = text.split(",")
        for n in names:
            if not re.fullmatch(r"[A-Z][A-Z0-9]*", n):
                self.err(f"bad name {n!r}")
        return names

    # ---------------- statements ----------------
    def classify(self, st, executable):
        s = st.text
        u = self.unit

        def P(text):
            return Parser(tokenize(text, self.err), self.err)

        if s.startswith("FORMAT("):
            return "FORMAT", parse_format(st.raw, self.err)
        if s.startswith("IF("):
            depth, j = 0, 2
            while j < len(s):
                if s[j] == "(":
                    depth += 1
                elif s[j] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            rest = s[j + 1:]
            if rest and not rest.startswith("="):
                cond = P(s[3:j]).expr()
                if re.fullmatch(r"\d+,\d+,\d+", rest):
                    return "AIF", (cond, [int(x) for x in rest.split(",")])
                sub = Statement(None, rest, rest, st.line)
                kind, args = self.classify(sub, True)
                if kind in ("DO", "LIF", "END", "FORMAT", "TYPE",
                            "DIMENSION", "COMMON", "DATA", "EXTERNAL",
                            "STFUNC"):
                    self.err(f"a logical IF cannot contain that statement")
                return "LIF", (cond, (kind, args))
        eq = self.top_equals(s)
        if eq is not None:
            m = re.match(r"DO(\d+)([A-Z][A-Z0-9]*)=", s)
            if m and m.end() == eq + 1 and self.top_comma(s, eq):
                p = P(s[eq + 1:])
                e1 = p.expr()
                p.expect("op", ",")
                e2 = p.expr()
                e3 = None
                if p.at("op", ","):
                    p.take()
                    e3 = p.expr()
                p.end()
                self.sym(m.group(2))
                return "DO", (int(m.group(1)), m.group(2), e1, e2, e3)
            p = P(s[:eq])
            lhs = p.primary()
            p.end()
            p = P(s[eq + 1:])
            rhs = p.expr()
            p.end()
            if lhs[0] == "ref":
                sym = u.syms.get(lhs[1])
                if not executable and not (sym and sym.is_array):
                    # a statement function
                    ps = []
                    for a in lhs[2]:
                        if a[0] != "name":
                            self.err("a statement function's arguments "
                                     "must be names")
                        ps.append(a[1])
                    self.sym(lhs[1])
                    u.stfuncs[lhs[1]] = (ps, rhs)
                    return "STFUNC", None
            elif lhs[0] != "name":
                self.err("cannot assign to that")
            return "ASSIGN", (lhs, rhs)
        m = re.fullmatch(r"GOTO(\d+)", s)
        if m:
            return "GOTO", int(m.group(1))
        m = re.fullmatch(r"GOTO\(([\d,]+)\),?(.+)", s)
        if m:
            p = P(m.group(2))
            e = p.expr()
            p.end()
            return "CGOTO", ([int(x) for x in m.group(1).split(",")], e)
        if s.startswith("CALL"):
            p = P(s[4:])
            name = p.name()
            args = []
            if p.at("op", "("):
                p.take()
                if not p.at("op", ")"):
                    args.append(p.expr())
                    while p.at("op", ","):
                        p.take()
                        args.append(p.expr())
                p.expect("op", ")")
            p.end()
            return "CALL", (name, args)
        if s == "CONTINUE":
            return "CONTINUE", None
        if s == "RETURN":
            return "RETURN", None
        m = re.fullmatch(r"(STOP|PAUSE)(\d*)", s)
        if m:
            return m.group(1), int(m.group(2)) if m.group(2) else None
        if s == "END":
            return "END", None
        m = re.fullmatch(r"(READ|WRITE)\((\d+),(\d+)(?:,END=(\d+))?\)(.*)", s)
        if m:
            unit_no = int(m.group(2))
            if m.group(1) == "READ" and unit_no != 5:
                self.err("READ is from unit 5, the card reader")
            if m.group(1) == "WRITE" and unit_no not in (6, 7):
                self.err("WRITE is to unit 6, the line printer, or 7, the "
                         "card punch")
            if m.group(4) and m.group(1) == "WRITE":
                self.err("END= belongs on a READ")
            return m.group(1), (unit_no, int(m.group(3)),
                                int(m.group(4)) if m.group(4) else None,
                                self.iolist(m.group(5)))
        m = re.fullmatch(r"(READ|PRINT|PUNCH)(\d+)(?:,(.*))?", s)
        if m:
            kind = "READ" if m.group(1) == "READ" else "WRITE"
            unit_no = {"READ": 5, "PRINT": 6, "PUNCH": 7}[m.group(1)]
            return kind, (unit_no, int(m.group(2)), None,
                          self.iolist(m.group(3) or ""))
        if s.startswith("DIMENSION"):
            self.declare(s[9:], None)
            return "DIMENSION", None
        m = re.match(r"(INTEGER|REAL|LOGICAL)(?!FUNCTION)", s)
        if m and len(s) > m.end():
            self.declare(s[m.end():], {"INTEGER": "I", "REAL": "R",
                                       "LOGICAL": "L"}[m.group(1)])
            return "TYPE", None
        if s.startswith("COMMON"):
            self.common(s[6:])
            return "COMMON", None
        if s.startswith("EXTERNAL"):
            for n in self.namelist(s[8:]):
                self.sym(n).external = True
            return "EXTERNAL", None
        if s.startswith("DATA"):
            self.data_stmt(s[4:])
            return "DATA", None
        for word in ("EQUIVALENCE", "BLOCKDATA", "ASSIGN", "DOUBLEPRECISION",
                     "COMPLEX", "ENTRY", "IMPLICIT", "BACKSPACE", "REWIND",
                     "ENDFILE"):
            if s.startswith(word):
                self.err(f"TRI-TRAN has no {word} statement")
        self.err(f"cannot understand this statement")

    @staticmethod
    def top_equals(s):
        depth = 0
        for i, c in enumerate(s):
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            elif c == "=" and depth == 0:
                return i
        return None

    @staticmethod
    def top_comma(s, start):
        depth = 0
        for c in s[start:]:
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            elif c == "," and depth == 0:
                return True
        return False

    def declare(self, text, type_):
        p = Parser(tokenize(text, self.err), self.err)
        while True:
            name = p.name()
            s = self.sym(name)
            if type_:
                if s.explicit:
                    self.err(f"{name} is typed twice")
                s.type, s.explicit = type_, True
            if p.at("op", "("):
                p.take()
                dims = []
                while True:
                    tk = p.take()
                    if tk.kind == "int" and tk.val > 0:
                        dims.append(tk.val)
                    elif tk.kind == "name":
                        dims.append(("var", tk.val))
                    else:
                        self.err(f"bad dimension for {name}")
                    if p.at("op", ","):
                        p.take()
                        continue
                    p.expect("op", ")")
                    break
                if s.dims is not None:
                    self.err(f"{name} is dimensioned twice")
                if len(dims) > 3:
                    self.err(f"{name} has more than three dimensions")
                s.dims = dims
                adjustable = any(not isinstance(d, int) for d in dims)
                if adjustable and s.dummy is None:
                    self.err(f"only an argument can have adjustable "
                             f"dimensions ({name})")
            elif type_ is None:
                self.err(f"DIMENSION {name} needs its bounds")
            if p.done():
                break
            p.expect("op", ",")

    def common(self, text):
        block = "_"
        rest = text
        while rest:
            m = re.match(r"/([A-Z][A-Z0-9]*)?/", rest)
            if m:
                block = m.group(1) or "_"
                rest = rest[m.end():]
                continue
            depth, j = 0, 0
            while j < len(rest):
                c = rest[j]
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                elif depth == 0 and c in ",/":
                    break
                j += 1
            item, rest = rest[:j], rest[j:]
            if rest.startswith(","):
                rest = rest[1:]
            if not item:
                continue
            m = re.fullmatch(r"([A-Z][A-Z0-9]*)(\(.*\))?", item)
            if not m:
                self.err(f"bad COMMON item {item!r}")
            if m.group(2):
                self.declare(item, None)
            s = self.sym(m.group(1))
            if s.dummy is not None:
                self.err(f"argument {s.name} cannot be in COMMON")
            if s.common is not None:
                self.err(f"{s.name} is in COMMON twice")
            s.common = (block, None)
            self.unit.commons.setdefault(block, []).append(s.name)

    def layout_commons(self, unit):
        for block, names in unit.commons.items():
            off = 0
            for n in names:
                s = unit.syms[n]
                if s.is_array and s.size() is None:
                    self.err(f"COMMON array {n} must have constant bounds")
                s.common = (block, off)
                off += s.size() if s.is_array else 1
            self.common_size[block] = max(self.common_size.get(block, 0), off)

    def constant(self, p):
        """A signed constant: (type, word)."""
        sign = 1
        if p.at("op", "-") or p.at("op", "+"):
            sign = -1 if p.take().val == "-" else 1
        tk = p.take()
        if tk.kind == "int":
            return "I", sign * tk.val
        if tk.kind == "real":
            w = real_word(tk.val)
            return "R", w if sign > 0 else fpu.normalise(-fpu.value(w))
        if tk.kind == "log" and sign == 1:
            return "L", tk.val
        self.err("expected a constant")

    def data_stmt(self, text):
        p = Parser(tokenize(text, self.err), self.err)
        while True:
            targets = []
            while True:
                name = p.name()
                s = self.sym(name)
                if s.dummy is not None or s.common is not None:
                    self.err(f"DATA cannot initialise {name}")
                if p.at("op", "("):
                    p.take()
                    subs = [self.constant(p)[1]]
                    while p.at("op", ","):
                        p.take()
                        subs.append(self.constant(p)[1])
                    p.expect("op", ")")
                    if not s.is_array or len(subs) != len(s.dims):
                        self.err(f"{name} is not an array of "
                                 f"{len(subs)} dimensions")
                    off, mult = 0, 1
                    for sub, d in zip(subs, s.dims):
                        if not 1 <= sub <= d:
                            self.err(f"subscript out of bounds in DATA")
                        off += (sub - 1) * mult
                        mult *= d
                    targets.append((s, off))
                elif s.is_array:
                    targets.extend((s, k) for k in range(s.size()))
                else:
                    targets.append((s, 0))
                if p.at("op", ","):
                    p.take()
                    continue
                break
            p.expect("op", "/")
            values = []
            while True:
                if p.at("int") and p.peek(1) and p.peek(1).kind == "op" \
                        and p.peek(1).val == "*":
                    r = p.take().val
                    p.take()
                    values.extend([self.constant(p)] * r)
                else:
                    values.append(self.constant(p))
                if p.at("op", ","):
                    p.take()
                    continue
                break
            p.expect("op", "/")
            if len(values) != len(targets):
                self.err(f"DATA: {len(targets)} names but {len(values)} "
                         "values")
            for (s, off), (ty, w) in zip(targets, values):
                if ty != s.type:
                    if ty == "I" and s.type == "R":
                        w = fpu.normalise(w)
                    else:
                        self.err(f"DATA: a {ty} constant for {s.type} "
                                 f"variable {s.name}")
                s.data[off] = w
            if p.done():
                break
            if p.at("op", ","):
                p.take()

    def iolist(self, text):
        if not text:
            return []
        p = Parser(tokenize(text, self.err), self.err)
        items = self.io_items(p)
        p.end()
        return items

    def io_items(self, p, closing=False):
        items = []
        while True:
            if p.at("op", "("):
                # an implied DO: (list, I = e1, e2 [, e3])
                save = p.i
                p.take()
                if self.is_implied_do(p):
                    inner = self.io_items(p, closing=True)
                    items.append(inner)
                else:
                    p.i = save
                    items.append(p.expr())
            else:
                items.append(p.expr())
            if closing and p.at("op", "="):
                # the last "item" was the DO variable
                var = items.pop()
                if var[0] != "name":
                    self.err("bad implied DO")
                p.take()
                e1 = p.expr()
                p.expect("op", ",")
                e2 = p.expr()
                e3 = None
                if p.at("op", ","):
                    p.take()
                    e3 = p.expr()
                p.expect("op", ")")
                self.sym(var[1])
                return ("impdo", items, var[1], e1, e2, e3)
            if p.done() or p.at("op", ")"):
                return items
            p.expect("op", ",")

    @staticmethod
    def is_implied_do(p):
        depth = 1
        j = p.i
        while j < len(p.toks):
            tk = p.toks[j]
            if tk.kind == "op" and tk.val == "(":
                depth += 1
            elif tk.kind == "op" and tk.val == ")":
                depth -= 1
                if depth == 0:
                    return False
            elif tk.kind == "op" and tk.val == "=" and depth == 1:
                return True
            j += 1
        return False

    @staticmethod
    def targets(st):
        k, a = st.kind, st.args
        if k == "GOTO":
            return [a]
        if k == "AIF":
            return a[1]
        if k == "CGOTO":
            return a[0]
        if k == "LIF":
            fake = Statement(None, "", "", st.line)
            fake.kind, fake.args = a[1]
            return Compiler.targets(fake)
        if k == "READ" and a[2]:
            return [a[2]]
        if k == "DO":
            return [a[0]]
        return []

    @staticmethod
    def format_refs(st):
        if st.kind in ("READ", "WRITE"):
            return [st.args[1]]
        if st.kind == "LIF" and st.args[1][0] in ("READ", "WRITE"):
            return [st.args[1][1][1]]
        return []

    # ==================================================================
    #  Semantics: names to storage, types, conversions
    # ==================================================================
    def resolve(self, e):
        """A typed tree.  Nodes: (kind, type, ...)."""
        k = e[0]
        if k == "int":
            if abs(e[1]) > WMAX:
                self.err(f"integer {e[1]} does not fit in a word")
            return ("const", "I", e[1])
        if k == "real":
            return ("const", "R", real_word(e[1]))
        if k == "log":
            return ("const", "L", e[1])
        if k == "name":
            s = self.sym(e[1])
            if s.is_array:
                return ("array", s.type, s)
            if s.external:
                return ("proc", s.type, s)
            return ("var", s.type, s)
        if k == "ref":
            name, args = e[1], e[2]
            s = self.unit.syms.get(name)
            if s is not None and s.is_array:
                if len(args) != len(s.dims):
                    self.err(f"{name} has {len(s.dims)} subscripts, not "
                             f"{len(args)}")
                subs = [self.resolve(a) for a in args]
                for a in subs:
                    if a[1] != "I":
                        self.err(f"a subscript of {name} is not an INTEGER")
                return ("elem", s.type, s, subs)
            if name in self.unit.stfuncs:
                ps, body = self.unit.stfuncs[name]
                if len(ps) != len(args):
                    self.err(f"statement function {name} takes {len(ps)} "
                             "arguments")
                return self.resolve(self.substitute(body, dict(zip(ps, args))))
            if name in INTRINSICS and not (s and (s.dummy is not None
                                                  or s.external)):
                return self.intrinsic(name, args)
            if s and s.result and name == self.unit.name:
                self.err(f"FUNCTION {name} cannot call itself")
            if s is None:
                s = self.sym(name)
            args_r = [self.actual(a) for a in args]
            if s.dummy is not None:
                return ("call", s.type, s, args_r)
            self.calls.append((self.unit, name, len(args), "func",
                               self.cur_line, s.type))
            return ("call", s.type, s, args_r)
        if k == "neg":
            a = self.resolve(e[1])
            if a[1] == "L":
                self.err("minus applied to a LOGICAL")
            if a[0] == "const":
                if a[1] == "I":
                    return ("const", "I", -a[2])
                return ("const", "R", fpu.normalise(-fpu.value(a[2])))
            return ("neg", a[1], a)
        if k == "not":
            a = self.resolve(e[1])
            if a[1] != "L":
                self.err(".NOT. needs a LOGICAL")
            if a[0] == "const":
                return ("const", "L", -a[2])
            return ("not", "L", a)
        if k == "arith":
            a, b = self.resolve(e[2]), self.resolve(e[3])
            a, b, ty = self.balance(a, b)
            if a[0] == "const" and b[0] == "const" and ty == "I":
                v = {"+": lambda x, y: x + y, "-": lambda x, y: x - y,
                     "*": lambda x, y: x * y,
                     "/": lambda x, y: t.trunc_div(x, y) if y else None}[
                         e[1]](a[2], b[2])
                if v is not None and abs(v) <= WMAX:
                    return ("const", "I", v)
            return ("arith", ty, e[1], a, b)
        if k == "pow":
            a, b = self.resolve(e[1]), self.resolve(e[2])
            if "L" in (a[1], b[1]):
                self.err("** applied to a LOGICAL")
            if a[1] == "I" and b[1] == "R":
                a = self.conv(a, "R")
            return ("pow", a[1], a, b)
        if k == "rel":
            a, b = self.resolve(e[2]), self.resolve(e[3])
            if "L" in (a[1], b[1]) and a[1] != b[1]:
                self.err("comparing a LOGICAL with a number")
            a, b, ty = self.balance(a, b)
            return ("rel", "L", e[1], a, b)
        if k == "logop":
            a, b = self.resolve(e[2]), self.resolve(e[3])
            if a[1] != "L" or b[1] != "L":
                self.err(f".{e[1]}. needs LOGICAL operands")
            if e[1] == "NEQV":
                return ("not", "L", ("logop", "L", "EQV", a, b))
            return ("logop", "L", e[1], a, b)
        self.err("cannot compile this expression")

    def substitute(self, e, env):
        if e[0] == "name" and e[1] in env:
            return env[e[1]]
        if e[0] == "ref":
            return ("ref", e[1], [self.substitute(a, env) for a in e[2]])
        if e[0] in ("neg", "not"):
            return (e[0], self.substitute(e[1], env))
        if e[0] in ("arith", "rel", "logop"):
            return (e[0], e[1], self.substitute(e[2], env),
                    self.substitute(e[3], env))
        if e[0] == "pow":
            return ("pow", self.substitute(e[1], env),
                    self.substitute(e[2], env))
        return e

    def actual(self, e):
        """An actual argument of a subprogram: passed by its address."""
        if e[0] == "name":
            s = self.sym(e[1])
            if s.external:
                return ("proc", s.type, s)
            if s.is_array:
                return ("array", s.type, s)
        return self.resolve(e)

    def conv(self, a, ty):
        if a[1] == ty:
            return a
        if a[1] == "L" or ty == "L":
            self.err("mixing LOGICAL with numbers")
        if a[0] == "const":
            if ty == "R":
                return ("const", "R", fpu.normalise(a[2]))
            return ("const", "I", int(fpu.value(a[2])))
        return ("conv", ty, a)

    def balance(self, a, b):
        if a[1] == "L" or b[1] == "L":
            if a[1] == b[1]:
                return a, b, "L"
            self.err("mixing LOGICAL with numbers")
        if a[1] == b[1]:
            return a, b, a[1]
        return self.conv(a, "R"), self.conv(b, "R"), "R"

    def intrinsic(self, name, args):
        aty, rty, arity, lib = INTRINSICS[name]
        if arity >= 0 and len(args) != arity:
            self.err(f"{name} takes {arity} argument"
                     f"{'s' if arity != 1 else ''}")
        if arity == -2 and len(args) < 2:
            self.err(f"{name} takes two or more arguments")
        rs = [self.resolve(a) for a in args]
        for a in rs:
            if a[1] != aty:
                want = {"I": "INTEGER", "R": "REAL", "L": "LOGICAL"}[aty]
                self.err(f"the argument of {name} must be {want}")
        return ("intr", rty, name, rs)

    # ==================================================================
    #  Code generation
    # ==================================================================
    def gen_unit(self, u):
        self.unit = u
        self.cur_line = u.line
        self.nlabel = 0
        self.temps = []
        self.active = []           # Loops, outermost first
        self.used_regs = set()
        self.reg_names = {}
        self.loops_at = {}         # terminal statement index -> [Loop]
        self.plan_loops(u)
        n = len(u.params)
        self.nparams = n
        head = len(self.out)
        if u.kind == "main":
            self.out.append("; main program" +
                            (f" {u.name}" if u.name != "MAIN" else ""))
        else:
            self.out.append(f"; {'SUBROUTINE' if u.kind == 'sub' else 'FUNCTION'}"
                            f" {u.name}({', '.join(u.params)})")
        self.place(u.entry)
        if u.kind != "main":
            self.emit("PUSH FP")
            self.emit("LEA  FP, 0(SP)")
        save_at = len(self.out)
        self.ret_lab = self.newlab()
        for i, st in enumerate(u.stmts):
            self.cur = i
            self.cur_line = st.line
            if st.label is not None:
                self.place(self.stlab(st.label))
            self.gen_stmt(st.kind, st.args, st)
            for loop in reversed(self.loops_at.get(i, [])):
                self.end_loop(loop)
        saves = sorted(self.used_regs)
        if u.kind != "main":
            self.place(self.ret_lab)
            if u.kind == "func":
                self.emit(f"LD   R1, {self.var_op(u.syms[u.name])}")
            for r in saves:
                self.emit(f"LD   {r}, {u.prefix}._S{r[1]}")
            self.emit("LEA  SP, 0(FP)")
            self.emit("POP  FP")
            self.emit(f"RET  {n}" if n else "RET")
            self.out[save_at:save_at] = [
                f"        ST   {r}, {u.prefix}._S{r[1]}" for r in saves]
            for r in saves:
                self.data.append(f"{u.prefix}._S{r[1]}:  DATA 0")
        if self.reg_names:
            self.out[head] += "   index registers: " + ", ".join(
                f"{r}={'/'.join(v)}" for r, v in sorted(self.reg_names.items()))
        self.gen_storage(u)

    def gen_storage(self, u):
        """FORTRAN's storage is static: every variable has its place."""
        for name, s in u.syms.items():
            if s.dummy is not None or s.common is not None or s.external:
                continue
            if not (s.is_array or s.used or s.result or s.data):
                continue
            lab = f"{u.prefix}.{name}"
            if s.is_array:
                n = s.size()
                if s.data:
                    words = [str(s.data.get(k, 0)) for k in range(n)]
                    for k in range(0, n, 12):
                        self.data.append((f"{lab}:  " if k == 0 else "        ")
                                         + "DATA " + ", ".join(words[k:k + 12]))
                else:
                    self.data.append(f"{lab}:  BSS {n}")
            else:
                self.data.append(f"{lab}:  DATA {s.data.get(0, 0)}")
        for lab in self.temps:
            self.data.append(f"{lab}:  DATA 0")
        for n, words in sorted(u.formats.items()):
            body = ", ".join(str(w) for w in words)
            self.data.append(f"{u.prefix}.{n}:  DATA {body}")

    def temp(self):
        self.nlabel += 1
        lab = f"{self.unit.prefix}._T{self.nlabel}"
        self.temps.append(lab)
        return lab

    # ---------------- DO loops and index registers ----------------
    def plan_loops(self, u):
        """Which DO loops may keep their index in a register: the index
        must be a local INTEGER variable, not assigned within the range,
        and no statement within the range may be jumped to from outside
        it (FORTRAN 66's "extended range")."""
        self.loop_plan = {}
        refs = {}                  # statement number -> [referring index]
        for i, st in enumerate(u.stmts):
            if st.kind == "DO":
                continue
            for n in self.targets(st):
                refs.setdefault(n, []).append(i)
        for i, st in enumerate(u.stmts):
            if st.kind != "DO":
                continue
            term, var = st.args[0], st.args[1]
            hi = u.labels[term]
            if hi <= i:
                self.err(f"DO {term}: the terminal statement comes before "
                         "the DO", st.line)
            tk = u.stmts[hi].kind
            if tk in ("GOTO", "AIF", "CGOTO", "RETURN", "STOP", "DO", "END"):
                self.err(f"DO {term}: a DO cannot end on "
                         f"{'an arithmetic IF' if tk == 'AIF' else tk}",
                         u.stmts[hi].line)
            s = u.syms[var]
            ok = (s.type == "I" and not s.is_array and s.dummy is None
                  and s.common is None and not s.result)
            if ok:
                for j in range(i + 1, hi + 1):
                    if var in self.assigned(u.stmts[j]):
                        ok = False
                        break
            if ok:
                for j in range(i + 1, hi + 1):
                    lab = u.stmts[j].label
                    if lab is not None and any(not i <= r <= hi
                                               for r in refs.get(lab, [])):
                        ok = False
                        break
            self.loop_plan[i] = (term, var, hi, ok)
            # nesting must be proper
        stack = []
        for i, st in enumerate(u.stmts):
            while stack and stack[-1] < i:
                stack.pop()
            if st.kind == "DO":
                hi = self.loop_plan[i][2]
                if stack and hi > stack[-1]:
                    self.err("DO loops overlap: the inner one must end "
                             "within the outer", st.line)
                stack.append(hi)

    def assigned(self, st):
        k, a = st.kind, st.args
        if k == "ASSIGN":
            return {a[0][1]} if a[0][0] == "name" else set()
        if k == "DO":
            return {a[1]}
        if k == "READ":
            out = set()

            def walk(items):
                for it in items:
                    if isinstance(it, tuple) and it[0] == "impdo":
                        out.add(it[2])
                        walk(it[1])
                    elif isinstance(it, tuple) and it[0] == "name":
                        out.add(it[1])
            walk(a[3])
            return out
        if k == "WRITE":
            out = set()

            def walk2(items):
                for it in items:
                    if isinstance(it, tuple) and it[0] == "impdo":
                        out.add(it[2])
                        walk2(it[1])
            walk2(a[3])
            return out
        if k == "LIF":
            fake = Statement(None, "", "", st.line)
            fake.kind, fake.args = a[1]
            return self.assigned(fake)
        return set()

    def begin_loop(self, st, args):
        term, var, e1, e2, e3 = args
        _, _, hi, ok = self.loop_plan[self.cur]
        s = self.sym(var)
        s.used = True
        home = self.var_op(s)
        reg = None
        if ok:
            busy = {l.reg for l in self.active if l.reg}
            free = [r for r in REGS if r not in busy]
            if free:
                reg = free[0]
        loop = Loop(var, reg, self.cur, hi, term)
        loop.home = home
        step = self.resolve(e3) if e3 is not None else ("const", "I", 1)
        start = self.resolve(e1)
        limit = self.resolve(e2)
        for e, what in ((start, "initial value"), (limit, "limit"),
                        (step, "step")):
            if e[1] != "I":
                self.err(f"the {what} of a DO must be INTEGER")
        if step[0] == "const" and step[2] == 0:
            self.err("the step of a DO cannot be zero")
        # the initial value
        if reg:
            op = self.operand(start)
            if op:
                self.emit(f"LD   {reg}, {op}")
            else:
                self.gen(start)
                self.emit(f"LD   {reg}, #0(R1)")
        else:
            self.gen(start)
            self.emit(f"ST   R1, {home}")
        assigned = set()
        for j in range(self.cur + 1, hi + 1):
            assigned |= self.assigned(self.unit.stmts[j])
        loop.limit = self.fixed_operand(limit, assigned)
        loop.step = self.fixed_operand(step, assigned)
        loop.down = step[0] == "const" and step[2] < 0
        if reg:
            self.used_regs.add(reg)
            self.note_reg(reg, var)
        self.active.append(loop)
        loop.body = self.newlab()
        self.place(loop.body)
        self.loops_at.setdefault(hi, []).append(loop)

    def note_reg(self, reg, var):
        names = self.reg_names.setdefault(reg, [])
        if var not in names:
            names.append(var)

    def fixed_operand(self, e, assigned):
        """An operand for a loop's limit or step, fixed on entry."""
        if e[0] == "const":
            return self.const_op(e)
        if e[0] == "var" and e[2].name not in assigned:
            op = self.operand(e)
            if op:
                return op
        self.gen(e)
        tmp = self.temp()
        self.emit(f"ST   R1, {tmp}")
        return tmp

    def end_loop(self, loop):
        """One trip at least, as in FORTRAN 66: the test is at the bottom."""
        again = "JNN" if loop.down else "JNP"
        if loop.reg:
            r = loop.reg
            self.emit(f"ADD  {r}, {loop.step}")
            self.emit(f"CMP  {r}, {loop.limit}")
            self.emit(f"{again:4} {loop.body}")
            self.active.remove(loop)
            self.emit(f"ST   {r}, {loop.home}")
        else:
            self.emit(f"LD   R1, {loop.home}")
            self.emit(f"ADD  R1, {loop.step}")
            self.emit(f"ST   R1, {loop.home}")
            self.emit(f"CMP  R1, {loop.limit}")
            self.emit(f"{again:4} {loop.body}")
            self.active.remove(loop)

    def reg_of(self, s):
        for loop in reversed(self.active):
            if loop.reg and loop.var == s.name:
                return loop.reg
        return None

    # ---------------- jumps ----------------
    def jump(self, n, cond="JMP"):
        """Jump to statement n, first storing the index registers of any
        loop whose range the jump leaves."""
        target = self.unit.labels[n]
        stores = [l for l in self.active if l.reg
                  and not l.lo < target <= l.hi]
        lab = self.stlab(n)
        if not stores:
            self.emit(f"{cond:4} {lab}")
            return
        skip = None
        if cond != "JMP":
            skip = self.newlab()
            self.emit(f"{INVERSE[cond]:4} {skip}")
        for l in stores:
            self.emit(f"ST   {l.reg}, {l.home}")
        self.emit(f"JMP  {lab}")
        if skip:
            self.place(skip)

    def leaves(self, n):
        target = self.unit.labels[n]
        return any(l.reg and not l.lo < target <= l.hi for l in self.active)

    # ---------------- statements ----------------
    def gen_stmt(self, kind, a, st):
        getattr(self, "s_" + kind.lower())(a, st)

    def s_continue(self, a, st):
        pass

    def s_end(self, a, st):
        if self.unit.kind == "main":
            self.emit("LD   R1, #0")
            self.emit("SVC  0")

    def s_return(self, a, st):
        if self.unit.kind == "main":
            self.err("RETURN in the main program")
        self.emit(f"JMP  {self.ret_lab}")

    def s_stop(self, n, st):
        if n is None:
            self.emit("LD   R1, #0")
            self.emit("SVC  0")
        else:
            self.call_lib("tt_stop", [("const", "I", n)])

    def s_pause(self, n, st):
        self.call_lib("tt_pause", [("const", "I", n if n is not None else -1)])

    def s_goto(self, n, st):
        self.jump(n)

    def s_cgoto(self, a, st):
        labs, e = a
        e = self.resolve(e)
        if e[1] != "I":
            self.err("a computed GO TO needs an INTEGER")
        self.gen(e)
        out = self.newlab()
        table = self.newlab()
        self.emit("CMP  R1, #1")
        self.emit(f"JN   {out}")
        self.emit(f"CMP  R1, #{len(labs)}")
        self.emit(f"JP   {out}")
        self.emit(f"JMP  {table}-1(R1)")
        self.place(table)
        stubs = []
        for n in labs:
            if self.leaves(n):
                s = self.newlab()
                stubs.append((s, n))
                self.emit(f"JMP  {s}")
            else:
                self.emit(f"JMP  {self.stlab(n)}")
        for s, n in stubs:
            self.place(s)
            self.jump(n)
        self.place(out)

    def s_aif(self, a, st):
        """IF (e) n1, n2, n3: to n1, n2 or n3 as e is negative, zero or
        positive.  The Duwamish does it with one J3."""
        e, (n1, n2, n3) = a
        e = self.resolve(e)
        self.set_condition(e)
        dests = {}
        stubs = []
        for n in (n1, n2, n3):
            if n not in dests:
                if self.leaves(n):
                    s = self.newlab()
                    stubs.append((s, n))
                    dests[n] = s
                else:
                    dests[n] = self.stlab(n)
        d1, d2, d3 = dests[n1], dests[n2], dests[n3]
        if n1 == n2 == n3:
            self.emit(f"JMP  {d1}")
        elif n1 == n2:
            self.emit(f"JP   {d3}")
            self.emit(f"JMP  {d1}")
        elif n2 == n3:
            self.emit(f"JN   {d1}")
            self.emit(f"JMP  {d2}")
        elif n1 == n3:
            self.emit(f"JZ   {d2}")
            self.emit(f"JMP  {d1}")
        else:
            mid = self.newlab()
            self.emit(f"J3   {mid}")
            self.emit(f"JMP  {d1}")
            self.place(mid)
            self.emit(f"JMP  {d2}")
            self.emit(f"JMP  {d3}")
        for s, n in stubs:
            self.place(s)
            self.jump(n)

    def set_condition(self, e):
        """Set the condition trit to the sign of e."""
        if e[0] == "arith" and e[2] == "-":
            a, b = e[3], e[4]
            op = self.operand(b)
            if op is None:
                self.gen(b)
                self.emit("PUSH R1")
                self.gen(a)
                self.emit("POP  R2")
                op = "#0(R2)"
            else:
                self.gen(a)
            self.emit(f"{'FCM' if e[1] == 'R' else 'CMP'}  R1, {op}")
            return
        if e[1] == "R":
            self.gen(e)
            self.emit("FCM  R1, #0")
            return
        op = self.operand(e)
        if op:
            self.emit(f"TST  {op}")
            return
        self.gen(e)
        self.emit("TST  #0(R1)")

    def s_lif(self, a, st):
        cond, (kind, args) = a
        cond = self.resolve(cond)
        if cond[1] != "L":
            self.err("a logical IF needs a LOGICAL expression")
        if kind == "GOTO" and not self.leaves(args):
            self.cond_true(cond, self.stlab(args))
            return
        skip = self.newlab()
        self.cond_false(cond, skip)
        self.gen_stmt(kind, args, st)
        self.place(skip)

    def s_do(self, a, st):
        self.begin_loop(st, a)

    def s_assign(self, a, st):
        lhs, rhs = a
        target = self.resolve(lhs)
        if target[0] not in ("var", "elem"):
            self.err("cannot assign to that")
        s = target[2]
        if target[0] == "var" and self.reg_of(s):
            self.err(f"{s.name} is the index of a DO loop that is running")
        value = self.resolve(rhs)
        if target[1] == "L" and value[1] != "L" or \
                target[1] != "L" and value[1] == "L":
            self.err("assigning a LOGICAL to a number, or a number to a "
                     "LOGICAL")
        value = self.convert(value, target[1])
        self.gen(value)
        self.store_r1(target)

    def convert(self, e, ty):
        if e[1] == ty:
            return e
        if ty == "R":
            return self.conv(e, "R")
        # REAL to INTEGER truncates, as FORTRAN does
        if e[0] == "const":
            return ("const", "I", int(fpu.value(e[2])))
        return ("intr", "I", "INT", [e])

    def store_r1(self, target):
        op = self.operand(target)
        if op:
            self.emit(f"ST   R1, {op}")
            return
        self.emit("PUSH R1")
        base = self.elem_index(target)
        self.emit("POP  R2")
        self.emit(f"ST   R2, {base}")

    def s_call(self, a, st):
        name, args = a
        s = self.unit.syms.get(name)
        if s is not None and s.dummy is not None:
            proc = s
        else:
            if name in self.unit.syms and self.unit.syms[name].is_array:
                self.err(f"{name} is an array")
            self.calls.append((self.unit, name, len(args), "call", st.line,
                               None))
            proc = None
        acts = [self.actual(x) for x in args]
        self.push_refs(acts)
        if proc is not None:
            proc.used = True
            self.emit(f"CALL @{self.arg_slot(proc)}(FP)")
        else:
            self.emit(f"CALL F_{name}")

    # ---------------- input and output ----------------
    def s_write(self, a, st):
        unit_no, fmt, _, items = a
        self.emit(f"LEA  R1, {self.unit.prefix}.{fmt}")
        self.emit("PUSH R1")
        self.emit(f"LD   R1, #{unit_no}")
        self.emit("PUSH R1")
        self.emit("CALL P_tt_wbeg")
        self.io_list(items, out=True)
        self.emit("CALL P_tt_wend")

    def s_read(self, a, st):
        unit_no, fmt, end, items = a
        self.emit(f"LEA  R1, {self.unit.prefix}.{fmt}")
        self.emit("PUSH R1")
        self.emit(f"LD   R1, #{1 if end else -1}")
        self.emit("PUSH R1")
        self.emit("CALL P_tt_rbeg")
        if end:
            self.emit("TST  #0(R1)")
            self.jump(end, "JN")
        self.io_list(items, out=False)

    def io_list(self, items, out):
        for it in items:
            if isinstance(it, tuple) and it[0] == "impdo":
                self.implied_do(it, out)
                continue
            e = self.resolve(it) if it[0] != "name" else self.actual(it)
            if e[0] == "array":
                s = e[2]
                s.used = True
                self.push_base(s)
                self.emit("PUSH R1")
                self.gen(self.array_size(s))
                self.emit("PUSH R1")
                self.emit(f"LD   R1, #{'IRL'.index(s.type) - 1}")
                self.emit("PUSH R1")
                self.emit(f"CALL P_tt_{'w' if out else 'r'}a")
                continue
            if out:
                self.gen(e)
                self.emit("PUSH R1")
                self.emit(f"CALL P_tt_w{e[1].lower()}")
            else:
                if e[0] not in ("var", "elem"):
                    self.err("READ needs variables")
                if e[0] == "var" and self.reg_of(e[2]):
                    self.err(f"READ into {e[2].name}, the index of a "
                             "running DO")
                self.emit(f"CALL P_tt_r{e[1].lower()}")
                self.store_r1(e)

    def array_size(self, s):
        n = None
        for d in s.dims:
            if isinstance(d, int):
                term = ("const", "I", d)
            else:
                term = self.resolve(("name", d[1]))
            n = term if n is None else ("arith", "I", "*", n, term)
        return n

    def implied_do(self, it, out):
        _, items, var, e1, e2, e3 = it
        s = self.sym(var)
        if s.type != "I" or s.is_array:
            self.err("an implied DO needs an INTEGER variable")
        if self.reg_of(s):
            self.err(f"{var} is the index of a running DO")
        s.used = True
        home = self.var_op(s)
        self.gen(self.resolve(e1))
        self.emit(f"ST   R1, {home}")
        limit = self.fixed_operand(self.resolve(e2), {var})
        step = (self.fixed_operand(self.resolve(e3), {var}) if e3 is not None
                else "#1")
        down = (e3 is not None and self.resolve(e3)[0] == "const"
                and self.resolve(e3)[2] < 0)
        top = self.newlab()
        self.place(top)
        self.io_list(items, out)
        self.emit(f"LD   R1, {home}")
        self.emit(f"ADD  R1, {step}")
        self.emit(f"ST   R1, {home}")
        self.emit(f"CMP  R1, {limit}")
        self.emit(f"{'JNN' if down else 'JNP'}  {top}")

    # ---------------- operands ----------------
    def const_op(self, e):
        v = e[2]
        if e[1] == "R" and v != 0:
            return f"={v}"
        if -ADDR_MAX <= v <= ADDR_MAX:
            return f"#{v}"
        return f"={v}"

    def arg_slot(self, s):
        return 2 + (self.nparams - 1 - s.dummy)

    def var_op(self, s):
        """The operand for a scalar variable (not a register)."""
        s.used = True
        if s.dummy is not None:
            return f"@{self.arg_slot(s)}(FP)"
        if s.common is not None:
            block, off = s.common
            return f"C.{block}+{off}" if off else f"C.{block}"
        return f"{self.unit.prefix}.{s.name}"

    def base_label(self, s):
        if s.common is not None:
            block, off = s.common
            return f"C.{block}+{off}" if off else f"C.{block}"
        return f"{self.unit.prefix}.{s.name}"

    def linear(self, e):
        """e as (non-constant part or None, constant)."""
        if e[0] == "const":
            return None, e[2]
        if e[0] == "arith" and e[2] in "+-" and e[1] == "I":
            a, ca = self.linear(e[3])
            b, cb = self.linear(e[4])
            if e[2] == "+":
                if a is None:
                    return b, ca + cb
                if b is None:
                    return a, ca + cb
            else:
                if b is None:
                    return a, ca - cb
        return e, 0

    def operand(self, e):
        """An operand string for e if it needs no computing, else None."""
        k = e[0]
        if k == "const":
            return self.const_op(e)
        if k == "var":
            s = e[2]
            s.used = True
            r = self.reg_of(s)
            if r:
                return f"#0({r})"
            return self.var_op(s)
        if k == "elem":
            s = e[2]
            s.used = True
            if s.dummy is not None:
                return None
            reg = None
            off = 0
            mult = 1
            for sub, d in zip(e[3], s.dims):
                x, c = self.linear(sub)
                off += (c - 1) * mult
                if x is not None:
                    if mult != 1 or reg is not None or x[0] != "var" or \
                            not self.reg_of(x[2]):
                        return None
                    reg = self.reg_of(x[2])
                mult *= d
            base = self.base_label(s)
            text = f"{base}{off:+d}" if off else base
            return f"{text}({reg})" if reg else text
        return None

    def elem_index(self, e):
        """Leave in R1 what, with the returned text as an operand
        base(R1), addresses the element: R1 is the index, or for an
        argument array the element's address.

        Column major, from 1: A(I,J,K) is element
        (I-1) + D1*((J-1) + D2*(K-1)), which is computed by Horner's rule
        from the last subscript.  With constant bounds, every constant
        part is folded into the displacement."""
        s = e[2]
        s.used = True
        subs, dims = e[3], s.dims
        const_dims = all(isinstance(d, int) for d in dims)
        disp = 0
        mult = 1
        parts = []
        for k, sub in enumerate(subs):
            x, c = self.linear(sub)
            if const_dims or k == 0:
                disp += (c - 1) * mult
                c = 1
            parts.append((x, c - 1))
            mult *= dims[k] if isinstance(dims[k], int) else 1
        started = False
        for k in range(len(subs) - 1, -1, -1):
            x, c = parts[k]
            if started:
                d = dims[k]
                dop = (f"#{d}" if isinstance(d, int)
                       else self.operand(self.resolve(("name", d[1]))))
                self.emit(f"MUL  R1, {dop}")
            if x is not None:
                if started:
                    op = self.operand(x)
                    if op is None:
                        self.emit("PUSH R1")
                        self.gen(x)
                        self.emit("POP  R2")
                        op = "#0(R2)"
                    self.emit(f"ADD  R1, {op}")
                else:
                    self.gen(x)
                    started = True
            if c:
                if started:
                    self.emit(f"ADD  R1, #{c}")
                else:
                    self.emit(f"LD   R1, #{c}")
                    started = True
        if not started:
            self.emit("LD   R1, #0")
        if s.dummy is not None:
            self.emit(f"ADD  R1, {self.arg_slot(s)}(FP)")
            return f"{disp}(R1)"
        base = self.base_label(s)
        return f"{base}{disp:+d}(R1)" if disp else f"{base}(R1)"

    # ---------------- expressions ----------------
    def gen(self, e):
        """Evaluate e into R1."""
        op = self.operand(e)
        if op is not None:
            self.emit(f"LD   R1, {op}")
            return
        k = e[0]
        if k == "elem":
            base = self.elem_index(e)
            self.emit(f"LD   R1, {base}")
        elif k == "arith":
            self.gen_arith(e)
        elif k == "neg":
            a = e[2]
            if e[1] == "I":
                aop = self.operand(a)
                if aop:
                    self.emit(f"NEG  R1, {aop}")
                else:
                    self.gen(a)
                    self.emit("NEG  R1, #0(R1)")
            else:
                self.gen(a)
                self.fneg()
        elif k == "not":
            aop = self.operand(e[2])
            if aop:
                self.emit(f"NEG  R1, {aop}")
            else:
                self.gen(e[2])
                self.emit("NEG  R1, #0(R1)")
        elif k == "conv":
            a = e[2]
            aop = self.operand(a)
            if e[1] == "R":
                if aop:
                    self.emit(f"FLT  R1, {aop}")
                else:
                    self.gen(a)
                    self.emit("FLT  R1, #0(R1)")
            else:
                self.gen(("intr", "I", "INT", [a]))
        elif k == "logop":
            ins = {"AND": "AND", "OR": "OR", "EQV": "EQV"}[e[2]]
            self.binary(ins, e[3], e[4], commutative=True)
        elif k == "rel":
            self.compare(e[3], e[4], e[2])
            self.emit(f"SEL  R1, #{SEL_TABLE[e[2]]}")
        elif k == "pow":
            self.gen_pow(e)
        elif k == "intr":
            self.gen_intrinsic(e)
        elif k == "call":
            s = e[2]
            self.push_refs(e[3])
            if s.dummy is not None:
                self.emit(f"CALL @{self.arg_slot(s)}(FP)")
            else:
                self.emit(f"CALL F_{s.name}")
        elif k == "array":
            self.err(f"array {e[2].name} used without a subscript")
        elif k == "proc":
            self.err(f"{e[2].name} is a subprogram, not a value")
        else:
            self.err(f"cannot compile {k}")

    def fneg(self):
        self.emit("LD   R2, #0(R1)")
        self.emit("LD   R1, #0")
        self.emit("FSB  R1, #0(R2)")

    def gen_arith(self, e):
        ty, op, a, b = e[1], e[2], e[3], e[4]
        if ty == "R":
            ins = {"+": "FAD", "-": "FSB", "*": "FMP", "/": "FDV"}[op]
        else:
            ins = {"+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV"}[op]
        self.binary(ins, a, b, commutative=op in "+*")

    def binary(self, ins, a, b, commutative):
        bop = self.operand(b)
        if bop is not None:
            self.gen(a)
            self.emit(f"{ins:4} R1, {bop}")
            return
        aop = self.operand(a)
        if commutative and aop is not None:
            self.gen(b)
            self.emit(f"{ins:4} R1, {aop}")
            return
        self.gen(b)
        self.emit("PUSH R1")
        self.gen(a)
        self.emit("POP  R2")
        self.emit(f"{ins:4} R1, #0(R2)")

    def compare(self, a, b, rel):
        """Set the condition to the sign of a - b; returns nothing."""
        ins = "FCM" if a[1] == "R" else "CMP"
        bop = self.operand(b)
        if bop is not None:
            self.gen(a)
            self.emit(f"{ins}  R1, {bop}")
            return rel
        self.gen(b)
        self.emit("PUSH R1")
        self.gen(a)
        self.emit("POP  R2")
        self.emit(f"{ins}  R1, #0(R2)")
        return rel

    def cond_false(self, e, lab):
        """Jump to lab unless e is .TRUE."""
        k = e[0]
        if k == "const":
            if e[2] != 1:
                self.emit(f"JMP  {lab}")
            return
        if k == "rel":
            self.compare(e[3], e[4], e[2])
            self.emit(f"{JUMP_FALSE[e[2]]:4} {lab}")
            return
        if k == "logop" and e[2] == "AND":
            self.cond_false(e[3], lab)
            self.cond_false(e[4], lab)
            return
        if k == "logop" and e[2] == "OR":
            yes = self.newlab()
            self.cond_true(e[3], yes)
            self.cond_false(e[4], lab)
            self.place(yes)
            return
        if k == "not" and e[2][0] == "rel":
            r = e[2]
            self.compare(r[3], r[4], r[2])
            self.emit(f"{JUMP_TRUE[r[2]]:4} {lab}")
            return
        op = self.operand(e)
        if op is not None:
            self.emit(f"TST  {op}")
        else:
            self.gen(e)
            self.emit("TST  #0(R1)")
        self.emit(f"JNP  {lab}")

    def cond_true(self, e, lab):
        """Jump to lab if e is .TRUE."""
        k = e[0]
        if k == "const":
            if e[2] == 1:
                self.emit(f"JMP  {lab}")
            return
        if k == "rel":
            self.compare(e[3], e[4], e[2])
            self.emit(f"{JUMP_TRUE[e[2]]:4} {lab}")
            return
        if k == "logop" and e[2] == "OR":
            self.cond_true(e[3], lab)
            self.cond_true(e[4], lab)
            return
        if k == "logop" and e[2] == "AND":
            no = self.newlab()
            self.cond_false(e[3], no)
            self.cond_true(e[4], lab)
            self.place(no)
            return
        if k == "not" and e[2][0] == "rel":
            r = e[2]
            self.compare(r[3], r[4], r[2])
            self.emit(f"{JUMP_FALSE[r[2]]:4} {lab}")
            return
        op = self.operand(e)
        if op is not None:
            self.emit(f"TST  {op}")
        else:
            self.gen(e)
            self.emit("TST  #0(R1)")
        self.emit(f"JP   {lab}")

    def gen_pow(self, e):
        ty, a, b = e[1], e[2], e[3]
        if b[0] == "const" and b[1] == "I" and b[2] in (2, 3):
            aop = self.operand(a)
            ins = "FMP" if ty == "R" else "MUL"
            if aop is None:
                self.gen(a)
                self.emit("LD   R2, #0(R1)")
                aop = "#0(R2)"
            else:
                self.emit(f"LD   R1, {aop}")
            for _ in range(b[2] - 1):
                self.emit(f"{ins:4} R1, {aop}")
            return
        if ty == "I":
            self.call_lib("tt_ipow", [a, b])
        elif b[1] == "I":
            self.call_lib("tt_rpowi", [a, b])
        else:
            self.call_lib("tt_rpow", [a, b])

    def call_lib(self, name, args):
        """A run-time library routine: arguments by value, SALISH style."""
        for x in args:
            self.gen(x)
            self.emit("PUSH R1")
        self.emit(f"CALL P_{name}")

    def gen_intrinsic(self, e):
        _, ty, name, args = e
        lib = INTRINSICS[name][3]
        if lib:
            self.call_lib(lib, args)
            return
        if name == "ICLOCK":
            self.emit("TIM  R1")
        elif name in ("ABS", "IABS"):
            self.gen(args[0])
            skip = self.newlab()
            if name == "IABS":
                self.emit("TST  #0(R1)")
                self.emit(f"JNN  {skip}")
                self.emit("NEG  R1, #0(R1)")
            else:
                self.emit("FCM  R1, #0")
                self.emit(f"JNN  {skip}")
                self.fneg()
            self.place(skip)
        elif name == "FLOAT":
            self.gen(("conv", "R", args[0]))
        elif name == "NINT":
            aop = self.operand(args[0])
            if aop:
                self.emit(f"FIX  R1, {aop}")
            else:
                self.gen(args[0])
                self.emit("FIX  R1, #0(R1)")
        elif name == "MOD":
            self.binary("MOD", args[0], args[1], commutative=False)
        elif name == "ITRIT":
            # trit K of N: XTR with length 1 at position K
            self.gen(args[1])
            self.emit("ADD  R1, #27")
            self.emit("PUSH R1")
            self.gen(args[0])
            self.emit("POP  R2")
            self.emit("XTR  R1, #0(R2)")
        elif name in ("MAX0", "MIN0", "AMAX1", "AMIN1", "AMAX0", "AMIN0",
                      "MAX1", "MIN1"):
            real = INTRINSICS[name][0] == "R"
            ins = "FCM" if real else "CMP"
            keep = "JNN" if "MAX" in name else "JNP"
            self.gen(args[0])
            for b in args[1:]:
                bop = self.operand(b)
                if bop is None:
                    self.emit("PUSH R1")
                    self.gen(b)
                    self.emit("LD   R2, #0(R1)")
                    self.emit("POP  R1")
                    bop = "#0(R2)"
                skip = self.newlab()
                self.emit(f"{ins}  R1, {bop}")
                self.emit(f"{keep:4} {skip}")
                self.emit(f"LD   R1, {bop}")
                self.place(skip)
            if name in ("AMAX0", "AMIN0"):
                self.emit("FLT  R1, #0(R1)")
            elif name in ("MAX1", "MIN1"):
                self.emit("PUSH R1")
                self.emit("CALL P_tt_ifix")
        else:
            self.err(f"cannot compile {name}")

    # ---------------- arguments by reference ----------------
    def push_refs(self, args):
        for a in args:
            self.address(a)
            self.emit("PUSH R1")

    def push_base(self, s):
        if s.dummy is not None:
            self.emit(f"LD   R1, {self.arg_slot(s)}(FP)")
        else:
            self.emit(f"LEA  R1, {self.base_label(s)}")

    def address(self, a):
        """The address of an actual argument, into R1."""
        k = a[0]
        if k == "var":
            s = a[2]
            s.used = True
            r = self.reg_of(s)
            if r:
                self.emit(f"ST   {r}, {self.var_op(s)}")
            if s.dummy is not None:
                self.emit(f"LD   R1, {self.arg_slot(s)}(FP)")
            else:
                self.emit(f"LEA  R1, {self.var_op(s)}")
        elif k == "array":
            a[2].used = True
            self.push_base(a[2])
        elif k == "elem":
            op = self.operand(a)
            if op:
                self.emit(f"LEA  R1, {op}")
            else:
                base = self.elem_index(a)
                self.emit(f"LEA  R1, {base}")
        elif k == "proc":
            s = a[2]
            if s.dummy is not None:
                self.emit(f"LD   R1, {self.arg_slot(s)}(FP)")
            else:
                self.calls.append((self.unit, s.name, None, "any",
                                   self.cur_line, None))
                self.emit(f"LEA  R1, F_{s.name}")
        elif k == "const":
            self.emit(f"LEA  R1, ={a[2]}")
        else:
            self.gen(a)
            tmp = self.temp()
            self.emit(f"ST   R1, {tmp}")
            self.emit(f"LEA  R1, {tmp}")


# ======================================================================
_library_cache = {}


def library_asm():
    """The run-time library, compiled by SALISH/O (once)."""
    if "asm" not in _library_cache:
        with open(LIBRARY) as f:
            asm, _ = salish.compile_source(f.read(), LIBRARY, optimise=True,
                                           library=True)
        _library_cache["asm"] = asm
    return _library_cache["asm"]


def compile_source(text, fname="<source>"):
    """Compile TRI-TRAN to TRIAD.  Returns (asm_text, compiler); the text
    includes the run-time library."""
    c = Compiler()
    asm = c.compile(text, fname)
    return asm + library_asm(), c
