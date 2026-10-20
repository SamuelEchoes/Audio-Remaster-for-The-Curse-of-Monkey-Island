# Audio Remaster for The Curse of Monkey Island
# Copyright (C) 2026 SamuelEchoes
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.

"""Genera datos/*.json: huellas de los archivos conocidos, recetas del proceso y firmas de referencia del resultado.

Lo usa solo el autor: necesita la carpeta de trabajo del proyecto (audio original, resultado de referencia, banda de
sonido y los analisis de coincidencias), que no se publica porque contiene el audio del juego.
Uso: python herramientas/generar_datos.py <carpeta de trabajo> <RESOURCE del juego en castellano> <RESOURCE del juego en ingles>
"""
import glob, hashlib, json, os, sys, zipfile
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, 'comi', 'motor'))
import numpy as np
import soundfile as sf
from comi import motor, pak
import bun
if len(sys.argv) != 4:
    sys.exit(__doc__)
R = sys.argv[1]
G = {'es': sys.argv[2], 'en': sys.argv[3]}
ORIG = {'es': os.path.join(R, 'original', 'es'), 'en': G['en']}
LISTO = {'es': os.path.join(R, 'listo'), 'en': os.path.join(R, 'listo_en')}
VID = {'es': os.path.join(R, 'videos_final'), 'en': os.path.join(R, 'videos_final_en')}
D = os.path.join(RAIZ, 'datos'); os.makedirs(D, exist_ok=True)
sha = pak.sha256_file
def dump(name, obj):
    json.dump(obj, open(os.path.join(D, name), 'w', encoding='utf-8'), separators=(',', ':'), ensure_ascii=False)
    print(name, os.path.getsize(os.path.join(D, name)) // 1024, 'KB', flush=True)

def firma_ogg(path, paso=4096):
    y, sr = sf.read(path, dtype='float32', always_2d=True)
    m = y.mean(axis=1) * 32768.0; n = len(m) // paso
    rms = np.sqrt((m[:n * paso].reshape(n, paso) ** 2).mean(axis=1)) if n else np.zeros(0)
    return {'frames': len(y), 'niv': np.clip(np.round(2 * 20 * np.log10(rms + 1.0)), 0, 255).astype(np.uint8).tobytes().hex()}

# ---- huellas
h = {'musica': {'MUSDISK%d.BUN' % n: {'sha256': sha(os.path.join(R, 'original', 'MUSDISK%d.BUN' % n)), 'size': os.path.getsize(os.path.join(R, 'original', 'MUSDISK%d.BUN' % n))} for n in (1, 2)},
     'musica_remaster': {'MUSDISK%d.BUN' % n: {'sha256': sha(os.path.join(R, 'listo', 'MUSDISK%d.BUN' % n)), 'size': os.path.getsize(os.path.join(R, 'listo', 'MUSDISK%d.BUN' % n))} for n in (1, 2)},
     'idiomas': {}}
for lang, nombre in (('es', 'Castellano'), ('en', 'English')):
    x = {'nombre': nombre, 'voces': {}, 'voces_remaster': {}, 'videos': {}, 'videos_remaster': {}}
    for n in (1, 2):
        f = 'VOXDISK%d.BUN' % n
        x['voces'][f] = {'sha256': sha(os.path.join(ORIG[lang], f)), 'size': os.path.getsize(os.path.join(ORIG[lang], f))}
        x['voces_remaster'][f] = {'sha256': sha(os.path.join(LISTO[lang], f)), 'size': os.path.getsize(os.path.join(LISTO[lang], f))}
    for s in sorted(glob.glob(os.path.join(G[lang], '*.SAN'))):
        b = os.path.basename(s)
        x['videos'][b] = {'sha256': sha(s), 'size': os.path.getsize(s)}
        o = os.path.join(VID[lang], b[:-4] + '.ogg')
        x['videos_remaster'][b[:-4] + '.ogg'] = {'sha256': sha(o), 'size': os.path.getsize(o)}
    x['language_tab'] = sha(os.path.join(G[lang], 'LANGUAGE.TAB'))
    h['idiomas'][lang] = x
dump('huellas.json', h)

# ---- banda de sonido
z = os.path.join(R, 'ost_completo', 'The_Curse_of_Monkey_Island_-_FLAC.zip')
flacdir = glob.glob(os.path.join(R, 'ost_completo', 'flac', '*'))[0]
ost = {'zip': os.path.basename(z), 'size': os.path.getsize(z), 'sha256': sha(z), 'md5': hashlib.md5(open(z, 'rb').read()).hexdigest(),
       'fuentes': [{'id': 'mixnmojo', 'nombre': 'Mixnmojo', 'url': 'https://mixnmojo.com/Music/CMI/The_Curse_of_Monkey_Island_-_FLAC.zip'},
                   {'id': 'archive', 'nombre': 'Internet Archive', 'url': 'https://archive.org/download/the-curse-of-monkey-island-soundtrack/The_Curse_of_Monkey_Island_-_FLAC.zip'}],
       'temas': {os.path.basename(f): {'sha256': sha(f), 'size': os.path.getsize(f)} for f in sorted(glob.glob(os.path.join(flacdir, '*.flac')))}}
with zipfile.ZipFile(z) as zf:
    ost['en_zip'] = sorted(i.filename for i in zf.infolist() if i.filename.lower().endswith('.flac'))[:3]
dump('banda.json', ost)

# ---- recetas
rec = {'musica': {}, 'videos': {}}
for n in (1, 2):
    cm = json.load(open(os.path.join(R, 'crossmatch_MUSDISK%d.json' % n), encoding='utf-8'))
    rec['musica'][str(n)] = {k: v.get('tema') for k, v in cm.items() if 'error' not in v}
scan = json.load(open(os.path.join(R, 'scan_videos.json'), encoding='utf-8'))
tema = lambda num: [t for t in ost['temas'] if t.startswith(num + ' - ')][0]
extra = {'CURSERNG.SAN': [(tema('12'), 10.8)], 'NEWBOOTS.SAN': [(tema('33'), 0.0)], 'MORESLAW.SAN': [(tema('57'), 0.0)]}
for k, v in scan.items():
    rec['videos'][k] = [[t['tema'], t['empieza_en_video']] for t in v.get('temas', [])] + [list(e) for e in extra.get(k, [])]
dump('recetas.json', rec)

# ---- firmas de referencia
fir = {'musica': {}, 'voces': {}, 'videos': {}}
for n in (1, 2):
    b = bun.Bun(os.path.join(R, 'listo', 'MUSDISK%d.BUN' % n))
    fir['musica'][str(n)] = {e['name']: motor.firma(b.raw(e)) for e in b.entries if b.raw(e)[:4] == b'iMUS'}
for lang in ('es', 'en'):
    fir['voces'][lang] = {}
    for n in (1, 2):
        b = bun.Bun(os.path.join(LISTO[lang], 'VOXDISK%d.BUN' % n))
        fir['voces'][lang][str(n)] = {e['name']: motor.firma(b.raw(e)) for e in b.entries if b.raw(e)[:4] == b'iMUS'}
    fir['videos'][lang] = {os.path.basename(o): firma_ogg(o) for o in sorted(glob.glob(os.path.join(VID[lang], '*.ogg')))}
dump('firmas.json', fir)
