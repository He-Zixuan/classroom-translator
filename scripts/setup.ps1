param([string]$Python = 'py', [switch]$Plan)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskVenvPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
if ($Plan) {
    Write-Host 'Create Python 3.12 virtual environment; install CUDA 12.8 PyTorch, pinned requirements, and the local WhisperLiveKit snapshot.'
    Write-Host 'Models are prepared separately after accepting their licenses. No model or classroom data is bundled.'
    exit 0
}
Push-Location $taskRoot
try {
    if (-not (Test-Path -LiteralPath $taskVenvPython)) {
        if ($Python -eq 'py') { & $Python -3.12 -m venv .venv }
        else { & $Python -m venv .venv }
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required. Install it or pass -Python with the path to your Python 3.12 executable.' }
    }
    & $taskVenvPython -c "import sys; assert sys.version_info[:2] == (3,12), 'Use Python 3.12 for this tested setup'"
    if ($LASTEXITCODE -ne 0) { throw 'The environment does not use Python 3.12.' }
    & $taskVenvPython -m pip install --upgrade pip 'setuptools>=83'
    if ($LASTEXITCODE -ne 0) { throw 'Unable to install packaging tools.' }
    & $taskVenvPython -m pip install torch==2.11.0+cu128 torchaudio==2.11.0+cu128 --index-url https://download.pytorch.org/whl/cu128
    if ($LASTEXITCODE -ne 0) { throw 'Unable to install CUDA PyTorch.' }
    & $taskVenvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Unable to install runtime dependencies.' }
    & $taskVenvPython -m pip install --no-deps -e ./vendor/whisperlivekit
    if ($LASTEXITCODE -ne 0) { throw 'Unable to install the vendored backend.' }
    foreach ($taskDirectory in @('models', 'runtime', 'history')) {
        New-Item -ItemType Directory -Path (Join-Path $taskRoot $taskDirectory) -Force | Out-Null
    }
    & $taskVenvPython -c "import torch; print('GPU:', torch.cuda.get_device_name() if torch.cuda.is_available() else 'not detected'); assert torch.cuda.is_available(), 'A supported NVIDIA GPU and driver are required'"
    if ($LASTEXITCODE -ne 0) { throw 'Python is installed, but a supported NVIDIA GPU was not detected.' }
    Write-Host 'Dependencies ready. Read THIRD_PARTY_NOTICES.md, then run:'
    Write-Host '.\.venv\Scripts\python.exe .\scripts\prepare_models.py --accept-model-licenses'
} finally { Pop-Location }
