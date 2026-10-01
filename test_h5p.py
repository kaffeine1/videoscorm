import json
from dataclasses import replace
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from batch import plan_batch, run_batch
from builder import BuildError, build_package


class H5PPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.video = self.root / "lezione.mp4"
        self.video.write_bytes(b"test-video")

    @patch("builder.inspect_video", return_value={"title": "Titolo è corretto", "duration": 10.5, "size": 10})
    def test_h5p_content_libraries_and_unmodified_video(self, _):
        path = build_package(self.video, self.root / "lesson.h5p", package_format="h5p", checkpoint=15, resume=False)
        with zipfile.ZipFile(path) as archive:
            self.assertIsNone(archive.testzip())
            metadata = json.loads(archive.read("h5p.json"))
            params = json.loads(archive.read("content/content.json"))
            self.assertEqual(metadata["mainLibrary"], "H5P.LumTrackedVideo")
            self.assertEqual(metadata["license"], "U")
            self.assertEqual(params["lessonTitle"], "Titolo è corretto")
            self.assertEqual(params["checkpointSeconds"], "15")
            self.assertFalse(params["resume"])
            self.assertEqual(archive.read("content/videos/video.mp4"), b"test-video")
            self.assertEqual(archive.getinfo("content/videos/video.mp4").compress_type, zipfile.ZIP_STORED)
            self.assertNotIn("imsmanifest.xml", archive.namelist())
            for dependency in metadata["preloadedDependencies"]:
                folder = f"{dependency['machineName']}-{dependency['majorVersion']}.{dependency['minorVersion']}"
                library = json.loads(archive.read(folder + "/library.json"))
                self.assertLessEqual(library["coreApi"]["minorVersion"], 27)
                for resource in library.get("preloadedJs", []) + library.get("preloadedCss", []):
                    self.assertIn(folder + "/" + resource["path"], archive.namelist())
            self.assertIn("H5P.Video-1.6/LICENSE.txt", archive.namelist())
            self.assertFalse(any(".github" in name for name in archive.namelist()))

    @patch("builder.inspect_video", return_value={"title": "Test", "duration": 10, "size": 10})
    def test_extension_and_format_mismatch_fail_without_output(self, _):
        for name, package_format in (("lesson.zip", "h5p"), ("lesson.h5p", "scorm"), ("lesson.zip", "bad")):
            with self.assertRaises(BuildError):
                build_package(self.video, self.root / name, package_format=package_format)
            self.assertFalse((self.root / name).exists())

    @patch("builder.inspect_video", return_value={"title": "Test", "duration": 10, "size": 10})
    def test_h5p_existing_file_and_failed_overwrite_are_preserved(self, _):
        output = self.root / "lesson.h5p"
        output.write_bytes(b"original-h5p")
        with self.assertRaises(BuildError):
            build_package(self.video, output, package_format="h5p")
        with patch("builder.zipfile.ZipFile.write", side_effect=OSError("Disco pieno")):
            with self.assertRaises(OSError):
                build_package(self.video, output, package_format="h5p", overwrite=True)
        self.assertEqual(output.read_bytes(), b"original-h5p")
        self.assertEqual(list(self.root.glob(".scorm-build-*")), [])

    @patch("batch.find_ffprobe", return_value="ffprobe")
    @patch("batch.inspect_video", return_value={"title": "Titolo", "duration": 10, "size": 10})
    def test_h5p_plan_preserves_folders_and_has_no_scorm_collisions(self, *_):
        nested = self.root / "modulo"
        nested.mkdir()
        (nested / "lezione.mp4").write_bytes(b"test-video")
        plan = plan_batch(self.root, self.root / "out", recursive=True, package_format="h5p")
        self.assertEqual(plan.package_format, "h5p")
        self.assertEqual([item.output.relative_to(plan.destination).as_posix() for item in plan.items],
                         ["lezione_h5p.h5p", "modulo/lezione_h5p.h5p"])
        bad = replace(plan, items=(replace(plan.items[0], output=plan.destination / "bad.zip"),))
        with self.assertRaises(BuildError):
            run_batch(bad)
        self.assertFalse(plan.destination.exists())

    @unittest.skipUnless(shutil.which("ffprobe"), "ffprobe non disponibile")
    def test_real_video_h5p_batch_and_repeated_run(self):
        sample = Path(__file__).parent / "build/installer/staging/app/sample.mp4"
        if not sample.exists():
            self.skipTest("Campione del build non disponibile")
        shutil.copyfile(sample, self.video)
        (self.root / "invalid.mp4").write_bytes(b"not-a-video")
        plan = plan_batch(self.root, self.root / "out", package_format="h5p")
        result = run_batch(plan)
        self.assertEqual((result.summary()["created"], result.summary()["failed"]), (1, 1))
        output = self.root / "out/lezione_h5p.h5p"
        before = output.read_bytes()
        result = run_batch(plan)
        self.assertEqual(result.summary()["skipped"], 1)
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(self.video.read_bytes(), sample.read_bytes())


if __name__ == "__main__":
    unittest.main()
