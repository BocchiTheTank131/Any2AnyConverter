# Any2Any

Choose a file, choose an output extension, and let Any2Any find a useful way to convert it. Everything runs locally on your computer.

For ordinary conversions, it uses the right decoder and encoder. When two formats have no natural connection, it can turn the contents into something useful: video frames become PDF pages, audio becomes a waveform, or spreadsheet values become sound. The app tells you which interpretation it used.

## Download and run

**[Download Any2Any.exe for Windows x64](https://github.com/BocchiTheTank131/Any2AnyConverter/releases/latest/download/Any2Any.exe)**

Copy the single EXE to any folder and open it. You don't need Python, the source code, or an installer. FFmpeg and the main conversion libraries are included. Startup may take a few seconds while the app unpacks its runtime into your temporary folder.

**v1.1.1 is a documentation-only release.** It includes the exact same executable as v1.1.0, with a shorter README and clearer release notes. There's no need to download it again if you already have v1.1.0.

## Using the app

1. Browse for a file or drag it into the window. You can add several files for a batch.
2. Choose an output extension, or type one yourself.
3. Pick an output location and review **Strategy & preview**. Leave **Interpretation** on Auto, or choose a different treatment.
4. Click **Convert**. The log shows the route used, any warnings, and where the output was saved.

Your source files stay untouched. The app asks before replacing an existing output and checks generated files before saving them. You can cancel a conversion from the window.

## What can it do?

| Example | Result |
| --- | --- |
| JPG → PNG, MP3 → WAV, MKV → MP4 | A normal image, audio, or video conversion |
| MP4 → PDF | Sampled frames, one per page |
| PDF → MP4 | A slideshow of the pages |
| Audio → PNG | A waveform, spectrogram, or frequency plot |
| PNG → WAV | Sound generated from brightness, colors, or scanlines |
| XLSX → TXT / PDF / MP3 | A readable table, paginated sheets, or sound based on cell values |
| Text → PNG / MP4 / audio | Wrapped text, slides or scrolling text, local speech or character tones |
| ZIP → TXT | A directory listing with file sizes |

The working set covers common images, audio, video, PDF and Office documents, spreadsheets, presentations, text/data formats, and archives. It recognizes **69 extension names**; available codecs and optional tools determine which native conversions can run. See the [format details](docs/technical-guide.md#supported-working-set).

## When there isn't a normal conversion

Any2Any tries a native conversion first, then extracts useful content or creates a visual or audio representation. Binary interpretation is the last resort: bytes become pixels, sound samples, or a bounded data report.

These interpretations aren't interchangeable file formats. For example, image sonification turns an image into sound; it doesn't preserve it as an audio codec would. An unknown output such as `.xyz` contains a JSON report rather than a made-up XYZ format. Limits and warnings tell you when content was shortened.

## Optional tools

The app works without these, but installing them adds features:

- **LibreOffice:** Office exports that better preserve the original layout, including older DOC/XLS/PPT files.
- **Tesseract:** text recognition in images and sampled video frames.
- **whisper.cpp with a local model:** offline speech transcription in the standalone EXE.
- **FFprobe:** more detailed media detection and metadata.

The **Capabilities** tab shows what's available. OCR and speech models aren't bundled. Setup instructions and other source-build transcription options are in the [technical guide](docs/technical-guide.md#optional-local-recognition).

## Run from source or build the EXE

On Windows, install Python 3.11 or newer with Tk support, then run **Install Any2Any.cmd** and **Launch Any2Any.cmd**. Run **Build Windows EXE.cmd** to create `dist/Any2Any.exe`.

On macOS or Linux, create and activate a Python environment, then run:

```sh
python -m pip install -r requirements.txt
python -m any2any
```

Linux may also need `python3-tk`. The downloadable EXE is for Windows x64 only.

The source CLI supports previews, batch conversion, and route diagnostics:

```sh
python -m any2any photo.jpg photo.png
python -m any2any video.mp4 frames.pdf --preview
python -m any2any --batch a.pdf b.xlsx --output-dir ./outputs --extension png
```

## Development and verification

Converters register routes through shared types such as text, tables, images, audio, and document pages. The planner prefers lossless conversion, transcoding, content extraction, and representation—in that order—before using bytes. New adapters can reuse these types instead of adding a converter for every file pair.

The existing suite passed **98 tests**. The released EXE also passed GUI initialization, 13 conversions, and a two-file batch from outside the project folder, including a run with an empty PATH. Actual OCR/transcription and manual visual inspection weren't verified.

See the [verification report](verification/TEST_REPORT.md) and [technical guide](docs/technical-guide.md) for architecture, settings, safety limits, testing, and extension points. Review dependency licenses before redistributing a custom build.
