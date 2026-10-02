# VideoSCORM 0.3.0

Create SCORM 1.2 and H5P video lessons from MP4 files, individually or in batches.
Videos are copied without re-encoding or changing the originals.

[Italiano](README.it.md) | Windows: [English](README-Windows.txt) / [Italiano](README-Windows.it.txt)

## Quick Start

Install Python 3 with Tkinter and FFmpeg (`ffprobe`), then run:

```bash
python gui.py
```

Choose SCORM 1.2 or H5P, select a video, review its title and save the package.
The title comes from video metadata or the filename. The interface is currently in Italian.
Use MP4 with H.264/yuv420p video and AAC audio, or no audio. HEVC is not supported.

## Command Line

```bash
python builder.py video.mp4 lesson_scorm.zip --title "Lesson title"
python builder.py video.mp4 lesson_h5p.h5p --format h5p --title "Lesson title"
python batch.py ./videos ./packages --recursive
python batch.py ./videos ./packages --format h5p --recursive
```

Batch mode creates one package per video and a CSV report, preserving subfolders
with `--recursive`. Existing packages are skipped unless `--force` is used.
Options: `--checkpoint 15|30|60` (seconds, default 30), `--no-resume`, `--ffprobe PATH`.
Disabling resume does not disable progress saving.

## Tracking and Moodle

- Completion requires full playback coverage. Seeking does not count as viewing.
- Position and progress are saved without a blocking resume dialog or a quiz grade.
  Closing the browser abruptly or losing connectivity can lose recent progress.
- Upload the generated lesson ZIP to a SCORM activity, or the `.h5p` file to H5P.
  **Do not upload the Windows installer archive to Moodle.**
- For SCORM, require the SCORM completed status, not just opening the activity.
- H5P includes `H5P.LumTrackedVideo 1.0` and `H5P.Video 1.6.66`. The first import
  needs permission to install H5P libraries. Enable content-state saving.
- **H5P attempt completion does not automatically complete the Moodle activity
  or unlock prerequisites.** Those rules need separate configuration or integration.

Full Windows installer and Moodle H5P workflow testing is still pending. Before
production, test playback, resume, seeking and network interruptions in a test
course and check server-side reports. This tool does not migrate existing lessons
or learner progress, and does not upload packages automatically.

## Build and Test

Windows installer target: Windows 10/11 x64. With NSIS and FFmpeg installed:

```bash
python3 build_installer.py
```

The build uses pinned, checksum-verified dependencies and writes to `dist/`.
Installers, videos and generated packages are not stored in this repository.
See the Windows instructions for installation and diagnostics.

```bash
python -m unittest test_builder.py test_batch.py test_h5p.py
node test_player.cjs
node test_h5p_player.cjs
```

Bundled H5P.Video: [third-party license and source notice](vendor/H5P-Video-NOTICE.txt).
