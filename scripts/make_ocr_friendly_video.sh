#!/usr/bin/env bash

set -euo pipefail

SOURCE_PATH="${1:-$HOME/test/sample.mp4}"
OUTPUT_PATH="${2:-$(pwd)/media/sample_ocr_friendly.mp4}"
FONT_PATH="${FONT_PATH:-/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf}"

if [ ! -f "$SOURCE_PATH" ]; then
    echo "Source video not found: $SOURCE_PATH" >&2
    exit 1
fi

if [ ! -f "$FONT_PATH" ]; then
    echo "Font not found: $FONT_PATH" >&2
    exit 1
fi

mkdir -p "$(dirname "$OUTPUT_PATH")"

ffmpeg -hide_banner -y -i "$SOURCE_PATH" \
    -vf "drawbox=x=24:y=24:w=620:h=140:color=black@0.94:t=fill,drawtext=fontfile=$FONT_PATH:text='%{pts\\:hms}':x=44:y=40:fontsize=80:fontcolor=yellow:borderw=5:bordercolor=black:box=0" \
    -c:v libx264 -preset veryfast -crf 18 -pix_fmt yuv420p \
    -c:a copy \
    "$OUTPUT_PATH"

echo "Created OCR-friendly test video:"
echo "$OUTPUT_PATH"
