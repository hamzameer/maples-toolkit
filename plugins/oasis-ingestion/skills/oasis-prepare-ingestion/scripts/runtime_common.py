"""Integrity and environment helpers for the private importer bundle."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'runtime'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def verify_bundle():
    inventory = json.loads((RUNTIME / 'integrity.json').read_text())
    for name, expected in inventory.items():
        path = ROOT / name
        if path.is_symlink() or not path.is_file() or digest(path) != expected:
            raise ValueError('Bundled runtime integrity check failed')
    return digest(RUNTIME / 'integrity.json')


def python_in(venv):
    return venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def environment_snapshot(venv):
    code = '''import importlib.metadata as m, json, hashlib
from pathlib import Path
import elephant, requests, pydantic
root=Path(elephant.__file__).parent
print(json.dumps({'packages': {d.metadata['Name'].lower().replace('_','-'):d.version for d in m.distributions()}, 'sdk_files': {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and p.suffix in ('.py', '.typed')}}))'''
    result = subprocess.run([str(python_in(venv)), '-I', '-c', code], capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Importer environment cannot import Elephant SDK and dependencies; run setup')
    return json.loads(result.stdout)


def check_environment(venv):
    fingerprint = verify_bundle()
    receipt = json.loads((venv / 'oasis-importer-setup.json').read_text())
    if receipt['bundle'] != fingerprint or receipt['environment'] != environment_snapshot(venv):
        raise ValueError('Importer environment changed or belongs to a different bundle; create a fresh environment')
    return fingerprint
