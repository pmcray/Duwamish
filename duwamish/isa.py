"""The Duwamish instruction set: formats, opcodes, encoding, disassembly.

Instruction word (27 trits, most significant on the left):

    | op : 5 | r : 2 | x : 2 | m : 2 | addr : 16 |

  op    balanced opcode, -121..+121.  Factory opcodes are all positive;
        the negative half of opcode space is left empty on purpose, for
        instructions the machine invents for itself (see WCS, docs/ARCHITECTURE).
  r     register operand, -4..+4 naming R0..R8 (value mod 9).
  x     index register, likewise.  R0 always reads as zero.
  m     addressing mode: -1 indirect, 0 direct, +1 immediate.
  addr  16-trit signed address or immediate (+/- 21,523,360).

Effective address EA = addr + X.  The operand is EA itself (immediate),
M[EA] (direct) or M[M[EA]] (indirect).
"""

from . import ternary as t

OP_POS, R_POS, X_POS, M_POS = 22, 20, 18, 16
ADDR_TRITS = 16
ADDR_MAX = (3 ** ADDR_TRITS - 1) // 2

NREGS = 9
FP, SP = 7, 8

MODE_IND, MODE_DIR, MODE_IMM = -1, 0, 1

# Instruction forms, used by the assembler and disassembler:
#   RE  register, operand          LD R1, X
#   E   operand only               JMP LOOP
#   R   register only              PUSH R1
#   RA  register, address (EA only, never a memory operand)
#   I   small immediate            SVC 1  /  RET 2
#   N   no operands                HLT
OPCODES = [
    # op  mnemonic form  description
    (1, "LD", "RE", "R <- operand; C <- sign"),
    (2, "ST", "RE", "M[EA] <- R"),
    (3, "LEA", "RE", "R <- EA"),
    (4, "ADD", "RE", "R <- R + operand; C <- sign"),
    (5, "SUB", "RE", "R <- R - operand; C <- sign"),
    (6, "MUL", "RE", "R <- R * operand (microcoded trit loop); C <- sign"),
    (7, "DIV", "RE", "R <- R / operand, truncated; C <- sign"),
    (8, "MOD", "RE", "R <- R rem operand; C <- sign"),
    (9, "NEG", "RE", "R <- -operand; C <- sign"),
    (10, "CMP", "RE", "C <- sign(R - operand)"),
    (11, "TST", "E", "C <- sign(operand)"),
    (12, "AND", "RE", "R <- tritwise min (Kleene and); C <- sign"),
    (13, "OR", "RE", "R <- tritwise max (Kleene or); C <- sign"),
    (14, "EQV", "RE", "R <- tritwise product (Kleene equivalence); C <- sign"),
    (15, "SHF", "RE", "R <- R * 3^operand (negative: shift right, rounding)"),
    (16, "XTR", "RE", "R <- trits [p, p+n) of R, operand = 27n + p"),
    (17, "TRT", "RE", "C <- trit of R at position operand"),
    (18, "SEL", "RE", "R <- trit (C+1) of operand: a 3-entry truth table"),
    (19, "NOP", "N", "no operation"),
    (20, "JMP", "E", "PC <- EA"),
    (21, "JN", "E", "if C = -1: PC <- EA"),
    (22, "JZ", "E", "if C = 0: PC <- EA"),
    (23, "JP", "E", "if C = +1: PC <- EA"),
    (24, "JNN", "E", "if C != -1: PC <- EA"),
    (25, "JNZ", "E", "if C != 0: PC <- EA"),
    (26, "JNP", "E", "if C != +1: PC <- EA"),
    (27, "J3", "E", "PC <- EA + C   (three-way jump)"),
    (28, "CALL", "E", "push PC; PC <- EA"),
    (29, "RET", "I", "pop PC; SP <- SP + addr (discard arguments)"),
    (30, "PUSH", "R", "SP <- SP - 1; M[SP] <- R"),
    (31, "POP", "R", "R <- M[SP]; SP <- SP + 1; C <- sign"),
    (32, "JSR", "RE", "R <- PC; PC <- EA"),
    (33, "SVC", "I", "supervisor call (trap 6)"),
    (34, "RTI", "N", "return from trap (privileged)"),
    (35, "IN", "RE", "R <- input from device operand (privileged); C <- sign"),
    (36, "OUT", "RE", "output R to device operand (privileged)"),
    (37, "HLT", "N", "halt the machine (privileged)"),
    (38, "TIM", "R", "R <- machine clock, in micro-cycles"),
    (39, "TAL", "RA", "R <- tally (execution count) of the word at EA"),
    (40, "TCL", "N", "clear all tallies"),
    (41, "RCS", "RA", "R <- control-store half-word EA"),
    (42, "WCS", "RA", "control-store half-word EA <- R"),
    (43, "RKS", "RA", "R <- constant store K[EA]"),
    (44, "WKS", "RA", "constant store K[EA] <- R"),
    (45, "RMAP", "RA", "R <- dispatch map entry for opcode EA"),
    (46, "WMAP", "RA", "dispatch map entry for opcode EA <- R"),
    # the floating-point feature (standard on the Model 90): see fpu.py
    (47, "FAD", "RE", "R <- R + operand, floating; C <- sign"),
    (48, "FSB", "RE", "R <- R - operand, floating; C <- sign"),
    (49, "FMP", "RE", "R <- R * operand, floating; C <- sign"),
    (50, "FDV", "RE", "R <- R / operand, floating; C <- sign"),
    (51, "FLT", "RE", "R <- the integer operand as a float; C <- sign"),
    (52, "FIX", "RE", "R <- the float operand rounded to an integer; C <- sign"),
    (53, "FCM", "RE", "C <- sign(R - operand), floating"),
]

BY_NAME = {name: (op, form) for op, name, form, _ in OPCODES}
BY_OP = {op: (name, form) for op, name, form, _ in OPCODES}
DESCRIPTION = {name: d for _, name, _, d in OPCODES}

# Jumps and other instructions that end a basic block.
BLOCK_ENDERS = {BY_NAME[n][0] for n in (
    "JMP", "JN", "JZ", "JP", "JNN", "JNZ", "JNP", "J3", "CALL", "RET",
    "JSR", "SVC", "RTI", "HLT")}

# Trap codes
TRAP_ILLEGAL = 1
TRAP_PROTECT = 2
TRAP_DIVZERO = 3
TRAP_ADDRESS = 4
TRAP_PRIV = 5
TRAP_SVC = 6
TRAP_WCS = 8
TRAP_TIME = 10
TRAP_FPU = 11
TRAP_NAMES = {
    TRAP_ILLEGAL: "ILLEGAL INSTRUCTION",
    TRAP_PROTECT: "PROTECTION VIOLATION",
    TRAP_DIVZERO: "DIVISION BY ZERO",
    TRAP_ADDRESS: "ADDRESS OUT OF CORE",
    TRAP_PRIV: "PRIVILEGED INSTRUCTION",
    TRAP_SVC: "SUPERVISOR CALL",
    TRAP_WCS: "CONTROL STORE LOCKED",
    TRAP_TIME: "TIME LIMIT EXCEEDED",
    TRAP_FPU: "FLOATING-POINT FEATURE NOT INSTALLED",
}

# Fixed low-core locations (negative, hence protected) used by the trap logic.
LOC_TRAP_PC = -1      # PC to resume at
LOC_TRAP_CODE = -2
LOC_TRAP_MODE = -3    # mode before the trap: +1 supervisor, -1 user
LOC_TRAP_C = -4       # condition trit before the trap
LOC_TRAP_VEC = -5     # address of the trap handler
LOC_TRAP_ARG = -6     # SVC operand, faulting address, ...
LOC_TRAP_IPC = -7     # address of the instruction that trapped

# Devices
DEV_TTY = 1       # operator's console typewriter (out)
DEV_READER = 2    # card reader (in): characters, 10 at end of card, -1 at end
DEV_PRINTER = 3   # line printer (out)
DEV_TIMER = 4     # interval timer (out): trap when clock passes this value
DEV_SATELLITE = 5 # channel to the satellite job-control computer (in)
DEV_CONFIG = 6    # configuration switches (in): +1 if the FPU is fitted
DEV_PUNCH = 7     # card punch (out): characters, 10 ends a card
DEV_CHANNEL = 8   # data channel to tape, drum and disc: OUT six words, IN status
FP_OPS = range(47, 54)


def reg_field(idx):
    """Register index 0..8 -> 2-trit field value -4..4."""
    return idx if idx <= 4 else idx - 9


def encode(op, r=0, x=0, m=0, addr=0):
    if not -ADDR_MAX <= addr <= ADDR_MAX:
        raise ValueError(f"address/immediate {addr} does not fit in 16 trits")
    return (op * 3 ** OP_POS + reg_field(r) * 3 ** R_POS
            + reg_field(x) * 3 ** X_POS + m * 3 ** M_POS + addr)


_decode_cache = {}


def decode(w):
    """Word -> (op, r, x, m, addr) with r and x as register indices 0..8."""
    d = _decode_cache.get(w)
    if d is None:
        addr = t.wrap(w, ADDR_TRITS)
        v = (w - addr) // 3 ** M_POS
        m = t.wrap(v, 2)
        v = (v - m) // 9
        x = t.wrap(v, 2)
        v = (v - x) // 9
        r = t.wrap(v, 2)
        op = (v - r) // 9
        d = (op, r % 9, x % 9, m, addr)
        if len(_decode_cache) < 200000:
            _decode_cache[w] = d
    return d


def reg_name(i):
    return {7: "FP", 8: "SP"}.get(i, f"R{i}")


def disassemble(w, symbols=None):
    """Render one word as an instruction (best effort)."""
    op, r, x, m, addr = decode(w)
    if op not in BY_OP:
        if op < 0:
            return f"OP{op}"          # a machine-invented instruction
        return f"DATA {w}"
    name, form = BY_OP[op]
    a = str(addr)
    if symbols and addr in symbols and m != MODE_IMM:
        a = symbols[addr]
    xs = f"({reg_name(x)})" if x else ""
    prefix = {MODE_IMM: "#", MODE_IND: "@", MODE_DIR: ""}.get(m, f"?{m}?")
    operand = f"{prefix}{a}{xs}"
    if form == "RE":
        return f"{name:5}{reg_name(r)}, {operand}"
    if form == "RA":
        return f"{name:5}{reg_name(r)}, {a}{xs}"
    if form == "E":
        return f"{name:5}{operand}"
    if form == "R":
        return f"{name:5}{reg_name(r)}"
    if form == "I":
        return f"{name:5}{addr}" if addr else name
    return name
