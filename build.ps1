$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$appPython = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if (-not (Test-Path $appPython)) { $appPython = (Get-Command python).Source }
$env:PYTHONPATH = Join-Path $PSScriptRoot '.build-deps'
$env:TCL_LIBRARY = Join-Path $PSScriptRoot 'vendor/tcl/tcl8.6'
$env:TK_LIBRARY = Join-Path $PSScriptRoot 'vendor/tcl/tk8.6'
foreach ($name in @('ffmpeg', 'ffprobe')) {
    $source = (Get-Command $name).Source
    Copy-Item -LiteralPath $source -Destination (Join-Path $PSScriptRoot "vendor/$name.exe") -Force
}
& $appPython -m PyInstaller --noconfirm --distpath release-simple AppVideoAI.spec
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
Copy-Item CLIENT-GUIDE.txt release-simple/AppVideoAI/HUONG-DAN.txt -Force
Compress-Archive -LiteralPath release-simple/AppVideoAI -DestinationPath release-simple/AppVideoAI-Tester.zip -Force
