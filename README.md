# Functional Tests

Python test environment for the `Functional Test Plan.pdf` dated March 27, 2026.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Install system tools used by the suite:

```bash
sudo apt-get install -y ffmpeg tesseract-ocr google-chrome-stable
```

Selenium Manager, bundled with Selenium 4, will resolve the Chrome driver automatically.

## Docker

Build an image with the runtime dependencies, then mount this repository into the container so the tests still run from your host checkout:

```bash
docker build -t vsmediatest-runner .
```

Run the full suite from the mounted repo:

```bash
docker run --rm -it \
  -v "$(pwd):/workspace" \
  -w /workspace \
  vsmediatest-runner \
  ". /etc/profile >/dev/null 2>&1 || true; python main.py \
    --server-url https://SERVER_HOST:5443 \
    --user admin@example.com \
    --password 'panel-password' \
    --application live \
    --media-file /workspace/media/sample-timestamped.mp4"
```

Run a single pytest target:

```bash
docker run --rm -it \
  -v "$(pwd):/workspace" \
  -w /workspace \
  -e AUTH_TOKEN \
  vsmediatest-runner \
  "pytest tests/test_02_01_rtmp_transcoding.py \
    --server-url https://SERVER_HOST:5443 \
    --rest-api-token \"$AUTH_TOKEN\" \
    --media-file /workspace/media/sample-timestamped.mp4"
```

Notes:

- The code under test comes from the bind-mounted host directory, not from the image.
- The image already contains Python, `ffmpeg`, `tesseract`, and `google-chrome-stable`.
- Selenium Manager resolves the driver inside the container at runtime.

## Run Everything

```bash
python main.py \
  --server-url https://SERVER_HOST:5443 \
  --user admin@example.com \
  --password 'panel-password' \
  --application live \
  --media-file /path/to/sample-timestamped.mp4 \
  --rtmp-endpoint rtmp://remote-endpoint/live/test \
  --snapshot-dir /opt/server/webapps/live/streams
```

## Run One Document Section

```bash
pytest tests/test_01_02_initial_connectivity_configuration.py \
  --server-url https://SERVER_HOST:5443 \
  --user admin@example.com \
  --password 'panel-password'
```

## Test Script Names

The test files intentionally match the functional test plan sections:

- `test_01_01_test_harness_requirements.py`
- `test_01_02_initial_connectivity_configuration.py`
- `test_02_01_rtmp_transcoding.py`
- `test_02_02_feature_obligations.py`
- `test_02_03_playback_protocol_latency_validation.py`
- `test_03_01_webrtc_transcoding.py`
- `test_03_02_webrtc_feature_obligations.py`
- `test_03_03_webrtc_playback_protocol_latency_validation.py`
- `test_04_stress_test.py`

## Notes

- REST calls use the server REST v2 paths: `/rest/v2/...` for management and `/{application}/rest/v2/...` for app APIs.
- Password authentication follows the web-panel API flow by sending the MD5 hash and keeping the returned session cookie.
- Some server-specific items, such as plugin install folders and server-side snapshot paths, are exposed as parameters because they depend on your deployment.
