# Audio Remaster for The Curse of Monkey Island
# Copyright (C) 2026 SamuelEchoes
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.
#
# Parts of this file are a translation to Python of ScummVM code (engines/scumm/imuse_digi/dimuse_bndmgr.cpp and dimuse_codecs.cpp).
# ScummVM is the legal property of its developers, whose names are too numerous to list here. Please refer
# to the COPYRIGHT file distributed with the ScummVM source code: https://github.com/scummvm/scummvm

# Lector / escritor de los .BUN de The Curse of Monkey Island (formato LB83), portado del codigo de ScummVM
# (engines/scumm/imuse_digi/dimuse_bndmgr.cpp y dimuse_codecs.cpp).
import struct

IMA = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66,
       73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449,
       494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272,
       2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442,
       11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767]
OTHER = [
    [-1, 4],
    [-1, -1, 2, 8],
    [-1, -1, -1, -1, 1, 2, 4, 6],
    [-1] * 8 + [1, 2, 4, 6, 8, 12, 16, 32],
    [-1] * 16 + [1, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 32],
    [-1] * 32 + list(range(1, 33)),
]
BITS = []
for pos in range(89):
    put = 1
    v = ((IMA[pos] * 4) // 7) // 2
    while v:
        v //= 2
        put += 1
    BITS.append(min(max(put, 3), 8) - 1)
T2 = [0] * (89 * 64)
for n in range(64):
    for pos in range(89):
        count, put, v = 32, 0, IMA[pos]
        while count:
            if count & n:
                put += v
            count //= 2
            v //= 2
        T2[n + pos * 64] = put


def decode_block(src, channels):
    """Un bloque comprimido (codec 13 mono / 15 estereo) -> 0x2000 bytes: cabecera cruda + PCM 16 bits LE."""
    out = bytearray(0x2000)
    left = 0x1000
    first = struct.unpack_from('>H', src, 0)[0]
    p = 2
    dst = 0
    tab = [0, 0]
    word = [0, 0]
    if first:
        out[0:first] = src[p:p + first]
        dst = first
        p += first
        left -= first // 2
    else:
        for c in range(channels):
            tab[c] = src[p]
            word[c] = struct.unpack_from('>i', src, p + 5)[0]
            p += 9
    data = src[p:] + b'\0\0\0\0'
    bitoff = 0
    for ch in range(channels):
        cur, w = tab[ch], word[ch]
        dpos = dst + ch * 2
        bound = left if channels == 1 else ((left + 1) // 2 if ch == 0 else left // 2)
        step = channels * 2
        for _ in range(bound):
            nb = BITS[cur]
            rp = bitoff >> 3
            rw = (((data[rp] << 8) | data[rp + 1]) << (bitoff & 7)) & 0xFFFF
            packet = rw >> (16 - nb)
            bitoff += nb
            sign = 1 << (nb - 1)
            d = packet & (sign - 1)
            delta = (IMA[cur] >> (nb - 1)) + T2[(d << (7 - nb)) + cur * 64]
            if packet & sign:
                delta = -delta
            w += delta
            if w > 32767:
                w = 32767
            elif w < -32768:
                w = -32768
            out[dpos] = w & 0xFF
            out[dpos + 1] = (w >> 8) & 0xFF
            dpos += step
            cur += OTHER[nb - 2][d]
            if cur < 0:
                cur = 0
            elif cur > 88:
                cur = 88
    return bytes(out)


class Bun:
    def __init__(self, path):
        self.path = path
        self.f = open(path, 'rb')
        tag, off, n = struct.unpack('>4sII', self.f.read(12))
        assert tag == b'LB83', tag
        self.dir_off = off
        self.f.seek(off)
        self.entries = []
        for _ in range(n):
            raw = self.f.read(20)
            name = raw[:8].rstrip(b'\0').decode('latin1') + '.' + raw[8:12].rstrip(b'\0').decode('latin1')
            o, s = struct.unpack('>II', raw[12:20])
            self.entries.append({'name': name, 'raw': raw[:12], 'offset': o, 'size': s})

    def find(self, name):
        for e in self.entries:
            if e['name'].lower() == name.lower():
                return e
        raise KeyError(name)

    def raw(self, e):
        self.f.seek(e['offset'])
        return self.f.read(e['size'])

    def comp_table(self, e):
        self.f.seek(e['offset'])
        tag, n, _, last = struct.unpack('>4sIII', self.f.read(16))
        if tag == b'iMUS':
            return None
        assert tag == b'COMP', tag
        items = [struct.unpack('>IIII', self.f.read(16))[:3] for _ in range(n)]
        return items, last

    def decode(self, e, max_blocks=None):
        """Devuelve el archivo descomprimido entero (iMUS + MAP + DATA + PCM LE)."""
        ct = self.comp_table(e)
        if ct is None:
            return self.raw(e)
        items, last = ct
        if max_blocks:
            items = items[:max_blocks]
        out = []
        for i, (off, size, codec) in enumerate(items):
            self.f.seek(e['offset'] + off)
            src = self.f.read(size) + b'\0'
            if codec == 0:
                blk = src[:size]
            elif codec in (13, 15):
                blk = decode_block(src, 1 if codec == 13 else 2)
            else:
                raise ValueError('codec %d' % codec)
            out.append(blk)
        data = b''.join(out)
        if not max_blocks:
            data = data[:(len(items) - 1) * 0x2000 + last]
        return data


def parse_imus(data):
    """Cabecera iMUS -> dict con formato, regiones, saltos, textos y posicion del audio."""
    assert data[:4] == b'iMUS', data[:4]
    assert data[8:12] == b'MAP ', data[8:12]
    map_size = struct.unpack_from('>I', data, 12)[0]
    p, end = 16, 16 + map_size
    info = {'regions': [], 'jumps': [], 'texts': [], 'syncs': [], 'stops': [], 'chunks': []}
    while p < end:
        tag = data[p:p + 4]
        size = struct.unpack_from('>I', data, p + 4)[0]
        body = data[p + 8:p + 8 + size]
        info['chunks'].append((tag.decode('latin1'), p, size))
        if tag == b'FRMT':
            off, endian, bits, rate, ch = struct.unpack_from('>5I', body, 0)
            info.update(frmt_off=off, endian=endian, bits=bits, rate=rate, channels=ch)
        elif tag == b'REGN':
            info['regions'].append(struct.unpack_from('>2I', body, 0))
        elif tag == b'JUMP':
            info['jumps'].append(struct.unpack_from('>4I', body, 0))
        elif tag == b'TEXT':
            info['texts'].append((struct.unpack_from('>I', body, 0)[0], body[4:].rstrip(b'\0').decode('latin1')))
        elif tag == b'SYNC':
            info['syncs'].append(size)
        elif tag == b'STOP':
            info['stops'].append(struct.unpack_from('>I', body, 0)[0])
        p += 8 + size
    assert data[p:p + 4] == b'DATA', data[p:p + 4]
    info['data_size'] = struct.unpack_from('>I', data, p + 4)[0]
    info['data_off'] = p + 8
    return info


if __name__ == '__main__':
    import sys
    b = Bun(sys.argv[1])
    print(len(b.entries), 'entradas')
    for e in b.entries:
        ct = b.comp_table(e)
        blocks = len(ct[0]) if ct else 0
        try:
            hdr = parse_imus(b.decode(e, max_blocks=1) if ct else b.raw(e)[:0x2000])
            secs = hdr['data_size'] / (hdr['rate'] * hdr['channels'] * hdr['bits'] / 8)
            extra = '%6.1f s  %d Hz %d canal(es) %d bits  regiones=%d saltos=%d' % (
                secs, hdr['rate'], hdr['channels'], hdr['bits'], len(hdr['regions']), len(hdr['jumps']))
        except Exception as ex:
            extra = 'ERROR cabecera: %r' % ex
        print('%-14s %9d bytes  %s' % (e['name'], e['size'], extra))
