# Audio Remaster for The Curse of Monkey Island
# Copyright (C) 2026 SamuelEchoes
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.

# Arma un .BUN nuevo reemplazando, en las entradas indicadas, el audio de las regiones que coinciden con un tema
# del disco. Las entradas tocadas se guardan SIN comprimir (iMUS directo, que ScummVM acepta); el resto se copia tal cual.
# La cabecera de cada entrada (regiones, saltos, marcas) no cambia: solo cambian las muestras, a 22.050 Hz.
# Uso: build_bun.py <origen.BUN> <destino.BUN> <entrada>=<tema.flac> [<entrada>=<tema.flac> ...]
import sys, os, struct, pickle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import soundfile as sf
from scipy import signal
import bun
from match import band, best, RATE

HERE = os.path.dirname(os.path.abspath(__file__))
BOOST_DB = 0.0    # con --volumen X sube X dB las entradas reemplazadas (solo con --44)
OUT44 = False     # con --44 las entradas reemplazadas salen a 44.100 Hz (requiere dimuse_sample_rate=44100 en ScummVM)


def decode_entry(b, name):
    cache = os.path.join(HERE, 'raw_' + name.replace('~', '_') + '.bin')
    if os.path.exists(cache):
        return open(cache, 'rb').read()
    data = b.decode(b.find(name))
    open(cache, 'wb').write(data)
    return data


def exact_offset(g44, h44, a44, b44, n44):
    """Retardo fino: devuelve d tal que juego[a44+t] ~ disco[b44+d+t]. Sale del pico de la respuesta al impulso
    del filtro disco->juego, que sirve aunque las dos versiones tengan distinta ecualizacion."""
    G = g44[a44:a44 + n44]
    H = h44[b44:b44 + n44]
    nf = 8192
    _, pxx = signal.welch(H, fs=44100, nperseg=nf)
    _, pxy = signal.csd(H, G, fs=44100, nperseg=nf)
    ir = np.fft.irfft(pxy / (pxx + 1e-12))
    nf = len(ir)                 # en tramos cortos welch achica el cuadro
    k = int(np.argmax(np.abs(ir)))
    idx = np.arange(k - 200, k + 201)
    w = ir[idx % nf] ** 2
    c = float((idx * w).sum() / w.sum())
    if c > nf // 2:
        c -= nf
    return -int(round(c)), float(np.sqrt(w.sum()))


def coherence(x, y):
    n = min(len(x), len(y))
    if n < 8192:
        return None
    f, c = signal.coherence(x[:n], y[:n], fs=RATE, nperseg=2048)
    return float(c[(f > 200) & (f < 4000)].mean())


def rebuild(data, flac, name):
    info = bun.parse_imus(data)
    assert info['rate'] == RATE and info['bits'] == 16 and info['channels'] == 2, info
    bps = 4
    base = info['frmt_off']
    assert base == info['data_off'], (base, info['data_off'])
    total = info['data_size'] // bps
    pcm = np.frombuffer(data, dtype='<i2', count=total * 2, offset=base).reshape(-1, 2).astype(np.float32) / 32768.0
    hq, sr = sf.read(flac, dtype='float32', always_2d=True)
    assert sr == 44100
    h22 = signal.resample_poly(hq, 1, 2, axis=0).astype(np.float32)
    gm, hm = band(pcm.mean(axis=1)), band(h22.mean(axis=1))
    cs = np.concatenate([[0.0], np.cumsum(hm.astype(np.float64) ** 2)])
    # 1) ubicar cada region
    regs = []
    for i, (off, length) in enumerate(info['regions']):
        a, n = (off - base) // bps, length // bps
        k, coef = best(gm[a:a + n], hm, cs)
        k2, coef2 = best(-gm[a:a + n], hm, cs)        # el disco puede venir con la polaridad invertida
        sign = 1.0
        if coef2 > coef and coef2 >= 0.9:
            k, coef, sign = k2, coef2, -1.0
        coh = coherence(pcm[a:a + n].mean(axis=1), h22[k:k + n].mean(axis=1)) if k is not None else None
        ok = k is not None and (coef >= 0.9 or (coef >= 0.4 and coh is not None and coh >= 0.9))
        regs.append({'i': i, 'a': a, 'n': n, 'k': k, 'coef': coef, 'coh': coh, 'ok': ok, 'sign': sign})
    # 2) agrupar regiones aceptadas y seguidas con el mismo desfase
    runs = []
    for r in regs:
        if not r['ok']:
            continue
        d = r['k'] - r['a']
        if runs and runs[-1]['end'] == r['a'] and abs(runs[-1]['d'] - d) <= 2 and runs[-1]['sign'] == r['sign']:
            runs[-1]['end'] = r['a'] + r['n']
            runs[-1]['regs'].append(r['i'])
        else:
            runs.append({'a': r['a'], 'end': r['a'] + r['n'], 'd': d, 'regs': [r['i']], 'sign': r['sign']})
    changed = True
    while changed:
        changed = False
        for r in regs:
            if r['ok'] or r['n'] < 8192:
                continue
            for run in runs:
                if r['a'] == run['end'] or r['a'] + r['n'] == run['a']:
                    k = r['a'] + run['d']
                    if k < 0 or k + r['n'] > len(h22):
                        continue
                    coh = coherence(pcm[r['a']:r['a'] + r['n']].mean(axis=1), h22[k:k + r['n']].mean(axis=1))
                    if coh is not None and coh >= 0.9:
                        r['ok'], r['coh'] = True, coh
                        run['a'], run['end'] = min(run['a'], r['a']), max(run['end'], r['a'] + r['n'])
                        run['regs'] = sorted(run['regs'] + [r['i']])
                        changed = True
                        break
    # regiones mas largas que el tema del disco: se busca el tema entero dentro de la region y se reemplaza esa parte
    csg = np.concatenate([[0.0], np.cumsum(gm.astype(np.float64) ** 2)])
    for r in regs:
        if r['ok'] or r['k'] is not None or r['n'] <= len(hm):
            continue
        m = len(hm) - 2 * RATE // 10                       # se deja 0,1 s de margen en cada punta del disco
        ref = hm[RATE // 10:RATE // 10 + m]
        sub = gm[r['a']:r['a'] + r['n']]
        c2 = np.concatenate([[0.0], np.cumsum(sub.astype(np.float64) ** 2)])
        pos, coef = best(ref, sub, c2)
        r['coef'] = coef
        if coef >= 0.9:
            a2 = r['a'] + pos
            runs.append({'a': a2, 'end': a2 + m, 'd': RATE // 10 - a2, 'regs': [r['i']], 'sign': 1.0})
            r['ok'] = True
            r['part'] = m
    # regiones rechazadas enteras pero que coinciden EN PARTE con el disco (una sola region larga donde el disco cubre
    # un pedazo): se ubica el desfase con tres muestras de la region; si dos coinciden, el tramo se reemplaza y despues
    # el control local (cada 0,5 s) deja con el audio original lo que no sea la misma musica.
    for r in regs:
        if r['ok'] or r['n'] < 4 * RATE:
            continue
        W = int(min(6 * RATE, r['n'] // 3))
        offs = []
        for frac in (0.15, 0.5, 0.85):
            pa = r['a'] + int(frac * (r['n'] - W))
            if W > len(hm):
                break
            k, coef = best(gm[pa:pa + W], hm, cs)
            if k is not None and coef >= 0.9:
                offs.append(k - pa)
        d = next((o for o in offs if sum(1 for q in offs if abs(q - o) <= 3) >= 2), None)
        if d is None:
            continue
        a2, e2 = max(r['a'], -d), min(r['a'] + r['n'], len(h22) - d)
        if e2 - a2 >= 3 * RATE:
            runs.append({'a': a2, 'end': e2, 'd': d, 'regs': [r['i']], 'sign': 1.0, 'local': True})
            r['ok'] = True
    runs.sort(key=lambda x: x['a'])
    # 3) reemplazar cada tramo
    g44 = signal.resample_poly(pcm, 2, 1, axis=0).mean(axis=1).astype(np.float32)
    h44m = hq.mean(axis=1)
    out = pcm.copy()
    out44 = signal.resample_poly(pcm, 2, 1, axis=0).astype(np.float32) if OUT44 else None   # lo que no se reemplaza va subido a 44,1k
    rep = 0
    for run in runs:
        a, n = run['a'], run['end'] - run['a']
        b44 = 2 * (a + run['d'])
        m44 = min(2 * n, 44100 * 40)
        d, peak = exact_offset(g44, h44m, 2 * a, b44, m44)
        s = b44 + d                                   # muestra del disco (44,1k) que corresponde a juego[a]
        pre = 64                                      # margen para que el filtro de la conversion no ensucie el borde
        seg = hq[max(s - 2 * pre, 0):s + 2 * (n + pre)]
        new = signal.resample_poly(seg, 1, 2, axis=0).astype(np.float32)
        lead = (s - max(s - 2 * pre, 0)) // 2
        new = new[lead:lead + n]
        if len(new) < n:                              # el disco se termina antes: se rellena con el original
            new = np.concatenate([new, pcm[a + len(new):a + n]])
        old = pcm[a:a + n]
        gain = np.sqrt((old ** 2).mean(axis=0) / ((new ** 2).mean(axis=0) + 1e-12))
        new = new * gain * run['sign']
        # fundido corto (10 ms) en los bordes del tramo, contra el audio original
        f = min(220, n // 4)
        ramp = np.linspace(0, 1, f, dtype=np.float32)[:, None]
        new[:f] = new[:f] * ramp + old[:f] * (1 - ramp)
        new[-f:] = new[-f:] * ramp[::-1] + old[-f:] * (1 - ramp[::-1])
        out[a:a + n] = new
        rep += n
        if OUT44:
            seg44 = hq[s:s + 2 * n] * gain * run['sign']
            old44 = out44[2 * a:2 * a + 2 * n]
            if len(seg44) < 2 * n:
                seg44 = np.concatenate([seg44, old44[len(seg44):]])
            if 2 * n >= 44100 * 3:
                # 1) seguir la dinamica del juego: el disco puede estar masterizado con otro volumen por tramos.
                #    Ganancia lenta = envolvente del original / envolvente del nuevo (ventanas de 0,5 s, suavizada 1,5 s).
                from scipy.ndimage import uniform_filter1d
                lp9 = signal.butter(6, 9000, fs=44100, output='sos')
                bp = signal.butter(4, [150, 6000], btype='band', fs=44100, output='sos')
                m_new, m_old = seg44.mean(axis=1), old44.mean(axis=1)
                e_new = uniform_filter1d(signal.sosfiltfilt(lp9, m_new) ** 2, size=22050)
                e_old = uniform_filter1d(signal.sosfiltfilt(lp9, m_old) ** 2, size=22050)
                ratio = np.sqrt((e_old + 1e-9) / (e_new + 1e-9))
                ratio = np.clip(uniform_filter1d(ratio, size=66150), 0.4, 2.5).astype(np.float32)
                seg44 = seg44 * ratio[:, None]
                # 2) donde el disco no es la misma musica (parecido local bajo) se deja el audio original.
                #    Solo se puede juzgar en temas sin giro de fase (parecido tipico alto).
                b_new, b_old = signal.sosfiltfilt(bp, seg44.mean(axis=1)), signal.sosfiltfilt(bp, m_old)
                w = 22050
                cc = np.array([np.corrcoef(b_new[x:x + w], b_old[x:x + w])[0, 1] for x in range(0, 2 * n - w + 1, w // 2)])
                kept = 0.0
                if run.get('local') or np.median(cc) >= 0.95:
                    mask = np.ones(2 * n, dtype=np.float32)
                    for j, c in enumerate(cc):
                        if c < 0.85:
                            x = j * (w // 2)
                            mask[max(x - w // 2, 0):x + w + w // 2] = 0.0
                    kept = float((mask < 0.5).mean()) * 2 * n / 44100
                    mask = uniform_filter1d(mask, size=1323)[:, None]            # fundidos de 30 ms
                    seg44 = seg44 * mask + old44 * (1 - mask)
                rep -= int(kept * RATE)
                print('      dinamica: ajuste entre %+.1f y %+.1f dB; parecido local mediano %.2f; se deja original %.1f s por no coincidir' % (
                    20 * np.log10(ratio.min()), 20 * np.log10(ratio.max()), float(np.median(cc)), kept))
            f4 = min(441, n // 2)
            r4 = np.linspace(0, 1, f4, dtype=np.float32)[:, None]
            seg44[:f4] = seg44[:f4] * r4 + old44[:f4] * (1 - r4)
            seg44[-f4:] = seg44[-f4:] * r4[::-1] + old44[-f4:] * (1 - r4[::-1])
            out44[2 * a:2 * a + 2 * n] = seg44
        cl = float((np.abs(new) > 1.0).mean()) * 100
        print('   tramo %7.2f - %7.2f s (regiones %d a %d): disco desde %7.3f s, ajuste fino %+d, ganancia L/R %.2f/%.2f, polaridad %s, parecido final %.3f, recorte %.3f %%' % (
            a / RATE, (a + n) / RATE, run['regs'][0], run['regs'][-1], s / 44100, d, gain[0], gain[1], 'invertida' if run['sign'] < 0 else 'igual', float(np.corrcoef(new.mean(axis=1), old.mean(axis=1))[0, 1]), cl))
    bad = [r for r in regs if not r['ok']]
    print('%s <- %s: reemplazado %.1f de %.1f s (%.0f %%). Regiones que quedan con el audio original: %s' % (
        name, os.path.basename(flac), rep / RATE, total / RATE, 100.0 * rep / total,
        ', '.join('%d (%.1f s, parecido %.2f)' % (r['i'], r['n'] / RATE, r['coef']) for r in bad) or 'ninguna'))
    if OUT44:
        return retime(data, info, out44)
    pcm16 = np.clip(np.round(out * 32768.0), -32768, 32767).astype('<i2').tobytes()
    assert len(pcm16) == total * 4
    return data[:base] + pcm16 + data[base + total * 4:]


def retime(data, info, out44):
    """Entrada a 44.100 Hz: mismas regiones, saltos y marcas, con todas las posiciones (en bytes desde el comienzo del
    audio) multiplicadas por dos, y la frecuencia de FRMT cambiada."""
    base = info['frmt_off']
    hdr = bytearray(data[:base])
    def fix(pos):
        v = struct.unpack_from('>I', hdr, pos)[0]
        struct.pack_into('>I', hdr, pos, base + 2 * (v - base))
    for tag, p, size in info['chunks']:
        body = p + 8
        if tag == 'FRMT':
            struct.pack_into('>I', hdr, body + 12, 44100)
        elif tag == 'REGN':
            fix(body)
            struct.pack_into('>I', hdr, body + 4, 2 * struct.unpack_from('>I', hdr, body + 4)[0])
        elif tag == 'JUMP':
            fix(body); fix(body + 4)
        elif tag in ('STOP', 'TEXT'):
            fix(body)
    if BOOST_DB:
        # subir el volumen de toda la entrada (tramos nuevos y originales por igual) y limitar solo los picos
        from scipy.ndimage import maximum_filter1d, minimum_filter1d, uniform_filter1d
        out44 = out44 * (10 ** (BOOST_DB / 20.0))
        env = maximum_filter1d(np.abs(out44).max(axis=1), size=441)
        lg = np.minimum(1.0, 0.97 / np.maximum(env, 1e-9))
        lg = uniform_filter1d(minimum_filter1d(lg, size=441), size=441).astype(np.float32)
        print('   volumen %+.1f dB; el limitador actua en el %.2f %% del tema (baja maxima %.1f dB)' % (
            BOOST_DB, 100 * float((lg < 0.999).mean()), 20 * np.log10(float(lg.min()))))
        out44 = out44 * lg[:, None]
    pcm16 = np.clip(np.round(out44 * 32768.0), -32768, 32767).astype('<i2').tobytes()
    assert len(pcm16) == 2 * info['data_size']
    struct.pack_into('>I', hdr, base - 4, len(pcm16))            # tamano del bloque DATA
    struct.pack_into('>I', hdr, 4, base + len(pcm16))            # tamano total (mismo criterio que el original)
    return bytes(hdr) + pcm16


if __name__ == '__main__':
    OUT44 = '--44' in sys.argv
    BOOST_DB = float(sys.argv[sys.argv.index('--volumen') + 1]) if '--volumen' in sys.argv else 0.0
    args = [a for i, a in enumerate(sys.argv[1:], 1) if a not in ('--44', '--volumen') and sys.argv[i - 1] != '--volumen']
    src, dst = args[0], args[1]
    specs = dict(a.split('=', 1) for a in args[2:])
    b = bun.Bun(src)
    new_entries = {}
    for name, flac in specs.items():
        e = b.find(name)
        new_entries[e['name']] = rebuild(decode_entry(b, e['name']), flac, e['name'])
    # reescribir el .BUN: mismas entradas y orden, indice nuevo al final
    with open(dst, 'wb') as o:
        o.write(b'LB83' + struct.pack('>II', 0, len(b.entries)))
        table = []
        for e in b.entries:
            blob = new_entries.get(e['name']) or b.raw(e)
            table.append((e['raw'], o.tell(), len(blob)))
            o.write(blob)
        diroff = o.tell()
        for raw, off, size in table:
            o.write(raw + struct.pack('>II', off, size))
        o.seek(4)
        o.write(struct.pack('>I', diroff))
    print('escrito %s: %d bytes (original %d), %d entradas, %d reemplazadas' % (
        os.path.basename(dst), os.path.getsize(dst), os.path.getsize(src), len(b.entries), len(new_entries)))
