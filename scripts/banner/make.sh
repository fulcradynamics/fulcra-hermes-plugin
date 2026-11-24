#!/usr/bin/env bash
# Rebuild assets/banner.png. Usage: scripts/banner/make.sh <fulcra-openai-plugin checkout> [font.ttf]
# The fresco is Michelangelo's Creation of Adam (public domain), from Wikimedia Commons.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
logo=$1/assets/icon.png font=${2:-/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf}
work=$(mktemp -d)
cd "$work"
curl -sfL -A "fulcra-hermes-plugin banner" -o adam.jpg \
  "https://commons.wikimedia.org/wiki/Special:FilePath/Michelangelo_-_Creation_of_Adam_(cropped).jpg?width=2400"
run() { uv run -q --no-project --with numpy --with pillow --with scipy --with matplotlib python "$@"; }
run "$here/compose.py" hands
run "$here/robot_arm.py"
run "$here/compose.py" banner "$logo" "$font"
cp banner.png "$here/../../assets/banner.png"
echo "assets/banner.png updated; preview on light and dark: $work/preview.png"
