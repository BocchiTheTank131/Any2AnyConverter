# Any2Any technical guide

For downloads and a quick introduction, start with the [README](../README.md). This guide keeps the detailed format behavior, settings, and development notes in one place.

A local desktop file converter that chooses a real conversion first, a documented semantic interpretation second, and a deterministic binary interpretation when neither works. The original file is never overwritten. There are no uploads, account requirements, macros, or source-code execution.

## Run on Windows

This checkout is ready to launch: double-click **Launch Any2Any.cmd**. It uses the project-local Python environment.

For a fresh installation, install Python 3.11 or newer with Tk support, then double-click **Install Any2Any.cmd**, followed by **Launch Any2Any.cmd**. FFmpeg on PATH is preferred; `imageio-ffmpeg` supplies a bundled executable when PATH has none. Install FFmpeg/ffprobe for the strongest media detection. LibreOffice is optional and enables layout-preserving Office exports. ImageMagick is detected for capability reporting but is not currently a registered encoder.

On other platforms:

```sh
python -m venv .venv
# Activate the environment using your platform's activation command.
python -m pip install -r requirements.txt
python -m any2any
```

Linux distributions may require their `python3-tk` package. Drag-and-drop uses `tkinterdnd2`; Browse remains available if it cannot load.

Download **Any2Any.exe** from the [GitHub releases](https://github.com/BocchiTheTank131/Any2AnyConverter/releases). It is a standalone Windows x64 executable: copy it to your Desktop, Downloads, a USB drive, or another folder and run it. Python, the source checkout, and an `_internal` folder are not needed. The bundled FFmpeg works even without system tools on PATH. Input and output paths are selected in the GUI; they do not depend on the launch folder.

**Build Windows EXE.cmd** creates this single-file executable at `dist/Any2Any.exe`. PyInstaller unpacks its bundled Python, Tk, libraries and FFmpeg into a temporary directory at startup, so the first launch can take a little longer and requires a writable temporary directory. LibreOffice, OCR engines and speech-recognition models remain optional system installations. This Windows build does not run natively on macOS or Linux. Review the licenses of FFmpeg and other dependencies before redistribution.

The packaged executable also accepts `--smoke-test <output-folder>` to initialize Tk/drag-and-drop and exercise native, semantic, media, document, spreadsheet and unknown-extension paths, writing `report.json` and example results without needing a console.

After building, run `.venv\Scripts\python.exe -X utf8 scripts\verify_portable.py` to copy just the executable into a temporary folder outside the checkout and test it from an unrelated working directory. This checks paths containing spaces and Unicode, both system-tool and empty-PATH operation, and writes the standalone verification reports.

## Desktop usage

1. Browse or drop one or multiple files into the input field.
2. Choose or type any extension. The editable selector accepts `.pdf`, `wav`, or even `.xyz`.
3. Set the output path and review **Strategy & preview**. Input detection shows the actual content format, MIME type, and detection evidence. Image sources have a thumbnail.
4. Select an **Interpretation** in **Strategy & preview**: Auto, image/RGB/scanline sonification, raw bytes, waveform/spectrogram/stereo, first/middle/last frames, scene changes, contact sheets, scrolling text, or progressive table rows. Choices are filtered for the first input and destination. Advanced settings provide sampling, font, color, page limits, OCR and transcription controls.
5. Convert. The worker leaves the UI responsive. Cancel stops conversion and cleans up temporary files. Existing outputs require confirmation; replacement happens only after a successful conversion.
6. **Log & result** contains the final actual route, classification, sizes, duration, warnings and destination. A failed native/semantic route may switch to binary interpretation; the final report records that change.

The preview describes the planned interpretation; it does not pre-render a full sonification or slideshow. Progress reports backend stages rather than a precise codec ETA. Files run sequentially in a batch to bound resources. With multiple inputs, **Location** chooses an output folder. **Batch queue** shows each input, actual output name, state and per-file progress; the two progress bars show current-file and overall progress. Preserve filenames or use numbered outputs. Duplicate stems get unique names. Failed files are reported while later files continue; Cancel stops the active file and marks remaining files cancelled. Preview describes the first input; each batch item plans its own route. If an explicit interpretation does not apply to a different category in a mixed batch, that item uses Auto with a warning rather than jumping directly to bytes.

**Route diagnostics** shows every simple route considered in the active registry (bounded to 1000 routes/12 edges for future plugins), its priority, display score, availability and selected status. Selection uses priority and route cost, not the approximate display score. No internal Python objects are exposed. **Capabilities** groups backends and explains which features missing dependencies unlock.

## Supported working set

| Category | Formats and behavior |
| --- | --- |
| Images | Pillow decodes its installed formats; registered outputs: PNG, JPEG, WEBP, GIF, BMP, TIFF, ICO, PPM/PGM/PBM, AVIF, TGA, PCX, DDS. Encoder availability depends on the Pillow build. Transparency composites onto white for JPEG. |
| Audio | FFmpeg reads its supported audio formats; outputs WAV, MP3, FLAC, OGG, OPUS, AAC, M4A, AIFF/AIF, WMA, AC3. |
| Video | FFmpeg reads its supported containers/codecs; outputs MP4, MOV, MKV, AVI, WEBM, M4V, MPG/MPEG, TS, WMV, FLV, OGV. Remux is attempted before transcoding. Animated GIF → video uses FFmpeg and retains source timing. |
| Documents | PDF renders with PyMuPDF and extracts text with page boundaries. DOCX text extraction and creation use python-docx. ODT extracts readable paragraphs locally. LibreOffice converts compatible DOC/DOCX/ODT, XLS/XLSX/ODS, PPT/PPTX/ODP families to PDF and supported family exports. |
| Spreadsheets/data | XLSX, ODS, CSV, TSV, JSON, XML → shared tables → CSV/TSV/JSON/XML/XLSX. Cached formula values are used. Generated XLSX strings remain data, not formulas. |
| Presentations | PPTX/ODP text extraction; PPTX slide rendering preserves text, pictures and aspect ratio. Complex slide objects may differ. LibreOffice provides faithful slide rendering when installed; ODP without it uses extracted text slides. |
| Text | TXT, MD, LOG, SRT/VTT, YAML/YML content → text bridges. HTML extracts visible text, discarding scripts/styles; RTF extracts readable text with striprtf. UTF-8/UTF-16 and charset-normalizer cover common encodings. |
| Archives | ZIP, TAR, GZIP, BZIP2, XZ and optional 7Z manifest reading. ZIP/TAR/GZIP/BZIP2/XZ creation packages the original file without interpreting it. 7Z listing uses py7zr; no 7Z encoder is registered. |
| Unknown extensions | A valid structured envelope with metadata and bounded base64 content. An `.xyz` output contains JSON, explicitly **not** a newly invented XYZ codec. |

Not every listed codec is guaranteed in every external build. Unavailable or failing backends produce explicit warnings and try the next route, eventually an envelope. **Generated output that fails validation is a hard error**; broken temporary outputs are deleted and never published. A byte-for-byte identity copy is also validated. Legacy binary Office documents require LibreOffice for useful extraction/export; without it they use binary interpretation. There are still 69 recognized extension names: this release expands meaning and interactions rather than adding obscure extensions.

## Semantic bridges

- **Audio → text/data:** embedded tags and codec/duration/channels/rate/bitrate metadata, optional offline speech recognition, then signal analysis. The analysis reports peak/RMS dBFS and silence windows in the first `audio_seconds` seconds. RMS is a loudness estimate, not calibrated LUFS. When ffprobe is absent, FFmpeg input headers provide less complete metadata. Only if these extraction/analysis operations fail does the planner use printable strings and bounded hex.
- **Video → text/data:** try embedded text subtitles first, then metadata, optional soundtrack transcription, optional OCR of up to five sampled frames, and media analysis. Subtitle extraction is limited to `audio_seconds` and eight subtitle tracks. Bitmap subtitles that cannot become SRT are skipped with a warning. Native text reports may be serialized to JSON/XML/CSV/TSV without embedding arbitrary source bytes.
- **Image → text/data:** metadata/EXIF, optional OCR, ASCII art, and bounded-thumbnail pixel statistics. OCR is labeled as recognition that may contain errors; ASCII art is a representation, not recognized document text.
- **Video → PDF/images:** first/middle/last frame, timed frames, every N frames, every frame, evenly distributed samples, scene changes, contact sheets or animated sequences. `max_pages` always caps extraction, including “every frame”. Images retain aspect ratio. PDF pages can include sampled timestamps. Scene selection includes the first frame and later frames crossing `scene_threshold`. Frame-based/scene modes report original PTS; timed sampling reports its regular sampling timeline. Last-frame selection uses a near-end seek (approximately 0.15 seconds before end), so variable frame rates may yield the final nearby frame. Unknown duration falls back to first/timed frames with a warning.
- **PDF → video:** render pages, letterbox to the requested resolution, encode at the requested FPS and seconds per page. Transitions are cuts or fades through black at each slide boundary. Optionally embed useful page text as subtitle tracks in MP4/MOV/MKV.
- **Image → audio:** deterministic brightness or RGB sonification. Resample the first page to 128×48. Horizontal position maps to time; vertical position maps to semitone pitch from 110 Hz; brightness maps to amplitude. RGB uses separate octave ranges. Scanline mode reads left-to-right/top-to-bottom and maps brightness to amplitude and 110–1870 Hz. Choose raw bytes for PCM instead.
- **Audio → images/PDF/video:** waveform, spectrogram, frequency spectrum or separate left/right stereo waveforms of the first configured audio seconds. Mono inputs duplicate channels in the stereo view. Video of the visualization is a silent slideshow; it does not preserve the source soundtrack.
- **Spreadsheet → audio:** rows divide the configured time, up to 16 columns produce separate tones. Pitch strategy maps absolute numeric values modulo 36 to semitones; amplitude strategy maps magnitude to `abs(x)/(1+abs(x))`. Strings use sums of Unicode code points. Empty values are zero. Up to 2048 rows are sounded.
- **Spreadsheet → text/images/PDF/video:** readable aligned tables, wrapping cells, vertical pagination with repeated headers, and horizontal panels covering all columns. Very tall/long cells can be clipped with a warning. Videos use worksheet pages or progressive rows; progressive mode shows the newest page/panel, so worksheet mode is recommended for complete wide-sheet coverage. JSON tables serialize as `{"sheets": {"name": [[...]]}}`; XML uses workbook/sheet/row/cell elements. CSV/TSV saves the first sheet only.
- **Text → audio:** prefer local Windows System.Speech or eSpeak (first 50,000 characters, installed voice). Otherwise character sonification maps code points modulo 36 into semitone tones, first 2048 characters. Disable `prefer_tts` for reproducible character tones across machines. No cloud TTS is used.
- **Text/DOCX/ODT → pages/PDF:** measured wrapping, configurable font size, page width/background and automatic image height. DOCX/ODT extracted text does not retain original document layout/artwork. **PPTX → PDF/video** renders slide text/pictures at the slide's aspect ratio, with a warning about unsupported complex objects when LibreOffice is absent.
- **Text → video:** wrapped page slides or continuous scrolling at `scroll_speed` pixels per second. The scrolling canvas is bounded to 16,000 pixels high/40 million pixels; video is bounded to 120 seconds and the configured page/time budget. Truncation produces warnings.
- **Archive → text:** structured archive name/format, entry count, total file/expanded sizes, directory tree, filenames and per-entry compressed/uncompressed sizes when available. Optional readable member contents are bounded. Unsafe paths are marked and never extracted. TAR links are never dereferenced; 7Z contents are never extracted.

GIF/TIFF/WEBP outputs can hold multiple rendered pages. Other image formats save the first page at the selected path and later pages as `name.page-002.png`, etc. Disable `multi_image` to save only the first page with a warning. All pages validate before any are published. The final report includes `additional_paths` and combined output size. Publication is a rollback-capable group transaction, not an OS-level atomic multi-file transaction; abrupt power loss can still interrupt it.

## Optional local recognition

Install **Tesseract** locally or set `ANY2ANY_TESSERACT` to its executable to unlock image/frame OCR. Missing OCR simply leaves metadata, ASCII/statistics and other representations available.

Enable **Use offline speech recognition** only after configuring existing weights:

- A local `.pt` model and the `openai-whisper` Python package; or
- A local faster-whisper model directory and `faster-whisper`; or
- A local whisper.cpp model plus `whisper-cli` on PATH (or `ANY2ANY_WHISPER_CLI`).

Set `ANY2ANY_WHISPER_MODEL` to the existing model file/directory. Model identifiers such as `base` are never downloaded. The Python worker forces offline mode and faster-whisper uses `local_files_only=True`. Transcription runs in a cancellable subprocess and only processes the configured audio prefix. This installation does not include recognition weights or Whisper Python dependencies. For the frozen executable, use a local `whisper-cli` executable/model, or rebuild after installing the desired Python backend into the build environment. Recognition was tested with stubbed OCR and unavailable-backend handling; actual OCR/STT quality depends on separately installed tools and models.

## Binary interpretation

The binary reader streams SHA-256 over the full source in 1 MiB chunks, retaining only a configurable prefix (16 MiB by default). Envelopes include original name, detected format, size, full-file hash, included bytes, truncation flag, encoding and base64 data. They are inspectable reports, not general reversible codec transformations; a truncated envelope cannot restore omitted bytes.

- **Image:** prefix bytes become RGB triplets; dimensions are derived from byte count, capped by render dimensions, and unused pixels are zero-padded. PNG stores source metadata.
- **WAV/audio:** bytes become unsigned sample amplitudes centered on zero, normalized to 35% peak with short start/end ramps. The duration setting caps retained samples; data is not repeated to fill time.
- **Video:** byte visualization becomes a valid slideshow video through FFmpeg.
- **PDF:** bounded metadata, printable strings, hexadecimal preview and an RGB visualization become pages. The page cap applies.
- **TXT:** readable UTF-8/UTF-16 when possible, followed by metadata/strings/hex for binary input. Hex is capped at 4096 bytes and extracted strings at 1000 matches.
- **JSON/XML/CSV/TSV:** metadata and bounded encoded source data. Other extensions use JSON envelopes when no actual encoder can write them.

Determinism is defined for the interpretation content under identical settings and dependency versions. PDF timestamps/container metadata and native lossy codecs need not produce byte-identical output. Sonification WAVs use no randomness and are tested byte-for-byte.

## Architecture and extension points

`FormatDetector` checks magic bytes, ZIP/Office container contents, ffprobe and Pillow decoder evidence, then text content. Extensions are secondary hints. FFmpeg protocol access is limited to local files/pipes. Ambiguous media is probed with bounded probe size and timeout. Large ZIP container inspection is skipped above 64 MiB rather than allocating its central directory blindly.

`ConversionRegistry` holds `ConverterBackend` edges with source/target types, operation, availability predicate and priority. `ConversionPlanner` uses a graph search minimizing `(highest edge priority, route cost)`. Priorities: native lossless identity/remux (0), native transcoding (1), semantic extraction (2), semantic visualization/representation (3), binary interpretation (4). Decode-only edges can have zero cost in priority without claiming that later lossy encoding is lossless. Remux and transcode are separate registered routes; a rejected remux tries transcoding before semantic routes. A shorter representation route beats unnecessarily rendering an extraction report when both have the same maximum priority.

The shared models are `ImageData`, `ImageSequence`, `DocumentPages`, `AudioData`, `VideoData`, `TextData`, `TableData`, `BinaryData`, `SubtitleData`, `MetadataData`, and `ArchiveTree`. Media source paths stay on disk. Extraction lives in `semantic.py`, bounded rendering in `rendering.py`, archive trees in `archives.py`, validation in `validation.py`, and sequential batches in `batch.py`. For example:

```text
XLSX → structured table parser → TableData → spreadsheet sonification → AudioData → MP3 encoder
PDF → page renderer → DocumentPages → slideshow video encoder → MP4
Unknown bytes → bounded prefix + streaming hash → BinaryData → RGB visualization → PNG encoder
```

Add a decoder, bridge or writer in the appropriate module, then register its graph edge in `default_registry`. Availability predicates keep absent dependencies out of planned routes. The engine excludes failed adapters and tries the next available route, eventually reaching a bounded binary path. Unknown extension handling is centralized, so the GUI never needs an N×N conversion matrix.

## Safety, limits and practical boundaries

- Source and output paths (including hard-link aliases) are compared. Writes occur in a private temporary directory on the destination filesystem. Valid results are published atomically with an exclusive hard link for new output, or atomic replace after confirmed overwrite. Some filesystems without hard-link support cannot publish new output; the app reports the error and retains existing files.
- Temporary directories are removed on success, failure and cooperative cancellation. A forced process termination or power loss can leave a `.any2any-*` directory; those can be deleted when no conversion is active.
- Cancellation is checked at chunk/page/row boundaries and while waiting for external tools. External tools are killed on cancel or timeout. A library decoder call or format detection may take a few seconds to return before cancellation can complete.
- Office/archives are checked against compressed byte, entry-count, expanded-size and ZIP compression-ratio limits. XML DTD/entities are disabled. Archive members are never written to filesystem paths. Source files are never executed. LibreOffice receives a private profile with highest macro security.
- Text and binary content have read limits. Spreadsheet cells, archive entries and expansion, pages, audio duration and tool runtime are bounded. A 40 million pixel budget bounds multi-page rendering; PDF/video can reduce resolution to fit it. Images over 40 megapixels or Pillow's decompression safety threshold fall back to bytes. Video/audio native conversions stream, but media output sizes can still be large.
- PyMuPDF/Pillow/Office parsing and NumPy operations are not an OS security sandbox. Only open files from sources you trust enough to feed into installed parsers. Limits reduce resource use; they do not guarantee fixed maximum RAM for every malformed third-party parser input.
- Validation verifies/decodes image frames, opens/renders PDF pages at a bounded scale, probes media and decodes its first 0.25 seconds with error checking, checks ZIP/Office CRCs and required members, streams TAR/compressed archive integrity, checks bounded 7Z integrity, parses JSON/XML/CSV and validates text encoding. It verifies structure/decodability, not perceptual quality or every frame of a long video. Failed validation is reported and never triggers a silent success via fallback.
- Every batch input is protected from overwrite by every other item, including generated page images. Previously completed batch outputs remain when a later item fails or is cancelled. Individual image groups roll back on publication failure.
- The GUI groups capabilities and explains missing-feature unlocks. Override tool paths with `ANY2ANY_FFMPEG`, `ANY2ANY_FFPROBE`, `ANY2ANY_SOFFICE`, `ANY2ANY_MAGICK`, `ANY2ANY_TESSERACT`, `ANY2ANY_WHISPER_CLI`.

## CLI and tests

```sh
python -m any2any input.jpg output.png
python -m any2any input.mp4 output.pdf --preview
python -m any2any input.png output.wav --binary
python -m any2any input.xlsx output.mp3 --settings settings.json
python -m any2any input.mp4 output.pdf --diagnostics
python -m any2any --batch a.pdf b.xlsx c.mp3 --output-dir ./outputs --extension png
python -m any2any --capabilities
python -m pip install pytest
python -m pytest -q
```

`--overwrite` explicitly authorizes replacing an existing CLI output. `settings.json` contains any `Settings` fields, for example:

```json
{"mode":"auto","frame_mode":"seconds","frame_interval":2.0,"max_pages":30,"seconds_per_page":2.0,"width":1280,"height":720,"fps":24,"transition":"fade","audio_seconds":8.0,"prefer_tts":false,"font_size":20,"background":"#fafafa","multi_image":true,"transcribe":false}
```

`mode` names and profiles live in `interpretations.py`: `auto`, `binary`, `brightness`, `rgb`, `scanline`, `image_text`, `media_text`, `waveform`, `spectrogram`, `spectrum`, `stereo`, `first`, `middle`, `last`, `timed`, `frames`, `every`, `even`, `scene`, `contact`, `animated`, `slides`, `scroll`, `table_pitch`, `table_amplitude`, `table_rows`, `table_sheets`. Auto honors advanced settings; an explicit profile overrides its corresponding settings.

For batches, `--numbered` uses numbered output names; default preserves stems and resolves collisions. `--preview` with `--batch` lists planned filenames. `--overwrite` authorizes replacing existing outputs, including numbered page companions. The CLI exits nonzero when any batch item fails or is cancelled.

Tests cover detection, prioritized route diagnostics, native and semantic outputs, subtitles/frame modes/stereo/scrolling, extracted HTML/RTF/OpenDocument/PDF text, structured semantic reports, pagination/multiple images, deterministic PCM, malformed inputs, resource limits, optional recognition handling, batch collision/input protection and cancellation, generated-output validation failures, rollback and cleanup, and GUI controls. See `verification/TEST_REPORT.md` for the latest run. Media tests require FFmpeg.
