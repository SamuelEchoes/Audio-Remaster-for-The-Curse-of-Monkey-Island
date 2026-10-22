# Audio Remaster for The Curse of Monkey Island
# Copyright (C) 2026 SamuelEchoes
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.

"""Arma "Audio-Remaster-for-The-Curse-of-Monkey-Island.exe" (un solo archivo) con PyInstaller y lo deja en dist\\.

Uso, con un Python 3.10 que tenga lo de requirements.txt:   python armar_exe.py
Tarda unos 2 minutos. El registro queda en build.log.
"""
import os
import subprocess
import sys

I = os.path.dirname(os.path.abspath(__file__))
os.chdir(I)
NOMBRE = 'Audio-Remaster-for-The-Curse-of-Monkey-Island'
PERFIL = os.path.join(I, 'comi', 'motor', 'perfil_mejora.json')
cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed', '--specpath', 'build',
       '--icon', os.path.join(I, 'datos', 'calavera.ico'), '--version-file', os.path.join(I, 'version_info.txt'),
       '--add-data', os.path.join(I, 'datos') + ';datos', '--collect-binaries', '_soundfile_data',
       '--paths', os.path.join(I, 'comi', 'motor'), '--add-data', PERFIL + ';comi/motor', '--add-data', PERFIL + ';.'] + \
      sum((['--hidden-import', m] for m in ('bun', 'build_bun', 'build_video', 'deess', 'enhance', 'match', 'san_audio')), []) + \
      ['--name', NOMBRE, '--distpath', 'dist', '--workpath', os.path.join('build', 'trabajo'), 'app_reconstruye.py']
with open('build.log', 'w', encoding='utf-8') as log:
    cod = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT).returncode
exe = os.path.join('dist', NOMBRE + '.exe')
if cod or not os.path.exists(exe):
    sys.exit('FALLO el armado (ver build.log)')
print('%s (%.0f MB)' % (exe, os.path.getsize(exe) / 1e6))
