# Audio Remaster for The Curse of Monkey Island
# Copyright (C) 2026 SamuelEchoes
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.

"""Idioma del instalador: un solo lugar para la interfaz, el registro de proceso, los informes y sus nombres.

Cada texto se escribe en el idioma que esta elegido EN EL MOMENTO en que se genera. La interfaz no deja cambiar de
idioma mientras corre una operacion, asi que cada informe queda entero en un idioma.
"""
import re

IDIOMA = ['es']


def t(es, en):
    return es if IDIOMA[0] == 'es' else en


def tr(x):
    """Texto guardado como par (castellano, ingles) -> el del idioma actual. Si ya es un texto, queda igual."""
    return t(*x) if isinstance(x, tuple) else x


def par(es, en, *args):
    """Par (castellano, ingles) con los mismos valores puestos en los dos."""
    return (es % args, en % args) if args else (es, en)


NOMBRES_IDIOMA = {'es': ('Castellano', 'Spanish'), 'en': ('Inglés', 'English')}


def nombre_idioma(cod):
    return t(*NOMBRES_IDIOMA[cod]) if cod in NOMBRES_IDIOMA else None


def par_idioma(cod):
    return NOMBRES_IDIOMA.get(cod, ('?', '?'))


MODOS = {'completo': ('completo', 'full'), 'reconstruido': ('reconstruido', 'rebuilt'), 'reconstruye': ('reconstruye', 'rebuild')}


def par_modo(m):
    return MODOS.get(m, (m or '?', m or '?'))


ESTADOS = {'original': 'original', 'parcheado': 'patched', 'parcheado_alterado': 'patched_modified',
           'remaster_sin_respaldo': 'remaster_without_backup', 'desconocido': 'unknown', 'incompleto': 'incomplete',
           'no_encontrado': 'not_found'}


def estado_txt(e):
    """Codigo interno del estado -> como se escribe en un informe."""
    return e if IDIOMA[0] == 'es' else ESTADOS.get(e, e)


def idioma_txt(cod):
    return t('otro', 'other') if cod == 'otro' else (cod or '-')


def informe_nombre():
    return t('COMI Audio Remaster - informe.txt', 'COMI Audio Remaster - report.txt')


def informe_auto_nombre():
    return t('COMI Audio Remaster - informe automatico.txt', 'COMI Audio Remaster - automatic report.txt')


# Detalles tecnicos que devuelve el motor (corre en otros procesos, siempre en castellano y sin acentos).
_MOTOR = [
    ('distinto orden o cantidad de entradas', 'different order or number of entries'),
    ('archivo auxiliar modificado', 'auxiliary file modified'),
    ('no esta sin comprimir', 'not uncompressed'),
    ('cabecera o tamano distintos', 'different header or size'),
    ('posicion fuera del audio', 'position outside the audio'),
    ('audio en silencio', 'silent audio'),
    ('tamano de datos', 'data size'),
    ('tamano total', 'total size'),
    ('largo distinto', 'different length'),
    ('de bloques fuera de tolerancia', 'of blocks out of tolerance'),
    ('canales/bits', 'channels/bits'),
    ('frecuencia', 'sample rate'),
    ('regiones', 'regions'),
    ('saltos', 'jumps'),
    ('(archivo)', '(file)'),
]


def motor(s):
    """Traduce un detalle del motor cuando la interfaz esta en ingles."""
    s = str(s)
    if IDIOMA[0] == 'es':
        return s
    for es, en in _MOTOR:
        s = s.replace(es, en)
    return re.sub(r'\bfin\b', 'end', s)
