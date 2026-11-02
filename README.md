# png-overlay-export

A Python port of the export engine of the AutoHotkey script `export_from_drawio_PY.ah2`, which turns a
keyboard-layout diagram (`source_diagram.drawio`) into stackable PNG overlays: one background and one
foreground per layer, mirrored layers, a legend, a cheat sheet, a sheet of all layers and a backup zip,
in three key styles (draw.io, SVG caps, Render with 3D-shaded caps and Legend 3D).

The AHK script keeps every dialog, the INI and (for now) the source rewrite and the layer picker; after
the picker it runs this exe, which draws the pages with draw.io's own code (from the user's draw.io
install, `resources\app.asar`) in the Edge already on Windows, and does all the image work in numpy.

## Use

```
png-overlay-export export --ini export_from_drawio_PY.ini --ahk export_from_drawio_PY.ah2 ^
    --layout LameSaddle --layers 0,3,16 [--recomp] [--all-run [--last]] [--last-bak <file>] ^
    [--drawio <draw.io folder>] [--progress <file>] [--result <file>]
png-overlay-export render --drawio <draw.io folder> -s 5 -t page.drawio page.png
png-overlay-export fontcheck Helvetica codepoints.txt
png-overlay-export --version
```

`--result` is a JSON file (`ok`, `message`, `line`, `warnings`, `images`, `mirrored`); put it outside the
export folder (the script takes any `*.json` there for a ZMK layout export). Exit code 0 = done,
2 = stopped with a message, 1 = crashed (the AHK script then exports the old way).

## Build

GitHub Actions (`.github/workflows/build.yml`) builds the Windows exe with PyInstaller (onedir) on a push
to `main` that touches the engine, by hand, or on a `v*` tag; a build of `main` publishes the Release named in `release.txt`. Each build also
renders `ci/parity_page.drawio` with the real draw.io and with the exe and checks Windows' glyph answers
for Helvetica; both reports are in the run's summary and its `checks` artifact.

## Layout

- `pyport/`: the engine (`engine.py` is the entry point), one module per area of the AHK script.
- `tests/`: the checks used during the port. They need the user's own files (source, INI, reference
  images from a Debug run), which are not in this repository; `tests/SETUP_PY.sh` restores them.
- `ci/`: the Windows checks' test page and scripts.

draw.io is Apache-2.0; its code is read from the user's install, not bundled.
