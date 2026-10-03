"""Read generated artifacts before publishing. Invalid output is a hard failure."""
import codecs
import csv
import json
import tarfile
import zipfile
import xml.etree.ElementTree as ET
from .detect import IMAGE_EXTS,AUDIO_EXTS,VIDEO_EXTS
from .model import ConversionError
from .tools import locate,run


class ValidationError(ConversionError): pass


def bounded(ctx,path):
    maximum=ctx.settings.max_read_bytes*2+1024*1024
    if path.stat().st_size>maximum: raise ValidationError('Structured output exceeds validation memory limit; raise the read limit.')
    return path.read_bytes()


def xml(ctx,path):
    data=bounded(ctx,path)
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper(): raise ValidationError('XML declarations/entities are disabled.')
    ET.fromstring(data)


def text(ctx,path):
    with path.open('rb') as source:
        prefix=source.read(4); source.seek(0)
        encoding='utf-16' if prefix.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig'
        decoder=codecs.getincrementaldecoder(encoding)('strict')
        while chunk:=source.read(1024*1024): ctx.check(); decoder.decode(chunk)
        decoder.decode(b'',final=True)


def validate(ctx,plan,ext,detector):
    path=ctx.destination
    try:
        ctx.check()
        if not path.is_file(): raise ValidationError('Backend produced no output.')
        envelope='envelope' in plan.steps[-1].name
        if envelope and ext not in {'xml','csv','tsv'}: json.loads(bounded(ctx,path)); return
        if ext in IMAGE_EXTS and not envelope:
            from PIL import Image
            with Image.open(path) as image: image.verify()
            with Image.open(path) as image:
                for frame in range(getattr(image,'n_frames',1)):
                    ctx.check(); image.seek(frame); image.load()
        elif ext=='pdf' and not envelope:
            import pymupdf
            with pymupdf.open(path) as document:
                if not len(document): raise ValidationError('PDF has no pages.')
                for page in document:
                    ctx.check()
                    import math
                    scale=min(.05,math.sqrt(1_000_000/max(1,page.rect.width*page.rect.height)))
                    page.get_pixmap(matrix=pymupdf.Matrix(scale,scale))
        elif ext in AUDIO_EXTS|VIDEO_EXTS and not envelope:
            detected=detector.detect(path)
            if detected.category not in {'audio','video'}: raise ValidationError('Media is not readable.')
            tool=locate('ffmpeg')
            if not tool: raise ValidationError('Media validation requires FFmpeg.')
            run(ctx,[tool,'-nostdin','-v','error','-xerror','-i',path,'-t','0.25','-f','null','-'])
        elif ext in {'zip','docx','pptx','xlsx','odt','ods','odp'} and not envelope:
            with zipfile.ZipFile(path) as archive:
                for item in archive.infolist():
                    ctx.check()
                    with archive.open(item) as member:
                        while member.read(1024*1024): ctx.check()
                names=set(archive.namelist())
                required={'docx':'word/document.xml','xlsx':'xl/workbook.xml','pptx':'ppt/presentation.xml',
                          'odt':'content.xml','ods':'content.xml','odp':'content.xml'}.get(ext)
                if required and required not in names: raise ValidationError('Office container is missing '+required)
        elif ext=='tar' and not envelope:
            with tarfile.open(path,'r|*') as archive:
                for item in archive:
                    ctx.check()
                    if item.isfile():
                        with archive.extractfile(item) as member:
                            while member.read(1024*1024): ctx.check()
        elif ext in {'gz','bz2','xz'} and not envelope:
            import gzip,bz2,lzma
            with {'gz':gzip.open,'bz2':bz2.open,'xz':lzma.open}[ext](path,'rb') as stream:
                while stream.read(1024*1024): ctx.check()
        elif ext=='7z' and not envelope:
            import py7zr
            with py7zr.SevenZipFile(path) as archive:
                if sum(item.uncompressed or 0 for item in archive.list())>ctx.settings.max_archive_bytes:
                    raise ValidationError('7Z integrity validation exceeds configured expansion limit.')
                if archive.testzip() is not None: raise ValidationError('7Z CRC check failed.')
        elif ext=='json': json.loads(bounded(ctx,path))
        elif ext=='xml': xml(ctx,path)
        elif ext in {'csv','tsv'}:
            with path.open(encoding='utf-8',newline='') as stream:
                for row in csv.reader(stream,delimiter='\t' if ext=='tsv' else ',',strict=True): ctx.check()
        elif ext in {'doc','xls','ppt'} and not envelope:
            with path.open('rb') as stream:
                if stream.read(8)!=b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1': raise ValidationError('Invalid OLE Office header.')
        else: text(ctx,path)
    except Exception as error:
        ctx.check()
        if isinstance(error,ValidationError): raise
        raise ValidationError(f'Output validation failed for .{ext}: {error}') from error
