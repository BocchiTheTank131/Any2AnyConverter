import shutil
from .model import ConversionError
from .tools import locate,run


def copy(ctx,_):
    # Reject damaged detected inputs before copying, so other decoders can still be tried.
    if ctx.info.category=='image':
        from PIL import Image
        with Image.open(ctx.source) as image:
            if image.width*image.height>40_000_000: raise ConversionError('Image exceeds the pixel safety limit.')
            image.verify()
    elif ctx.info.format=='pdf':
        import pymupdf
        with pymupdf.open(ctx.source) as document:
            if not len(document): raise ConversionError('Source PDF has no pages.')
    elif ctx.info.format in {'zip','docx','pptx','xlsx','odt','ods','odp','7z'}:
        from .readers import small_container
        small_container(ctx)
    with ctx.source.open('rb') as source,ctx.destination.open('wb') as target:
        while chunk:=source.read(1024*1024): ctx.check(); target.write(chunk)


def remux(ctx,_):
    tool=locate('ffmpeg')
    if not tool: raise ConversionError('FFmpeg unavailable.')
    run(ctx,[tool,'-nostdin','-v','error','-i',ctx.source,'-map','0:v:0','-map','0:a?',
             '-c','copy',ctx.destination])


def media(ctx,_):
    tool=locate('ffmpeg')
    if not tool: raise ConversionError('FFmpeg is unavailable.')
    ext=ctx.destination.suffix.lower()[1:]
    from .detect import AUDIO_EXTS
    if ext in AUDIO_EXTS:
        options={'wav':['-c:a','pcm_s16le'],'mp3':['-c:a','libmp3lame'],'opus':['-c:a','libopus'],
                 'm4a':['-c:a','aac'],'wma':['-c:a','wmav2'],'ogg':['-c:a','libvorbis']}.get(ext,[])
        run(ctx,[tool,'-nostdin','-v','error','-i',ctx.source,'-vn',*options,ctx.destination])
        return
    codecs={'webm':['-c:v','libvpx-vp9','-c:a','libopus'], 'ogv':['-c:v','libtheora','-c:a','libvorbis'],
            'wmv':['-c:v','wmv2','-c:a','wmav2'], 'mpg':['-c:v','mpeg2video','-c:a','mp2'],
            'mpeg':['-c:v','mpeg2video','-c:a','mp2']}.get(ext,['-c:v','libx264','-c:a','aac'])
    run(ctx,[tool,'-nostdin','-v','error','-i',ctx.source,'-map','0:v:0','-map','0:a?',
             *codecs,'-pix_fmt','yuv420p','-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2',ctx.destination])


def office(ctx,_):
    from .readers import small_container
    small_container(ctx)
    tool=locate('soffice')
    if not tool: raise ConversionError('LibreOffice is unavailable.')
    # Private user profile prevents interference with an existing office session.
    profile=ctx.temporary/'lo-profile'
    safe_input=ctx.temporary/('office-input.'+ctx.info.format)
    shutil.copyfile(ctx.source,safe_input)
    # Never open macro-enabled content; headless import does not run macros, profile further disables them.
    profile.mkdir()
    (profile/'user').mkdir()
    (profile/'user'/'registrymodifications.xcu').write_text(
        '<?xml version="1.0"?><oor:items xmlns:oor="http://openoffice.org/2001/registry">'
        '<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse">'
        '<value>3</value></prop></item></oor:items>',encoding='utf-8')
    out=ctx.temporary/'office-output'; out.mkdir()
    run(ctx,[tool,'-env:UserInstallation='+profile.as_uri(),'--headless','--norestore','--convert-to',
             ctx.destination.suffix[1:],'--outdir',out,safe_input])
    generated=out/('office-input'+ctx.destination.suffix)
    if not generated.is_file(): raise ConversionError('LibreOffice did not produce the requested output.')
    shutil.copyfile(generated,ctx.destination)
