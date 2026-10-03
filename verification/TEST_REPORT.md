# Any2Any verification

Verified on Windows on October 3, 2026, with Python 3.14.2.

- `python -X utf8 -m pytest -q`: **98 passed**, 19.05 seconds, no skipped tests.
- Python source compilation succeeded.
- PyInstaller produced the standalone single file `dist/Any2Any.exe`, with bundled Python, Tk, drag-and-drop, conversion libraries and fallback FFmpeg.
- The final executable's smoke test passed with system FFmpeg/ffprobe on PATH.
- The same executable passed with an empty PATH, using bundled FFmpeg and signature-based media detection without ffprobe.
- Both final runtime tests initialized the GUI and drag-and-drop and completed 13 conversions: PNG→JPEG, PNG→WAV, XLSX→MP3, DOCX→PDF, PDF→MP4 with fades/subtitles, MP4→PDF, arbitrary bytes→XYZ envelope, WAV→TXT, MP4→TXT, PNG→JSON, XLSX→TXT, scrolling TXT→MP4, and MP4→PNG contact sheet.
- Both runtime tests also completed a two-file mixed image/spreadsheet batch to WEBP.

Runtime details and actual routes are in `system-runtime.json` and `bundled-runtime.json` in this directory.

## Standalone release verification

The single executable was copied by itself into a temporary directory outside the checkout whose name contains spaces and a Unicode character. It was launched with an unrelated working directory, once with system tools and once with an empty PATH. Both runs initialized the GUI and drag-and-drop, completed all 13 conversions and the two-file batch, and required no project files or adjacent `_internal` folder. These reports, including the executable SHA256 and file size, are in `standalone-system.json` and `standalone-bundled.json`. The temporary test directory was cleaned afterward.

Coverage includes detection, planner priorities, valid native/semantic/binary outputs, animated image dimensions/timing, deterministic amplitude-limited PCM, archive traversal and bombs, huge-file prefix limits, malformed inputs, unavailable dependencies, input/overwrite protection, cancellation including a running subprocess, cleanup, formula strings as data, and Tk construction.

Expanded coverage includes audio analysis and silence detection, image metadata/ASCII/statistics, OCR integration with a stub, PDF page boundaries, HTML/RTF/ODT/ODS extraction, readable spreadsheet rendering and pagination, all frame-sampling modes, subtitles, stereo visualization, scrolling text, progressive tables, presentation video, route diagnostics, mixed-batch interpretation handling, multi-image output collisions and rollback, generated-output validation failures, and offline speech-model configuration. Transcription tests verify local-only loading with mocks; they do not establish recognition accuracy.

LibreOffice, ImageMagick, Tesseract and local speech-recognition engines/models were unavailable during verification. Native LibreOffice exports and actual OCR/transcription were therefore not exercised. DOCX/PPTX semantic rendering was exercised; complex presentation layouts may differ from Office rendering. ImageMagick is listed as a future-adapter capability, not an active converter. GUI construction and controls were tested programmatically; manual visual inspection and drag gestures were not performed.
