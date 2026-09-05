#!/bin/sh
# Generates the local fallback standby video shown when the library USB
# isn't inserted (or is missing its own standby.mp4) -- see
# src/core/player.py, where Player automatically falls back to this
# whenever the real standby video isn't present on disk.
#
# Deliberately NOT tracked in git and NOT part of the library USB: this
# is a small, reproducible, text-on-black-background clip, so the script
# that generates it is what's committed, not the resulting binary file.
# Run this once, directly on the Raspberry Pi (it needs ffmpeg's
# drawtext filter and a font, both already present on the project's
# reference image -- see TESTING.md).
#
# Usage:
#   sh scripts/generate_fallback_standby.sh [output_path]
#
# output_path defaults to ~/pedal-assets/fallback-standby.mp4, which is
# also main.py's default --fallback-standby value.

set -e

OUTPUT="${1:-$HOME/pedal-assets/fallback-standby.mp4}"
FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
TEXT="Please insert the USB into the Raspberry Pi"

mkdir -p "$(dirname "$OUTPUT")"

ffmpeg -y \
  -f lavfi -i "color=c=black:s=1920x1080:r=25:d=10" \
  -vf "drawtext=fontfile=${FONT}:text='${TEXT}':fontcolor=white:fontsize=54:x=(w-text_w)/2:y=(h-text_h)/2" \
  -c:v libx264 -pix_fmt yuv420p -t 10 \
  "$OUTPUT"

echo "Fallback standby written to $OUTPUT"
