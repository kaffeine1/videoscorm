VideoSCORM 0.3.0 - Windows 10/11 x64
Italian instructions: README-Windows.it.txt

INSTALL
Download the installer from:
https://github.com/kaffeine1/videoscorm/releases/tag/v0.3.0
For a local build, follow README.md.
Extract VideoSCORM-0.3.0-Windows.zip and run VideoSCORM-0.3.0-Setup-x64.exe.
Python and ffprobe are included. Launch "Video SCORM" from the desktop or Start.
The interface and installer messages are currently in Italian.
Setup updates an existing installation without changing source videos or
packages saved outside the application folder.
Do not upload the Windows installer archive to Moodle: it is not a lesson.

CREATE A LESSON
1. Choose SCORM 1.2 or H5P and select an MP4 video (H.264/yuv420p, AAC or no audio).
   A sample video is available at app\sample.mp4 in the installation folder.
2. Review the suggested title and choose the output file.
3. Click "Crea pacchetto" to create the lesson.
4. Upload the lesson ZIP to a Moodle SCORM activity, or the .h5p file to H5P.
   Test in a separate course before production use.

BATCH MODE
Open "Cartella", choose the MP4 folder and output folder, then click "Crea tutti".
Use "Leggi cartella" to review titles first, and "Modifica titolo" to edit them.
"Includi sottocartelle" preserves the folder structure.
Existing packages are skipped unless replacement is explicitly confirmed.
"Interrompi" finishes the current file and stops. A CSV report records results.

TRACKING
Completion requires full playback coverage; seeking does not count as viewing.
Progress and position are saved, but abrupt closure or network loss can lose
recent progress. Video playback does not assign a quiz grade.
For SCORM, require the completed status rather than simply opening the activity.
H5P imports include a custom library and need permission to install libraries.
Enable H5P content-state saving. H5P attempt completion alone does not complete
the Moodle activity or unlock prerequisites; configure those rules separately.
Full Windows installer and Moodle H5P workflow testing is still pending.
The program does not migrate existing lessons or learner progress.

DIAGNOSTICS
Logs: %LOCALAPPDATA%\VideoSCORM\logs\installation.log and app.log.
Uninstall through Windows app settings. Videos and packages stored outside the
application folder are preserved.
