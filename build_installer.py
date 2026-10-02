"""Cross-build an offline Windows installer with a private Python runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parent
VERSION = "0.3.0"
APP_FILES = ("builder.py", "batch.py", "gui.py", "launch.pyw", "selfcheck.py", "index.html",
             "player.js", "style.css", "README-Windows.txt", "README-Windows.it.txt")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def download(dependency: dict, cache: Path) -> Path:
    path = cache / dependency["filename"]
    if not path.exists() or digest(path) != dependency["sha256"]:
        partial = path.with_suffix(path.suffix + ".partial")
        print(f"Download: {dependency['filename']}", flush=True)
        request = urllib.request.Request(dependency["url"], headers={"User-Agent": "VideoSCORM-installer-build/0.1"})
        with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as target:
            shutil.copyfileobj(response, target)
        if digest(partial) != dependency["sha256"]:
            partial.unlink()
            raise RuntimeError(f"Checksum non valido: {dependency['filename']}")
        partial.replace(path)
    print(f"SHA-256 verificato: {dependency['filename']}", flush=True)
    return path


def prepare(build: Path, dependencies: dict) -> Path:
    cache = build / "downloads"
    cache.mkdir(parents=True, exist_ok=True)
    python_archive = download(dependencies["python"], cache)
    ffmpeg_archive = download(dependencies["ffprobe"], cache)
    staging = build / "staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    unpacked = build / "python-unpacked"
    if unpacked.exists():
        shutil.rmtree(unpacked)
    unpacked.mkdir()
    with tarfile.open(python_archive) as archive:
        archive.extractall(unpacked, filter="data")
    python_root = unpacked / "python"
    for executable in ("python.exe", "pythonw.exe"):
        if not (python_root / executable).is_file():
            raise RuntimeError(f"Runtime incompleto: manca {executable}")
    if not list(python_root.rglob("_tkinter.pyd")):
        raise RuntimeError("Runtime incompleto: manca il modulo Tkinter.")
    if not list(python_root.rglob("tcl*.dll")) or not list(python_root.rglob("tk*.dll")):
        raise RuntimeError("Runtime incompleto: mancano le librerie Tcl/Tk.")
    shutil.copytree(python_root, staging / "runtime")
    app = staging / "app"
    app.mkdir()
    for filename in APP_FILES:
        shutil.copy2(ROOT / filename, app / filename)
    shutil.copytree(ROOT / "h5p", app / "h5p")
    shutil.copytree(ROOT / "vendor", app / "vendor", ignore=shutil.ignore_patterns(".git", ".github", "__pycache__"))
    (app / "bin").mkdir()
    (app / "licenses").mkdir()
    with zipfile.ZipFile(ffmpeg_archive) as archive:
        def copy_member(suffix: str, target: Path):
            matches = [name for name in archive.namelist() if name.endswith(suffix)]
            if len(matches) != 1:
                raise RuntimeError(f"Archivio FFmpeg inatteso: {suffix}")
            with archive.open(matches[0]) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
        copy_member("/bin/ffprobe.exe", app / "bin" / "ffprobe.exe")
        copy_member("/LICENSE", app / "licenses" / "FFmpeg-LICENSE.txt")
        copy_member("/README.txt", app / "licenses" / "FFmpeg-README.txt")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Serve ffmpeg sul computer di build per generare il video campione.")
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=320x180:rate=25", "-t", "4", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-metadata", "title=Video di prova",
                    "-movflags", "+faststart", str(app / "sample.mp4")], check=True)
    info = {"application": "VideoSCORM", "version": VERSION, "target": "Windows 10/11 x64",
            "dependencies": dependencies,
            "files": {str(path.relative_to(staging)).replace("\\", "/"): digest(path)
                      for path in sorted(staging.rglob("*")) if path.is_file()}}
    (staging / "build-info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    return staging


def main() -> int:
    parser = argparse.ArgumentParser(description="Compila il Setup.exe Windows offline con NSIS.")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    dependencies = json.loads((ROOT / "installer_dependencies.json").read_text(encoding="utf-8"))
    staging = prepare(ROOT / "build" / "installer", dependencies)
    if args.prepare_only:
        print(staging)
        return 0
    compiler = shutil.which("makensis")
    if not compiler:
        raise RuntimeError("Compilatore NSIS (makensis) non trovato.")
    output_dir = ROOT / "dist"
    output_dir.mkdir(exist_ok=True)
    output = output_dir / f"VideoSCORM-{VERSION}-Setup-x64.exe"
    subprocess.run([compiler, "-INPUTCHARSET", "UTF8", "-WX", "-V2",
                    f"-DSTAGING={staging}", f"-DOUTPUT={output}",
                    str(ROOT / "windows_installer.nsi")], check=True)
    checksum = digest(output)
    output.with_suffix(".exe.sha256").write_text(f"{checksum}  {output.name}\n", encoding="ascii")
    portable = output_dir / f"VideoSCORM-{VERSION}-Windows.zip"
    with zipfile.ZipFile(portable, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(output, output.name, compress_type=zipfile.ZIP_STORED)
        archive.write(output.with_suffix(".exe.sha256"), output.name + ".sha256")
        archive.write(ROOT / "README-Windows.txt", "README.txt")
        archive.write(ROOT / "README-Windows.it.txt", "LEGGIMI.txt")
    print(f"Installer: {output}\nDimensione: {output.stat().st_size / 1024 / 1024:.1f} MiB\nSHA-256: {checksum}\nPacchetto: {portable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
