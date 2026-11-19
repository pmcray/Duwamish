"""The Duwamish floating-point unit.

An optional feature, as floating point was on the IBM System/360: fitted as
standard to the Model 90 and available for the Model 30.  It is a separate
functional unit with its own double-length registers, so a product or a
quotient is formed exactly and rounded once.

Format (the same as the software library duwamish/lib/tfloat.sal):

    | exponent : 5 trits | mantissa : 22 trits |      value = m * 3^(e - 21)

Both fields are balanced, so a float needs no sign bit, no bias and no
complement.  (But the word's own sign is not the number's: a small
positive float has a negative exponent field.  The condition trit set by
these instructions is the sign of the number.)

A normalised mantissa has |m| > (3^21 - 1)/2, so the relative precision
is 3^-21, about 1e-10.  Zero is the word 0.  Exponent overflow saturates
at +121; underflow gives zero.  Rounding is to nearest, which in balanced
ternary is simply truncation of trits.

Timing, in 200 ns cycles beyond the instruction's own: add or subtract 3
(0.6 us), multiply 5 (1.0 us), divide 15 (3.0 us), convert or compare 2 --
roughly the speed of a CDC 6600's floating-point units.
"""

from fractions import Fraction

from . import ternary as t

P21 = 3 ** 21
P22 = 3 ** 22
MHI = (P22 - 1) // 2
MLO = (P21 - 1) // 2
EMAX = 121

LATENCY = {"FAD": 3, "FSB": 3, "FMP": 5, "FDV": 15, "FLT": 2, "FIX": 2,
           "FCM": 2}


class FPUDivideByZero(Exception):
    pass


def unpack(a):
    m = t.wrap(a, 22)
    e = (a - m) // P22
    return m, e


def pack(m, e):
    return e * P22 + m


def _round(x):
    """Nearest integer to a Fraction (balanced ternary rounds this way)."""
    return int(round(x))


def normalise(value):
    """Round an exact rational to the nearest representable float."""
    if value == 0:
        return 0
    value = Fraction(value)
    a = abs(value)
    # choose e so that 3^21/2 < |value| * 3^(21-e) <= 3^22/2
    e = 21
    while a * Fraction(3) ** (21 - e) > Fraction(MHI):
        e += 1
    while a * Fraction(3) ** (21 - e) <= Fraction(MLO):
        e -= 1
    m = _round(value * Fraction(3) ** (21 - e))
    if abs(m) > MHI:                    # rounding carried into a new trit
        e += 1
        m = _round(value * Fraction(3) ** (21 - e))
    if e < -EMAX:
        return 0
    if e > EMAX:
        e = EMAX
        m = MHI if m > 0 else -MHI
    return pack(m, e)


def value(a):
    m, e = unpack(a)
    return Fraction(m) * Fraction(3) ** (e - 21)


def fadd(a, b):
    return normalise(value(a) + value(b))


def fsub(a, b):
    return normalise(value(a) - value(b))


def fmul(a, b):
    return normalise(value(a) * value(b))


def fdiv(a, b):
    if unpack(b)[0] == 0:
        raise FPUDivideByZero()
    return normalise(value(a) / value(b))


def flt(n):
    return normalise(n)


def fix(a):
    """The nearest integer to a float, clipped to the word."""
    v = _round(value(a))
    return max(t.WMIN, min(t.WMAX, v))


def fcm(a, b):
    """The sign of a - b."""
    d = value(a) - value(b)
    return (d > 0) - (d < 0)


def to_float(a):
    """For display: the Python float nearest a Duwamish float."""
    return float(value(a))


def from_float(x):
    return normalise(Fraction(x))


def operate(name, r, operand):
    """Execute one FPU instruction.  Returns (new R, condition trit);
    FCM leaves R unchanged."""
    if name == "FAD":
        v = fadd(r, operand)
    elif name == "FSB":
        v = fsub(r, operand)
    elif name == "FMP":
        v = fmul(r, operand)
    elif name == "FDV":
        v = fdiv(r, operand)
    elif name == "FLT":
        v = flt(operand)
    elif name == "FIX":
        v = fix(operand)
    elif name == "FCM":
        return r, fcm(r, operand)
    else:
        raise ValueError(name)
    # the sign of a float is the sign of its mantissa, not of the word:
    # a small positive number has a negative exponent field
    s = v if name == "FIX" else unpack(v)[0]
    return v, (s > 0) - (s < 0)
