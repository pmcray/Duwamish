#!/usr/bin/env python3
"""
vmsdisk.py -- create and manage MiniVMS (MFS-1) disk images on the host.

The image is a plain block-for-block disk file that SIMH attaches to the
RQDX3 controller (ATTACH RQ0 file).  Layout (see minivms/SYSDEF.MAR):

    LBN 0        bootstrap (reserved)
    LBN 1        home block
    LBN 2..17    directory, 128 entries of 64 bytes
    LBN 18..     file data; every file is one contiguous extent

Commands:
    vmsdisk.py init  DISK [--blocks N] [--label L] [--owner O] [--year Y]
    vmsdisk.py put   DISK HOSTFILE [NAME.TYPE] [--binary | --text]
    vmsdisk.py get   DISK NAME.TYPE[;V] HOSTFILE
    vmsdisk.py dir   DISK
    vmsdisk.py delete DISK NAME.TYPE;V
"""

import argparse
import datetime
import os
import struct
import sys

BLOCK = 512
HOME_LBN = 1
DIR_LBN = 2
DIR_BLOCKS = 16
ENTSIZE = 64
ENTRIES = DIR_BLOCKS * BLOCK // ENTSIZE
DATA_LBN = DIR_LBN + DIR_BLOCKS
MAGIC = b'MINIVMS-MFS1    '
NAMELEN = 32

RFM_UDF, RFM_FIX, RFM_VAR, RFM_STMLF = 0, 1, 2, 5
RFM_NAMES = {0: 'UDF', 1: 'FIX', 2: 'VAR', 3: 'VFC', 4: 'STM', 5: 'STMLF',
             6: 'STMCR'}

# RD54 size, the largest of the RD-series Winchesters for the RQDX3
DEFAULT_BLOCKS = 311200

TEXT_TYPES = {'MAR', 'TXT', 'LIS', 'COM', 'SCO', 'SCORE', 'DAT', 'FOR',
              'MSS', 'DOC', 'MEM', 'CSV', 'MAP', 'STB', 'LOG', 'NOTE'}

MJD_EPOCH = datetime.date(1858, 11, 17)


class Volume:
    def __init__(self, path):
        self.path = path
        self.f = open(path, 'r+b')
        self.home = bytearray(self.read(HOME_LBN, 1))
        if self.home[0:16] != MAGIC:
            sys.exit('%s: not a MiniVMS (MFS-1) volume' % path)
        self.dir = bytearray(self.read(DIR_LBN, DIR_BLOCKS))

    def read(self, lbn, n):
        self.f.seek(lbn * BLOCK)
        data = self.f.read(n * BLOCK)
        return data.ljust(n * BLOCK, b'\0')

    def write(self, lbn, data):
        self.f.seek(lbn * BLOCK)
        self.f.write(data)

    def flush(self):
        self.write(HOME_LBN, self.home)
        self.write(DIR_LBN, self.dir)
        self.f.close()

    # home block fields
    maxblk = property(lambda s: struct.unpack_from('<I', s.home, 28)[0])
    freelbn = property(lambda s: struct.unpack_from('<I', s.home, 40)[0])

    def set_freelbn(self, v):
        struct.pack_into('<I', self.home, 40, v)

    def entries(self):
        for i in range(ENTRIES):
            e = self.dir[i * ENTSIZE:(i + 1) * ENTSIZE]
            if e[34] & 1:
                yield i, decode_entry(e)

    def lookup(self, name, version=0):
        best = None
        for i, e in self.entries():
            if e['name'] != name:
                continue
            if version:
                if e['version'] == version:
                    return i, e
            elif best is None or e['version'] > best[1]['version']:
                best = (i, e)
        return best


def decode_entry(e):
    name = e[0:NAMELEN].decode('latin-1').rstrip()
    version, flags, rfm, lbn, alloc, size, day, cs, attr = struct.unpack_from(
        '<HBBIIIIII', e, 32)
    return dict(name=name, version=version, flags=flags, rfm=rfm, lbn=lbn,
                alloc=alloc, size=size, day=day, cs=cs, attr=attr)


def now_mfs(year=None):
    t = datetime.datetime.now()
    if year:
        try:
            t = t.replace(year=year)
        except ValueError:
            t = t.replace(year=year, day=28)
    day = (t.date() - MJD_EPOCH).days
    cs = (t.hour * 3600 + t.minute * 60 + t.second) * 100 + \
        t.microsecond // 10000
    return day, cs


def fmt_date(day, cs):
    d = MJD_EPOCH + datetime.timedelta(days=day)
    s = cs // 100
    return '%2d-%s-%04d %02d:%02d:%02d' % (
        d.day, d.strftime('%b').upper(), d.year, s // 3600, s // 60 % 60,
        s % 60)


def parse_name(spec):
    spec = spec.upper()
    for sep in (':', ']', '>'):
        if sep in spec:
            spec = spec.rsplit(sep, 1)[1]
    version = 0
    if ';' in spec:
        spec, v = spec.split(';', 1)
        version = int(v) if v else 0
    if '.' not in spec:
        spec += '.'
    if len(spec) > NAMELEN:
        sys.exit('file name too long (max %d characters): %s' %
                 (NAMELEN, spec))
    ok = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789$_-.')
    if not set(spec) <= ok or spec.count('.') != 1:
        sys.exit('bad file name: %s' % spec)
    return spec, version


def cmd_init(a):
    blocks = a.blocks
    with open(a.disk, 'wb') as f:
        f.truncate(blocks * BLOCK)
        home = bytearray(BLOCK)
        home[0:16] = MAGIC
        home[16:28] = a.label.upper().encode()[:12].ljust(12)
        struct.pack_into('<IIII', home, 28, blocks, DIR_LBN, DIR_BLOCKS,
                         DATA_LBN)
        home[44:56] = a.owner.upper().encode()[:12].ljust(12)
        struct.pack_into('<H', home, 60, a.year)
        f.seek(HOME_LBN * BLOCK)
        f.write(home)
    print('%s: MFS-1 volume %s, %d blocks, owner [%s], year %d' % (
        a.disk, a.label.upper(), blocks, a.owner.upper(), a.year))


def cmd_put(a):
    v = Volume(a.disk)
    name, _ = parse_name(a.name or os.path.basename(a.hostfile))
    data = open(a.hostfile, 'rb').read()
    ftype = name.split('.', 1)[1]
    if a.binary:
        text = False
    elif a.text:
        text = True
    else:
        text = ftype in TEXT_TYPES
    if text:
        data = data.replace(b'\r\n', b'\n')
        if data and not data.endswith(b'\n'):
            data += b'\n'
    blocks = (len(data) + BLOCK - 1) // BLOCK
    lbn = v.freelbn
    if lbn + blocks > v.maxblk:
        sys.exit('%s: device full' % a.disk)
    highest = 0
    free = None
    for i in range(ENTRIES):
        e = v.dir[i * ENTSIZE:(i + 1) * ENTSIZE]
        if e[34] & 1:
            d = decode_entry(e)
            if d['name'] == name:
                highest = max(highest, d['version'])
        elif free is None:
            free = i
    if free is None:
        sys.exit('%s: directory full' % a.disk)
    v.write(lbn, data.ljust(blocks * BLOCK, b'\0'))
    day, cs = now_mfs(struct.unpack_from('<H', v.home, 60)[0])
    ent = bytearray(ENTSIZE)
    ent[0:NAMELEN] = name.encode().ljust(NAMELEN)
    struct.pack_into('<HBBIIIIII', ent, 32, highest + 1, 1,
                     RFM_STMLF if text else RFM_UDF, lbn, blocks, len(data),
                     day, cs, 2 if text else 0)
    v.dir[free * ENTSIZE:(free + 1) * ENTSIZE] = ent
    v.set_freelbn(lbn + blocks)
    v.flush()
    print('%s;%d  %d blocks (%s)' % (name, highest + 1, blocks,
                                    'text' if text else 'binary'))


def cmd_get(a):
    v = Volume(a.disk)
    name, version = parse_name(a.name)
    r = v.lookup(name, version)
    if not r:
        sys.exit('%s: file not found' % a.name)
    _, e = r
    data = v.read(e['lbn'], e['alloc'])[:e['size']]
    with open(a.hostfile, 'wb') as f:
        f.write(data)
    print('%s;%d -> %s (%d bytes)' % (e['name'], e['version'], a.hostfile,
                                      len(data)))


def cmd_dir(a):
    v = Volume(a.disk)
    owner = v.home[44:56].decode().rstrip()
    print('\nDirectory DUA0:[%s]\n' % owner)
    ents = sorted((e for _, e in v.entries()),
                  key=lambda e: (e['name'], -e['version']))
    total = 0
    for e in ents:
        blocks = (e['size'] + BLOCK - 1) // BLOCK
        total += blocks
        print('%-24s%7d  %s  %-5s LBN %d' % (
            '%s;%d' % (e['name'], e['version']), blocks,
            fmt_date(e['day'], e['cs']), RFM_NAMES.get(e['rfm'], '?'),
            e['lbn']))
    print('\nTotal of %d file%s, %d block%s.  Free: %d blocks.' % (
        len(ents), '' if len(ents) == 1 else 's', total,
        '' if total == 1 else 's', v.maxblk - v.freelbn))


def cmd_delete(a):
    v = Volume(a.disk)
    name, version = parse_name(a.name)
    if not version:
        sys.exit('explicit version number required')
    r = v.lookup(name, version)
    if not r:
        sys.exit('%s: file not found' % a.name)
    i, e = r
    v.dir[i * ENTSIZE + 34] = 0
    if e['lbn'] + e['alloc'] == v.freelbn:
        v.set_freelbn(e['lbn'])
    v.flush()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('init')
    p.add_argument('disk')
    p.add_argument('--blocks', type=int, default=DEFAULT_BLOCKS)
    p.add_argument('--label', default='TRAVELLER')
    p.add_argument('--owner', default='FREDERICKS')
    p.add_argument('--year', type=int, default=1986)
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser('put')
    p.add_argument('disk')
    p.add_argument('hostfile')
    p.add_argument('name', nargs='?')
    g = p.add_mutually_exclusive_group()
    g.add_argument('--binary', action='store_true')
    g.add_argument('--text', action='store_true')
    p.set_defaults(fn=cmd_put)
    p = sub.add_parser('get')
    p.add_argument('disk')
    p.add_argument('name')
    p.add_argument('hostfile')
    p.set_defaults(fn=cmd_get)
    p = sub.add_parser('dir')
    p.add_argument('disk')
    p.set_defaults(fn=cmd_dir)
    p = sub.add_parser('delete')
    p.add_argument('disk')
    p.add_argument('name')
    p.set_defaults(fn=cmd_delete)
    a = ap.parse_args()
    a.fn(a)


if __name__ == '__main__':
    main()
