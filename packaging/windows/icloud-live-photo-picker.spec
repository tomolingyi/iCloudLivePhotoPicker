import importlib.util
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata


ROOT = Path(SPECPATH).parents[1]
SRC = ROOT / "src"
ICON = SRC / "icloud_live_picker" / "assets" / "app-icon.ico"

datas = [(str(ICON), "icloud_live_picker/assets")]
binaries = []
hiddenimports = []

# PyInstaller's isolated Qt probe can be confused by Anaconda's older ICU
# libraries. Collect the small set of Qt plugins this desktop app uses
# explicitly so builds remain complete even when that probe emits a warning.
pyqt_spec = importlib.util.find_spec("PyQt6")
if pyqt_spec is None or pyqt_spec.origin is None:
    raise RuntimeError("PyQt6 is not installed in the build environment")
qt_plugins = Path(pyqt_spec.origin).parent / "Qt6" / "plugins"
for group in ("platforms", "styles", "imageformats", "iconengines"):
    source = qt_plugins / group
    if source.is_dir():
        binaries += [(str(path), f"PyQt6/Qt6/plugins/{group}") for path in source.glob("*.dll")]

# A venv created from Anaconda uses its _ctypes extension, whose libffi DLL
# lives next to the base interpreter instead of inside the venv.
ffi_candidates = (
    Path(sys.base_prefix) / "Library" / "bin" / "ffi.dll",
    Path(sys.prefix) / "Library" / "bin" / "ffi.dll",
)
for candidate in ffi_candidates:
    if candidate.is_file():
        binaries.append((str(candidate), "."))
        break

for package in ("pyicloud_ipd", "imageio_ffmpeg", "certifi"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

hiddenimports += collect_submodules("keyring.backends")
hiddenimports += collect_submodules("keyrings.alt")
for distribution in ("icloudpd", "imageio-ffmpeg", "keyring", "keyrings-alt"):
    datas += copy_metadata(distribution)

a = Analysis(
    [str(ROOT / "app.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "customtkinter", "pytest"],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="iCloudLivePhotoPicker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON),
    version=str(ROOT / "packaging" / "windows" / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="iCloudLivePhotoPicker",
)
