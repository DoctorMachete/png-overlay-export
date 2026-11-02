#!/bin/bash
# Restores the Python port's workspace (PYTHON_EXPORT_HANDOFF.md §15-§25).
# Usage: bash SETUP_PY.sh <source_diagram.drawio> <export_from_drawio_PY.ah2 (.148)> <export_from_drawio_PY.ini>
#                         <capmodels.zip> <__DEBUG_0x_2x.zip> [<AHK_PEEK_SHADER_test_RAW.zip>]
set -e
K="$(cd "$(dirname "$0")" && pwd)"; H=/home/claude
mkdir -p $H/pyport $H/build66 $H/dbg $H/capmodels_x $H/dl/drawio30 $H/refraw
cp "$K"/pyport/*.py $H/pyport/; cp "$K"/tests/*.py "$K"/tests/*.txt $H/pyport/; cp "$K"/combo_data.txt $H/combo_data.txt; cp "$K"/font_probe.txt $H/capmodels_x/font_probe.txt
cp "$1" $H/src.drawio; cp "$2" $H/build66/export_from_drawio.ah2; cp "$3" $H/export_from_drawio.ini
unzip -q -o "$4" -d $H/capmodels_x; unzip -q -o "$5" -d $H/dbg
[ -n "$6" ] && unzip -q -o "$6" -d $H/refraw
# draw.io 30.0.1 (the user's version): Windows zip for app.asar, Linux .deb for the reference CLI
cd $H/dl/drawio30 && curl -sSL -o win.zip https://github.com/jgraph/drawio-desktop/releases/download/v30.0.1/draw.io-30.0.1-windows.zip && unzip -q -o win.zip resources/app.asar && rm win.zip
mkdir -p $H/dl/drawio30lin && cd $H/dl/drawio30lin && curl -sSL -o d.deb https://github.com/jgraph/drawio-desktop/releases/download/v30.0.1/drawio-amd64-30.0.1.deb && dpkg-deb -x d.deb x && rm d.deb
mkdir -p $H/e2e && cp $H/export_from_drawio.ini $H/e2e/export_from_drawio_PY.ini && cp $H/src.drawio $H/e2e/source_diagram.drawio && cp $H/combo_data.txt $H/capmodels_x/font_probe.txt $H/e2e/ && cp -r $H/capmodels_x/capmodels $H/e2e/ && cp $H/build66/export_from_drawio.ah2 $H/e2e/export_from_drawio_PY.ah2
echo "Restored. Checks: cd $H/pyport && python3 test_model_layout.py && python3 test_compose.py && python3 test_shade.py && python3 test_combos.py && python3 test_sheets.py && python3 test_engine.py LameSaddle && python3 test_engine.py classic_minteal && python3 test_engine.py svg_G && python3 test_pages.py LameSaddle:bg LameSaddle:fg svg_G:bg svg_G:bgg svg_G:fg classic_minteal:bg classic_minteal:fg LameSaddle:mbg LameSaddle:mfg svg_G:mbg svg_G:mbgg svg_G:mfg classic_minteal:mbg classic_minteal:mfg LameSaddle:legend svg_G:legend classic_minteal:legend"
