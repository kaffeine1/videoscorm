"""Check the bundled runtime on the target Windows computer."""

from pathlib import Path
import json
import os
import shutil
import tempfile
import traceback
import zipfile


def main() -> int:
    log_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "VideoSCORM" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "installation.log").open("w", encoding="utf-8") as log:
        try:
            from builder import build_package, inspect_video
            from batch import plan_batch, run_batch
            from gui import BuilderWindow
            root = BuilderWindow()
            root.withdraw()
            root.update_idletasks()
            root.destroy()
            log.write("Interfaccia Tk: OK\n")
            sample = Path(__file__).resolve().parent / "sample.mp4"
            info = inspect_video(sample)
            log.write(f"ffprobe e video campione: OK ({info['duration']} secondi)\n")
            with tempfile.TemporaryDirectory(prefix="videoscorm-check-") as temporary:
                output = Path(temporary) / "sample.zip"
                build_package(sample, output, title="Prova installazione")
                with zipfile.ZipFile(output) as archive:
                    config = json.loads(archive.read("config.json"))
                    if config["title"] != "Prova installazione" or archive.testzip():
                        raise RuntimeError("Verifica del pacchetto non riuscita.")
            log.write("Creazione e integrità ZIP SCORM: OK\n")
            with tempfile.TemporaryDirectory(prefix="videoh5p-check-") as temporary:
                output = Path(temporary) / "sample.h5p"
                build_package(sample, output, title="Prova H5P", package_format="h5p")
                with zipfile.ZipFile(output) as archive:
                    definition = json.loads(archive.read("h5p.json"))
                    if definition["mainLibrary"] != "H5P.LumTrackedVideo" or archive.testzip():
                        raise RuntimeError("Verifica H5P non riuscita.")
            log.write("Creazione e integrità H5P: OK\n")
            with tempfile.TemporaryDirectory(prefix="videoscorm-batch-check-") as temporary:
                source = Path(temporary) / "input"
                source.mkdir()
                shutil.copyfile(sample, source / "sample.mp4")
                for package_format in ("scorm", "h5p"):
                    plan = plan_batch(source, Path(temporary) / package_format, package_format=package_format)
                    report = run_batch(plan)
                    if report.summary()["created"] != 1 or report.summary()["failed"]:
                        raise RuntimeError(f"Verifica della creazione massiva {package_format} non riuscita.")
                    log.write(f"Creazione massiva {package_format} e report: OK\n")
        except Exception:
            traceback.print_exc(file=log)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
