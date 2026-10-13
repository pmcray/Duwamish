#!/usr/bin/env python3
"""
macro32.py -- a VAX MACRO-32 cross-assembler (and trivial linker).

Written for the Duwamish project so that Alan Fredericks' 1985 VAX MACRO
programs can be assembled on a modern host and run on an emulated MicroVAX II
/ VAXstation II (SIMH) under the MiniVMS executive.

It implements the parts of DEC's MACRO-32 language that real programs of the
period use:

  * the full VAX instruction set (opcode table generated from SIMH),
  * every addressing mode, including index mode and the B^ W^ L^ S^ I^ G^
    forcing operators, with automatic displacement sizing,
  * MACRO-32 expressions (left-to-right evaluation, <> grouping, ^X ^O ^B
    ^D ^A ^C ^M ^F operators, local labels 10$, the location counter '.'),
  * data directives (.BYTE .WORD .LONG .QUAD .ADDRESS .ASCII .ASCIZ .ASCIC
    .ASCID .F_FLOATING .D_FLOATING .G_FLOATING .BLKx .ALIGN ...),
  * .PSECT program sections (including ABS psects for structure offsets),
  * .ENTRY procedure entry masks, .END transfer address,
  * keyword/positional macros with defaults, created local labels (?LBL),
    string concatenation ('), \value arguments, .NARG, .MEXIT, %LENGTH,
  * conditional assembly (.IF/.IF_FALSE/.IF_TRUE/.ENDC/.IIF) and repeat
    blocks (.REPT/.IRP/.IRPC),
  * MACRO-style listings (code bytes shown right-to-left) and a symbol table.

Instead of producing object modules for a separate linker, every source file
named on the command line is assembled together and laid out at a fixed base
address -- effectively MACRO and LINK in one step.  Symbols exported by
another image (e.g. the system service vectors in MINIVMS.EXE) are imported
from a symbol table file (.STB), exactly the role SYS.STB plays on VMS.

Usage:
  macro32.py [-o OUT] [--base ADDR] [--format exe|raw] [-l LIS]
             [--stb-out STB] [--stb IN.STB ...] source.mar ...
"""

import argparse
import math
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vaxops import OPCODES, ALIASES  # noqa: E402

for _a, _b in ALIASES.items():
    OPCODES.setdefault(_a, OPCODES[_b])


class AsmError(Exception):
    pass


class Undef:
    """Value of an expression that references a not-yet-defined symbol."""
    _inst = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

    def __repr__(self):
        return 'UNDEF'


UNDEF = Undef()

REGS = {'R%d' % i: i for i in range(16)}
REGS.update({'AP': 12, 'FP': 13, 'SP': 14, 'PC': 15})

SYMCH = r'[A-Za-z0-9_$.]'
SYM_RE = re.compile(r'[A-Za-z_$.][A-Za-z0-9_$.]*')
LOCAL_RE = re.compile(r'\d+\$')

DATA_SIZES = {'b': 1, 'w': 2, 'l': 4, 'q': 8, 'o': 16,
              'f': 4, 'd': 8, 'g': 8, 'h': 16}


# --------------------------------------------------------------------------
# VAX floating point encodings
# --------------------------------------------------------------------------

def _vax_float_bits(x, expbits, fracbits):
    """Return (sign, exp, frac) for a VAX F/D/G value; exp biased by 2**(expbits-1)."""
    if x == 0.0:
        return 0, 0, 0
    sign = 1 if x < 0 else 0
    m, e = math.frexp(abs(x))           # x = m * 2**e, 0.5 <= m < 1
    frac = round((m * 2 - 1) * (1 << fracbits))
    if frac >= (1 << fracbits):
        frac = 0
        e += 1
    bias = 1 << (expbits - 1)
    exp = e + bias
    if exp <= 0:
        return 0, 0, 0                  # underflow -> 0
    if exp >= (1 << expbits):
        raise AsmError('floating point overflow: %r' % x)
    return sign, exp, frac


def vax_f(x):
    s, e, f = _vax_float_bits(x, 8, 23)
    bits = (s << 31) | (e << 23) | f
    # VAX stores the high-order word first in memory.
    return struct.pack('<HH', bits >> 16, bits & 0xFFFF)


def vax_d(x):
    s, e, f = _vax_float_bits(x, 8, 55)
    bits = (s << 63) | (e << 55) | f
    return struct.pack('<HHHH', (bits >> 48) & 0xFFFF, (bits >> 32) & 0xFFFF,
                       (bits >> 16) & 0xFFFF, bits & 0xFFFF)


def vax_g(x):
    s, e, f = _vax_float_bits(x, 11, 52)
    bits = (s << 63) | (e << 52) | f
    return struct.pack('<HHHH', (bits >> 48) & 0xFFFF, (bits >> 32) & 0xFFFF,
                       (bits >> 16) & 0xFFFF, bits & 0xFFFF)


def vax_h(x):
    s, e, f = _vax_float_bits(x, 15, 112)
    bits = (s << 127) | (e << 112) | f
    return b''.join(struct.pack('<H', (bits >> (112 - 16 * i)) & 0xFFFF)
                    for i in range(8))


FLOAT_ENC = {'f': vax_f, 'd': vax_d, 'g': vax_g, 'h': vax_h}


def short_float_literal(x):
    """Return the 6-bit short literal encoding of x, or None."""
    for e in range(8):
        for f in range(8):
            if (8 + f) / 16.0 * (1 << e) == x:
                return (e << 3) | f
    return None


FLOAT_RE = re.compile(r'^[+-]?(\d+\.\d*|\.\d+|\d+)([EeDdGgHh][+-]?\d+)?$')


# --------------------------------------------------------------------------
# Small text helpers
# --------------------------------------------------------------------------

def signed32(v):
    """Interpret an unsigned longword value as signed."""
    if 0x80000000 <= v < (1 << 32):
        return v - (1 << 32)
    return v


def strip_comment(text):
    """Remove a ';' comment, respecting <...>, ^A/x/ and string delimiters
    of .ASCIx directives."""
    out = []
    i, n = 0, len(text)
    depth = 0
    asc = re.search(r'\.ASCI[IZCD]\b', text, re.I)
    asc_start = asc.end() if asc else None
    while i < n:
        c = text[i]
        if asc_start is not None and i >= asc_start and depth == 0 \
                and c not in ' \t,<;':
            # delimited string
            j = text.find(c, i + 1)
            if j < 0:
                j = n - 1
            out.append(text[i:j + 1])
            i = j + 1
            continue
        if c == '^' and i + 2 < n and text[i + 1] in 'Aa' and \
                text[i + 2] not in ' \t':
            d = text[i + 2]
            j = text.find(d, i + 3)
            if j < 0:
                j = n - 1
            out.append(text[i:j + 1])
            i = j + 1
            continue
        if c == '<':
            depth += 1
        elif c == '>' and depth:
            depth -= 1
        elif c == ';' and depth == 0:
            break
        out.append(c)
        i += 1
    return ''.join(out).rstrip()


def split_args(text):
    """Split on top-level commas (respecting <> and ^A/x/ and quotes)."""
    parts, cur, depth, i, n = [], [], 0, 0, len(text)
    while i < n:
        c = text[i]
        if c == '^' and i + 2 < n and text[i + 1] in 'Aa' and depth == 0:
            d = text[i + 2]
            j = text.find(d, i + 3)
            if j < 0:
                j = n - 1
            cur.append(text[i:j + 1])
            i = j + 1
            continue
        if c == '<':
            depth += 1
        elif c == '>':
            depth = max(0, depth - 1)
        if c == ',' and depth == 0:
            parts.append(''.join(cur).strip())
            cur = []
        else:
            cur.append(c)
        i += 1
    last = ''.join(cur).strip()
    if parts or last:
        parts.append(last)
    return parts


def unbracket(s):
    s = s.strip()
    if s.startswith('<') and s.endswith('>'):
        # only strip when the brackets match each other
        depth = 0
        for i, c in enumerate(s):
            if c == '<':
                depth += 1
            elif c == '>':
                depth -= 1
                if depth == 0 and i != len(s) - 1:
                    return s
        return s[1:-1]
    if s.startswith('^') and len(s) >= 3 and s[1] not in 'AaXxOoBbDdCcMmFf' \
            and s[-1] == s[1]:
        return s[2:-1]
    return s


# --------------------------------------------------------------------------
# Expression evaluator (MACRO-32: unary ops bind tightest; binary operators
# all have equal precedence and are evaluated left to right)
# --------------------------------------------------------------------------

class Expr:
    def __init__(self, asm, text):
        self.asm = asm
        self.s = text
        self.i = 0

    def peek(self):
        self.skip()
        return self.s[self.i] if self.i < len(self.s) else ''

    def skip(self):
        while self.i < len(self.s) and self.s[self.i] in ' \t':
            self.i += 1

    def parse(self):
        v = self.expr()
        self.skip()
        if self.i != len(self.s):
            raise AsmError('junk in expression: %r' % self.s)
        return v

    def expr(self):
        v = self.term()
        while True:
            c = self.peek()
            if c and c in '+-*/@&!\\':
                self.i += 1
                w = self.term()
                v = self.binop(c, v, w)
            else:
                return v

    @staticmethod
    def binop(op, a, b):
        if a is UNDEF or b is UNDEF:
            return UNDEF
        if op == '+':
            return a + b
        if op == '-':
            return a - b
        if op == '*':
            return a * b
        if op == '/':
            if b == 0:
                raise AsmError('division by zero')
            q = abs(a) // abs(b)
            return q if (a >= 0) == (b >= 0) else -q
        if op == '@':
            return a << b if b >= 0 else a >> -b
        if op == '&':
            return a & b
        if op == '!':
            return a | b
        if op == '\\':
            return a ^ b
        raise AsmError('bad operator ' + op)

    def term(self):
        c = self.peek()
        if c == '+':
            self.i += 1
            return self.term()
        if c == '-':
            self.i += 1
            v = self.term()
            return UNDEF if v is UNDEF else -v
        if c == '<':
            self.i += 1
            v = self.expr()
            if self.peek() != '>':
                raise AsmError('missing > in expression: %r' % self.s)
            self.i += 1
            return v
        if c == '^':
            return self.circumflex()
        if c == '.' and (self.i + 1 >= len(self.s) or
                         not re.match(SYMCH, self.s[self.i + 1])):
            self.i += 1
            return self.asm.location()
        m = re.compile(r'\d+\$').match(self.s, self.i)
        if m:
            self.i = m.end()
            return self.asm.lookup(m.group(0))
        m = re.compile(r'(\d+)(\.?)').match(self.s, self.i)
        if m:
            self.i = m.end()
            radix = 10 if m.group(2) else self.asm.radix
            return int(m.group(1), radix)
        m = SYM_RE.match(self.s, self.i)
        if m:
            self.i = m.end()
            return self.asm.lookup(m.group(0))
        raise AsmError('bad expression: %r' % self.s)

    def circumflex(self):
        self.i += 1
        if self.i >= len(self.s):
            raise AsmError('bad ^ operator')
        k = self.s[self.i].upper()
        self.i += 1
        if k in 'XOBD':
            radix = {'X': 16, 'O': 8, 'B': 2, 'D': 10}[k]
            self.skip()
            if self.peek() == '<':
                save = self.asm.radix
                self.asm.radix = radix
                try:
                    return self.term()
                finally:
                    self.asm.radix = save
            digits = {16: '0-9A-Fa-f', 8: '0-7', 2: '01', 10: '0-9'}[radix]
            m = re.compile('[%s]+' % digits).match(self.s, self.i)
            if not m:
                raise AsmError('bad number after ^%s' % k)
            self.i = m.end()
            return int(m.group(0), radix)
        if k == 'C':
            v = self.term()
            return UNDEF if v is UNDEF else ~v & 0xFFFFFFFF
        if k == 'A':
            d = self.s[self.i]
            j = self.s.index(d, self.i + 1)
            txt = self.s[self.i + 1:j]
            self.i = j + 1
            v = 0
            for n, ch in enumerate(txt.encode('latin-1')):
                v |= ch << (8 * n)
            return v
        if k == 'M':
            self.skip()
            if self.peek() != '<':
                raise AsmError('^M needs <register list>')
            j = self.s.index('>', self.i)
            names = [x.strip().upper() for x in self.s[self.i + 1:j].split(',')
                     if x.strip()]
            self.i = j + 1
            mask = 0
            for nm in names:
                if nm == 'IV':
                    mask |= 0x4000
                elif nm == 'DV':
                    mask |= 0x8000
                elif nm in REGS:
                    mask |= 1 << REGS[nm]
                else:
                    raise AsmError('bad register in ^M: ' + nm)
            return mask
        if k == 'F':
            m = re.compile(r'[+-]?(\d+\.?\d*|\.\d+)([Ee][+-]?\d+)?').match(
                self.s, self.i)
            if not m:
                raise AsmError('bad ^F literal')
            self.i = m.end()
            return struct.unpack('<I', vax_f(float(m.group(0))))[0]
        raise AsmError('unknown operator ^' + k)


# --------------------------------------------------------------------------
# Operand parsing
# --------------------------------------------------------------------------

class Operand:
    def __init__(self, kind, reg=None, expr=None, deferred=False, force=None,
                 index=None, text=''):
        self.kind, self.reg, self.expr = kind, reg, expr
        self.deferred, self.force, self.index = deferred, force, index
        self.text = text


def reg_of(s):
    return REGS.get(s.strip().upper())


def parse_operand(text):
    t = text.strip()
    orig = t
    index = None
    m = re.match(r'^(.*)\[\s*([A-Za-z0-9]+)\s*\]$', t)
    if m and reg_of(m.group(2)) is not None:
        index = reg_of(m.group(2))
        t = m.group(1).strip()
    force = None
    m = re.match(r'^([SIBWLGsibwlg])\^(.*)$', t)
    if m:
        force = m.group(1).upper()
        t = m.group(2).strip()
    deferred = False
    if t.startswith('@'):
        deferred = True
        t = t[1:].strip()
        if force is None:
            m = re.match(r'^([BWLGbwlg])\^(.*)$', t)
            if m:
                force = m.group(1).upper()
                t = m.group(2).strip()
    if t.startswith('#'):
        if force is None:
            m = re.match(r'^#\s*([SIsi])\^(.*)$', t)
            if m:
                force = m.group(1).upper()
                t = '#' + m.group(2)
        k = 'abs' if deferred else 'lit'
        return Operand(k, expr=t[1:].strip(), force=force, index=index,
                       text=orig)
    if reg_of(t) is not None:
        if deferred:
            raise AsmError('illegal operand ' + orig)
        return Operand('reg', reg=reg_of(t), index=index, text=orig)
    m = re.match(r'^\(\s*(\w+)\s*\)\+$', t)
    if m and reg_of(m.group(1)) is not None:
        return Operand('autoinc', reg=reg_of(m.group(1)), deferred=deferred,
                       index=index, text=orig)
    m = re.match(r'^-\(\s*(\w+)\s*\)$', t)
    if m and reg_of(m.group(1)) is not None:
        if deferred:
            raise AsmError('illegal operand ' + orig)
        return Operand('autodec', reg=reg_of(m.group(1)), index=index,
                       text=orig)
    m = re.match(r'^\(\s*(\w+)\s*\)$', t)
    if m and reg_of(m.group(1)) is not None:
        if deferred:
            return Operand('disp', reg=reg_of(m.group(1)), expr='0',
                           deferred=True, force=force, index=index, text=orig)
        return Operand('regdef', reg=reg_of(m.group(1)), index=index,
                       text=orig)
    m = re.match(r'^(.*)\(\s*(\w+)\s*\)$', t)
    if m and reg_of(m.group(2)) is not None and m.group(1).strip():
        return Operand('disp', reg=reg_of(m.group(2)), expr=m.group(1).strip(),
                       deferred=deferred, force=force, index=index, text=orig)
    if not t:
        raise AsmError('missing operand')
    return Operand('rel', expr=t, deferred=deferred, force=force, index=index,
                   text=orig)


# --------------------------------------------------------------------------
# Program sections
# --------------------------------------------------------------------------

ALIGNS = {'BYTE': 0, 'WORD': 1, 'LONG': 2, 'QUAD': 3, 'OCTA': 4, 'PAGE': 9}


class Psect:
    def __init__(self, name, order):
        self.name = name
        self.order = order
        self.align = 0
        self.abs = False
        self.attrs = set()
        self.data = bytearray()
        self.loc = 0
        self.size = 0
        self.inited = 0      # high-water mark of initialised data

    def put(self, b):
        end = self.loc + len(b)
        if end > len(self.data):
            self.data.extend(bytes(end - len(self.data)))
        self.data[self.loc:end] = b
        self.loc = end
        self.size = max(self.size, end)
        self.inited = max(self.inited, end)

    def reserve(self, n):
        self.loc += n
        self.size = max(self.size, self.loc)


# --------------------------------------------------------------------------
# Macros
# --------------------------------------------------------------------------

class Macro:
    def __init__(self, name, formals, body):
        self.name = name
        self.formals = formals     # list of (name, default, created)
        self.body = body           # list of (text, file, line)


# --------------------------------------------------------------------------
# The assembler
# --------------------------------------------------------------------------

class Assembler:
    MAXPASS = 40

    def __init__(self, files, base=0, imported=None):
        self.files = files
        self.base = base
        self.imported = imported or {}
        self.prev = {}           # symbol values at end of previous pass
        self.sizes = {}          # site -> chosen size (for relaxation)
        self.prev_bases = {}

    # ---- symbols ----------------------------------------------------------

    def local_key(self, name):
        # Labels created by macros (?LABEL -> 30000$ upwards) are unique,
        # so they need no local-block scoping (this lets a macro define
        # one in another psect).
        if int(name[:-1]) >= 30000:
            return name.upper()
        return '%s@%d' % (name.upper(), self.lsb)

    def lookup(self, name):
        u = name.upper()
        if LOCAL_RE.fullmatch(u):
            key = self.local_key(u)
        else:
            key = u
            if u in REGS:
                raise AsmError('register %s used in expression' % u)
        if key in self.labels:
            ps, off = self.labels[key]
            return self.psect_base(ps) + off
        if key in self.syms:
            return self.syms[key]
        if key in self.imported:
            return self.imported[key]
        if key in self.prev:
            return self.prev[key]
        self.undefined_refs.add(key)
        return UNDEF

    def defined(self, name):
        u = name.upper()
        return (u in self.labels or u in self.syms or u in self.imported)

    def psect_base(self, ps):
        if ps.abs:
            return 0
        return self.prev_bases.get(ps.name, self.base)

    def location(self):
        return self.psect_base(self.cur) + self.cur.loc

    def define_label(self, name, glob=False):
        u = name.upper()
        if LOCAL_RE.fullmatch(u):
            key = self.local_key(u)
        else:
            key = u
            if not self.lsb_enabled:
                self.lsb_counter += 1
                self.lsb = self.lsb_counter
        if key in self.labels or key in self.syms:
            raise AsmError('multiply defined symbol ' + u)
        # labels after a non-local label are in the new local block
        if LOCAL_RE.fullmatch(u):
            key = self.local_key(u)
        self.labels[key] = (self.cur, self.cur.loc)
        if glob:
            self.globals.add(key)

    def evaluate(self, text):
        return Expr(self, text).parse()

    def value(self, text, what='expression'):
        v = self.evaluate(text)
        if v is UNDEF and self.final:
            raise AsmError('undefined symbol in %s: %s' % (what, text))
        return v

    def const(self, text):
        """An expression that must be known now (e.g. .BLKB count)."""
        v = self.evaluate(text)
        if v is UNDEF:
            if self.final:
                raise AsmError('undefined symbol in %s' % text)
            return 0
        return v

    # ---- pass driver ------------------------------------------------------

    def run(self):
        for passno in range(1, self.MAXPASS + 1):
            self.passno = passno
            self.final = False
            self.one_pass()
            # compute bases for next pass
            bases = {}
            addr = self.base
            for ps in sorted(self.psects.values(), key=lambda p: p.order):
                if ps.abs:
                    continue
                a = 1 << ps.align
                addr = (addr + a - 1) & ~(a - 1)
                bases[ps.name] = addr
                addr += ps.size
            values = dict(self.syms)
            for key, (ps, off) in self.labels.items():
                values[key] = (0 if ps.abs else bases[ps.name]) + off
            stable = (values == self.prev and bases == self.prev_bases and
                      self.sizes == self.prev_sizes)
            self.prev = values
            self.prev_bases = bases
            if stable and passno >= 2:
                # Re-run as the final pass: identical inputs, but now
                # undefined symbols and range errors are reported.
                self.final = True
                self.one_pass()
                if self.errors:
                    return False
                self.end_address = addr
                return True
        raise AsmError('assembly did not converge')

    def one_pass(self):
        self.prev_sizes = dict(self.sizes)
        self.syms = {}
        self.labels = {}
        self.globals = set()
        self.psects = {}
        self.macros = {}
        self.cur = self.get_psect('. BLANK .')
        self.radix = 10
        self.lsb = 0
        self.lsb_counter = 0
        self.lsb_enabled = False
        self.site = 0
        self.created_label = 30000
        self.transfer = None
        self.title = ''
        self.ident = ''
        self.errors = []
        self.listing = []
        self.undefined_refs = set()
        self.cond = []          # stack of [active, value, parent_active]
        self.psect_stack = []
        for name, val in self.imported.items():
            pass
        for f in self.files:
            with open(f, encoding='latin-1') as fh:
                lines = fh.read().split('\n')
            src = [(l.rstrip('\r'), f, i + 1) for i, l in enumerate(lines)]
            self.ended = False
            self.process_lines(src, depth=0)
            if self.cond:
                self.error(f, len(lines), 'missing .ENDC')
                self.cond = []

    def error(self, f, line, msg):
        if self.final:
            self.errors.append('%s:%d: %%MACRO-E-ERROR, %s' %
                               (os.path.basename(f), line, msg))

    def get_psect(self, name):
        u = name.upper()
        if u not in self.psects:
            self.psects[u] = Psect(u, len(self.psects))
        return self.psects[u]

    def active(self):
        return all(c[0] for c in self.cond)

    # ---- line processing -------------------------------------------------

    def join_continuations(self, src):
        out = []
        buf = None
        for text, f, ln in src:
            body = strip_comment(text)
            if buf is not None:
                buf = (buf[0] + ' ' + body.strip(), buf[1], buf[2], buf[3] +
                       [text])
            else:
                buf = (body, f, ln, [text])
            if buf[0].endswith('-') and not buf[0].endswith('--'):
                buf = (buf[0][:-1], buf[1], buf[2], buf[3])
                continue
            out.append(buf)
            buf = None
        if buf is not None:
            out.append(buf)
        return out

    def process_lines(self, src, depth, macro_args=None):
        if depth > 60:
            raise AsmError('macro nesting too deep')
        lines = self.join_continuations(src)
        i = 0
        while i < len(lines):
            if self.ended:
                return
            text, f, ln, raw = lines[i]
            i += 1
            try:
                # Block-structured directives that swallow following lines
                m = re.match(r'^\s*(?:[A-Za-z0-9_$.]+::?\s*)*'
                             r'(\.MACRO|\.REPT|\.REPEAT|\.IRPC?)\b(.*)$',
                             text, re.I)
                if m and self.active():
                    kind = m.group(1).upper()
                    body, i = self.collect_block(lines, i, kind)
                    self.list_line(f, ln, raw, depth)
                    if kind == '.MACRO':
                        self.define_macro(m.group(2), body)
                    else:
                        self.expand_repeat(kind, m.group(2), body, depth)
                    continue
                if m and not self.active():
                    # skip the block entirely
                    _, i = self.collect_block(lines, i, m.group(1).upper())
                    continue
                if self.handle_conditional(text):
                    self.list_line(f, ln, raw, depth)
                    continue
                if not self.active():
                    continue
                self.cur_file, self.cur_line = f, ln
                r = self.statement(text, f, ln, raw, depth)
                if r == 'MEXIT':
                    return 'MEXIT'
            except AsmError as e:
                self.error(f, ln, str(e))
                self.list_line(f, ln, raw, depth)

    def collect_block(self, lines, i, kind):
        opener = re.compile(r'^\s*(?:[A-Za-z0-9_$.]+::?\s*)*'
                            r'(\.MACRO|\.REPT|\.REPEAT|\.IRPC?)\b', re.I)
        if kind == '.MACRO':
            closer = re.compile(r'^\s*\.ENDM\b', re.I)
        else:
            closer = re.compile(r'^\s*\.ENDR\b', re.I)
        depth = 1
        body = []
        while i < len(lines):
            text, f, ln, raw = lines[i]
            i += 1
            om = opener.match(text)
            if om:
                k = om.group(1).upper()
                if (k == '.MACRO') == (kind == '.MACRO'):
                    depth += 1
            elif closer.match(text):
                depth -= 1
                if depth == 0:
                    return body, i
            body.append((text, f, ln))
        raise AsmError('unterminated ' + kind)

    # ---- conditionals ----------------------------------------------------

    def handle_conditional(self, text):
        m = re.match(r'^\s*(\.[A-Za-z_]+)\s*(.*)$', text)
        if not m:
            return False
        d = m.group(1).upper()
        rest = m.group(2).strip()
        if d == '.IF':
            parent = self.active()
            val = self.eval_condition(rest) if parent else False
            self.cond.append([val, val, parent])
            return True
        if d in ('.IF_FALSE', '.IFF', '.ELSE'):
            c = self.cond[-1]
            c[0] = c[2] and not c[1]
            return True
        if d in ('.IF_TRUE', '.IFT'):
            c = self.cond[-1]
            c[0] = c[2] and c[1]
            return True
        if d in ('.IF_TRUE_FALSE', '.IFTF'):
            c = self.cond[-1]
            c[0] = c[2]
            return True
        if d == '.ENDC':
            if not self.cond:
                raise AsmError('.ENDC without .IF')
            self.cond.pop()
            return True
        if d == '.IIF':
            if not self.active():
                return True
            parts = split_args(rest)
            # condition and its argument(s) come before the statement
            mm = re.match(r'^(\w+)\s+(.*)$', rest)
            cond = mm.group(1).upper()
            body = mm.group(2)
            if cond in ('IDN', 'DIF', 'IDENTICAL', 'DIFFERENT'):
                a = split_args(body)
                carg = ','.join(a[:2])
                stmt = ','.join(a[2:])
            else:
                a = split_args(body)
                carg = a[0]
                stmt = ','.join(a[1:])
            if self.eval_condition(cond + ' ' + carg):
                self.statement(stmt, self.cur_file, self.cur_line, [], 1)
            return True
        return False

    def eval_condition(self, rest):
        m = re.match(r'^(\w+)\s*,?\s*(.*)$', rest)
        if not m:
            raise AsmError('bad .IF')
        c = m.group(1).upper()
        arg = m.group(2).strip()
        alias = {'EQUAL': 'EQ', 'NOT_EQUAL': 'NE', 'GREATER': 'GT',
                 'LESS_THAN': 'LT', 'GREATER_EQUAL': 'GE', 'LESS_EQUAL': 'LE',
                 'DEFINED': 'DF', 'NOT_DEFINED': 'NDF', 'BLANK': 'B',
                 'NOT_BLANK': 'NB', 'IDENTICAL': 'IDN', 'DIFFERENT': 'DIF'}
        c = alias.get(c, c)
        if c in ('EQ', 'NE', 'GT', 'LT', 'GE', 'LE'):
            v = self.evaluate(arg)
            if v is UNDEF:
                v = 0
            v = signed32(v)
            return {'EQ': v == 0, 'NE': v != 0, 'GT': v > 0, 'LT': v < 0,
                    'GE': v >= 0, 'LE': v <= 0}[c]
        if c in ('DF', 'NDF'):
            d = self.defined(arg)
            return d if c == 'DF' else not d
        if c in ('B', 'NB'):
            blank = unbracket(arg).strip() == ''
            return blank if c == 'B' else not blank
        if c in ('IDN', 'DIF'):
            a = split_args(arg)
            a += [''] * (2 - len(a))
            same = unbracket(a[0]).strip().upper() == \
                unbracket(a[1]).strip().upper()
            return same if c == 'IDN' else not same
        raise AsmError('unknown condition ' + c)

    # ---- macros ------------------------------------------------------------

    def define_macro(self, header, body):
        parts = header.strip().split(None, 1)
        name = parts[0].rstrip(',').upper()
        formals = []
        if len(parts) > 1:
            for a in split_args(parts[1].replace('\t', ' ')):
                for piece in ([a] if '=' in a or '<' in a else a.split()):
                    piece = piece.strip()
                    if not piece:
                        continue
                    created = piece.startswith('?')
                    piece = piece.lstrip('?')
                    if '=' in piece:
                        nm, dv = piece.split('=', 1)
                        formals.append((nm.strip().upper(), unbracket(dv),
                                        created))
                    else:
                        formals.append((piece.upper(), '', created))
        self.macros[name] = Macro(name, formals, body)

    def call_macro(self, mac, argtext, depth):
        actual = {}
        positional = []
        for a in split_args(argtext) if argtext.strip() else []:
            m = re.match(r'^([A-Za-z_$][A-Za-z0-9_$]*)\s*=(?!=)(.*)$', a)
            if m and m.group(1).upper() in [f[0] for f in mac.formals]:
                actual[m.group(1).upper()] = self.macro_arg(m.group(2))
            else:
                positional.append(self.macro_arg(a))
        names = [f[0] for f in mac.formals]
        for k, v in zip(names, positional):
            actual.setdefault(k, v)
        subst = {}
        for nm, dv, created in mac.formals:
            if nm in actual and actual[nm] != '':
                subst[nm] = actual[nm]
            elif created:
                subst[nm] = '%d$' % self.created_label
                self.created_label += 1
            else:
                subst[nm] = dv
        self.narg = len(positional)
        out = []
        for text, f, ln in mac.body:
            out.append((self.substitute(text, subst), f, ln))
        saved_lsb = None
        r = self.process_lines(out, depth + 1)
        return r

    def macro_arg(self, a):
        a = a.strip()
        if a.startswith('\\'):
            v = self.evaluate(a[1:])
            return '0' if v is UNDEF else str(v)
        return unbracket(a)

    def substitute(self, text, subst):
        if not subst:
            return text

        out = []
        pos = 0
        for m in re.finditer(r'[A-Za-z_$][A-Za-z0-9_$]*', text):
            u = m.group(0).upper()
            if u not in subst:
                continue
            s, e = m.start(), m.end()
            seg = text[pos:s]
            if seg.endswith("'"):          # concatenation operator
                seg = seg[:-1]
            out.append(seg)
            out.append(subst[u])
            if text[e:e + 1] == "'":
                e += 1
            pos = e
        out.append(text[pos:])
        text = ''.join(out)
        # %LENGTH(string) and %EXTRACT(start,length,string)
        text = re.sub(r'%LENGTH\(([^)]*)\)', lambda m: str(len(m.group(1))),
                      text, flags=re.I)

        def ext(m):
            s, n, st = m.group(1), m.group(2), m.group(3)
            return st[int(s):int(s) + int(n)]
        text = re.sub(r'%EXTRACT\(\s*(\d+)\s*,\s*(\d+)\s*,([^)]*)\)', ext,
                      text, flags=re.I)
        return text

    def expand_repeat(self, kind, rest, body, depth):
        rest = rest.strip()
        if kind in ('.REPT', '.REPEAT'):
            n = self.const(rest)
            for _ in range(n):
                self.process_lines(list(body), depth + 1)
            return
        parts = split_args(rest)
        sym = parts[0].upper()
        if kind == '.IRP':
            items = split_args(unbracket(','.join(parts[1:])))
            for it in items:
                self.process_lines([(self.substitute(t, {sym: unbracket(it)}),
                                     f, l) for t, f, l in body], depth + 1)
        else:  # .IRPC
            for ch in unbracket(','.join(parts[1:])):
                self.process_lines([(self.substitute(t, {sym: ch}), f, l)
                                    for t, f, l in body], depth + 1)

    # ---- statements --------------------------------------------------------

    def statement(self, text, f, ln, raw, depth):
        start_ps = self.cur
        start_loc = self.cur.loc
        start_addr = self.location()
        rest = text
        # assignment?
        m = re.match(r'^\s*([A-Za-z_$.][A-Za-z0-9_$.]*)\s*(==|=)(?!=)\s*(.*)$',
                     rest)
        if m:
            name, op, expr = m.group(1).upper(), m.group(2), m.group(3)
            v = self.value(expr)
            if name == '.':
                if v is not UNDEF:
                    self.cur.loc = v - self.psect_base(self.cur)
                    self.cur.size = max(self.cur.size, self.cur.loc)
            else:
                if name in self.labels:
                    raise AsmError('label redefined: ' + name)
                self.syms[name] = v if v is not UNDEF else 0
                if v is UNDEF:
                    self.syms.pop(name)
                if op == '==':
                    self.globals.add(name)
            self.list_line(f, ln, raw, depth, value=v)
            return
        # labels
        while True:
            m = re.match(r'^\s*([A-Za-z0-9_$.]+)(::?)\s*', rest)
            if not m or (m.group(1)[0].isdigit() and
                         not LOCAL_RE.fullmatch(m.group(1))):
                break
            self.define_label(m.group(1), glob=(m.group(2) == '::'))
            rest = rest[m.end():]
        m = re.match(r'^\s*([A-Za-z_$.%][A-Za-z0-9_$.]*)\s*(.*)$', rest)
        if not m:
            if rest.strip():
                raise AsmError('syntax error: ' + rest.strip())
            self.list_line(f, ln, raw, depth, ps=start_ps, loc=start_loc,
                           addr=start_addr)
            return
        op = m.group(1).upper()
        args = m.group(2).strip()
        r = None
        if op in self.macros:
            self.list_line(f, ln, raw, depth, ps=start_ps, loc=start_loc,
                           addr=start_addr)
            r = self.call_macro(self.macros[op], args, depth)
            return None
        if op.startswith('.'):
            r = self.directive(op, args)
        elif op in OPCODES:
            self.instruction(op, args)
        else:
            raise AsmError('unknown opcode or macro: ' + op)
        self.list_line(f, ln, raw, depth, ps=start_ps, loc=start_loc,
                       addr=start_addr)
        return r

    # ---- listing -----------------------------------------------------------

    def list_line(self, f, ln, raw, depth, ps=None, loc=None, addr=None,
                  value=None):
        if not self.final:
            return
        code = b''
        if ps is not None and not ps.abs and loc is not None:
            code = bytes(ps.data[loc:ps.loc]) if ps.loc > loc else b''
        self.listing.append((f, ln, raw, depth, code, addr, value,
                             ps.abs if ps else False))

    def write_listing(self, path):
        out = []
        page = 0
        for f, ln, raw, depth, code, addr, value, isabs in self.listing:
            lines = raw if raw else ['']
            chunks = [code[i:i + 8] for i in range(0, len(code), 8)] or [b'']
            for n, chunk in enumerate(chunks):
                hexs = ' '.join('%02X' % b for b in reversed(chunk))
                if value is not None and value is not UNDEF and n == 0 and \
                        not code:
                    hexs = '%08X' % (value & 0xFFFFFFFF)
                a = '%08X' % (addr & 0xFFFFFFFF) if addr is not None and \
                    (code or n == 0) and not isabs else ' ' * 8
                if not code and value is None:
                    a = ' ' * 8 if not code else a
                if n == 0:
                    src = lines[0] if lines else ''
                    mark = '' if depth == 0 else '+'
                    out.append('%24s %s %5d%1s %s' % (hexs, a, ln, mark,
                                                      src.expandtabs()))
                    for extra in lines[1:]:
                        out.append('%24s %s %5s  %s' % ('', ' ' * 8, '',
                                                         extra.expandtabs()))
                else:
                    out.append('%24s %08X' % (hexs, addr + 8 * n))
        out.append('')
        out.append('Symbol table')
        out.append('------------')
        syms = []
        for key, val in self.prev.items():
            if '@' in key:
                continue
            syms.append('%-31s %08X%s' % (key, val & 0xFFFFFFFF,
                                         ' G' if key in self.globals else ''))
        out.extend(sorted(syms))
        out.append('')
        out.append('Program sections')
        out.append('----------------')
        for ps in sorted(self.psects.values(), key=lambda p: p.order):
            if ps.size == 0 and ps.name == '. BLANK .':
                continue
            b = 0 if ps.abs else self.prev_bases[ps.name]
            out.append('%-31s base %08X size %08X align %d%s' % (
                ps.name, b, ps.size, ps.align, ' ABS' if ps.abs else ''))
        with open(path, 'w') as fh:
            fh.write('\n'.join(out) + '\n')

    # ---- directives ----------------------------------------------------------

    def directive(self, op, args):
        ps = self.cur
        if op in ('.TITLE',):
            self.title = args
            return
        if op == '.IDENT':
            self.ident = unbracket(args.strip())
            s = args.strip()
            if len(s) >= 2:
                self.ident = s[1:-1]
            return
        if op in ('.SBTTL', '.SUBTITLE', '.PAGE', '.LIST', '.NLIST', '.SHOW',
                  '.NOSHOW', '.DEFAULT', '.EXTERNAL', '.EXTRN', '.GLOBAL',
                  '.GLOBL', '.WEAK', '.LIBRARY', '.MCALL', '.LINK',
                  '.DSABL', '.ENABL', '.CROSS', '.NOCROSS', '.PRINT',
                  '.PSECT_ATTR', '.DEBUG', '.TRANSFER', '.MASK'):
            if op in ('.GLOBAL', '.GLOBL'):
                for a in split_args(args):
                    self.globals.add(a.upper())
            if op == '.PRINT' and self.final:
                print('%MACRO-I-PRINT,', args)
            return
        if op in ('.ENABLE', '.DISABLE'):
            for a in split_args(args):
                if a.upper() in ('LSB', 'LOCAL_BLOCK'):
                    if op == '.ENABLE':
                        self.lsb_counter += 1
                        self.lsb = self.lsb_counter
                        self.lsb_enabled = True
                    else:
                        self.lsb_enabled = False
                        self.lsb_counter += 1
                        self.lsb = self.lsb_counter
            return
        if op in ('.ERROR', '.WARN'):
            raise AsmError('%s %s' % (op, args))
        if op == '.END':
            if args.strip():
                self.transfer = self.value(args, '.END')
            self.ended = True
            return
        if op == '.MEXIT':
            return 'MEXIT'
        if op == '.NARG':
            self.syms[args.strip().upper()] = getattr(self, 'narg', 0)
            return
        if op == '.RADIX':
            self.radix = int(args.strip())
            return
        if op in ('.SAVE_PSECT', '.SAVE'):
            self.psect_stack.append((self.cur, self.lsb))
            return
        if op in ('.RESTORE_PSECT', '.RESTORE'):
            if not self.psect_stack:
                raise AsmError('.RESTORE_PSECT without .SAVE_PSECT')
            self.cur, self.lsb = self.psect_stack.pop()
            return
        if op == '.PSECT':
            parts = split_args(args) if args.strip() else ['. BLANK .']
            p = self.get_psect(parts[0] or '. BLANK .')
            for a in parts[1:]:
                u = a.upper()
                if u in ALIGNS:
                    p.align = max(p.align, ALIGNS[u])
                elif u.isdigit():
                    p.align = max(p.align, int(u))
                elif u == 'ABS':
                    p.abs = True
                else:
                    p.attrs.add(u)
            self.cur = p
            if not self.lsb_enabled:
                self.lsb_counter += 1
                self.lsb = self.lsb_counter
            return
        if op == '.ENTRY':
            parts = split_args(args)
            self.define_label(parts[0], glob=True)
            mask = self.value(parts[1]) if len(parts) > 1 else 0
            self.emit_int(0 if mask is UNDEF else mask, 2)
            return
        if op in ('.BYTE', '.WORD', '.LONG', '.QUAD', '.ADDRESS',
                  '.SIGNED_BYTE', '.SIGNED_WORD', '.OCTA'):
            size = {'.BYTE': 1, '.WORD': 2, '.LONG': 4, '.QUAD': 8,
                    '.ADDRESS': 4, '.SIGNED_BYTE': 1, '.SIGNED_WORD': 2,
                    '.OCTA': 16}[op]
            for a in split_args(args) or ['0']:
                rep = 1
                mm = re.match(r'^(.*)\[(.*)\]$', a)
                if mm:
                    a, rep = mm.group(1), self.const(mm.group(2))
                v = self.value(a) if a.strip() else 0
                for _ in range(rep):
                    self.emit_int(0 if v is UNDEF else v, size,
                                  check=op.startswith('.SIGNED'))
            return
        if op in ('.F_FLOATING', '.FLOAT', '.D_FLOATING', '.DOUBLE',
                  '.G_FLOATING', '.H_FLOATING'):
            t = {'.F_FLOATING': 'f', '.FLOAT': 'f', '.D_FLOATING': 'd',
                 '.DOUBLE': 'd', '.G_FLOATING': 'g', '.H_FLOATING': 'h'}[op]
            for a in split_args(args):
                self.cur.put(FLOAT_ENC[t](self.float_value(a)))
            return
        if op in ('.ASCII', '.ASCIZ', '.ASCIC', '.ASCID'):
            s = self.parse_strings(args)
            if op == '.ASCIZ':
                s += b'\0'
            elif op == '.ASCIC':
                if len(s) > 255:
                    raise AsmError('.ASCIC string too long')
                s = bytes([len(s)]) + s
            elif op == '.ASCID':
                hdr = struct.pack('<HBBI', len(s), 14, 1,
                                  (self.location() + 8) & 0xFFFFFFFF)
                s = hdr + s
            self.cur.put(s)
            return
        if op in ('.BLKB', '.BLKW', '.BLKL', '.BLKQ', '.BLKO', '.BLKF',
                  '.BLKD', '.BLKG', '.BLKH', '.BLKA'):
            unit = {'.BLKB': 1, '.BLKW': 2, '.BLKL': 4, '.BLKQ': 8,
                    '.BLKO': 16, '.BLKF': 4, '.BLKD': 8, '.BLKG': 8,
                    '.BLKH': 16, '.BLKA': 4}[op]
            n = self.const(args) if args.strip() else 1
            self.cur.reserve(n * unit)
            return
        if op in ('.ALIGN', '.EVEN', '.ODD'):
            if op == '.EVEN':
                bits, fill = 1, 0
            elif op == '.ODD':
                if self.cur.loc % 2 == 0:
                    self.cur.reserve(1)
                return
            else:
                parts = split_args(args)
                u = parts[0].upper()
                bits = ALIGNS[u] if u in ALIGNS else self.const(parts[0])
                fill = self.const(parts[1]) if len(parts) > 1 else None
            ps.align = max(ps.align, bits)
            a = 1 << bits
            pad = (-self.cur.loc) % a
            if fill is None:
                self.cur.reserve(pad)
            else:
                self.cur.put(bytes([fill & 0xFF]) * pad)
            return
        raise AsmError('unknown directive ' + op)

    def float_value(self, text):
        t = text.strip()
        if t.upper().startswith('^F'):
            t = t[2:]
        if FLOAT_RE.match(t):
            return float(re.sub('[DdGgHh]', 'E', t))
        v = self.value(t)
        return 0.0 if v is UNDEF else float(v)

    def parse_strings(self, args):
        out = bytearray()
        i, n = 0, len(args)
        while i < n:
            c = args[i]
            if c in ' \t,':
                i += 1
                continue
            if c == '<':
                j = args.index('>', i)
                v = self.value(args[i + 1:j])
                out.append(0 if v is UNDEF else v & 0xFF)
                i = j + 1
                continue
            j = args.find(c, i + 1)
            if j < 0:
                raise AsmError('unterminated string')
            out += args[i + 1:j].encode('latin-1')
            i = j + 1
        return bytes(out)

    def emit_int(self, v, size, check=False):
        if self.final and check:
            lo, hi = -(1 << (8 * size - 1)), (1 << (8 * size - 1)) - 1
            if not lo <= v <= hi:
                raise AsmError('value %d out of range' % v)
        if self.final and size <= 4 and not check:
            if not -(1 << (8 * size - 1)) <= v < (1 << (8 * size)) and \
                    size < 4:
                raise AsmError('data truncation: %d does not fit in %d '
                               'bytes' % (v, size))
        v &= (1 << (8 * size)) - 1
        self.cur.put(v.to_bytes(size, 'little'))

    # ---- instructions ------------------------------------------------------

    def next_site(self):
        self.site += 1
        return self.site

    def pick(self, site, candidates, fits):
        """Choose the smallest candidate size for which fits(size) is true.
        Sizes never shrink after pass 2 (guarantees convergence)."""
        floor = self.prev_sizes.get(site, 0) if self.passno >= 3 else 0
        for s in candidates:
            if s < floor:
                continue
            if fits(s):
                self.sizes[site] = s
                return s
        s = candidates[-1]
        self.sizes[site] = s
        return s

    def instruction(self, op, args):
        code, specs = OPCODES[op]
        ops = split_args(args) if args.strip() else []
        if len(ops) != len(specs):
            raise AsmError('%s needs %d operand(s), got %d' %
                           (op, len(specs), len(ops)))
        if code > 0xFF:
            self.cur.put(bytes([code >> 8, code & 0xFF]))
        else:
            self.cur.put(bytes([code]))
        for text, spec in zip(ops, specs):
            if spec in ('bb', 'bw'):
                size = 1 if spec == 'bb' else 2
                tgt = self.value(text, 'branch')
                end = self.location() + size
                if tgt is UNDEF:
                    disp = 0
                else:
                    disp = tgt - end
                    lim = 1 << (8 * size - 1)
                    if self.final and not -lim <= disp < lim:
                        raise AsmError('branch out of range (%d bytes) to %s'
                                       % (disp, text))
                self.cur.put((disp & ((1 << (8 * size)) - 1)).to_bytes(
                    size, 'little'))
            else:
                self.operand(parse_operand(text), spec)

    def operand(self, o, spec):
        access, dtype = spec[0], spec[1]
        isfloat = access == 'r' and dtype in 'fdgh'
        dsize = DATA_SIZES[dtype]
        if access == 'r' and dtype in 'fdgh':
            pass
        if o.index is not None:
            if o.kind in ('reg', 'lit'):
                raise AsmError('illegal index base: ' + o.text)
            if o.index == 15:
                raise AsmError('PC cannot be an index register')
            self.cur.put(bytes([0x40 | o.index]))
        k = o.kind
        if k == 'reg':
            if access in 'a':
                raise AsmError('register not allowed for address operand: ' +
                               o.text)
            self.cur.put(bytes([0x50 | o.reg]))
            return
        if k == 'regdef':
            self.cur.put(bytes([0x60 | o.reg]))
            return
        if k == 'autodec':
            self.cur.put(bytes([0x70 | o.reg]))
            return
        if k == 'autoinc':
            self.cur.put(bytes([(0x90 if o.deferred else 0x80) | o.reg]))
            return
        if k == 'abs':
            v = self.value(o.expr)
            self.cur.put(bytes([0x9F]))
            self.cur.put(((0 if v is UNDEF else v) & 0xFFFFFFFF).to_bytes(
                4, 'little'))
            return
        if k == 'lit':
            self.literal(o, access, dtype, isfloat, dsize)
            return
        if k == 'disp':
            v = self.value(o.expr)
            site = self.next_site()
            if o.force in ('B', 'W', 'L'):
                s = {'B': 1, 'W': 2, 'L': 4}[o.force]
            else:
                def fits(sz):
                    if v is UNDEF:
                        return sz == 4 if self.passno > 1 else True
                    sv = signed32(v)
                    lim = 1 << (8 * sz - 1)
                    return -lim <= sv < lim
                s = self.pick(site, [1, 2, 4], fits)
            mode = {1: 0xA0, 2: 0xC0, 4: 0xE0}[s] | (0x10 if o.deferred else 0)
            self.cur.put(bytes([mode | o.reg]))
            vv = 0 if v is UNDEF else v
            if self.final:
                sv = signed32(vv)
                lim = 1 << (8 * s - 1)
                if not -lim <= sv < (1 << (8 * s)):
                    raise AsmError('displacement out of range: ' + o.text)
            self.cur.put((vv & ((1 << (8 * s)) - 1)).to_bytes(s, 'little'))
            return
        if k == 'rel':
            v = self.value(o.expr)
            if o.force == 'G':
                # general addressing: use absolute (@#) mode
                self.cur.put(bytes([0xFF if o.deferred else 0x9F]))
                if o.deferred:
                    # @G^x  ->  longword relative deferred
                    end = self.location() + 4
                    d = 0 if v is UNDEF else v - end
                    self.cur.put((d & 0xFFFFFFFF).to_bytes(4, 'little'))
                else:
                    self.cur.put(((0 if v is UNDEF else v) &
                                  0xFFFFFFFF).to_bytes(4, 'little'))
                return
            site = self.next_site()
            here = self.location() + 1        # after the mode byte
            if o.force in ('B', 'W', 'L'):
                s = {'B': 1, 'W': 2, 'L': 4}[o.force]
            else:
                def fits(sz):
                    if v is UNDEF:
                        return sz == 4 if self.passno > 1 else sz == 2
                    d = v - (here + sz)
                    lim = 1 << (8 * sz - 1)
                    return -lim <= d < lim
                s = self.pick(site, [1, 2, 4], fits)
            mode = {1: 0xAF, 2: 0xCF, 4: 0xEF}[s] + (0x10 if o.deferred else 0)
            self.cur.put(bytes([mode]))
            d = 0 if v is UNDEF else v - (here + s)
            if self.final:
                lim = 1 << (8 * s - 1)
                if not -lim <= d < lim and s < 4:
                    raise AsmError('displacement out of range: ' + o.text)
            self.cur.put((d & ((1 << (8 * s)) - 1)).to_bytes(s, 'little'))
            return
        raise AsmError('bad operand ' + o.text)

    def literal(self, o, access, dtype, isfloat, dsize):
        if access not in 'r':
            raise AsmError('literal not allowed for %s operand: %s' %
                           ({'m': 'modify', 'w': 'write', 'a': 'address',
                             'v': 'field'}.get(access, access), o.text))
        site = self.next_site()
        if isfloat:
            x = self.float_value(o.expr)
            sl = short_float_literal(x)
            if o.force != 'I' and sl is not None:
                self.sizes[site] = 1
                self.cur.put(bytes([sl]))
                return
            if o.force == 'S':
                raise AsmError('not a short literal: ' + o.text)
            self.cur.put(bytes([0x8F]))
            self.cur.put(FLOAT_ENC[dtype](x))
            return
        v = self.value(o.expr)
        if o.force == 'S':
            short = True
        elif o.force == 'I':
            short = False
        else:
            def fits(sz):
                if sz == 1:
                    if v is UNDEF:
                        return self.passno == 1
                    return 0 <= v <= 63
                return True
            short = self.pick(site, [1, 2], fits) == 1
        vv = 0 if v is UNDEF else v
        if short:
            if self.final and not 0 <= vv <= 63:
                raise AsmError('short literal out of range: ' + o.text)
            self.cur.put(bytes([vv & 0x3F]))
        else:
            self.cur.put(bytes([0x8F]))
            self.cur.put((vv & ((1 << (8 * dsize)) - 1)).to_bytes(
                dsize, 'little'))

    # ---- output ------------------------------------------------------------

    def image(self):
        """Return (bytes from base, total size incl. trailing bss)."""
        out = bytearray()
        total = 0
        stored = 0
        for ps in sorted(self.psects.values(), key=lambda p: p.order):
            if ps.abs:
                continue
            b = self.prev_bases[ps.name] - self.base
            end = b + ps.size
            if end > len(out):
                out.extend(bytes(end - len(out)))
            out[b:b + len(ps.data)] = ps.data
            total = max(total, end)
            if ps.inited:
                stored = max(stored, b + ps.inited)
        return bytes(out[:stored]), total

    def global_symbols(self):
        return {k: v for k, v in self.prev.items() if k in self.globals}


def read_stb(path):
    syms = {}
    with open(path) as fh:
        for line in fh:
            m = re.match(r'^\s*([A-Za-z0-9_$.]+)\s*==\s*\^X([0-9A-Fa-f]+)',
                         line)
            if m:
                syms[m.group(1).upper()] = int(m.group(2), 16)
    return syms


EXE_MAGIC = b'MVMSEXE1'


def main(argv=None):
    ap = argparse.ArgumentParser(description='VAX MACRO-32 cross-assembler')
    ap.add_argument('sources', nargs='+')
    ap.add_argument('-o', '--output')
    ap.add_argument('-l', '--listing')
    ap.add_argument('--base', default='0x200')
    ap.add_argument('--format', choices=['exe', 'raw'], default='exe')
    ap.add_argument('--stb', action='append', default=[])
    ap.add_argument('--stb-out')
    ap.add_argument('--stack-pages', type=int, default=64)
    a = ap.parse_args(argv)
    imported = {}
    for s in a.stb:
        imported.update(read_stb(s))
    asm = Assembler(a.sources, base=int(a.base, 0), imported=imported)
    try:
        ok = asm.run()
    except AsmError as e:
        print('%%MACRO-F-FATAL, %s' % e, file=sys.stderr)
        return 2
    if a.listing:
        asm.write_listing(a.listing)
    if not ok:
        for e in asm.errors:
            print(e, file=sys.stderr)
        print('%%MACRO-E-ERRORS, %d error(s)' % len(asm.errors),
              file=sys.stderr)
        return 1
    data, total = asm.image()
    out = a.output or os.path.splitext(a.sources[-1])[0] + \
        ('.exe' if a.format == 'exe' else '.bin')
    with open(out, 'wb') as fh:
        if a.format == 'exe':
            transfer = asm.transfer if asm.transfer is not None else asm.base
            name = os.path.splitext(os.path.basename(out))[0].upper()
            hdr = bytearray(512)
            hdr[0:8] = EXE_MAGIC
            struct.pack_into('<IIIII', hdr, 8, asm.base, transfer & 0xFFFFFFFF,
                             len(data), total, a.stack_pages)
            hdr[32:64] = name.encode()[:32].ljust(32)
            hdr[64:80] = asm.ident.encode('latin-1')[:16].ljust(16)
            hdr[80:120] = asm.title.encode('latin-1')[:40].ljust(40)
            fh.write(hdr)
        fh.write(data)
    if a.stb_out:
        with open(a.stb_out, 'w') as fh:
            fh.write('; Symbol table exported from %s\n' %
                     ' '.join(os.path.basename(s) for s in a.sources))
            for k, v in sorted(asm.global_symbols().items()):
                fh.write('%s == ^X%08X\n' % (k, v & 0xFFFFFFFF))
    print('%%MACRO-S-NORMAL, %s: %d bytes, transfer %08X' %
          (os.path.basename(out), total,
           (asm.transfer or 0) & 0xFFFFFFFF))
    return 0


if __name__ == '__main__':
    sys.exit(main())
