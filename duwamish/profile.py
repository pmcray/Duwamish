"""The Beer monitor, read out: execution tallies aggregated by procedure.

Stafford Beer wanted every viable system to watch itself.  The Duwamish
keeps a hardware tally of how often each word of core is executed; this
module attributes those counts to the procedures of a SALISH program.
"""

import bisect


def by_procedure(machine, obj, top=20):
    starts = sorted((a, n[2:]) for n, a in obj.symbols.items()
                    if n.startswith("P_") and isinstance(a, int))
    addrs = [a for a, _ in starts]
    totals = {}
    for addr, count in machine.tally_items():
        i = bisect.bisect_right(addrs, addr) - 1
        if i >= 0 and addr < obj.end:
            name = starts[i][1]
            totals[name] = totals.get(name, 0) + count
    grand = sum(totals.values()) or 1
    rows = sorted(totals.items(), key=lambda kv: -kv[1])[:top]
    return [(name, n, 100.0 * n / grand) for name, n in rows]


def report(machine, obj, top=20):
    lines = [f"{'procedure':24} {'instructions':>14} {'share':>7}"]
    for name, n, pct in by_procedure(machine, obj, top):
        lines.append(f"{name:24} {n:14,} {pct:6.1f}%")
    return "\n".join(lines)
