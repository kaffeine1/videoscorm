import csv
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from batch import BatchCancelled, plan_batch, run_batch
from builder import BuildError


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / "video"
        self.source.mkdir()
        self.output = self.root / "pacchetti"
        self.info = {"title": "Lezione perché", "duration": 4.0, "size": 10}
        for target, options in (("batch.find_ffprobe", {"return_value": "ffprobe"}),
                                ("batch.inspect_video", {"return_value": self.info}),
                                ("builder.inspect_video", {"return_value": self.info})):
            mocked = patch(target, **options)
            mocked.start()
            self.addCleanup(mocked.stop)

    def video(self, name):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test-video")
        return path

    def test_flat_scan_is_case_insensitive_and_ignores_other_files(self):
        self.video("02.MP4")
        self.video("01.mp4")
        self.video("note.txt")
        self.video("Modulo/03.mp4")
        plan = plan_batch(self.source, self.output)
        self.assertEqual([item.video.name for item in plan.items], ["01.mp4", "02.MP4"])
        self.assertFalse(self.output.exists())

    def test_recursive_names_preserve_subfolders(self):
        self.video("Modulo 1/Lezione.mp4")
        self.video("Modulo 2/Lezione.mp4")
        plan = plan_batch(self.source, self.output, recursive=True)
        report = run_batch(plan)
        self.assertEqual(report.summary()["created"], 2)
        self.assertTrue((self.output / "Modulo 1/Lezione_scorm.zip").exists())
        self.assertTrue((self.output / "Modulo 2/Lezione_scorm.zip").exists())

    def test_output_subfolder_is_excluded_from_recursive_scan(self):
        self.video("Lezione.mp4")
        destination = self.source / "SCORM"
        self.video("SCORM/non_input.mp4")
        plan = plan_batch(self.source, destination, recursive=True)
        self.assertEqual(len(plan.items), 1)

    def test_empty_or_invalid_source_does_not_create_output(self):
        for source in (self.source, self.root / "missing"):
            with self.assertRaises(BuildError):
                plan_batch(source, self.output)
        self.assertFalse(self.output.exists())

    def test_windows_filename_collisions_are_rejected_before_writes(self):
        paths = [self.source / "Lezione.mp4", self.source / "LEZIONE.MP4"]
        with patch("batch._videos", return_value=paths):
            with self.assertRaises(BuildError):
                plan_batch(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_title_overrides_and_package_options(self):
        self.video("Lezione.mp4")
        plan = plan_batch(self.source, self.output)
        item = replace(plan.items[0], title="Titolo corretto è questo")
        report = run_batch(replace(plan, items=(item,)), checkpoint=15, resume=False)
        with zipfile.ZipFile(item.output) as archive:
            config = json.loads(archive.read("config.json"))
            self.assertEqual(config["title"], item.title)
            self.assertEqual(config["checkpointSeconds"], 15)
            self.assertFalse(config["resume"])
            self.assertIn("imsmanifest.xml", archive.namelist())
        self.assertEqual(report.results[0].title, item.title)

    def test_existing_zip_is_skipped_unless_explicitly_overwritten(self):
        video = self.video("Lezione.mp4")
        plan = plan_batch(self.source, self.output)
        self.output.mkdir()
        target = plan.items[0].output
        target.write_bytes(b"old-package")
        report = run_batch(plan)
        self.assertEqual(report.summary()["skipped"], 1)
        self.assertEqual(target.read_bytes(), b"old-package")
        report = run_batch(plan, overwrite=True)
        self.assertEqual(report.summary()["created"], 1)
        self.assertTrue(zipfile.is_zipfile(target))
        self.assertEqual(video.read_bytes(), b"test-video")

    def test_invalid_video_does_not_stop_valid_files(self):
        self.video("01.mp4")
        self.video("02.mp4")
        self.video("03.mp4")

        def inspect(video, _):
            if video.name == "02.mp4":
                raise BuildError("Video HEVC non compatibile")
            return self.info

        with patch("batch.inspect_video", side_effect=inspect):
            plan = plan_batch(self.source, self.output)
        report = run_batch(plan)
        self.assertEqual([row.status for row in report.results], ["created", "failed", "created"])
        self.assertIn("HEVC", report.results[1].error)
        self.assertFalse(plan.items[1].output.exists())

    def test_io_error_does_not_stop_the_next_file(self):
        self.video("01.mp4")
        self.video("02.mp4")
        plan = plan_batch(self.source, self.output)
        with patch("batch.build_package", side_effect=[OSError("Disco pieno"), plan.items[1].output]):
            report = run_batch(plan)
        self.assertEqual([row.status for row in report.results], ["failed", "created"])
        self.assertIn("Disco pieno", report.results[0].error)

    def test_cancellation_preserves_finished_packages_and_records_remaining(self):
        for name in ("01.mp4", "02.mp4", "03.mp4"):
            self.video(name)
        plan = plan_batch(self.source, self.output)
        cancel = threading.Event()
        report = run_batch(plan, cancel=cancel, progress=lambda *_: cancel.set())
        self.assertEqual([row.status for row in report.results], ["created", "cancelled", "cancelled"])
        self.assertTrue(plan.items[0].output.exists())
        self.assertFalse(plan.items[1].output.exists())
        self.assertEqual(report.summary()["cancelled"], 2)

    def test_cancelled_scan_creates_nothing(self):
        self.video("01.mp4")
        self.video("02.mp4")
        cancel = threading.Event()
        with self.assertRaises(BatchCancelled):
            plan_batch(self.source, self.output, cancel=cancel, progress=lambda *_: cancel.set())
        self.assertFalse(self.output.exists())

    def test_symlinked_inputs_are_ignored(self):
        self.video("actual.mp4")
        external = self.root / "outside.mp4"
        external.write_bytes(b"external")
        (self.source / "link.mp4").symlink_to(external)
        plan = plan_batch(self.source, self.output)
        self.assertEqual([item.video.name for item in plan.items], ["actual.mp4"])

    def test_output_symlink_cannot_escape_destination(self):
        self.video("Modulo/Lezione.mp4")
        self.output.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        (self.output / "Modulo").symlink_to(outside, target_is_directory=True)
        plan = plan_batch(self.source, self.output, recursive=True)
        with self.assertRaises(BuildError):
            run_batch(plan)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(list(self.output.glob("*.csv")), [])

    def test_duplicate_or_invalid_plan_is_rejected(self):
        self.video("Lezione.mp4")
        plan = plan_batch(self.source, self.output)
        for invalid in (replace(plan, items=plan.items * 2), replace(plan, items=())):
            with self.assertRaises(BuildError):
                run_batch(invalid)
        self.assertFalse(self.output.exists())
        with self.assertRaises(BuildError):
            run_batch(plan, checkpoint=3)

    def test_output_aliases_cannot_target_the_same_physical_zip(self):
        self.video("A/Lezione.mp4")
        self.video("B/Lezione.mp4")
        (self.output / "A").mkdir(parents=True)
        (self.output / "B").symlink_to(self.output / "A", target_is_directory=True)
        plan = plan_batch(self.source, self.output, recursive=True)
        with self.assertRaises(BuildError):
            run_batch(plan)
        self.assertEqual(list(self.output.rglob("*.zip")), [])
        self.assertEqual(list(self.output.glob("*.csv")), [])

    def test_csv_is_utf8_excel_readable_and_formula_safe(self):
        self.video("Lezione.mp4")
        plan = plan_batch(self.source, self.output)
        item = replace(plan.items[0], title="=Titolo è")
        report = run_batch(replace(plan, items=(item,)))
        self.assertTrue(report.path.read_bytes().startswith(b"\xef\xbb\xbf"))
        with report.path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter=";"))
        self.assertEqual(rows[0]["Titolo"], "'=Titolo è")
        self.assertEqual(rows[0]["Esito"], "Creato")
        self.assertEqual(rows[0]["Video"], str(item.video))
        self.assertEqual(list(self.output.glob(".scorm-build-*")), [])


class BatchIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffprobe"), "ffprobe non disponibile")
    def test_real_videos_invalid_file_and_repeat_run(self):
        sample = Path(__file__).parent / "build/installer/staging/app/sample.mp4"
        if not sample.exists():
            self.skipTest("Video campione del build non disponibile")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, destination = root / "input", root / "output"
            (source / "Modulo").mkdir(parents=True)
            shutil.copyfile(sample, source / "prima.mp4")
            shutil.copyfile(sample, source / "Modulo/seconda.MP4")
            (source / "nonvalido.mp4").write_bytes(b"not a video")
            command = [sys.executable, str(Path(__file__).parent / "batch.py"),
                       str(source), str(destination), "--recursive", "--checkpoint", "15"]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 1, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["created"], 2)
            self.assertEqual(summary["failed"], 1)
            for output in (destination / "prima_scorm.zip", destination / "Modulo/seconda_scorm.zip"):
                with zipfile.ZipFile(output) as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertEqual(json.loads(archive.read("config.json"))["title"], "Video di prova")
            hashes = {path: path.read_bytes() for path in destination.rglob("*.zip")}
            repeated = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(json.loads(repeated.stdout)["skipped"], 2)
            self.assertEqual(json.loads(repeated.stdout)["created"], 0)
            self.assertEqual(hashes, {path: path.read_bytes() for path in destination.rglob("*.zip")})


if __name__ == "__main__":
    unittest.main()
