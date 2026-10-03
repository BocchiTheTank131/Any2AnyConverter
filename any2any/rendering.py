"""Reusable bounded renderers for text, tables, sampled frames and contact sheets."""
from dataclasses import replace
import math
import re
from .model import ImageData, ImageSequence, TextData, ConversionError
from .tools import locate,run
from .bridges import font


def wrap_line(draw,text,typeface,width):
    """Wrap by measured glyph width, including unbroken tokens."""
    lines=[]; current=''
    for token in re.findall(r'\S+\s*',text.expandtabs(4)):
        if current and draw.textlength(current+token,font=typeface)>width:
            lines.append(current.rstrip()); current=''
        while draw.textlength(token,font=typeface)>width and token:
            lo,hi=1,len(token)
            while lo<hi:
                mid=(lo+hi+1)//2
                if draw.textlength(token[:mid],font=typeface)<=width: lo=mid
                else: hi=mid-1
            lines.append(token[:lo]); token=token[lo:]
        current+=token
    return lines+[current.rstrip()] if current else lines or ['']


def text_pages(ctx,value):
    from PIL import Image,ImageDraw
    w,h=ctx.settings.width,ctx.settings.height; size=ctx.settings.font_size
    margin=min(24,w//8); line_height=size+6; face=font(size)
    draw=ImageDraw.Draw(Image.new('RGB',(1,1)))
    per_page=max(1,(h-2*margin-20)//line_height)
    lines=[]; limit=per_page*ctx.settings.max_pages
    for line in value.text.splitlines() or ['(empty text)']:
        ctx.check()
        lines.extend(wrap_line(draw,line,face,max(1,w-2*margin)))
        if len(lines)>limit:
            ctx.warn('Text rendering capped by maximum page count.'); lines=lines[:limit]; break
    pages=[]; pixels=0
    rgb=tuple(int(ctx.settings.background[index:index+2],16) for index in (1,3,5))
    foreground='#f8fafc' if sum(rgb)/3<128 else '#182130'
    for start in range(0,len(lines),per_page):
        ctx.check(); selected=lines[start:start+per_page]
        height=min(h,max(64,len(selected)*line_height+2*margin+20)) if ctx.settings.auto_height else h
        if pixels+w*height>40_000_000: ctx.warn('Text rendering pixel budget reached.'); break
        image=Image.new('RGB',(w,height),ctx.settings.background); draw=ImageDraw.Draw(image)
        for i,line in enumerate(selected): draw.text((margin,margin+i*line_height),line,fill=foreground,font=face)
        draw.text((margin,height-20),f'Page {len(pages)+1}',fill='#64748b',font=font(10))
        pages.append(image); pixels+=w*height
    return ImageData(pages)


def table_text(ctx,value):
    parts=[]; total=0
    for name,rows in value.sheets:
        ctx.check(); columns=max((len(row) for row in rows),default=1)
        widths=[min(40,max(3,max((len(str(row[c] if c<len(row) and row[c] is not None else '')) for row in rows),default=3))) for c in range(columns)]
        parts.append(f'Worksheet: {name} ({len(rows)} rows × {columns} columns)')
        for index,row in enumerate(rows):
            ctx.check()
            cells=[str(row[c] if c<len(row) and row[c] is not None else '').replace('\n',' ↵ ') for c in range(columns)]
            # Readable, aligned cells; retain full values even when longer than alignment width.
            line=' | '.join(cell.ljust(widths[c]) for c,cell in enumerate(cells))
            if total+len(line)>ctx.settings.max_read_bytes: ctx.warn('Tabular text reached read limit.'); break
            parts.append(line); total+=len(line)
            if index==0: parts.append('-+-'.join('-'*width for width in widths))
        parts.append('')
    return TextData('\n'.join(parts))


def table_pages(ctx,value):
    from PIL import Image,ImageDraw
    w,h=ctx.settings.width,max(160,ctx.settings.height); margin=min(20,w//8)
    size=min(ctx.settings.font_size,24); face=font(size); small=font(12)
    line_height=size+5; pages=[]; budget=0
    for name,rows in value.sheets:
        columns=max((len(row) for row in rows),default=1)
        per_panel=max(1,(w-2*margin)//130)
        for begin_col in range(0,columns,per_panel):
            count=min(per_panel,columns-begin_col); cell_width=(w-2*margin)/count
            prepared=[]
            for row in rows or [['(empty sheet)']]:
                ctx.check(); cells=[]
                for column in range(begin_col,begin_col+count):
                    text=str(row[column] if column<len(row) and row[column] is not None else '')
                    if len(text)>2000: text=text[:1997]+'...'; ctx.warn('Rendered cell text capped at 2000 characters.')
                    draw=ImageDraw.Draw(Image.new('RGB',(1,1)))
                    cell=wrap_line(draw,text,face,max(1,cell_width-12))
                    max_lines=max(1,(h-115)//(2*line_height))
                    if len(cell)>max_lines: cell=cell[:max_lines]; cell[-1]+='…'; ctx.warn('Very tall cells are clipped to fit a page.')
                    cells.append(cell)
                prepared.append((cells,max(len(cell) for cell in cells)*line_height+12))
            index=1
            while True:
                ctx.check()
                if len(pages)>=ctx.settings.max_pages or budget+w*h>40_000_000:
                    ctx.warn('Table pages capped by page/pixel limits.'); return ImageData(pages)
                image=Image.new('RGB',(w,h),ctx.settings.background); draw=ImageDraw.Draw(image)
                draw.text((margin,12),f'{name} · columns {begin_col+1}–{begin_col+count}',font=font(min(20,size)),fill='#172554')
                y=45
                def render(cells,height,header=False):
                    nonlocal y
                    for column,lines in enumerate(cells):
                        x=margin+column*cell_width
                        draw.rectangle((x,y,x+cell_width,y+height),fill='#e2e8f0' if header else 'white',outline='#cbd5e1')
                        for i,line in enumerate(lines): draw.text((x+6,y+6+i*line_height),line,font=face,fill='#0f172a')
                    y+=height
                render(*prepared[0],header=True)
                while index<len(prepared) and y+prepared[index][1]<h-25:
                    render(*prepared[index]); index+=1
                draw.text((margin,h-20),f'Page {len(pages)+1} · header repeated',font=small,fill='#64748b')
                pages.append(image); budget+=w*h
                if index>=len(prepared): break
    return ImageData(pages)


def table_sequence(ctx,value):
    if ctx.settings.table_video=='sheets': return table_pages(ctx,value)
    ctx.warn('Progressive rows display the newest table page/panel; choose worksheet slides for complete horizontal and vertical pagination.')
    from .model import TableData
    pages=[]
    for name,rows in value.sheets:
        for count in range(2,max(3,len(rows)+1)):
            ctx.check()
            if len(pages)>=ctx.settings.max_pages: ctx.warn('Progressive rows capped at maximum frame count.'); return ImageSequence(pages)
            # Last table page shows the newest row, retaining repeated headers.
            local=replace(ctx,settings=replace(ctx.settings,max_pages=min(20,ctx.settings.max_pages)))
            rendered=table_pages(local,TableData([(name,rows[:count])]))
            if rendered.pages: pages.append(rendered.pages[-1])
            if sum(image.width*image.height for image in pages)>=40_000_000: ctx.warn('Progressive rows reached pixel budget.'); return ImageSequence(pages)
    return ImageSequence(pages)


def text_sequence(ctx,value):
    if ctx.settings.text_video=='slides': return text_pages(ctx,value)
    from PIL import Image,ImageDraw
    # Render clean wrapped pages, stitch only within a bounded tall canvas, then pan through it.
    local=replace(ctx,settings=replace(ctx.settings,auto_height=True))
    rendered=text_pages(local,value)
    w,h=ctx.settings.width,ctx.settings.height
    max_height=min(16000,40_000_000//w)
    height=min(max_height,sum(page.height for page in rendered.pages))
    canvas=Image.new('RGB',(w,max(h,height)),ctx.settings.background); y=0
    for page in rendered.pages:
        if y>=height: ctx.warn('Scrolling canvas is bounded; later text omitted.'); break
        canvas.paste(page,(0,y)); y+=page.height
    return ImageSequence([canvas],motion='scroll')


def duration(ctx):
    from .semantic import probe,optional
    data=optional(ctx,'Duration probe',lambda:probe(ctx)) or {}
    try:
        value=float(data.get('format',{}).get('duration') or ctx.info.details.get('duration') or 0)
        if value>0: return value
    except (TypeError,ValueError): pass
    # The bundled FFmpeg can read duration even without a separate ffprobe executable.
    tool=locate('ffmpeg')
    if not tool: return 0
    run(ctx,[tool,'-nostdin','-v','info','-i',ctx.source,'-t','0.01','-f','null','-'])
    text=(ctx.temporary/'external.log').read_text(errors='replace')
    match=re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)',text)
    return sum(float(value)*factor for value,factor in zip(match.groups(),(3600,60,1))) if match else 0


def contact_sheet(ctx,value):
    from PIL import Image,ImageDraw
    count=len(value.pages)
    if not count: raise ConversionError('No frames for contact sheet.')
    w,h=ctx.settings.width,ctx.settings.height
    columns=math.ceil(math.sqrt(count*w/max(1,h))); columns=min(count,max(1,columns)); rows=math.ceil(count/columns)
    cell_w=w//columns; cell_h=h//rows
    canvas=Image.new('RGB',(w,h),'#101827'); draw=ImageDraw.Draw(canvas)
    for index,page in enumerate(value.pages):
        ctx.check(); page=page.convert('RGB'); page.thumbnail((max(1,cell_w-8),max(1,cell_h-24)))
        x=(index%columns)*cell_w; y=(index//columns)*cell_h
        canvas.paste(page,(x+(cell_w-page.width)//2,y+2))
        caption=value.captions[index] if index<len(value.captions) else f'Frame {index+1}'
        draw.text((x+4,y+cell_h-18),caption,font=font(10),fill='white')
    return ImageData([canvas])


def video_frames(ctx,_):
    from PIL import Image
    settings=ctx.settings; tool=locate('ffmpeg')
    if not tool: raise ConversionError('Video frame extraction requires FFmpeg.')
    for old in ctx.temporary.glob('frame-*.png'): old.unlink()
    view=settings.video_view; single=view in {'first','middle','last'}
    count=1 if single else settings.max_pages
    max_w=min(settings.width,max(1,int(math.sqrt(40_000_000/count*settings.width/settings.height))))
    max_h=min(settings.height,max(1,int(40_000_000/count/max_w)))
    scale=f'scale={max_w}:{max_h}:force_original_aspect_ratio=decrease'
    seconds=duration(ctx) if view in {'middle','last','contact'} or settings.frame_mode=='even' else 0
    seek=0
    if view=='middle': seek=seconds/2
    if view=='last': seek=max(0,seconds-.15)
    if view in {'middle','last'} and not seconds: ctx.warn('Duration unavailable; using first frame.')
    selection='select=1'; sample_seconds=settings.frame_interval
    if not single:
        if settings.frame_mode=='frames': selection=f'select=not(mod(n\\,{max(1,int(settings.frame_interval))}))'
        elif settings.frame_mode=='every': selection='select=1'
        elif settings.frame_mode=='scene': selection=f'select=eq(n\\,0)+gt(scene\\,{settings.scene_threshold})'
        else:
            if settings.frame_mode=='even' or view=='contact':
                if seconds:
                    count=min(count,max(1,math.ceil(seconds*24)))
                    sample_seconds=seconds/count
                else: ctx.warn('Duration unavailable; using timed sampling for distributed samples.')
            selection=f'fps=1/{sample_seconds}:start_time=0:round=up:eof_action=pass'
    args=[tool,'-nostdin','-v','info']
    if seek: args+=['-ss',str(seek)]
    args+=['-i',ctx.source,'-vf',selection+','+scale+',showinfo','-fps_mode','vfr','-frames:v',str(count),ctx.temporary/'frame-%05d.png']
    run(ctx,args)
    paths=sorted(ctx.temporary.glob('frame-*.png'))
    if not paths:
        ctx.warn('Sampler produced no frames; using first decodable frame.')
        run(ctx,[tool,'-nostdin','-v','info','-i',ctx.source,'-vf',scale+',showinfo','-frames:v','1',ctx.temporary/'frame-00001.png'])
        paths=sorted(ctx.temporary.glob('frame-*.png'))
    text=(ctx.temporary/'external.log').read_text(errors='replace')
    times=re.findall(r'pts_time:([\d.]+)',text); pages=[]; captions=[]
    for index,path in enumerate(paths):
        ctx.check()
        with Image.open(path) as image: pages.append(image.copy())
        captions.append(f'{seek+(float(times[index]) if index<len(times) else index*sample_seconds):.2f} s')
    if not pages: raise ConversionError('Video has no decodable frames.')
    ctx.warn(f'Frame extraction retained {len(pages)} frames; maximum {settings.max_pages}.')
    durations=[max(10,round(sample_seconds*1000))]*len(pages) if view=='animated' else []
    sequence=ImageSequence(pages,captions if settings.timestamps else [],durations)
    return contact_sheet(ctx,sequence) if view=='contact' else sequence


def audio_stereo(ctx,_):
    import wave
    import numpy as np
    from PIL import Image,ImageDraw
    from .semantic import decoded_audio
    path=decoded_audio(ctx,channels=2)
    with wave.open(str(path),'rb') as source:
        if source.getsampwidth()!=2: raise ConversionError('Stereo visualization requires 16-bit PCM.')
        channels=source.getnchannels()
        data=source.readframes(int(ctx.settings.audio_seconds*source.getframerate()))
    samples=np.frombuffer(data,dtype='<i2').astype(float).reshape(-1,channels)/32768
    if not len(samples): raise ConversionError('No decoded audio.')
    w,h=ctx.settings.width,ctx.settings.height
    image=Image.new('RGB',(w,h),'#101827'); draw=ImageDraw.Draw(image)
    for channel in range(min(2,channels)):
        center=h*(.28 if channel==0 else .75)
        draw.text((12,center-h*.2),'Left' if channel==0 else 'Right',font=font(14),fill='white')
        for x in range(w):
            ctx.check(); begin=x*len(samples)//w; end=max(begin+1,(x+1)*len(samples)//w)
            block=samples[begin:end,channel]
            draw.line((x,center-float(block.max())*h*.19,x,center-float(block.min())*h*.19),
                      fill='#38bdf8' if channel==0 else '#2dd4bf')
    draw.text((12,8),'Stereo waveform · bounded decoded prefix (mono inputs duplicate channels)',font=font(14),fill='white')
    return ImageData([image])
