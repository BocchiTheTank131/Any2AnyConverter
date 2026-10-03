"""Structured archive trees; members remain data and are never extracted to disk."""
from pathlib import PurePosixPath
import tarfile
import zipfile
from .model import ArchiveTree,TextData,ConversionError
from .readers import small_container,archive_reader


def tree_reader(ctx,_):
    small_container(ctx); entries=[]; total=0
    def add(name,size,compressed=None,directory=False):
        nonlocal total
        ctx.check(); total+=size
        if len(entries)>=ctx.settings.max_archive_entries: raise ConversionError('Archive entry limit exceeded.')
        if total>ctx.settings.max_archive_bytes: raise ConversionError('Archive expanded-size safety limit exceeded.')
        path=PurePosixPath(name.replace('\\','/'))
        safe=not(path.is_absolute() or '..' in path.parts or ':' in name)
        entries.append({'name':name,'uncompressed_size':size,'compressed_size':compressed,
                        'directory':directory,'safe_path':safe})
    fmt=ctx.info.format
    if fmt=='zip':
        with zipfile.ZipFile(ctx.source) as archive:
            for item in archive.infolist(): add(item.filename,item.file_size,item.compress_size,item.is_dir())
    elif fmt=='7z':
        import py7zr
        with py7zr.SevenZipFile(ctx.source) as archive:
            for item in archive.list(): add(item.filename,item.uncompressed or 0,getattr(item,'compressed',None),item.is_directory)
    elif fmt=='tar' or tarfile.is_tarfile(ctx.source):
        with tarfile.open(ctx.source,'r|*') as archive:
            for item in archive: add(item.name,item.size,None,item.isdir())
    else:
        # The existing bounded stream reader validates expansion without materializing filesystem members.
        report=archive_reader(ctx,None)
        import re
        match=re.search(r'^\s*(\d+)\s+(.+)$',report.text,re.M)
        add(ctx.source.stem,int(match.group(1)) if match else 0,ctx.source.stat().st_size)
    return ArchiveTree(ctx.source.name,fmt,ctx.source.stat().st_size,entries)


def tree_text(ctx,value):
    lines=[f'Archive: {value.name}',f'Format: {value.format}',f'Entry count: {len(value.entries)}',
           f'Compressed file size: {value.compressed_size:,} bytes',
           f'Uncompressed entries total: {sum(item["uncompressed_size"] for item in value.entries):,} bytes','',
           'Directory tree / filenames (compressed → uncompressed bytes):']
    tree={}; unsafe=[]
    for item in value.entries:
        ctx.check(); parts=PurePosixPath(item['name'].replace('\\','/')).parts
        if not item['safe_path'] or len(parts)>32:
            unsafe.append(item); continue
        level=tree
        for part in parts:
            node=level.setdefault(part,{'children':{},'entry':None}); level=node['children']
        if parts: node['entry']=item
    def display(level,depth=0):
        for name,node in sorted(level.items()):
            ctx.check(); item=node['entry']
            label='  '*depth+'- '+name+('/' if node['children'] or (item and item['directory']) else '')
            if item:
                compressed=str(item['compressed_size']) if item['compressed_size'] is not None else 'not available per entry'
                label+=f' [{compressed} → {item["uncompressed_size"]}] ({item["name"]})'
            lines.append(label); display(node['children'],depth+1)
    display(tree)
    for item in unsafe:
        lines.append(f'{item["name"]} [{item["compressed_size"]} → {item["uncompressed_size"]}]'+
                     (' [unsafe path; never extracted]' if not item['safe_path'] else ' [deep path listed without expansion]'))
    if ctx.settings.archive_text:
        report=archive_reader(ctx,None)
        lines+=['','Safe readable member inspection:',report.text]
    return TextData('\n'.join(lines)[:ctx.settings.max_read_bytes])
