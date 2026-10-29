"""Validate release ZIP contents against the checkout and smoke-test its card."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


def validate_release(root, archive, expected_version=None):
    source = root / 'custom_components/spot_trace_history'
    manifest = json.loads((source / 'manifest.json').read_text())
    version = expected_version or manifest['version']
    if manifest['version'] != version:
        raise ValueError('Source manifest does not match the requested release version')
    expected = {str(path.relative_to(source).as_posix()): path for path in source.rglob('*')
                if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc'}
    with zipfile.ZipFile(archive) as package:
        files = [info.filename for info in package.infolist() if not info.is_dir()]
        if len(files) != len(set(files)):
            raise ValueError('Release ZIP contains duplicate file entries')
        missing, extra = set(expected) - set(files), set(files) - set(expected)
        if missing or extra:
            raise ValueError(f'Release file list differs from source: missing={sorted(missing)}, extra={sorted(extra)}')
        if package.testzip() is not None:
            raise ValueError('Release ZIP failed its CRC integrity check')
        packaged_manifest = json.loads(package.read('manifest.json'))
        if packaged_manifest.get('domain') != 'spot_trace_history' or packaged_manifest.get('version') != version:
            raise ValueError('Packaged manifest has an incorrect domain or release version')
        for name, path in expected.items():
            if package.read(name) != path.read_bytes():
                raise ValueError(f'Packaged file differs from source: {name}')
        card = package.read('www/spot-trace-history-card.js')
    check = subprocess.run(['node', str(Path(__file__).with_name('check_packaged_card.cjs'))],
                           input=card, capture_output=True)
    if check.returncode:
        raise ValueError('Packaged card failed its runtime smoke test:\n' + check.stderr.decode(errors='replace'))
    return {'version':version, 'files':len(expected), 'card_sha256':hashlib.sha256(card).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', nargs='?', type=Path, help='Defaults to the current version ZIP in dist/')
    parser.add_argument('--version', help='Expected release version, e.g. 0.5.12')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        version = args.version or json.loads((root/'custom_components/spot_trace_history/manifest.json').read_text())['version']
        archive = args.archive or root/'dist'/f'spot_trace_history-{version}.zip'
        result = validate_release(root, archive, version)
        print(f"Release ZIP OK: {archive.name}, version {result['version']}, {result['files']} files")
        print(f"Bundled card SHA-256: {result['card_sha256']}")
        print('Packaged card registration and playback smoke test passed')
    except (ValueError, KeyError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(1, f'Release validation failed: {exc}\n')
