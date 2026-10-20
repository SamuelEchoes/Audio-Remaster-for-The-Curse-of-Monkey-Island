# Audio Remaster for The Curse of Monkey Island
# Copyright (C) 2026 SamuelEchoes
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.

# Arma el .ogg (44,1 kHz) que reemplaza el audio de un video .SAN. Version general de build_opening3.py.
#   - Donde suena un tema del disco: musica del disco + lo que habia encima (voces y efectos) rescatado de la resta.
#   - Voces/efectos rescatados y todo el resto del video: quitaclics + de-esser + agudos regenerados a la mitad
#     (metodo "5b" elegido por el usuario para voces).
# Uso: build_video.py <audio_del_video.wav 22050> <salida.ogg|.flac> [<tema.flac>@<segundo del video donde empieza>] ...
#      Opciones: --solo-resto (sin la musica del disco, para escuchar que se rescata)
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import soundfile as sf
from scipy import signal
from scipy.signal import medfilt
from scipy.ndimage import uniform_filter, uniform_filter1d, maximum_filter1d, minimum_filter1d
import enhance, deess

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 22050
AIR_VOZ = 0.5
PROF = json.load(open(os.path.join(HERE, 'perfil_mejora.json')))
bp = signal.butter(4, [150, 6000], btype='band', fs=SR, output='sos')


def win_corr(a, b, w=SR, hop=SR // 2):
    return np.array([np.corrcoef(a[x:x + w], b[x:x + w])[0, 1] if np.std(a[x:x + w]) > 1e-6 and np.std(b[x:x + w]) > 1e-6 else 0.0
                     for x in range(0, len(a) - w + 1, hop)])


def span_of(cc, thr, hop=SR // 2, w=SR):
    """Del primer al ultimo segundo donde el tema se reconoce. El desfase ya es conocido y unico, asi que los tramos
    intermedios con parecido bajo son la misma musica tapada por voces o efectos, no otra cosa."""
    good = np.where(cc >= thr)[0]
    if len(good) < 2:
        return None
    return int(good[0]) * hop, int(good[-1]) * hop + w


def declick(x):
    y = x.copy(); total = 0
    for ch in range(x.shape[1]):
        v = x[:, ch]
        dev = np.abs(v - medfilt(v, 9))
        loc = np.sqrt(uniform_filter1d(dev.astype(np.float64) ** 2, size=2001)) + 1e-5
        idx = np.where(dev > 5 * loc)[0]
        if not len(idx):
            continue
        cuts = np.where(np.diff(idx) > 3)[0]
        starts = np.concatenate([[idx[0]], idx[cuts + 1]]); ends = np.concatenate([idx[cuts], [idx[-1]]])
        for s, e in zip(starts, ends):
            if e - s + 1 > 6 or s < 2 or e > len(v) - 3:
                continue
            a, b = s - 1, e + 1
            y[a:b + 1, ch] = np.linspace(v[a], v[b], b - a + 1); total += 1
    return y, total


def denoise22(x, strength):
    f, tt, Z = signal.stft(x, fs=SR, nperseg=1024, noverlap=768)
    mag = np.abs(Z)
    noise = np.percentile(mag, 20, axis=1, keepdims=True) * strength
    gain = uniform_filter(np.clip((mag ** 2 - noise ** 2) / (mag ** 2 + 1e-12), 0.03, 1.0), size=(3, 5))
    y = signal.istft(Z * gain, fs=SR, nperseg=1024, noverlap=768)[1][:len(x)]
    return np.pad(y, (0, len(x) - len(y))).astype(np.float32)


def voz(x22, clean=1.0):
    """Metodo 5b sobre audio a 22.050 (n, 2): de-esser normal + agudos regenerados a la mitad -> 44.100."""
    y = np.stack([deess.deess(x22[:, ch], strength=1.0)[0] for ch in range(x22.shape[1])], axis=1)
    return enhance.enhance(y, PROF, clean=clean, air=AIR_VOZ)


def refine_offset(gm, hm, off0, search=0.6):
    """Ajusta el desfase (muestra del video donde cae el comienzo del tema) alrededor de off0."""
    g0, h0 = max(off0, 0), max(-off0, 0)
    N = min(len(gm) - g0, len(hm) - h0)
    L = int(min(30 * SR, N * 0.6))
    a = (N - L) // 2
    frag = hm[h0 + a:h0 + a + L]
    S = int(search * SR)
    lo = max(g0 + a - S, 0)
    seg = gm[lo:g0 + a + L + S]
    c = np.abs(signal.fftconvolve(seg, frag[::-1], mode='valid'))
    k = int(np.argmax(c))
    return off0 + (lo + k) - (g0 + a)


def build(wav, dst, specs, solo_resto=False, log=print, quitaclics=False):
    game, sr = sf.read(wav, dtype='float32', always_2d=True)
    assert sr == SR
    if game.shape[1] == 1:
        game = np.repeat(game, 2, axis=1)
    gd, nclk = declick(game) if quitaclics else (game, 0)
    out = voz(gd)                                           # base: todo el video con el metodo de voces
    n44 = len(out)
    info = {'dura': round(len(game) / SR, 1), 'clics': nclk, 'temas': []}
    Gm = signal.sosfiltfilt(bp, gd.mean(axis=1))
    for flac, start in specs:
        hq, hsr = sf.read(flac, dtype='float32', always_2d=True)
        if hsr != 44100:
            hq = signal.resample_poly(hq, 44100, hsr, axis=0).astype(np.float32)
        h22 = signal.resample_poly(hq, 1, 2, axis=0).astype(np.float32)
        Hm = signal.sosfiltfilt(bp, h22.mean(axis=1))
        off = refine_offset(Gm, Hm, int(round(start * SR)))
        g0, h0 = max(off, 0), max(-off, 0)
        N = min(len(gd) - g0, len(h22) - h0)
        if N < 3 * SR:
            continue
        G, H = gd[g0:g0 + N], h22[h0:h0 + N]
        Gb = Gm[g0:g0 + N]
        NF = 4096

        def filt(a, b):
            m = np.zeros_like(G)
            for ch in (0, 1):
                _, pxx = signal.welch(H[a:b, ch], fs=SR, nperseg=min(NF, b - a))
                _, pxy = signal.csd(H[a:b, ch], G[a:b, ch], fs=SR, nperseg=min(NF, b - a))
                ir = np.fft.irfft(pxy / (pxx + 1e-12)); L = len(ir)
                fir = np.roll(ir, L // 2) * np.hanning(L)
                m[:, ch] = signal.fftconvolve(H[:, ch], fir, mode='full')[L // 2:L // 2 + N]
            return m
        m = filt(0, N)
        cc = win_corr(Gb, signal.sosfiltfilt(bp, m.mean(axis=1)))
        sp = span_of(cc, 0.25)
        fijo = False
        if sp is None:
            sp, fijo = (0, N), True                          # tapado por voces: se usa todo el solape
        a, b = sp
        m = filt(a, b)
        mb = signal.sosfiltfilt(bp, m.mean(axis=1))
        cc = win_corr(Gb, mb)
        med = float(np.median(cc[a // (SR // 2):max(a // (SR // 2) + 1, (b - SR) // (SR // 2))]))
        if med < 0.3:
            fijo = True
        # volumen con que la musica esta mezclada en el video: valor global del tramo y, alrededor de el, un ajuste
        # lento (ventanas de 4 s). La proyeccion no se sesga con voces encima (no se parecen a la musica), solo baila.
        cg = float(np.dot(Gb[a:b], mb[a:b]) / (np.dot(mb[a:b], mb[a:b]) + 1e-9))
        cg = float(np.clip(cg, 0.3, 1.8))
        if fijo:
            c = np.full(N, cg, dtype=np.float32)
        else:
            num = uniform_filter1d(Gb * mb, size=4 * SR); den = uniform_filter1d(mb * mb, size=4 * SR) + 1e-9
            c = np.clip(uniform_filter1d(num / den, size=2 * SR), 0.6 * cg, 1.5 * cg).astype(np.float32)
        resid = (G - m * c[:, None])[a:b]
        ps = np.array([10 * np.log10(np.mean(resid[x:x + SR] ** 2) / (np.mean(G[a + x:a + x + SR] ** 2) + 1e-12) + 1e-12)
                       for x in range(0, b - a - SR, SR)])
        if quitaclics:
            resid, _ = declick(resid)
        resid = np.stack([denoise22(resid[:, ch], 1.8) for ch in (0, 1)], axis=1)
        R44 = voz(resid, clean=0.0)
        gains = np.sqrt((m[a:b] ** 2).mean(axis=0) / ((H[a:b] ** 2).mean(axis=0) + 1e-12)).astype(np.float32)
        M = hq[2 * (h0 + a):2 * (h0 + b)] * gains
        k = min(len(M), len(R44), n44 - 2 * (g0 + a))
        mix = R44[:k].copy() if solo_resto else M[:k] * np.repeat(c[a:b], 2)[:k, None] + R44[:k]
        s44 = 2 * (g0 + a)
        old = out[s44:s44 + k]
        fz = min(int(0.5 * 44100), k // 4)
        ramp = np.linspace(0, 1, fz, dtype=np.float32)[:, None]
        mix[:fz] = mix[:fz] * ramp + old[:fz] * (1 - ramp)
        mix[-fz:] = mix[-fz:] * ramp[::-1] + old[-fz:] * (1 - ramp[::-1])
        out[s44:s44 + k] = mix
        t = {'tema': os.path.basename(flac), 'video_desde': round((g0 + a) / SR, 2), 'video_hasta': round((g0 + b) / SR, 2),
             'disco_desde': round((h0 + a) / SR, 2), 'parecido_mediano': round(med, 2), 'modo': 'fijo' if fijo else 'normal',
             'resto_limpio_dB': round(float(np.percentile(ps, 10)), 1) if len(ps) else None,
             'resto_mediana_dB': round(float(np.median(ps)), 1) if len(ps) else None}
        info['temas'].append(t)
        log('   %s: video %.1f-%.1f s (disco desde %.1f s) | parecido %.2f (%s) | resto: %.1f dB en lo mas limpio, mediana %.1f dB' % (
            t['tema'][:28], t['video_desde'], t['video_hasta'], t['disco_desde'], med, t['modo'], t['resto_limpio_dB'] or 0, t['resto_mediana_dB'] or 0))
    env = maximum_filter1d(np.abs(out).max(axis=1), size=441)
    lg = np.minimum(1.0, 0.97 / np.maximum(env, 1e-9))
    lg = uniform_filter1d(minimum_filter1d(lg, size=441), size=441).astype(np.float32)
    out = np.clip(out * lg[:, None], -1, 1)
    assert np.isfinite(out).all()
    info['limitador_pct'] = round(100 * float((lg < 0.999).mean()), 2)
    fmt = dict(format='FLAC', subtype='PCM_16') if dst.lower().endswith('.flac') else dict(format='OGG', subtype='VORBIS', compression_level=0.1)
    with sf.SoundFile(dst + '.tmp', 'w', samplerate=44100, channels=2, **fmt) as fo:
        for x in range(0, len(out), 44100 * 5):
            fo.write(out[x:x + 44100 * 5])
    os.replace(dst + '.tmp', dst)
    return info


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    specs = [(a.rsplit('@', 1)[0], float(a.rsplit('@', 1)[1])) for a in args[2:]]
    print(json.dumps(build(args[0], args[1], specs, solo_resto='--solo-resto' in sys.argv), indent=1))
