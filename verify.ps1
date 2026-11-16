$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonPath)) { throw 'Rode .\run.ps1 primeiro para preparar o ambiente virtual.' }
& $pythonPath -m unittest discover -s (Join-Path $PSScriptRoot 'tests') -v
if ($LASTEXITCODE -ne 0) { throw 'Testes unitarios falharam.' }
& $pythonPath (Join-Path $PSScriptRoot 'verify_oracle.py')
if ($LASTEXITCODE -ne 0) { throw 'Smoke test Oracle falhou.' }
