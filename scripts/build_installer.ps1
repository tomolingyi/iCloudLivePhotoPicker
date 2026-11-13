param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PortableBuild = Join-Path $PSScriptRoot "build_windows.ps1"

if ($SkipTests) {
    & $PortableBuild -SkipTests
} else {
    & $PortableBuild
}
if ($LASTEXITCODE -ne 0) {
    throw "The portable Windows build failed; installer creation stopped."
}

$Candidates = @(
    (Get-Command "ISCC.exe" -ErrorAction SilentlyContinue).Source,
    (Join-Path $env:ProgramFiles "Inno Setup 7\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 7\ISCC.exe")
)
$Compiler = $Candidates |
    Where-Object { $_ -and (Test-Path -LiteralPath $_) } |
    Select-Object -First 1
if (-not $Compiler) {
    throw "Inno Setup was not found. Install it, then run build_installer.bat again."
}

$PortableDirectory = Join-Path $ProjectRoot "dist\iCloudLivePhotoPicker"
if (-not (Test-Path -LiteralPath (Join-Path $PortableDirectory "iCloudLivePhotoPicker.exe"))) {
    throw "The portable application directory is incomplete: $PortableDirectory"
}

$InstallerScript = Join-Path $ProjectRoot "packaging\windows\installer.iss"
Write-Host "Building the Windows Setup installer with $Compiler"
& $Compiler $InstallerScript
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed."
}

$Installer = Join-Path $ProjectRoot "dist\iCloudLivePhotoPicker-v0.5.4-Setup.exe"
if (-not (Test-Path -LiteralPath $Installer)) {
    throw "The installer compiler completed without producing $Installer"
}
Write-Host "Installer build complete:"
Write-Host "  $Installer"
