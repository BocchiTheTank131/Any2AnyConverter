from pathlib import Path
import os
import shutil
import subprocess
import time
from .model import ConversionError


def locate(name):
    configured = os.environ.get('ANY2ANY_' + name.upper().replace('-','_'))
    if configured and Path(configured).is_file():
        return configured
    found = shutil.which(name)
    if found:
        return found
    if name == 'ffmpeg':
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, RuntimeError):
            pass
    if name == 'soffice':
        for root in ('C:/Program Files', 'C:/Program Files (x86)'):
            path = Path(root) / 'LibreOffice/program/soffice.exe'
            if path.exists():
                return str(path)
    if name=='tesseract':
        path=Path('C:/Program Files/Tesseract-OCR/tesseract.exe')
        if path.is_file(): return str(path)
    return None


def run(ctx, arguments):
    """No shell, bounded log file, cancellation/timeout, no terminal windows."""
    ctx.check()
    arguments=list(arguments)
    if Path(arguments[0]).stem.lower().startswith('ffmpeg'):
        arguments[1:1]=['-y','-protocol_whitelist','file,pipe']
    ctx.log('Running ' + Path(arguments[0]).name)
    log_path = ctx.temporary / 'external.log'
    start = time.monotonic()
    with log_path.open('wb') as output:
        process = subprocess.Popen([str(x) for x in arguments], stdout=output, stderr=output,
                                   stdin=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            while process.poll() is None:
                ctx.check()
                if time.monotonic() - start > ctx.settings.tool_timeout:
                    raise ConversionError('External tool timed out. Increase the timeout for long conversions.')
                if log_path.stat().st_size>ctx.settings.max_read_bytes*2+1024*1024:
                    raise ConversionError('External tool log exceeded the configured safety limit.')
                time.sleep(.08)
        finally:
            if process.poll() is None:
                if os.name=='nt':
                    try:
                        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,
                                       timeout=5,creationflags=subprocess.CREATE_NO_WINDOW)
                    except (OSError,subprocess.TimeoutExpired):
                        pass
                process.kill()
                process.wait()
    if process.returncode:
        with log_path.open('rb') as stream:
            stream.seek(max(0, log_path.stat().st_size - 6000))
            message = stream.read().decode('utf-8', 'replace')
        raise ConversionError(f'{Path(arguments[0]).name} failed:\n{message}')


def capabilities():
    import importlib.util
    return {**{name: locate(name) or 'Unavailable' for name in ('ffmpeg', 'ffprobe', 'soffice', 'magick')},
            **{name: 'Available' if importlib.util.find_spec(name) else 'Unavailable'
               for name in ('PIL', 'pymupdf', 'openpyxl', 'docx', 'pptx', 'py7zr', 'tkinterdnd2')}}


def capability_groups():
    """Human-readable capability descriptions; absent optional tools are informative."""
    import importlib.util
    from .semantic import transcription_backend
    groups=[('Media backend',[
        ('FFmpeg',bool(locate('ffmpeg')),'Audio/video decoding, encoding, frame sampling, signal analysis.',locate('ffmpeg')),
        ('ffprobe',bool(locate('ffprobe')),'Detailed codec, duration, tags, channels, bitrate and subtitle discovery.',locate('ffprobe'))]),
        ('Image backend',[
        ('Pillow',bool(importlib.util.find_spec('PIL')),'Image decoding, encoding, ASCII art and rendering.',None),
        ('ImageMagick',bool(locate('magick')),'Detected for future specialized codecs; no active ImageMagick adapter is registered.',locate('magick'))]),
        ('Office backend',[
        ('LibreOffice',bool(locate('soffice')),'Native DOC/XLS/PPT → PDF; faithful slide rendering; native ODT/ODS/ODP import/export.',locate('soffice'))]),
        ('Document backend',[
        ('PyMuPDF',bool(importlib.util.find_spec('pymupdf')),'PDF text extraction, page rendering and validation.',None),
        ('python-docx',bool(importlib.util.find_spec('docx')),'DOCX readable text and generated documents.',None),
        ('python-pptx',bool(importlib.util.find_spec('pptx')),'PPTX text, pictures and slide rendering.',None),
        ('openpyxl',bool(importlib.util.find_spec('openpyxl')),'XLSX parsing and writing.',None),
        ('striprtf',bool(importlib.util.find_spec('striprtf')),'Readable RTF text extraction.',None)]),
        ('Archive backend',[
        ('py7zr',bool(importlib.util.find_spec('py7zr')),'7Z metadata trees and integrity validation.',None)]),
        ('Local recognition',[
        ('Tesseract OCR',bool(locate('tesseract')),'Image text and sampled video-frame OCR.',locate('tesseract')),
        ('Offline speech recognition',bool(transcription_backend()),'Audio/video transcription. Requires Whisper/faster-whisper or whisper-cli plus ANY2ANY_WHISPER_MODEL pointing to existing local weights. No downloads.',transcription_backend()),
        ('Local TTS',bool(shutil.which('powershell')) if os.name=='nt' else bool(locate('espeak')),
         'Windows System.Speech voices or eSpeak. Backend availability is checked when used; character tones remain available.',None)])]
    return [{'group':group,'items':[{'name':name,'status':'Available' if available else 'Missing',
             'functionality':description,'path':path} for name,available,description,path in items]} for group,items in groups]
