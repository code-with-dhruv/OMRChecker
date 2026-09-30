import logging
import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from main import entry_point_for_args
from src.logger import logger


class QueueLogHandler(logging.Handler):
    def __init__(self, message_queue):
        super().__init__()
        self.message_queue = message_queue

    def emit(self, record):
        self.message_queue.put(("log", self.format(record)))


class OMRCheckerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("OMRChecker | Desktop")
        self.root.geometry("900x680")
        self.root.minsize(720, 560)
        self.root.configure(background="#f2f5f3")

        self.message_queue = queue.Queue()
        self.input_paths = []
        self.output_path = tk.StringVar(value=str(ROOT_DIR / "outputs"))
        self.auto_align = tk.BooleanVar(value=False)
        self.set_layout = tk.BooleanVar(value=False)
        self.detailed_tracebacks = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Ready")

        self._configure_styles()
        self._build_interface()
        self.log_handler = QueueLogHandler(self.message_queue)
        self.log_handler.setFormatter(logging.Formatter("%(levelname)s  %(message)s"))
        logger.log.addHandler(self.log_handler)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(100, self._poll_messages)

        default_input = ROOT_DIR / "inputs"
        if default_input.is_dir():
            self._add_input_path(default_input)

    def _configure_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#f2f5f3")
        style.configure("Panel.TFrame", background="#ffffff")
        style.configure(
            "Title.TLabel",
            background="#f2f5f3",
            foreground="#173b35",
            font=("Segoe UI Semibold", 23),
        )
        style.configure(
            "Subhead.TLabel",
            background="#f2f5f3",
            foreground="#61736e",
            font=("Segoe UI", 10),
        )
        style.configure(
            "Section.TLabel",
            background="#ffffff",
            foreground="#173b35",
            font=("Segoe UI Semibold", 11),
        )
        style.configure(
            "TButton",
            font=("Segoe UI Semibold", 10),
            padding=(12, 8),
            background="#e4ece8",
            foreground="#173b35",
        )
        style.map("TButton", background=[("active", "#d5e3dc")])
        style.configure(
            "Accent.TButton",
            background="#176b57",
            foreground="#ffffff",
        )
        style.map("Accent.TButton", background=[("active", "#105642")])
        style.configure("TCheckbutton", background="#ffffff", foreground="#30433e")
        style.configure("TEntry", padding=7)

    def _build_interface(self):
        page = ttk.Frame(self.root, padding=(28, 24, 28, 18))
        page.pack(fill="both", expand=True)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)

        ttk.Label(page, text="OMRChecker", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            page,
            text="Process, align, and evaluate answer sheets from one workspace.",
            style="Subhead.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 18))

        content = ttk.Frame(page)
        content.grid(row=2, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)

        files_panel = ttk.Frame(content, style="Panel.TFrame", padding=18)
        files_panel.grid(row=0, column=0, sticky="nsew")
        files_panel.columnconfigure(0, weight=1)
        files_panel.rowconfigure(1, weight=1)

        input_header = ttk.Frame(files_panel, style="Panel.TFrame")
        input_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 9))
        input_header.columnconfigure(0, weight=1)
        ttk.Label(input_header, text="Input folders", style="Section.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(input_header, text="Add folders", command=self._browse_inputs).grid(
            row=0, column=1, padx=(8, 0)
        )
        ttk.Button(input_header, text="Remove selected", command=self._remove_selected).grid(
            row=0, column=2, padx=(8, 0)
        )

        list_frame = ttk.Frame(files_panel, style="Panel.TFrame")
        list_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.input_list = tk.Listbox(
            list_frame,
            selectmode=tk.EXTENDED,
            activestyle="none",
            background="#f7faf8",
            foreground="#263b35",
            selectbackground="#c9e1d7",
            selectforeground="#173b35",
            highlightthickness=1,
            highlightbackground="#dce6e0",
            relief="flat",
            font=("Segoe UI", 10),
        )
        self.input_list.grid(row=0, column=0, sticky="nsew")
        list_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.input_list.yview)
        list_scroll.grid(row=0, column=1, sticky="ns")
        self.input_list.configure(yscrollcommand=list_scroll.set)

        output_frame = ttk.Frame(files_panel, style="Panel.TFrame")
        output_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(17, 0))
        output_frame.columnconfigure(1, weight=1)
        ttk.Label(output_frame, text="Output folder", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 14)
        )
        ttk.Entry(output_frame, textvariable=self.output_path).grid(
            row=0, column=1, sticky="ew"
        )
        ttk.Button(output_frame, text="Browse", command=self._browse_output).grid(
            row=0, column=2, padx=(8, 0)
        )

        options = ttk.Frame(page, style="Panel.TFrame", padding=(18, 14))
        options.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        options.columnconfigure(0, weight=1)
        options.columnconfigure(1, weight=1)
        ttk.Label(options, text="Processing options", style="Section.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        ttk.Checkbutton(options, text="Auto-align scans", variable=self.auto_align).grid(
            row=1, column=0, sticky="w", pady=3
        )
        ttk.Checkbutton(
            options,
            text="Template layout preview",
            variable=self.set_layout,
        ).grid(row=1, column=1, sticky="w", pady=3)
        ttk.Checkbutton(
            options,
            text="Show detailed tracebacks",
            variable=self.detailed_tracebacks,
        ).grid(row=2, column=0, sticky="w", pady=3)
        ttk.Label(
            options,
            text="Layout preview opens the existing image windows; press Q or Esc to continue.",
            background="#ffffff",
            foreground="#71817c",
            font=("Segoe UI", 9),
        ).grid(row=2, column=1, sticky="w", pady=3)

        log_panel = ttk.Frame(page, style="Panel.TFrame", padding=14)
        log_panel.grid(row=4, column=0, sticky="nsew", pady=(12, 0))
        page.rowconfigure(4, weight=1)
        log_panel.columnconfigure(0, weight=1)
        log_panel.rowconfigure(1, weight=1)
        log_header = ttk.Frame(log_panel, style="Panel.TFrame")
        log_header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        log_header.columnconfigure(0, weight=1)
        ttk.Label(log_header, text="Run log", style="Section.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(log_header, text="Clear", command=self._clear_log).grid(
            row=0, column=1
        )
        self.log_view = tk.Text(
            log_panel,
            height=8,
            wrap="word",
            state="disabled",
            background="#172522",
            foreground="#dce9e2",
            insertbackground="#ffffff",
            relief="flat",
            padx=12,
            pady=10,
            font=("Cascadia Mono", 9),
        )
        self.log_view.grid(row=1, column=0, sticky="nsew")

        footer = ttk.Frame(page)
        footer.grid(row=5, column=0, sticky="ew", pady=(13, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status, style="Subhead.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.open_output_button = ttk.Button(
            footer, text="Open output", command=self._open_output, state="disabled"
        )
        self.open_output_button.grid(row=0, column=1, padx=(0, 8))
        self.run_button = ttk.Button(
            footer, text="Run OMRChecker", style="Accent.TButton", command=self._start_run
        )
        self.run_button.grid(row=0, column=2)

    def _add_input_path(self, path):
        path = Path(path).expanduser().resolve()
        if path.is_dir() and path not in self.input_paths:
            self.input_paths.append(path)
            self.input_list.insert(tk.END, str(path))

    def _browse_inputs(self):
        while True:
            selected = filedialog.askdirectory(title="Choose an OMR input folder")
            if not selected:
                break
            self._add_input_path(selected)
            if not messagebox.askyesno("Add another?", "Add another input folder?"):
                break

    def _remove_selected(self):
        selected = list(self.input_list.curselection())
        for index in reversed(selected):
            self.input_list.delete(index)
            del self.input_paths[index]

    def _browse_output(self):
        selected = filedialog.askdirectory(
            title="Choose an output folder", initialdir=self.output_path.get()
        )
        if selected:
            self.output_path.set(selected)

    def _start_run(self):
        if not self.input_paths:
            messagebox.showerror("Input required", "Add at least one input folder first.")
            return
        output = Path(self.output_path.get()).expanduser()
        if not output.is_absolute():
            output = (ROOT_DIR / output).resolve()
        if not output.exists():
            try:
                output.mkdir(parents=True)
            except OSError as exc:
                messagebox.showerror("Output folder error", str(exc))
                return
        if not output.is_dir():
            messagebox.showerror("Output folder error", "The output path is not a folder.")
            return

        args = {
            "input_paths": [str(path) for path in self.input_paths],
            "output_dir": str(output),
            "autoAlign": self.auto_align.get(),
            "setLayout": self.set_layout.get(),
            "debug": not self.detailed_tracebacks.get(),
        }
        self.output_path.set(str(output))
        self.run_button.configure(state="disabled")
        self.open_output_button.configure(state="disabled")
        self.status.set("Processing OMR sheets...")
        self._append_log("Starting OMRChecker run.")
        threading.Thread(target=self._run, args=(args,), daemon=True).start()

    def _run(self, args):
        try:
            entry_point_for_args(args)
        except Exception:
            logger.log.exception("OMRChecker run failed")
            self.message_queue.put(("finished", False))
        else:
            self.message_queue.put(("finished", True))

    def _poll_messages(self):
        while True:
            try:
                kind, payload = self.message_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._append_log(payload)
            elif kind == "finished":
                self.run_button.configure(state="normal")
                self.open_output_button.configure(state="normal")
                self.status.set("Completed" if payload else "Finished with errors")
                self._append_log(
                    "Run completed." if payload else "Run stopped because of an error."
                )
        self.root.after(100, self._poll_messages)

    def _append_log(self, message):
        self.log_view.configure(state="normal")
        self.log_view.insert(tk.END, message + "\n")
        self.log_view.see(tk.END)
        self.log_view.configure(state="disabled")

    def _clear_log(self):
        self.log_view.configure(state="normal")
        self.log_view.delete("1.0", tk.END)
        self.log_view.configure(state="disabled")

    def _open_output(self):
        output = Path(self.output_path.get())
        if output.is_dir():
            os.startfile(str(output))

    def _close(self):
        logger.log.removeHandler(self.log_handler)
        self.root.destroy()


def main():
    root = tk.Tk()
    OMRCheckerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()