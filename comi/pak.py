# Audio Remaster for The Curse of Monkey Island
# Copyright (C) 2026 SamuelEchoes
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.

"""Contenedor .pak: un .BUN remasterizado (entradas iMUS sin comprimir) guardado con el audio en FLAC.

La reconstruccion es exacta, byte a byte: cada entrada se guarda como cabecera cruda + FLAC del PCM de 16 bits + cola
cruda, y el .BUN se rearma con el mismo orden y la misma tabla. El indice lleva el SHA-256 del .BUN original armado.
"""
import hashlib
import io
import json
import os
import struct

import numpy as np
import soundfile as sf

MAGIC = b'CMIPAK1\n'


def _parse_data(blob):
    """(posicion del PCM, tamano del PCM, canales) de una entrada iMUS sin comprimir, o None si no lo es."""
    if blob[:4] != b'iMUS' or blob[8:12] != b'MAP ':
        return None
    map_size = struct.unpack_from('>I', blob, 12)[0]
    p, end, ch, bits = 16, 16 + map_size, None, None
    while p < end:
        tag = blob[p:p + 4]
        size = struct.unpack_from('>I', blob, p + 4)[0]
        if tag == b'FRMT':
            _, _, bits, _, ch = struct.unpack_from('>5I', blob, p + 8)
        p += 8 + size
    if blob[p:p + 4] != b'DATA' or bits != 16 or ch not in (1, 2):
        return None
    return p + 8, struct.unpack_from('>I', blob, p + 4)[0], ch


def read_dir(f):
    tag, off, n = struct.unpack('>4sII', f.read(12))
    if tag != b'LB83':
        raise ValueError('no es un .BUN (LB83)')
    f.seek(off)
    out = []
    for _ in range(n):
        raw = f.read(20)
        o, s = struct.unpack('>II', raw[12:20])
        out.append((raw[:12], o, s))
    return out


def sha256_file(path, progress=None, chunk=4 << 20):
    h = hashlib.sha256()
    total = os.path.getsize(path)
    done = 0
    with open(path, 'rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
            done += len(b)
            if progress:
                progress(done, total)
    return h.hexdigest()


def pack(bun_path, pak_path, level=5):
    entries = []
    with open(bun_path, 'rb') as f, open(pak_path + '.tmp', 'wb') as o:
        o.write(MAGIC + b'\0' * 8)
        for raw12, off, size in read_dir(f):
            f.seek(off)
            blob = f.read(size)
            d = _parse_data(blob)
            e = {'raw': raw12.hex(), 'pos': o.tell(), 'size': size}
            frames = 0
            if d:
                data_off, data_size, ch = d
                frames = data_size // (2 * ch)
            if d and frames > 0:
                pcm = np.frombuffer(blob, dtype='<i2', count=frames * ch, offset=data_off).reshape(-1, ch)
                bio = io.BytesIO()
                sf.write(bio, pcm, 44100, format='FLAC', subtype='PCM_16', compression_level=level / 8.0)
                fl = bio.getvalue()
                tail = blob[data_off + frames * 2 * ch:]
                o.write(blob[:data_off]); o.write(fl); o.write(tail)
                e.update(kind='flac', hdr=data_off, flac=len(fl), tail=len(tail), ch=ch, frames=frames)
            else:
                o.write(blob)
                e.update(kind='raw')
            entries.append(e)
        idx_pos = o.tell()
        index = {'bun': os.path.basename(bun_path), 'bun_size': os.path.getsize(bun_path),
                 'bun_sha256': sha256_file(bun_path), 'entries': entries}
        o.write(json.dumps(index, separators=(',', ':')).encode('utf-8'))
        o.seek(len(MAGIC))
        o.write(struct.pack('>Q', idx_pos))
    os.replace(pak_path + '.tmp', pak_path)
    return index


def read_index(pak_path):
    with open(pak_path, 'rb') as f:
        if f.read(len(MAGIC)) != MAGIC:
            raise ValueError('no es un .pak valido: ' + pak_path)
        idx_pos = struct.unpack('>Q', f.read(8))[0]
        f.seek(idx_pos)
        return json.loads(f.read().decode('utf-8'))


def unpack(pak_path, bun_path, progress=None, cancel=None):
    """Rearma el .BUN. Devuelve el SHA-256 de lo escrito (se calcula mientras se escribe)."""
    index = read_index(pak_path)
    total = index['bun_size']
    h = hashlib.sha256()
    table = []
    with open(pak_path, 'rb') as f, open(bun_path, 'wb') as o:
        head = b'LB83' + struct.pack('>II', 0, len(index['entries']))
        o.write(head)
        pos = len(head)
        chunks = [head]
        for e in index['entries']:
            if cancel and cancel():
                raise InterruptedError('cancelado')
            f.seek(e['pos'])
            if e['kind'] == 'flac':
                hdr = f.read(e['hdr'])
                fl = f.read(e['flac'])
                tail = f.read(e['tail'])
                pcm, _ = sf.read(io.BytesIO(fl), dtype='int16', always_2d=True)
                if len(pcm) != e['frames'] or pcm.shape[1] != e['ch']:
                    raise ValueError('audio danado en el paquete')
                blob = hdr + pcm.astype('<i2').tobytes() + tail
            else:
                blob = f.read(e['size'])
            if len(blob) != e['size']:
                raise ValueError('entrada con tamano inesperado')
            table.append((bytes.fromhex(e['raw']), pos, len(blob)))
            o.write(blob)
            chunks.append(blob)
            pos += len(blob)
            if progress:
                progress(pos, total)
        diroff = pos
        tab = b''.join(raw + struct.pack('>II', off, size) for raw, off, size in table)
        o.write(tab)
        o.seek(4)
        o.write(struct.pack('>I', diroff))
    # el hash se calcula sobre el archivo final (la cabecera se reescribio)
    return sha256_file(bun_path)


if __name__ == '__main__':
    import sys
    import time
    if sys.argv[1] == 'pack':
        t = time.time()
        idx = pack(sys.argv[2], sys.argv[3])
        print('%s -> %s: %d entradas, %.0f MB -> %.0f MB (%.0f %%), %.0f s' % (
            idx['bun'], os.path.basename(sys.argv[3]), len(idx['entries']), idx['bun_size'] / 1e6,
            os.path.getsize(sys.argv[3]) / 1e6, 100.0 * os.path.getsize(sys.argv[3]) / idx['bun_size'], time.time() - t), flush=True)
    elif sys.argv[1] == 'test':
        t = time.time()
        got = unpack(sys.argv[2], sys.argv[3])
        want = read_index(sys.argv[2])['bun_sha256']
        print('%s: %s (%.0f s)' % (os.path.basename(sys.argv[2]), 'IDENTICO' if got == want else 'DISTINTO', time.time() - t), flush=True)
        os.remove(sys.argv[3])
