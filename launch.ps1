param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskUrl = 'http://127.0.0.1:8766'
$taskHealth = $null
try { $taskHealth = Invoke-RestMethod "$taskUrl/health" -TimeoutSec 2 } catch { }
if ($null -ne $taskHealth) {
    if ($taskHealth.PSObject.Properties.Name -contains 'translation_ready') {
        if (-not $NoBrowser) { Start-Process $taskUrl }
        exit
    }
    throw 'Port 8766 is occupied by another service.'
}
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw '运行环境缺失，请重新准备安装环境。' }
$taskProcess = Start-Process -FilePath $taskPython -ArgumentList @('-u', 'classroom_app.py') -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskRoot 'runtime/app.log') -RedirectStandardError (Join-Path $taskRoot 'runtime/app-error.log') -PassThru
for ($taskIndex=0; $taskIndex -lt 60; $taskIndex++) {
    if ($taskProcess.HasExited) { throw '服务启动失败，请打开 runtime/app-error.log 查看原因。' }
    try {
        $taskHealth = Invoke-RestMethod "$taskUrl/health" -TimeoutSec 1
        if ($taskHealth.PSObject.Properties.Name -contains 'translation_ready') {
            if (-not $NoBrowser) { Start-Process $taskUrl }
            exit
        }
    } catch { }
    Start-Sleep -Seconds 1
}
throw '启动超时，请查看 runtime/app-error.log。'



