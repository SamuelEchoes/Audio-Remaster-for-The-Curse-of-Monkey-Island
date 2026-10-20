# Audio Remaster for The Curse of Monkey Island
# Copyright (C) 2026 SamuelEchoes
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.

"""Las dos formas de instalar (con el audio incluido, o reconstruyendolo) y la descarga de la banda de sonido.

Todo corre en un hilo aparte de la interfaz: informa con log(texto) y progreso(fraccion 0..1, etapa).
El juego no se toca hasta que TODO lo nuevo esta generado y verificado; recien ahi se intercambian los archivos.
"""
import json
import os
import shutil
import sys
import time
import urllib.request
import zipfile

from . import juego, pak
from .juego import Problema, CARPETA, gb
from .textos import t, motor as tm


def datos_dir():
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, 'datos')


def cargar(nombre):
    return json.load(open(os.path.join(datos_dir(), nombre), encoding='utf-8'))


def carpeta_del_programa():
    return os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Cancelado(Exception):
    pass


def _chk(cancel):
    if cancel and cancel():
        raise Cancelado()


def _limpiar(path):
    shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path, exist_ok=True)


def _poner_scummvm(res, marca, inis, log):
    for ini, seccion in inis:
        try:
            marca['scummvm'].append(juego.poner_ajuste(ini, seccion))
            log(t('ScummVM: ajuste aplicado en [%s] de %s', 'ScummVM: setting applied to [%s] in %s') % (seccion, ini))
        except Exception as ex:
            log(t('ScummVM: no se pudo aplicar el ajuste en %s (%s)', 'ScummVM: the setting could not be applied in %s (%s)') % (ini, ex))
    juego.guardar_marca(res, marca)


# ------------------------------------------------------------------------------------------ instalador completo

def paquetes_completo(lang):
    return [('MUSDISK1.BUN', 'musica1.pak'), ('MUSDISK2.BUN', 'musica2.pak'),
            ('VOXDISK1.BUN', 'voces1_%s.pak' % lang), ('VOXDISK2.BUN', 'voces2_%s.pak' % lang)]


def buscar_paquetes():
    for c in (os.path.join(carpeta_del_programa(), 'paquetes'), os.path.join(os.path.dirname(carpeta_del_programa()), 'paquetes')):
        if os.path.isdir(c):
            return c
    return os.path.join(carpeta_del_programa(), 'paquetes')


def espacio_completo(lang, paqs):
    total, falta = 0, []
    for bun, p in paquetes_completo(lang):
        f = os.path.join(paqs, p)
        if os.path.exists(f):
            total += pak.read_index(f)['bun_size']
        else:
            falta.append(p)
    v = os.path.join(paqs, 'videos_' + lang)
    if os.path.isdir(v):
        total += sum(os.path.getsize(os.path.join(v, x)) for x in os.listdir(v))
    else:
        falta.append('videos_' + lang)
    return total, falta


def instalar_completo(estado, paqs, inis, log, progreso, cancel=None):
    res, lang = estado['res'], estado['idioma']
    huellas = cargar('huellas.json')
    _, falta = espacio_completo(lang, paqs)
    if falta:
        raise Problema(t('Faltan archivos del instalador en la carpeta "paquetes": ', 'Installer files are missing from the "paquetes" folder: ') + ', '.join(falta))
    nuevo = os.path.join(res, CARPETA, 'nuevo')
    _limpiar(nuevo)
    sha = {}
    try:
        lista = paquetes_completo(lang)
        for i, (bun, p) in enumerate(lista):
            _chk(cancel)
            log(t('Reconstruyendo %s ...', 'Rebuilding %s ...') % bun)
            idx = pak.read_index(os.path.join(paqs, p))
            got = pak.unpack(os.path.join(paqs, p), os.path.join(nuevo, bun),
                             progress=lambda d, tt, i=i: progreso((i + d / max(tt, 1)) / (len(lista) + 1), bun), cancel=cancel)
            if got != idx['bun_sha256']:
                raise Problema(t('%s no resultó idéntico al de referencia. El paquete puede estar dañado.',
                                 '%s does not match the reference. The package may be damaged.') % bun)
            sha[bun] = got
            log(t('   %s: huella correcta (%s)', '   %s: fingerprint OK (%s)') % (bun, gb(idx['bun_size'])))
        vdir = os.path.join(paqs, 'videos_' + lang)
        ref = huellas['idiomas'][lang]['videos_remaster']
        vids = sorted(os.listdir(vdir))
        for j, f in enumerate(vids):
            _chk(cancel)
            shutil.copyfile(os.path.join(vdir, f), os.path.join(nuevo, f))
            got = pak.sha256_file(os.path.join(nuevo, f))
            if f in ref and got != ref[f]['sha256']:
                raise Problema(t('El audio del video %s está dañado en el paquete.', 'The audio for video %s is damaged in the package.') % f)
            sha[f] = got
            progreso((len(lista) + (j + 1) / len(vids)) / (len(lista) + 1), 'videos')
        log(t('   audio de %d videos copiado y verificado', '   audio for %d videos copied and verified') % len(vids))
        _chk(cancel)
        marca = juego.aplicar(res, nuevo, {'modo': 'completo', 'idioma': lang, 'sha_nuevos': sha})
        log(t('Archivos del juego reemplazados; originales guardados en %s\\original', 'Game files replaced; originals saved in %s\\original') % CARPETA)
    except BaseException:
        shutil.rmtree(nuevo, ignore_errors=True)
        if not juego.leer_marca(res):
            shutil.rmtree(os.path.join(res, CARPETA), ignore_errors=True)
        raise
    shutil.rmtree(nuevo, ignore_errors=True)
    _poner_scummvm(res, marca, inis, log)
    progreso(1.0, t('listo', 'done'))
    return marca


# ------------------------------------------------------------------------------------------ banda de sonido

def fuente_disponible(url, timeout=12):
    """(disponible, tamano o None, detalle). Pide solo el primer byte para no bajar nada."""
    try:
        req = urllib.request.Request(url, headers={'Range': 'bytes=0-0', 'User-Agent': 'COMI-Remaster/' + juego.VERSION})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            cr = r.headers.get('Content-Range', '')
            size = int(cr.split('/')[-1]) if '/' in cr and cr.split('/')[-1].isdigit() else (int(r.headers.get('Content-Length', 0)) or None)
            return True, size, 'HTTP %s' % r.status
    except Exception as ex:
        return False, None, str(ex)[:120]


def descargar(url, destino, total, log, progreso, cancel=None):
    """Baja con reanudacion: si el archivo parcial existe, sigue desde donde quedo."""
    parcial = destino + '.parcial'
    hecho = os.path.getsize(parcial) if os.path.exists(parcial) else 0
    if hecho >= total:
        hecho = 0
        os.remove(parcial)
    intentos = 0
    while hecho < total:
        _chk(cancel)
        try:
            req = urllib.request.Request(url, headers={'Range': 'bytes=%d-' % hecho, 'User-Agent': 'COMI-Remaster/' + juego.VERSION})
            with urllib.request.urlopen(req, timeout=30) as r, open(parcial, 'ab' if hecho else 'wb') as o:
                if hecho and r.status != 206:
                    o.close()
                    hecho = 0
                    open(parcial, 'wb').close()
                    continue
                t0, b0 = time.time(), hecho
                while True:
                    _chk(cancel)
                    blk = r.read(1 << 18)
                    if not blk:
                        break
                    o.write(blk)
                    hecho += len(blk)
                    dt = time.time() - t0
                    vel = (hecho - b0) / dt if dt > 1 else 0
                    progreso(hecho / total, t('descarga: %s de %s%s', 'download: %s of %s%s') % (gb(hecho), gb(total), ' (%.1f MB/s)' % (vel / 1e6) if vel else ''))
            intentos = 0
        except Cancelado:
            raise
        except Exception as ex:
            intentos += 1
            if intentos > 6:
                raise Problema(t('La descarga se interrumpió varias veces: %s', 'The download was interrupted several times: %s') % str(ex)[:150])
            log(t('   la descarga se interrumpió (%s); reintento %d ...', '   download interrupted (%s); retry %d ...') % (str(ex)[:80], intentos))
            time.sleep(3)
    os.replace(parcial, destino)


def validar_zip(path, banda, progreso=None):
    if os.path.getsize(path) != banda['size']:
        return False, t('el tamaño no coincide (%s, se esperaba %s)', 'size does not match (%s, expected %s)') % (gb(os.path.getsize(path)), gb(banda['size']))
    got = pak.sha256_file(path, progreso)
    return got == banda['sha256'], (t('huella correcta', 'fingerprint OK') if got == banda['sha256'] else
                                    t('huella distinta: no es la misma edición', 'fingerprint differs: not the same edition'))


def extraer_banda(zip_path, destino, banda, log, progreso, cancel=None):
    """Extrae los 79 temas y comprueba la huella de cada uno."""
    os.makedirs(destino, exist_ok=True)
    temas = banda['temas']
    with zipfile.ZipFile(zip_path) as z:
        porn = {os.path.basename(i.filename): i for i in z.infolist() if i.filename.lower().endswith('.flac')}
        falta = [x for x in temas if x not in porn]
        if falta:
            raise Problema(t('Al archivo de la banda de sonido le faltan temas: ', 'The soundtrack file is missing tracks: ') + ', '.join(falta[:4]))
        for k, tema in enumerate(temas):
            _chk(cancel)
            dst = os.path.join(destino, tema)
            if not (os.path.exists(dst) and os.path.getsize(dst) == temas[tema]['size']):
                with z.open(porn[tema]) as src, open(dst, 'wb') as o:
                    shutil.copyfileobj(src, o, 1 << 20)
            if pak.sha256_file(dst) != temas[tema]['sha256']:
                raise Problema(t('El tema "%s" no coincide con el de referencia.', 'Track "%s" does not match the reference.') % tema)
            progreso((k + 1) / len(temas), t('temas', 'tracks'))
    log(t('   %d temas extraídos y verificados uno por uno', '   %d tracks extracted and verified one by one') % len(temas))


# ------------------------------------------------------------------------------------------ instalador que reconstruye

ESPACIO_RECONSTRUIR = 9.5e9      # banda extraida + entradas sueltas + archivos armados, todo a la vez


def instalar_reconstruyendo(estado, zip_path, inis, log, progreso, cancel=None, procesos=None, conservar_zip=True):
    """Fabrica el audio nuevo con el juego del usuario y la banda de sonido, lo valida y recien entonces lo instala."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from . import motor
    res, lang = estado['res'], estado['idioma']
    banda, recetas, firmas = cargar('banda.json'), cargar('recetas.json'), cargar('firmas.json')
    base = os.path.join(res, CARPETA)
    trabajo, nuevo = os.path.join(base, 'trabajo'), os.path.join(base, 'nuevo')
    _limpiar(nuevo)
    os.makedirs(trabajo, exist_ok=True)
    procesos = procesos or max(1, min(8, (os.cpu_count() or 4) - 2))
    informe = {'musica': 0, 'voces': 0, 'videos': 0, 'avisos': []}
    etapas = [('banda', 0.04), ('musica', 0.50), ('voces', 0.24), ('videos', 0.18), ('final', 0.04)]
    ini_et = {}
    acc = 0.0
    for n, w in etapas:
        ini_et[n] = (acc, w)
        acc += w

    def pr(etapa, frac, texto=None):
        a, w = ini_et[etapa]
        progreso(a + w * min(max(frac, 0.0), 1.0), texto or etapa)

    def correr(pool, fn, tareas, etapa, texto, cada=None):
        futs = [pool.submit(fn, x) for x in tareas]
        out = []
        try:
            for k, f in enumerate(as_completed(futs)):
                _chk(cancel)
                out.append(f.result())
                pr(etapa, (k + 1) / len(futs), texto % (k + 1, len(futs)))
        except BaseException:
            for f in futs:
                f.cancel()
            raise
        return out

    try:
        # 1) banda de sonido
        log(t('Verificando la banda de sonido ...', 'Checking the soundtrack ...'))
        ok, det = validar_zip(zip_path, banda, lambda d, tt: pr('banda', 0.5 * d / max(tt, 1), t('verificando la banda de sonido', 'checking the soundtrack')))
        if not ok:
            raise Problema(t('El archivo de la banda de sonido no es válido: ', 'The soundtrack file is not valid: ') + det)
        log(t('   archivo completo: ', '   whole file: ') + det)
        flacs = os.path.join(trabajo, 'flac')
        extraer_banda(zip_path, flacs, banda, log, lambda f, s: pr('banda', 0.5 + 0.5 * f, t('extrayendo temas', 'extracting tracks')), cancel)

        with ProcessPoolExecutor(procesos) as pool:
            # 2) musica
            log(t('Generando la música (%d procesos) ...', 'Building the music (%d processes) ...') % procesos)
            tareas = []
            for n in ('1', '2'):
                d = os.path.join(trabajo, 'm' + n)
                os.makedirs(d, exist_ok=True)
                orig = juego._real(res, 'MUSDISK%s.BUN' % n)
                for name, tema in recetas['musica'][n].items():
                    tareas.append((orig, name, os.path.join(flacs, tema) if tema else None, d))
            correr(pool, motor.musica_entrada, tareas, 'musica', t('música: pista %d de %d', 'music: track %d of %d'))
            for n in ('1', '2'):
                d = os.path.join(trabajo, 'm' + n)
                mal = []
                for name, ref in firmas['musica'][n].items():
                    f = os.path.join(d, name.replace('~', '_') + '.bin')
                    if not os.path.exists(f):
                        mal.append(name + t(' (no se generó)', ' (not generated)'))
                        continue
                    ok, det = motor.comparar_firma(open(f, 'rb').read(), ref)
                    if not ok:
                        mal.append('%s (%s)' % (name, tm(det)))
                    informe['musica'] += 1
                if mal:
                    raise Problema(t('Música, disco %s: %d pistas no coinciden con la referencia: %s',
                                     'Music, disc %s: %d tracks do not match the reference: %s') % (n, len(mal), '; '.join(mal[:4])))
                dst = os.path.join(nuevo, 'MUSDISK%s.BUN' % n)
                motor.armar(juego._real(res, 'MUSDISK%s.BUN' % n), d, dst)
                bad = motor.verificar_estructura(juego._real(res, 'MUSDISK%s.BUN' % n), dst)
                if bad:
                    raise Problema(t('Música, disco %s: problemas de estructura: %s', 'Music, disc %s: structure problems: %s') % (
                        n, '; '.join('%s: %s' % (tm(a), tm(b)) for a, b in bad[:4])))
                shutil.rmtree(d, ignore_errors=True)
                log(t('   disco %s: %d pistas coinciden con la referencia; estructura correcta',
                      '   disc %s: %d tracks match the reference; structure OK') % (n, len(firmas['musica'][n])))

            # 3) voces
            log(t('Generando las voces ...', 'Building the voices ...'))
            tareas, por_disco = [], {}
            for n in ('1', '2'):
                d = os.path.join(trabajo, 'v' + n)
                os.makedirs(d, exist_ok=True)
                orig = juego._real(res, 'VOXDISK%s.BUN' % n)
                _, comp = motor.nombres(orig)
                por_disco[n] = (orig, d, comp)
                tareas += [(orig, comp[i:i + 60], d) for i in range(0, len(comp), 60)]
            errores = []
            for hechas, errs in correr(pool, motor.voces_lote, tareas, 'voces', t('voces: lote %d de %d', 'voices: batch %d of %d')):
                errores += errs
            if errores:
                raise Problema(t('Voces: %d frases no pudieron procesarse: %s', 'Voices: %d lines could not be processed: %s') % (len(errores), '; '.join(errores[:3])))
            ref_v = firmas['voces'].get(lang)
            for n in ('1', '2'):
                orig, d, comp = por_disco[n]
                if ref_v:
                    mal = []
                    for name, ref in ref_v[n].items():
                        f = os.path.join(d, name.replace('~', '_') + '.bin')
                        ok, det = motor.comparar_firma(open(f, 'rb').read(), ref) if os.path.exists(f) else (False, t('no se generó', 'not generated'))
                        if not ok:
                            mal.append('%s (%s)' % (name, tm(det)))
                    if mal:
                        raise Problema(t('Voces, disco %s: %d frases no coinciden con la referencia: %s',
                                         'Voices, disc %s: %d lines do not match the reference: %s') % (n, len(mal), '; '.join(mal[:4])))
                dst = os.path.join(nuevo, 'VOXDISK%s.BUN' % n)
                rep = motor.armar(orig, d, dst)
                if rep != len(comp):
                    raise Problema(t('Voces, disco %s: se esperaban %d frases y hay %d.', 'Voices, disc %s: %d lines were expected and there are %d.') % (n, len(comp), rep))
                bad = motor.verificar_estructura(orig, dst)
                if bad:
                    raise Problema(t('Voces, disco %s: problemas de estructura: %s', 'Voices, disc %s: structure problems: %s') % (
                        n, '; '.join('%s: %s' % (tm(a), tm(b)) for a, b in bad[:4])))
                informe['voces'] += rep
                shutil.rmtree(d, ignore_errors=True)
                log(t('   disco %s: %d frases; %s; estructura correcta', '   disc %s: %d lines; %s; structure OK') % (
                    n, rep, t('coinciden con la referencia', 'they match the reference') if ref_v else
                    t('sin referencia para este idioma (solo control de estructura)', 'no reference for this language (structure check only)')))

            # 4) videos
            log(t('Generando el audio de los videos ...', 'Building the video audio ...'))
            tmpv = os.path.join(trabajo, 'vid')
            os.makedirs(tmpv, exist_ok=True)
            tareas = []
            for san in juego.videos_del_juego(res):
                specs = [(os.path.join(flacs, tema), float(s)) for tema, s in recetas['videos'].get(san.upper(), [])]
                tareas.append((os.path.join(res, san), os.path.join(nuevo, os.path.splitext(san)[0] + '.ogg'), specs, tmpv))
            resv = correr(pool, motor.video_uno, tareas, 'videos', t('videos: %d de %d', 'videos: %d of %d'))
        import numpy as np
        import soundfile as sf
        ref_vid = firmas['videos'].get(lang, {})
        for san, info in resv:
            ogg = os.path.join(nuevo, os.path.splitext(san)[0] + '.ogg')
            y, sr = sf.read(ogg, dtype='float32', always_2d=True)
            esperado = int(round(info['segundos_san'] * 44100))
            if sr != 44100 or abs(len(y) - esperado) > 4410:
                raise Problema(t('Video %s: la duración del audio nuevo no coincide con la del video.', 'Video %s: the new audio length does not match the video.') % san)
            if not np.isfinite(y).all() or float(np.abs(y).max()) < 1e-4:
                raise Problema(t('Video %s: el audio nuevo resultó vacío o dañado.', 'Video %s: the new audio is empty or damaged.') % san)
            ref = ref_vid.get(os.path.basename(ogg))
            if ref:
                m = y.mean(axis=1) * 32768.0
                k = len(m) // 4096
                q = np.clip(np.round(2 * 20 * np.log10(np.sqrt((m[:k * 4096].reshape(k, 4096) ** 2).mean(axis=1)) + 1.0)), 0, 255).astype(int)
                r = np.frombuffer(bytes.fromhex(ref['niv']), dtype=np.uint8).astype(int)
                if len(q) != len(r) or float((np.abs(q - r) > 3).mean()) > 0.01:
                    raise Problema(t('Video %s: el audio nuevo no coincide con la referencia.', 'Video %s: the new audio does not match the reference.') % san)
            informe['videos'] += 1
        log(t('   %d videos; duración correcta%s', '   %d videos; length OK%s') % (
            informe['videos'], t(' y coinciden con la referencia', ' and they match the reference') if ref_vid else
            t(' (sin referencia para este idioma)', ' (no reference for this language)')))

        # 5) intercambio
        _chk(cancel)
        pr('final', 0.2, t('instalando', 'installing'))
        marca = juego.aplicar(res, nuevo, {'modo': 'reconstruido', 'idioma': lang},
                              progreso=lambda d, tt: pr('final', 0.2 + 0.8 * d / max(tt, 1), t('instalando', 'installing')))
        log(t('Archivos del juego reemplazados; originales guardados en %s\\original', 'Game files replaced; originals saved in %s\\original') % CARPETA)
    except BaseException:
        shutil.rmtree(nuevo, ignore_errors=True)
        shutil.rmtree(os.path.join(trabajo, 'm1'), ignore_errors=True)
        shutil.rmtree(os.path.join(trabajo, 'm2'), ignore_errors=True)
        shutil.rmtree(os.path.join(trabajo, 'v1'), ignore_errors=True)
        shutil.rmtree(os.path.join(trabajo, 'v2'), ignore_errors=True)
        if not juego.leer_marca(res):
            try:
                os.rmdir(os.path.join(base, 'original'))
            except OSError:
                pass
        raise
    shutil.rmtree(nuevo, ignore_errors=True)
    shutil.rmtree(trabajo, ignore_errors=True)
    marca['validacion'] = informe
    _poner_scummvm(res, marca, inis, log)
    progreso(1.0, t('listo', 'done'))
    return marca
