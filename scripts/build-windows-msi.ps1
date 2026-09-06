[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$FfmpegDirectory,
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$publishDirectory = Join-Path $repositoryRoot "build\windows\whisperflow"
$publishParent = Split-Path -Parent $publishDirectory
$ffmpeg = Join-Path $FfmpegDirectory "ffmpeg.exe"
$ffprobe = Join-Path $FfmpegDirectory "ffprobe.exe"

foreach ($tool in @("pyinstaller", "wix")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "Required build tool '$tool' was not found on PATH."
    }
}
foreach ($binary in @($ffmpeg, $ffprobe)) {
    if (-not (Test-Path $binary -PathType Leaf)) {
        throw "Required FFmpeg binary was not found: $binary"
    }
}

Remove-Item $publishDirectory -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $publishParent -Force | Out-Null
Push-Location $repositoryRoot
try {
    pyinstaller --noconfirm --clean --onedir --name whisperflow --paths src `
        --collect-all faster_whisper --collect-all ctranslate2 `
        --add-binary "$ffmpeg;bin" --add-binary "$ffprobe;bin" src\cli\main.py
    Move-Item dist\whisperflow $publishDirectory
    wix build packaging\windows\WhisperFlow.wxs -d "PublishDir=$publishDirectory" `
        -d "Version=$Version" -o "dist\WhisperFlow-$Version.msi"
}
finally {
    Pop-Location
}