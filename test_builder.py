import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from builder import ADLCP, SCORM, BuildError, build_package, find_ffprobe, inspect_video


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / "Lezione_1.mp4"
        self.video.write_bytes(b"test-video")

    def probe_result(self, codec="h264", tags=None):
        return json.dumps({"format": {"duration": "10.5", "tags": tags or {}},
                           "streams": [{"codec_type": "video", "codec_name": codec}]})

    @patch("builder.find_ffprobe", return_value="/usr/bin/ffprobe")
    @patch("builder.subprocess.run")
    def test_title_metadata_and_filename_fallback(self, run, _):
        run.return_value.stdout = self.probe_result(tags={"title": "Perché studiare questa lezione"})
        self.assertEqual(inspect_video(self.video)["title"], "Perché studiare questa lezione")
        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")
        run.return_value.stdout = self.probe_result()
        self.assertEqual(inspect_video(self.video)["title"], "Lezione 1")

    @patch("builder.shutil.which", return_value=None)
    def test_installer_probe_is_available_without_path(self, _):
        bundled = self.root / "bin" / "ffprobe.exe"
        bundled.parent.mkdir()
        bundled.write_bytes(b"test-executable")
        with patch("builder.ROOT", self.root):
            self.assertEqual(find_ffprobe(), str(bundled))

    @patch("builder.find_ffprobe", return_value="/usr/bin/ffprobe")
    @patch("builder.subprocess.run")
    def test_reject_non_browser_codec(self, run, _):
        run.return_value.stdout = self.probe_result(codec="hevc")
        with self.assertRaises(BuildError):
            inspect_video(self.video)

    @patch("builder.inspect_video", return_value={"title": "Originale", "duration": 10.5, "size": 10})
    def test_package_manifest_and_options(self, _):
        target = self.root / "out.zip"
        build_package(self.video, target, title="Titolo modificato", checkpoint=15, resume=False)
        with zipfile.ZipFile(target) as archive:
            self.assertEqual(set(archive.namelist()), {"imsmanifest.xml", "index.html", "player.js",
                                                       "style.css", "config.json", "video.mp4"})
            manifest = ET.fromstring(archive.read("imsmanifest.xml"))
            resource = manifest.find(f".//{{{SCORM}}}resource")
            self.assertEqual(resource.attrib[f"{{{ADLCP}}}scormtype"], "sco")
            self.assertEqual(resource.attrib["href"], "index.html")
            self.assertEqual(manifest.find(f".//{{{SCORM}}}item/{{{SCORM}}}title").text, "Titolo modificato")
            config = json.loads(archive.read("config.json"))
            self.assertEqual(config["checkpointSeconds"], 15)
            self.assertFalse(config["resume"])
            self.assertEqual(archive.getinfo("video.mp4").compress_type, zipfile.ZIP_STORED)
        with self.assertRaises(BuildError):
            build_package(self.video, target)
        self.assertEqual(len(list(self.root.glob(".scorm-build-*"))), 0)

    @patch("builder.inspect_video", return_value={"title": "Originale", "duration": 10.5, "size": 10})
    def test_invalid_options_do_not_create_package(self, _):
        target = self.root / "out.zip"
        with self.assertRaises(BuildError):
            build_package(self.video, target, title="\n", checkpoint=30)
        with self.assertRaises(BuildError):
            build_package(self.video, target, checkpoint=3)
        self.assertFalse(target.exists())

    @patch("builder.inspect_video", return_value={"title": "Originale", "duration": 10.5, "size": 10})
    def test_failed_replacement_preserves_original_zip(self, _):
        target = self.root / "out.zip"
        target.write_bytes(b"original-package")
        with patch("builder.zipfile.ZipFile.write", side_effect=OSError("Disco pieno")):
            with self.assertRaises(OSError):
                build_package(self.video, target, overwrite=True)
        self.assertEqual(target.read_bytes(), b"original-package")
        self.assertEqual(list(self.root.glob(".scorm-build-*")), [])


if __name__ == "__main__":
    unittest.main()
