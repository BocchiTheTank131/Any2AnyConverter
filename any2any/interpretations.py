"""User-facing interpretations and their reusable settings profiles."""
from dataclasses import replace

MODES = {
    'auto': ('Auto', {}), 'binary': ('Raw bytes / binary interpretation', {}),
    'brightness': ('Image sonification', {'image_audio': 'brightness'}),
    'rgb': ('RGB sonification', {'image_audio': 'rgb'}),
    'scanline': ('Scanline sonification', {'image_audio': 'scanline'}),
    'image_text': ('Image metadata / OCR / ASCII art', {}),
    'media_text': ('Media subtitles / metadata / analysis', {}),
    'waveform': ('Waveform', {'audio_view': 'waveform'}),
    'spectrogram': ('Spectrogram', {'audio_view': 'spectrogram'}),
    'spectrum': ('Frequency spectrum', {'audio_view': 'spectrum'}),
    'stereo': ('Stereo visualization', {'audio_view': 'stereo'}),
    'first': ('First frame', {'video_view': 'first'}),
    'middle': ('Middle frame', {'video_view': 'middle'}),
    'last': ('Last frame', {'video_view': 'last'}),
    'timed': ('Timed frames', {'video_view': 'sampling', 'frame_mode': 'seconds'}),
    'frames': ('Every N frames', {'video_view': 'sampling', 'frame_mode': 'frames'}),
    'every': ('Every frame', {'video_view': 'sampling', 'frame_mode': 'every'}),
    'even': ('Evenly distributed samples', {'video_view': 'sampling', 'frame_mode': 'even'}),
    'scene': ('Scene changes', {'video_view': 'sampling', 'frame_mode': 'scene'}),
    'contact': ('Contact sheet', {'video_view': 'contact', 'frame_mode': 'even'}),
    'animated': ('Animated frames', {'video_view': 'animated', 'frame_mode': 'seconds'}),
    'scroll': ('Scrolling text', {'text_video': 'scroll'}),
    'slides': ('Text pages / slides', {'text_video': 'slides'}),
    'table_pitch': ('Table pitch mapping (rows as time)', {'table_audio': 'pitch'}),
    'table_amplitude': ('Table amplitude mapping (columns as tones)', {'table_audio': 'amplitude'}),
    'table_rows': ('Progressive table rows', {'table_video': 'rows'}),
    'table_sheets': ('Worksheet slides', {'table_video': 'sheets'}),
}


def effective(settings):
    return replace(settings, **MODES[settings.mode][1])


def choices(info, extension):
    from .detect import AUDIO_EXTS, IMAGE_EXTS, VIDEO_EXTS
    keys = ['auto']
    if info.category == 'image':
        if extension in AUDIO_EXTS: keys += ['brightness', 'rgb', 'scanline']
        else: keys += ['image_text']
    if info.category in {'audio', 'video'}:
        keys += ['media_text']
    if info.category == 'audio' and extension in IMAGE_EXTS | VIDEO_EXTS | {'pdf'}:
        keys += ['waveform', 'spectrogram', 'spectrum', 'stereo']
    if info.category == 'video' and extension in IMAGE_EXTS | {'pdf'}:
        keys += ['first', 'middle', 'last', 'timed', 'frames', 'every', 'even', 'scene', 'contact']
        if extension in {'gif', 'webp', 'tif', 'tiff'}: keys += ['animated']
    if info.category in {'text', 'data', 'document', 'presentation'} and extension in VIDEO_EXTS: keys += ['slides', 'scroll']
    if info.category == 'table' or info.format in {'csv','tsv','json','xml'}:
        if extension in AUDIO_EXTS: keys += ['table_pitch', 'table_amplitude']
        if extension in VIDEO_EXTS: keys += ['table_sheets', 'table_rows']
    return keys + ['binary']


def permits(mode, backend):
    """Restrict the first operation when the user explicitly chooses an interpretation."""
    if mode == 'auto': return True
    if backend.target=='bytes': return True
    if mode == 'binary': return backend.target == 'bytes'
    if mode == 'image_text': return backend.target == 'text'
    if mode == 'media_text': return backend.target in {'audio_source', 'video_source'}
    if mode in {'brightness','rgb','scanline'}: return backend.target=='pages'
    if mode in {'slides','scroll'}: return backend.target=='text'
    if mode.startswith('table_'): return backend.target=='table'
    # Other explicit choices must avoid identity/remux/Office shortcuts.
    return backend.target in {'pages', 'audio_source', 'video_source', 'table', 'text'}
