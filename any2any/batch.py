"""Sequential batch execution with stable paths, per-file events and shared cancellation."""
from dataclasses import dataclass,replace
from pathlib import Path
import os
import threading
from .engine import ConversionEngine,normalize_extension
from .model import Cancelled,ConversionError,Settings


@dataclass
class BatchItem:
    source: str
    destination: str
    status: str = 'pending'
    progress: float = 0
    result: object = None
    error: str = ''


class BatchConverter:
    def __init__(self,engine=None): self.engine=engine or ConversionEngine()

    def plan(self,sources,directory,extension,preserve_names=True):
        directory=Path(directory).resolve(); extension=normalize_extension(extension)
        if not directory.is_dir(): raise ConversionError('Choose an existing batch output directory.')
        paths=[Path(source).resolve() for source in sources]
        if not paths: raise ConversionError('Select at least one input file.')
        reserved={os.path.normcase(str(path)) for path in paths}; allocated=set(); items=[]
        for index,source in enumerate(paths):
            stem=source.stem if preserve_names else f'converted-{index+1:03d}'
            destination=directory/(stem+'.'+extension); count=1
            while os.path.normcase(str(destination)) in reserved|allocated:
                count+=1; destination=directory/(stem+f'.converted-{count}.'+extension)
            allocated.add(os.path.normcase(str(destination)))
            items.append(BatchItem(str(source),str(destination)))
        return items

    def convert(self,items,settings=None,cancel=None,log=None,event=None,overwrite=False):
        settings=settings or Settings(); cancel=cancel or threading.Event()
        event=event or (lambda index,item,overall:None); log=log or (lambda message:None)
        for index,item in enumerate(items):
            if cancel.is_set():
                for pending_index,pending in enumerate(items[index:],start=index):
                    pending.status='cancelled'; event(pending_index,pending,index/len(items))
                break
            item.status='converting'; event(index,item,index/len(items))
            def progress(amount):
                item.progress=max(item.progress,amount)
                event(index,item,(index+item.progress)/len(items))
            try:
                selected=settings; warning=None
                if settings.mode not in {'auto','binary'}:
                    from .interpretations import choices,MODES
                    info=self.engine.detector.detect(item.source)
                    if settings.mode not in choices(info,Path(item.destination).suffix.lstrip('.')):
                        warning=f'{MODES[settings.mode][0]} does not apply to {Path(item.source).name}; this batch item uses Auto.'
                        log('Warning: '+warning); selected=replace(settings,mode='auto')
                protected=[other.source for other in items]+[other.destination for other in items if other is not item]
                item.result=self.engine.convert(item.source,item.destination,selected,cancel,log,progress,overwrite,protected_sources=protected)
                if warning: item.result.warnings.append(warning)
                item.status='complete'; item.progress=1
            except Cancelled as error: item.status='cancelled'; item.error=str(error)
            except Exception as error: item.status='failed'; item.error=str(error)
            event(index,item,(index+1)/len(items))
        return items
