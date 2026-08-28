from __future__ import annotations

import unittest
from pathlib import Path


class WindowsLauncherTests(unittest.TestCase):
    def test_launcher_uses_versioned_shared_environment_and_dependency_stamp(self) -> None:
        launcher = (Path(__file__).parents[1] / "run_windows.bat").read_text(encoding="utf-8")

        self.assertIn(r"%LOCALAPPDATA%\iCloudLivePhotoPicker", launcher)
        self.assertIn(r"venv-py%PYVER%", launcher)
        self.assertIn("requirements.installed.txt", launcher)
        self.assertIn('fc /b "requirements.txt" "%STAMP%"', launcher)
        self.assertIn(r'set "PYTHONPATH=%CD%\src"', launcher)
        self.assertNotIn(r'set "VPY=.venv\Scripts\python.exe"', launcher)

    def test_installer_is_per_user_and_packages_the_complete_portable_app(self) -> None:
        root = Path(__file__).parents[1]
        installer = (root / "packaging" / "windows" / "installer.iss").read_text(encoding="utf-8")
        build_script = (root / "scripts" / "build_installer.ps1").read_text(encoding="utf-8")

        self.assertIn("PrivilegesRequired=lowest", installer)
        self.assertIn(r"DefaultDirName={localappdata}\Programs\iCloudLivePhotoPicker", installer)
        self.assertIn(r'Source: "..\..\dist\iCloudLivePhotoPicker\*"', installer)
        self.assertIn("recursesubdirs createallsubdirs", installer)
        self.assertIn("UninstallDisplayIcon", installer)
        self.assertIn("build_windows.ps1", build_script)
        self.assertIn("ISCC.exe", build_script)


if __name__ == "__main__":
    unittest.main()
