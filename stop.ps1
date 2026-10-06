$ErrorActionPreference = 'Stop'
$taskKey = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'runtime/local.key') -Raw
$taskResponse = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8766/shutdown' -Headers @{'x-local-key'=$taskKey}
if ($taskResponse.ok) { Write-Host 'Stopped classroom service.' }
