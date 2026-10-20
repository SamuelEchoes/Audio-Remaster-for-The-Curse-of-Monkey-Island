# Audio Remaster for The Curse of Monkey Island
# Copyright (C) 2026 SamuelEchoes
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.

# De-esser para las voces del juego (22.050 Hz mono): baja la banda de las eses solo cuando domina.
# Las voces suenan seseantes porque el codec concentra ruido en las consonantes agudas. Se separa la banda alta
# (por encima de ~4,5 kHz) con un filtro de fase lineal, se mide cuanto pesa respecto del total cada pocos milisegundos
# y, cuando pasa el umbral, se la atenua (hasta 'maxcut' dB). El resto de la voz no se toca.
import numpy as np
from scipy import signal
from scipy.ndimage import uniform_filter1d, minimum_filter1d


def deess(x, sr=22050, split=4500.0, thr=0.45, maxcut=9.0, strength=1.0):
    taps = signal.firwin(255, split, fs=sr, pass_zero=False)
    hf = signal.fftconvolve(x, taps, mode='same').astype(np.float32)
    lf = x - hf
    w = max(int(0.004 * sr), 1)
    e_hf = np.sqrt(np.maximum(uniform_filter1d(hf.astype(np.float64) ** 2, size=w), 0.0))
    e_all = np.sqrt(np.maximum(uniform_filter1d(x.astype(np.float64) ** 2, size=w), 0.0)) + 1e-6
    ratio = e_hf / e_all                              # 0 = nada de agudos, 1 = solo agudos (una ese pura)
    over = np.clip((ratio - thr) / (1.0 - thr), 0.0, 1.0)
    cut_db = maxcut * strength * over
    cut_db[e_all < 0.003] = 0.0                       # no actuar sobre el silencio
    g = 10 ** (-cut_db / 20.0)
    g = minimum_filter1d(g, size=int(0.003 * sr))     # ataque rapido
    g = uniform_filter1d(g, size=int(0.02 * sr))      # soltar suave
    return (lf + hf * g).astype(np.float32), float((cut_db > 1.0).mean()), float(cut_db.max())
