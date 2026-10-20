# Audio Remaster for The Curse of Monkey Island
# Copyright (C) 2026 SamuelEchoes
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.

"""COMI Audio Remaster - instalador (reconstruye)."""
import multiprocessing
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == '__main__':
    multiprocessing.freeze_support()
    if '--auto' in sys.argv:
        from comi import cli
        sys.exit(cli.correr('reconstruye', sys.argv))
    from comi import ui
    ui.main('reconstruye')
