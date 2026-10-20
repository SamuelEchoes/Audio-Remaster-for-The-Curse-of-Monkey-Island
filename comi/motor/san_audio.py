# Audio Remaster for The Curse of Monkey Island
# Copyright (C) 2026 SamuelEchoes
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.
#
# Parts of this file are a translation to Python of ScummVM code (SmushPlayer::handleIACT in engines/scumm/smush/smush_player.cpp).
# ScummVM is the legal property of its developers, whose names are too numerous to list here. Please refer
# to the COPYRIGHT file distributed with the ScummVM source code: https://github.com/scummvm/scummvm

# Extrae el audio embebido (trozos IACT) de un video .SAN de The Curse of Monkey Island.
# Portado de SmushPlayer::handleIACT de ScummVM. Salida: 22050 Hz, estereo, 16 bits.
import struct, sys
import numpy as np


def iact_stream(path):
    d = open(path, 'rb').read()
    assert d[:4] == b'ANIM'
    pos, frames, parts, first_audio_frame = 8, 0, [], None
    while pos < len(d) - 8:
        tag = d[pos:pos + 4]
        sz = struct.unpack_from('>I', d, pos + 4)[0]
        if tag == b'FRME':
            frames += 1
            q, e = pos + 8, pos + 8 + sz
            while q < e - 8:
                t = d[q:q + 4]
                s = struct.unpack_from('>I', d, q + 4)[0]
                if t == b'IACT':
                    code, flags = struct.unpack_from('<HH', d, q + 8)
                    if code == 8 and flags == 46:
                        if first_audio_frame is None:
                            first_audio_frame = frames
                        parts.append(d[q + 8 + 18:q + 8 + s])
                q += 8 + s + (s & 1)
        pos += 8 + sz + (sz & 1)
    return b''.join(parts), frames, first_audio_frame


def decode(stream):
    out = []
    p, n = 0, len(stream)
    while p + 2 <= n:
        ln = struct.unpack_from('>H', stream, p)[0]
        pk = stream[p + 2:p + 2 + ln]
        p += 2 + ln
        if len(pk) < ln or ln < 1:
            break
        v1 = pk[0] & 0x0F          # canal derecho
        v2 = pk[0] >> 4            # canal izquierdo
        body = pk[1:]
        if len(body) == 2048 and 0x80 not in body:
            a = np.frombuffer(body, dtype=np.int8).astype(np.int32).reshape(-1, 2)
            blk = np.empty((1024, 2), dtype=np.int16)
            blk[:, 0] = (a[:, 0] << v2).astype(np.int16)
            blk[:, 1] = (a[:, 1] << v1).astype(np.int16)
        else:
            blk = np.zeros((1024, 2), dtype=np.int16)
            q = 0
            for i in range(1024):
                for ch, sh in ((0, v2), (1, v1)):
                    if q >= len(body):
                        break
                    v = body[q]
                    q += 1
                    if v == 0x80:
                        val = struct.unpack_from('>h', body, q)[0]
                        q += 2
                    else:
                        val = ((v - 256 if v > 127 else v) << sh)
                        val = (val + 32768) % 65536 - 32768
                    blk[i, ch] = val
        out.append(blk)
    return np.concatenate(out)


if __name__ == '__main__':
    import soundfile as sf
    stream, frames, first = iact_stream(sys.argv[1])
    pcm = decode(stream)
    print('cuadros de video: %d | primer cuadro con audio: %s | audio: %d muestras = %.2f s | video a 12 fps = %.2f s' % (
        frames, first, len(pcm), len(pcm) / 22050.0, frames / 12.0))
    sf.write(sys.argv[2], pcm, 22050, subtype='PCM_16')
