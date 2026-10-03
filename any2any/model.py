from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import threading
from typing import Callable


class ConversionError(Exception):
    pass


class Cancelled(ConversionError):
    pass


@dataclass
class FormatInfo:
    format: str
    category: str
    mime: str
    description: str
    evidence: str
    details: dict = field(default_factory=dict)


@dataclass
class Settings:
    mode: str = 'auto'
    frame_mode: str = 'seconds'
    frame_interval: float = 5.0
    max_pages: int = 50
    timestamps: bool = True
    seconds_per_page: float = 2.0
    width: int = 1280
    height: int = 720
    fps: int = 24
    transition: str = 'cut'
    subtitles: bool = False
    audio_seconds: float = 8.0
    sample_rate: int = 22050
    audio_view: str = 'waveform'
    table_audio: str = 'pitch'
    rgb_audio: bool = False
    archive_text: bool = False
    prefer_tts: bool = True
    image_audio: str = 'brightness'
    video_view: str = 'sampling'
    text_video: str = 'slides'
    table_video: str = 'sheets'
    font_size: int = 20
    background: str = '#fafafa'
    auto_height: bool = True
    multi_image: bool = True
    transcribe: bool = False
    ocr: bool = True
    scene_threshold: float = .3
    scroll_speed: int = 40
    max_read_bytes: int = 16 * 1024 * 1024
    max_cells: int = 20000
    max_archive_entries: int = 10000
    max_archive_bytes: int = 32 * 1024 * 1024
    tool_timeout: int = 600

    def validate(self):
        bounds = {'max_pages': (1, 500), 'frame_interval': (.01, 100000),
                  'seconds_per_page': (.1, 60), 'width': (64, 3840),
                  'height': (64, 2160), 'fps': (1, 60), 'audio_seconds': (.1, 120),
                  'sample_rate': (8000, 48000), 'max_read_bytes': (1024, 256*1024*1024),
                  'max_cells': (1, 100000), 'max_archive_entries': (1, 100000),
                  'max_archive_bytes': (1024, 256*1024*1024), 'tool_timeout': (1, 3600),
                  'font_size': (8, 96), 'scene_threshold': (.01, 1), 'scroll_speed': (10,500)}
        for key, (lo, hi) in bounds.items():
            if not lo <= getattr(self, key) <= hi:
                raise ConversionError(f'{key} must be between {lo} and {hi}.')
        for key in ('max_pages', 'width', 'height', 'fps', 'sample_rate', 'max_read_bytes',
                    'max_cells', 'max_archive_entries', 'max_archive_bytes', 'tool_timeout', 'font_size', 'scroll_speed'):
            if not isinstance(getattr(self, key), int):
                raise ConversionError(f'{key} must be an integer.')
        from .interpretations import MODES
        choices = {'mode': tuple(MODES), 'frame_mode': ('seconds', 'frames', 'every', 'even', 'scene'),
                   'transition': ('cut', 'fade'), 'audio_view': ('waveform', 'spectrogram', 'spectrum', 'stereo'),
                   'table_audio': ('pitch', 'amplitude'), 'image_audio': ('brightness', 'rgb', 'scanline'),
                   'video_view': ('sampling', 'first', 'middle', 'last', 'contact', 'animated'),
                   'text_video': ('slides', 'scroll'), 'table_video': ('sheets', 'rows')}
        for key, allowed in choices.items():
            if getattr(self, key) not in allowed:
                raise ConversionError(f'Invalid {key}.')
        if not __import__('re').fullmatch(r'#[0-9a-fA-F]{6}', self.background):
            raise ConversionError('Background must be a six-digit hexadecimal color, for example #fafafa.')


@dataclass
class ImageData:
    pages: list
    captions: list[str] = field(default_factory=list)
    durations: list[int] = field(default_factory=list)
    loop: int = 0


@dataclass
class TextData:
    text: str


@dataclass
class TableData:
    sheets: list[tuple[str, list[list]]]


@dataclass
class AudioData:
    path: Path


@dataclass
class BinaryData:
    data: bytes
    metadata: dict


@dataclass
class VideoData:
    path: Path


@dataclass
class DocumentPages(ImageData):
    pass


@dataclass
class ImageSequence(ImageData):
    """A bounded sequence of frames with captions and optional timing."""
    motion: str = ''


@dataclass
class SubtitleData:
    text: str
    codec: str = 'srt'


@dataclass
class MetadataData:
    title: str
    fields: dict


@dataclass
class ArchiveTree:
    name: str
    format: str
    compressed_size: int
    entries: list[dict]


@dataclass
class Context:
    source: Path
    destination: Path
    info: FormatInfo
    settings: Settings
    temporary: Path
    cancel: threading.Event
    log: Callable[[str], None]
    progress: Callable[[float], None]
    warnings: list[str] = field(default_factory=list)
    additional_outputs: list[Path] = field(default_factory=list)
    protected_sources: list[Path] = field(default_factory=list)

    def check(self):
        if self.cancel.is_set():
            raise Cancelled('Conversion cancelled. Original and existing output are unchanged.')

    def warn(self, message):
        if message not in self.warnings:
            self.warnings.append(message)
            self.log('Warning: ' + message)

    def read(self):
        self.check()
        with self.source.open('rb') as stream:
            data = stream.read(self.settings.max_read_bytes)
        if self.source.stat().st_size > len(data):
            self.warn(f'Interpretation uses the first {len(data):,} bytes; source is larger than the read limit.')
        return data
