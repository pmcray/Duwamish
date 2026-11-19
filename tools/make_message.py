"""Write the two transmissions of the Byurakan demonstration,
data/byurakan1.msg and data/byurakan2.msg.

A transmission is a string of trits, sent as pulses of one polarisation
(+), pulses of the other (-), and silence (0).  Its grammar:

    a number     a run of +, counted
    an item      numbers, separated by 0
    a section    items, separated by -
    the message  sections, each ended by --

The sections are the frame (the primes from 2 to 31), the rules of a
machine (in each rule the first number is what is replaced, and the rest
is what replaces it), and the seed the machine starts from.
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))
PRIMES = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31]


def item(numbers):
    return "0".join("+" * n for n in numbers)


def section(items):
    return "-".join(item(i) for i in items) + "--"


def message(rules, seed):
    return section([PRIMES]) + section(rules) + section([seed])


def write(name, text):
    with open(os.path.join(HERE, "..", "data", name), "w") as f:
        for i in range(0, len(text), 60):
            f.write(text[i:i + 60] + "\n")


if __name__ == "__main__":
    # Lindenmayer's alga (1968): 1 -> 1 2, 2 -> 1
    write("byurakan1.msg", message([[1, 1, 2], [2, 1]], [1]))
    # a square that grows: 1 -> a ring of 1 round a 2; 2 -> nine of 2
    write("byurakan2.msg", message([[1, 1, 1, 1, 1, 2, 1, 1, 1, 1],
                                    [2] + [2] * 9], [1]))
