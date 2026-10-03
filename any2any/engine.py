from dataclasses import dataclass,field,replace
from pathlib import Path
import json
import os
import re
import tempfile
import threading
import time
from .detect import FormatDetector
from .model import Context,Settings,ConversionError,Cancelled
from .planner import ConversionPlanner
from .validation import ValidationError,validate


def normalize_extension(value):
    extension=value.strip().lower().lstrip('.')
    if not re.fullmatch(r'[a-z0-9][a-z0-9_+-]{0,23}',extension):
        raise ConversionError('Enter an extension of 1–24 letters, digits, underscores, + or - (for example .pdf).')
    return extension


@dataclass
class ConversionResult:
    input_format: str
    destination_format: str
    classification: str
    route: str
    input_size: int
    output_size: int
    duration: float
    warnings: list
    destination: str
    additional_paths: list[str] = field(default_factory=list)


class ConversionEngine:
    def __init__(self):
        self.detector=FormatDetector(); self.planner=ConversionPlanner()

    def preview(self,source,extension,settings=None):
        settings=settings or Settings(); settings.validate()
        from .interpretations import effective
        settings=effective(settings)
        extension=normalize_extension(extension)
        info=self.detector.detect(source)
        return info,self.planner.plan(info,extension,settings)

    def convert(self,source,destination,settings=None,cancel=None,log=None,progress=None,overwrite=False,protected_sources=None):
        source=Path(source).resolve(); destination=Path(destination).absolute()
        if not source.is_file(): raise ConversionError('Choose an existing regular input file.')
        if source==destination.resolve() or (destination.exists() and os.path.samefile(source,destination)):
            raise ConversionError('The output must never overwrite the input file.')
        if destination.exists() and not overwrite: raise ConversionError('Output already exists. Confirm overwrite first.')
        if not destination.parent.is_dir(): raise ConversionError('Output directory does not exist.')
        settings=settings or Settings(); settings.validate()
        from .interpretations import effective
        settings=effective(settings)
        extension=normalize_extension(destination.suffix)
        cancel=cancel or threading.Event(); log=log or (lambda message:None); progress=progress or (lambda amount:None)
        started=time.monotonic()
        if cancel.is_set(): raise Cancelled('Conversion cancelled before detection.')
        info=self.detector.detect(source)
        with tempfile.TemporaryDirectory(prefix='.any2any-',dir=destination.parent) as folder:
            temp=Path(folder); staged=temp/('result.'+extension)
            ctx=Context(source,staged,info,settings,temp,cancel,log,progress)
            ctx.protected_sources=[Path(path).resolve() for path in (protected_sources or [])]
            plan=self.planner.plan(info,extension,settings)
            excluded=set()
            while True:
                ctx.check(); log(plan.label+': '+plan.route)
                ctx.additional_outputs.clear()
                value=None; failed=None
                try:
                    for index,step in enumerate(plan.steps):
                        ctx.check(); failed=step
                        log(step.name); value=step.convert(ctx,value)
                        progress(.1+.75*(index+1)/len(plan.steps))
                    self.validate(ctx,plan,extension)
                    for extra in ctx.additional_outputs: self.validate(replace(ctx,destination=extra),plan,extension)
                    break
                except Cancelled: raise
                except ValidationError:
                    staged.unlink(missing_ok=True)
                    raise
                except Exception as error:
                    ctx.check()
                    if plan.priority==4 and failed and ('envelope' in failed.name):
                        raise ConversionError(f'Binary envelope failed: {error}') from error
                    ctx.warn(f'{failed.name if failed else "Validation"} failed: {error}')
                    staged.unlink(missing_ok=True)
                    if plan.priority<4:
                        ctx.warn('Trying the next available route; binary interpretation is used if native and semantic decoders fail.')
                    if failed: excluded.add(failed.name)
                    # Validation failures exclude the writer; avoids repeating an invalid codec.
                    if failed is None: excluded.add(plan.steps[-1].name)
                    plan=self.planner.plan(info,extension,settings,binary_only=plan.priority>=4,excluded=excluded)
            ctx.check()
            if not staged.exists(): raise ConversionError('Backend did not produce a file.')
            pairs=[(staged,destination)]+[(extra,destination.with_name(destination.stem+f'.page-{index+2:03d}'+destination.suffix))
                                         for index,extra in enumerate(ctx.additional_outputs)]
            publish(ctx,pairs,overwrite)
            progress(1)
            return ConversionResult(info.description,extension,plan.label,plan.route,source.stat().st_size,
                                    sum(path.stat().st_size for _,path in pairs),time.monotonic()-started,ctx.warnings,str(destination),
                                    [str(path) for _,path in pairs[1:]])

    def validate(self,ctx,plan,ext):
        return validate(ctx,plan,ext,self.detector)


def publish(ctx,pairs,overwrite):
    """Validate first, publish as a rollback-capable group; collisions never damage inputs."""
    import shutil
    backups=[]; published=[]
    for _,path in pairs:
        for protected in [ctx.source,*ctx.protected_sources]:
            if path.resolve()==protected or (path.exists() and protected.exists() and os.path.samefile(path,protected)):
                raise ConversionError('An output page would overwrite a protected input or another batch target: '+str(path))
        if path.exists() and not overwrite: raise ConversionError(f'Output already exists; confirm overwrite: {path}')
    try:
        for index,(staged,path) in enumerate(pairs):
            ctx.check()
            if path.exists() and overwrite:
                backup=ctx.temporary/f'backup-{index}'
                shutil.copy2(path,backup); backups.append((backup,path))
                os.replace(staged,path)
            else:
                os.link(staged,path)
            published.append(path)
    except Exception:
        for path in reversed(published): path.unlink(missing_ok=True)
        for backup,path in backups: os.replace(backup,path)
        raise
