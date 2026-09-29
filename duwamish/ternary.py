"""Balanced-ternary arithmetic for the Duwamish 27-trit word.

A trit takes the values -1, 0, +1 (written T, 0, 1).  A word is 27 trits,
so a word holds every integer in [-WMAX, +WMAX] where WMAX = (3**27 - 1)/2.
Inside the simulator a word is kept as an ordinary Python int in that range;
the trit-level structure is recovered only when an operation needs it.

Balanced ternary has properties the committee prized:
  * negation is tritwise inversion -- there is no separate sign;
  * truncating trits *is* rounding to nearest, so shifts never bias;
  * a comparison has three outcomes, which is exactly one trit.
"""

TRITS = 27
RADIX = 3 ** TRITS
WMAX = (RADIX - 1) // 2
WMIN = -WMAX

POW3 = [3 ** i for i in range(TRITS + 2)]

TRIT_CHARS = {-1: "T", 0: "0", 1: "1"}
CHAR_TRITS = {"T": -1, "t": -1, "-": -1, "0": 0, "1": 1, "+": 1}

# Heptavintimal (balanced base-27) digits: three trits per digit, nine per word.
# 0 is '0', 1..13 are A..M, -13..-1 are N..Z.
HEPT_DIGITS = "NOPQRSTUVWXYZ0ABCDEFGHIJKLM"   # index = digit + 13


def wrap(v, n=TRITS):
    """Reduce an integer into the balanced range of an n-trit word."""
    m = POW3[n]
    h = (m - 1) // 2
    return (v + h) % m - h


def in_range(v, n=TRITS):
    h = (POW3[n] - 1) // 2
    return -h <= v <= h


def trits(v, n=TRITS):
    """Trits of v, least significant first (v must fit in n trits)."""
    out = []
    for _ in range(n):
        r = v % 3
        if r == 2:
            r = -1
        out.append(r)
        v = (v - r) // 3
    return out


def from_trits(ts):
    """Integer value of a trit list, least significant first."""
    v = 0
    for t in reversed(ts):
        v = v * 3 + t
    return v


def shift(v, n):
    """Multiply by 3**n.  For negative n this drops trits, which in balanced
    ternary rounds to the nearest integer (ties cannot occur)."""
    if n >= 0:
        return wrap(v * POW3[n]) if n < len(POW3) else 0
    n = -n
    if n >= TRITS + 1:
        return 0
    p = POW3[n]
    return (v + (p - 1) // 2) // p


def field(v, pos, length):
    """Balanced value of trits pos .. pos+length-1 of v."""
    if pos:
        p = POW3[pos]
        v = (v + (p - 1) // 2) // p
    return wrap(v, length)


def trit_at(v, pos):
    return field(v, pos, 1)


def lst(v):
    """Least significant trit."""
    r = v % 3
    return -1 if r == 2 else r


def sign(v):
    return (v > 0) - (v < 0)


def _tritwise(a, b, f):
    ta, tb = trits(a), trits(b)
    return from_trits([f(x, y) for x, y in zip(ta, tb)])


def tmin(a, b):
    """Tritwise minimum: Kleene AND on each trit."""
    return _tritwise(a, b, min)


def tmax(a, b):
    """Tritwise maximum: Kleene OR on each trit."""
    return _tritwise(a, b, max)


def teqv(a, b):
    """Tritwise product: +1 where trits agree (and are non-zero), -1 where they
    disagree, 0 where either is unknown.  Kleene equivalence."""
    return _tritwise(a, b, lambda x, y: x * y)


def trunc_div(a, b):
    """Quotient truncated toward zero (the SALISH / DIV convention)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def trunc_mod(a, b):
    return a - b * trunc_div(a, b)


def to_tstr(v, n=TRITS, strip=False):
    """Balanced-ternary string, most significant trit first, e.g. '1T0'."""
    s = "".join(TRIT_CHARS[t] for t in reversed(trits(v, n)))
    if strip:
        s = s.lstrip("0") or "0"
    return s


def from_tstr(s):
    v = 0
    for ch in s:
        if ch in "_ ":
            continue
        v = v * 3 + CHAR_TRITS[ch]
    return v


def to_hept(v, digits=9):
    """Heptavintimal rendering: nine letters per 27-trit word."""
    out = []
    for _ in range(digits):
        r = v % 27
        if r > 13:
            r -= 27
        out.append(HEPT_DIGITS[r + 13])
        v = (v - r) // 27
    return "".join(reversed(out))


def from_hept(s):
    v = 0
    for ch in s.upper():
        v = v * 27 + HEPT_DIGITS.index(ch) - 13
    return v
