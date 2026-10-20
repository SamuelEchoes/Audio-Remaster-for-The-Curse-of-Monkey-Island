# Audio Remaster for The Curse of Monkey Island
# Copyright (C) 2026 SamuelEchoes
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.

"""Motor de reconstruccion: fabrica el audio remasterizado a partir del juego original y de la banda de sonido.

Es el mismo proceso con que se hizo el parche (modulos copiados tal cual del proyecto), ordenado en funciones que
trabajan por entrada para poder repartirlas entre varios procesos.
"""
import os
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import numpy as np                                                       # noqa: E402

VOLUMEN_DB = 2.0          # decision del usuario: musica +2 dB sobre el original
AIRE_MUSICA = 2.0         # metodo "2b" para lo que queda con el audio del juego
FORZAR_IGUAL = ('1511', '2420', '2508')   # misma musica que el disco; el control fino las rechazaba por giro de fase
SOLO_ORIGINAL = ('1277',)                 # variante del juego: no se reemplaza nada


def _low_priority():
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.c_void_p(-1), 0x4000)
    except Exception:
        pass


def _pcm(data, info):
    return np.frombuffer(data, dtype='<i2', count=info['data_size'] // 2, offset=info['data_off']).reshape(
        -1, info['channels']).astype(np.float32) / 32768.0


# ----------------------------------------------------------------------------------------------- musica

def _forzar_igual(data, info, flac):
    """Disco alineado + nivel y dinamica del juego + control local por coherencia (port de forzar.py, modo igual)."""
    import soundfile as sf
    from scipy import signal
    from scipy.ndimage import uniform_filter1d
    import build_bun
    from match import band, best, RATE
    lp9 = signal.butter(6, 9000, fs=44100, output='sos')
    pcm = _pcm(data, info)
    hq, sr = sf.read(flac, dtype='float32', always_2d=True)
    assert sr == 44100
    h22 = signal.resample_poly(hq, 1, 2, axis=0).astype(np.float32)
    gm, hm = band(pcm.mean(axis=1)), band(h22.mean(axis=1))
    cs = np.concatenate([[0.0], np.cumsum(hm.astype(np.float64) ** 2)])
    W, step = 5 * RATE, 2 * RATE
    rows = []
    for a in range(0, max(len(gm) - W, 1), step):
        k, c = best(gm[a:a + W], hm, cs)
        if k is not None:
            rows.append((a, k - a, c))
    offs = [d for _, d, c in rows if c >= 0.3]
    d = max(set(offs), key=lambda o: sum(1 for q in offs if abs(q - o) <= 4))
    ok = [a for a, dd, c in rows if abs(dd - d) <= 90 and c >= 0.3]
    a, e = min(ok), max(ok) + W
    a, e = max(a, -d), min(e, len(h22) - d, len(pcm))
    up = signal.resample_poly(pcm, 2, 1, axis=0).astype(np.float32)
    N = 2 * (e - a)
    fine, _ = build_bun.exact_offset(up.mean(axis=1), hq.mean(axis=1), 2 * a, 2 * (a + d), min(N, 44100 * 40))
    s = 2 * (a + d) + fine
    old = up[2 * a:2 * a + N]
    pad = 48000
    lo = max(s - pad, 0)
    src = hq[lo:s + N + pad]
    seg = src[s - lo:s - lo + N].copy()
    gain = np.sqrt((old[:len(seg)] ** 2).mean(axis=0) / ((seg ** 2).mean(axis=0) + 1e-12))
    seg = seg * gain
    if len(seg) < N:
        seg = np.concatenate([seg, old[len(seg):]])
    e_new = uniform_filter1d(signal.sosfiltfilt(lp9, seg.mean(axis=1)) ** 2, size=22050)
    e_old = uniform_filter1d(signal.sosfiltfilt(lp9, old.mean(axis=1)) ** 2, size=22050)
    ratio = np.clip(uniform_filter1d(np.sqrt((e_old + 1e-9) / (e_new + 1e-9)), size=66150), 0.4, 2.5).astype(np.float32)
    seg = seg * ratio[:, None]
    w = 2 * 44100
    mo, ms = old.mean(axis=1), seg.mean(axis=1)
    mask = np.ones(N, dtype=np.float32)
    for x0 in range(0, N - w + 1, w // 2):
        f, c = signal.coherence(mo[x0:x0 + w], ms[x0:x0 + w], fs=44100, nperseg=4096)
        if c[(f > 200) & (f < 4000)].mean() < 0.75:
            mask[x0:x0 + w] = 0.0
    mask = uniform_filter1d(mask, size=2205)[:, None]
    seg = seg * mask + old * (1 - mask)
    f4 = min(2205, N // 8)
    r4 = np.linspace(0, 1, f4, dtype=np.float32)[:, None]
    seg[:f4] = seg[:f4] * r4 + old[:f4] * (1 - r4)
    seg[-f4:] = seg[-f4:] * r4[::-1] + old[-f4:] * (1 - r4[::-1])
    out44 = up.copy()
    out44[2 * a:2 * a + N] = seg
    return build_bun.retime(data, info, out44)


def _paso_final(fino, data):
    """Mejora lo que quedo con el audio del juego, sube el volumen y limita los picos (port de final_pass.py)."""
    import json
    from scipy import signal
    from scipy.ndimage import uniform_filter1d, maximum_filter1d, minimum_filter1d
    import bun
    import enhance
    prof = json.load(open(os.path.join(_HERE, 'perfil_mejora.json')))
    info = bun.parse_imus(fino[:0x10000])
    assert info['rate'] == 44100 and info['channels'] == 2, info
    base = info['data_off']
    new = np.frombuffer(fino, dtype='<i2', count=info['data_size'] // 2, offset=base).reshape(-1, 2).astype(np.float32) / 32768.0
    ri = bun.parse_imus(data[:0x10000])
    old = np.frombuffer(data, dtype='<i2', count=ri['data_size'] // 2, offset=ri['data_off']).reshape(-1, 2).astype(np.float32) / 32768.0
    up = signal.resample_poly(old, 2, 1, axis=0).astype(np.float32)
    n = min(len(new), len(up))
    diff = np.abs(new[:n] - up[:n]).max(axis=1)
    orig = (maximum_filter1d(diff, size=2205) < 3e-4).astype(np.float32)
    m = np.clip(uniform_filter1d(orig, size=882), 0, 1)[:, None]
    enh = enhance.enhance(old, prof, air=AIRE_MUSICA)[:n]
    mix = new[:n] * (1 - m) + enh * m
    mix = mix * (10 ** (VOLUMEN_DB / 20.0))
    env = maximum_filter1d(np.abs(mix).max(axis=1), size=441)
    lg = np.minimum(1.0, 0.97 / np.maximum(env, 1e-9))
    lg = uniform_filter1d(minimum_filter1d(lg, size=441), size=441).astype(np.float32)
    mix = mix * lg[:, None]
    assert np.isfinite(mix).all()
    pcm16 = np.clip(np.round(mix * 32768.0), -32768, 32767).astype('<i2').tobytes()
    assert len(pcm16) == info['data_size'], (len(pcm16), info['data_size'])
    return fino[:base] + pcm16


def musica_entrada(args):
    """Una entrada de MUSDISK -> archivo <out>/<nombre>.bin. args = (bun, nombre, flac o None, out)."""
    bunpath, name, flac, out = args
    _low_priority()
    import contextlib
    import io
    from scipy import signal
    import bun
    import build_bun
    dst = os.path.join(out, name.replace('~', '_') + '.bin')
    if os.path.exists(dst):
        return name, 'ya estaba'
    b = bun.Bun(bunpath)
    e = b.find(name)
    if b.raw(e)[:4] not in (b'COMP', b'iMUS'):
        return name, 'no es musica'
    data = b.decode(e)
    info = bun.parse_imus(data)
    build_bun.OUT44, build_bun.BOOST_DB = True, 0.0
    idn = name[:4]
    with contextlib.redirect_stdout(io.StringIO()):
        if flac and idn in FORZAR_IGUAL:
            fino = _forzar_igual(data, info, flac)
        elif flac and idn not in SOLO_ORIGINAL:
            fino = build_bun.rebuild(data, flac, name)
        else:
            fino = build_bun.retime(data, info, signal.resample_poly(_pcm(data, info), 2, 1, axis=0).astype(np.float32))
        final = _paso_final(fino, data)
    open(dst + '.tmp', 'wb').write(final)
    os.replace(dst + '.tmp', dst)
    return name, 'ok'


# ----------------------------------------------------------------------------------------------- voces

def voces_lote(args):
    """Un lote de frases de VOXDISK -> <out>/<nombre>.bin (port de voices_pass.py). args = (bun, nombres, out)."""
    bunpath, names, out = args
    _low_priority()
    import json
    from scipy import signal
    import bun
    import build_bun
    import deess
    import enhance
    prof = json.load(open(os.path.join(_HERE, 'perfil_mejora.json')))
    b = bun.Bun(bunpath)
    build_bun.BOOST_DB = 0.0
    done, errores = 0, []
    for name in names:
        dst = os.path.join(out, name.replace('~', '_') + '.bin')
        if os.path.exists(dst):
            done += 1
            continue
        try:
            data = b.decode(b.find(name))
            info = bun.parse_imus(data)
            assert info['bits'] == 16 and info['rate'] == 22050, info
            ch = info['channels']
            x = _pcm(data, info)
            if len(x) >= 4096:
                y = np.stack([deess.deess(x[:, c], strength=1.0)[0] for c in range(ch)], axis=1)
                z = enhance.enhance(y, prof, clean=1.0, air=0.5)
            else:
                z = signal.resample_poly(x, 2, 1, axis=0).astype(np.float32)
            z = z[:2 * len(x)]
            if len(z) < 2 * len(x):
                z = np.concatenate([z, np.zeros((2 * len(x) - len(z), ch), np.float32)])
            if info['data_size'] % 2:
                z = np.concatenate([z, np.zeros((1, ch), np.float32)])
            peak = float(np.abs(z).max()) if len(z) else 0.0
            if peak > 0.98:
                z *= 0.98 / peak
            assert np.isfinite(z).all()
            new = build_bun.retime(data, info, z)
            open(dst + '.tmp', 'wb').write(new)
            os.replace(dst + '.tmp', dst)
            done += 1
        except Exception as ex:
            errores.append('%s: %r' % (name, ex))
    return done, errores


# ----------------------------------------------------------------------------------------------- videos

def video_uno(args):
    """Audio de un .SAN -> .ogg. args = (san, ogg, [(flac, segundo del video donde empieza), ...], carpeta temporal)."""
    san, ogg, specs, tmp = args
    _low_priority()
    import soundfile as sf
    import build_video
    import san_audio
    if os.path.exists(ogg):
        return os.path.basename(san), {'ya': True}
    stream, frames, first = san_audio.iact_stream(san)
    pcm = san_audio.decode(stream)
    wav = os.path.join(tmp, os.path.basename(san) + '.wav')
    sf.write(wav, pcm, 22050, subtype='PCM_16')
    try:
        info = build_video.build(wav, ogg, specs, log=lambda s: None)
    finally:
        try:
            os.remove(wav)
        except OSError:
            pass
    info['segundos_san'] = len(pcm) / 22050.0
    return os.path.basename(san), info


# ----------------------------------------------------------------------------------------------- armado y control

def nombres(bunpath):
    """(todas las entradas, las que son audio comprimido)."""
    import bun
    b = bun.Bun(bunpath)
    return [e['name'] for e in b.entries], [e['name'] for e in b.entries if b.raw(e)[:4] == b'COMP']


def armar(bun_orig, carpeta, destino):
    """Arma el .BUN nuevo: las entradas rehechas salen de la carpeta, el resto se copia del original."""
    import bun
    b = bun.Bun(bun_orig)
    rep = 0
    with open(destino + '.tmp', 'wb') as o:
        o.write(b'LB83' + struct.pack('>II', 0, len(b.entries)))
        table = []
        for e in b.entries:
            f = os.path.join(carpeta, e['name'].replace('~', '_') + '.bin')
            if os.path.exists(f):
                blob = open(f, 'rb').read()
                rep += 1
            else:
                blob = b.raw(e)
            table.append((e['raw'], o.tell(), len(blob)))
            o.write(blob)
        diroff = o.tell()
        for raw, off, size in table:
            o.write(raw + struct.pack('>II', off, size))
        o.seek(4)
        o.write(struct.pack('>I', diroff))
    os.replace(destino + '.tmp', destino)
    return rep


def verificar_estructura(bun_orig, bun_nuevo):
    """Lo que haria que el juego lea mal una entrada (port de verificar_bun.py). Devuelve lista de problemas."""
    import bun
    o, n = bun.Bun(bun_orig), bun.Bun(bun_nuevo)
    bad = []
    if [e['name'] for e in o.entries] != [e['name'] for e in n.entries]:
        return [('(archivo)', 'distinto orden o cantidad de entradas')]
    for eo, en in zip(o.entries, n.entries):
        ro = o.raw(eo)[:4]
        if ro not in (b'COMP', b'iMUS'):
            if o.raw(eo) != n.raw(en):
                bad.append((eo['name'], 'archivo auxiliar modificado'))
            continue
        cto = o.comp_table(eo)
        io_ = bun.parse_imus(o.decode(eo, max_blocks=2) if cto else o.raw(eo)[:0x10000])
        rn = n.raw(en)
        if rn[:4] != b'iMUS':
            bad.append((en['name'], 'no esta sin comprimir'))
            continue
        i = bun.parse_imus(rn)
        base = i['data_off']
        k = i['rate'] // io_['rate']
        p = []
        if i['rate'] != 44100:
            p.append('frecuencia %d' % i['rate'])
        if (i['channels'], i['bits']) != (io_['channels'], io_['bits']):
            p.append('canales/bits')
        esperado = k * io_['data_size'] + (2 * i['channels'] if io_['data_size'] % 2 and i['channels'] == 1 else 0)
        if i['data_size'] not in (k * io_['data_size'], esperado):
            p.append('tamano de datos')
        if base + i['data_size'] != en['size'] or struct.unpack('>I', rn[4:8])[0] != en['size']:
            p.append('tamano total')
        conv = lambda v: base + k * (v - io_['data_off'])                 # noqa: E731
        if [(conv(a), k * b) for a, b in io_['regions']] != list(i['regions']):
            p.append('regiones')
        if [(conv(a), conv(b), c, d) for a, b, c, d in io_['jumps']] != list(i['jumps']):
            p.append('saltos')
        if [conv(s) for s in io_['stops']] != list(i['stops']):
            p.append('fin')
        end = base + i['data_size']
        if any(a < base or a + b > end for a, b in i['regions']) or any(not (base <= d <= end) for _, d, _, _ in i['jumps']):
            p.append('posicion fuera del audio')
        pcm = np.frombuffer(rn, dtype='<i2', count=i['data_size'] // 2, offset=base)
        if len(pcm) and not np.any(pcm):
            if np.any(np.frombuffer(o.decode(eo), dtype='<i2', count=io_['data_size'] // 2, offset=io_['data_off'])):
                p.append('audio en silencio')
        if p:
            bad.append((en['name'], ', '.join(p)))
    return bad


def firma(blob, paso=4096):
    """Firma tolerante de una entrada rehecha: cabecera exacta + nivel por bloque (0,5 dB) de la mezcla mono."""
    import hashlib
    import bun
    info = bun.parse_imus(blob)
    base = info['data_off']
    pcm = np.frombuffer(blob, dtype='<i2', count=info['data_size'] // 2, offset=base).astype(np.float32)
    pcm = pcm.reshape(-1, info['channels']).mean(axis=1)
    n = len(pcm) // paso
    rms = np.sqrt((pcm[:n * paso].reshape(n, paso) ** 2).mean(axis=1)) if n else np.zeros(0)
    q = np.clip(np.round(2 * 20 * np.log10(rms + 1.0)), 0, 255).astype(np.uint8)
    return {'cab': hashlib.sha256(blob[:base]).hexdigest()[:16], 'n': int(info['data_size']), 'niv': q.tobytes().hex()}


def comparar_firma(blob, ref, tol=2, max_fuera=0.002):
    """True si la entrada coincide con la firma de referencia dentro de la tolerancia (1 dB en casi todos los bloques)."""
    f = firma(blob)
    if f['cab'] != ref['cab'] or f['n'] != ref['n']:
        return False, 'cabecera o tamano distintos'
    a = np.frombuffer(bytes.fromhex(f['niv']), dtype=np.uint8).astype(int)
    b = np.frombuffer(bytes.fromhex(ref['niv']), dtype=np.uint8).astype(int)
    if len(a) != len(b):
        return False, 'largo distinto'
    if not len(a):
        return True, ''
    fuera = float((np.abs(a - b) > tol).mean())
    return fuera <= max_fuera, '%.2f %% de bloques fuera de tolerancia' % (100 * fuera)
