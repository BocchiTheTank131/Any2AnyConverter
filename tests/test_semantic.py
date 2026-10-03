"""Behavior tests for semantic meaning, selection, validation and batch safety."""
from dataclasses import replace
import json
from pathlib import Path
import threading
import wave
import zipfile
import pytest
from PIL import Image,PngImagePlugin
import pymupdf
from test_conversion import engine,sources
from any2any.model import Settings,Context,ConversionError
from any2any.validation import ValidationError
from any2any.batch import BatchConverter
from any2any.interpretations import effective
from any2any.tools import capability_groups


def test_image_text_meaning_and_ocr(engine,tmp_path,monkeypatch):
    source=tmp_path/'metadata.png'; metadata=PngImagePlugin.PngInfo(); metadata.add_text('Author','Any2Any Test')
    Image.new('RGB',(80,40),'#123456').save(source,pnginfo=metadata)
    monkeypatch.setattr('any2any.semantic.ocr',lambda *args,**kw:'Recognized words')
    result=engine.convert(source,tmp_path/'image.txt')
    text=Path(result.destination).read_text(encoding='utf-8')
    assert result.classification=='Semantic conversion'
    assert all(value in text for value in ['Any2Any Test','Recognized words','ASCII-art','Pixel statistics','mean_RGB'])
    assert 'Hexadecimal' not in text


def test_audio_text_analysis_without_optional_recognition(engine,sources,tmp_path):
    result=engine.convert(sources['wav'],tmp_path/'analysis.txt',Settings(transcribe=True,audio_seconds=1))
    text=Path(result.destination).read_text(encoding='utf-8')
    assert result.classification=='Semantic conversion'
    assert all(value in text for value in ['codec_name','channels','sample_rate','rms_level_dbfs','peak_level_dbfs','silence_sections'])
    assert any('local model/backend' in warning for warning in result.warnings)


def test_audio_silence_sections(engine,tmp_path):
    source=tmp_path/'silent.wav'
    with wave.open(str(source),'wb') as stream:
        stream.setparams((1,2,22050,0,'NONE','not compressed')); stream.writeframes(b'\0'*(22050*2))
    result=engine.convert(source,tmp_path/'silence.txt',Settings(audio_seconds=1))
    text=Path(result.destination).read_text(encoding='utf-8')
    assert '0.0' in text and '1.0' in text and '-240.0' in text and result.classification=='Semantic conversion'


@pytest.mark.parametrize('source',['png','wav'])
@pytest.mark.parametrize('extension',['json','xml','csv'])
def test_extracted_structured_reports(engine,sources,tmp_path,source,extension):
    result=engine.convert(sources[source],tmp_path/f'report.{extension}',Settings(audio_seconds=.2,ocr=False))
    assert result.classification=='Semantic conversion' and 'report serializer' in result.route
    text=Path(result.destination).read_text(encoding='utf-8')
    assert 'data_encoding' not in text and 'Hexadecimal' not in text


@pytest.mark.parametrize('fmt,text,expected',[
    ('html','<!DOCTYPE html><html><style>hidden style</style><body><h1>Hello</h1><p>World &amp; friends</p><script>danger()</script></body></html>','World & friends'),
    ('rtf',r'{\rtf1\ansi Hello\par World \b bold\b0}', 'World bold')])
def test_document_readable_text(engine,tmp_path,fmt,text,expected):
    source=tmp_path/f'input.{fmt}'; source.write_text(text,encoding='utf-8')
    result=engine.convert(source,tmp_path/'output.txt')
    value=Path(result.destination).read_text(encoding='utf-8')
    assert expected in value and 'danger()' not in value and '<html>' not in value and '\\rtf' not in value


def test_opendocument_extraction(engine,tmp_path):
    ns='xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"'
    odt=tmp_path/'input.odt'
    with zipfile.ZipFile(odt,'w') as archive:
        archive.writestr('mimetype','application/vnd.oasis.opendocument.text')
        archive.writestr('content.xml',f'<office:document-content {ns}><text:p>Readable ODT paragraph</text:p></office:document-content>')
    result=engine.convert(odt,tmp_path/'odt.txt')
    assert 'Readable ODT paragraph' in Path(result.destination).read_text(encoding='utf-8')
    ods=tmp_path/'input.ods'
    with zipfile.ZipFile(ods,'w') as archive:
        archive.writestr('mimetype','application/vnd.oasis.opendocument.spreadsheet')
        archive.writestr('content.xml',f'<office:document-content {ns}><table:table table:name="Numbers"><table:table-row><table:table-cell><text:p>Header</text:p></table:table-cell></table:table-row><table:table-row table:number-rows-repeated="3"><table:table-cell><text:p>42</text:p></table:table-cell></table:table-row></table:table></office:document-content>')
    result=engine.convert(ods,tmp_path/'ods.txt')
    assert 'Worksheet: Numbers' in Path(result.destination).read_text(encoding='utf-8')
    result=engine.convert(ods,tmp_path/'ods.csv')
    assert Path(result.destination).read_text(encoding='utf-8').count('42')==3


def test_pdf_text_boundaries(engine,sources,tmp_path):
    result=engine.convert(sources['pdf'],tmp_path/'pages.txt')
    text=Path(result.destination).read_text(encoding='utf-8')
    assert all(value in text for value in ['--- Page 1 ---','--- Page 2 ---','Page one','Page two'])


@pytest.mark.parametrize('mode',['brightness','rgb','scanline','binary'])
def test_image_audio_interpretations(engine,sources,tmp_path,mode):
    settings=Settings(mode=mode,audio_seconds=.2)
    result=engine.convert(sources['png'],tmp_path/f'{mode}.wav',settings)
    assert result.classification==('Binary interpretation' if mode=='binary' else 'Semantic conversion')
    assert ('bytes to PCM' in result.route) if mode=='binary' else mode in result.route
    result2=engine.convert(sources['png'],tmp_path/f'{mode}-again.wav',settings)
    assert Path(result.destination).read_bytes()==Path(result2.destination).read_bytes()


def test_multi_image_outputs_and_transaction(engine,sources,tmp_path):
    result=engine.convert(sources['pdf'],tmp_path/'pages.png')
    assert len(result.additional_paths)==1
    with Image.open(result.additional_paths[0]) as image: image.verify()
    original=Path(result.destination).read_bytes(); second=Path(result.additional_paths[0]).read_bytes()
    with pytest.raises(ConversionError): engine.convert(sources['pdf'],tmp_path/'pages.png')
    assert Path(result.destination).read_bytes()==original and Path(result.additional_paths[0]).read_bytes()==second
    limited=engine.convert(sources['pdf'],tmp_path/'single.png',Settings(multi_image=False))
    assert not limited.additional_paths and limited.warnings


def test_validation_failure_never_publishes_or_falls_back(engine,sources,tmp_path,monkeypatch):
    def broken(ctx,value): ctx.destination.write_bytes(b'not an image')
    monkeypatch.setattr('any2any.writers.image_writer',broken)
    target=tmp_path/'output.png'; target.write_bytes(b'keep existing')
    with pytest.raises(ValidationError): engine.convert(sources['image'],target,overwrite=True)
    assert target.read_bytes()==b'keep existing' and not list(tmp_path.glob('.any2any-*'))


def test_multi_image_publication_rolls_back_all_files(engine,sources,tmp_path,monkeypatch):
    import os
    primary=tmp_path/'group.png'; companion=tmp_path/'group.page-002.png'
    primary.write_bytes(b'old first'); companion.write_bytes(b'old second')
    replace_=os.replace
    def fail_second(source,target):
        if Path(source).name=='extra-000.png': raise OSError('Simulated second-page publication failure')
        return replace_(source,target)
    monkeypatch.setattr('any2any.engine.os.replace',fail_second)
    with pytest.raises(OSError): engine.convert(sources['pdf'],primary,overwrite=True)
    assert primary.read_bytes()==b'old first' and companion.read_bytes()==b'old second'
    assert not list(tmp_path.glob('.any2any-*'))


def test_companion_collision_prevents_partial_publication(engine,sources,tmp_path):
    companion=tmp_path/'group.page-002.png'; companion.write_bytes(b'keep companion')
    with pytest.raises(ConversionError): engine.convert(sources['pdf'],tmp_path/'group.png')
    assert not (tmp_path/'group.png').exists() and companion.read_bytes()==b'keep companion'


def test_invalid_xml_and_archive_outputs_are_reported(engine,sources,tmp_path,monkeypatch):
    def invalid(ctx,value): ctx.destination.write_bytes(b'broken')
    monkeypatch.setattr('any2any.writers.table_writer',invalid)
    with pytest.raises(ValidationError): engine.convert(sources['xlsx'],tmp_path/'invalid.xml')
    monkeypatch.setattr('any2any.writers.archive_writer',invalid)
    with pytest.raises(ValidationError): engine.convert(sources['text'],tmp_path/'invalid.gz')
    assert not (tmp_path/'invalid.xml').exists() and not (tmp_path/'invalid.gz').exists()


def test_transcription_requires_local_weights_and_forces_offline(tmp_path,monkeypatch):
    import sys,types,os
    from any2any.semantic import transcription_backend
    from any2any.transcribe_worker import main
    monkeypatch.setenv('ANY2ANY_WHISPER_MODEL','base')
    assert transcription_backend() is None
    folder=tmp_path/'existing-model'; folder.mkdir()
    observations={}
    class LocalModel:
        def __init__(self,path,**kwargs): observations.update(path=path,**kwargs)
        def transcribe(self,path,**kwargs): return iter([types.SimpleNamespace(text='Offline words')]),None
    monkeypatch.setitem(sys.modules,'faster_whisper',types.SimpleNamespace(WhisperModel=LocalModel))
    monkeypatch.setenv('HF_HUB_OFFLINE','0'); monkeypatch.setenv('TRANSFORMERS_OFFLINE','0')
    output=tmp_path/'transcript.txt'
    main(['faster_whisper',str(folder),'local.wav',str(output)])
    assert observations['local_files_only'] is True and observations['path']==str(folder)
    assert os.environ['HF_HUB_OFFLINE']=='1' and os.environ['TRANSFORMERS_OFFLINE']=='1'
    assert output.read_text(encoding='utf-8')=='Offline words'


def test_archive_tree_details(engine,sources,tmp_path):
    result=engine.convert(sources['archive'],tmp_path/'tree.txt',Settings(archive_text=True))
    text=Path(result.destination).read_text(encoding='utf-8')
    assert all(value in text for value in ['Entry count: 2','Compressed file size','Uncompressed entries total','Directory tree','notes/hello.txt','Archive text','unsafe path'])


def test_diagnostics_show_semantic_before_binary(engine,sources):
    info,selected=engine.preview(sources['wav'],'txt')
    candidates=engine.planner.diagnostics(info,'txt',Settings())
    assert candidates[0]['selected'] and candidates[0]['route']==selected.route
    assert candidates[0]['priority']==2
    assert any(candidate['priority']==4 for candidate in candidates)
    assert all(set(candidate)=={'route','classification','priority','score','cost','available','blocked_by','selected'} for candidate in candidates)


def test_batch_names_progress_and_failures(engine,sources,tmp_path):
    folder=tmp_path/'out'; folder.mkdir()
    batch=BatchConverter(engine); items=batch.plan([sources['png'],sources['image'],tmp_path/'missing.bin'],folder,'png')
    assert len({item.destination for item in items})==3
    events=[]; batch.convert(items,Settings(width=320,height=240),event=lambda i,item,p:events.append((i,item.status,p)))
    assert [item.status for item in items]==['complete','complete','failed']
    assert events[-1][2]==1 and all(0<=event[2]<=1 for event in events)
    assert not list(folder.glob('.any2any-*'))


def test_batch_cancellation(engine,sources,tmp_path):
    batch=BatchConverter(engine); items=batch.plan([sources['png'],sources['image']],tmp_path,'jpg',preserve_names=False)
    cancel=threading.Event()
    def event(i,item,overall):
        if item.status=='complete': cancel.set()
    batch.convert(items,cancel=cancel,event=event)
    assert [item.status for item in items]==['complete','cancelled']
    assert not Path(items[1].destination).exists()


def test_batch_mixed_interpretation_keeps_meaningful_routes(engine,sources,tmp_path):
    batch=BatchConverter(engine); items=batch.plan([sources['png'],sources['xlsx']],tmp_path,'wav',False)
    batch.convert(items,Settings(mode='rgb',audio_seconds=.2))
    assert all(item.status=='complete' and item.result.classification=='Semantic conversion' for item in items)
    assert 'rgb' in items[0].result.route and 'spreadsheet' in items[1].result.route
    assert any('uses Auto' in warning for warning in items[1].result.warnings)


def test_batch_never_overwrites_other_inputs(engine,sources,tmp_path):
    source=sources['pdf']; other=tmp_path/'document.page-002.png'; other.write_bytes(b'protected original')
    batch=BatchConverter(engine); items=batch.plan([source,other],tmp_path,'png')
    batch.convert(items,overwrite=True)
    assert items[0].status=='failed' and 'protected' in items[0].error
    assert other.read_bytes()==b'protected original' and not (tmp_path/'document.png').exists()


def test_grouped_capabilities():
    groups=capability_groups()
    assert {'Media backend','Image backend','Office backend','Document backend','Archive backend','Local recognition'}=={g['group'] for g in groups}
    assert all(item['functionality'] and item['status'] in {'Available','Missing'} for g in groups for item in g['items'])


def test_semantic_gui_batch_controls():
    from tkinterdnd2 import TkinterDnD
    from any2any.gui import App
    root=TkinterDnD.Tk(); root.withdraw()
    try:
        app=App(root); root.update()
        app.interpretation.set('RGB sonification')
        assert app.get_settings().mode=='rgb'
        app.cancel=threading.Event(); app.cancel_button.configure(state='normal'); app.cancel_button.invoke()
        assert app.cancel.is_set()  # The button must target the current worker's event.
        assert app.batch_tree.winfo_exists() and app.diagnostics.winfo_exists()
    finally: root.destroy()


def test_new_media_modes(engine,sources,tmp_path):
    settings=Settings(width=320,height=240,seconds_per_page=.5,fps=10,max_pages=4,audio_seconds=1,ocr=False)
    video=tmp_path/'video.mp4'; engine.convert(sources['pdf'],video,replace(settings,subtitles=True))
    text=engine.convert(video,tmp_path/'video.txt',settings)
    value=Path(text.destination).read_text(encoding='utf-8')
    assert 'Embedded subtitles' in value and 'Page one' in value and text.classification=='Semantic conversion'
    for mode in ['first','middle','last','even','scene','contact','animated']:
        result=engine.convert(video,tmp_path/f'{mode}.gif' if mode=='animated' else tmp_path/f'{mode}.png',replace(settings,mode=mode))
        assert result.classification=='Semantic conversion'
        assert mode in result.route or (mode=='even' and '/ even ' in result.route)
    stereo=engine.convert(sources['wav'],tmp_path/'stereo.png',replace(settings,mode='stereo'))
    assert 'stereo visualization' in stereo.route
    scrolling=engine.convert(sources['text'],tmp_path/'scroll.mp4',replace(settings,mode='scroll'))
    assert 'scroll' in scrolling.route and scrolling.classification=='Semantic conversion'
    table=engine.convert(sources['xlsx'],tmp_path/'rows.mp4',replace(settings,mode='table_rows'))
    assert '/ rows' in table.route and table.classification=='Semantic conversion'
    slides=engine.convert(sources['pptx'],tmp_path/'presentation.mp4',settings)
    assert 'presentation slides' in slides.route and slides.classification=='Semantic conversion'


def test_paginated_tables_cover_wide_sheets_and_text_heights(engine,sources,tmp_path):
    from openpyxl import Workbook
    path=tmp_path/'wide.xlsx'; workbook=Workbook(); workbook.active.append([f'Header {i}' for i in range(15)])
    for _ in range(20): workbook.active.append(['Wrapped words in a longer cell']*15)
    workbook.save(path)
    result=engine.convert(path,tmp_path/'wide.pdf',Settings(width=480,height=320,max_pages=100,font_size=14))
    with pymupdf.open(result.destination) as document: assert len(document)>3
    result=engine.convert(sources['text'],tmp_path/'auto.png',Settings(width=480,height=720,font_size=14))
    with Image.open(result.destination) as image: assert image.height<720
