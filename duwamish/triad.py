"""TRIAD: the Duwamish symbolic assembler.

Source format, one statement per line:

    [label:]  MNEMONIC  operands      ; comment
    name = expression                 ; symbol definition

Operands:
    R1 .. R8, FP (=R7), SP (=R8)      registers
    expr          direct              M[expr]
    #expr         immediate           the value expr itself
    @expr         indirect            M[M[expr]]
    =expr         literal             a pool word holding expr (direct)
    any of the above may be followed by (Rn) to add an index register.

Pseudo-operations:
    ORG expr          set the location counter
    DATA e, e, "s"    one word per expression; a string gives one word per
                      character
    STR "text"        a length-prefixed string: length, then the characters
    BSS n             reserve n words of zeros
    ENTRY label       program entry point
    LTORG             place the literal pool here (default: end of program)

Expressions: decimal numbers, 0t1T0 balanced-ternary literals, 'c'
characters, symbols, $ (the location counter), + - * / and parentheses.
"""

import re

from . import isa
from . import ternary as t

REGS = {f"R{i}": i for i in range(9)}
REGS.update(FP=7, SP=8)


class AsmError(Exception):
    pass


class ObjectProgram:
    def __init__(self):
        self.words = {}        # address -> word
        self.entry = None
        self.symbols = {}
        self.listing = []
        self.low = None
        self.high = None

    def image(self):
        return sorted(self.words.items())

    def listing_text(self):
        return "\n".join(self.listing)

    def address_names(self):
        rev = {}
        for k, v in self.symbols.items():
            if isinstance(v, int) and v in self.words and not k.startswith("."):
                rev.setdefault(v, k)
        return rev


class _Expr:
    TOK = re.compile(r"\s*(0t[T01]+|\d+|'(?:\\.|[^'])'|[A-Za-z_.][A-Za-z0-9_.]*"
                     r"|\$|[-+*/()])")

    def __init__(self, text, symbols, loc, lineno, strict):
        self.toks = []
        pos = 0
        text = text.strip()
        while pos < len(text):
            m = self.TOK.match(text, pos)
            if not m:
                raise AsmError(f"line {lineno}: bad expression {text!r}")
            self.toks.append(m.group(1))
            pos = m.end()
        self.i = 0
        self.symbols = symbols
        self.loc = loc
        self.lineno = lineno
        self.strict = strict

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else None

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def parse(self):
        v = self.expr()
        if self.peek() is not None:
            raise AsmError(f"line {self.lineno}: junk in expression")
        return v

    def expr(self):
        v = self.term()
        while self.peek() in ("+", "-"):
            if self.take() == "+":
                v += self.term()
            else:
                v -= self.term()
        return v

    def term(self):
        v = self.factor()
        while self.peek() in ("*", "/"):
            if self.take() == "*":
                v *= self.factor()
            else:
                d = self.factor()
                v = t.trunc_div(v, d) if d else 0
        return v

    def factor(self):
        tok = self.take()
        if tok is None:
            raise AsmError(f"line {self.lineno}: missing operand")
        if tok == "-":
            return -self.factor()
        if tok == "+":
            return self.factor()
        if tok == "(":
            v = self.expr()
            if self.take() != ")":
                raise AsmError(f"line {self.lineno}: missing )")
            return v
        if tok == "$":
            return self.loc
        if tok.startswith("0t"):
            return t.from_tstr(tok[2:])
        if tok[0].isdigit():
            return int(tok)
        if tok.startswith("'"):
            body = tok[1:-1]
            return ord(bytes(body, "utf-8").decode("unicode_escape"))
        if tok in self.symbols:
            return self.symbols[tok]
        if self.strict:
            raise AsmError(f"line {self.lineno}: undefined symbol {tok}")
        return 0


def _split_operands(s):
    """Split on commas that are outside quotes and parentheses."""
    out, cur, depth, q = [], "", 0, None
    for ch in s:
        if q:
            cur += ch
            if ch == q:
                q = None
            continue
        if ch in "\"'":
            q = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
            continue
        cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def _strip_comment(line):
    q = None
    for i, ch in enumerate(line):
        if q:
            if ch == "\\":
                continue
            if ch == q:
                q = None
        elif ch in "\"'":
            # a quote only opens a character constant like 'a' or a string
            q = ch
        elif ch == ";":
            return line[:i]
    return line


def _unescape(s):
    return bytes(s, "utf-8").decode("unicode_escape")


_INDEX = re.compile(r"^(.*)\((R[0-8]|FP|SP)\)\s*$", re.I)
_STRING = re.compile(r'^"((?:\\.|[^"\\])*)"$')


def assemble(source, origin=0, predefined=None):
    lines = source.splitlines()
    symbols = dict(predefined or {})
    literals = {}       # literal text -> pool index

    def parse_line(raw):
        code = _strip_comment(raw).rstrip()
        label = None
        m = re.match(r"^\s*([A-Za-z_.][A-Za-z0-9_.]*)\s*:(.*)$", code)
        if m:
            label, code = m.group(1), m.group(2)
        code = code.strip()
        if not code:
            return label, None, None, None
        m = re.match(r"^([A-Za-z_.][A-Za-z0-9_.]*)\s*=\s*(.+)$", code)
        if m:
            return label, "=", m.group(1), m.group(2)
        parts = code.split(None, 1)
        return label, parts[0].upper(), parts[1] if len(parts) > 1 else "", None

    def size_of(op, rest, lineno):
        if op in isa.BY_NAME:
            return 1
        if op == "DATA":
            n = 0
            for item in _split_operands(rest):
                sm = _STRING.match(item)
                n += len(_unescape(sm.group(1))) if sm else 1
            return n
        if op == "STR":
            sm = _STRING.match(rest.strip())
            if not sm:
                raise AsmError(f"line {lineno}: STR needs a string")
            return 1 + len(_unescape(sm.group(1)))
        if op == "BSS":
            return _Expr(rest, symbols, 0, lineno, True).parse()
        if op in ("ORG", "ENTRY", "LTORG"):
            return 0
        raise AsmError(f"line {lineno}: unknown operation {op}")

    # ---------------- pass 1 ----------------
    loc = origin
    pool_at = None
    parsed = []
    for lineno, raw in enumerate(lines, 1):
        label, op, rest, extra = parse_line(raw)
        if label:
            if label in symbols and label not in (predefined or {}):
                raise AsmError(f"line {lineno}: duplicate label {label}")
            symbols[label] = loc
        parsed.append((lineno, raw, label, op, rest, extra, loc))
        if op is None:
            continue
        if op == "=":
            symbols[rest] = _Expr(extra, symbols, loc, lineno, True).parse()
            continue
        if op == "ORG":
            loc = _Expr(rest, symbols, loc, lineno, True).parse()
            continue
        if op == "LTORG":
            pool_at = loc
            loc += 10 ** 6       # placeholder, fixed below
            raise AsmError(f"line {lineno}: LTORG is not supported here")
        if op in isa.BY_NAME:
            for opnd in _split_operands(rest):
                if opnd.startswith("="):
                    body = _INDEX.match(opnd)
                    key = (body.group(1) if body else opnd)[1:].strip()
                    literals.setdefault(key, len(literals))
        loc += size_of(op, rest, lineno)
    pool_at = loc
    for key, i in literals.items():
        symbols[f".LIT{i}"] = pool_at + i
    end = pool_at + len(literals)
    symbols.setdefault("END_OF_PROGRAM", end)

    # ---------------- pass 2 ----------------
    obj = ObjectProgram()
    obj.symbols = symbols

    def ev(text, loc, lineno):
        return _Expr(text, symbols, loc, lineno, True).parse()

    def put(addr, w, text=""):
        obj.words[addr] = t.wrap(w)
        obj.listing.append(f"{addr:8}  {t.to_hept(t.wrap(w))}  {text}")

    def operand(text, loc, lineno):
        """Returns (mode, x, addr)."""
        text = text.strip()
        x = 0
        m = _INDEX.match(text)
        if m and m.group(1).strip():
            text = m.group(1).strip()
            x = REGS[m.group(2).upper()]
        if text.startswith("#"):
            return isa.MODE_IMM, x, ev(text[1:], loc, lineno)
        if text.startswith("@"):
            return isa.MODE_IND, x, ev(text[1:], loc, lineno)
        if text.startswith("="):
            return isa.MODE_DIR, x, symbols[f".LIT{literals[text[1:].strip()]}"]
        return isa.MODE_DIR, x, ev(text, loc, lineno)

    def reg(text, lineno):
        r = REGS.get(text.strip().upper())
        if r is None:
            raise AsmError(f"line {lineno}: expected a register, got {text!r}")
        return r

    for lineno, raw, label, op, rest, extra, loc in parsed:
        if op is None or op == "=" or op == "ORG":
            if op is None and label:
                obj.listing.append(f"{loc:8}             {raw.strip()}")
            continue
        try:
            if op in isa.BY_NAME:
                code, form = isa.BY_NAME[op]
                ops = _split_operands(rest)
                r = x = m = addr = 0
                if form == "RE":
                    if len(ops) != 2:
                        raise AsmError(f"line {lineno}: {op} needs R, operand")
                    r = reg(ops[0], lineno)
                    m, x, addr = operand(ops[1], loc, lineno)
                elif form == "RA":
                    if len(ops) != 2:
                        raise AsmError(f"line {lineno}: {op} needs R, address")
                    r = reg(ops[0], lineno)
                    m, x, addr = operand(ops[1], loc, lineno)
                    if m != isa.MODE_DIR:
                        raise AsmError(f"line {lineno}: {op} takes a plain address")
                elif form == "E":
                    if len(ops) != 1:
                        raise AsmError(f"line {lineno}: {op} needs an operand")
                    m, x, addr = operand(ops[0], loc, lineno)
                elif form == "R":
                    if len(ops) != 1:
                        raise AsmError(f"line {lineno}: {op} needs a register")
                    r = reg(ops[0], lineno)
                elif form == "I":
                    m = isa.MODE_IMM
                    if ops:
                        addr = ev(ops[0].lstrip("#"), loc, lineno)
                elif ops:
                    raise AsmError(f"line {lineno}: {op} takes no operands")
                put(loc, isa.encode(code, r, x, m, addr), raw.strip())
            elif op == "DATA":
                a = loc
                for item in _split_operands(rest):
                    sm = _STRING.match(item)
                    if sm:
                        for ch in _unescape(sm.group(1)):
                            put(a, ord(ch), raw.strip() if a == loc else "")
                            a += 1
                    else:
                        put(a, ev(item, a, lineno), raw.strip() if a == loc else "")
                        a += 1
            elif op == "STR":
                s = _unescape(_STRING.match(rest.strip()).group(1))
                put(loc, len(s), raw.strip())
                for i, ch in enumerate(s):
                    put(loc + 1 + i, ord(ch))
            elif op == "BSS":
                n = ev(rest, loc, lineno)
                for i in range(n):
                    obj.words[loc + i] = 0
                obj.listing.append(f"{loc:8}  ({n} words)  {raw.strip()}")
            elif op == "ENTRY":
                obj.entry = ev(rest, loc, lineno)
        except (KeyError, ValueError) as e:
            raise AsmError(f"line {lineno}: {e}: {raw.strip()}") from None

    for key, i in literals.items():
        a = symbols[f".LIT{i}"]
        put(a, ev(key, a, 0), f"literal ={key}")
    if obj.words:
        obj.low = min(obj.words)
        obj.high = max(obj.words)
    obj.end = end
    return obj
