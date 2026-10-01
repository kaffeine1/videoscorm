"""Desktop entry point with a persistent log for installation troubleshooting."""

from pathlib import Path
import ctypes
import os
import sys
import traceback


def main():
    log_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "VideoSCORM" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "app.log").open("a", encoding="utf-8", buffering=1) as log:
        sys.stdout = sys.stderr = log
        try:
            from gui import BuilderWindow
            window = BuilderWindow()
            window.mainloop()
        except Exception:
            traceback.print_exc()
            ctypes.windll.user32.MessageBoxW(
                None, f"Avvio non riuscito. Il dettaglio è nel file:\n{log_dir / 'app.log'}",
                "Video SCORM", 0x10)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
