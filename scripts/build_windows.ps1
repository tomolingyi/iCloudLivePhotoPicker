param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Find-Python {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($Version in @("-3.13", "-3.12", "-3.11", "-3.10")) {
            & py $Version -c "import sys" 2>$null
            if ($LASTEXITCODE -eq 0) {
                return @{ Command = "py"; Arguments = @($Version) }
            }
        }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python -c "import sys; assert (3, 10) <= sys.version_info[:2] < (3, 14)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return @{ Command = "python"; Arguments = @() }
        }
    }
    throw "Python 3.10-3.13 was not found."
}

$Base = Find-Python
$VersionToken = & $Base.Command @($Base.Arguments) -c "import sys; print(sys.version_info.major*100+sys.version_info.minor)"
$EnvironmentRoot = if ($env:LOCALAPPDATA) {
    Join-Path $env:LOCALAPPDATA "iCloudLivePhotoPicker"
} else {
    Join-Path $env:TEMP "iCloudLivePhotoPicker"
}
$VirtualEnvironment = Join-Path $EnvironmentRoot "venv-py$VersionToken"
$Python = Join-Path $VirtualEnvironment "Scripts\python.exe"
$RuntimeStamp = Join-Path $VirtualEnvironment "requirements.installed.txt"
$BuildStamp = Join-Path $VirtualEnvironment "build-requirements.installed.txt"

New-Item -ItemType Directory -Force -Path $EnvironmentRoot | Out-Null
if (-not (Test-Path -LiteralPath $Python)) {
    Write-Host "Creating the shared environment once at $VirtualEnvironment"
    & $Base.Command @($Base.Arguments) -m venv $VirtualEnvironment
    if ($LASTEXITCODE -ne 0) { throw "Unable to create the shared environment." }
}

$Requirements = Join-Path $ProjectRoot "requirements.txt"
$BuildRequirements = Join-Path $ProjectRoot "requirements-build.txt"
$RuntimeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Requirements).Hash
$BuildHash = "$RuntimeHash`n$((Get-FileHash -Algorithm SHA256 -LiteralPath $BuildRequirements).Hash)"
$InstalledRuntimeHash = if (Test-Path -LiteralPath $RuntimeStamp) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $RuntimeStamp).Hash
} else { "" }
$RequiredRuntimeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Requirements).Hash

if ($InstalledRuntimeHash -ne $RequiredRuntimeHash) {
    Write-Host "Installing runtime dependencies into the shared environment..."
    & $Python -m pip install --upgrade "pip>=25.1"
    if ($LASTEXITCODE -ne 0) { throw "Unable to update pip." }
    & $Python -m pip install -r $Requirements
    if ($LASTEXITCODE -ne 0) { throw "Unable to install runtime dependencies." }
    Copy-Item -LiteralPath $Requirements -Destination $RuntimeStamp -Force
}

$InstalledBuildHash = if (Test-Path -LiteralPath $BuildStamp) {
    Get-Content -LiteralPath $BuildStamp -Raw
} else { "" }
if ($InstalledBuildHash.Trim() -ne $BuildHash.Trim()) {
    Write-Host "Installing build tools into the shared environment..."
    & $Python -m pip install -r $BuildRequirements
    if ($LASTEXITCODE -ne 0) { throw "Unable to install build dependencies." }
    Set-Content -LiteralPath $BuildStamp -Value $BuildHash -Encoding utf8NoBOM
} else {
    Write-Host "Reusing the shared build environment."
}

Push-Location $ProjectRoot
try {
    $env:PYTHONPATH = Join-Path $ProjectRoot "src"
    $env:QT_QPA_PLATFORM = "offscreen"
    if (-not $SkipTests) {
        Write-Host "Running automated tests..."
        & $Python -m unittest discover -s tests -v
        if ($LASTEXITCODE -ne 0) { throw "Tests failed; packaging stopped." }
    }

    foreach ($Directory in @("build", "dist")) {
        $Target = Join-Path $ProjectRoot $Directory
        if (Test-Path -LiteralPath $Target) {
            $Resolved = (Resolve-Path -LiteralPath $Target).Path
            if (-not $Resolved.StartsWith($ProjectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Refusing to clean unexpected path: $Resolved"
            }
            Remove-Item -LiteralPath $Resolved -Recurse -Force
        }
    }

    Write-Host "Building the Windows portable application..."
    & $Python -m PyInstaller --noconfirm --clean (Join-Path $ProjectRoot "packaging\windows\icloud-live-photo-picker.spec")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

    $PortableDirectory = Join-Path $ProjectRoot "dist\iCloudLivePhotoPicker"
    foreach ($File in @("README.md", "CHANGELOG.md", "LICENSE", "THIRD_PARTY_NOTICES.md")) {
        Copy-Item -LiteralPath (Join-Path $ProjectRoot $File) -Destination $PortableDirectory -Force
    }
    $PortableImages = Join-Path $PortableDirectory "docs\images"
    New-Item -ItemType Directory -Force -Path $PortableImages | Out-Null
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "docs\images\application.png") -Destination $PortableImages -Force
    $Archive = Join-Path $ProjectRoot "dist\iCloudLivePhotoPicker-v0.5.3-windows-x64.zip"
    Compress-Archive -Path (Join-Path $PortableDirectory "*") -DestinationPath $Archive -CompressionLevel Optimal -Force

    $SourceStage = Join-Path $ProjectRoot "dist\iCloudLivePhotoPicker-v0.5.3-source"
    New-Item -ItemType Directory -Force -Path $SourceStage | Out-Null
    foreach ($Directory in @(".github", "docs", "packaging", "scripts", "src", "tests")) {
        Copy-Item -LiteralPath (Join-Path $ProjectRoot $Directory) -Destination $SourceStage -Recurse -Force
    }
    foreach ($File in @(
        ".editorconfig", ".gitattributes", ".gitignore", "app.py", "build_installer.bat", "build_windows.bat",
        "CHANGELOG.md", "CONTRIBUTING.md", "LICENSE", "MANIFEST.in", "pyproject.toml",
        "README.md", "requirements-build.txt", "requirements.txt", "run_windows.bat",
        "SECURITY.md", "THIRD_PARTY_NOTICES.md"
    )) {
        Copy-Item -LiteralPath (Join-Path $ProjectRoot $File) -Destination $SourceStage -Force
    }
    Get-ChildItem -LiteralPath $SourceStage -Recurse -Directory -Filter "__pycache__" |
        Sort-Object FullName -Descending |
        Remove-Item -Recurse -Force
    Get-ChildItem -LiteralPath $SourceStage -Recurse -File -Include "*.pyc", "*.pyo" |
        Remove-Item -Force
    $SourceArchive = Join-Path $ProjectRoot "dist\iCloudLivePhotoPicker-v0.5.3-source.zip"
    Compress-Archive -Path (Join-Path $SourceStage "*") -DestinationPath $SourceArchive -CompressionLevel Optimal -Force
    Remove-Item -LiteralPath $SourceStage -Recurse -Force
    Write-Host "Build complete:"
    Write-Host "  $PortableDirectory\iCloudLivePhotoPicker.exe"
    Write-Host "  $Archive"
    Write-Host "  $SourceArchive"
}
finally {
    Pop-Location
}
