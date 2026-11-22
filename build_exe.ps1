# =====================================================================
#  Slideshow Video Creator Pro - build a standalone Windows .exe
#
#  Double-click build_exe.bat (or run this file) and it will:
#    1. bump the release version (or use -SetVersion 4.5.0)
#    2. make sure PyInstaller is available
#    3. bundle FFmpeg next to the exe (downloads it once if missing)
#    4. build dist\SlideshowVideoCreator\SlideshowVideoCreator.exe
#    5. build Windows/source ZIPs + update-manifest.json in release\
#
#  Optional:  build_exe.ps1 -SetVersion 4.5   (set an exact version)
# =====================================================================

#Requires -Version 5.1
param(
    [string]$SetVersion = ""
)

$ErrorActionPreference = 'Stop'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

$AppDir      = $PSScriptRoot
$EntryFile   = Join-Path $AppDir 'slideshow_app v4.py'
$ReqFile     = Join-Path $AppDir 'requirements.txt'
$VersionFile = Join-Path $AppDir 'build_version.json'
$DistRoot    = Join-Path $AppDir 'dist'
$BuildRoot   = Join-Path $AppDir 'build'
$ReleaseRoot = Join-Path $AppDir 'release'
$FFmpegDir   = Join-Path $AppDir 'ffmpeg'
$BaseName    = 'SlideshowVideoCreator'
$FFmpegUrl   = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'

function Step($t) { Write-Host ""; Write-Host "==> $t" -ForegroundColor Cyan }
function Ok($t)   { Write-Host "    $t" -ForegroundColor Green }
function Warn($t) { Write-Host "    $t" -ForegroundColor Yellow }

function Download-File {
    param([string]$Url, [string]$Dest, [string]$Name)
    Write-Host "    Downloading $Name ..." -ForegroundColor Gray
    if (Test-Path -LiteralPath $Dest) { Remove-Item -LiteralPath $Dest -Force -ErrorAction SilentlyContinue }
    $ok = $false
    try { Start-BitsTransfer -Source $Url -Destination $Dest -ErrorAction Stop; $ok = $true } catch { }
    if (-not $ok) {
        $old = $ProgressPreference; $ProgressPreference = 'SilentlyContinue'
        try { Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing -TimeoutSec 900 -ErrorAction Stop; $ok = $true }
        finally { $ProgressPreference = $old }
    }
    if (-not $ok -or -not (Test-Path -LiteralPath $Dest)) { throw "Download failed: $Name" }
}

# ------------------------------------------------------------ version bump
if (Test-Path -LiteralPath $VersionFile) {
    try { $current = (Get-Content -LiteralPath $VersionFile -Raw | ConvertFrom-Json).version }
    catch { $current = '4.0' }
} else { $current = '4.0' }

if ($SetVersion) {
    $newVersion = $SetVersion
} else {
    $parts = $current.Split('.')
    $major = [int]$parts[0]
    $minor = if ($parts.Count -gt 1) { [int]$parts[1] } else { 0 }
    $newVersion = "$major.$($minor + 1).0"
}
if ($newVersion -notmatch '^\d+\.\d+(\.\d+)?$') { throw 'Use a numeric version such as 4.5.0.' }
$Name = $BaseName
$VersionResource = Join-Path $BuildRoot 'windows-version.txt'

Write-Host ""
Write-Host "===================================================" -ForegroundColor White
Write-Host "  Building $Name" -ForegroundColor White
Write-Host "  $current  ->  $newVersion" -ForegroundColor White
Write-Host "===================================================" -ForegroundColor White

if (-not (Test-Path -LiteralPath $EntryFile)) { throw "Cannot find 'slideshow_app v4.py' next to the script." }

# --------------------------------------------------------- interpreter
Step 'Python + PyInstaller'
$Python = 'py'
try {
    & $Python -V | Out-Null
    Ok "Using the 'py' launcher"
} catch {
    throw "Python launcher 'py' not found. Install Python 3.12 from python.org first."
}

& $Python -m PyInstaller --version 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Warn 'PyInstaller not found - installing it ...'
    & $Python -m pip install --upgrade pyinstaller
    if ($LASTEXITCODE -ne 0) { throw 'Could not install PyInstaller.' }
}
$piVer = (& $Python -m PyInstaller --version 2>$null | Select-Object -First 1)
Ok "PyInstaller $piVer"

Step 'Checking the app dependencies'
& $Python -c "import PIL, numpy, moviepy, cv2, onnxruntime, tkinterdnd2"
if ($LASTEXITCODE -ne 0) {
    Warn 'Some dependencies are missing - installing requirements.txt ...'
    & $Python -m pip install -r $ReqFile
    if ($LASTEXITCODE -ne 0) { throw 'Could not install the app dependencies.' }
}
Ok 'Dependencies present'

# --------------------------------------------------------------- FFmpeg
Step 'FFmpeg for the bundle'
if (Test-Path -LiteralPath (Join-Path $FFmpegDir 'ffmpeg.exe')) {
    Ok 'Using the existing .\ffmpeg folder'
} else {
    $zip = Join-Path $env:TEMP 'ffmpeg-essentials.zip'
    $extract = Join-Path $env:TEMP 'ffmpeg-extract'
    try {
        Download-File -Url $FFmpegUrl -Dest $zip -Name 'FFmpeg (~106 MB)'
        if (Test-Path -LiteralPath $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }
        Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
        $ff = Get-ChildItem -LiteralPath $extract -Recurse -Filter 'ffmpeg.exe'  | Select-Object -First 1
        $fp = Get-ChildItem -LiteralPath $extract -Recurse -Filter 'ffprobe.exe' | Select-Object -First 1
        $fpl = Get-ChildItem -LiteralPath $extract -Recurse -Filter 'ffplay.exe' | Select-Object -First 1
        if (-not $ff -or -not $fp) { throw 'ffmpeg.exe / ffprobe.exe not found in the archive.' }
        New-Item -ItemType Directory -Force -Path $FFmpegDir | Out-Null
        Copy-Item -LiteralPath $ff.FullName  -Destination (Join-Path $FFmpegDir 'ffmpeg.exe')  -Force
        Copy-Item -LiteralPath $fp.FullName  -Destination (Join-Path $FFmpegDir 'ffprobe.exe') -Force
        if ($fpl) { Copy-Item -LiteralPath $fpl.FullName -Destination (Join-Path $FFmpegDir 'ffplay.exe') -Force }
        Ok 'FFmpeg downloaded into .\ffmpeg'
    } catch {
        Warn "Could not download FFmpeg ($($_.Exception.Message))."
        Warn 'The exe will build, but video export needs FFmpeg. Put ffmpeg.exe/ffprobe.exe in .\ffmpeg and rebuild.'
    } finally {
        Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $extract -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# Version must be written before bundling, so source, EXE and manifest agree.
Set-Content -LiteralPath $VersionFile -Value ("{`n  `"version`": `"$newVersion`"`n}") -Encoding UTF8
& $Python (Join-Path $AppDir 'tools\package_release.py') --version-resource $VersionResource
if ($LASTEXITCODE -ne 0) { throw 'Could not generate Windows version information.' }

# ------------------------------------------------------------ PyInstaller
Step "Building $Name.exe (this takes a few minutes)"
if (Test-Path -LiteralPath (Join-Path $DistRoot $Name)) {
    Remove-Item -LiteralPath (Join-Path $DistRoot $Name) -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Force -Path $DistRoot, $ReleaseRoot | Out-Null

$pyArgs = @(
    '--noconfirm', '--clean', '--windowed', '--onedir',
    '--name', $Name,
    '--distpath', $DistRoot,
    '--workpath', $BuildRoot,
    '--specpath', $BuildRoot,
    '--paths', $AppDir,
    '--version-file', $VersionResource,
    '--add-data', "$VersionFile;.",
    '--add-data', "$(Join-Path $AppDir 'slideshow\update_install.ps1');slideshow",
    '--collect-all', 'tkinterdnd2',
    '--collect-all', 'imageio_ffmpeg',
    '--collect-all', 'cv2',
    '--collect-binaries', 'onnxruntime',
    '--copy-metadata', 'imageio',
    '--copy-metadata', 'imageio-ffmpeg',
    '--copy-metadata', 'moviepy',
    '--copy-metadata', 'proglog',
    '--copy-metadata', 'tqdm',
    '--hidden-import', 'moviepy.editor',
    '--hidden-import', 'onnxruntime',
    '--hidden-import', 'cv2',
    '--hidden-import', 'proglog',
    '--hidden-import', 'decorator',
    '--hidden-import', 'tqdm',
    '--hidden-import', 'PIL._tkinter_finder',
    # Keep the build lean: only the onnxruntime runtime is needed, not its
    # transformers/tools (which drag in torch/tensorflow/numba).
    '--exclude-module', 'onnxruntime.transformers',
    '--exclude-module', 'onnxruntime.tools',
    '--exclude-module', 'onnxruntime.quantization',
    '--exclude-module', 'onnxruntime.datasets',
    '--exclude-module', 'torch',
    '--exclude-module', 'torchvision',
    '--exclude-module', 'torchaudio',
    '--exclude-module', 'tensorflow',
    '--exclude-module', 'keras',
    '--exclude-module', 'numba',
    '--exclude-module', 'llvmlite',
    '--exclude-module', 'sympy',
    '--exclude-module', 'pygame',
    '--exclude-module', 'av',
    '--exclude-module', 'matplotlib',
    '--exclude-module', 'scipy',
    '--exclude-module', 'pandas',
    '--exclude-module', 'sklearn',
    '--exclude-module', 'IPython',
    '--exclude-module', 'pytest',
    $EntryFile
)
& $Python -m PyInstaller @pyArgs
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }

$distFolder = Join-Path $DistRoot $Name
$distExe = Join-Path $distFolder "$Name.exe"
if (-not (Test-Path -LiteralPath $distExe)) { throw "Build finished but $distExe was not found." }
Ok "Built $distExe"
Copy-Item -LiteralPath $VersionFile -Destination (Join-Path $distFolder 'build_version.json') -Force

# ------------------------------------------------- copy FFmpeg next to exe
Step 'Adding FFmpeg to the build'
if (Test-Path -LiteralPath (Join-Path $FFmpegDir 'ffmpeg.exe')) {
    $target = Join-Path $distFolder 'ffmpeg'
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -Path (Join-Path $FFmpegDir '*') -Destination $target -Recurse -Force
    Ok 'Copied ffmpeg\ next to the exe'
} else {
    Warn 'No ffmpeg\ folder - the exe was built without FFmpeg.'
}

# ------------------------------------------------------ release + updater ZIPs
Step 'Packaging clean release and automatic-update assets'
& $Python (Join-Path $AppDir 'tools\package_release.py') --windows-dir $distFolder --output-dir $ReleaseRoot
if ($LASTEXITCODE -ne 0) { throw 'Release packaging failed.' }
$zipPath = Join-Path $ReleaseRoot "${BaseName}_v${newVersion}_windows.zip"

$nextMaj = [int]$newVersion.Split('.')[0]
$nextMin = [int]$newVersion.Split('.')[1] + 1

Write-Host ""
Write-Host "===================================================" -ForegroundColor Green
Write-Host "  Done:  $Name" -ForegroundColor Green
Write-Host "  EXE:   $distExe"
Write-Host "  ZIP:   $zipPath"
Write-Host "  Next build will be v$nextMaj.$nextMin"
Write-Host "===================================================" -ForegroundColor Green
