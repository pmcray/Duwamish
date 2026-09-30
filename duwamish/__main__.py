"""Command-line operator's console for the Duwamish.

    python -m duwamish run JOBDECK...        run job decks through the satellite
    python -m duwamish go FILE [--data F]    compile/assemble one program, run it
    python -m duwamish compile FILE.sal      show the TRIAD code SALISH produces
    python -m duwamish asm FILE.tri          assemble and list
    python -m duwamish micro                 list the Model 30 microprogram
    python -m duwamish microkit              print the microkit include file

Options for run/go:  --model 30|90   --wcs (enable the writable control
store key)   --fpu / --no-fpu (fit or remove the floating-point unit;
standard on the Model 90)   --opt (compile SALISH with the optimising
compiler; also for compile)   --list (print listings)   --time N (cycle
limit, go only)
"""

import argparse
import sys

from . import microasm, salish, satellite, triad


def main(argv=None):
    ap = argparse.ArgumentParser(prog="duwamish", description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("decks", nargs="+")
    g = sub.add_parser("go")
    g.add_argument("file")
    g.add_argument("--data")
    g.add_argument("--time", type=int, default=0)
    for p in (r, g):
        p.add_argument("--model", type=int, default=30, choices=(30, 90))
        p.add_argument("--wcs", action="store_true")
        p.add_argument("--list", action="store_true")
        p.add_argument("--fpu", dest="fpu", action="store_true", default=None)
        p.add_argument("--no-fpu", dest="fpu", action="store_false")
    c = sub.add_parser("compile")
    c.add_argument("file")
    for p in (r, g, c):
        p.add_argument("--opt", action="store_true")
    a = sub.add_parser("asm")
    a.add_argument("file")
    sub.add_parser("micro")
    sub.add_parser("microkit")
    args = ap.parse_args(argv)

    if args.cmd == "run":
        satellite.run_decks(args.decks, model=args.model, wcs=args.wcs,
                            listing=args.list, fpu=args.fpu,
                            optimise=args.opt)
    elif args.cmd == "go":
        satellite.run_program(args.file, data=args.data, model=args.model,
                              wcs=args.wcs, listing=args.list,
                              time_limit=args.time, fpu=args.fpu,
                              optimise=args.opt)
    elif args.cmd == "compile":
        with open(args.file) as f:
            asm, comp = salish.compile_source(f.read(), args.file,
                                              optimise=args.opt)
        sys.stdout.write(asm)
        if comp.peephole_counts:
            print("; peephole: " + ", ".join(
                f"{v} {k}" for k, v in sorted(comp.peephole_counts.items())))
        if comp.bloop_report:
            print(";", comp.bloop_report)
    elif args.cmd == "asm":
        with open(args.file) as f:
            obj = triad.assemble(f.read(), origin=satellite.USER_ORIGIN)
        print(obj.listing_text())
    elif args.cmd == "micro":
        print(microasm.default_microprogram().listing())
    elif args.cmd == "microkit":
        sys.stdout.write(microasm.microkit_source())


if __name__ == "__main__":
    main()
