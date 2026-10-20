# Audio Remaster for The Curse of Monkey Island
# Copyright (C) 2026 SamuelEchoes
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.

# Mejora "a ciegas" de la musica del juego que no tiene tema en el disco (22.050 Hz, comprimida) para que no desentone
# con la reemplazada. Dos pasos, los dos calibrados con temas que SI tienen pareja (se aprende de comparar juego y disco):
#   1) Limpieza: el ruido del codec es parejo en frecuencia y sube y baja con el volumen. Se aprende cuanto ruido hay en
#      cada frecuencia respecto de la energia del momento, y se atenua lo que no lo supera (filtro de Wiener por cuadro).
#   2) Agudos: por encima de 11 kHz el juego no tiene nada. Se regenera esa banda copiando en espejo la de 5,5-11 kHz
#      (replica espectral, como hacen los codecs modernos) con el nivel tipico que tiene esa banda en el disco.
# No inventa informacion real: es una aproximacion. Uso como modulo: perfil = learn(...); y = enhance(x22, perfil)
import os, sys, json
import numpy as np
from scipy import signal
from scipy.ndimage import uniform_filter

NF = 2048          # cuadro a 44,1 kHz (46 ms)
HOP = 512


def stft(x):
    return signal.stft(x, fs=44100, nperseg=NF, noverlap=NF - HOP)[2]


def istft(Z, n):
    y = signal.istft(Z, fs=44100, nperseg=NF, noverlap=NF - HOP)[1]
    return np.pad(y, (0, max(n - len(y), 0)))[:n].astype(np.float32)


def learn(pairs, discs):
    """pairs: lista de (juego_subido_44k, disco_alineado_44k) mono, mismo largo -> ruido del codec por frecuencia.
    discs: lista de audios del disco (44,1k mono) -> nivel de 11-20 kHz respecto de su espejo en 2-11 kHz."""
    half = NF // 4            # indice de 11.025 Hz (el cuadro llega a 22.050)
    num = np.zeros(half + 1); den = 0.0
    for g, h in pairs:
        G, H = stft(g), stft(h)
        E = (np.abs(G[:half + 1]) ** 2).mean(axis=0) + 1e-12          # energia media del cuadro (banda del juego)
        N = np.abs(G[:half + 1] - H[:half + 1]) ** 2                   # lo que el juego tiene de mas o de menos: ruido
        ok = E > np.percentile(E, 30)                                  # se ignoran los cuadros casi en silencio
        num += np.median(N[:, ok] / E[ok], axis=1) * ok.sum(); den += ok.sum()
    alpha = num / den
    # el ruido del codec es parejo en frecuencia; por debajo de 3 kHz la diferencia medida es de ecualizacion entre
    # las dos versiones, no ruido, asi que se usa para todo el valor tipico de 3 a 10 kHz
    k3, k10 = int(3000 * NF / 44100), int(10000 * NF / 44100)
    alpha = np.full_like(alpha, float(np.median(alpha[k3:k10])))
    ratios = []
    for d in discs:
        D = np.abs(stft(d)) + 1e-9
        hi = D[half + 1:]                       # 11-22 kHz, de abajo hacia arriba
        lo = D[half - 1::-1][:hi.shape[0]]      # espejo: 11 -> 0 kHz
        loud = D[:half].mean(axis=0) > np.percentile(D[:half].mean(axis=0), 30)
        ratios.append(np.median(hi[:, loud] / lo[:, loud], axis=1))
    ratio = np.median(np.array(ratios), axis=0)
    return {'alpha': alpha.tolist(), 'ratio': ratio.tolist()}


def enhance(x22, prof, clean=1.0, air=1.0):
    """x22: (n, 2) float a 22.050 Hz -> (2n, 2) a 44.100 Hz."""
    alpha, ratio = np.array(prof['alpha']), np.array(prof['ratio'])
    half = NF // 4
    up = signal.resample_poly(x22, 2, 1, axis=0).astype(np.float32)
    out = np.zeros_like(up)
    f = np.arange(len(ratio)) * 44100.0 / NF + 11025.0
    taper = np.clip((20000.0 - f) / 2000.0, 0.0, 1.0)          # los agudos nuevos se apagan entre 18 y 20 kHz
    for ch in range(up.shape[1]):
        Z = stft(up[:, ch])
        lo = Z[:half + 1]
        if clean > 0:
            E = (np.abs(lo) ** 2).mean(axis=0, keepdims=True)
            P = np.abs(lo) ** 2 + 1e-12
            g = np.clip(1.0 - clean * alpha[:, None] * E / P, 0.05, 1.0)
            g = np.sqrt(uniform_filter(g, size=(3, 3)))
            lo = lo * g
            Z[:half + 1] = lo
        if air > 0:
            mirror = np.conj(lo[half - 1::-1])[:Z.shape[0] - half - 1]   # espejo de 0-11 kHz hacia 11-22 kHz
            Z[half + 1:] = mirror * (ratio[:mirror.shape[0], None] * taper[:mirror.shape[0], None] * air)
        out[:, ch] = istft(Z, len(up))
    return out
