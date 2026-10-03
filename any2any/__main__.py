import argparse
import json
from dataclasses import asdict
from .engine import ConversionEngine
from .model import Settings,ConversionError
from .tools import capabilities


def main():
    import sys
    for stream in (sys.stdout,sys.stderr):
        if stream and hasattr(stream,'reconfigure'): stream.reconfigure(encoding='utf-8',errors='replace')
    parser=argparse.ArgumentParser(description='Any2Any desktop converter and CLI')
    parser.add_argument('input',nargs='?'); parser.add_argument('output',nargs='?')
    parser.add_argument('--binary',action='store_true'); parser.add_argument('--overwrite',action='store_true')
    parser.add_argument('--preview',action='store_true'); parser.add_argument('--capabilities',action='store_true')
    parser.add_argument('--settings',help='Path to a JSON object containing Settings fields')
    parser.add_argument('--diagnostics',action='store_true',help='List considered conversion routes')
    parser.add_argument('--batch',nargs='+',help='Input files for batch conversion')
    parser.add_argument('--output-dir',help='Batch destination directory')
    parser.add_argument('--extension',default='png',help='Batch output extension')
    parser.add_argument('--numbered',action='store_true',help='Use numbered batch output names')
    args=parser.parse_args()
    if args.capabilities: print(json.dumps(capabilities(),indent=2)); return
    if not args.input and not args.batch:
        from .gui import main as gui
        gui(); return
    if not args.batch and not args.output: parser.error('output path required for CLI conversion')
    settings=Settings(**json.loads(open(args.settings,encoding='utf-8').read())) if args.settings else Settings()
    if args.binary: settings.mode='binary'
    engine=ConversionEngine()
    try:
        if args.batch:
            from .batch import BatchConverter
            if not args.output_dir: parser.error('--output-dir required with --batch')
            batch=BatchConverter(engine); items=batch.plan(args.batch,args.output_dir,args.extension,not args.numbered)
            if not args.preview: batch.convert(items,settings,overwrite=args.overwrite,log=lambda msg:print(msg,file=sys.stderr))
            print(json.dumps([asdict(item) for item in items],indent=2))
            if any(item.status in {'failed','cancelled'} for item in items): parser.exit(1)
        elif args.preview or args.diagnostics:
            from pathlib import Path
            info,plan=engine.preview(args.input,Path(args.output).suffix,settings)
            report={'detected':asdict(info),'classification':plan.label,'route':plan.route}
            if args.diagnostics:
                from .interpretations import effective
                report['candidates']=engine.planner.diagnostics(info,Path(args.output).suffix.lstrip('.'),effective(settings))
            print(json.dumps(report,indent=2))
        else:
            import sys
            result=engine.convert(args.input,args.output,settings,overwrite=args.overwrite,log=lambda msg:print(msg,file=sys.stderr))
            print(json.dumps(asdict(result),indent=2))
    except ConversionError as error:
        parser.exit(1,str(error)+'\n')


if __name__=='__main__': main()
