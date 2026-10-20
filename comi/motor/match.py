# Audio Remaster for The Curse of Monkey Island
# Copyright (C) 2026 SamuelEchoes
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.

# Busca cada region de un tema del juego dentro de uno o varios temas del disco (correlacion cruzada).
# Uso: match.py <MUSDISK.BUN> <entrada> <flac> [<flac> ...]
import sys, pickle, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import soundfile as sf
from scipy import signal
import bun

RATE = 22050


def load_game(bunpath, name):
    cache = os.path.join(os.path.dirname(__file__), 'dec_' + name.replace('~', '_') + '.pkl')
    if os.path.exists(cache):
        return pickle.load(open(cache, 'rb'))
    b = bun.Bun(bunpath)
    data = b.decode(b.find(name))
    info = bun.parse_imus(data)
    pcm = np.frombuffer(data, dtype='<i2', count=info['data_size'] // 2, offset=info['data_off'])
    pcm = pcm.reshape(-1, info['channels']).astype(np.float32) / 32768.0
    pickle.dump((info, pcm), open(cache, 'wb'))
    return info, pcm


def load_ost(path):
    x, sr = sf.read(path, dtype='float32', always_2d=True)
    y = signal.resample_poly(x, RATE, sr, axis=0).astype(np.float32)   # 44100 -> 22050
    return x, sr, y


def band(m):
    # la comparacion se hace en mono y entre 150 Hz y 6 kHz (donde el codec del juego mete menos ruido)
    sos = signal.butter(4, [150, 6000], btype='band', fs=RATE, output='sos')
    return signal.sosfiltfilt(sos, m).astype(np.float32)


def best(frag, ref, ref_energy_cs):
    """Posicion (en muestras de 22050) donde frag coincide mejor dentro de ref, y coeficiente -1..1."""
    if len(frag) > len(ref):
        return None, 0.0
    c = signal.fftconvolve(ref, frag[::-1], mode='valid')
    n = len(frag)
    e = ref_energy_cs[n:] - ref_energy_cs[:-n]
    norm = np.sqrt(np.maximum(e, 1e-12) * float(np.dot(frag, frag)) + 1e-20)
    r = c / norm[:len(c)]
    k = int(np.argmax(r))
    return k, float(r[k])


if __name__ == '__main__':
    bunpath, name, flacs = sys.argv[1], sys.argv[2], sys.argv[3:]
    info, pcm = load_game(bunpath, name)
    bps = info['channels'] * info['bits'] // 8
    print('%s: %.1f s, %d regiones, %d saltos, datos desde %d' % (
        name, len(pcm) / RATE, len(info['regions']), len(info['jumps']), info['frmt_off']))
    g = band(pcm.mean(axis=1))
    refs = []
    for f in flacs:
        x, sr, y = load_ost(f)
        r = band(y.mean(axis=1))
        refs.append((os.path.basename(f), r, np.concatenate([[0.0], np.cumsum(r.astype(np.float64) ** 2)])))
        print('  disco: %s  %.1f s  %d Hz' % (os.path.basename(f), len(x) / sr, sr))
    base = info['frmt_off']
    rows = []
    for i, (off, length) in enumerate(info['regions']):
        a = (off - base) // bps
        n = length // bps
        frag = g[a:a + n]
        res = []
        for nm, r, cs in refs:
            k, coef = best(frag, r, cs)
            res.append((coef, nm, k))
        coef, nm, k = max(res)
        rows.append((i, a, n, nm, k, coef))
    good = sum(n for (_, _, n, _, _, c) in rows if c >= 0.9)
    tot = sum(n for (_, _, n, _, _, c) in rows)
    print('cobertura con coincidencia >= 0.90: %.1f %% del audio (%d de %d regiones)' % (
        100.0 * good / tot, sum(1 for r in rows if r[5] >= 0.9), len(rows)))
    show = rows if len(rows) <= 12 else rows[:8] + rows[-4:]
    for i, a, n, nm, k, coef in show:
        print('  region %2d  juego %7.2f s  dura %6.2f s  ->  %s @ %7.2f s  coef %.3f' % (
            i, a / RATE, n / RATE, nm[:2], (k or 0) / RATE, coef))
    pickle.dump((info, rows), open(os.path.join(os.path.dirname(__file__), 'match_' + name.replace('~', '_') + '.pkl'), 'wb'))
