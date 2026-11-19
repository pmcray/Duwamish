"""WHALE: the Woodworth Heuristic Associative Learning Evaluator.

WHALE is SALISH with an associative store, as Stanford's SAIL was ALGOL
with Feldman and Rovner's LEAP.  Its facts are triples of items,

    attribute of object is value

and every triple carries a weight of evidence, so that its truth is
three-valued: true, false, or not yet known (see duwamish/lib/whale.sal).

This module is the WHALE compiler.  It parses the main file with a SALISH
parser extended by these forms, and turns them into SALISH -- calls on the
run-time library -- which the SALISH compiler compiles as usual:

  declarations
    item a, b, c                 items: constants numbered from 1, whose
                                 names the program can print
  statements
    make  A of O is V            true, with certainty
    deny  A of O is V            false, with certainty
    erase A of O is V            forgotten: unknown again
    confirm A of O is V by w     add w centidecibans of evidence (w < 0
                                 is evidence against)
    foreach [ranked] x, y such that C1 and C2 ... do S
                                 every binding of x, y for which the
                                 conjuncts hold; a conjunct is a triple, in
                                 which an unbound variable matches any
                                 item, or any SALISH condition.  A triple
                                 matches when it is true; written
                                 `possibly A of O is V', when it is true or
                                 unknown -- not false.  `ranked' takes the
                                 best supported triples first.
  expressions
    fact   A of O is V           +1 true, 0 unknown, -1 false
    weight A of O is V           its weight of evidence (centidecibans)
    the    A of O                the value best supported as true, or 0
    new                          a fresh item

The matches of each triple are found when the loop over it starts, so the
body of a foreach may make and erase triples freely.  `break' and `next'
apply to the innermost triple of a foreach.

The library files the program gets are SALISH, parsed as SALISH: only the
main file is WHALE.
"""

from . import salish
from .salish import CompileError

WHALE_KW = {"item", "make", "deny", "erase", "confirm", "foreach", "such",
            "that", "is", "fact", "weight", "the", "ranked", "new", "possibly"}
KEYWORDS = salish.KEYWORDS | WHALE_KW
MATCH_MAX = 128             # the matches of one triple a foreach can hold


class WhaleParser(salish.Parser):
    def __init__(self, toks):
        super().__init__(toks)
        self.items = []
        self.nforeach = 0

    # ---------------- declarations ----------------
    def module(self):
        decls = []
        bloop = False
        first = self.tok
        while not self.at("eof"):
            if self.at_kw("item"):
                self.next()
                while True:
                    t = self.tok
                    n = self.name()
                    if n in self.items:
                        self.err(f"item {n} is declared twice", t)
                    self.items.append(n)
                    decls.append(("const", t.line, n,
                                  ("num", t.line, len(self.items))))
                    if not self.at_op(","):
                        break
                    self.next()
                continue
            # anything else is a SALISH declaration: parse one at a time
            save = self.toks
            start = self.i
            end = self._decl_end(start)
            self.toks = save[start:end] + [salish.Tok("eof", None,
                                                      save[end].line, True,
                                                      save[end].file)]
            self.i = 0
            more, b = super().module()
            self.toks = save
            self.i = end
            decls += more
            bloop = bloop or b
        line = first.line
        names = [("str", line, "")] + [("str", line, n) for n in self.items]
        decls = ([("get", line, "whale", first),
                  ("const", line, "wh_nitems", ("num", line, len(self.items))),
                  ("global", line, "wh_names", None,
                   ("table", line, names))] + decls)
        return decls, bloop

    def _decl_end(self, i):
        """The index of the next top-level `item' after token i (or eof).
        `item' is a keyword, so it cannot occur inside a declaration."""
        i += 1
        while self.toks[i].kind != "eof" and not (
                self.toks[i].kind == "kw" and self.toks[i].val == "item"):
            i += 1
        return i

    # ---------------- triples ----------------
    def triple(self):
        a = self.postfix()
        self.expect("kw", "of")
        o = self.postfix()
        self.expect("kw", "is")
        v = self.postfix()
        return a, o, v

    @staticmethod
    def call(line, name, args):
        return ("call", line, name, args)

    # ---------------- statements ----------------
    def stmt(self):
        t = self.tok
        line = t.line
        if t.kind == "kw" and t.val in ("make", "deny", "erase"):
            self.next()
            a, o, v = self.triple()
            code = {"make": 1, "deny": -1, "erase": 0}[t.val]
            return ("expr", line, self.call(line, "wh_set",
                                            [a, o, v, ("num", line, code)]))
        if t.kind == "kw" and t.val == "confirm":
            self.next()
            a, o, v = self.triple()
            self.expect("kw", "by")
            w = self.expr()
            return ("expr", line, self.call(line, "wh_confirm", [a, o, v, w]))
        if t.kind == "kw" and t.val == "foreach":
            return self.foreach()
        return super().stmt()

    def foreach(self):
        line = self.next().line
        ranked = 0
        if self.at_kw("ranked"):
            self.next()
            ranked = 1
        names = [self.name()]
        while self.at_op(","):
            self.next()
            names.append(self.name())
        if len(set(names)) != len(names):
            self.err("a foreach variable is named twice")
        self.expect("kw", "such")
        self.expect("kw", "that")
        conj = [self.conjunct()]
        while self.at_kw("and"):
            self.next()
            conj.append(self.conjunct())
        self.expect("kw", "do")
        body = self.stmt()
        self.nforeach += 1
        inner = self.expand(conj, set(names), set(), body, ranked, line)
        return ("block", line,
                [("var", line, [(n, None, ("num", line, 0), line)
                                for n in names]), inner])

    def conjunct(self):
        """A triple, or any SALISH condition (without `and' or `or')."""
        if self.at_kw("possibly"):
            self.next()
            return ("triple", 0) + self.triple()
        start = self.i
        try:
            self.postfix()
            is_triple = self.at_kw("of")
        except CompileError:
            is_triple = False
        self.i = start
        if is_triple:
            return ("triple", 1) + self.triple()
        return ("test", self.not_expr())

    def expand(self, conj, fvars, bound, body, ranked, line):
        if not conj:
            return body
        c, rest = conj[0], conj[1:]
        if c[0] == "test":
            inner = self.expand(rest, fvars, bound, body, ranked, line)
            return ("if", line, c[1], inner, None)
        self.nforeach += 1
        k = self.nforeach
        buf, n, i = f"wh_b{k}", f"wh_n{k}", f"wh_k{k}"
        pattern, binds, checks = [], [], []
        now = set(bound)
        for slot, e in zip(("wh_attr", "wh_obj", "wh_val"), c[2:]):
            if e[0] == "name" and e[2] in fvars and e[2] not in bound:
                pattern.append(("num", line, 0))
                got = self.call(line, slot, [("index", line,
                                              ("name", line, buf),
                                              ("name", line, i))])
                if e[2] in now:          # twice in one triple: must agree
                    checks.append(("cmp", line, "=", e, got))
                else:
                    binds.append(("assign", line, e, got))
                    now.add(e[2])
            else:
                pattern.append(e)
        inner = self.expand(rest, fvars, now, body, ranked, line)
        if checks:
            test = checks[0]
            for ch in checks[1:]:
                test = ("and", line, test, ch)
            inner = ("if", line, test, inner, None)
        match = self.call(line, "wh_match",
                          pattern + [("name", line, buf),
                                     ("num", line, MATCH_MAX),
                                     ("num", line, ranked),
                                     ("num", line, c[1])])
        loop = ("for", line, i, ("num", line, 0),
                ("bin", line, "-", ("name", line, n), ("num", line, 1)),
                ("num", line, 1), ("block", line, binds + [inner]))
        return ("block", line, [
            ("var", line, [(buf, ("num", line, MATCH_MAX), None, line),
                           (n, None, match, line)]),
            loop])

    # ---------------- expressions ----------------
    def primary(self):
        t = self.tok
        if t.kind == "kw" and t.val in ("fact", "weight"):
            self.next()
            a, o, v = self.triple()
            return self.call(t.line, "wh_truth" if t.val == "fact"
                             else "wh_weight", [a, o, v])
        if t.kind == "kw" and t.val == "the":
            self.next()
            a = self.postfix()
            self.expect("kw", "of")
            o = self.postfix()
            return self.call(t.line, "wh_the", [a, o])
        if t.kind == "kw" and t.val == "new":
            self.next()
            if self.at_op("(") and self.cont():
                self.next()
                self.expect("op", ")")
            return self.call(t.line, "wh_new", [])
        return super().primary()


def parse(text, fname):
    return WhaleParser(salish.tokenize(text, fname, KEYWORDS)).module()


def compile_source(text, fname="<source>", include_path=None, optimise=False):
    """Compile WHALE text to TRIAD assembly.  Returns (asm_text, compiler)."""
    c = salish.Compiler(include_path, optimise)
    c.main_parser = parse
    c.main_file = fname
    asm = c.compile(text, fname)
    return asm, c
