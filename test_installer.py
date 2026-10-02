from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import build_installer


class InstallerTests(unittest.TestCase):
    def test_windows_archive_includes_both_guides_and_matching_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "installer_dependencies.json").write_text("{}", encoding="utf-8")
            english = b"English installation instructions\n"
            italian = b"Istruzioni di installazione italiane\n"
            (root / "README-Windows.txt").write_bytes(english)
            (root / "README-Windows.it.txt").write_bytes(italian)

            def compile_stub(command, **_):
                output = next(value.removeprefix("-DOUTPUT=") for value in command
                              if value.startswith("-DOUTPUT="))
                Path(output).write_bytes(b"installer-test-fixture")

            with patch("build_installer.ROOT", root), \
                    patch("build_installer.prepare", return_value=root / "staging"), \
                    patch("build_installer.shutil.which", return_value="makensis"), \
                    patch("build_installer.subprocess.run", side_effect=compile_stub), \
                    patch("sys.argv", ["build_installer.py"]), redirect_stdout(io.StringIO()):
                self.assertEqual(build_installer.main(), 0)

            installer = root / "dist" / f"VideoSCORM-{build_installer.VERSION}-Setup-x64.exe"
            archive_path = root / "dist" / f"VideoSCORM-{build_installer.VERSION}-Windows.zip"
            with zipfile.ZipFile(archive_path) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()),
                                 {installer.name, installer.name + ".sha256", "README.txt", "LEGGIMI.txt"})
                self.assertEqual(archive.read(installer.name), installer.read_bytes())
                self.assertEqual(archive.read("README.txt"), english)
                self.assertEqual(archive.read("LEGGIMI.txt"), italian)
                expected = f"{build_installer.digest(installer)}  {installer.name}\n"
                self.assertEqual(archive.read(installer.name + ".sha256").decode("ascii"), expected)

    def test_installer_includes_and_removes_both_windows_guides(self):
        script = (Path(__file__).resolve().parent / "windows_installer.nsi").read_text(encoding="utf-8")
        for filename in ("README-Windows.txt", "README-Windows.it.txt"):
            self.assertIn(filename, build_installer.APP_FILES)
            self.assertIn(f'Delete "$INSTDIR\\app\\{filename}"', script)
        self.assertIn('CreateShortcut "$SMPROGRAMS\\Video SCORM\\Istruzioni.lnk" '
                      '"$INSTDIR\\app\\README-Windows.it.txt"', script)


if __name__ == "__main__":
    unittest.main()
