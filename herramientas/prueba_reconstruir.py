# Audio Remaster for The Curse of Monkey Island
# Copyright (C) 2026 SamuelEchoes
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.

"""Prueba de punta a punta del instalador que reconstruye, sin ventana, sobre una COPIA del juego.

Instala, compara con la referencia y desinstala; al final controla que la carpeta quede identica a la de antes.
Uso: python herramientas/prueba_reconstruir.py <banda.zip> es=<copia del juego> [en=<copia del juego>]
"""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if __name__ == '__main__':
    from comi import juego, operaciones as op, pak
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    H = op.cargar('huellas.json')
    Z = sys.argv[1]
    for lang, carpeta in [(a.split('=')[0], a.split('=')[1]) for a in sys.argv[2:]]:
        carpeta = os.path.abspath(carpeta); t = time.time()
        e = juego.detectar(carpeta, H); print(lang, '| antes:', e['estado'], e['idioma'], flush=True)
        antes = {f: pak.sha256_file(os.path.join(e['res'], f)) for f in os.listdir(e['res']) if os.path.isfile(os.path.join(e['res'], f))}
        ult = [0]
        def pr(f, s):
            if time.time() - ult[0] > 30: ult[0] = time.time(); print('      %3.0f %%  %s' % (100 * f, s), flush=True)
        m = op.instalar_reconstruyendo(e, Z, [], lambda s: print('   ', s, flush=True), pr)
        print('   TIEMPO TOTAL: %.0f s | validacion: %s' % (time.time() - t, m.get('validacion')), flush=True)
        e2 = juego.detectar(carpeta, H); print('   despues:', e2['estado'], e2['idioma'])
        ref = H['idiomas'].get(lang if lang in H['idiomas'] else 'en')
        for b in juego.BUNS:
            got = pak.sha256_file(os.path.join(e['res'], b)); want = (H['musica_remaster'] if b.startswith('MUS') else ref['voces_remaster'])[b]['sha256']
            print('   %s: %s' % (b, 'IDENTICO a la referencia' if got == want else 'distinto byte a byte (validado por firma)'))
        ig = sum(1 for f, v in ref['videos_remaster'].items() if pak.sha256_file(os.path.join(e['res'], f)) == v['sha256'])
        print('   videos identicos a la referencia: %d de %d' % (ig, len(ref['videos_remaster'])))
        inf = juego.desinstalar(e['res']); print('   desinstalar:', inf)
        despues = {f: pak.sha256_file(os.path.join(e['res'], f)) for f in os.listdir(e['res']) if os.path.isfile(os.path.join(e['res'], f))}
        print('   carpeta identica a la de antes:', antes == despues, flush=True)
