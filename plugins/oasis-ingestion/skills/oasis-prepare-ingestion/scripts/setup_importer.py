#!/usr/bin/env python3
"""Create a private importer environment; no Elephant connection is made."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv
from runtime_common import RUNTIME, verify_bundle, python_in, environment_snapshot, check_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--venv', required=True, type=Path)
    parser.add_argument('--installer', choices=['auto', 'pip', 'uv'], default='auto')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    dest = args.venv.expanduser().absolute()
    try:
        if sys.version_info < (3, 10):
            raise ValueError('Python 3.10 or newer is required')
        fingerprint = verify_bundle()
        if args.check:
            check_environment(dest)
            print('PASS: bundled runtime, installed SDK, and dependency environment verified; no server calls')
            return
        if dest.exists() or dest.is_symlink():
            raise ValueError('Environment destination already exists; use --check or select a fresh directory')
        installer = args.installer
        if installer == 'auto':
            installer = 'uv' if shutil.which('uv') else 'pip'
        os.umask(0o077)
        if installer == 'uv':
            uv = shutil.which('uv')
            if not uv:
                raise ValueError('uv is not installed; select pip with a Python that supports venv/ensurepip')
            subprocess.run([uv, 'venv', '--python', sys.executable, str(dest)], check=True)
            pip = [uv, 'pip']
            target = ['--python', str(python_in(dest))]
        else:
            try:
                import ensurepip  # noqa: F401
            except ImportError:
                raise ValueError('This Python lacks ensurepip. Use an approved Python with venv support, or install/use uv. No system changes were made.')
            venv.EnvBuilder(with_pip=True).create(dest)
            pip = [str(python_in(dest)), '-I', '-m', 'pip']
            target = []
        subprocess.run(pip + ['install'] + target + ['--require-hashes', '--only-binary=:all:', '-r', str(RUNTIME / 'requirements.lock')], check=True)
        subprocess.run(pip + ['install'] + target + ['--no-deps', str(RUNTIME / 'elephant_sdk-3.1.1-py3-none-any.whl')], check=True)
        subprocess.run(pip + ['check'] + target, check=True)
        snapshot = environment_snapshot(dest)
        import zipfile, hashlib
        with zipfile.ZipFile(RUNTIME / 'elephant_sdk-3.1.1-py3-none-any.whl') as wheel:
            expected = {n[len('elephant/'):]:hashlib.sha256(wheel.read(n)).hexdigest() for n in wheel.namelist() if n.startswith('elephant/') and n.endswith(('.py', '.typed'))}
        if snapshot['sdk_files'] != expected:
            raise ValueError('Installed SDK differs from the bundled wheel')
        (dest / 'oasis-importer-setup.json').write_text(json.dumps({'bundle':fingerprint, 'environment':snapshot}, indent=2)+'\n')
        print('PASS: importer environment created; no server calls. Use --check to verify it later.')
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'Setup failed: {exc}\nPartial environments are preserved; fix the cause and choose a fresh destination.\n')


if __name__ == '__main__':
    main()
