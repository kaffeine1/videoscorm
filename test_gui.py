from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile
import json
import os

try:
    from gui import BuilderWindow
except ImportError:
    BuilderWindow = None


@unittest.skipUnless(os.environ.get("VIDEOSCORM_GUI_TESTS") == "1" and BuilderWindow is not None
                     and shutil.which("ffprobe"), "Abilitare VIDEOSCORM_GUI_TESTS=1 con Tk e un desktop disponibile")
class GuiTests(unittest.TestCase):
    def setUp(self):
        sample = Path(__file__).parent / "build/installer/staging/app/sample.mp4"
        if not sample.exists():
            self.skipTest("Video campione del build non disponibile")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "input"
        self.source.mkdir()
        self.destination = self.root / "output"
        for name in ("uno.mp4", "due.MP4"):
            shutil.copyfile(sample, self.source / name)
        self.window = BuilderWindow()
        self.window.withdraw()
        self.addCleanup(self.close_window)
        self.callback_errors = []
        self.window.report_callback_exception = lambda *args: self.callback_errors.append(args)
        self.window.batch_source.set(str(self.source))
        self.window.batch_output.set(str(self.destination))
        self.dialogs = {}
        for method in ("showinfo", "showerror", "showwarning", "askyesno"):
            mocked = patch(f"gui.messagebox.{method}", return_value=True)
            self.dialogs[method] = mocked.start()
            self.addCleanup(mocked.stop)

    def close_window(self):
        if not self.window._closing:
            self.window._close()

    def wait_idle(self):
        deadline = time.monotonic() + 10
        while self.window._busy and time.monotonic() < deadline:
            self.window.update()
            time.sleep(0.005)
        self.assertFalse(self.window._busy, "Operazione GUI non terminata")
        self.assertEqual(self.callback_errors, [])

    def test_direct_batch_button_creates_packages_without_preliminary_scan(self):
        self.window.build_batch()
        self.wait_idle()
        self.assertEqual(len(self.window.batch_tree.get_children()), 2)
        self.assertEqual(len(list(self.destination.glob("*_scorm.zip"))), 2)
        self.assertEqual(self.window.batch_tree.set("0", "status"), "Creato")
        self.dialogs["showinfo"].assert_called_once()
        self.assertTrue(self.window.batch_stop_button.instate(["disabled"]))

    def test_title_edit_is_used_by_batch(self):
        self.window.scan_batch()
        self.wait_idle()
        self.window.batch_tree.selection_set("0")
        with patch("gui.simpledialog.askstring", return_value="Titolo è corretto"):
            self.window.edit_batch_title()
        output = self.window.batch_plan.items[0].output
        self.window.build_batch()
        self.wait_idle()
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(json.loads(archive.read("config.json"))["title"], "Titolo è corretto")

    def test_destination_change_invalidates_the_previous_plan(self):
        self.window.scan_batch()
        self.wait_idle()
        self.assertIsNotNone(self.window.batch_plan)
        self.window.batch_output.set(str(self.root / "other"))
        self.assertIsNone(self.window.batch_plan)
        self.assertEqual(self.window.batch_tree.get_children(), ())

    def test_overwrite_requires_confirmation_and_rejection_keeps_packages(self):
        self.window.build_batch()
        self.wait_idle()
        before = {path: path.read_bytes() for path in self.destination.glob("*.zip")}
        reports = list(self.destination.glob("*.csv"))
        self.window.batch_overwrite.set(True)
        self.dialogs["askyesno"].return_value = False
        self.window.build_batch()
        self.assertFalse(self.window._busy)
        self.dialogs["askyesno"].assert_called_once()
        self.assertEqual(before, {path: path.read_bytes() for path in self.destination.glob("*.zip")})
        self.assertEqual(reports, list(self.destination.glob("*.csv")))

    def test_stop_during_scan_creates_no_packages(self):
        self.window.scan_batch()
        self.window.stop_batch()
        self.wait_idle()
        self.assertIsNone(self.window.batch_plan)
        self.assertFalse(self.destination.exists())
        self.dialogs["showerror"].assert_not_called()

    def test_close_waits_for_the_worker_and_still_processes_completion(self):
        self.window._run(lambda: time.sleep(0.15), lambda _: None, cancellable=True)
        self.window._close()
        self.wait_idle()
        self.assertTrue(self.window._closing)

    def test_invalid_video_is_reported_without_blocking_other_files(self):
        (self.source / "errore.mp4").write_bytes(b"not a video")
        self.window.build_batch()
        self.wait_idle()
        self.assertEqual(len(list(self.destination.glob("*_scorm.zip"))), 2)
        self.assertEqual(self.window.batch_tree.set("1", "status"), "Errore")
        self.dialogs["showwarning"].assert_called_once()
        self.dialogs["showerror"].assert_not_called()

    def test_controls_fit_at_minimum_and_standard_window_sizes(self):
        self.window.deiconify()
        notebook = self.window.notebook
        for dimensions in ("760x600", "900x660"):
            self.window.geometry(dimensions)
            for tab in notebook.tabs():
                notebook.select(tab)
                self.window.update()
                for control in self.window._controls:
                    if control.winfo_ismapped():
                        parent = control.master
                        self.assertGreaterEqual(control.winfo_x(), 0)
                        self.assertGreaterEqual(control.winfo_y(), 0)
                        self.assertLessEqual(control.winfo_x() + control.winfo_width(), parent.winfo_width())
                        self.assertLessEqual(control.winfo_y() + control.winfo_height(), parent.winfo_height())

    def test_h5p_batch_and_format_switch_invalidate_plan(self):
        self.window.scan_batch()
        self.wait_idle()
        self.assertIsNotNone(self.window.batch_plan)
        self.window.package_format.set("h5p")
        self.assertIsNone(self.window.batch_plan)
        self.window.build_batch()
        self.wait_idle()
        self.assertEqual(len(list(self.destination.glob("*_h5p.h5p"))), 2)
        with zipfile.ZipFile(next(self.destination.glob("*.h5p"))) as archive:
            self.assertIn("h5p.json", archive.namelist())
        self.assertFalse(list(self.destination.glob("*.zip")))

    def test_single_output_name_tracks_selected_format(self):
        self.window.output.set(str(self.root / "lesson_scorm.zip"))
        self.window.package_format.set("h5p")
        self.assertEqual(Path(self.window.output.get()).name, "lesson_h5p.h5p")
        self.window.package_format.set("scorm")
        self.assertEqual(Path(self.window.output.get()).name, "lesson_scorm.zip")


if __name__ == "__main__":
    unittest.main()
