import os

from duwamish import satellite

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_job(deck, model=90, wcs=False):
    """Run a job deck (text); return the satellite (jobs, steps, output)."""
    sat = satellite.Satellite([(deck, os.path.join(ROOT, "test.job"))],
                              model=model, wcs=wcs, out=lambda s: None)
    sat.run()
    return sat


def run_salish(src, data=None, model=90, wcs=False):
    """Compile and run SALISH source; return (printer output, step result)."""
    deck = "//JOB T\n//SALISH\n" + src + "\n//EXEC\n"
    if data is not None:
        deck += "//DATA\n" + data + "\n"
    sat = run_job(deck, model, wcs)
    job = sat.jobs[0]
    if job.failed:
        raise AssertionError("\n".join(job.log))
    step = job.steps[0]
    return step.output, step.result


def run_file(path, data=None, model=90, wcs=False):
    kind = "TRIAD" if path.endswith(".tri") else "SALISH"
    deck = f"//JOB T\n//{kind} FROM={os.path.join(ROOT, path)}\n//EXEC\n"
    if data is not None:
        deck += f"//DATA FROM={os.path.join(ROOT, data)}\n"
    sat = run_job(deck, model, wcs)
    job = sat.jobs[0]
    if job.failed:
        raise AssertionError("\n".join(job.log))
    return job.steps[0].output, job.steps[0].result


def run_lisp(text, model=90):
    sat = run_job("//JOB L\n//EXEC TRILISP\n//DATA\n" + text + "\n", model)
    return sat.jobs[0].steps[0].output
