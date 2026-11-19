"""The one-level store, after Kilburn's Atlas (1962).

Atlas gave its programs one store: a million words of address space, of
which a few pages were in core and the rest on the drum.  When a program
touched a page not in core, the hardware trapped; the supervisor chose a
page to send back to the drum, brought the wanted page in, and let the
program go on as though nothing had happened.  Which page to send back
was decided by a "learning program": it watched how long each page had
lain idle, and predicted from its past when it would next be wanted.

On the Duwamish (the //STORE card, in duwamish/satellite.py):

  * A page is 729 words (3^6); the program's address space is the first
    243 pages of core, 177,147 words, which is what the drum holds, a
    page to a track.  The stack starts at the top of that space.
  * The paging unit checks every fetch, load and store a program makes.
    For each page it keeps whether the page is in core, whether it has
    been altered, the time of its last use, and the length of its last
    period of idleness -- Atlas's "use digits", kept as instruction
    counts.  A reference to a page not in core is trap 12, page fault.
  * On a page fault the unit sets out its table in protected core, at
    TABLE: first the instruction count now and the number of pages, then
    four words for each page: in core, idle now (t), last idle period
    (T), altered.  The Executive calls the pager (duwamish/lib/pager.sal,
    SALISH, in protected core) to choose a page to evict, writes that page
    back to the drum if it was altered, reads the wanted page in, and
    restarts the instruction.  Drum transfers are timed as the drum's.
  * The simulator leaves every page at its own address in core rather
    than moving it into one of a few page frames; the pager keeps no more
    pages in core than the frames allowed, so the store behaves, and is
    timed, as one with that many frames.

This module holds the paging unit and, for comparison afterwards, the
replacement policies run over a recorded string of page references --
among them Belady's (1966) optimum, which needs the future and so can
only be computed after the event.
"""

from . import isa

PAGE = 729
NPAGES = 243
SPACE = PAGE * NPAGES                  # words of address space
SAMPLE = 1024                          # Atlas looked every 1024 instructions
TRAP_PAGE = 12
TABLE = -20000                         # where the unit sets out its table
DEV_PAGE = 9                           # OUT p+1: p is in core; OUT -(p+1): out

POLICIES = {"ATLAS": 0, "FIFO": 1, "LRU": 2, "RANDOM": 3}


class PagingUnit:
    def __init__(self, frames, record=True):
        self.frames = frames
        self.resident = [False] * NPAGES
        self.altered = [False] * NPAGES
        self.last = [0] * NPAGES
        self.idle = [0] * NPAGES
        self.faults = 0
        self.ins = 0
        self.outs = 0
        self.writebacks = 0
        self.refs = [] if record else None
        self.lastref = -1

    def touch(self, m, a, write):
        """A user reference to address a >= 0: trap if its page is out."""
        p = a // PAGE
        if p >= NPAGES:
            raise isa_trap(isa.TRAP_ADDRESS, a)
        if not self.resident[p]:
            self.faults += 1
            raise isa_trap(TRAP_PAGE, p)
        now = m.icount
        gap = now - self.last[p]
        if gap > SAMPLE:
            self.idle[p] = gap
        self.last[p] = now
        if write:
            self.altered[p] = True
        if p != self.lastref:
            self.lastref = p
            if self.refs is not None:
                self.refs.append(p)

    def publish(self, m):
        """Set out the table in protected core, for the supervisor."""
        from .machine import MEM_OFF as off
        mem, now = m.mem, m.icount
        base = TABLE + off
        mem[base] = now
        mem[base + 1] = NPAGES
        for p in range(NPAGES):
            i = base + 4 + 4 * p
            if self.resident[p]:
                mem[i] = 1
                mem[i + 1] = now - self.last[p]
                mem[i + 2] = self.idle[p]
                mem[i + 3] = 1 if self.altered[p] else 0
            else:
                mem[i] = mem[i + 1] = mem[i + 2] = mem[i + 3] = 0

    def out(self, m, v):
        """The supervisor's OUT to the paging unit."""
        if v > 0:
            # the page's history stays: the time it spent on the drum is
            # the idle period its next use will measure
            p = v - 1
            self.resident[p] = True
            self.altered[p] = False
            self.ins += 1
        elif v < 0:
            p = -v - 1
            if self.altered[p]:
                self.writebacks += 1
            self.resident[p] = False
            self.altered[p] = False
            self.outs += 1


def isa_trap(code, arg):
    from .machine import Trap
    return Trap(code, arg)


# ----------------------------------------------------------------------
# replacement policies over a recorded reference string
# ----------------------------------------------------------------------
def fifo_faults(refs, frames):
    from collections import deque
    inq, q, faults = set(), deque(), 0
    for p in refs:
        if p in inq:
            continue
        faults += 1
        if len(q) >= frames:
            inq.discard(q.popleft())
        q.append(p)
        inq.add(p)
    return faults


def lru_faults(refs, frames):
    from collections import OrderedDict
    od, faults = OrderedDict(), 0
    for p in refs:
        if p in od:
            od.move_to_end(p)
            continue
        faults += 1
        if len(od) >= frames:
            od.popitem(last=False)
        od[p] = True
    return faults


def min_faults(refs, frames):
    """Belady's optimum: evict the page whose next use is furthest off."""
    import heapq
    n = len(refs)
    nxt = [0] * n
    seen = {}
    for i in range(n - 1, -1, -1):
        nxt[i] = seen.get(refs[i], n + i)
        seen[refs[i]] = i
    resident = {}                      # page -> its next use
    heap = []                          # (-next use, page), lazily cleaned
    faults = 0
    for i, p in enumerate(refs):
        if p in resident:
            resident[p] = nxt[i]
            heapq.heappush(heap, (-nxt[i], p))
            continue
        faults += 1
        if len(resident) >= frames:
            while True:
                negu, q = heapq.heappop(heap)
                if q in resident and resident[q] == -negu:
                    del resident[q]
                    break
        resident[p] = nxt[i]
        heapq.heappush(heap, (-nxt[i], p))
    return faults
