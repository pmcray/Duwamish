"""Micro-assembler for the Duwamish Model 30 control store.

A microinstruction is horizontal: one line of source may name one register
transfer through the ALU, a memory cycle, the PC incrementer, one special
action and one sequencing order, all of which happen in a single micro-cycle.

    LABEL:  DST<-SRC op SRC, READ|WRITE, SETC, PC+1, SPECIAL, SEQUENCING

Stored form: two 27-trit half-words.

    half A (datapath)    a:3  b:3  alu:3  d:3  mem:1  setc:1  pcinc:1  lit:6
    half B (sequencing)  seq:3  sel:2  special:3  target:10

Order of events inside one micro-cycle:
    1. IFETCH (if present): note instruction address, tally, timer check
    2. ALU transfer, then C <- sign(result) if SETC
    3. PC <- PC + 1 if PC+1
    4. memory cycle: READ is MDR <- M[MAR]; WRITE is M[MAR] <- MDR
    5. any other special action
    6. sequencing: NEXT, GOTO L, CASE sel L (goes to L-1, L or L+1 as the
       selected trit is -1, 0, +1), CALL L, RET, DISP L (dispatch on the
       opcode in IR, remembering L as the continuation), ENDI (go to the
       continuation: normally FETCH).
"""

import os
import re

from . import ternary as t

CS_SIZE = 3 ** 7            # 2187 microwords
K_SIZE = 243                # constant (local) store
MAP_SIZE = 243              # one entry per opcode, -121..121

SRC = {"0": 0, "PC": 1, "IR": 2, "MAR": 3, "MDR": 4, "T": 5, "U": 6, "EA": 7,
       "CNT": 8, "R": 9, "X": 10, "SP": 11, "ADDR": 12, "LIT": 13, "KS": -1,
       "CV": -2, "OPC": -3, "IPC": -4}
DST = {"NUL": 0, "PC": 1, "IR": 2, "MAR": 3, "MDR": 4, "T": 5, "U": 6,
       "EA": 7, "CNT": 8, "R": 9, "SP": 11}
ALU = {"PASS": 0, "ADD": 1, "SUB": 2, "NEG": 3, "MIN": 4, "MAX": 5, "EQV": 6,
       "SHF": 7, "SHL": 8, "SHR": 9, "LST": 10, "CMP": 11, "DIV": 12,
       "MOD": 13, "XTR": -1, "TRIT": -2, "SEL": -3, "SGN": -4}
UNARY = {"NEG", "SHL", "SHR", "LST", "SEL", "SGN"}
BINARY = {"MIN", "MAX", "EQV", "SHF", "CMP", "DIV", "MOD", "XTR", "TRIT"}
SEQ = {"NEXT": 0, "GOTO": 1, "CASE": 2, "CALL": 3, "RET": 4, "DISP": 5,
       "ENDI": 6}
SEL = {"C": 0, "Z": 1, "M": 2, "P": 3}
SPECIAL = {"": 0, "IFETCH": 1, "TRAP": 2, "HALT": 3, "CHKSUP": 4, "IOIN": 5,
           "IOOUT": 6, "RTI": 7, "RCS": 8, "WCS": 9, "RKS": 10, "WKS": 11,
           "RMAP": 12, "WMAP": 13, "TAL": -1, "TCL": -2, "TIM": -3,
           "FPU": -4}

# Field positions (least significant trit of each field).
A_POS = {"a": 0, "b": 3, "alu": 6, "d": 9, "mem": 12, "setc": 13,
         "pcinc": 14, "lit": 15}
A_LEN = {"a": 3, "b": 3, "alu": 3, "d": 3, "mem": 1, "setc": 1, "pcinc": 1,
         "lit": 6}
B_POS = {"seq": 0, "sel": 3, "special": 5, "target": 8}
B_LEN = {"seq": 3, "sel": 2, "special": 3, "target": 10}

MICROCODE_FILE = os.path.join(os.path.dirname(__file__), "microcode",
                              "model30.dmc")


class MicroAsmError(Exception):
    pass


def encode_a(a=0, b=0, alu=0, d=0, mem=0, setc=0, pcinc=0, lit=0):
    f = dict(a=a, b=b, alu=alu, d=d, mem=mem, setc=setc, pcinc=pcinc, lit=lit)
    return sum(v * 3 ** A_POS[k] for k, v in f.items())


def encode_b(seq=0, sel=0, special=0, target=0):
    f = dict(seq=seq, sel=sel, special=special, target=target)
    return sum(v * 3 ** B_POS[k] for k, v in f.items())


def decode(half_a, half_b):
    """Return the microword as a tuple
    (a, b, alu, d, mem, setc, pcinc, lit, seq, sel, special, target)."""
    fa = tuple(t.field(half_a, A_POS[k], A_LEN[k]) for k in
               ("a", "b", "alu", "d", "mem", "setc", "pcinc", "lit"))
    fb = tuple(t.field(half_b, B_POS[k], B_LEN[k]) for k in
               ("seq", "sel", "special", "target"))
    return fa + fb


_TOK = re.compile(r"#-?\d+|K\[\d+\]|[A-Z_][A-Z0-9_]*|\d+|[+-]")


class Microprogram:
    """An assembled control store image."""

    def __init__(self, cs, labels, dispatch, source_lines):
        self.cs = cs                      # list of (half_a, half_b)
        self.labels = labels              # name -> micro-address
        self.dispatch = dispatch          # list, index op+121 -> micro-address
        self.source_lines = source_lines  # micro-address -> source text
        self.free = len(cs)               # first unused micro-address

    def listing(self):
        rev = {}
        for k, v in self.labels.items():
            rev.setdefault(v, []).append(k)
        out = []
        for i, (ha, hb) in enumerate(self.cs):
            lab = ",".join(rev.get(i, []))
            out.append(f"{i:5}  {t.to_hept(ha)} {t.to_hept(hb)}  "
                       f"{lab + ':' if lab else '':10} {self.source_lines[i]}")
        return "\n".join(out)


def _parse_transfer(dst, rhs, lineno):
    """Returns dict of half-A fields and the literal (or None)."""
    toks = _TOK.findall(rhs.upper())
    lit = None

    def src(tok):
        nonlocal lit
        if tok.startswith("#"):
            lit = int(tok[1:])
            return SRC["LIT"]
        if tok.startswith("K["):
            lit = int(tok[2:-1])
            return SRC["KS"]
        if tok not in SRC:
            raise MicroAsmError(f"line {lineno}: unknown source {tok!r}")
        return SRC[tok]

    if dst not in DST:
        raise MicroAsmError(f"line {lineno}: unknown destination {dst!r}")
    f = {"d": DST[dst]}
    if len(toks) == 1:
        f.update(a=src(toks[0]), alu=ALU["PASS"])
    elif len(toks) == 2 and toks[0] in UNARY:
        f.update(a=src(toks[1]), alu=ALU[toks[0]])
    elif len(toks) == 3 and toks[1] in ("+", "-"):
        f.update(a=src(toks[0]), b=src(toks[2]),
                 alu=ALU["ADD" if toks[1] == "+" else "SUB"])
    elif len(toks) == 3 and toks[1] in BINARY:
        f.update(a=src(toks[0]), b=src(toks[2]), alu=ALU[toks[1]])
    else:
        raise MicroAsmError(f"line {lineno}: cannot parse transfer {rhs!r}")
    return f, lit


def assemble(text, opcode_names=None):
    """Assemble microcode source text into a Microprogram."""
    from . import isa
    if opcode_names is None:
        opcode_names = isa.BY_NAME
    # pass 1: labels
    lines = []
    labels = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        code = raw.split(";", 1)[0].rstrip()
        if not code.strip():
            continue
        m = re.match(r"\s*([A-Z_][A-Z0-9_]*):(.*)", code)
        label = None
        if m:
            label, code = m.group(1), m.group(2)
            if label in labels:
                raise MicroAsmError(f"line {lineno}: duplicate label {label}")
            labels[label] = len(lines)
        if not code.strip():
            raise MicroAsmError(f"line {lineno}: label without instruction")
        lines.append((lineno, code.strip(), raw.strip()))
    if len(lines) > CS_SIZE:
        raise MicroAsmError("control store overflow")

    # pass 2: encode
    cs = []
    src_lines = []
    for lineno, code, raw in lines:
        fa = {}
        fb = {}
        lit = None
        for order in [o.strip() for o in code.split(",")]:
            u = order.upper()
            words = u.split()
            if "<-" in u:
                dst, rhs = u.split("<-", 1)
                f, l2 = _parse_transfer(dst.strip(), rhs, lineno)
                fa.update(f)
                if l2 is not None:
                    if lit is not None and lit != l2:
                        raise MicroAsmError(f"line {lineno}: two literals")
                    lit = l2
            elif u == "READ":
                fa["mem"] = -1
            elif u == "WRITE":
                fa["mem"] = 1
            elif u == "SETC":
                fa["setc"] = 1
            elif u == "PC+1":
                fa["pcinc"] = 1
            elif words[0] in SEQ:
                fb["seq"] = SEQ[words[0]]
                if words[0] == "CASE":
                    fb["sel"] = SEL[words[1]]
                    tgt = words[2]
                elif words[0] in ("GOTO", "CALL", "DISP"):
                    tgt = words[1]
                else:
                    tgt = None
                if tgt is not None:
                    if tgt not in labels:
                        raise MicroAsmError(
                            f"line {lineno}: undefined label {tgt}")
                    fb["target"] = labels[tgt]
            elif words[0] in SPECIAL:
                fb["special"] = SPECIAL[words[0]]
                if words[0] == "TRAP":
                    l2 = int(words[1])
                    if lit is not None and lit != l2:
                        raise MicroAsmError(f"line {lineno}: two literals")
                    lit = l2
            else:
                raise MicroAsmError(f"line {lineno}: unknown order {order!r}")
        if lit is not None:
            fa["lit"] = lit
        cs.append((encode_a(**fa), encode_b(**fb)))
        src_lines.append(code)

    ill = labels.get("ILLOP")
    if ill is None:
        raise MicroAsmError("microprogram must define ILLOP")
    dispatch = [ill] * MAP_SIZE
    for name, (op, _form) in opcode_names.items():
        if name in labels:
            dispatch[op + 121] = labels[name]
    return Microprogram(cs, labels, dispatch, src_lines)


_default = None


def default_microprogram():
    global _default
    if _default is None:
        with open(MICROCODE_FILE) as f:
            _default = assemble(f.read())
    return _default


def microkit_source(mp=None):
    """A SALISH include file describing the microword format, so that
    programs running on the machine can write microcode for themselves."""
    mp = mp or default_microprogram()
    lines = ["-- microkit: generated from the Model 30 micro-assembler.",
             "-- Field positions and codes for writing control-store words."]

    def c(name, val):
        lines.append(f"const {name} = {val}")
    c("UC_FETCH", mp.labels["FETCH"])
    c("UC_FREE", mp.free)
    c("UC_SIZE", CS_SIZE)
    c("UK_SIZE", K_SIZE)
    for k, v in A_POS.items():
        c(f"UA_{k.upper()}_POS", v)
    for k, v in B_POS.items():
        c(f"UB_{k.upper()}_POS", v)
    for k, v in SRC.items():
        c(f"US_{'ZERO' if k == '0' else k}", v)
    for k, v in DST.items():
        c(f"UD_{k}", v)
    for k, v in ALU.items():
        c(f"UALU_{k}", v)
    for k, v in SEQ.items():
        c(f"USEQ_{k}", v)
    return "\n".join(lines) + "\n"
