# Audio Remaster for The Curse of Monkey Island
# Copyright (C) 2026 SamuelEchoes
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.

"""Interfaz del instalador (tkinter): asistente por pasos, oscuro y discreto. Sirve para los dos modos."""
import os
import queue
import sys
import threading
import time
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, ttk

from . import juego, operaciones as op, textos
from .juego import Problema, gb
from .textos import IDIOMA, t, tr, nombre_idioma

BG, PANEL, LINEA = '#1D2024', '#262A30', '#343941'
TXT, TENUE, ACENTO = '#D9DCE1', '#8C929B', '#6F93AD'
OK, AVISO, MAL = '#78A886', '#C7A765', '#C2706F'
F = 'Segoe UI'
ESCALA = [1.0]                                  # pixeles por pixel de 96 ppp; se mide al crear la ventana


def px(n):
    """Medida en pixeles a 100 % de escala -> pixeles reales (acepta tuplas, como pady=px((4, 10)))."""
    return tuple(px(v) for v in n) if isinstance(n, tuple) else int(round(n * ESCALA[0]))


def _nitidez():
    """Avisa a Windows que el programa maneja la escala de pantalla. Si no, con escala mayor a 100 % Windows estira
    la ventana ya dibujada y los textos y el icono se ven borrosos. Va antes de crear la primera ventana."""
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


class Boton(tk.Label):
    def __init__(self, master, texto, cmd, tipo='normal', **kw):
        self.colores = {'primario': (ACENTO, '#101316', '#86A9C2'), 'normal': (LINEA, TXT, '#414751'),
                        'peligro': ('#5A3A3A', '#F0D9D8', '#704646')}[tipo]
        super().__init__(master, text=texto, bg=self.colores[0], fg=self.colores[1], font=(F, 10, 'bold' if tipo == 'primario' else 'normal'),
                         padx=px(18), pady=px(7), cursor='hand2', **kw)
        self.cmd, self.activo = cmd, True
        self.bind('<Button-1>', lambda e: self.activo and self.cmd())
        self.bind('<Enter>', lambda e: self.activo and self.config(bg=self.colores[2]))
        self.bind('<Leave>', lambda e: self.activo and self.config(bg=self.colores[0]))

    def habilitar(self, si):
        self.activo = si
        self.config(bg=self.colores[0] if si else '#2B2F35', fg=self.colores[1] if si else '#5C626B', cursor='hand2' if si else 'arrow')


class App(tk.Tk):
    def __init__(self, modo):
        _nitidez()
        super().__init__()
        ESCALA[0] = max(self.winfo_fpixels('1i') / 96.0, 1.0)
        self.modo = modo                      # 'completo' o 'reconstruye'
        self.title('The Curse of Monkey Island - Audio Remaster')
        try:                                  # icono de la ventana y de sus dialogos
            self.iconbitmap(default=os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'datos', 'calavera.ico'))
        except Exception:
            pass
        self.configure(bg=BG)
        w, h = min(px(900), self.winfo_screenwidth() - 40), min(px(640), self.winfo_screenheight() - 80)
        self.geometry('%dx%d+%d+%d' % (w, h, (self.winfo_screenwidth() - w) // 2, max((self.winfo_screenheight() - h) // 2 - 20, 0)))
        self.minsize(min(px(820), w), min(px(580), h))
        st = ttk.Style(self)
        st.theme_use('clam')
        st.configure('B.Horizontal.TProgressbar', troughcolor=PANEL, background=ACENTO, bordercolor=PANEL, lightcolor=ACENTO, darkcolor=ACENTO, thickness=px(10))
        st.configure('TCheckbutton', background=BG, foreground=TXT, font=(F, 10), focuscolor=BG)
        st.map('TCheckbutton', background=[('active', BG)], foreground=[('disabled', TENUE)])
        st.configure('P.TCheckbutton', background=PANEL, foreground=TXT, font=(F, 10), focuscolor=PANEL)
        st.map('P.TCheckbutton', background=[('active', PANEL)])
        st.configure('P.TRadiobutton', background=PANEL, foreground=TXT, font=(F, 10), focuscolor=PANEL)
        st.map('P.TRadiobutton', background=[('active', PANEL)], foreground=[('disabled', TENUE)])
        for est in ('TCheckbutton', 'P.TCheckbutton', 'P.TRadiobutton'):
            st.configure(est, indicatorcolor=PANEL if est != 'TCheckbutton' else BG, indicatorbackground=LINEA, bordercolor=TENUE, lightcolor=LINEA, darkcolor=LINEA)
            st.map(est, indicatorcolor=[('selected', ACENTO), ('disabled', '#2B2F35')])
        self.q = queue.Queue()
        self.huellas = op.cargar('huellas.json')
        self.banda = op.cargar('banda.json') if modo == 'reconstruye' else None
        self.estado = None
        self.carpeta = tk.StringVar(value=self._sugerir_carpeta())
        self.zip_local = None
        self.fuente = tk.StringVar(value='')
        self.fuentes_ok = {}
        self.inis_extra = []
        self.cancelar = False
        self.trabajando = False
        self.registro = []
        self.pasos = ['inicio', 'juego'] + (['banda'] if modo == 'reconstruye' else []) + ['resumen', 'progreso', 'fin']
        self.paso = 'inicio'
        self._armar()
        self.mostrar('inicio')
        self.after(80, self._bombear)
        self.protocol('WM_DELETE_WINDOW', self._cerrar)

    # ---------------------------------------------------------------- estructura
    def _armar(self):
        self.lado = tk.Frame(self, bg=PANEL, width=px(220))
        self.lado.pack(side='left', fill='y')
        self.lado.pack_propagate(False)
        tk.Label(self.lado, text='AUDIO\nREMASTER', bg=PANEL, fg=TXT, font=(F, 17, 'bold'), justify='left').pack(anchor='w', padx=px(22), pady=px((26, 0)))
        tk.Label(self.lado, text='The Curse of Monkey Island', bg=PANEL, fg=TENUE, font=(F, 9)).pack(anchor='w', padx=px(22), pady=px((4, 26)))
        self.marcas = {}
        self.caja_pasos = tk.Frame(self.lado, bg=PANEL)
        self.caja_pasos.pack(fill='x')
        pie = tk.Frame(self.lado, bg=PANEL)
        pie.pack(side='bottom', fill='x', padx=px(22), pady=px(18))
        self.lbl_idioma = tk.Label(pie, text='', bg=PANEL, fg=ACENTO, font=(F, 9, 'underline'), cursor='hand2')
        self.lbl_idioma.pack(anchor='w')
        self.lbl_idioma.bind('<Button-1>', lambda e: self._cambiar_idioma())
        tk.Label(pie, text='v%s  -  %s' % (juego.VERSION, t(*textos.par_modo(self.modo))), bg=PANEL, fg='#5F656E', font=(F, 8)).pack(anchor='w', pady=px((6, 0)))
        self.cuerpo = tk.Frame(self, bg=BG)
        self.cuerpo.pack(side='left', fill='both', expand=True)
        self.contenido = tk.Frame(self.cuerpo, bg=BG)
        self.contenido.pack(fill='both', expand=True, padx=px(34), pady=px((28, 0)))
        self.barra = tk.Frame(self.cuerpo, bg=BG)
        self.barra.pack(fill='x', padx=px(34), pady=px(22))

    def _nombres_pasos(self):
        return {'inicio': t('Inicio', 'Welcome'), 'juego': t('El juego', 'The game'), 'banda': t('Banda de sonido', 'Soundtrack'),
                'resumen': t('Resumen', 'Summary'), 'progreso': t('Proceso', 'Progress'), 'fin': t('Resultado', 'Result')}

    def _pintar_pasos(self):
        for w in self.caja_pasos.winfo_children():
            w.destroy()
        actual = self.pasos.index(self.paso)
        for i, p in enumerate(self.pasos):
            fila = tk.Frame(self.caja_pasos, bg=PANEL)
            fila.pack(fill='x', padx=px(22), pady=px(5))
            col = TXT if i == actual else (OK if i < actual else '#666C75')
            tk.Label(fila, text='●' if i <= actual else '○', bg=PANEL, fg=ACENTO if i == actual else col, font=(F, 9)).pack(side='left')
            tk.Label(fila, text=self._nombres_pasos()[p], bg=PANEL, fg=col, font=(F, 10, 'bold' if i == actual else 'normal')).pack(side='left', padx=px(9))
        self.lbl_idioma.config(text='English' if IDIOMA[0] == 'es' else 'Castellano')

    def _cambiar_idioma(self):
        if self.trabajando:
            return
        IDIOMA[0] = 'en' if IDIOMA[0] == 'es' else 'es'
        self.mostrar(self.paso)

    def mostrar(self, paso):
        self.paso = paso
        for w in self.contenido.winfo_children() + self.barra.winfo_children():
            w.destroy()
        self._pintar_pasos()
        getattr(self, 'p_' + paso)()

    # ---------------------------------------------------------------- piezas
    def titulo(self, texto, sub=None):
        lbl = tk.Label(self.contenido, text=texto, bg=BG, fg=TXT, font=(F, 17, 'bold'), anchor='w', justify='left', wraplength=px(560))
        lbl.pack(fill='x')
        self._ajustar(lbl)
        if sub:
            lbl = tk.Label(self.contenido, text=sub, bg=BG, fg=TENUE, font=(F, 10), anchor='w', justify='left', wraplength=px(560))
            lbl.pack(fill='x', pady=px((6, 0)))
            self._ajustar(lbl)
        tk.Frame(self.contenido, bg=BG, height=px(16)).pack()

    def parrafo(self, texto, color=TXT, master=None, tam=10, pad=(0, 8)):
        m = master or self.contenido
        lbl = tk.Label(m, text=texto, bg=m['bg'], fg=color, font=(F, tam), anchor='w', justify='left', wraplength=px(520))
        lbl.pack(fill='x', pady=px(pad))
        self._ajustar(lbl)
        return lbl

    def _ajustar(self, lbl):
        lbl.bind('<Configure>', lambda e, w=lbl: w.config(wraplength=max(e.width - px(6), px(200))))

    def tarjeta(self, color=None):
        ext = tk.Frame(self.contenido, bg=color or LINEA)
        ext.pack(fill='x', pady=px((4, 10)))
        inn = tk.Frame(ext, bg=PANEL)
        inn.pack(fill='both', expand=True, padx=px((4 if color else 1, 1)), pady=px(1))
        caja = tk.Frame(inn, bg=PANEL)
        caja.pack(fill='both', expand=True, padx=px(16), pady=px(12))
        return caja

    def botones(self, *bs):
        """bs: (texto, cmd, tipo, lado). Devuelve los botones creados."""
        out = []
        for texto, cmd, tipo, lado in bs:
            b = Boton(self.barra, texto, cmd, tipo)
            b.pack(side=lado, padx=px((0, 10) if lado == 'left' else (10, 0)))
            out.append(b)
        return out

    def luz(self, master, color):
        c = tk.Canvas(master, width=px(16), height=px(16), bg=master['bg'], highlightthickness=0)
        c.create_oval(px(2), px(2), px(14), px(14), fill=color, outline=color)
        return c

    def _sugerir_carpeta(self):
        import re
        for ini in juego.buscar_inis():
            try:
                txt = open(ini, encoding='utf-8', errors='replace').read()
            except OSError:
                continue
            for m in re.finditer(r'(?ms)^\[[^\]]+\][^\n]*\n(.*?)(?=^\[|\Z)', txt):
                kv = dict((a.strip().lower(), b.strip()) for a, b in re.findall(r'(?m)^([^=\r\n#;]+)=(.*)$', m.group(1)))
                if kv.get('gameid', '').lower() == 'comi' and os.path.isdir(kv.get('path', '')):
                    return kv['path']
        return ''

    # ---------------------------------------------------------------- paso: inicio
    def p_inicio(self):
        self.titulo(t('Audio remasterizado', 'Remastered audio'),
                    t('Reemplaza la música comprimida del juego por la de la banda de sonido en alta calidad, y mejora las voces y el audio de los videos.',
                      'Replaces the compressed in-game music with the high quality soundtrack, and improves voices and video audio.'))
        c = self.tarjeta()
        for es, en in (('Funciona únicamente con ScummVM (o con RetroArch y el núcleo ScummVM).',
                        'It works only with ScummVM (or RetroArch with the ScummVM core).'),
                       ('No altera la música del juego: donde la banda de sonido es la misma grabación, se utiliza la banda de sonido; el resto conserva el audio del juego, mejorado.',
                        'It does not change the game music: where the soundtrack is the same recording, the soundtrack is used; everything else keeps the game audio, enhanced.'),
                       ('Conserva los archivos originales y puede desinstalarse desde este mismo programa.',
                        'Original files are kept, and the patch can be removed from this same program.')):
            self.parrafo('•  ' + t(es, en), master=c, pad=(2, 4))
        c = self.tarjeta(AVISO)
        self.parrafo(t('Partidas guardadas', 'Saved games'), AVISO, c, 10, (0, 2))
        self.parrafo(t('Las partidas guardadas ANTES de instalar el parche pueden reproducir la música a mitad de velocidad al cargarlas. Se soluciona pasando por una sala con otra música y guardando nuevamente, o comenzando una partida nueva.',
                       'Saved games made BEFORE installing the patch may play music at half speed when loaded. Fix: walk into a room with different music and save again, or start a new game.'),
                     master=c, pad=(0, 0))
        if self.modo == 'reconstruye':
            self.parrafo(t('Este instalador no incluye audio: lo genera en su equipo a partir de su juego y de la banda de sonido, que se descarga por separado (1,2 GB). Demora entre 10 y 40 minutos según el equipo.',
                           'This installer ships no audio: it builds it on your PC from your game and the soundtrack, downloaded separately (1.2 GB). It takes 10 to 40 minutes depending on the PC.'), TENUE)
        self.botones((t('Siguiente', 'Next'), lambda: self.mostrar('juego'), 'primario', 'right'))

    # ---------------------------------------------------------------- paso: juego
    def p_juego(self):
        self.titulo(t('Dónde está el juego', 'Where the game is'),
                    t('Seleccione la carpeta del juego (la que contiene COMI.LA0, o su carpeta RESOURCE).', 'Select the game folder (the one containing COMI.LA0, or its RESOURCE folder).'))
        fila = tk.Frame(self.contenido, bg=BG)
        fila.pack(fill='x')
        e = tk.Entry(fila, textvariable=self.carpeta, bg=PANEL, fg=TXT, insertbackground=TXT, relief='flat', font=(F, 10))
        e.pack(side='left', fill='x', expand=True, ipady=px(7), padx=px((0, 10)))
        Boton(fila, t('Examinar...', 'Browse...'), self._examinar).pack(side='left')
        tk.Frame(self.contenido, bg=BG, height=px(10)).pack()
        fila2 = tk.Frame(self.contenido, bg=BG)
        fila2.pack(fill='x')
        self.b_analizar = Boton(fila2, t('Analizar', 'Analyze'), self._analizar, 'primario')
        self.b_analizar.pack(side='left')
        self.lbl_anal = tk.Label(fila2, text='', bg=BG, fg=TENUE, font=(F, 9))
        self.lbl_anal.pack(side='left', padx=px(12))
        self.zona = tk.Frame(self.contenido, bg=BG)
        self.zona.pack(fill='both', expand=True, pady=px((12, 0)))
        self.b_sig, = self.botones((t('Siguiente', 'Next'), self._tras_juego, 'primario', 'right'))
        self.botones((t('Atrás', 'Back'), lambda: self.mostrar('inicio'), 'normal', 'right'))
        self.b_sig.habilitar(False)
        if self.estado and self.estado.get('carpeta') == self.carpeta.get():
            self._pintar_estado()

    def _examinar(self):
        d = filedialog.askdirectory(title=t('Carpeta del juego', 'Game folder'), initialdir=self.carpeta.get() or None)
        if d:
            self.carpeta.set(os.path.normpath(d))
            self._analizar()

    def _analizar(self):
        if self.trabajando:
            return
        carpeta = self.carpeta.get().strip().strip('"')
        self.trabajando = True
        self.b_analizar.habilitar(False)
        self.lbl_anal.config(text=t('Leyendo los archivos del juego...', 'Reading the game files...'))

        def tarea():
            try:
                e = juego.detectar(carpeta, self.huellas, lambda d, tt: self.q.put(('anal', d / max(tt, 1))))
                e['carpeta'] = carpeta
                self.q.put(('estado', e))
            except Exception as ex:
                self.q.put(('estado', {'estado': 'desconocido', 'idioma': None, 'res': None, 'detalle': [str(ex)], 'carpeta': carpeta}))
        threading.Thread(target=tarea, daemon=True).start()

    def _textos_estado(self, e):
        nombre = nombre_idioma(e.get('idioma'))
        est = e['estado']
        if est == 'original' and e['idioma'] in self.huellas['idiomas']:
            return OK, t('Juego original - %s', 'Original game - %s') % nombre, t('El parche puede instalarse.', 'The patch can be installed.'), True
        if est == 'original':
            if self.modo == 'reconstruye':
                return AVISO, t('Juego original - idioma no reconocido', 'Original game - unrecognized language'), \
                    t('La música es la conocida. Las voces y los videos se procesan con el mismo método.',
                      'The music is the known one. Voices and videos are processed with the same method.'), True
            return MAL, t('Juego original - idioma no incluido', 'Original game - language not included'), \
                t('Este instalador solo incluye audio en castellano e inglés. Para otro idioma se requiere el instalador que reconstruye.',
                  'This installer only includes Spanish and English audio. Other languages require the rebuilding installer.'), False
        if est == 'parcheado':
            return ACENTO, t('Parche instalado - %s', 'Patch installed - %s') % (nombre or '?'), t('Puede desinstalarse para volver al juego original.', 'It can be removed to go back to the original game.'), False
        if est == 'parcheado_alterado':
            return AVISO, t('Parche instalado, con cambios', 'Patch installed, with changes'), t('Algún archivo fue modificado después de la instalación. Puede intentarse la restauración con las copias de respaldo.',
                                                                                              'Some file was modified after installation. Restoring from the backups can be attempted.'), False
        if est == 'remaster_sin_respaldo':
            return ACENTO, t('Ya tiene el audio remasterizado', 'Remastered audio already present'), t('Fue colocado manualmente, sin copias de respaldo en esta carpeta. No hay nada para instalar ni para desinstalar.',
                                                                                                     'It was placed by hand, with no backups in this folder. Nothing to install or remove.'), False
        if est == 'incompleto':
            return MAL, t('Faltan archivos del juego', 'Game files are missing'), '', False
        if est == 'no_encontrado':
            return MAL, t('No se encontró el juego en esa carpeta', 'The game was not found in that folder'), '', False
        return MAL, t('Versión desconocida', 'Unknown version'), t('Los archivos no coinciden con ninguna versión conocida. Por seguridad, no se modifica nada.',
                                                                    'The files do not match any known version. For safety, nothing is modified.'), False

    def _pintar_estado(self):
        for w in self.zona.winfo_children():
            w.destroy()
        e = self.estado
        color, tit, sub, puede = self._textos_estado(e)
        ext = tk.Frame(self.zona, bg=color)
        ext.pack(fill='x')
        inn = tk.Frame(ext, bg=PANEL)
        inn.pack(fill='both', padx=px((4, 0)))
        caja = tk.Frame(inn, bg=PANEL)
        caja.pack(fill='both', padx=px(16), pady=px(12))
        tk.Label(caja, text=tit, bg=PANEL, fg=color, font=(F, 13, 'bold'), anchor='w').pack(fill='x')
        if sub:
            self.parrafo(sub, master=caja, pad=(4, 4))
        for d in e.get('detalle', []):
            self.parrafo(tr(d), TENUE, caja, 9, (0, 0))
        if e.get('res'):
            self.parrafo(t('Carpeta de recursos: ', 'Resource folder: ') + e['res'], TENUE, caja, 9, (4, 0))
            self.parrafo(t('Espacio libre en ese disco: ', 'Free space on that drive: ') + gb(juego.espacio_libre(e['res'])), TENUE, caja, 9, (0, 0))
        if e['estado'] in ('parcheado', 'parcheado_alterado') and e.get('marca') and not e['marca'].get('danada'):
            fila = tk.Frame(self.zona, bg=BG)
            fila.pack(fill='x', pady=px(12))
            Boton(fila, t('Desinstalar el parche', 'Remove the patch'), self._confirmar_desinstalar, 'peligro').pack(side='left')
        self.b_sig.habilitar(puede)

    def _tras_juego(self):
        self.mostrar('banda' if self.modo == 'reconstruye' else 'resumen')

    # ---------------------------------------------------------------- paso: banda de sonido
    def p_banda(self):
        b = self.banda
        self.titulo(t('La banda de sonido', 'The soundtrack'),
                    t('Se requiere la edición en FLAC publicada por Mixnmojo (%s). El instalador verifica que sea exactamente esa edición: con otra, las posiciones no coinciden.',
                      'The FLAC edition published by Mixnmojo is required (%s). The installer verifies it is exactly that edition: with another one, positions do not match.') % gb(b['size']))
        c = self.tarjeta()
        self.parrafo(t('Descargarla ahora desde:', 'Download it now from:'), TENUE, c, 9, (0, 6))
        self.filas_fuente = {}
        for f in b['fuentes']:
            fila = tk.Frame(c, bg=PANEL)
            fila.pack(fill='x', pady=px(3))
            lz = self.luz(fila, '#5C626B')
            lz.pack(side='left', padx=px((0, 10)))
            rb = ttk.Radiobutton(fila, text=f['nombre'], value=f['id'], variable=self.fuente, style='P.TRadiobutton', command=self._act_banda)
            rb.pack(side='left')
            lbl = tk.Label(fila, text=t('verificando...', 'checking...'), bg=PANEL, fg=TENUE, font=(F, 9))
            lbl.pack(side='left', padx=px(12))
            self.filas_fuente[f['id']] = (lz, rb, lbl)
        self.parrafo(t('Verde: el archivo está disponible en este momento. Rojo: el sitio no responde.', 'Green: the file is available right now. Red: the site is not responding.'), TENUE, c, 9, (8, 0))
        c2 = self.tarjeta()
        fila = tk.Frame(c2, bg=PANEL)
        fila.pack(fill='x')
        ttk.Radiobutton(fila, text=t('Ya dispongo del archivo .zip', 'I already have the .zip file'), value='local', variable=self.fuente, style='P.TRadiobutton', command=self._elegir_zip).pack(side='left')
        self.lbl_zip = tk.Label(c2, text='', bg=PANEL, fg=TENUE, font=(F, 9), anchor='w', justify='left', wraplength=px(560))
        self.lbl_zip.pack(fill='x', pady=px((6, 0)))
        self.b_sig, = self.botones((t('Siguiente', 'Next'), lambda: self.mostrar('resumen'), 'primario', 'right'))
        self.botones((t('Atrás', 'Back'), lambda: self.mostrar('juego'), 'normal', 'right'))
        # si ya esta bajado en Descargas, se usa
        ya = os.path.join(self._descargas(), b['zip'])
        if not self.zip_local and os.path.isfile(ya) and os.path.getsize(ya) == b['size']:
            self.zip_local = ya
            self.fuente.set('local')
        self._act_banda()
        for f in b['fuentes']:
            if f['id'] in self.fuentes_ok:
                self._pintar_fuente(f['id'])
            else:
                threading.Thread(target=lambda f=f: self.q.put(('fuente', f['id'], op.fuente_disponible(f['url']))), daemon=True).start()

    def _descargas(self):
        d = os.path.join(os.path.expanduser('~'), 'Downloads')
        return d if os.path.isdir(d) else os.path.expanduser('~')

    def _pintar_fuente(self, fid):
        if self.paso != 'banda' or fid not in self.filas_fuente:
            return
        ok, size, det = self.fuentes_ok[fid]
        lz, rb, lbl = self.filas_fuente[fid]
        bien = ok and (size in (None, self.banda['size']))
        lz.delete('all')
        lz.create_oval(2, 2, 14, 14, fill='#7FCB93' if bien else '#D9706E', outline='#7FCB93' if bien else '#D9706E')
        if bien:
            lbl.config(text=t('disponible', 'available') + (' (%s)' % gb(size) if size else ''), fg=OK)
        elif ok:
            lbl.config(text=t('responde, pero el archivo no tiene el tamaño esperado', 'responds, but the file size is not the expected one'), fg=MAL)
        else:
            lbl.config(text=t('no disponible ahora', 'not available now'), fg=MAL)
        rb.state(['!disabled'] if bien else ['disabled'])
        if bien and not self.fuente.get():
            self.fuente.set(fid)
        self._act_banda()

    def _elegir_zip(self):
        p = filedialog.askopenfilename(title=self.banda['zip'], filetypes=[('ZIP', '*.zip')])
        if p:
            self.zip_local = os.path.normpath(p)
        elif not self.zip_local:
            self.fuente.set('')
        self._act_banda()

    def _act_banda(self):
        if self.paso != 'banda':
            return
        f = self.fuente.get()
        if f == 'local' and self.zip_local:
            ok = os.path.getsize(self.zip_local) == self.banda['size']
            self.lbl_zip.config(text=self.zip_local + '\n' + (t('Tamaño correcto; la huella se verifica antes de comenzar.', 'Size is correct; the fingerprint is verified before starting.') if ok else
                                                             t('El tamaño no coincide con el de la edición esperada.', 'Size does not match the expected edition.')), fg=TENUE if ok else MAL)
            self.b_sig.habilitar(ok)
        else:
            self.lbl_zip.config(text='')
            self.b_sig.habilitar(bool(f) and f != 'local')

    # ---------------------------------------------------------------- paso: resumen
    def _espacio(self):
        e = self.estado
        if self.modo == 'completo':
            need, falta = op.espacio_completo(e['idioma'], op.buscar_paquetes())
            return need + 200e6, falta
        need = op.ESPACIO_RECONSTRUIR
        return need, []

    def p_resumen(self):
        e = self.estado
        color, tit, _, _ = self._textos_estado(e)
        self.titulo(t('Antes de comenzar', 'Before starting'))
        c = self.tarjeta(color)
        tk.Label(c, text=t('Versión detectada: ', 'Detected version: ') + tit, bg=PANEL, fg=TXT, font=(F, 11, 'bold'), anchor='w').pack(fill='x')
        self.parrafo(e['res'], TENUE, c, 9, (2, 0))
        need, falta = self._espacio()
        libre = juego.espacio_libre(e['res'])
        alcanza = libre >= need and not falta
        c = self.tarjeta(OK if alcanza else MAL)
        if falta:
            self.parrafo(t('Faltan archivos del instalador: ', 'Installer files are missing: ') + ', '.join(falta), MAL, c, 10, (0, 0))
        else:
            self.parrafo(t('Espacio necesario en el disco del juego: %s. Libre: %s.', 'Space needed on the game drive: %s. Free: %s.') % (gb(need), gb(libre)),
                         TXT if alcanza else MAL, c, 10, (0, 2))
            if self.modo == 'reconstruye':
                self.parrafo(t('Gran parte es espacio de trabajo, que se libera al finalizar. El juego remasterizado ocupa unos 3,5 GB más que el original.',
                               'Most of it is working space, released at the end. The remastered game takes about 3.5 GB more than the original.'), TENUE, c, 9, (0, 0))
                if self.fuente.get() != 'local':
                    ld = juego.espacio_libre(self._descargas())
                    self.parrafo(t('La banda de sonido (%s) se descarga en %s (libre: %s).', 'The soundtrack (%s) is downloaded to %s (free: %s).') % (gb(self.banda['size']), self._descargas(), gb(ld)),
                                 TENUE if ld > self.banda['size'] * 1.05 else MAL, c, 9, (2, 0))
                    alcanza = alcanza and ld > self.banda['size'] * 1.05
        # ScummVM
        c = self.tarjeta()
        tk.Label(c, text='ScummVM', bg=PANEL, fg=TXT, font=(F, 10, 'bold'), anchor='w').pack(fill='x')
        self.parrafo(t('El audio nuevo requiere el ajuste  dimuse_sample_rate=44100  en la entrada del juego dentro de scummvm.ini. Sin ese ajuste, la música no se reproduce correctamente.',
                       'The new audio requires the setting  dimuse_sample_rate=44100  in the game entry inside scummvm.ini. Without it, music does not play correctly.'), TENUE, c, 9, (2, 6))
        self.vars_ini = []
        for ini in juego.buscar_inis(self.inis_extra):
            for sec, tiene in juego.secciones_comi(ini, e.get('raiz', e['res']), e['res']):
                v = tk.BooleanVar(value=True)
                ttk.Checkbutton(c, text='[%s]  %s%s' % (sec, ini, t('  (ya lo tiene)', '  (already set)') if tiene else ''), variable=v, style='P.TCheckbutton').pack(anchor='w')
                self.vars_ini.append((v, ini, sec))
        if not self.vars_ini:
            self.parrafo(t('No se encontró la entrada de este juego en ningún scummvm.ini. Puede indicar el archivo, o agregar la línea manualmente más tarde.',
                           'The entry for this game was not found in any scummvm.ini. You can select the file, or add the line manually later.'), AVISO, c, 9, (0, 4))
        lk = tk.Label(c, text=t('Indicar otro scummvm.ini (por ejemplo, el de RetroBat: bios\\scummvm.ini)...', 'Select another scummvm.ini (e.g. RetroBat: bios\\scummvm.ini)...'),
                      bg=PANEL, fg=ACENTO, font=(F, 9, 'underline'), cursor='hand2', anchor='w')
        lk.pack(fill='x', pady=px((6, 0)))
        lk.bind('<Button-1>', lambda ev: self._otro_ini())
        abiertos = juego.programas_abiertos()
        if abiertos:
            c = self.tarjeta(MAL)
            self.parrafo(t('Cierre %s antes de continuar: mantienen abiertos los archivos del juego o reescriben la configuración al salir.',
                           'Close %s before continuing: they hold the game files open or rewrite the configuration on exit.') % ' / '.join(abiertos), MAL, c, 10, (0, 0))
        self.v_aviso = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.contenido, text=t('Entiendo que las partidas guardadas anteriores pueden reproducirse a mitad de velocidad.', 'I understand that earlier saved games may play at half speed.'),
                        variable=self.v_aviso, command=lambda: self.b_inst.habilitar(self.v_aviso.get() and alcanza and not juego.programas_abiertos())).pack(anchor='w', pady=px((4, 0)))
        self.b_inst, = self.botones((t('Instalar', 'Install'), self._instalar, 'primario', 'right'))
        self.botones((t('Atrás', 'Back'), lambda: self.mostrar('banda' if self.modo == 'reconstruye' else 'juego'), 'normal', 'right'),
                     (t('Verificar nuevamente', 'Check again'), lambda: self.mostrar('resumen'), 'normal', 'left'))
        self.b_inst.habilitar(False)

    def _otro_ini(self):
        p = filedialog.askopenfilename(title='scummvm.ini', filetypes=[('scummvm.ini', '*.ini'), ('*', '*.*')])
        if p:
            self.inis_extra.append(os.path.normpath(p))
            self.mostrar('resumen')

    # ---------------------------------------------------------------- paso: progreso
    def p_progreso(self):
        self.titulo(self.tit_proc, self.sub_proc)
        self.lbl_et = tk.Label(self.contenido, text='', bg=BG, fg=TXT, font=(F, 10), anchor='w')
        self.lbl_et.pack(fill='x', pady=px((0, 6)))
        self.pb = ttk.Progressbar(self.contenido, style='B.Horizontal.TProgressbar', maximum=1000)
        self.pb.pack(fill='x')
        self.lbl_t = tk.Label(self.contenido, text='', bg=BG, fg=TENUE, font=(F, 9), anchor='w')
        self.lbl_t.pack(fill='x', pady=px((6, 10)))
        marco = tk.Frame(self.contenido, bg=LINEA)
        marco.pack(fill='both', expand=True)
        self.txt = tk.Text(marco, bg=PANEL, fg=TENUE, font=('Consolas', 9), relief='flat', wrap='word', state='disabled', padx=px(12), pady=px(10))
        self.txt.pack(fill='both', expand=True, padx=px(1), pady=px(1))
        for linea in self.registro:
            self._agregar(linea)
        self.b_canc, = self.botones((t('Cancelar', 'Cancel'), self._cancelar, 'normal', 'right'))

    def _agregar(self, linea):
        if self.paso != 'progreso':
            return
        self.txt.config(state='normal')
        self.txt.insert('end', linea + '\n')
        self.txt.see('end')
        self.txt.config(state='disabled')

    def _cancelar(self):
        if self.trabajando and messagebox.askyesno('Audio Remaster', t('¿Desea cancelar el proceso? El juego aún no fue modificado.', 'Cancel the process? The game has not been modified yet.')):
            self.cancelar = True
            self.lbl_et.config(text=t('Cancelando...', 'Cancelling...'))

    def _lanzar(self, titulo, sub, fn):
        self.tit_proc, self.sub_proc = titulo, sub
        self.registro, self.cancelar, self.trabajando, self.t0 = [], False, True, time.time()
        self.mostrar('progreso')

        def tarea():
            try:
                res = fn(lambda s: self.q.put(('log', s)), lambda f, s: self.q.put(('prog', f, s)), lambda: self.cancelar)
                self.q.put(('fin', True, res))
            except op.Cancelado:
                self.q.put(('fin', False, t('Cancelado. El juego no fue modificado.', 'Cancelled. The game was not modified.')))
            except Problema as ex:
                self.q.put(('fin', False, str(ex)))
            except Exception as ex:
                self.q.put(('log', traceback.format_exc()))
                self.q.put(('fin', False, t('Error inesperado: ', 'Unexpected error: ') + repr(ex)))
        threading.Thread(target=tarea, daemon=True).start()

    def _instalar(self):
        e = self.estado
        inis = [(ini, sec) for v, ini, sec in self.vars_ini if v.get()]
        self.accion = 'instalar'
        if self.modo == 'completo':
            paqs = op.buscar_paquetes()
            fn = lambda log, prog, canc: op.instalar_completo(e, paqs, inis, log, prog, canc)        # noqa: E731
            sub = t('Se genera el audio nuevo, se verifica y, recién entonces, se reemplaza en el juego.', 'The new audio is built and verified, and only then swapped into the game.')
        else:
            fuente, banda, zip_local, desc = self.fuente.get(), self.banda, self.zip_local, self._descargas()

            def fn(log, prog, canc):
                z = zip_local
                if fuente != 'local':
                    url = [f['url'] for f in banda['fuentes'] if f['id'] == fuente][0]
                    z = os.path.join(desc, banda['zip'])
                    if not (os.path.isfile(z) and os.path.getsize(z) == banda['size']):
                        log(t('Descargando la banda de sonido desde ', 'Downloading the soundtrack from ') + url)
                        op.descargar(url, z, banda['size'], log, lambda f, s: prog(0.0, s), canc)
                        log(t('   guardada en ', '   saved to ') + z)
                return op.instalar_reconstruyendo(e, z, inis, log, prog, canc)
            sub = t('Se genera el audio nuevo a partir de su juego y de la banda de sonido, se valida pista por pista y, recién entonces, se reemplaza en el juego.',
                    'The new audio is built from your game and the soundtrack, validated track by track, and only then swapped into the game.')
        self._lanzar(t('Instalando', 'Installing'), sub, fn)

    def _confirmar_desinstalar(self, preguntar=True):
        if juego.programas_abiertos():
            messagebox.showwarning('Audio Remaster', t('Cierre ScummVM / RetroArch antes de desinstalar.', 'Close ScummVM / RetroArch before removing the patch.'))
            return
        if preguntar and not messagebox.askyesno('Audio Remaster', t('¿Desea volver al juego original?\n\nSe quitarán los archivos del parche y se restaurarán los originales guardados.',
                                                       'Go back to the original game?\n\nPatch files will be removed and the saved originals restored.')):
            return
        res = self.estado['res']
        self.accion = 'desinstalar'

        def fn(log, prog, canc):
            inf = juego.desinstalar(res, lambda d, tt: prog(d / max(tt, 1), t('restaurando y verificando', 'restoring and verifying')))
            for linea in inf:
                log(linea)
            return {'informe': inf}
        self._lanzar(t('Desinstalando', 'Removing'), t('Se restauran los archivos originales y se verifica la huella de cada uno.', 'Original files are restored and each fingerprint is verified.'), fn)

    # ---------------------------------------------------------------- paso: fin
    def p_fin(self):
        ok, res = self.resultado
        inst = self.accion == 'instalar'
        if ok:
            self.titulo(t('Listo', 'Done'), t('El juego cuenta ahora con el audio remasterizado.', 'The game now has the remastered audio.') if inst else t('El juego volvió a su estado original.', 'The game is back to its original state.'))
            c = self.tarjeta(OK)
            if inst:
                v = (res or {}).get('validacion')
                if v:
                    self.parrafo(t('Validado contra la referencia: %d pistas de música, %d frases de voz y %d videos. Estructura de los archivos correcta.',
                                   'Validated against the reference: %d music tracks, %d voice lines and %d videos. File structure is correct.') % (v['musica'], v['voces'], v['videos']), master=c)
                else:
                    self.parrafo(t('Cada archivo escrito tiene la huella esperada.', 'Every written file has the expected fingerprint.'), master=c)
                sc = (res or {}).get('scummvm') or []
                if sc:
                    self.parrafo(t('ScummVM configurado: ', 'ScummVM configured: ') + ', '.join('[%s]' % x['seccion'] for x in sc), master=c, pad=(0, 0))
                else:
                    self.parrafo(t('Falta el ajuste de ScummVM: agregue la línea  dimuse_sample_rate=44100  en la entrada del juego dentro de scummvm.ini.',
                                   'ScummVM setting still needed: add the line  dimuse_sample_rate=44100  to the game entry inside scummvm.ini.'), AVISO, c, 10, (0, 0))
                self.parrafo(t('Los archivos originales quedaron guardados dentro de la carpeta del juego (%s). No la elimine si desea poder desinstalar.',
                               'Original files are kept inside the game folder (%s). Do not delete it if you want to be able to remove the patch.') % juego.CARPETA, TENUE)
            else:
                for linea in (res or {}).get('informe', []):
                    self.parrafo(linea, master=c, pad=(0, 2))
        else:
            self.titulo(t('No fue posible completar el proceso', 'The process could not be completed'))
            c = self.tarjeta(MAL)
            self.parrafo(str(res), master=c)
            if inst:
                self.parrafo(t('El juego no fue modificado.', 'The game was not modified.'), TENUE, c, 10, (0, 0))
        self.parrafo(t('Duración: %d min %02d s', 'Elapsed: %d min %02d s') % divmod(int(self.dur), 60), TENUE, tam=9)
        if self.informe_path:
            self.parrafo(t('Informe guardado en: ', 'Report saved to: ') + self.informe_path, TENUE, tam=9)
        self.botones((t('Cerrar', 'Close'), self.destroy, 'primario', 'right'), (t('Volver al inicio', 'Back to start'), self._reinicio, 'normal', 'right'))

    def _reinicio(self):
        self.estado = None
        self.mostrar('juego')

    def _guardar_informe(self, ok, res):
        try:
            raiz = (self.estado or {}).get('raiz') or (self.estado or {}).get('res')
            p = os.path.join(raiz, textos.informe_nombre())
            accion = t('instalar', 'install') if self.accion == 'instalar' else t('desinstalar', 'uninstall')
            with open(p, 'a', encoding='utf-8') as f:
                f.write('\n=== %s | %s | %s | v%s | %s ===\n' % (time.strftime('%Y-%m-%d %H:%M'), accion,
                                                             t('modo %s', 'mode %s') % t(*textos.par_modo(self.modo)), juego.VERSION, 'OK' if ok else 'ERROR'))
                f.write('\n'.join(self.registro) + '\n')
                if not ok:
                    f.write(t('RESULTADO: %s\n', 'RESULT: %s\n') % res)
            return p
        except Exception:
            return None

    # ---------------------------------------------------------------- mensajes del hilo de trabajo
    def _bombear(self):
        try:
            while True:
                m = self.q.get_nowait()
                if m[0] == 'anal':
                    if self.paso == 'juego':
                        self.lbl_anal.config(text=t('Leyendo los archivos del juego... %d %%', 'Reading the game files... %d %%') % int(100 * m[1]))
                elif m[0] == 'estado':
                    self.trabajando = False
                    self.estado = m[1]
                    if self.paso == 'juego':
                        self.b_analizar.habilitar(True)
                        self.lbl_anal.config(text='')
                        self._pintar_estado()
                elif m[0] == 'fuente':
                    self.fuentes_ok[m[1]] = m[2]
                    self._pintar_fuente(m[1])
                elif m[0] == 'log':
                    self.registro.append(m[1])
                    self._agregar(m[1])
                elif m[0] == 'prog' and self.paso == 'progreso':
                    self.pb['value'] = int(1000 * m[1])
                    self.lbl_et.config(text=m[2])
                    el = time.time() - self.t0
                    self.lbl_t.config(text=t('Transcurrido: %d min %02d s', 'Elapsed: %d min %02d s') % divmod(int(el), 60))
                elif m[0] == 'fin':
                    self.trabajando = False
                    self.dur = time.time() - self.t0
                    self.resultado = (m[1], m[2])
                    self.informe_path = self._guardar_informe(m[1], m[2])
                    self.mostrar('fin')
        except queue.Empty:
            pass
        self.after(80, self._bombear)

    def _cerrar(self):
        if self.trabajando and self.paso == 'progreso':
            self._cancelar()
            return
        self.destroy()


def main(modo):
    import multiprocessing
    multiprocessing.freeze_support()
    app = App(modo)
    prueba = os.environ.get('COMI_PRUEBA')
    if prueba:                                   # solo para capturas de prueba
        paso, _, carpeta = prueba.partition('|')
        app.dur, app.informe_path, app.accion = 0, None, 'instalar'

        def ir():
            if paso in ('juego', 'banda', 'resumen', 'instalar', 'desinstalar') and carpeta:
                app.carpeta.set(carpeta)
                app.mostrar('juego')
                app._analizar()

                def luego():
                    if app.trabajando:
                        return app.after(300, luego)
                    if paso == 'desinstalar':
                        app._confirmar_desinstalar(preguntar=False)
                    elif paso == 'instalar':
                        if modo == 'reconstruye':
                            app.fuente.set('local')
                            app.zip_local = os.environ.get('COMI_PRUEBA_ZIP')
                        app.mostrar('resumen')
                        app.v_aviso.set(True)
                        app._instalar()
                    elif paso != 'juego':
                        if paso == 'resumen' and modo == 'reconstruye':
                            app.fuente.set('mixnmojo')
                        app.mostrar(paso)
                app.after(300, luego)
        app.after(600, ir)
    app.mainloop()
