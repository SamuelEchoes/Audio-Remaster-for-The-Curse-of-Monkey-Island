# Audio Remaster for The Curse of Monkey Island
# Copyright (C) 2026 SamuelEchoes
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.

"""Deteccion del juego, instalacion con respaldo, desinstalacion y ajuste de ScummVM. Sin interfaz."""
import datetime
import json
import os
import re
import shutil
import subprocess

from .pak import sha256_file
from .textos import t, par, par_idioma, par_modo

VERSION = '1.0'
CARPETA = '_comi_remaster'          # dentro de la carpeta de recursos del juego
MARCA = 'estado.json'
BUNS = ('MUSDISK1.BUN', 'MUSDISK2.BUN', 'VOXDISK1.BUN', 'VOXDISK2.BUN')
AJUSTE = ('dimuse_sample_rate', '44100')


class Problema(Exception):
    """Error que se le muestra al usuario tal cual."""


def _real(carpeta, nombre):
    """Ruta del archivo sin distinguir mayusculas, o None."""
    try:
        for f in os.listdir(carpeta):
            if f.lower() == nombre.lower():
                return os.path.join(carpeta, f)
    except OSError:
        pass
    return None


def buscar_recursos(carpeta):
    """Carpeta que tiene los .BUN: la elegida, su RESOURCE o la de arriba."""
    if not carpeta or not os.path.isdir(carpeta):
        return None
    cands = [carpeta, _real(carpeta, 'RESOURCE'), os.path.dirname(carpeta.rstrip('\\/'))]
    for c in cands:
        if c and os.path.isdir(c) and _real(c, 'MUSDISK1.BUN'):
            return c
    return None


def espacio_libre(ruta):
    return shutil.disk_usage(ruta).free


def _es_bun(path):
    try:
        with open(path, 'rb') as f:
            return f.read(4) == b'LB83'
    except OSError:
        return False


def leer_marca(res):
    p = os.path.join(res, CARPETA, MARCA)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding='utf-8'))
        except Exception:
            return {'danada': True}
    return None


def detectar(carpeta, huellas, progreso=None):
    """Estado del juego. Devuelve un dict con 'estado', 'idioma', 'res' y 'detalle' (lineas para mostrar).

    estados: no_encontrado, incompleto, original, parcheado, parcheado_alterado, remaster_sin_respaldo, desconocido
    """
    r = {'estado': 'no_encontrado', 'idioma': None, 'res': None, 'detalle': [], 'sha': {}, 'marca': None}
    res = buscar_recursos(carpeta)
    if not res:
        r['detalle'].append(par('No se encontró MUSDISK1.BUN en esa carpeta ni en su subcarpeta RESOURCE.',
                                'MUSDISK1.BUN was not found in that folder or in its RESOURCE subfolder.'))
        return r
    r['res'] = res
    r['raiz'] = res if _real(res, 'COMI.LA0') else os.path.dirname(res)
    faltan = [b for b in BUNS if not _real(res, b)]
    if faltan:
        r['estado'] = 'incompleto'
        r['detalle'].append(par('Faltan archivos del juego: %s', 'Game files are missing: %s', ', '.join(faltan)))
        return r
    marca = leer_marca(res)
    if marca:
        r['marca'] = marca
        if marca.get('danada'):
            r['estado'] = 'parcheado_alterado'
            r['detalle'].append(par('Existe una instalación del parche, pero su registro está dañado.',
                                    'A patch installation exists, but its record is damaged.'))
            return r
        r['idioma'] = marca.get('idioma')
        mal = []
        for i, (f, v) in enumerate(marca.get('nuevos', {}).items()):
            p = _real(res, f)
            if not p or os.path.getsize(p) != v['size']:
                mal.append(f)
            if progreso:
                progreso(i + 1, len(marca['nuevos']))
        falta_resp = [f for f in marca.get('originales', {}) if not os.path.exists(os.path.join(res, CARPETA, 'original', f))]
        if falta_resp:
            r['detalle'].append(par('Faltan copias de respaldo: %s', 'Backups are missing: %s', ', '.join(falta_resp)))
        if mal or falta_resp:
            r['estado'] = 'parcheado_alterado'
            if mal:
                r['detalle'].append(par('Archivos del parche modificados o ausentes: %s', 'Patch files changed or missing: %s', ', '.join(mal)))
        else:
            r['estado'] = 'parcheado'
            v, f, m = marca.get('version', '?'), marca.get('fecha', '?'), par_modo(marca.get('modo'))
            r['detalle'].append(('Parche %s instalado el %s (%s).' % (v, f, m[0]), 'Patch %s installed on %s (%s).' % (v, f, m[1])))
        return r
    # sin marca: se identifican los cuatro .BUN por su huella completa
    for i, b in enumerate(BUNS):
        r['sha'][b] = sha256_file(_real(res, b), (lambda d, t, i=i: progreso(i * 100 + int(100 * d / max(t, 1)), 400)) if progreso else None)
    mus_orig = all(r['sha'][b] == huellas['musica'][b]['sha256'] for b in BUNS[:2])
    mus_rem = all(r['sha'][b] == huellas['musica_remaster'][b]['sha256'] for b in BUNS[:2])
    voz_orig = voz_rem = None
    for lang, x in huellas['idiomas'].items():
        if all(r['sha'][b] == x['voces'][b]['sha256'] for b in BUNS[2:]):
            voz_orig = lang
        if all(r['sha'][b] == x['voces_remaster'][b]['sha256'] for b in BUNS[2:]):
            voz_rem = lang
    if mus_orig and voz_orig:
        r['estado'], r['idioma'] = 'original', voz_orig
        n = par_idioma(voz_orig)
        r['detalle'].append(('Juego original, %s.' % n[0].lower(), 'Original game, %s.' % n[1]))
    elif mus_rem and voz_rem:
        r['estado'], r['idioma'] = 'remaster_sin_respaldo', voz_rem
        r['detalle'].append(par('Ya tiene el audio remasterizado, colocado manualmente (sin copias de respaldo en esta carpeta).',
                                'The remastered audio is already present, placed by hand (no backups in this folder).'))
    elif mus_orig and all(_es_bun(_real(res, b)) for b in BUNS[2:]):
        r['estado'], r['idioma'] = 'original', 'otro'
        r['detalle'].append(par('Música original reconocida. Las voces corresponden a un idioma que este parche no conoce.',
                                'Original music recognized. The voices are in a language this patch does not know.'))
    else:
        r['estado'] = 'desconocido'
        if mus_rem != bool(voz_rem):
            r['detalle'].append(par('Mezcla de archivos originales y modificados.', 'Mix of original and modified files.'))
        r['detalle'].append(par('Los archivos no coinciden con ninguna versión conocida. No se modifica nada.',
                            'The files do not match any known version. Nothing is modified.'))
    return r


def videos_del_juego(res):
    return sorted(f for f in os.listdir(res) if f.lower().endswith('.san'))


# ------------------------------------------------------------------------------------------ instalar / desinstalar

def aplicar(res, nuevos_dir, marca_extra, progreso=None):
    """Pasa los archivos de nuevos_dir al juego, guardando los originales. Si algo falla, deshace todo.

    Los archivos ya deben estar generados y verificados: aca solo se mueven (mismo disco: es instantaneo).
    """
    base = os.path.join(res, CARPETA)
    resp = os.path.join(base, 'original')
    os.makedirs(resp, exist_ok=True)
    archivos = sorted(os.listdir(nuevos_dir))
    marca = {'version': VERSION, 'fecha': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), 'originales': {}, 'nuevos': {},
             'agregados': [], 'scummvm': []}
    marca.update(marca_extra)
    hechos = []
    try:
        for i, f in enumerate(archivos):
            actual = _real(res, f)
            nuevo = os.path.join(nuevos_dir, f)
            info_nuevo = {'size': os.path.getsize(nuevo), 'sha256': marca_extra.get('sha_nuevos', {}).get(f) or sha256_file(nuevo)}
            if actual:
                marca['originales'][os.path.basename(actual)] = {'size': os.path.getsize(actual), 'sha256': sha256_file(actual)}
                os.replace(actual, os.path.join(resp, os.path.basename(actual)))
                hechos.append(('mover', os.path.join(resp, os.path.basename(actual)), actual))
                destino = actual
            else:
                destino = os.path.join(res, f)
                marca['agregados'].append(f)
            os.replace(nuevo, destino)
            hechos.append(('nuevo', destino, nuevo))
            marca['nuevos'][os.path.basename(destino)] = info_nuevo
            if progreso:
                progreso(i + 1, len(archivos))
        marca.pop('sha_nuevos', None)
        json.dump(marca, open(os.path.join(base, MARCA), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    except Exception:
        for tipo, a, b in reversed(hechos):
            try:
                os.replace(a, b)
            except OSError:
                pass
        raise
    return marca


def guardar_marca(res, marca):
    json.dump(marca, open(os.path.join(res, CARPETA, MARCA), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)


def desinstalar(res, progreso=None):
    """Vuelve al juego original y comprueba cada archivo contra la huella guardada al instalar. Devuelve lineas de informe."""
    marca = leer_marca(res)
    if not marca or marca.get('danada'):
        raise Problema(t('No hay un registro válido del parche en esta carpeta.', 'There is no valid patch record in this folder.'))
    base = os.path.join(res, CARPETA)
    resp = os.path.join(base, 'original')
    falta = [f for f in marca['originales'] if not os.path.exists(os.path.join(resp, f))]
    if falta:
        raise Problema(t('Faltan copias de respaldo; no es posible volver atrás: ', 'Backups are missing; it is not possible to go back: ') + ', '.join(falta))
    informe = []
    total = len(marca['originales']) + len(marca['agregados'])
    n = 0
    for f in marca['originales']:
        actual = _real(res, f)
        if actual:
            os.remove(actual)
        os.replace(os.path.join(resp, f), os.path.join(res, f))
        n += 1
        if progreso:
            progreso(n, total * 2)
    for f in marca['agregados']:
        p = _real(res, f)
        if p:
            os.remove(p)
        n += 1
        if progreso:
            progreso(n, total * 2)
    mal = []
    for i, (f, v) in enumerate(marca['originales'].items()):
        p = os.path.join(res, f)
        if os.path.getsize(p) != v['size'] or sha256_file(p) != v['sha256']:
            mal.append(f)
        if progreso:
            progreso(total + i + 1, total * 2)
    for cambio in marca.get('scummvm', []):
        try:
            quitar_ajuste(cambio)
            informe.append(t('ScummVM: ajuste quitado en ', 'ScummVM: setting removed from ') + cambio['ini'])
        except Exception as ex:
            informe.append(t('ScummVM: no se pudo deshacer el ajuste en %s (%s)', 'ScummVM: the setting could not be undone in %s (%s)') % (cambio['ini'], ex))
    if mal:
        raise Problema(t('Se restauraron los archivos, pero estos no coinciden con la huella original: ',
                         'The files were restored, but these do not match the original fingerprint: ') + ', '.join(mal))
    shutil.rmtree(base, ignore_errors=True)
    informe.insert(0, t('%d archivos originales restaurados y verificados; %d archivos del parche quitados.',
                        '%d original files restored and verified; %d patch files removed.') % (
        len(marca['originales']), len(marca['agregados'])))
    return informe


# ------------------------------------------------------------------------------------------ ScummVM

def programas_abiertos():
    """Nombres de programas abiertos que usan los archivos del juego o reescriben la configuracion."""
    try:
        out = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True, creationflags=0x08000000).stdout.lower()
    except Exception:
        return []
    return [n for n in ('scummvm.exe', 'retroarch.exe') if n in out]


def buscar_inis(extra=()):
    cands = [os.path.join(os.environ.get('APPDATA', ''), 'ScummVM', 'scummvm.ini')] + list(extra)
    return [c for c in cands if c and os.path.isfile(c)]


def _norm(p):
    return os.path.normcase(os.path.normpath(p.strip().strip('"'))).rstrip('\\')


def secciones_comi(ini, raiz, res):
    """Secciones del scummvm.ini que son este juego: [(nombre, tiene_el_ajuste)]."""
    try:
        txt = open(ini, encoding='utf-8', errors='replace').read()
    except OSError:
        return []
    out = []
    for m in re.finditer(r'(?ms)^\[([^\]\r\n]+)\][^\n]*\n(.*?)(?=^\[|\Z)', txt):
        nombre, cuerpo = m.group(1), m.group(2)
        if nombre.lower() == 'scummvm':
            continue
        kv = dict((a.strip().lower(), b.strip()) for a, b in re.findall(r'(?m)^([^=\r\n#;]+)=(.*)$', cuerpo))
        bajo = nombre.lower()
        if not (kv.get('gameid', '').lower() == 'comi' or bajo == 'comi' or bajo.startswith(('comi-', 'comi_'))):
            continue
        if 'path' in kv and _norm(kv['path']) not in (_norm(raiz), _norm(res)):
            continue
        out.append((nombre, kv.get(AJUSTE[0]) == AJUSTE[1]))
    return out


def poner_ajuste(ini, seccion):
    """Pone dimuse_sample_rate=44100 en la seccion. Devuelve el registro para deshacerlo."""
    raw = open(ini, 'rb').read()
    nl = b'\r\n' if b'\r\n' in raw else b'\n'
    txt = raw.decode('utf-8', errors='surrogateescape')
    m = re.search(r'(?ms)^\[' + re.escape(seccion) + r'\][^\n]*\n(.*?)(?=^\[|\Z)', txt)
    if not m:
        raise Problema(t('No se encontró la sección [%s] en %s', 'Section [%s] was not found in %s') % (seccion, ini))
    cuerpo = m.group(1)
    previo = re.search(r'(?m)^' + AJUSTE[0] + r'[ \t]*=[ \t]*([^\r\n]*)', cuerpo)
    antes = previo.group(1).strip() if previo else None
    linea = '%s=%s' % AJUSTE
    if previo:
        nuevo = cuerpo[:previo.start()] + linea + cuerpo[previo.end():]
    else:
        nuevo = linea + nl.decode() + cuerpo
    if nuevo != cuerpo:
        copia = ini + '.antes_comi_remaster'
        if not os.path.exists(copia):
            shutil.copy2(ini, copia)
        txt = txt[:m.start(1)] + nuevo + txt[m.end(1):]
        open(ini, 'wb').write(txt.encode('utf-8', errors='surrogateescape'))
    return {'ini': ini, 'seccion': seccion, 'antes': antes}


def quitar_ajuste(cambio):
    ini, seccion, antes = cambio['ini'], cambio['seccion'], cambio.get('antes')
    if not os.path.isfile(ini):
        return
    txt = open(ini, 'rb').read().decode('utf-8', errors='surrogateescape')
    m = re.search(r'(?ms)^\[' + re.escape(seccion) + r'\][^\n]*\n(.*?)(?=^\[|\Z)', txt)
    if not m:
        return
    cuerpo = m.group(1)
    if antes is None:
        nuevo = re.sub(r'(?m)^' + AJUSTE[0] + r'[ \t]*=[^\r\n]*(\r?\n|\Z)', '', cuerpo, count=1)
    else:
        nuevo = re.sub(r'(?m)^' + AJUSTE[0] + r'[ \t]*=[^\r\n]*', lambda q: '%s=%s' % (AJUSTE[0], antes), cuerpo, count=1)
    open(ini, 'wb').write((txt[:m.start(1)] + nuevo + txt[m.end(1):]).encode('utf-8', errors='surrogateescape'))


def gb(n):
    return '%.1f GB' % (n / 1e9) if n >= 1e9 else '%.0f MB' % (n / 1e6)
