"""Optional isolated worker. Only explicit local model paths are accepted."""
import json
import os
from pathlib import Path
import sys


def main(args=None):
    backend,model,audio,output=(args or sys.argv[1:])
    if not Path(model).exists(): raise ValueError('Local model path does not exist.')
    os.environ['HF_HUB_OFFLINE']='1'; os.environ['TRANSFORMERS_OFFLINE']='1'
    if backend=='faster_whisper':
        from faster_whisper import WhisperModel
        engine=WhisperModel(model,device='cpu',compute_type='int8',local_files_only=True)
        segments,_=engine.transcribe(audio,beam_size=1)
        text='\n'.join(segment.text for segment in segments)
    elif backend=='whisper':
        import whisper
        engine=whisper.load_model(model,device='cpu')
        text=engine.transcribe(audio,fp16=False)['text']
    else: raise ValueError('Unknown local transcription backend.')
    Path(output).write_text(text,encoding='utf-8')


if __name__=='__main__': main()
