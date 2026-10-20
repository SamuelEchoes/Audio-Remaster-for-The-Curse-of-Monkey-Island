# Audio Remaster for The Curse of Monkey Island
# Copyright (C) 2026 SamuelEchoes
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.

"""Modo sin ventana, para pruebas y para quien quiera automatizar.

  <exe> --auto <carpeta del juego> [--zip <banda.zip>] [--desinstalar] [--ini <scummvm.ini>] [--informe <archivo.txt>] [--en]

Escribe todo en el informe y termina con codigo 0 si todo salio bien, 1 si hubo un problema. Con --en el informe sale en
ingles y se llama 'COMI Audio Remaster - automatic report.txt'; sin eso, en castellano ('... - informe automatico.txt').
Por defecto queda junto al programa. --uninstall equivale a --desinstalar y --report a --informe.
"""
import os
import time
import traceback

from . import juego, operaciones as op, textos
from .textos import t, tr


def correr(modo, argv):
    def arg(*nombres):
        for nombre in nombres:
            if nombre in argv and argv.index(nombre) + 1 < len(argv):
                return argv[argv.index(nombre) + 1]
        return None
    textos.IDIOMA[0] = 'en' if '--en' in argv else 'es'
    carpeta = arg('--auto')
    informe = arg('--informe', '--report') or os.path.join(op.carpeta_del_programa(), textos.informe_auto_nombre())
    f = open(informe, 'w', encoding='utf-8')
    t0 = time.time()

    def log(s):
        f.write('%6.0f s  %s\n' % (time.time() - t0, s))
        f.flush()
    ult = [0.0]

    def prog(fr, s):
        if time.time() - ult[0] > 20:
            ult[0] = time.time()
            log('   ... %3.0f %%  %s' % (100 * fr, s))
    cod = 1
    try:
        H = op.cargar('huellas.json')
        e = juego.detectar(carpeta, H)
        log(t('modo %s | carpeta %s', 'mode %s | folder %s') % (t(*textos.par_modo(modo)), carpeta))
        log(t('estado: %s | idioma: %s | %s', 'state: %s | language: %s | %s') % (
            textos.estado_txt(e['estado']), textos.idioma_txt(e['idioma']), ' / '.join(tr(d) for d in e['detalle'])))
        if '--desinstalar' in argv or '--uninstall' in argv:
            if e['estado'] not in ('parcheado', 'parcheado_alterado'):
                raise juego.Problema(t('No hay un parche instalado en esa carpeta.', 'There is no patch installed in that folder.'))
            for linea in juego.desinstalar(e['res']):
                log(linea)
        else:
            if e['estado'] != 'original' or (modo == 'completo' and e['idioma'] not in H['idiomas']):
                raise juego.Problema(t('No es posible instalar sobre este estado.', 'It is not possible to install over this state.'))
            abiertos = juego.programas_abiertos()
            if abiertos:
                raise juego.Problema(t('Hay programas abiertos que usan el juego: ', 'There are open programs using the game: ') + ', '.join(abiertos))
            inis = []
            for ini in juego.buscar_inis([arg('--ini')] if arg('--ini') else []):
                inis += [(ini, sec) for sec, _ in juego.secciones_comi(ini, e.get('raiz', e['res']), e['res'])]
            libre = juego.espacio_libre(e['res'])
            if modo == 'completo':
                paqs = op.buscar_paquetes()
                need, falta = op.espacio_completo(e['idioma'], paqs)
                if falta or libre < need:
                    raise juego.Problema(t('Faltan paquetes (%s) o espacio (%s de %s).', 'Packages (%s) or space (%s of %s) are missing.') % (
                        ', '.join(falta) or '-', juego.gb(libre), juego.gb(need)))
                m = op.instalar_completo(e, paqs, inis, log, prog)
            else:
                z = arg('--zip')
                if not z or not os.path.isfile(z):
                    raise juego.Problema(t('En modo automático se debe indicar --zip <archivo de la banda de sonido>.',
                                           'In automatic mode --zip <soundtrack file> is required.'))
                if libre < op.ESPACIO_RECONSTRUIR:
                    raise juego.Problema(t('Falta espacio: %s de %s.', 'Not enough space: %s of %s.') % (juego.gb(libre), juego.gb(op.ESPACIO_RECONSTRUIR)))
                m = op.instalar_reconstruyendo(e, z, inis, log, prog)
                v = m.get('validacion') or {}
                log(t('validación: %d pistas de música, %d frases de voz, %d videos', 'validation: %d music tracks, %d voice lines, %d videos') % (
                    v.get('musica', 0), v.get('voces', 0), v.get('videos', 0)))
        e2 = juego.detectar(carpeta, H)
        log(t('estado final: %s | idioma: %s', 'final state: %s | language: %s') % (textos.estado_txt(e2['estado']), textos.idioma_txt(e2['idioma'])))
        log(t('RESULTADO: OK', 'RESULT: OK'))
        cod = 0
    except juego.Problema as ex:
        log(t('RESULTADO: PROBLEMA - %s', 'RESULT: PROBLEM - %s') % ex)
    except Exception:
        log(traceback.format_exc())
        log(t('RESULTADO: ERROR INESPERADO', 'RESULT: UNEXPECTED ERROR'))
    f.close()
    return cod
