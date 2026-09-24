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
# Build only into a disposable packaging directory. Never let PyInstaller remove
# the installed app directory: users may have exported films inside it.
$packageRoot = Join-Path $PSScriptRoot 'build/package'
$stagedApp = Join-Path $packageRoot 'AppVideoAI'
$releaseRoot = Join-Path $PSScriptRoot 'release-simple'
$installedApp = Join-Path $releaseRoot 'AppVideoAI'
& $appPython -m PyInstaller --noconfirm --distpath $packageRoot AppVideoAI.spec
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
Copy-Item CLIENT-GUIDE.txt (Join-Path $stagedApp 'HUONG-DAN.txt') -Force
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
# ZIP the clean staging directory, never the user's outputs or saved files.
Compress-Archive -LiteralPath $stagedApp -DestinationPath (Join-Path $releaseRoot 'AppVideoAI-Tester.zip') -Force
$installedExe = Join-Path $installedApp 'AppVideoAI.exe'
$running = Get-Process -Name AppVideoAI -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $installedExe }
if ($running) {
    Write-Output 'ZIP ready. Running app was kept open; extract the new ZIP after closing it.'
} else {
    New-Item -ItemType Directory -Path $installedApp -Force | Out-Null
    foreach ($item in Get-ChildItem -LiteralPath $stagedApp) {
        Copy-Item -LiteralPath $item.FullName -Destination $installedApp -Recurse -Force
    }
    Write-Output 'EXE and ZIP ready. Existing exported videos were preserved.'
}
