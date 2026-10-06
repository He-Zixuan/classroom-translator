# Copyright (c) 2026 He-Zixuan
# SPDX-License-Identifier: LicenseRef-Classroom-Personal-NonCommercial-1.0
"""Check a source publication without printing secret values."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.git', '.venv', '__pycache__', '.pytest_cache', 'build', 'dist', '*.egg-info'}
PRIVATE_DIRS = {'history', 'runtime', 'models', 'recordings', 'exports'}
FORBIDDEN_EXTENSIONS = {'.wav', '.mp3', '.m4a', '.mp4', '.flac', '.ogg', '.db', '.sqlite', '.sqlite3', '.key', '.pem', '.log', '.pt', '.gguf', '.safetensors', '.bin'}
SECRETS = [r'gh[pousr]_[A-Za-z0-9]{30,}', r'github_pat_[A-Za-z0-9_]{30,}', r'sk-[A-Za-z0-9_-]{30,}', r'hf_[A-Za-z0-9]{30,}', r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', r'[A-Za-z]:[/\\]Users[/\\][^\s"\'<>]+']


def main():
    errors = []
    count = 0
    for path in ROOT.rglob('*'):
        if not path.is_file(): continue
        relative = path.relative_to(ROOT)
        if any(part in SKIP or part.endswith('.egg-info') for part in relative.parts): continue
        count += 1
        if any(part in PRIVATE_DIRS for part in relative.parts[:-1]) or path.suffix.lower() in FORBIDDEN_EXTENSIONS or path.name.startswith('.env'):
            errors.append(f'Private/runtime artifact: {relative}')
        if path.stat().st_size >= 95 * 1024 * 1024:
            errors.append(f'Oversized file: {relative}')
        try: content = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            allowed = str(relative).replace('\\', '/').startswith(('vendor/whisperlivekit/whisperlivekit/silero_vad_models/', 'vendor/whisperlivekit/whisperlivekit/whisper/assets/'))
            if not allowed: errors.append(f'Unreviewed binary: {relative}')
            continue
        for pattern in SECRETS:
            if re.search(pattern, content):
                errors.append(f'Potential credential or private path: {relative}')
                break
    for required in ['README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'vendor/whisperlivekit/LICENSE', 'scripts/model-checksums.json']:
        if not (ROOT / required).is_file(): errors.append(f'Missing required file: {required}')
    if errors:
        print('\n'.join(errors)); return 1
    print(f'Publication checks passed: {count} files; no personal data artifacts, credentials or user paths detected.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
