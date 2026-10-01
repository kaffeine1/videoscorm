"""Plan and build one independent SCORM package per MP4 in a folder."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time
from typing import Callable
import uuid

from builder import PACKAGE_FORMATS, BuildError, build_package, find_ffprobe, inspect_video


class BatchCancelled(BuildError):
    pass


@dataclass(frozen=True)
class BatchItem:
    video: Path
    output: Path
    title: str
    error: str = ""


@dataclass(frozen=True)
class BatchPlan:
    source: Path
    destination: Path
    items: tuple[BatchItem, ...]
    package_format: str = "scorm"


@dataclass(frozen=True)
class BatchResult:
    video: str
    output: str
    title: str
    status: str
    error: str
    seconds: float


@dataclass(frozen=True)
class BatchReport:
    results: tuple[BatchResult, ...]
    path: Path

    def summary(self) -> dict:
        return {"total": len(self.results),
                **{status: sum(row.status == status for row in self.results)
                   for status in ("created", "skipped", "failed", "cancelled")},
                "report": str(self.path)}


def _contained(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root)


def _linked(path: Path) -> bool:
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def _videos(source: Path, destination: Path, recursive: bool) -> list[Path]:
    found = []

    def check(candidate):
        if (candidate.suffix.lower() == ".mp4" and not _linked(candidate)
                and candidate.is_file() and _contained(candidate, source)):
            found.append(candidate)

    if recursive:
        def on_error(error):
            raise BuildError(f"Impossibile leggere una cartella: {error}") from error

        for folder, directories, files in os.walk(source, followlinks=False, onerror=on_error):
            current = Path(folder)
            directories[:] = [name for name in directories
                              if not _linked(current / name) and _contained(current / name, source)
                              and ((current / name).resolve() != destination or destination == source)]
            for name in files:
                check(current / name)
    else:
        for candidate in source.iterdir():
            check(candidate)
    return sorted(found, key=lambda path: path.relative_to(source).as_posix().casefold())


def plan_batch(source: Path, destination: Path, *, recursive: bool = False,
               ffprobe: str | None = None, cancel: threading.Event | None = None,
               progress: Callable[[int, int, BatchItem], None] | None = None,
               package_format: str = "scorm") -> BatchPlan:
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_dir():
        raise BuildError("Seleziona una cartella di video esistente.")
    if destination.exists() and not destination.is_dir():
        raise BuildError("La destinazione dei pacchetti deve essere una cartella.")
    if package_format not in PACKAGE_FORMATS:
        raise BuildError("Formato pacchetto non valido: scegli SCORM oppure H5P.")
    videos = _videos(source, destination, recursive)
    if not videos:
        raise BuildError("Nessun video MP4 trovato nella cartella selezionata.")
    targets = []
    names = set()
    for video in videos:
        relative = video.relative_to(source)
        target = destination / relative.parent / f"{video.stem}{PACKAGE_FORMATS[package_format][0]}"
        key = target.relative_to(destination).as_posix().casefold()
        if key in names:
            raise BuildError(f"Due video produrrebbero lo stesso pacchetto su Windows: {relative}")
        names.add(key)
        targets.append(target)
    probe = find_ffprobe(ffprobe)
    items = []
    for index, (video, target) in enumerate(zip(videos, targets), start=1):
        if cancel is not None and cancel.is_set():
            raise BatchCancelled("Lettura della cartella interrotta.")
        title, error = video.stem, ""
        try:
            title = inspect_video(video, probe)["title"]
        except (BuildError, OSError) as exc:
            error = str(exc)
        item = BatchItem(video, target, title, error)
        items.append(item)
        if progress:
            progress(index, len(videos), item)
    if cancel is not None and cancel.is_set():
        raise BatchCancelled("Lettura della cartella interrotta.")
    return BatchPlan(source, destination, tuple(items), package_format)


def _csv_cell(value):
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def run_batch(plan: BatchPlan, *, checkpoint: int = 30, resume: bool = True,
              ffprobe: str | None = None, overwrite: bool = False,
              cancel: threading.Event | None = None,
              progress: Callable[[int, int, BatchResult], None] | None = None) -> BatchReport:
    if checkpoint not in (15, 30, 60):
        raise BuildError("L'intervallo di salvataggio deve essere 15, 30 o 60 secondi.")
    if not plan.items:
        raise BuildError("Il piano di creazione è vuoto.")
    if plan.package_format not in PACKAGE_FORMATS:
        raise BuildError("Formato del piano non valido.")
    # Validate the complete plan before creating folders, reports or packages.
    targets = set()
    for item in plan.items:
        if not _contained(item.video, plan.source) or not _contained(item.output, plan.destination):
            raise BuildError("Un percorso del piano esce dalle cartelle selezionate.")
        key = item.output.resolve().relative_to(plan.destination).as_posix().casefold()
        if key in targets or item.output.suffix.lower() != PACKAGE_FORMATS[plan.package_format][1] or item.output == item.video:
            raise BuildError("Il piano contiene destinazioni duplicate o non valide.")
        targets.add(key)
    plan.destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = plan.destination / f"VideoSCORM-report-{stamp}-{uuid.uuid4().hex[:8]}.csv"
    results = []
    labels = {"created": "Creato", "skipped": "Saltato: pacchetto esistente",
              "failed": "Errore", "cancelled": "Non elaborato: interrotto"}
    with report_path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(("Video", "Pacchetto", "Titolo", "Esito", "Errore", "Secondi"))
        stream.flush()
        for index, item in enumerate(plan.items, start=1):
            started = time.monotonic()
            status, error = "created", ""
            if cancel is not None and cancel.is_set():
                status = "cancelled"
            elif (item.output.exists() or item.output.is_symlink()) and not overwrite:
                status = "skipped"
            elif item.error:
                status, error = "failed", item.error
            else:
                try:
                    if not _contained(item.output, plan.destination) or not _contained(item.video, plan.source):
                        raise BuildError("Il percorso del file è cambiato dopo la lettura della cartella.")
                    item.output.parent.mkdir(parents=True, exist_ok=True)
                    build_package(item.video, item.output, title=item.title, checkpoint=checkpoint,
                                  resume=resume, ffprobe=ffprobe, overwrite=overwrite, package_format=plan.package_format)
                except Exception as exc:
                    status, error = "failed", str(exc)
            result = BatchResult(str(item.video), str(item.output), item.title, status, error,
                                 round(time.monotonic() - started, 3))
            results.append(result)
            writer.writerow([_csv_cell(value) for value in (
                result.video, result.output, result.title, labels[result.status], result.error, result.seconds)])
            stream.flush()
            if progress:
                progress(index, len(plan.items), result)
    return BatchReport(tuple(results), report_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Crea uno SCORM o H5P per ogni MP4 di una cartella.")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--force", action="store_true", help="Sostituisce gli ZIP già esistenti.")
    parser.add_argument("--checkpoint", type=int, choices=(15, 30, 60), default=30)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--ffprobe")
    parser.add_argument("--format", choices=tuple(PACKAGE_FORMATS), default="scorm")
    args = parser.parse_args()
    cancel = threading.Event()
    previous = signal.signal(signal.SIGINT, lambda *_: cancel.set())
    try:
        plan = plan_batch(args.source, args.destination, recursive=args.recursive,
                          ffprobe=args.ffprobe, cancel=cancel, package_format=args.format)
        report = run_batch(plan, checkpoint=args.checkpoint, resume=not args.no_resume,
                           ffprobe=args.ffprobe, overwrite=args.force, cancel=cancel,
                           progress=lambda index, total, row: print(
                               f"[{index}/{total}] {row.status}: {row.video}", file=sys.stderr, flush=True))
    except (BuildError, OSError) as exc:
        parser.error(str(exc))
    finally:
        signal.signal(signal.SIGINT, previous)
    summary = report.summary()
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if summary["failed"] or summary["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
