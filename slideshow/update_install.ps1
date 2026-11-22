# Runs from an external staging folder after the app closes. Never swaps the
# whole installation directory: only the verified application files are copied.
#Requires -Version 5.1
param([Parameter(Mandatory=$true)][string]$ConfigPath)
$ErrorActionPreference = 'Stop'
$config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$work = [IO.Path]::GetFullPath($config.work)
$appDir = [IO.Path]::GetFullPath($config.app_dir)
$stage = [IO.Path]::GetFullPath($config.stage)
$backup = Join-Path $work 'backup'
$log = Join-Path $work 'install.log'
$ready = Join-Path $work 'startup-ready.json'
$changes = New-Object System.Collections.ArrayList
$newProcess = $null
$oldExited = $false

function Log([string]$message) {
    Add-Content -LiteralPath $log -Value ("{0:u} {1}" -f (Get-Date), $message) -Encoding UTF8
}

function ChildPath([string]$root, [string]$relative) {
    if ([IO.Path]::IsPathRooted($relative) -or $relative.Contains(':') -or
        $relative.Contains('\') -or ($relative.Split('/') -contains '..')) {
        throw "Invalid update path: $relative"
    }
    $path = [IO.Path]::GetFullPath((Join-Path $root ($relative.Replace('/', '\'))))
    if (-not $path.StartsWith($root.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Update path escapes installation: $relative"
    }
    return $path
}

function CheckTarget([string]$relative) {
    $top = $relative.Split('/')[0].ToLowerInvariant()
    if ($top -in @('settings.json','profiles.json','profiles','projects','music',
                  'music_tracker.json','models','temp','erase_cache','logo.jpg',
                  '.git','.venv','venv','crash.log')) {
        throw "User data cannot be updated: $relative"
    }
    if ($config.kind -eq 'source') {
        $rootFiles = @('slideshow_app v4.py','build_version.json','requirements.txt',
                      'run.bat','install.bat','install.ps1','LICENSE','README.md')
        if ($relative -notin $rootFiles -and $relative -notmatch '^slideshow/.+\.(py|ps1)$') {
            throw "Not an application source file: $relative"
        }
    } elseif ($config.kind -eq 'windows') {
        $exeName = [IO.Path]::GetFileName($config.restart_exe)
        if ($relative -notin @($exeName, 'build_version.json') -and
            -not $relative.StartsWith('_internal/') -and
            $relative -notin @('ffmpeg/ffmpeg.exe','ffmpeg/ffprobe.exe','ffmpeg/ffplay.exe')) {
            throw "Not an application binary: $relative"
        }
    } else { throw 'Unknown update installation kind.' }
}

function CopyRetry([string]$source, [string]$destination) {
    $parent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    for ($try = 0; $try -lt 15; $try++) {
        try { Copy-Item -LiteralPath $source -Destination $destination -Force; return }
        catch { if ($try -eq 14) { throw }; Start-Sleep -Milliseconds 500 }
    }
}

function Launch([bool]$withReady) {
    $arguments = @($config.restart_args)
    if ($withReady) { $arguments += @('--update-ready', $ready) }
    $options = @{ FilePath = $config.restart_exe; WorkingDirectory = $appDir; PassThru = $true }
    if ($arguments.Count -gt 0) {
        $options.ArgumentList = (($arguments | ForEach-Object { '"' + $_ + '"' }) -join ' ')
    }
    return Start-Process @options
}

try {
    Log "Preparing update to $($config.version) ($($config.kind))."
    if (-not (Test-Path -LiteralPath $appDir -PathType Container)) { throw 'Installation folder is missing.' }
    if ([int]$config.pid -gt 0) {
        $timer = [Diagnostics.Stopwatch]::StartNew()
        while (Get-Process -Id ([int]$config.pid) -ErrorAction SilentlyContinue) {
            if ($timer.Elapsed.TotalSeconds -gt 120) { throw 'The app did not close; update was not applied.' }
            Start-Sleep -Milliseconds 300
        }
    }
    $oldExited = $true
    foreach ($file in $config.files) {
        CheckTarget $file.target
        $source = ChildPath $stage $file.source
        $null = ChildPath $appDir $file.target
        if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.sha256) {
            throw "Checksum mismatch: $($file.source)"
        }
    }
    if ($config.install_dependencies) {
        Log 'Installing updated Python dependencies.'
        $pipLog = Join-Path $work 'dependencies.log'
        $pipErr = Join-Path $work 'dependencies-errors.log'
        $requirements = Join-Path $stage 'requirements.txt'
        $p = Start-Process -FilePath $config.python_exe -ArgumentList (
            '-m pip install --disable-pip-version-check -r "' + $requirements + '"') `
            -RedirectStandardOutput $pipLog -RedirectStandardError $pipErr -Wait -PassThru
        if ($p.ExitCode -ne 0) { throw "Python dependency installation failed; see $pipLog" }
    }
    foreach ($file in ($config.files | Sort-Object { $_.target -eq 'build_version.json' })) {
        $source = ChildPath $stage $file.source
        $target = ChildPath $appDir $file.target
        # A user's existing FFmpeg folder is retained. The release includes it
        # for fresh installations, but subsequent app updates do not replace it.
        if ($file.target.StartsWith('ffmpeg/') -and (Test-Path -LiteralPath $target)) { continue }
        $exists = Test-Path -LiteralPath $target
        if ($exists) { CopyRetry $target (ChildPath $backup $file.target) }
        $null = $changes.Add(@{ target = $file.target; existed = $exists })
        CopyRetry $source $target
    }
    Log 'Files installed. Starting application and waiting for startup confirmation.'
    $newProcess = Launch $true
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $confirmed = $false
    while ($timer.Elapsed.TotalSeconds -lt 120) {
        if (Test-Path -LiteralPath $ready) {
            try {
                $ack = Get-Content -LiteralPath $ready -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($ack.version -eq $config.version) { $confirmed = $true; break }
            } catch { }
        }
        if ($newProcess.HasExited) { break }
        Start-Sleep -Milliseconds 400
        $newProcess.Refresh()
    }
    if (-not $confirmed) { throw 'The updated app did not confirm startup. Rolling back.' }
    Log 'Update completed successfully.'
    @{ status = 'success'; version = $config.version; restart_pid = $newProcess.Id } | ConvertTo-Json | Set-Content (
        Join-Path $work 'result.json') -Encoding UTF8
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue
    exit 0
} catch {
    $failure = $_.Exception.Message
    Log "ERROR: $failure"
    if ($null -ne $newProcess -and -not $newProcess.HasExited) {
        Stop-Process -Id $newProcess.Id -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 800
    }
    for ($i = $changes.Count - 1; $i -ge 0; $i--) {
        $change = $changes[$i]
        try {
            $target = ChildPath $appDir $change.target
            if ($change.existed) { CopyRetry (ChildPath $backup $change.target) $target }
            elseif (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Force }
        } catch { Log "Rollback error: $($_.Exception.Message)" }
    }
    $restartedPid = 0
    if ($oldExited) {
        try { $restoredProcess = Launch $false; $restartedPid = $restoredProcess.Id }
        catch { Log 'Could not restart original app.' }
    }
    @{ status = 'failed'; error = $failure; restart_pid = $restartedPid } | ConvertTo-Json | Set-Content (
        Join-Path $work 'result.json') -Encoding UTF8
    if (-not $config.quiet) {
        Add-Type -AssemblyName System.Windows.Forms
        [Windows.Forms.MessageBox]::Show(
            "Update failed. The previous application files were restored.`n`n$failure`n`nLog: $log",
            'Slideshow Video Creator - Update') | Out-Null
    }
    exit 1
}
