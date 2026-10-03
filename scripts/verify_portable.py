"""Test only the copied single executable outside the project checkout."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import tempfile

project = Path(__file__).resolve().parent.parent
original = project / 'dist' / 'Any2Any.exe'
with original.open('rb') as stream:
    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
with tempfile.TemporaryDirectory(prefix='Any2Any Portable Ω ') as directory:
    portable = Path(directory)
    executable = portable / 'Any2Any.exe'
    shutil.copy2(original, executable)
    launch_folder = portable / 'unrelated working folder'
    launch_folder.mkdir()
    for mode in ('system', 'bundled'):
        environment = os.environ.copy()
        if mode == 'bundled':
            environment['PATH'] = ''
        output = portable / ('results ' + mode)
        subprocess.run([str(executable), '--smoke-test', str(output)],
                       cwd=launch_folder, env=environment, timeout=120, check=True)
        report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
        assert report['success'], report.get('error')
        assert len(report['results']) == 13
        assert len(report['batch']) == 2
        assert all(item['status'] == 'complete' for item in report['batch'])
        report['portable_test'] = {
            'single_executable_only': True,
            'outside_project': True,
            'different_working_directory': True,
            'spaces_and_unicode_path': True,
            'empty_path': mode == 'bundled',
            'sha256': digest,
            'executable_size': original.stat().st_size,
        }
        (project / 'verification' / ('standalone-' + mode + '.json')).write_text(
            json.dumps(report, indent=2), encoding='utf-8')
        print(f'{mode}: GUI, 13 conversions and two-file batch passed', flush=True)
print(f'SHA256: {digest}', flush=True)
