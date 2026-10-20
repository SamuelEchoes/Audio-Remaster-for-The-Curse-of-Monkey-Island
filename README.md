# Audio Remaster for The Curse of Monkey Island

*Castellano: ver [LEEME.md](LEEME.md).*

A fan-made installer that gives **The Curse of Monkey Island** (LucasArts, 1997) high quality audio when played with
**ScummVM**. It replaces the game's compressed music with the **official soundtrack in lossless quality**, and digitally
remasters the voices and the audio of the videos.

It **does not include any audio**. It builds the new audio on your computer from **your own copy of the game** and the
FLAC soundtrack published by Mixnmojo, which it downloads for you.

**[Download the latest version](../../releases/latest)** (one file: `Audio-Remaster-for-The-Curse-of-Monkey-Island.exe`, Windows 64-bit).

## What it does

- **Music:** wherever the official soundtrack has the same recording as the game, the game's compressed music is
  replaced with the **lossless soundtrack** (FLAC source, 44.1 kHz, stored uncompressed in the game files). The game's
  music is not changed: no track is swapped for a different version because it sounds better.
  Music that is not on the album is **digitally remastered** from the game audio: codec noise reduction and restored high
  frequencies, calibrated against the tracks that are on the album, so it matches the rest.
- **Voices:** all 8,490 voice lines (Spanish or English) are **digitally remastered**: codec noise reduction, de-essing
  and restored high frequencies, at 44.1 kHz.
- **Videos:** the lossless soundtrack is used wherever the music matches; voices and effects are digitally remastered with
  the same method. The video files themselves are not modified: ScummVM plays a separate `.ogg` file next to each video.
- **Reversible:** the original files are kept in a subfolder and can be restored from the same program.

## Requirements

- The original game, **Windows CD version**, in **Spanish or English**. Other languages are accepted if the music is the
  known original one; voices and videos are processed with the same method.
- **ScummVM**, or RetroArch with the ScummVM core. This patch is meant for ScummVM only; it is not intended for the
  game's original 1997 executable.
- The **FLAC soundtrack published by Mixnmojo** (1.2 GB). The installer downloads it from Mixnmojo or from the Internet
  Archive, or you can point it to a `.zip` you already have. It checks that it is exactly that edition.
- About **10 GB free** on the game drive during the process. When finished, the game takes about 3.5 GB more.

## How to use

1. Close ScummVM / RetroArch.
2. Run `Audio-Remaster-for-The-Curse-of-Monkey-Island.exe`.
3. Select the game folder, choose where to download the soundtrack from, and follow the steps.
4. It takes 10 to 40 minutes depending on the computer. **The game is not modified until all the new audio has been
   built and validated**; if something fails or you cancel, the game stays as it was.

The interface is in Spanish and English (switch it from the bottom left corner).

### Two important points

- **ScummVM setting:** the new audio needs the line `dimuse_sample_rate=44100` in the game entry inside `scummvm.ini`.
  The installer adds it when it finds the file, and tells you otherwise. With RetroBat, the file is `bios\scummvm.ini`
  and you can select it from the installer.
- **Saved games made before installing** may play the music at half speed when loaded (ScummVM stores the playback
  position and sample rate in the saved game). Walk into a room with different music and save again, or start a new
  game.

### Removing the patch

Run the same program, select the game folder and choose **Remove the patch**. The originals kept in the
`_comi_remaster` subfolder are restored and each one is verified. Do not delete that subfolder if you want to be able to
go back. The ScummVM setting added by the installer is removed too.

### Windowless mode (optional)

```
"Audio-Remaster-for-The-Curse-of-Monkey-Island.exe" --auto "<game folder>" --zip "<soundtrack.zip>" --en
"Audio-Remaster-for-The-Curse-of-Monkey-Island.exe" --auto "<game folder>" --uninstall --en
```

The result is written to `COMI Audio Remaster - automatic report.txt`, next to the program.

## How the result is checked

- **Soundtrack:** fingerprint of the whole file and of each of the 79 tracks.
- **Result:** every music track, every voice line and every video is compared with a reference signature of the
  expected result. The comparison is made on the waveform with a minimal tolerance, because the same computation gives
  inaudible differences on different processors.
- **Structure:** sizes, regions, jumps and markers of every file, so that the game reads them just like the originals.

## Windows and antivirus warnings

- The program is **not digitally signed**. When downloaded from the internet, Windows SmartScreen
  may show *"Windows protected your PC"*. Click **More info** → **Run anyway**.
- Some antivirus programs may flag it. It is a single-file Python program made with PyInstaller, a packaging method
  also used by malware; it is new and has no reputation yet. The full source code is in this repository, and you can
  build the `.exe` yourself (see below).

## Building from source

With Python 3.10 (64-bit) on Windows:

```
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python armar_exe.py
```

The program is left in `dist\`. To run it without building: `venv\Scripts\python app_reconstruye.py`.

Layout: `comi\` (interface, game detection, install and uninstall), `comi\motor\` (the audio processing), `datos\`
(fingerprints of the known game files, the recipe of which album track matches each game track, and the reference
signatures of the expected result). `herramientas\` holds the script that generated `datos\` (it needs the author's
working files, which include game audio and are not published) and an end-to-end test.

The code comments and messages are mostly in Spanish.

## Credits

- **The Curse of Monkey Island** © LucasArts / Lucasfilm. This project is not affiliated with or
  endorsed by Lucasfilm, LucasArts or Disney. You need your own copy of the game.
- **Soundtrack:** the FLAC release published by [Mixnmojo](https://mixnmojo.com/), also available on the
  [Internet Archive](https://archive.org/details/the-curse-of-monkey-island-soundtrack). Not included here: the
  installer downloads it from where it is published.
- **[ScummVM](https://www.scummvm.org/):** the readers for the game's `.BUN` audio files and the video audio are
  translations to Python of ScummVM code (GPL v3 or later), and the knowledge of the formats comes from its source.
  ScummVM is the legal property of its developers.
- Developed by **SamuelEchoes**.

## License

Copyright (C) 2026 SamuelEchoes

This program is free software: you can redistribute it and/or modify it under the terms of the **GNU General Public
License, version 3 or (at your option) any later version**. It is distributed WITHOUT ANY WARRANTY. See
[LICENSE](LICENSE).

The license covers this program only. It gives no rights over the game, its audio or the soundtrack.
