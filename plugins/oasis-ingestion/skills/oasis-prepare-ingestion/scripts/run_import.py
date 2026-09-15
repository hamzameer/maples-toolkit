#!/usr/bin/env python3
"""Run the bundled importer with explicit target, review, and receipt boundaries."""
import argparse
import contextlib
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import runpy
import stat
import subprocess
import sys
from urllib.parse import urlsplit
from runtime_common import RUNTIME, verify_bundle, check_environment, python_in
from validate_manifest import validate


def read_config(path, windows_acl_verified=False):
    if path.is_symlink() or not path.is_file():
        raise ValueError('Connection config must be a regular, nonsymlink file')
    if os.name == 'posix':
        for candidate in (path, path.parent):
            st = candidate.stat()
            if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077:
                raise ValueError('Connection file and its directory must be owned by you and private (0600/0700)')
    elif not windows_acl_verified:
        raise ValueError('Verify owner-only Windows ACLs and supply --windows-acl-verified')
    values = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        name, sep, value = line.partition('=')
        name, value = name.strip(), value.strip()
        if not sep or name not in ('ELEPHANT_API_KEY', 'ELEPHANT_API_URL') or name in values:
            raise ValueError('Config needs exactly one entry for each required variable; no other assignments')
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError('Invalid quoting in connection config')
            value = value[1:-1]
        if not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('Blank or invalid connection field')
        values[name] = value  # Literal values only: no expansion or shell evaluation.
    if set(values) != {'ELEPHANT_API_KEY', 'ELEPHANT_API_URL'}:
        raise ValueError('Missing required connection field')
    url = values['ELEPHANT_API_URL']
    parsed = urlsplit(url)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.scheme not in ('https', 'http')):
        raise ValueError('Invalid Elephant base URL')
    if parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Use HTTPS or an approved loopback tunnel')
    return values


def restrict_requests(base_url):
    import requests
    original = requests.Session.request
    def origin(url):
        u = urlsplit(url)
        return u.scheme, u.hostname, u.port or (443 if u.scheme == 'https' else 80)
    allowed = origin(base_url)
    def bounded(self, method, url, **kwargs):
        if origin(url) != allowed:
            raise requests.RequestException('Cross-origin request blocked')
        self.trust_env = False  # No ambient proxy, netrc, or unrelated credential injection.
        kwargs['allow_redirects'] = False
        kwargs['verify'] = True
        result = original(self, method, url, **kwargs)
        if 300 <= result.status_code < 400:
            result.close()
            raise requests.RequestException('Redirect blocked')
        return result
    requests.Session.request = bounded


class RedactedLog(io.TextIOBase):
    def __init__(self, stream, secret):
        self.stream, self.secret, self.pending = stream, secret, ''
    def write(self, text):
        self.pending += text
        while '\n' in self.pending:
            line, self.pending = self.pending.split('\n', 1)
            self.stream.write(line.replace(self.secret, '[REDACTED]') + '\n')
        return len(text)
    def flush(self):
        if self.pending:
            self.stream.write(self.pending.replace(self.secret, '[REDACTED]'))
            self.pending = ''
        self.stream.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['dry-run', 'check-connection', 'ingest'])
    parser.add_argument('--venv', type=Path)
    parser.add_argument('--csv', type=Path)
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--receipt-dir', type=Path, required=True)
    parser.add_argument('--expected-url')
    parser.add_argument('--review-validation', type=Path)
    parser.add_argument('--confirm-ingest', action='store_true')
    parser.add_argument('--windows-acl-verified', action='store_true')
    args = parser.parse_args()
    try:
        bundle_fingerprint = verify_bundle()
        if args.action != 'dry-run':
            if not args.venv:
                raise ValueError('Select the prepared environment with --venv')
            check_environment(args.venv)
            if Path(sys.prefix).resolve() != args.venv.resolve():
                # -I prevents current-directory/PYTHONPATH package injection.
                code = 'import sys,runpy;sys.path.insert(0,sys.argv.pop(1));sys.argv.pop(0);runpy.run_path(sys.argv[0],run_name="__main__")'
                command = [str(python_in(args.venv)), '-I', '-c', code,
                           str(Path(__file__).resolve().parent), str(Path(__file__).resolve())] + sys.argv[1:]
                raise SystemExit(subprocess.call(command))
        values = None
        if args.action != 'dry-run':
            if not args.config or not args.expected_url:
                raise ValueError('Connection requires --config and the exact reviewed --expected-url')
            values = read_config(args.config, args.windows_acl_verified)
            if values['ELEPHANT_API_URL'] != args.expected_url:
                raise ValueError('Configured endpoint does not match the reviewed target')
        report = None
        if args.action != 'check-connection':
            if not args.csv or not args.data_dir:
                raise ValueError('Select --csv and --data-dir')
            report = validate(args.csv, args.data_dir)
            if report['status'] != 'PASS':
                raise ValueError('Manifest validation failed; run the validator for protected details')
        if args.action == 'ingest':
            if not args.confirm_ingest or not args.review_validation:
                raise ValueError('Ingestion requires explicit confirmation and the reviewed validation receipt')
            reviewed = json.loads(args.review_validation.read_text())
            if reviewed != report:
                raise ValueError('Manifest or input files differ from the reviewed validation receipt')
        os.umask(0o077)
        args.receipt_dir.mkdir(parents=False, exist_ok=False)
        if report is not None:
            (args.receipt_dir / 'validation.json').write_text(json.dumps(report, indent=2)+'\n')
        started = datetime.now(timezone.utc).isoformat()
        status = 0
        with (args.receipt_dir / 'import.log').open('x', encoding='utf-8') as stream:
            log = RedactedLog(stream, values['ELEPHANT_API_KEY'] if values else '\x00')
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                try:
                    if values:
                        restrict_requests(values['ELEPHANT_API_URL'])
                    if args.action == 'check-connection':
                        from elephant import ElephantClient
                        client = ElephantClient(api_key=values['ELEPHANT_API_KEY'], base_url=values['ELEPHANT_API_URL'])
                        client.get_health()
                        client.get_file_types()
                        print('Health and file-types reads succeeded. Write role and namespace isolation are not established.')
                    else:
                        for k in list(os.environ):
                            if k.startswith(('ELEPHANT_', 'OASIS_')):
                                os.environ.pop(k)
                        if values:
                            os.environ.update(values)
                        sys.argv = [str(RUNTIME / 'load-data.py'), '--csv', str(args.csv.resolve()), '--data-dir', str(args.data_dir.resolve())]
                        if args.action == 'dry-run':
                            sys.argv.append('--dry-run')
                        runpy.run_path(str(RUNTIME / 'load-data.py'), run_name='__main__')
                except SystemExit as exc:
                    status = exc.code if isinstance(exc.code, int) else 1
                    if status:
                        print('Importer exited unsuccessfully; inspect preceding protected output.')
                except Exception:
                    status = 1
                    print('Operation failed; raw exception withheld to avoid credential disclosure.')
                finally:
                    log.flush()
                    os.environ.pop('ELEPHANT_API_KEY', None)
        receipt = {'action':args.action, 'exit_code':status,
                   'started_at':started, 'finished_at':datetime.now(timezone.utc).isoformat(),
                   'bundle_integrity_sha256':bundle_fingerprint,
                   'manifest_sha256':report['manifest_sha256'] if report else None,
                   'source':json.loads((RUNTIME/'provenance.json').read_text())['commit'],
                   'target':values['ELEPHANT_API_URL'] if values else None,
                   'status':'COMMAND_SUCCEEDED_RECONCILIATION_REQUIRED' if args.action=='ingest' and status==0 else 'PASS' if status==0 else 'FAIL',
                   'limits':'No automatic post-import server reconciliation or write-role verification. Review protected receipts before declaring ingestion complete.'}
        (args.receipt_dir / 'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
        print(json.dumps({'action':args.action, 'status':receipt['status'], 'exit_code':status}))
        raise SystemExit(status)
    except (OSError, ValueError, KeyError):
        parser.exit(1, 'Preflight failed: verify bundle/environment, private config, exact target, reviewed inputs, confirmation, and fresh receipt path. No import started.\n')


if __name__ == '__main__':
    main()
