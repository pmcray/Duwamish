"""The Duwamish central processor, core memory and peripherals.

Two implementations of one architecture, as IBM did with System/360:

  Model 30  microprogrammed.  Every instruction is interpreted by the
            microprogram in the (writable) control store, one micro-cycle
            at a time.  Timing is exact: 1 cycle per microinstruction plus
            MEM_WAIT cycles for each core-memory reference.

  Model 90  hardwired (Cray's design).  Executes factory instructions
            directly; any opcode whose microcode has been rewritten or
            invented falls back to the micro-engine, so the two models
            always compute the same results.  Timing is nominal: one
            instruction per core cycle.

Core: 3^12 = 531,441 words, addressed -265,720 .. +265,720.  The negative
half belongs to the Executive and is protected from user-mode programs.
"""

from . import isa
from . import microasm
from . import ternary as t
from .isa import decode

MEM_TRITS = 12
MEM_SIZE = 3 ** MEM_TRITS
MEM_MAX = (MEM_SIZE - 1) // 2
MEM_OFF = MEM_MAX

MEM_WAIT = 4           # extra micro-cycles per core reference
FAST_CYCLES = 5        # nominal Model 90 cycles per instruction

SUPERVISOR, USER = 1, -1

# micro-register indices in Machine.ur
PC, IR, MAR, MDR, T, U, EA, CNT = 1, 2, 3, 4, 5, 6, 7, 8

WMAX = t.WMAX
RADIX = t.RADIX


def _wrap(v):
    if -WMAX <= v <= WMAX:
        return v
    return (v + WMAX) % RADIX - WMAX


def _sign(v):
    return (v > 0) - (v < 0)


def alu_xtr(a, spec):
    pos, n = spec % 27, spec // 27
    if n <= 0:
        return 0
    return t.field(a, pos, min(n, 27 - pos) if pos + n > 27 else n)


def alu_trit(a, pos):
    return t.trit_at(a, pos) if 0 <= pos < 27 else 0


# operand-fetch flags per opcode (index op + 121 is not needed: only the
# factory opcodes 1..40 run on the hardwired path)
_NEEDS_EA = [False] * 243
_NEEDS_VAL = [False] * 243
for _op, _name, _form, _ in isa.OPCODES:
    if _form in ("RE", "E") or _name in ("SVC",):
        _NEEDS_EA[_op] = True
        _NEEDS_VAL[_op] = _name not in ("ST", "LEA", "JMP", "JN", "JZ", "JP",
                                        "JNN", "JNZ", "JNP", "J3", "CALL",
                                        "JSR")
_ZERO_TALLY = [0] * MEM_SIZE


class Trap(Exception):
    def __init__(self, code, arg=0):
        super().__init__(code, arg)
        self.code = code
        self.arg = arg


class MachineCheck(Exception):
    """A trap taken in supervisor mode: the Executive itself has failed."""


class Machine:
    def __init__(self, model=30, microprogram=None, wcs_enabled=False,
                 satellite=None):
        if model not in (30, 90):
            raise ValueError("model must be 30 or 90")
        self.model = model
        self.mp = microprogram or microasm.default_microprogram()
        self.mem = [0] * MEM_SIZE
        self.rf = [0] * isa.NREGS
        self.ur = [0] * 9
        self.ir_f = (0, 0, 0, 0, 0)
        self.c = 0
        self.zres = 0
        self.mode = SUPERVISOR
        self.ipc = 0
        self.clock = 0
        self.icount = 0
        self.timer = 0
        self.tally = [0] * MEM_SIZE
        self.cs = [list(p) for p in self.mp.cs]
        self.cs += [[0, 0] for _ in range(microasm.CS_SIZE - len(self.cs))]
        self.ucode = [microasm.decode(a, b) for a, b in self.cs]
        self.factory_size = self.mp.free
        self.factory_dirty = False
        self.kstore = [0] * microasm.K_SIZE
        self.map = list(self.mp.dispatch)
        self.fetch_addr = self.mp.labels["FETCH"]
        self.upc = self.fetch_addr
        self.unx = self.fetch_addr
        self.ustack = []
        self.wcs_enabled = wcs_enabled
        self.halted = False
        self.check = None
        # peripherals
        self.tty = []
        self.printer = []
        self.reader = []
        self.reader_pos = 0
        self.satellite = satellite
        self.trace = None
        self._native = [False] * 243
        self._refresh_native()

    # ------------------------------------------------------------------
    # core memory
    # ------------------------------------------------------------------
    def load(self, a):
        if a < 0 and self.mode < 0:
            raise Trap(isa.TRAP_PROTECT, a)
        i = a + MEM_OFF
        if not 0 <= i < MEM_SIZE:
            raise Trap(isa.TRAP_ADDRESS, a)
        return self.mem[i]

    def store(self, a, v):
        if a < 0 and self.mode < 0:
            raise Trap(isa.TRAP_PROTECT, a)
        i = a + MEM_OFF
        if not 0 <= i < MEM_SIZE:
            raise Trap(isa.TRAP_ADDRESS, a)
        self.mem[i] = v

    def peek(self, a):
        return self.mem[a + MEM_OFF]

    def poke(self, a, v):
        self.mem[a + MEM_OFF] = t.wrap(v)

    def load_image(self, image):
        """image: dict or iterable of (address, word)."""
        items = image.items() if isinstance(image, dict) else image
        for a, w in items:
            self.poke(a, w)

    # ------------------------------------------------------------------
    # the Beer monitor: execution tallies
    # ------------------------------------------------------------------
    def tally_get(self, a):
        return self.tally[a + MEM_OFF] if -MEM_MAX <= a <= MEM_MAX else 0

    def tally_clear(self):
        self.tally[:] = _ZERO_TALLY

    def tally_items(self):
        """(address, count) for every word executed at least once."""
        tl = self.tally
        return [(i - MEM_OFF, c) for i, c in enumerate(tl) if c]

    # ------------------------------------------------------------------
    # peripherals
    # ------------------------------------------------------------------
    def io_in(self, dev):
        if dev == isa.DEV_READER:
            if self.reader_pos < len(self.reader):
                v = self.reader[self.reader_pos]
                self.reader_pos += 1
                return v
            return -1
        if dev == isa.DEV_SATELLITE and self.satellite:
            return self.satellite.channel_in(self)
        return -1

    def io_out(self, dev, v):
        if dev == isa.DEV_TTY:
            self.tty.append(v)
        elif dev == isa.DEV_PRINTER:
            self.printer.append(v)
        elif dev == isa.DEV_TIMER:
            self.timer = v
        elif dev == isa.DEV_SATELLITE and self.satellite:
            self.satellite.channel_out(self, v)

    @staticmethod
    def text(codes):
        return "".join(chr(c) if 0 <= c < 0x110000 else "?" for c in codes)

    # ------------------------------------------------------------------
    # traps
    # ------------------------------------------------------------------
    def take_trap(self, code, arg):
        if self.mode == SUPERVISOR:
            self.halted = True
            self.check = (code, arg, self.ipc)
            raise MachineCheck(
                f"machine check: trap {code} ({isa.TRAP_NAMES.get(code, '?')})"
                f" in supervisor mode at {self.ipc}, arg {arg}")
        prev_mode = self.mode
        self.mode = SUPERVISOR
        self.store(isa.LOC_TRAP_PC, self.ur[PC])
        self.store(isa.LOC_TRAP_CODE, code)
        self.store(isa.LOC_TRAP_MODE, prev_mode)
        self.store(isa.LOC_TRAP_C, self.c)
        self.store(isa.LOC_TRAP_ARG, t.wrap(arg))
        self.store(isa.LOC_TRAP_IPC, self.ipc)
        self.ur[PC] = self.load(isa.LOC_TRAP_VEC)
        self.upc = self.unx = self.fetch_addr
        self.ustack.clear()

    def return_from_trap(self):
        self.ur[PC] = self.load(isa.LOC_TRAP_PC)
        self.c = _sign(self.load(isa.LOC_TRAP_C))
        self.mode = USER if self.load(isa.LOC_TRAP_MODE) < 0 else SUPERVISOR

    # ------------------------------------------------------------------
    # the writable control store
    # ------------------------------------------------------------------
    def _refresh_native(self):
        fm = self.mp.dispatch
        ok = not self.factory_dirty
        for i in range(243):
            op = i - 121
            self._native[i] = (ok and op in isa.BY_OP and op < 41
                               and self.map[i] == fm[i])

    def cs_read(self, ea):
        if not 0 <= ea < 2 * microasm.CS_SIZE:
            raise Trap(isa.TRAP_ADDRESS, ea)
        return self.cs[ea // 2][ea % 2]

    def cs_write(self, ea, v):
        if not self.wcs_enabled:
            raise Trap(isa.TRAP_WCS, ea)
        if not 0 <= ea < 2 * microasm.CS_SIZE:
            raise Trap(isa.TRAP_ADDRESS, ea)
        w = ea // 2
        self.cs[w][ea % 2] = v
        self.ucode[w] = microasm.decode(*self.cs[w])
        if w < self.factory_size and not self.factory_dirty:
            self.factory_dirty = True
            self._refresh_native()

    def ks_check(self, ea):
        if not 0 <= ea < microasm.K_SIZE:
            raise Trap(isa.TRAP_ADDRESS, ea)

    def map_read(self, op):
        if not -121 <= op <= 121:
            raise Trap(isa.TRAP_ADDRESS, op)
        return self.map[op + 121]

    def map_write(self, op, v):
        if not self.wcs_enabled:
            raise Trap(isa.TRAP_WCS, op)
        if not -121 <= op <= 121 or not 0 <= v < microasm.CS_SIZE:
            raise Trap(isa.TRAP_ADDRESS, op)
        self.map[op + 121] = v
        self._refresh_native()

    # ------------------------------------------------------------------
    # Model 30: the micro-engine
    # ------------------------------------------------------------------
    def _src(self, code, lit):
        if 1 <= code <= 8:
            return self.ur[code]
        if code == 0:
            return 0
        if code == 9:
            return self.rf[self.ir_f[1]]
        if code == 10:
            return self.rf[self.ir_f[2]]
        if code == 11:
            return self.rf[8]
        if code == 12:
            return self.ir_f[4]
        if code == 13:
            return lit
        if code == -1:
            if not 0 <= lit < microasm.K_SIZE:
                raise Trap(isa.TRAP_ADDRESS, lit)
            return self.kstore[lit]
        if code == -2:
            return self.c
        if code == -3:
            return self.ir_f[0]
        if code == -4:
            return self.ipc
        raise Trap(isa.TRAP_ILLEGAL, code)

    def _alu(self, op, a, b):
        if op == 0:
            return a
        if op == 1:
            return _wrap(a + b)
        if op == 2:
            return _wrap(a - b)
        if op == 3:
            return -a
        if op == 8:
            return _wrap(a * 3)
        if op == 9:
            return (a + 1) // 3
        if op == 10:
            r = a % 3
            return -1 if r == 2 else r
        if op == 11:
            return _sign(a - b)
        if op == 4:
            return t.tmin(a, b)
        if op == 5:
            return t.tmax(a, b)
        if op == 6:
            return t.teqv(a, b)
        if op == 7:
            return t.shift(a, b)
        if op == 12 or op == 13:
            if b == 0:
                raise Trap(isa.TRAP_DIVZERO, 0)
            return t.trunc_div(a, b) if op == 12 else t.trunc_mod(a, b)
        if op == -1:
            return alu_xtr(a, b)
        if op == -2:
            return alu_trit(a, b)
        if op == -3:
            return t.trit_at(a, self.c + 1)
        if op == -4:
            return _sign(a)
        raise Trap(isa.TRAP_ILLEGAL, op)

    def _dst(self, code, v):
        if 1 <= code <= 8:
            self.ur[code] = v
            if code == IR:
                self.ir_f = decode(v)
        elif code == 9:
            r = self.ir_f[1]
            if r:
                self.rf[r] = v
        elif code == 11:
            self.rf[8] = v
        else:
            raise Trap(isa.TRAP_ILLEGAL, code)

    def _special(self, sp, lit):
        ur = self.ur
        r = self.ir_f[1]
        if sp == 2:                               # TRAP n
            raise Trap(lit, ur[MDR])
        if sp == 4:                               # CHKSUP
            if self.mode < 0:
                raise Trap(isa.TRAP_PRIV, self.ir_f[0])
            return
        val = None
        ea = ur[EA]
        if sp == 5:                               # IOIN
            val = t.wrap(self.io_in(ur[MDR]))
            self.c = _sign(val)
        elif sp == 6:                             # IOOUT
            self.io_out(ur[MDR], self.rf[r])
        elif sp == 3:                             # HALT
            self.halted = True
        elif sp == 7:                             # RTI
            self.return_from_trap()
        elif sp == 8:
            val = self.cs_read(ea)
        elif sp == 9:
            self.cs_write(ea, self.rf[r])
        elif sp == 10:
            self.ks_check(ea)
            val = self.kstore[ea]
        elif sp == 11:
            if not self.wcs_enabled:
                raise Trap(isa.TRAP_WCS, ea)
            self.ks_check(ea)
            self.kstore[ea] = self.rf[r]
        elif sp == 12:
            val = self.map_read(ea)
        elif sp == 13:
            self.map_write(ea, self.rf[r])
        elif sp == -1:
            val = self.tally_get(ea)
        elif sp == -2:
            self.tally_clear()
        elif sp == -3:
            val = t.wrap(self.clock)
        else:
            raise Trap(isa.TRAP_ILLEGAL, sp)
        if val is not None and r:
            self.rf[r] = val

    def ustep(self):
        """Execute one microinstruction."""
        (a, b, alu, d, mem, setc, pcinc, lit,
         seq, sel, special, target) = self.ucode[self.upc]
        self.clock += 1
        ur = self.ur
        if special == 1:                          # IFETCH
            pc = ur[PC]
            self.ipc = pc
            if (self.mode < 0 and self.timer
                    and self.clock >= self.timer):
                raise Trap(isa.TRAP_TIME, 0)
            if -MEM_MAX <= pc <= MEM_MAX:
                self.tally[pc + MEM_OFF] += 1
            self.icount += 1
            if self.trace:
                self.trace(self, pc)
        if d or setc:
            va = self._src(a, lit)
            vb = self._src(b, lit) if b else 0
            res = self._alu(alu, va, vb)
            self.zres = (res > 0) - (res < 0)
            if setc:
                self.c = self.zres
            if d:
                self._dst(d, res)
        if pcinc:
            ur[PC] = _wrap(ur[PC] + 1)
        if mem:
            self.clock += MEM_WAIT
            if mem < 0:
                ur[MDR] = self.load(ur[MAR])
            else:
                self.store(ur[MAR], ur[MDR])
        if special > 1 or special < 0:
            self._special(special, lit)
        if seq == 0:
            self.upc += 1
        elif seq == 6:
            self.upc = self.unx
        elif seq == 3:
            self.ustack.append(self.upc + 1)
            self.upc = target
        elif seq == 4:
            self.upc = self.ustack.pop()
        elif seq == 2:
            if sel == 0:
                v = self.c
            elif sel == 2:
                v = self.ir_f[3]
                if not -1 <= v <= 1:
                    raise Trap(isa.TRAP_ILLEGAL, v)
            elif sel == 1:
                v = self.zres
            else:
                v = self.mode
            self.upc = target + v
        elif seq == 1:
            self.upc = target
        elif seq == 5:
            self.unx = target
            self.upc = self.map[self.ir_f[0] + 121]
        else:
            raise Trap(isa.TRAP_ILLEGAL, seq)

    def _run_micro(self, max_cycles):
        stop = self.clock + max_cycles
        while not self.halted and self.clock < stop:
            try:
                self.ustep()
            except Trap as tr:
                self.take_trap(tr.code, tr.arg)

    def _micro_instruction(self):
        """Model 90 helper: run the micro-engine from the dispatch point of
        the instruction now in IR until control returns to FETCH."""
        self.unx = self.fetch_addr
        self.upc = self.map[self.ir_f[0] + 121]
        self.ustack.clear()
        fetch = self.fetch_addr
        guard = self.clock + 10_000_000
        while self.upc != fetch and not self.halted:
            self.ustep()
            if self.clock > guard:
                raise MachineCheck("microprogram runaway")

    # ------------------------------------------------------------------
    # Model 90: the hardwired engine
    # ------------------------------------------------------------------
    def _run_fast(self, max_instr):
        """Execute up to max_instr instructions directly.  The trap-free
        path is kept flat and local for speed; anything unusual raises
        Trap, which is handled exactly as the micro-engine handles it."""
        rf = self.rf
        ur = self.ur
        mem = self.mem
        native = self._native
        tally = self.tally
        load = self.load
        store = self.store
        needs_ea = _NEEDS_EA
        needs_val = _NEEDS_VAL
        off = MEM_OFF
        size = MEM_SIZE
        dcache = isa._decode_cache
        n = 0
        while n < max_instr and not self.halted:
            n += 1
            pc = ur[PC]
            try:
                self.ipc = pc
                if self.timer and self.mode < 0 and self.clock >= self.timer:
                    raise Trap(isa.TRAP_TIME, 0)
                i = pc + off
                if 0 <= i < size:
                    tally[i] += 1
                self.icount += 1
                if self.trace:
                    self.trace(self, pc)
                ur[PC] = pc + 1 if pc < WMAX else _wrap(pc + 1)
                if pc < 0 and self.mode < 0:
                    raise Trap(isa.TRAP_PROTECT, pc)
                if not 0 <= i < size:
                    raise Trap(isa.TRAP_ADDRESS, pc)
                w = mem[i]
                pc = ur[PC]
                f = dcache.get(w)
                if f is None:
                    f = decode(w)
                op, r, x, m, addr = f
                if not native[op + 121]:
                    ur[IR] = ur[MDR] = w
                    ur[MAR] = self.ipc
                    self.ir_f = f
                    self._micro_instruction()
                    continue
                self.clock += FAST_CYCLES
                # ---- effective address / operand ----
                if needs_ea[op]:
                    ea = addr + rf[x] if x else addr
                    if ea > WMAX or ea < -WMAX:
                        ea = _wrap(ea)
                    if m == 0:
                        if needs_val[op]:
                            j = ea + off
                            if ea >= 0 and j < size:
                                v = mem[j]
                            else:
                                v = load(ea)
                    elif m == 1:
                        if not needs_val[op]:
                            raise Trap(isa.TRAP_ILLEGAL, w)
                        v = ea
                    elif m == -1:
                        ea = load(ea)
                        if needs_val[op]:
                            v = load(ea)
                    else:
                        raise Trap(isa.TRAP_ILLEGAL, m)
                # ---- execute ----
                if op == 1:                                   # LD
                    if r:
                        rf[r] = v
                    self.c = (v > 0) - (v < 0)
                elif op == 2:                                 # ST
                    j = ea + off
                    if ea >= 0 and j < size:
                        mem[j] = rf[r]
                    else:
                        store(ea, rf[r])
                elif op == 4:                                 # ADD
                    v = rf[r] + v
                    if v > WMAX or v < -WMAX:
                        v = _wrap(v)
                    if r:
                        rf[r] = v
                    self.c = (v > 0) - (v < 0)
                elif op == 10:                                # CMP
                    d = rf[r] - v
                    self.c = (d > 0) - (d < 0)
                elif 20 <= op <= 27:                          # jumps
                    c = self.c
                    if (op == 20 or (op == 21 and c < 0)
                            or (op == 22 and c == 0) or (op == 23 and c > 0)
                            or (op == 24 and c >= 0) or (op == 25 and c != 0)
                            or (op == 26 and c <= 0)):
                        ur[PC] = ea
                    elif op == 27:
                        ur[PC] = _wrap(ea + c)
                elif op == 30:                                # PUSH
                    sp = rf[8] - 1
                    rf[8] = sp
                    j = sp + off
                    if sp >= 0 and j < size:
                        mem[j] = rf[r]
                    else:
                        rf[8] = sp = _wrap(sp)
                        store(sp, rf[r])
                elif op == 31:                                # POP
                    sp = rf[8]
                    j = sp + off
                    v = mem[j] if sp >= 0 and j < size else load(sp)
                    rf[8] = _wrap(sp + 1)
                    if r:
                        rf[r] = v
                    self.c = (v > 0) - (v < 0)
                elif op == 5:                                 # SUB
                    v = rf[r] - v
                    if v > WMAX or v < -WMAX:
                        v = _wrap(v)
                    if r:
                        rf[r] = v
                    self.c = (v > 0) - (v < 0)
                elif op == 3:                                 # LEA
                    if r:
                        rf[r] = ea
                elif op == 28:                                # CALL
                    sp = _wrap(rf[8] - 1)
                    rf[8] = sp
                    store(sp, pc)
                    ur[PC] = ea
                elif op == 29:                                # RET
                    v = load(rf[8])
                    ur[PC] = v
                    rf[8] = _wrap(rf[8] + addr + 1)
                elif op == 18:                                # SEL
                    v = t.trit_at(v, self.c + 1)
                    if r:
                        rf[r] = v
                    self.c = v
                elif op == 11:                                # TST
                    self.c = (v > 0) - (v < 0)
                elif op == 16:                                # XTR
                    if v == 27:                               # low trit
                        v = rf[r] % 3
                        if v == 2:
                            v = -1
                    else:
                        v = alu_xtr(rf[r], v)
                    if r:
                        rf[r] = v
                    self.c = (v > 0) - (v < 0)
                elif op == 6 or op == 7 or op == 8 or op == 9 or \
                        12 <= op <= 15:
                    a = rf[r]
                    if op == 6:
                        v = _wrap(a * v)
                    elif op == 7 or op == 8:
                        if v == 0:
                            raise Trap(isa.TRAP_DIVZERO, 0)
                        v = t.trunc_div(a, v) if op == 7 else t.trunc_mod(a, v)
                    elif op == 9:
                        v = -v
                    elif op == 12:
                        v = t.tmin(a, v)
                    elif op == 13:
                        v = t.tmax(a, v)
                    elif op == 14:
                        v = t.teqv(a, v)
                    else:
                        v = t.shift(a, v)
                    if r:
                        rf[r] = v
                    self.c = (v > 0) - (v < 0)
                elif op == 17:                                # TRT
                    self.c = alu_trit(rf[r], v)
                elif op == 19:                                # NOP
                    pass
                elif op == 32:                                # JSR
                    if r:
                        rf[r] = pc
                    ur[PC] = ea
                elif op == 33:                                # SVC
                    raise Trap(isa.TRAP_SVC, v)
                elif op == 34:                                # RTI
                    if self.mode < 0:
                        raise Trap(isa.TRAP_PRIV, op)
                    self.return_from_trap()
                elif op == 35:                                # IN
                    if self.mode < 0:
                        raise Trap(isa.TRAP_PRIV, op)
                    v = t.wrap(self.io_in(v))
                    if r:
                        rf[r] = v
                    self.c = (v > 0) - (v < 0)
                elif op == 36:                                # OUT
                    if self.mode < 0:
                        raise Trap(isa.TRAP_PRIV, op)
                    self.io_out(v, rf[r])
                elif op == 37:                                # HLT
                    if self.mode < 0:
                        raise Trap(isa.TRAP_PRIV, op)
                    self.halted = True
                elif op == 38:                                # TIM
                    if r:
                        rf[r] = t.wrap(self.clock)
                elif op == 39:                                # TAL
                    if r:
                        rf[r] = self.tally_get(_wrap(addr + rf[x]))
                elif op == 40:                                # TCL
                    self.tally_clear()
                    tally = self.tally
                else:
                    raise Trap(isa.TRAP_ILLEGAL, op)
            except Trap as tr:
                self.take_trap(tr.code, tr.arg)
        return n

    # ------------------------------------------------------------------
    def run(self, max_cycles=None, max_instructions=None):
        """Run until HLT, a machine check, or a limit.  Returns a reason."""
        try:
            if self.model == 30:
                limit = max_cycles if max_cycles is not None else 10 ** 12
                self._run_micro(limit)
            else:
                limit = (max_instructions if max_instructions is not None
                         else 10 ** 12)
                while not self.halted and limit > 0:
                    limit -= self._run_fast(min(limit, 1_000_000))
                    if max_cycles is not None and self.clock >= max_cycles:
                        break
        except MachineCheck as mc:
            self.check_message = str(mc)
            return "machine check"
        return "halt" if self.halted else "limit"

    # convenience for tests and tools
    @property
    def pc(self):
        return self.ur[PC]

    @pc.setter
    def pc(self, v):
        self.ur[PC] = v
