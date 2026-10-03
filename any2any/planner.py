"""A small graph of registered adapters, rather than a source × destination switch."""
from dataclasses import dataclass
import heapq
import itertools
from typing import Callable
from . import readers, bridges, writers, native, semantic, rendering, archives
from .interpretations import permits
from .detect import IMAGE_EXTS,AUDIO_EXTS,VIDEO_EXTS,TEXT_EXTS,OFFICE_EXTS,category
from .tools import locate


@dataclass
class ConverterBackend:
    source: str
    target: str
    name: str
    priority: int
    convert: Callable
    available: Callable = lambda: True


@dataclass
class Plan:
    steps: list[ConverterBackend]
    priority: int
    @property
    def label(self):
        return 'Native conversion' if self.priority<=1 else ('Semantic conversion' if self.priority<=3 else 'Binary interpretation')
    @property
    def route(self):
        return ' → '.join([self.steps[0].source]+[step.name for step in self.steps]+[self.steps[-1].target])


class ConversionRegistry:
    def __init__(self): self.backends=[]
    def register(self,source,target,name,priority,convert,available=lambda:True):
        self.backends.append(ConverterBackend(source,target,name,priority,convert,available))


def module(name):
    import importlib.util
    return lambda: importlib.util.find_spec(name) is not None


def default_registry(info,extension,settings):
    registry=ConversionRegistry(); add=registry.register
    src='input:'+info.category; dest='output:'+extension
    # Direct native paths are registered only where they are actual format-aware operations.
    aliases={'jpg':'jpeg','tif':'tiff','aif':'aiff'}
    if aliases.get(extension,extension)==aliases.get(info.format,info.format) and info.category!='binary':
        add(src,dest,'validated identity copy',0,native.copy)
    if (info.category in {'audio','video'} or (info.format=='gif' and extension in VIDEO_EXTS)) and extension in AUDIO_EXTS|VIDEO_EXTS:
        if info.category=='video' or info.format=='gif' or extension in AUDIO_EXTS:
            if extension in VIDEO_EXTS: add(src,dest,'FFmpeg lossless remux',0,native.remux,lambda:bool(locate('ffmpeg')))
            add(src,dest,'FFmpeg native transcoding',1,native.media,lambda:bool(locate('ffmpeg')))
    if info.format in OFFICE_EXTS and extension in OFFICE_EXTS|{'pdf','csv','txt','html'}:
        compatible=(info.category==category(extension) or extension in {'pdf','txt','html'} or
                    (info.category=='table' and extension=='csv'))
        if compatible: add(src,dest,'LibreOffice headless export',1,native.office,lambda:bool(locate('soffice')))
    if info.category=='image':
        add(src,'pages','Pillow image decoder',0,readers.image_reader,module('PIL'))
        add(src,'text','image metadata / EXIF → OCR → ASCII art / pixel statistics',2,semantic.image_text,module('PIL'))
    if info.category in {'text','data'} and info.format not in {'csv','tsv','json','xml'}:
        add(src,'text','readable HTML / RTF extraction' if info.format in {'html','htm','rtf'} else 'bounded text decoder',
            2 if info.format in {'html','htm','rtf'} else 0,semantic.document_text)
    if info.format in {'xlsx','csv','tsv','json','xml'}:
        add(src,'table','structured table parser',1,readers.table_reader,module('openpyxl') if info.format=='xlsx' else lambda:True)
    if info.format=='ods': add(src,'table','OpenDocument worksheet parser',2,semantic.ods_table)
    if info.format in {'docx','pptx','pdf','odt','odp'}:
        dep={'docx':'docx','pptx':'pptx','pdf':'pymupdf'}.get(info.format)
        add(src,'text','document text extraction with page boundaries',2,semantic.document_text,module(dep) if dep else lambda:True)
    if info.format=='pdf': add(src,'pages','PDF page renderer',3,readers.pdf_reader,module('pymupdf'))
    if info.format in {'pptx','odp'}:
        add(src,'pages','presentation slides: text / pictures with slide aspect ratio',3,semantic.presentation_pages,module('pptx') if info.format=='pptx' else module('PIL'))
    if info.category=='video' or info.format=='gif':
        add(src,'video_source','VideoData: local media source',0,semantic.video_source)
        add('video_source','pages','FFmpeg '+settings.video_view+' / '+settings.frame_mode+' bounded frame sampler',3,rendering.video_frames,lambda:bool(locate('ffmpeg')))
        add('video_source','text','embedded subtitles → metadata → offline transcription → OCR → media analysis',2,semantic.video_text)
    if info.category=='audio':
        add(src,'audio_source','AudioData: local media source',0,semantic.audio_source)
        add('audio_source','pages','audio '+settings.audio_view+' visualization',3,rendering.audio_stereo if settings.audio_view=='stereo' else bridges.audio_pages,
            lambda:bool(locate('ffmpeg')) and module('PIL')())
        add('audio_source','text','audio metadata → offline transcription → signal analysis',2,semantic.audio_text)
    if info.category=='archive': add(src,'archive_tree','safe archive manifest / ArchiveTree',2,archives.tree_reader,module('py7zr') if info.format=='7z' else lambda:True)
    add('archive_tree','text','archive directory tree, entry counts and sizes',2,archives.tree_text)
    add('table','text','readable aligned worksheet tables',2,rendering.table_text)
    add('table','pages','spreadsheet paginated table renderer / '+settings.table_video,3,rendering.table_sequence if extension in VIDEO_EXTS else rendering.table_pages,module('PIL'))
    add('text','pages','wrapped text page renderer / '+settings.text_video,3,rendering.text_sequence if extension in VIDEO_EXTS else rendering.text_pages,module('PIL'))
    add('pages','audio','image sonification / '+settings.image_audio,3,bridges.image_audio,module('numpy'))
    add('table','audio','spreadsheet '+settings.table_audio+' sonification',3,bridges.table_audio,module('numpy'))
    add('text','audio','deterministic character sonification',3,bridges.text_audio,module('numpy'))
    if extension in IMAGE_EXTS: add('pages',dest,'Pillow '+extension.upper()+' encoder',0 if extension in {'png','bmp','tif','tiff','ppm'} else 1,writers.image_writer,module('PIL'))
    if extension=='pdf': add('pages',dest,'aspect-preserving PDF page writer',1,writers.pdf_writer,module('reportlab'))
    if extension in VIDEO_EXTS: add('pages',dest,'slideshow video encoder',3,writers.video_writer,lambda:bool(locate('ffmpeg')))
    if extension in AUDIO_EXTS: add('audio',dest,'PCM / FFmpeg audio encoder',1,writers.audio_writer,lambda:extension=='wav' or bool(locate('ffmpeg')))
    if extension in {'txt','md','log','html','htm','docx','pptx'}:
        add('text',dest,'text/document writer',1 if extension in {'txt','md','log','html','htm'} else 2,writers.text_writer,
            module(extension) if extension in {'docx','pptx'} else lambda:True)
    if extension in {'csv','tsv','json','xml','xlsx'}:
        add('table',dest,'structured table serializer',1,writers.table_writer,module('openpyxl') if extension=='xlsx' else lambda:True)
    if extension in {'csv','tsv','json','xml'}:
        add('text',dest,'semantic text report serializer',2,writers.semantic_report_writer)
    if extension in {'zip','tar','gz','bz2','xz'}: add(src,dest,'stream source into archive container',1,writers.archive_writer)
    add(src,'bytes','bounded binary reader + streaming SHA-256',4,readers.binary_reader)
    if extension=='pdf': add('bytes','pages','binary report: metadata, strings, hex and RGB visualization',4,bridges.binary_pdf_pages,module('PIL'))
    add('bytes','pages','RGB byte visualization',4,bridges.binary_image,module('PIL'))
    add('bytes','audio','normalized bytes to PCM',4,bridges.binary_audio,module('numpy'))
    add('bytes','text','metadata, printable strings and bounded hex',4,bridges.binary_text)
    # Every extension has a final honest envelope, including a known format whose encoder is absent.
    add('bytes',dest,'base64 metadata envelope (JSON/XML/CSV; unknown extensions contain JSON)',4,writers.binary_writer)
    return registry


class ConversionPlanner:
    def plan(self,info,extension,settings,binary_only=False,excluded=None):
        registry=default_registry(info,extension,settings)
        src='input:'+info.category; target='output:'+extension
        queue=[(0,0,0,src,[])]; visited={}; sequence=itertools.count(1)
        while queue:
            priority,cost,_,node,path=heapq.heappop(queue)
            if node==target: return Plan(path,priority)
            # Keep a state per bottleneck priority: a shorter semantic path may
            # become preferable when a later common edge raises both paths to binary.
            state=(node,priority)
            if state in visited and visited[state]<=cost: continue
            visited[state]=cost
            for backend in registry.backends:
                if backend.source!=node or not backend.available() or backend.name in (excluded or set()): continue
                if (binary_only or settings.mode=='binary') and node==src and backend.target!='bytes': continue
                if not binary_only and node==src and not permits(settings.mode,backend): continue
                if settings.mode=='media_text' and node in {'audio_source','video_source'} and backend.target!='text': continue
                # At binary priority prefer a real destination encoder over the generic envelope.
                penalty=100 if 'envelope' in backend.name and extension not in {'json','xml','csv','tsv'} else 1
                heapq.heappush(queue,(max(priority,backend.priority),cost+penalty,next(sequence),backend.target,path+[backend]))
        raise RuntimeError('Registry has no binary fallback route.')

    def diagnostics(self,info,extension,settings):
        """All simple routes in this registry, including unavailable routes, bounded for plugins."""
        registry=default_registry(info,extension,settings)
        src='input:'+info.category; target='output:'+extension
        selected=self.plan(info,extension,settings)
        candidates=[]
        def visit(node,path,seen,blocked):
            if len(candidates)>=1000 or len(path)>12: return
            if node==target:
                priority=max(step.priority for step in path)
                cost=sum(100 if 'envelope' in step.name and extension not in {'json','xml','csv','tsv'} else 1 for step in path)
                route=Plan(path,priority)
                candidates.append({'route':route.route,'classification':route.label,'priority':priority,
                    'score':max(0,[100,90,75,50,10][priority]-len(path)+1),'cost':cost,
                    'available':not blocked,'blocked_by':blocked,'selected':not blocked and route.route==selected.route})
                return
            for step in registry.backends:
                if step.source!=node or step.target in seen: continue
                if node==src and not permits(settings.mode,step): continue
                if settings.mode=='media_text' and node in {'audio_source','video_source'} and step.target!='text': continue
                visit(step.target,path+[step],seen|{step.target},blocked+([] if step.available() else [step.name]))
        visit(src,[],{src},[])
        return sorted(candidates,key=lambda candidate:(not candidate['available'],candidate['priority'],candidate['cost']))
