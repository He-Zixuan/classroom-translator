# Copyright (c) 2026 He-Zixuan
# SPDX-License-Identifier: LicenseRef-Classroom-Personal-NonCommercial-1.0
"""Prepare vendor models and Vulkan runtime; never read classroom history."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WHISPER_REVISION = '41f01f3fe87f28c78e2fbf8b568835947dd65ed9'
HY_REVISION = '265b2e615a7dc9b06c435dc878829ad99a512ba2'
LLAMA_TAG = 'b11146'
LLAMA_FILE = f'llama-{LLAMA_TAG}-bin-win-vulkan-x64.zip'
LLAMA_SHA256 = '55a378aa095b466979d85075234f66d7655c7a7483222af0c006c0e55b4d7bd6'


def checksum(path):
    sha = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()


def download(url, path, expected):
    if path.is_file() and checksum(path) == expected:
        print(f'Already verified: {path.name}', flush=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + '.partial')
    print(f'Downloading {path.name}…', flush=True)
    with urllib.request.urlopen(url, timeout=120) as source, partial.open('wb') as out:
        shutil.copyfileobj(source, out, length=8 * 1024 * 1024)
    if checksum(partial) != expected:
        raise RuntimeError(f'Checksum mismatch: {path.name}; incomplete file retained for diagnosis')
    partial.replace(path)


def convert_whisper(source, target):
    import torch
    from transformers import WhisperConfig, WhisperForConditionalGeneration
    from transformers import WhisperTokenizerFast, GenerationConfig, WhisperFeatureExtractor
    from ctranslate2.converters import Converter
    from ctranslate2.converters.transformers import WhisperLoader
    from whisperlivekit.whisper import _convert_hf_state_dict

    metadata = 'openai/whisper-large-v3-turbo'
    config = WhisperConfig.from_pretrained(metadata, revision=WHISPER_REVISION)
    tokenizer = WhisperTokenizerFast.from_pretrained(metadata, revision=WHISPER_REVISION)
    generation = GenerationConfig.from_pretrained(metadata, revision=WHISPER_REVISION)
    features = WhisperFeatureExtractor.from_pretrained(metadata, revision=WHISPER_REVISION)
    checkpoint = torch.load(source, map_location='cpu', weights_only=True)
    original = checkpoint['model_state_dict']
    with torch.device('meta'):
        model = WhisperForConditionalGeneration(config)
    mapped = {}
    for hf_name, empty in model.state_dict().items():
        if hf_name == 'proj_out.weight':
            native = 'decoder.token_embedding.weight'
        else:
            keys = _convert_hf_state_dict({hf_name: empty})
            if len(keys) != 1:
                raise ValueError(f'Unexpected mapping: {hf_name}')
            native = next(iter(keys))
        if native not in original or empty.shape != original[native].shape:
            raise ValueError(f'Checkpoint shape or key mismatch: {hf_name}')
        mapped[hf_name] = original[native]
    model.load_state_dict(mapped, strict=True, assign=True)
    model.generation_config = generation
    model.config._name_or_path = metadata

    class LocalConverter(Converter):
        def _load(self):
            return WhisperLoader()(model, tokenizer)

    # Stage separately. An interrupted conversion must not appear ready.
    stage = target.with_name(target.name + '.preparing')
    if stage.exists():
        raise RuntimeError(f'Previous incomplete conversion found at {stage.name}; inspect it before retrying')
    LocalConverter().convert(str(stage), quantization='float16')
    tokenizer.save_pretrained(stage)
    features.save_pretrained(stage)
    (stage / 'conversion-provenance.json').write_text(json.dumps({
        'source': 'OpenAI official large-v3-turbo checkpoint',
        'source_sha256': checksum(source), 'metadata_repository': metadata,
        'metadata_revision': WHISPER_REVISION, 'quantization': 'float16',
        'tensor_mapping': 'all keys and shapes validated; weights assigned without retraining',
    }, indent=2) + '\n', encoding='utf-8')
    stage.rename(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--accept-model-licenses', action='store_true')
    parser.add_argument('--plan', action='store_true', help='Show pinned sources without downloading')
    args = parser.parse_args()
    expected = {item['filename']: item['sha256'] for item in json.loads((ROOT / 'scripts/model-checksums.json').read_text())}
    sources = [
        ('large-v3-turbo.pt', f'https://openaipublic.azureedge.net/main/whisper/models/{expected["large-v3-turbo.pt"]}/large-v3-turbo.pt'),
        ('HY-MT1.5-1.8B-Q4_K_M.gguf', f'https://huggingface.co/tencent/HY-MT1.5-1.8B-GGUF/resolve/{HY_REVISION}/HY-MT1.5-1.8B-Q4_K_M.gguf'),
    ]
    if args.plan:
        for name, url in sources: print(f'{name}: {url}')
        print(f'llama.cpp: {LLAMA_TAG}; SHA-256: {LLAMA_SHA256}')
        return
    if not args.accept_model_licenses:
        parser.error('Read THIRD_PARTY_NOTICES.md and licenses/Tencent-HY-Community.txt; then pass --accept-model-licenses if you accept the applicable terms')
    if sys.platform != 'win32':
        parser.error('The provided runtime preparation currently supports Windows x64 only')
    sys.path.insert(0, str(ROOT / 'vendor/whisperlivekit'))
    for name, url in sources:
        download(url, ROOT / 'models' / name, expected[name])
    converted = ROOT / 'models/large-v3-turbo-ct2'
    if converted.exists():
        proof = converted / 'conversion-provenance.json'
        info = json.loads(proof.read_text()) if proof.is_file() else {}
        if info.get('source_sha256') != expected['large-v3-turbo.pt'] or not (converted / 'model.bin').is_file():
            raise RuntimeError('Existing CT2 model has no matching conversion provenance; inspect it before retrying')
        print('Existing CT2 conversion verified', flush=True)
    else:
        print('Converting English checkpoint to float16 CT2…', flush=True)
        convert_whisper(ROOT / 'models/large-v3-turbo.pt', converted)
    archive = ROOT / 'runtime/downloads' / LLAMA_FILE
    download(f'https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}/{LLAMA_FILE}', archive, LLAMA_SHA256)
    destination = (ROOT / 'runtime/llama').resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            if not (destination / item.filename).resolve().is_relative_to(destination):
                raise ValueError('Unsafe path in runtime archive')
        bundle.extractall(destination)
    if not list(destination.rglob('llama-server.exe')):
        raise RuntimeError('Runtime archive contains no llama-server.exe')
    print('Models and runtime ready. Start with 开始课堂翻译.cmd', flush=True)


if __name__ == '__main__':
    main()
