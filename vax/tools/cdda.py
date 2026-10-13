#!/usr/bin/env python3
"""
cdda.py -- do things with the raw Red Book audio that CDGEN writes.

A .CDDA file is exactly what goes onto an audio CD: 44,100 frames per
second, each frame a signed 16-bit little-endian left sample followed by
the right sample, in sectors of 2352 bytes (588 frames).  Nothing needs
converting -- these commands only wrap the data for modern tools.

    cdda.py wav  TRACK.CDDA [OUT.wav]      add a RIFF/WAVE header, to listen
    cdda.py cue  ALBUM.bin TRACK1.CDDA [TRACK2.CDDA ...] [--title T]
                                           build a burnable BIN/CUE image
                                           (2-second pregap per track)
    cdda.py info TRACK.CDDA                length, levels, a crude spectrum
"""

import argparse
import math
import os
import struct
import sys

RATE = 44100
SECTOR = 2352
FRAMES = 588


def read(path):
    data = open(path, 'rb').read()
    if len(data) % 4:
        data = data[:len(data) - len(data) % 4]
    return data


def msf(sectors):
    return '%02d:%02d:%02d' % (sectors // (75 * 60), sectors // 75 % 60,
                               sectors % 75)


def cmd_wav(a):
    data = read(a.cdda)
    out = a.out or os.path.splitext(a.cdda)[0] + '.wav'
    with open(out, 'wb') as f:
        f.write(b'RIFF' + struct.pack('<I', 36 + len(data)) + b'WAVE')
        f.write(b'fmt ' + struct.pack('<IHHIIHH', 16, 1, 2, RATE, RATE * 4,
                                      4, 16))
        f.write(b'data' + struct.pack('<I', len(data)))
        f.write(data)
    print('%s: %d frames (%.2f s) -> %s' % (a.cdda, len(data) // 4,
                                            len(data) / 4 / RATE, out))


def cmd_cue(a):
    pos = 0
    lines = []
    if a.title:
        lines.append('TITLE "%s"' % a.title)
    if a.performer:
        lines.append('PERFORMER "%s"' % a.performer)
    lines.append('FILE "%s" BINARY' % os.path.basename(a.bin))
    with open(a.bin, 'wb') as out:
        for n, path in enumerate(a.tracks, 1):
            data = read(path)
            if len(data) % SECTOR:
                data += bytes(SECTOR - len(data) % SECTOR)
            gap = bytes(2 * 75 * SECTOR)        # two seconds of silence
            lines.append('  TRACK %02d AUDIO' % n)
            lines.append('    TITLE "%s"' %
                         os.path.splitext(os.path.basename(path))[0])
            lines.append('    INDEX 00 %s' % msf(pos))
            out.write(gap)
            pos += len(gap) // SECTOR
            lines.append('    INDEX 01 %s' % msf(pos))
            out.write(data)
            pos += len(data) // SECTOR
    cue = os.path.splitext(a.bin)[0] + '.cue'
    with open(cue, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    print('%s + %s: %d tracks, %s (%d sectors)' % (a.bin, cue,
                                                  len(a.tracks), msf(pos),
                                                  pos))


def cmd_info(a):
    data = read(a.cdda)
    n = len(data) // 4
    s = struct.unpack('<%dh' % (2 * n), data)
    print('%s: %d frames, %.2f s, %d sectors (%s)' % (
        a.cdda, n, n / RATE, (len(data) + SECTOR - 1) // SECTOR,
        msf((len(data) + SECTOR - 1) // SECTOR)))
    peak = max(max(s), -min(s)) if s else 0
    print('peak %d (%.1f dBFS)' % (peak, 20 * math.log10(max(peak, 1) /
                                                          32768)))
    step = RATE // a.per_second
    print('   time    L rms    R rms   dominant (Hz)')
    for start in range(0, n, step):
        L = s[2 * start:2 * (start + step):2]
        R = s[2 * start + 1:2 * (start + step):2]
        if not L:
            break
        lr = math.sqrt(sum(x * x for x in L) / len(L))
        rr = math.sqrt(sum(x * x for x in R) / len(R))
        print('%7.2f  %7.0f  %7.0f   %s' % (start / RATE, lr, rr,
                                            dominant(L) if lr > 30 else '-'))


def dominant(x):
    """Strongest frequency by zero-crossing-free autocorrelation search."""
    n = min(len(x), 4096)
    x = x[:n]
    mean = sum(x) / n
    x = [v - mean for v in x]
    best, best_lag = 0, 0
    for lag in range(20, 1200):
        c = sum(x[i] * x[i + lag] for i in range(0, n - lag, 2))
        if c > best:
            best, best_lag = c, lag
    return '%.1f' % (RATE / best_lag) if best_lag else '?'


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('wav')
    p.add_argument('cdda')
    p.add_argument('out', nargs='?')
    p.set_defaults(fn=cmd_wav)
    p = sub.add_parser('cue')
    p.add_argument('bin')
    p.add_argument('tracks', nargs='+')
    p.add_argument('--title')
    p.add_argument('--performer', default='Alan Fredericks')
    p.set_defaults(fn=cmd_cue)
    p = sub.add_parser('info')
    p.add_argument('cdda')
    p.add_argument('--per-second', type=int, default=2)
    p.set_defaults(fn=cmd_info)
    a = ap.parse_args()
    a.fn(a)


if __name__ == '__main__':
    main()
