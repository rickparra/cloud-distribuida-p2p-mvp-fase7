$ErrorActionPreference = 'Stop'
$venvPath = Join-Path $PSScriptRoot '.venv'
$pythonPath = Join-Path $venvPath 'Scripts\python.exe'

if (-not (Test-Path $pythonPath)) {
    py -3.13 -m venv $venvPath
}
& $pythonPath -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependencias Python.' }
& $pythonPath (Join-Path $PSScriptRoot 'launch.py')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao iniciar o MVP. Confira a conexao Oracle.' }
