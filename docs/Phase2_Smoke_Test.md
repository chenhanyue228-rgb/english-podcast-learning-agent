# Phase 2 MVP Smoke Test

This checklist verifies the Phase 2 MVP source extraction path manually.

Scope:

- Apple Podcasts URL to local audio file
- Podcast RSS feed to local audio file
- Local mp3 validation

Out of scope:

- Whisper transcription quality
- Notion page creation
- Expression extraction
- Transcript highlighting
- Weekly review

## Prerequisites

Install dependencies:

```bash
python3 scripts/bootstrap_environment.py
```

For non-mp3 audio conversion, the project dependency set provides FFmpeg.

Create the output directory if needed:

```bash
mkdir -p data/audio
```

## Test 1: Apple Podcasts URL

Input:

```text
https://podcasts.apple.com/cn/podcast/world-today/id894467023?i=1000776913465
```

Command:

```bash
python3 - <<'PY'
from src.extractor.pipeline import extract_audio_from_source

audio_path = extract_audio_from_source(
    "https://podcasts.apple.com/cn/podcast/world-today/id894467023?i=1000776913465",
    output_dir="data/audio",
)
print(audio_path)
PY
```

Expected:

```text
Apple Podcasts URL
↓
RSS feed lookup
↓
episode enclosure audio URL
↓
local audio file
```

Pass criteria:

- Command exits with code `0`.
- Printed path exists.
- Printed path ends with `.mp3`.
- File size is greater than `0`.

Notes:

- The resolver uses Apple/iTunes Lookup API to find the RSS feed.
- If the Apple episode ID is not found in the RSS feed, the resolver may fall
  back to the first audio enclosure. This should be reviewed before treating
  the result as a correct episode match.

## Test 2: Local mp3

Input:

```text
Path to an existing local .mp3 file
```

Command:

```bash
python3 - <<'PY'
from src.extractor.pipeline import extract_audio_from_source

audio_path = extract_audio_from_source(
    "data/audio/sample.mp3",
    output_dir="data/audio",
)
print(audio_path)
PY
```

Expected:

```text
Local mp3
↓
file validation
```

Pass criteria:

- Command exits with code `0`.
- Printed path is the existing local mp3 path.
- File size is greater than `0`.
- No download is attempted.

## Result Template

Record manual smoke test results here:

```text
Date:
Tester:

Apple Podcasts URL:
- Pass/Fail:
- Output path:
- Notes:

Local mp3:
- Pass/Fail:
- Output path:
- Notes:
```

## Out of Scope for v1

YouTube is intentionally excluded from this smoke test and the supported v1
product. Existing downloader code is experimental future work.
