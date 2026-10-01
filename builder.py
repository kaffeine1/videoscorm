"""Build a SCORM 1.2 or H5P video package with full-playback tracking."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parent
VIDEO_NAME = "video.mp4"
ASSETS = ("index.html", "player.js", "style.css")
PACKAGE_FORMATS = {"scorm": ("_scorm.zip", ".zip"), "h5p": ("_h5p.h5p", ".h5p")}
SCORM = "http://www.imsproject.org/xsd/imscp_rootv1p1p2"
ADLCP = "http://www.adlnet.org/xsd/adlcp_rootv1p2"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
ET.register_namespace("", SCORM)
ET.register_namespace("adlcp", ADLCP)
ET.register_namespace("xsi", XSI)


class BuildError(ValueError):
    pass


def find_ffprobe(explicit: str | None = None) -> str:
    candidates = [explicit, str(ROOT / "bin" / "ffprobe.exe"), str(ROOT / "ffprobe.exe")]
    if getattr(sys, "frozen", False):
        candidates.extend([str(Path(sys.executable).parent / "ffprobe.exe"),
                           str(Path(getattr(sys, "_MEIPASS", "")) / "ffprobe.exe")])
    candidates.append(shutil.which("ffprobe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise BuildError("ffprobe non trovato. Installa FFmpeg o scegli il percorso di ffprobe.exe.")


def inspect_video(video: Path, ffprobe: str | None = None) -> dict:
    video = Path(video)
    if not video.is_file() or video.suffix.lower() != ".mp4":
        raise BuildError("Seleziona un file MP4 esistente.")
    if video.stat().st_size == 0:
        raise BuildError("Il file video è vuoto.")
    command = [find_ffprobe(ffprobe), "-v", "error", "-show_format", "-show_streams", "-of", "json", str(video)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=60, check=True,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        probe = json.loads(result.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise BuildError("Impossibile leggere i metadati del video con ffprobe.") from exc
    streams = probe.get("streams", [])
    pictures = [s for s in streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    if len(pictures) != 1 or pictures[0].get("codec_name") != "h264":
        raise BuildError("Serve un MP4 con un solo flusso video H.264 (non HEVC/H.265).")
    if pictures[0].get("pix_fmt") not in (None, "yuv420p", "yuvj420p"):
        raise BuildError("Esporta H.264 in formato pixel yuv420p per la compatibilità con i browser.")
    if any(s.get("codec_name") != "aac" for s in audio):
        raise BuildError("L'audio MP4 deve essere AAC. Esporta nuovamente il video.")
    try:
        duration = float(probe["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise BuildError("Durata video non disponibile.") from exc
    if not math.isfinite(duration) or duration < 1:
        raise BuildError("La durata video deve essere almeno un secondo.")
    tags = [probe.get("format", {}).get("tags", {})] + [s.get("tags", {}) for s in pictures]
    title = next((str(v).strip() for group in tags for k, v in group.items()
                  if k.lower() == "title" and str(v).strip()), "")
    if not title:
        title = re.sub(r"[_-]+", " ", video.stem).strip()
    return {"title": title, "duration": duration, "size": video.stat().st_size}


def _manifest(title: str) -> bytes:
    root = ET.Element(f"{{{SCORM}}}manifest", {
        "identifier": "ORG-VIDEO-SCORM-12", "version": "1.0",
        f"{{{XSI}}}schemaLocation": f"{SCORM} imscp_rootv1p1p2.xsd {ADLCP} adlcp_rootv1p2.xsd",
    })
    metadata = ET.SubElement(root, f"{{{SCORM}}}metadata")
    ET.SubElement(metadata, f"{{{SCORM}}}schema").text = "ADL SCORM"
    ET.SubElement(metadata, f"{{{SCORM}}}schemaversion").text = "1.2"
    orgs = ET.SubElement(root, f"{{{SCORM}}}organizations", {"default": "ORG-1"})
    org = ET.SubElement(orgs, f"{{{SCORM}}}organization", {"identifier": "ORG-1"})
    ET.SubElement(org, f"{{{SCORM}}}title").text = title
    item = ET.SubElement(org, f"{{{SCORM}}}item", {"identifier": "ITEM-1", "identifierref": "RES-1"})
    ET.SubElement(item, f"{{{SCORM}}}title").text = title
    resources = ET.SubElement(root, f"{{{SCORM}}}resources")
    resource = ET.SubElement(resources, f"{{{SCORM}}}resource", {
        "identifier": "RES-1", "type": "webcontent", f"{{{ADLCP}}}scormtype": "sco", "href": "index.html",
    })
    for filename in (*ASSETS, "config.json", VIDEO_NAME):
        ET.SubElement(resource, f"{{{SCORM}}}file", {"href": filename})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def build_package(video: Path, output: Path, *, title: str | None = None,
                  checkpoint: int = 30, resume: bool = True, ffprobe: str | None = None,
                  overwrite: bool = False, package_format: str = "scorm") -> Path:
    video, output = Path(video).resolve(), Path(output).resolve()
    info = inspect_video(video, ffprobe)
    title = (title if title is not None else info["title"]).strip()
    if not title or len(title) > 200 or any(ord(ch) < 32 for ch in title):
        raise BuildError("Il titolo deve contenere da 1 a 200 caratteri stampabili.")
    if checkpoint not in (15, 30, 60):
        raise BuildError("L'intervallo di salvataggio deve essere 15, 30 o 60 secondi.")
    if package_format not in PACKAGE_FORMATS:
        raise BuildError("Formato pacchetto non valido: scegli SCORM oppure H5P.")
    if output.suffix.lower() != PACKAGE_FORMATS[package_format][1] or output == video:
        raise BuildError(f"La destinazione deve essere un file {PACKAGE_FORMATS[package_format][1]} distinto dal video.")
    if not output.parent.is_dir():
        raise BuildError("La cartella di destinazione non esiste.")
    if output.exists() and not overwrite:
        raise BuildError("Il pacchetto esiste già. Scegli un altro nome o conferma la sostituzione.")
    config = {"title": title, "duration": info["duration"], "checkpointSeconds": checkpoint,
              "resume": bool(resume), "version": 1}
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".scorm-build-", suffix=".zip", dir=output.parent, delete=False) as temp:
            temp_name = temp.name
        with zipfile.ZipFile(temp_name, "w", allowZip64=True) as archive:
            if package_format == "h5p":
                _write_h5p(archive, video, config)
            else:
                archive.writestr("imsmanifest.xml", _manifest(title), compress_type=zipfile.ZIP_DEFLATED)
                archive.writestr("config.json", json.dumps(config, ensure_ascii=False).encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
                for asset in ASSETS:
                    archive.write(ROOT / asset, asset, compress_type=zipfile.ZIP_DEFLATED)
                archive.write(video, VIDEO_NAME, compress_type=zipfile.ZIP_STORED)
        with zipfile.ZipFile(temp_name) as archive:
            if archive.testzip() is not None:
                raise BuildError("Il pacchetto ZIP non ha superato la verifica di integrità.")
        os.replace(temp_name, output)
        temp_name = None
        return output
    finally:
        if temp_name and Path(temp_name).exists():
            Path(temp_name).unlink()


def _write_h5p(archive: zipfile.ZipFile, video: Path, config: dict) -> None:
    libraries = (ROOT / "h5p" / "H5P.LumTrackedVideo-1.0", ROOT / "vendor" / "H5P.Video-1.6")
    dependencies = []
    for folder in libraries:
        if not (folder / "library.json").is_file():
            raise BuildError("Librerie H5P mancanti. Reinstalla il programma.")
        library = json.loads((folder / "library.json").read_text(encoding="utf-8"))
        if library.get("coreApi", {}).get("minorVersion", 0) > 27:
            raise BuildError("Libreria H5P non compatibile con Moodle 4.5/API 1.27.")
        dependencies.append({key: library[key] for key in ("machineName", "majorVersion", "minorVersion")})
        for asset in (*library.get("preloadedJs", []), *library.get("preloadedCss", [])):
            if not (folder / asset["path"]).is_file():
                raise BuildError(f"Libreria H5P incompleta: {asset['path']}")
        for path in sorted(folder.rglob("*")):
            relative = path.relative_to(folder)
            if (path.is_file() and not any(part.startswith(".") for part in relative.parts)
                    and path.suffix.lower() in (".json", ".js", ".css", ".svg", ".png", ".woff", ".woff2", ".ttf")):
                archive.write(path, f"{folder.name}/{relative.as_posix()}", compress_type=zipfile.ZIP_DEFLATED)
    definition = {"title": config["title"], "language": "it", "mainLibrary": "H5P.LumTrackedVideo",
                  "embedTypes": ["iframe"], "license": "U", "preloadedDependencies": dependencies}
    params = {"lessonTitle": config["title"], "duration": config["duration"],
              "video": [{"path": "videos/video.mp4", "mime": "video/mp4"}],
              "checkpointSeconds": str(config["checkpointSeconds"]), "resume": config["resume"]}
    archive.writestr("h5p.json", json.dumps(definition, ensure_ascii=False).encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
    archive.writestr("content/content.json", json.dumps(params, ensure_ascii=False).encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
    archive.write(ROOT / "vendor" / "H5P-Video-NOTICE.txt", "H5P.Video-1.6/LICENSE.txt", compress_type=zipfile.ZIP_DEFLATED)
    archive.write(video, "content/videos/video.mp4", compress_type=zipfile.ZIP_STORED)


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera un pacchetto video SCORM 1.2 o H5P senza voto.")
    parser.add_argument("video", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--title")
    parser.add_argument("--checkpoint", type=int, choices=(15, 30, 60), default=30)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--ffprobe")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--format", choices=tuple(PACKAGE_FORMATS), default="scorm")
    args = parser.parse_args()
    try:
        path = build_package(args.video, args.output, title=args.title, checkpoint=args.checkpoint,
                             resume=not args.no_resume, ffprobe=args.ffprobe, overwrite=args.force, package_format=args.format)
    except BuildError as exc:
        parser.error(str(exc))
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
