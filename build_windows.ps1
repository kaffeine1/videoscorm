param(
    [Parameter(Mandatory = $true)]
    [string]$FfprobePath
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -Path $FfprobePath -PathType Leaf)) {
    throw "ffprobe.exe non trovato: $FfprobePath"
}
if ([IO.Path]::GetFileName($FfprobePath).ToLowerInvariant() -ne 'ffprobe.exe') {
    throw 'Specificare ffprobe.exe, non ffmpeg.exe.'
}

Set-Location $PSScriptRoot
python -m PyInstaller --noconfirm --onefile --windowed --name VideoSCORM `
    --add-data "index.html;." --add-data "player.js;." --add-data "style.css;." `
    --add-data "h5p;h5p" --add-data "vendor;vendor" `
    --add-binary "$FfprobePath;." gui.py
if ($LASTEXITCODE -ne 0) { throw 'Build PyInstaller non riuscita.' }
Write-Host "Creato: $PSScriptRoot\dist\VideoSCORM.exe"
