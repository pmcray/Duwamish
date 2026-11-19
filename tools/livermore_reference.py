"""Double-precision reference for programs/livermore.sal: the same six
kernels on the same data, returning each checksum times 3^12."""

N, M, S = 100, 112, 3 ** 12


def datum(k):
    return (k * 7919) % 729 - 364


def reference():
    y = [datum(k) / 729 for k in range(M)]
    z = [datum(k + 37) / 729 for k in range(M)]
    u = [datum(k + 101) / 729 for k in range(M)]
    q, r, t = 250 / 729, 170 / 729, 100 / 729
    out = {}
    x = [0.0] * M
    for k in range(N):
        x[k] = q + y[k] * (r * z[k + 10] + t * z[k + 11])
    out[1] = sum(x[:N])
    out[3] = sum(z[k] * y[k] for k in range(N))
    x[0] = y[0]
    for i in range(1, N):
        x[i] = z[i] * (y[i] - x[i - 1])
    out[5] = sum(x[:N])
    for k in range(N):
        x[k] = (u[k] + r * (z[k] + r * y[k])
                + t * (u[k + 3] + r * (u[k + 2] + r * u[k + 1])
                       + t * (u[k + 6] + q * (u[k + 5] + q * u[k + 4]))))
    out[7] = sum(x[:N])
    x[0] = y[0]
    for k in range(1, N):
        x[k] = x[k - 1] + y[k]
    out[11] = sum(x[:N])
    for k in range(N):
        x[k] = y[k + 1] - y[k]
    out[12] = sum(x[:N])
    return {k: v * S for k, v in out.items()}


if __name__ == "__main__":
    for k, v in reference().items():
        print(f"kernel {k:2}  {v:16.1f}")
