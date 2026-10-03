from pathlib import Path
import json
import mimetypes
import subprocess
import zipfile
from .model import FormatInfo, ConversionError
from .tools import locate

IMAGE_EXTS = set('png jpg jpeg webp gif bmp tif tiff ico ppm pgm pbm avif tga pcx dds'.split())
AUDIO_EXTS = set('wav mp3 flac ogg opus aac m4a aiff aif wma ac3'.split())
VIDEO_EXTS = set('mp4 mov mkv avi webm m4v mpg mpeg ts wmv flv ogv'.split())
TEXT_EXTS = set('txt md log html htm rtf srt vtt'.split())
DATA_EXTS = set('csv tsv json xml yaml yml'.split())
OFFICE_EXTS = set('doc docx odt xls xlsx ods ppt pptx odp'.split())
ARCHIVE_EXTS = set('zip tar gz bz2 xz 7z'.split())


def category(ext):
    for group, name in ((IMAGE_EXTS, 'image'), (AUDIO_EXTS, 'audio'), (VIDEO_EXTS, 'video'),
                        (TEXT_EXTS, 'text'), (DATA_EXTS, 'data'), (ARCHIVE_EXTS, 'archive')):
        if ext in group:
            return name
    if ext == 'pdf': return 'document'
    if ext in {'xlsx', 'xls', 'ods'}: return 'table'
    if ext in {'pptx', 'ppt', 'odp'}: return 'presentation'
    if ext in {'docx', 'doc', 'odt'}: return 'document'
    return 'binary'


class FormatDetector:
    def detect(self, path):
        path = Path(path)
        if not path.is_file():
            raise ConversionError('Choose an existing regular file.')
        with path.open('rb') as stream:
            head = stream.read(65536)
        ext = path.suffix.lower().lstrip('.')
        fmt, evidence, details = None, 'signature', {}
        detected_category=None
        signatures = [(b'%PDF-', 'pdf'), (b'\x89PNG\r\n\x1a\n', 'png'), (b'\xff\xd8\xff', 'jpeg'),
                      (b'GIF8', 'gif'), (b'BM', 'bmp'), (b'II*\0', 'tiff'), (b'MM\0*', 'tiff'),
                      (b'fLaC', 'flac'), (b'\x1f\x8b', 'gz'), (b'7z\xbc\xaf\x27\x1c', '7z'),
                      (b'BZh', 'bz2'), (b'\xfd7zXZ\0', 'xz'), (b'\x7fELF','elf'),
                      (b'MZ','pe'), (b'SQLite format 3\0','sqlite')]
        for magic, detected in signatures:
            if head.startswith(magic):
                fmt = detected
                break
        if head.startswith(b'RIFF'):
            fmt = {b'WAVE': 'wav', b'WEBP': 'webp', b'AVI ': 'avi'}.get(head[8:12])
        if head.startswith(b'{\\rtf'): fmt='rtf'
        if head.lstrip().lower().startswith((b'<!doctype html',b'<html')): fmt='html'
        if len(head)>=12 and head[4:8]==b'ftyp':
            fmt='mov' if head[8:12]==b'qt  ' else ('m4a' if head[8:12] in {b'M4A ',b'M4B '} else 'mp4')
        if head.startswith(b'\x1aE\xdf\xa3'):
            fmt='webm' if b'webm' in head[:4096] else 'mkv'
        if head.startswith(b'OggS'):
            fmt='ogv' if b'theora' in head[:4096] else ('opus' if b'OpusHead' in head[:4096] else 'ogg')
        if head.startswith(b'ID3') or (len(head)>1 and head[0]==255 and head[1]&0xe0==0xe0 and head[1]&6):
            if fmt is None: fmt='mp3'
        if len(head)>1 and head[0]==255 and head[1]&0xf6==0xf0: fmt='aac'
        if head.startswith((b'\0\0\x01\xba',b'\0\0\x01\xb3')): fmt='mpg'
        if len(head)>376 and head[0]==head[188]==head[376]==0x47: fmt='ts'
        if head.startswith(b'PK'):
            fmt = 'zip'
            try:
                if path.stat().st_size > 64*1024*1024:
                    raise OSError('Container inspection skipped above 64 MiB')
                with zipfile.ZipFile(path) as archive:
                    if len(archive.filelist) <= 100000:
                        names = {item.filename for item in archive.filelist}
                        for prefix, office in [('word/', 'docx'), ('xl/', 'xlsx'), ('ppt/', 'pptx')]:
                            if any(name.startswith(prefix) for name in names):
                                fmt = office
                                break
                        if 'mimetype' in names:
                            item = archive.getinfo('mimetype')
                            if item.file_size < 256:
                                mime = archive.read(item).decode('ascii', 'replace')
                                fmt = {'application/vnd.oasis.opendocument.text': 'odt',
                                       'application/vnd.oasis.opendocument.spreadsheet': 'ods',
                                       'application/vnd.oasis.opendocument.presentation': 'odp'}.get(mime, fmt)
                        evidence = 'ZIP container inspection'
            except (zipfile.BadZipFile, OSError):
                details['warning'] = 'ZIP inspection skipped or damaged container'
        if head[257:262] == b'ustar': fmt = 'tar'
        if head.startswith(b'\xd0\xcf\x11\xe0'):
            fmt = ext if ext in {'doc', 'xls', 'ppt'} else 'ole'
            evidence = 'OLE signature; extension used for subtype'
        # Probe ambiguous media, irrespective of filename. Never executes input data.
        if fmt is None or fmt in AUDIO_EXTS|VIDEO_EXTS:
            probe = locate('ffprobe')
            if probe:
                try:
                    result = subprocess.run([probe, '-protocol_whitelist', 'file,pipe', '-v', 'error', '-probesize', '5000000',
                        '-analyzeduration', '3000000', '-show_format', '-show_streams', '-of', 'json', str(path)],
                        capture_output=True, timeout=10,
                        creationflags=0x08000000 if __import__('os').name == 'nt' else 0)
                    media = json.loads(result.stdout or b'{}')
                    streams = media.get('streams', [])
                    types = {s.get('codec_type') for s in streams if not s.get('disposition', {}).get('attached_pic')}
                    if streams and ('audio' in types or 'video' in types):
                        probed = media.get('format', {}).get('format_name', '').split(',')
                        aliases = {'matroska': 'mkv', 'mpegts': 'ts', 'mpeg': 'mpg', 'asf': 'wmv'}
                        fmt = ext if ext in probed else aliases.get(probed[0], probed[0])
                        if 'mov' in probed:
                            fmt = 'mov' if head[8:12] == b'qt  ' else ('mp4' if 'video' in types else 'm4a')
                        if fmt == 'mkv' and head.find(b'webm') >= 0: fmt = 'webm'
                        cat = 'video' if 'video' in types else 'audio'
                        details = {'duration': media.get('format', {}).get('duration'), 'streams': streams, 'probe':media}
                        codecs = ', '.join(s.get('codec_name', '?') for s in streams)
                        return FormatInfo(fmt, cat, mimetypes.guess_type('a.'+fmt)[0] or 'application/octet-stream',
                                          f'{fmt.upper()} {cat} ({codecs})', 'ffprobe', details)
                except (subprocess.TimeoutExpired, ValueError, OSError, IndexError):
                    pass
        if fmt is None:
            try:
                from PIL import Image
                with Image.open(path) as image:
                    fmt = image.format.lower()
                    detected_category='image'
                    evidence = 'image decoder'
            except Exception:
                pass
        if fmt is None and head:
            try:
                text = head.decode('utf-8-sig')
                if head.startswith((b'\xff\xfe', b'\xfe\xff')):
                    text = head.decode('utf-16')
            except UnicodeError:
                text = None
                if head.startswith((b'\xff\xfe', b'\xfe\xff')):
                    text = head.decode('utf-16', 'replace')
            if text and sum(c.isprintable() or c.isspace() for c in text)/len(text) > .95:
                fmt, evidence = 'txt', 'text content'
                stripped = text.lstrip()
                if stripped.startswith(('{', '[')):
                    try:
                        json.loads(text)
                        fmt = 'json'
                    except ValueError:
                        if ext == 'json': fmt = 'json'
                elif stripped.startswith('<?xml') or (ext == 'xml' and stripped.startswith('<')): fmt = 'xml'
                elif ext in TEXT_EXTS | DATA_EXTS: fmt = ext
        if fmt is None:
            fmt, evidence = 'binary', 'unknown signature (extension is only a hint)'
            details['extension_hint'] = ext
        cat=detected_category or category(fmt)
        return FormatInfo(fmt, cat, mimetypes.guess_type('a.'+fmt)[0] or 'application/octet-stream',
                          f'{fmt.upper()} {cat}', evidence, details)
