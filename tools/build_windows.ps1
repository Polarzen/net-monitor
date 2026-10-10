[CmdletBinding()]
param(
    [string]$Python = (Join-Path $PSScriptRoot '..\.venv-build-stage5\Scripts\python.exe'),
    [string]$OutputRoot = (Join-Path $PSScriptRoot '..\artifacts\stage5'),
    [ValidateSet('internal-test', 'public-prerelease')]
    [string]$Channel = 'internal-test'
)
$ErrorActionPreference = 'Stop'
$pythonPath = (Resolve-Path -LiteralPath $Python).Path
& $pythonPath (Join-Path $PSScriptRoot 'build_windows.py') --output-root $OutputRoot --channel $Channel
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
