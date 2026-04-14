#!/usr/bin/env bash

set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: ./run_test.sh <test-file> [extra pytest args]"
    echo "Example: ./run_test.sh test_03_webrtc_ingest.py"
    exit 1
fi

test_name="$1"
shift

test_target="$test_name"
test_path="${test_target%%::*}"

if [[ "$test_path" == tests/* ]]; then
    resolved_path="$test_path"
else
    resolved_path="tests/$test_path"
fi

if [[ "$resolved_path" != *.py ]]; then
    resolved_path="${resolved_path}.py"
fi

node_suffix=""
if [[ "$test_target" == *::* ]]; then
    node_suffix="${test_target#"$test_path"}"
fi

full_target="${resolved_path}${node_suffix}"

if [ ! -f "$resolved_path" ]; then
    echo "Test file not found: $resolved_path"
    exit 1
fi

python3 -m pytest "$full_target" \
    --server-url http://localhost:5080 \
    --user test@example.com \
    --password 'testtest' \
    --media-file "${TESTKIT_MEDIA_FILE:-$(if [ -f "$(pwd)/media/sample_ocr_friendly.mp4" ]; then printf '%s' "$(pwd)/media/sample_ocr_friendly.mp4"; else printf '%s' "$HOME/test/sample_timestamped.mp4"; fi)}" \
    --rtmp-endpoint rtmp://remote-endpoint/live/test \
    "$@"
