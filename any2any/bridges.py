"""Deterministic semantic and binary interpretations; never described as codecs."""
import io
import math
import re
import wave
from .model import ImageData, TextData, TableData, AudioData, ConversionError
from .tools import locate, run


def font(size=20):
    from PIL import ImageFont
    for name in ('C:/Windows/Fonts/consola.ttf', 'DejaVuSans.ttf'):
        try: return ImageFont.truetype(name, size)
        except OSError: pass
    return ImageFont.load_default(size=size)


def text_pages(ctx, value):
    from PIL import Image, ImageDraw
    import textwrap
    w, h = ctx.settings.width, ctx.settings.height
    size = max(10, min(24, w//45))
    f = font(size)
    width = max(1, (w-40)//max(6,int(size*.62)))
    page_lines = max(1, (h-60)//(size+6))
    pages, lines = [], []
    for line in value.text.splitlines() or ['(empty text)']:
        ctx.check()
        lines.extend(textwrap.wrap(line.expandtabs(4), width=width, replace_whitespace=False) or [''])
        if len(lines) > page_lines * ctx.settings.max_pages:
            ctx.warn('Text rendering limited to maximum page count.')
            break
    for start in range(0, min(len(lines), page_lines*ctx.settings.max_pages), page_lines):
        ctx.check()
        image = Image.new('RGB', (w,h), '#fafafa')
        draw = ImageDraw.Draw(image)
        for index, line in enumerate(lines[start:start+page_lines]):
            draw.text((20,20+index*(size+6)), line, fill='#182130', font=f)
        draw.text((20,h-28), f'Any2Any · page {len(pages)+1}', fill='#64748b', font=font(12))
        pages.append(image)
        if len(pages)*w*h>=40_000_000:
            ctx.warn('Text pages capped at 40 million rendered pixels.'); break
    return ImageData(pages)


def table_text(ctx, value):
    stream = io.StringIO()
    import csv
    writer = csv.writer(stream)
    for name, rows in value.sheets:
        ctx.check()
        stream.write(f'[{name}]\n')
        writer.writerows(rows)
    return TextData(stream.getvalue())


def table_pages(ctx, value):
    from PIL import Image, ImageDraw
    w,h = ctx.settings.width, ctx.settings.height
    pages = []
    row_height = 32
    per_page = max(1, (h-90)//row_height)
    for name, rows in value.sheets:
        cols = min(12, max((len(row) for row in rows), default=1))
        if any(len(row)>cols for row in rows): ctx.warn('Table visualization displays the first 12 columns.')
        cell_width = (w-40)/cols
        for start in range(0,max(1,len(rows)),per_page):
            ctx.check()
            if len(pages) >= ctx.settings.max_pages:
                ctx.warn('Table rendering limited to maximum page count.')
                return ImageData(pages)
            image = Image.new('RGB',(w,h),'#f8fafc')
            draw = ImageDraw.Draw(image)
            draw.text((20,15),f'{name} · rows {start+1}–{min(start+per_page,len(rows))}',font=font(20),fill='#172554')
            for index,row in enumerate(rows[start:start+per_page]):
                y=55+index*row_height
                for col in range(cols):
                    x=20+col*cell_width
                    draw.rectangle((x,y,x+cell_width,y+row_height),fill='#e2e8f0' if (start+index)==0 else '#ffffff',outline='#cbd5e1')
                    text = str(row[col] if col<len(row) and row[col] is not None else '')
                    while draw.textlength(text,font=font(14)) > cell_width-12 and text:
                        text=text[:-1]
                    draw.text((x+6,y+7),text,font=font(14),fill='#0f172a')
            pages.append(image)
            if len(pages)*w*h>=40_000_000:
                ctx.warn('Table pages capped at 40 million rendered pixels.'); return ImageData(pages)
    return ImageData(pages)


def write_pcm(ctx, samples):
    import numpy as np
    path = ctx.temporary/'interpretation.wav'
    samples = np.nan_to_num(samples)
    peak = float(np.max(np.abs(samples))) if len(samples) else 0
    if peak: samples = samples/peak*.35
    # Avoid start/end clicks. No randomness, loudness safely below full scale.
    ramp = min(len(samples)//2, int(.02*ctx.settings.sample_rate))
    if ramp:
        samples[:ramp] *= np.linspace(0,1,ramp)
        samples[-ramp:] *= np.linspace(1,0,ramp)
    with wave.open(str(path),'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(ctx.settings.sample_rate)
        stream.writeframes((samples*32767).astype('<i2').tobytes())
    return AudioData(path)


def image_audio(ctx, value):
    import numpy as np
    image=value.pages[0].convert('RGB').resize((128,48))
    rgb=np.asarray(image,dtype=float)/255
    if ctx.settings.image_audio=='scanline':
        brightness=rgb.mean(axis=2).reshape(-1)
        count=int(ctx.settings.audio_seconds*ctx.settings.sample_rate)
        values=np.interp(np.linspace(0,len(brightness)-1,count),np.arange(len(brightness)),brightness)
        frequency=110+values*1760
        phase=np.cumsum(frequency)*2*np.pi/ctx.settings.sample_rate
        ctx.warn('Scanline sonification reads pixels left-to-right, top-to-bottom; brightness maps to 110–1870 Hz and amplitude.')
        return write_pcm(ctx,values*np.sin(phase))
    channels = [rgb.mean(axis=2)] if not (ctx.settings.rgb_audio or ctx.settings.image_audio=='rgb') else [rgb[:,:,i] for i in range(3)]
    count=int(ctx.settings.audio_seconds*ctx.settings.sample_rate)
    output=np.zeros(count,dtype=float)
    time=np.arange(count)/ctx.settings.sample_rate
    positions=np.linspace(0,127,count)
    for channel, grid in enumerate(channels):
        for row in range(48):
            ctx.check()
            freq=110*2**((47-row)/12 + channel)
            amp=np.interp(positions,np.arange(128),grid[row])
            output += amp*np.sin(2*np.pi*freq*time)
    ctx.warn('Image sonification maps horizontal position to time and vertical position to pitch (110 Hz upward); brightness controls amplitude.')
    return write_pcm(ctx,output)


def table_audio(ctx,value):
    import numpy as np
    rows=[row for _,sheet in value.sheets for row in sheet]
    if not rows: rows=[[]]
    if len(rows)>2048:
        rows=rows[:2048]
        ctx.warn('Sonification uses the first 2048 rows.')
    count=int(ctx.settings.audio_seconds*ctx.settings.sample_rate)
    output=np.zeros(count)
    for index,row in enumerate(rows):
        ctx.check()
        begin=index*count//len(rows)
        end=(index+1)*count//len(rows)
        time=np.arange(end-begin)/ctx.settings.sample_rate
        segment=np.zeros(end-begin)
        for column,value in enumerate(row[:16]):
            try: numeric=float(value or 0)
            except (ValueError,TypeError): numeric=sum(ord(c) for c in str(value))
            if not math.isfinite(numeric): numeric=0
            base=110*2**(column/12)
            if ctx.settings.table_audio=='pitch':
                freq=base*2**((abs(numeric)%36)/12)
                amplitude=.5
            else:
                freq=base
                amplitude=abs(numeric)/(1+abs(numeric))
            segment+=amplitude*np.sin(2*np.pi*freq*time)
        if len(segment): segment*=np.sin(np.linspace(0,np.pi,len(segment)))**2
        output[begin:end]=segment
    ctx.warn('Rows map to time; columns to tones. Non-numeric values use character sums. At most 16 columns are sounded.')
    return write_pcm(ctx,output)


def text_audio(ctx,value):
    import os
    import shutil
    if ctx.settings.prefer_tts and os.name!='nt' and locate('espeak'):
        text=ctx.temporary/'speech.txt'; target=ctx.temporary/'speech.wav'
        text.write_text(value.text[:50000] or 'Empty text',encoding='utf-8')
        try:
            run(ctx,[locate('espeak'),'-f',text,'-w',target])
            return AudioData(target)
        except ConversionError as error: ctx.check(); ctx.warn('Local eSpeak unavailable; using character tones: '+str(error)[:200])
    if ctx.settings.prefer_tts and os.name=='nt' and shutil.which('powershell'):
        script=ctx.temporary/'speech.ps1'; text=ctx.temporary/'speech.txt'; target=ctx.temporary/'speech.wav'
        text.write_text(value.text[:50000] or 'Empty text',encoding='utf-8')
        script.write_text('param([string]$InputText,[string]$OutputAudio)\n'
                          '$ErrorActionPreference="Stop"\n'
                          'Add-Type -AssemblyName System.Speech\n'
                          '$speaker=New-Object System.Speech.Synthesis.SpeechSynthesizer\n'
                          'try { $speaker.SetOutputToWaveFile($OutputAudio); '
                          '$speaker.Speak([System.IO.File]::ReadAllText($InputText)); } '
                          'finally { $speaker.Dispose() }',encoding='utf-8')
        try:
            run(ctx,[shutil.which('powershell'),'-NoProfile','-NonInteractive','-File',script,text,target])
            ctx.warn('Local Windows speech synthesizer used (first 50,000 characters); voice depends on installed system voices.')
            return AudioData(target)
        except ConversionError as error:
            ctx.check(); ctx.warn('Local speech synthesis unavailable: '+str(error)[:400]+'; using character tones.')
    import numpy as np
    chars=value.text[:2048] or '\0'
    count=int(ctx.settings.audio_seconds*ctx.settings.sample_rate)
    samples=np.zeros(count)
    for index,char in enumerate(chars):
        ctx.check()
        begin=index*count//len(chars); end=(index+1)*count//len(chars)
        time=np.arange(end-begin)/ctx.settings.sample_rate
        samples[begin:end]=np.sin(2*np.pi*(220*2**((ord(char)%36)/12))*time)*np.sin(np.linspace(0,np.pi,end-begin))**2
    ctx.warn('Deterministic character sonification: first 2048 characters, code point modulo 36 mapped to semitone tones; this is not speech.')
    return write_pcm(ctx,samples)


def audio_pages(ctx,_):
    import numpy as np
    from PIL import Image,ImageDraw
    tool=locate('ffmpeg')
    if not tool: raise ConversionError('Audio visualization requires FFmpeg.')
    raw=ctx.temporary/'audio.pcm'
    run(ctx,[tool,'-nostdin','-v','error','-i',ctx.source,'-t',str(ctx.settings.audio_seconds),
             '-f','s16le','-ac','1','-ar',str(ctx.settings.sample_rate),raw])
    samples=np.fromfile(raw,dtype='<i2').astype(float)/32768
    if len(samples)==0: raise ConversionError('No audio samples decoded.')
    w,h=ctx.settings.width,ctx.settings.height
    image=Image.new('RGB',(w,h),'#101827'); draw=ImageDraw.Draw(image)
    mode=ctx.settings.audio_view
    if mode=='spectrogram':
        n=512; hop=max(1,len(samples)//max(1,w))
        columns=[]
        for begin in range(0,len(samples),hop):
            ctx.check()
            block=np.zeros(n); chunk=samples[begin:begin+n]; block[:len(chunk)]=chunk
            columns.append(np.abs(np.fft.rfft(block*np.hanning(n))))
        magnitude=np.log1p(np.array(columns).T)
        magnitude/=max(1e-9,float(magnitude.max()))
        color=np.stack([magnitude*255,magnitude**2*200,magnitude**.5*230],axis=2).astype('uint8')[::-1]
        image=Image.fromarray(color).resize((w,h))
        draw=ImageDraw.Draw(image)
    elif mode=='spectrum':
        block=samples[:min(65536,len(samples))]
        spectrum=np.log1p(np.abs(np.fft.rfft(block*np.hanning(len(block)))))
        spectrum/=max(1e-9,float(spectrum.max()))
        points=[(x,h-30-float(spectrum[min(len(spectrum)-1,int(x/w*len(spectrum)))])*(h-70)) for x in range(w)]
        draw.line(points,fill='#38bdf8',width=2)
    else:
        for x in range(w):
            ctx.check()
            chunk=samples[x*len(samples)//w:max(x*len(samples)//w+1,(x+1)*len(samples)//w)]
            draw.line((x,h/2-float(chunk.max())*(h/2-50),x,h/2-float(chunk.min())*(h/2-50)),fill='#2dd4bf')
    draw.rectangle((0,0,w,36),fill='#101827')
    draw.text((12,8),f'{mode.title()} · first {len(samples)/ctx.settings.sample_rate:.2f}s · {ctx.settings.sample_rate}Hz',fill='white',font=font(16))
    ctx.warn('Audio visualization is limited to the configured audio duration.')
    return ImageData([image])


def binary_image(ctx,value):
    from PIL import Image
    data=value.data
    maximum=ctx.settings.width*ctx.settings.height*3
    if len(data)>maximum: ctx.warn(f'Binary image shows the first {maximum:,} bytes.')
    data=data[:maximum] or b'\0'
    pixels=math.ceil(len(data)/3)
    width=min(ctx.settings.width,max(1,math.ceil(math.sqrt(pixels))))
    height=math.ceil(pixels/width)
    image=Image.frombytes('RGB',(width,height),data.ljust(width*height*3,b'\0'))
    ctx.info.details['binary_metadata']=value.metadata
    return ImageData([image])


def binary_pdf_pages(ctx,value):
    pages=text_pages(ctx,binary_text(ctx,value))
    visualization=binary_image(ctx,value)
    if len(pages.pages)<ctx.settings.max_pages: pages.pages.extend(visualization.pages)
    return pages


def binary_audio(ctx,value):
    import numpy as np
    values=np.frombuffer(value.data or b'\x80',dtype='uint8').astype(float)/127.5-1
    count=int(ctx.settings.audio_seconds*ctx.settings.sample_rate)
    if len(values)>count: ctx.warn('Binary audio uses a prefix capped by the configured duration.')
    return write_pcm(ctx,values[:count])


def binary_text(ctx,value):
    import json
    data=value.data
    try:
        text=data.decode('utf-8-sig')
        if all(c.isprintable() or c.isspace() for c in text):
            return TextData(json.dumps(value.metadata,indent=2)+'\n\n'+text)
    except UnicodeError: pass
    if data.startswith((b'\xff\xfe',b'\xfe\xff')):
        return TextData(json.dumps(value.metadata,indent=2)+'\n\n'+data.decode('utf-16','replace'))
    strings=re.findall(rb'[\x20-\x7e]{4,}',data)
    report=json.dumps(value.metadata,indent=2)+'\n\nPrintable strings (bounded):\n'
    report+='\n'.join(s.decode('ascii') for s in strings[:1000])
    report+='\n\nHexadecimal preview (first 4096 bytes):\n'
    report+='\n'.join(f'{i:08x}  {data[i:i+16].hex(" ")}' for i in range(0,min(4096,len(data)),16))
    return TextData(report)
