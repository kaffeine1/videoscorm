"""Windows desktop front-end for the video SCORM package builder."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from batch import BatchCancelled, plan_batch, run_batch
from builder import PACKAGE_FORMATS, build_package, inspect_video


class BuilderWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Video SCORM / H5P 0.3.0")
        self.geometry("900x660")
        self.minsize(760, 600)
        self.video = tk.StringVar()
        self.title_text = tk.StringVar()
        self.output = tk.StringVar()
        self.ffprobe = tk.StringVar()
        self.checkpoint = tk.StringVar(value="30")
        self.resume = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Seleziona un video MP4.")
        self._busy = False
        self._closing = False
        self._events = queue.SimpleQueue()
        self._cancel = threading.Event()
        self._controls = []
        self.batch_plan = None
        self.batch_source = tk.StringVar()
        self.batch_output = tk.StringVar()
        self.batch_recursive = tk.BooleanVar(value=False)
        self.batch_overwrite = tk.BooleanVar(value=False)
        self.batch_checkpoint = tk.StringVar(value="30")
        self.batch_resume = tk.BooleanVar(value=True)
        self.batch_status = tk.StringVar(value="")
        self.package_format = tk.StringVar(value="scorm")
        formats = ttk.Frame(self)
        formats.pack(fill="x", padx=24, pady=(12, 0))
        ttk.Label(formats, text="Formato").pack(side="left", padx=(0, 16))
        ttk.Radiobutton(formats, text="SCORM 1.2", value="scorm", variable=self.package_format).pack(side="left")
        ttk.Radiobutton(formats, text="H5P", value="h5p", variable=self.package_format).pack(side="left", padx=16)
        notebook = ttk.Notebook(self)
        self.notebook = notebook
        notebook.pack(fill="both", expand=True, padx=12, pady=12)
        single = ttk.Frame(notebook)
        batch = ttk.Frame(notebook)
        notebook.add(single, text="Video singolo")
        notebook.add(batch, text="Cartella")
        self._single_widgets(single)
        self._batch_widgets(batch)
        self._collect_controls(formats)
        for parent in (single, batch):
            self._collect_controls(parent)
        for variable in (self.batch_source, self.batch_output, self.batch_recursive, self.ffprobe):
            variable.trace_add("write", self._invalidate_batch)
        self.package_format.trace_add("write", self._format_changed)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(60, self._poll_events)

    def _single_widgets(self, parent):
        parent.columnconfigure(1, weight=1)
        pad = {"padx": 12, "pady": 8}

        ttk.Label(parent, text="Video MP4").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(parent, textvariable=self.video, state="readonly").grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(parent, text="Sfoglia...", command=self.choose_video).grid(row=0, column=2, **pad)
        ttk.Label(parent, text="Titolo della lezione").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(parent, textvariable=self.title_text).grid(row=1, column=1, columnspan=2, sticky="ew", **pad)
        self.output_label = ttk.Label(parent, text="Pacchetto ZIP")
        self.output_label.grid(row=2, column=0, sticky="w", **pad)
        ttk.Entry(parent, textvariable=self.output).grid(row=2, column=1, sticky="ew", **pad)
        ttk.Button(parent, text="Sfoglia...", command=self.choose_output).grid(row=2, column=2, **pad)
        ttk.Label(parent, text="Salvataggio (secondi)").grid(row=3, column=0, sticky="w", **pad)
        ttk.Combobox(parent, textvariable=self.checkpoint, values=("15", "30", "60"), state="readonly", width=10).grid(row=3, column=1, sticky="w", **pad)
        ttk.Checkbutton(parent, text="Ripresa automatica", variable=self.resume).grid(row=4, column=0, columnspan=3, sticky="w", **pad)
        ttk.Label(parent, text="ffprobe.exe (opzionale)").grid(row=5, column=0, columnspan=3, sticky="w", **pad)
        ttk.Entry(parent, textvariable=self.ffprobe).grid(row=6, column=0, columnspan=2, sticky="ew", **pad)
        ttk.Button(parent, text="Sfoglia...", command=self.choose_ffprobe).grid(row=6, column=2, **pad)
        ttk.Separator(parent).grid(row=7, column=0, columnspan=3, sticky="ew", padx=12, pady=10)
        ttk.Label(parent, textvariable=self.status, wraplength=650).grid(row=8, column=0, columnspan=3, sticky="w", **pad)
        self.progress = ttk.Progressbar(parent, mode="indeterminate")
        self.progress.grid(row=9, column=0, columnspan=2, sticky="ew", **pad)
        self.build_button = ttk.Button(parent, text="Crea pacchetto", command=self.build)
        self.build_button.grid(row=9, column=2, sticky="e", **pad)

    def _batch_widgets(self, parent):
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(4, weight=1)
        pad = {"padx": 10, "pady": 6}
        ttk.Label(parent, text="Cartella MP4").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(parent, textvariable=self.batch_source, state="readonly").grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(parent, text="Sfoglia...", command=self.choose_batch_source).grid(row=0, column=2, **pad)
        ttk.Label(parent, text="Cartella pacchetti").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(parent, textvariable=self.batch_output, state="readonly").grid(row=1, column=1, sticky="ew", **pad)
        ttk.Button(parent, text="Sfoglia...", command=self.choose_batch_output).grid(row=1, column=2, **pad)
        options = ttk.Frame(parent)
        options.grid(row=2, column=0, columnspan=3, sticky="ew", **pad)
        ttk.Checkbutton(options, text="Includi sottocartelle", variable=self.batch_recursive).pack(side="left")
        ttk.Checkbutton(options, text="Sostituisci pacchetti esistenti", variable=self.batch_overwrite).pack(side="left", padx=16)
        settings = ttk.Frame(parent)
        settings.grid(row=3, column=0, columnspan=3, sticky="ew", **pad)
        ttk.Label(settings, text="Salvataggio (secondi)").pack(side="left")
        ttk.Combobox(settings, textvariable=self.batch_checkpoint, values=("15", "30", "60"),
                     state="readonly", width=5).pack(side="left", padx=8)
        ttk.Checkbutton(settings, text="Ripresa automatica", variable=self.batch_resume).pack(side="left", padx=12)
        table = ttk.Frame(parent)
        table.grid(row=4, column=0, columnspan=3, sticky="nsew", **pad)
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self.batch_tree = ttk.Treeview(table, columns=("video", "title", "status"), show="headings", selectmode="browse")
        for column, label, width in (("video", "Video", 240), ("title", "Titolo", 280), ("status", "Esito", 150)):
            self.batch_tree.heading(column, text=label)
            self.batch_tree.column(column, width=width, minwidth=100)
        self.batch_tree.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(table, orient="vertical", command=self.batch_tree.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self.batch_tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.batch_tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.batch_tree.bind("<Double-1>", lambda _: self.edit_batch_title())
        actions = ttk.Frame(parent)
        actions.grid(row=5, column=0, columnspan=3, sticky="ew", **pad)
        ttk.Button(actions, text="Leggi cartella", command=self.scan_batch).pack(side="left")
        ttk.Button(actions, text="Modifica titolo", command=self.edit_batch_title).pack(side="left", padx=8)
        self.batch_stop_button = ttk.Button(actions, text="Interrompi", command=self.stop_batch, state="disabled")
        self.batch_stop_button.pack(side="right")
        ttk.Button(actions, text="Crea tutti", command=self.build_batch).pack(side="right", padx=8)
        self.batch_progress = ttk.Progressbar(parent, mode="determinate")
        self.batch_progress.grid(row=6, column=0, columnspan=3, sticky="ew", **pad)
        ttk.Label(parent, textvariable=self.batch_status, wraplength=650).grid(row=7, column=0, columnspan=3, sticky="w", **pad)

    def _collect_controls(self, parent):
        for child in parent.winfo_children():
            if isinstance(child, (ttk.Button, ttk.Entry, ttk.Combobox, ttk.Checkbutton, ttk.Radiobutton)):
                if child is not self.batch_stop_button:
                    self._controls.append(child)
            self._collect_controls(child)

    def _poll_events(self):
        try:
            while True:
                callback, args = self._events.get_nowait()
                callback(*args)
        except queue.Empty:
            pass
        finally:
            if self._busy or not self._closing:
                self.after(60, self._poll_events)

    def _run(self, task, completed, *, cancellable=False):
        if self._busy:
            return
        self._busy = True
        self._cancel.clear()
        for control in self._controls:
            control.state(["disabled"])
        self.batch_stop_button.state(["!disabled"] if cancellable else ["disabled"])
        self.progress.start(12)

        def worker():
            try:
                result, error = task(), None
            except Exception as exc:
                result, error = None, exc
            self._events.put((finish, (result, error)))

        def finish(result, error):
            self._busy = False
            for control in self._controls:
                control.state(["!disabled"])
            self.batch_stop_button.state(["disabled"])
            self.progress.stop()
            if self._closing:
                self.destroy()
                return
            if isinstance(error, BatchCancelled):
                self.batch_status.set(str(error))
            elif error:
                self.status.set(str(error))
                self.batch_status.set(str(error))
                messagebox.showerror("Video SCORM", str(error))
            else:
                completed(result)

        threading.Thread(target=worker, daemon=True).start()

    def _close(self):
        if not self._busy:
            self._closing = True
            self.destroy()
        elif messagebox.askyesno("Video SCORM", "Interrompere dopo il file in corso e chiudere?"):
            self._closing = True
            self._cancel.set()
            self.batch_status.set("Chiusura al termine del file in corso...")

    def _invalidate_batch(self, *_):
        if not self._busy:
            self.batch_plan = None
            self.batch_tree.delete(*self.batch_tree.get_children())
            self.batch_status.set("")

    def choose_batch_source(self):
        if self._busy:
            return
        folder = filedialog.askdirectory(title="Cartella dei video MP4")
        if folder:
            self.batch_source.set(folder)
            self.batch_output.set(str(Path(folder) / "Pacchetti"))

    def _format_changed(self, *_):
        self._invalidate_batch()
        extension = PACKAGE_FORMATS[self.package_format.get()][1]
        self.output_label.configure(text="Pacchetto H5P" if extension == ".h5p" else "Pacchetto ZIP")
        if self.output.get():
            path = Path(self.output.get())
            for suffix, _ in PACKAGE_FORMATS.values():
                if path.name.endswith(suffix):
                    self.output.set(str(path.with_name(path.name[:-len(suffix)] + PACKAGE_FORMATS[self.package_format.get()][0])))
                    break
            else:
                self.output.set(str(path.with_suffix(extension)))

    def choose_batch_output(self):
        if self._busy:
            return
        folder = filedialog.askdirectory(title="Cartella dei pacchetti")
        if folder:
            self.batch_output.set(folder)

    def _scan_progress(self, index, total, item):
        self.batch_progress.configure(maximum=total, value=index)
        relative = item.video.relative_to(Path(self.batch_source.get()).resolve())
        self.batch_tree.insert("", "end", iid=str(index - 1), values=(
            str(relative), item.title, "Non valido" if item.error else "Pronto"))
        self.batch_status.set(f"Lettura video {index} di {total}: {relative}")

    def scan_batch(self, *, start_after=False):
        if self._busy:
            return
        if not self.batch_source.get() or not self.batch_output.get():
            messagebox.showerror("Video SCORM", "Seleziona le cartelle dei video e dei pacchetti.")
            return
        self.batch_plan = None
        self.batch_tree.delete(*self.batch_tree.get_children())
        source, destination = Path(self.batch_source.get()), Path(self.batch_output.get())
        recursive, probe = self.batch_recursive.get(), self.ffprobe.get().strip() or None
        package_format = self.package_format.get()
        self.batch_status.set("Lettura dei video in corso...")

        def completed(plan):
            self.batch_plan = plan
            errors = sum(bool(item.error) for item in plan.items)
            self.batch_status.set(f"Video trovati: {len(plan.items)}. Non validi: {errors}.")
            if start_after:
                self.build_batch()

        self._run(lambda: plan_batch(source, destination, recursive=recursive, ffprobe=probe,
                                    cancel=self._cancel, package_format=package_format,
                                    progress=lambda *args: self._events.put((self._scan_progress, args))),
                  completed, cancellable=True)

    def edit_batch_title(self):
        if self._busy or self.batch_plan is None:
            return
        selection = self.batch_tree.selection()
        if not selection:
            return
        index = int(selection[0])
        item = self.batch_plan.items[index]
        title = simpledialog.askstring("Titolo della lezione", str(item.video.name), initialvalue=item.title, parent=self)
        if title is not None:
            title = title.strip()
            if not title or len(title) > 200 or any(ord(character) < 32 for character in title):
                messagebox.showerror("Video SCORM", "Il titolo deve contenere da 1 a 200 caratteri stampabili.")
                return
            items = list(self.batch_plan.items)
            items[index] = replace(item, title=title)
            self.batch_plan = replace(self.batch_plan, items=tuple(items))
            self.batch_tree.set(selection[0], "title", title)

    def _build_progress(self, index, total, row):
        labels = {"created": "Creato", "skipped": "Pacchetto esistente", "failed": "Errore", "cancelled": "Interrotto"}
        self.batch_tree.set(str(index - 1), "status", labels[row.status])
        self.batch_progress.configure(maximum=total, value=index)
        self.batch_status.set(f"Elaborati {index} di {total}: {Path(row.video).name}")

    def build_batch(self):
        if self._busy:
            return
        if self.batch_plan is None:
            self.scan_batch(start_after=True)
            return
        plan, overwrite = self.batch_plan, self.batch_overwrite.get()
        existing = sum(item.output.exists() or item.output.is_symlink() for item in plan.items)
        if overwrite and existing and not messagebox.askyesno(
                "Sostituire i pacchetti?", f"Saranno sostituiti {existing} pacchetti già esistenti. Continuare?"):
            return
        checkpoint, resume = int(self.batch_checkpoint.get()), self.batch_resume.get()
        probe = self.ffprobe.get().strip() or None
        self.batch_progress.configure(maximum=len(plan.items), value=0)
        self.batch_status.set("Creazione dei pacchetti in corso...")

        def completed(report):
            summary = report.summary()
            text = (f"Creati: {summary['created']}. Saltati: {summary['skipped']}. "
                    f"Errori: {summary['failed']}. Interrotti: {summary['cancelled']}.")
            self.batch_status.set(text)
            notify = messagebox.showwarning if summary["failed"] or summary["cancelled"] else messagebox.showinfo
            notify("Creazione massiva", f"{text}\n\nReport:\n{report.path}")

        self._run(lambda: run_batch(plan, checkpoint=checkpoint, resume=resume, ffprobe=probe,
                                   overwrite=overwrite, cancel=self._cancel,
                                   progress=lambda *args: self._events.put((self._build_progress, args))),
                  completed, cancellable=True)

    def stop_batch(self):
        if self._busy:
            self._cancel.set()
            self.batch_stop_button.state(["disabled"])
            self.batch_status.set("Interruzione al termine del file in corso...")

    def choose_video(self):
        if self._busy:
            return
        name = filedialog.askopenfilename(title="Seleziona video", filetypes=[("Video MP4", "*.mp4")])
        if not name:
            return
        self.video.set(name)
        self.output.set(str(Path(name).with_name(Path(name).stem + PACKAGE_FORMATS[self.package_format.get()][0])))
        self.status.set("Lettura dei metadati del video...")
        selected_probe = self.ffprobe.get().strip() or None
        self._run(lambda: inspect_video(Path(name), selected_probe),
                  lambda info: (self.title_text.set(info["title"]),
                                self.status.set(f"Durata: {info['duration'] / 60:.1f} minuti.")))

    def choose_output(self):
        if self._busy:
            return
        extension = PACKAGE_FORMATS[self.package_format.get()][1]
        name = filedialog.asksaveasfilename(title="Salva pacchetto", defaultextension=extension,
                                          filetypes=[("Pacchetto H5P" if extension == ".h5p" else "Pacchetto SCORM", "*" + extension)])
        if name:
            self.output.set(name)

    def choose_ffprobe(self):
        if self._busy:
            return
        name = filedialog.askopenfilename(title="Seleziona ffprobe.exe", filetypes=[("Eseguibile ffprobe", "ffprobe.exe"), ("Tutti", "*")])
        if name:
            self.ffprobe.set(name)

    def build(self):
        video, output = Path(self.video.get()), Path(self.output.get())
        if not self.video.get() or not self.output.get():
            messagebox.showerror("Video SCORM / H5P", "Seleziona il video e la destinazione del pacchetto.")
            return
        overwrite = output.exists() and messagebox.askyesno("Sostituire il pacchetto?", f"Il file esiste già:\n{output}\n\nSostituirlo?")
        if output.exists() and not overwrite:
            return
        options = {"title": self.title_text.get(), "checkpoint": int(self.checkpoint.get()),
                   "resume": self.resume.get(), "ffprobe": self.ffprobe.get().strip() or None,
                   "overwrite": overwrite, "package_format": self.package_format.get()}
        self.status.set("Creazione e verifica del pacchetto in corso...")
        self._run(lambda: build_package(video, output, **options),
                  lambda path: (self.status.set(f"Pacchetto pronto: {path}"),
                                messagebox.showinfo("Video SCORM", f"Pacchetto creato:\n{path}")))


if __name__ == "__main__":
    BuilderWindow().mainloop()
