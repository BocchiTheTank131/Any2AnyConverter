import base64
import csv
import html
import io
import json
from pathlib import Path
import shutil
import zipfile
import tarfile
import xml.etree.ElementTree as ET
from .model import ConversionError
from .tools import locate,run


def image_writer(ctx,value):
    from PIL import Image, PngImagePlugin
    ext=ctx.destination.suffix.lower()[1:]
    if not value.pages: raise ConversionError('No pages to write.')
    page=value.pages[0]
    fmt={'jpg':'JPEG','jpeg':'JPEG','tif':'TIFF','ppm':'PPM','pgm':'PPM','pbm':'PPM'}.get(ext,ext.upper())
    if fmt=='JPEG':
        background=Image.new('RGB',page.size,'white')
        if page.mode=='RGBA': background.paste(page,mask=page.getchannel('A'))
        else: background.paste(page.convert('RGB'))
        page=background
    if ext in {'pgm','pbm'}: page=page.convert('L' if ext=='pgm' else '1')
    if ext=='ico': page=page.copy(); page.thumbnail((256,256))
    options={}
    if fmt=='PNG':
        metadata=PngImagePlugin.PngInfo()
        metadata.add_text('Any2Any',f'{ctx.info.description} interpreted as image. Source: {ctx.source.name}')
        if 'binary_metadata' in ctx.info.details:
            metadata.add_text('Any2AnySource',json.dumps(ctx.info.details['binary_metadata']))
        options['pnginfo']=metadata
    if len(value.pages)>1:
        if fmt in {'GIF','TIFF','WEBP'}:
            options.update(save_all=True,append_images=value.pages[1:])
            if fmt!='TIFF': options.update(duration=value.durations or int(ctx.settings.seconds_per_page*1000),loop=value.loop)
        elif ctx.settings.multi_image:
            for index,extra in enumerate(value.pages[1:]):
                ctx.check()
                target=ctx.temporary/f'extra-{index:03d}.{ext}'
                if fmt=='JPEG':
                    background=Image.new('RGB',extra.size,'white')
                    if extra.mode=='RGBA': background.paste(extra,mask=extra.getchannel('A'))
                    else: background.paste(extra.convert('RGB'))
                    extra=background
                if ext in {'pgm','pbm'}: extra=extra.convert('L' if ext=='pgm' else '1')
                if ext=='ico': extra=extra.copy(); extra.thumbnail((256,256))
                extra.save(target,format=fmt); ctx.additional_outputs.append(target)
            ctx.log(f'Writing {len(value.pages)} separate images; additional pages use .page-NNN filenames.')
        else: ctx.warn('Destination image stores only the first page/frame because multi-image output is disabled.')
    page.save(ctx.destination,format=fmt,**options)


def pdf_writer(ctx,value):
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    document=canvas.Canvas(str(ctx.destination))
    document.setTitle(ctx.source.name)
    if not value.pages: raise ConversionError('No pages to write.')
    for index,image in enumerate(value.pages):
        ctx.check()
        caption=value.captions[index] if index<len(value.captions) else ''
        scale=min(1,1440/max(image.size))
        w,h=image.width*scale,image.height*scale
        footer=24 if caption else 0
        document.setPageSize((w,h+footer))
        document.drawImage(ImageReader(image),0,footer,width=w,height=h,mask='auto')
        if caption:
            document.setFont('Helvetica',9)
            document.drawString(8,8,caption[:200].replace('\n',' '))
        document.showPage()
        ctx.progress(.6+.3*(index+1)/len(value.pages))
    document.save()


def video_writer(ctx,value):
    from PIL import Image
    ffmpeg=locate('ffmpeg')
    if not ffmpeg: raise ConversionError('Video output requires FFmpeg. Install it or set ANY2ANY_FFMPEG.')
    if not value.pages: raise ConversionError('No pages to encode.')
    w=ctx.settings.width//2*2; h=ctx.settings.height//2*2
    ext=ctx.destination.suffix.lower()[1:]
    codec={'webm':'libvpx-vp9','ogv':'libtheora','wmv':'wmv2','mpg':'mpeg2video','mpeg':'mpeg2video'}.get(ext,'libx264')
    if getattr(value,'motion','')=='scroll':
        canvas=value.pages[0].convert('RGB'); path=ctx.temporary/'scroll-canvas.png'; canvas.save(path)
        ideal=max(2,(canvas.height-h)/ctx.settings.scroll_speed+2)
        duration=min(120,ctx.settings.max_pages*ctx.settings.seconds_per_page,ideal)
        if duration<ideal: ctx.warn('Scrolling video duration is capped at 120 seconds and the configured page/time budget; later text may be omitted.')
        filter_=f"fps={ctx.settings.fps},crop={w}:{h}:0:'min(ih-oh,t*{ctx.settings.scroll_speed})',format=yuv420p"
        run(ctx,[ffmpeg,'-nostdin','-v','error','-loop','1','-i',path,'-vf',filter_,'-t',str(duration),'-c:v',codec,ctx.destination])
        return
    # Fixed frame sequence, with optional per-slide fade-in/out; no shell or concat path interpolation.
    for index,page in enumerate(value.pages):
        ctx.check()
        page=page.convert('RGB'); page.thumbnail((w,h))
        canvas=Image.new('RGB',(w,h),'black'); canvas.paste(page,((w-page.width)//2,(h-page.height)//2))
        canvas.save(ctx.temporary/f'slide-{index:05d}.png')
    duration=ctx.settings.seconds_per_page
    filter_=f'fps={ctx.settings.fps},format=yuv420p'
    if ctx.settings.transition=='fade':
        fade=min(.4,duration/4)
        expression=f'min(1,min(mod(T,{duration})/{fade},({duration}-mod(T,{duration}))/{fade}))'
        filter_=f"fps={ctx.settings.fps},format=gbrp,geq=r='r(X,Y)*{expression}':g='g(X,Y)*{expression}':b='b(X,Y)*{expression}',format=yuv420p"
    run(ctx,[ffmpeg,'-nostdin','-v','error','-framerate',str(1/duration),'-i',ctx.temporary/'slide-%05d.png',
             '-vf',filter_,'-t',str(len(value.pages)*duration),'-c:v',codec,ctx.destination])
    if ctx.settings.subtitles and value.captions:
        # Keep subtitles embedded in supported containers, so commit remains one atomic output.
        def stamp(seconds):
            ms=round(seconds*1000); sec,ms=divmod(ms,1000); minute,sec=divmod(sec,60); hour,minute=divmod(minute,60)
            return f'{hour:02}:{minute:02}:{sec:02},{ms:03}'
        subtitles=ctx.temporary/'subtitles.srt'
        subtitles.write_text('\n\n'.join(f'{i+1}\n{stamp(i*duration)} --> {stamp((i+1)*duration)}\n{text}'
                                        for i,text in enumerate(value.captions)),encoding='utf-8')
        if ext in {'mp4','mov','mkv'}:
            intermediate=ctx.temporary/f'without-subs.{ext}'
            ctx.destination.replace(intermediate)
            run(ctx,[ffmpeg,'-nostdin','-v','error','-i',intermediate,'-i',subtitles,'-map','0','-map','1',
                     '-c','copy','-c:s','srt' if ext=='mkv' else 'mov_text',ctx.destination])
        else: ctx.warn('Embedded subtitles supported only in MP4, MOV, MKV; skipped for this container.')


def audio_writer(ctx,value):
    ext=ctx.destination.suffix.lower()[1:]
    if ext=='wav': shutil.copyfile(value.path,ctx.destination); return
    tool=locate('ffmpeg')
    if not tool: raise ConversionError('Compressed audio output requires FFmpeg.')
    options={'mp3':['-c:a','libmp3lame'],'opus':['-c:a','libopus'],'m4a':['-c:a','aac'],
             'wma':['-c:a','wmav2'],'ogg':['-c:a','libvorbis']}.get(ext,[])
    run(ctx,[tool,'-nostdin','-v','error','-i',value.path,*options,ctx.destination])


def text_writer(ctx,value):
    ext=ctx.destination.suffix.lower()[1:]
    text=value.text
    if ext in {'html','htm'}: text='<!doctype html><meta charset="utf-8"><pre>'+html.escape(text)+'</pre>'
    elif ext=='docx':
        from docx import Document
        document=Document()
        for line in text.splitlines():
            ctx.check(); document.add_paragraph(line)
        document.save(ctx.destination); return
    elif ext=='pptx':
        from pptx import Presentation
        presentation=Presentation()
        import textwrap
        chunks=textwrap.wrap(text,1000) or ['']
        for chunk in chunks[:ctx.settings.max_pages]:
            ctx.check(); slide=presentation.slides.add_slide(presentation.slide_layouts[1])
            slide.shapes.title.text=ctx.source.name
            slide.placeholders[1].text=chunk
        presentation.save(ctx.destination); return
    ctx.destination.write_text(text,encoding='utf-8')


def semantic_report_writer(ctx,value):
    """Preserve extracted meaning in structured destinations instead of embedding source bytes."""
    ext=ctx.destination.suffix.lower()[1:]
    fields={'conversion_type':'semantic_extraction','original_name':ctx.source.name,
            'detected_format':ctx.info.description,'text':value.text}
    if ext=='json': ctx.destination.write_text(json.dumps(fields,indent=2,ensure_ascii=False),encoding='utf-8')
    elif ext=='xml':
        root=ET.Element('semantic_report')
        for key,item in fields.items(): ET.SubElement(root,key).text=item
        ET.ElementTree(root).write(ctx.destination,encoding='utf-8',xml_declaration=True)
    else:
        with ctx.destination.open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream,delimiter='\t' if ext=='tsv' else ',')
            writer.writerow(['line','text'])
            for index,line in enumerate(value.text.splitlines()): ctx.check(); writer.writerow([index+1,line])


def table_writer(ctx,value):
    ext=ctx.destination.suffix.lower()[1:]
    if ext=='xlsx':
        from openpyxl import Workbook
        workbook=Workbook(write_only=True)
        for name,rows in value.sheets:
            sheet=workbook.create_sheet(name[:31])
            for row in rows:
                ctx.check()
                # Source strings never become executable formulas in a generated workbook.
                from openpyxl.cell import WriteOnlyCell
                cells=[]
                for item in row:
                    if isinstance(item,(dict,list)): item=json.dumps(item,ensure_ascii=False)
                    cell=WriteOnlyCell(sheet,value=item)
                    if isinstance(item,str): cell.data_type='s'
                    cells.append(cell)
                sheet.append(cells)
        workbook.save(ctx.destination); return
    if ext in {'csv','tsv'}:
        if len(value.sheets)>1: ctx.warn('CSV/TSV stores the first worksheet only.')
        with ctx.destination.open('w',newline='',encoding='utf-8') as stream:
            writer=csv.writer(stream,delimiter='\t' if ext=='tsv' else ',')
            for row in value.sheets[0][1]:
                ctx.check()
                writer.writerow(row)
        ctx.warn('CSV text may be interpreted as formulas when opened in spreadsheet software; Any2Any does not execute it.')
        return
    sheets={name:rows for name,rows in value.sheets}
    if ext=='json': ctx.destination.write_text(json.dumps({'sheets':sheets},indent=2,default=str,ensure_ascii=False),encoding='utf-8')
    else:
        root=ET.Element('workbook')
        for name,rows in value.sheets:
            sheet=ET.SubElement(root,'sheet',name=name)
            for row in rows:
                node=ET.SubElement(sheet,'row')
                for item in row: ET.SubElement(node,'cell').text=str(item if item is not None else '')
        ET.ElementTree(root).write(ctx.destination,encoding='utf-8',xml_declaration=True)


def binary_writer(ctx,value):
    metadata={**value.metadata,'data_encoding':'base64','data':base64.b64encode(value.data).decode('ascii')}
    ext=ctx.destination.suffix.lower()[1:]
    if ext=='xml':
        root=ET.Element('binary_interpretation')
        for key,item in metadata.items(): ET.SubElement(root,key).text=str(item)
        ET.ElementTree(root).write(ctx.destination,encoding='utf-8',xml_declaration=True)
    elif ext in {'csv','tsv'}:
        with ctx.destination.open('w',newline='',encoding='utf-8') as stream:
            writer=csv.writer(stream,delimiter='\t' if ext=='tsv' else ','); writer.writerow(['key','value']); writer.writerows(metadata.items())
    else:
        if ext!='json': ctx.warn(f'.{ext} has no registered encoder. Output is a UTF-8 JSON envelope with this extension; it is not a valid {ext.upper()} codec/container.')
        ctx.destination.write_text(json.dumps(metadata,indent=2),encoding='utf-8')


def archive_writer(ctx,_):
    ext=ctx.destination.suffix.lower()[1:]
    if ext=='zip':
        with zipfile.ZipFile(ctx.destination,'w',zipfile.ZIP_DEFLATED) as archive:
            with archive.open(ctx.source.name,'w',force_zip64=True) as target,ctx.source.open('rb') as source:
                while chunk:=source.read(1024*1024): ctx.check(); target.write(chunk)
    elif ext=='tar':
        # tarfile.add streams but has no callback; feed a cancellation-aware file wrapper.
        with tarfile.open(ctx.destination,'w') as archive,ctx.source.open('rb') as source:
            entry=archive.gettarinfo(str(ctx.source),arcname=ctx.source.name)
            class Reader:
                def read(self,n): ctx.check(); return source.read(n)
            archive.addfile(entry,Reader())
    elif ext in {'gz','bz2','xz'}:
        import gzip,bz2,lzma
        with {'gz':gzip.open,'bz2':bz2.open,'xz':lzma.open}[ext](ctx.destination,'wb') as target,ctx.source.open('rb') as source:
            while chunk:=source.read(1024*1024): ctx.check(); target.write(chunk)
    else:
        raise ConversionError('7Z creation is not registered; use ZIP/TAR/GZIP/BZIP2/XZ.')
