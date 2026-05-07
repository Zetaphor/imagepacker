#!/usr/bin/env python3

"""OBJ UV Packer -- tkinter GUI frontend."""

import os
import queue
import re
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _DND_IMPORT_OK = True
except ImportError:
    _DND_IMPORT_OK = False

from packer import run_pack, PackError

WINDOW_TITLE = "OBJ UV Packer"
WINDOW_MIN_W = 660
WINDOW_MIN_H = 560


def find_obj_files(folder):
    """Recursively find all .obj files under a folder, skipping *_packed* dirs."""
    results = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames if "_packed" not in d.lower()]
        for f in filenames:
            if f.lower().endswith(".obj"):
                results.append(os.path.join(dirpath, f))
    results.sort()
    return results


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self._dnd_ok = self._try_init_dnd()
        self.title(WINDOW_TITLE)
        self.minsize(WINDOW_MIN_W, WINDOW_MIN_H)
        self.resizable(True, True)

        self._log_queue = queue.Queue()
        self._tile_event = threading.Event()
        self._tile_result = False
        self._packing = False
        self._obj_paths = []

        self._build_ui()
        self._setup_dnd()
        self._poll_log()

    def _try_init_dnd(self):
        """Try to load tkdnd at runtime. Returns True on success."""
        if not _DND_IMPORT_OK:
            return False
        try:
            from tkinterdnd2.TkinterDnD import _require
            _require(self)
            return True
        except Exception:
            return False

    def _build_ui(self):
        pad = dict(padx=8, pady=4)

        # --- Input selection ---
        input_frame = ttk.LabelFrame(self, text="Input", padding=8)
        input_frame.pack(fill="x", **pad)

        btn_row = ttk.Frame(input_frame)
        btn_row.grid(row=0, column=0, columnspan=3, sticky="w")

        ttk.Button(btn_row, text="Open OBJ File...",
                   command=self._browse_obj).pack(side="left")
        ttk.Button(btn_row, text="Open Folder...",
                   command=self._browse_folder).pack(side="left", padx=(8, 0))

        dnd_hint = " (or drag and drop here)" if self._dnd_ok else ""
        self._drop_label = tk.Label(
            input_frame,
            text="Drop .obj files or a folder here",
            relief="groove", padx=12, pady=10, fg="gray",
        )
        if self._dnd_ok:
            self._drop_label.grid(row=0, column=2, sticky="e", padx=(12, 0))

        self._input_var = tk.StringVar(
            value="(no file or folder selected{})".format(dnd_hint))
        ttk.Label(input_frame, textvariable=self._input_var,
                  foreground="gray").grid(row=1, column=0, columnspan=3,
                                          sticky="w", pady=(4, 0))

        self._file_list_var = tk.StringVar(value="")
        self._file_list_label = ttk.Label(input_frame,
                                          textvariable=self._file_list_var,
                                          wraplength=600, justify="left")
        self._file_list_label.grid(row=2, column=0, columnspan=3, sticky="w",
                                   pady=(2, 0))

        # --- MTL override (only for single-file mode) ---
        self._mtl_frame = ttk.Frame(input_frame)
        self._mtl_frame.grid(row=3, column=0, columnspan=3, sticky="ew",
                             pady=(6, 0))

        ttk.Label(self._mtl_frame, text="MTL override:").pack(side="left")
        self._mtl_var = tk.StringVar(value="(auto-detect)")
        ttk.Entry(self._mtl_frame, textvariable=self._mtl_var,
                  state="readonly", width=45).pack(side="left", padx=(4, 4))
        ttk.Button(self._mtl_frame, text="Browse...",
                   command=self._browse_mtl).pack(side="left")

        input_frame.columnconfigure(1, weight=1)

        # --- Output directory ---
        out_frame = ttk.LabelFrame(self, text="Output", padding=8)
        out_frame.pack(fill="x", **pad)

        self._outdir_var = tk.StringVar(value="(same folder as input)")
        ttk.Entry(out_frame, textvariable=self._outdir_var,
                  state="readonly", width=55).pack(side="left", fill="x",
                                                    expand=True)
        ttk.Button(out_frame, text="Browse...",
                   command=self._browse_outdir).pack(side="left", padx=(4, 0))
        ttk.Button(out_frame, text="Reset",
                   command=self._reset_outdir).pack(side="left", padx=(4, 0))

        # --- Options ---
        opt_frame = ttk.LabelFrame(self, text="Options", padding=8)
        opt_frame.pack(fill="x", **pad)

        self._crop_var = tk.BooleanVar(value=True)
        self._tile_var = tk.BooleanVar(value=True)
        self._wrap_var = tk.BooleanVar(value=True)

        ttk.Checkbutton(opt_frame, text="Crop textures to used UV region",
                        variable=self._crop_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(opt_frame, text="Tile textures outside UV space",
                        variable=self._tile_var).grid(row=0, column=1, sticky="w",
                                                      padx=(16, 0))
        ttk.Checkbutton(opt_frame, text="Wrap UVs into [0,1]",
                        variable=self._wrap_var).grid(row=0, column=2, sticky="w",
                                                      padx=(16, 0))

        # --- Pack button ---
        btn_frame = ttk.Frame(self, padding=(8, 0))
        btn_frame.pack(fill="x")

        self._pack_btn = ttk.Button(btn_frame, text="Pack Textures",
                                    command=self._start_pack)
        self._pack_btn.pack(side="left")

        self._status_var = tk.StringVar(value="Ready")
        ttk.Label(btn_frame, textvariable=self._status_var,
                  foreground="gray").pack(side="left", padx=(12, 0))

        # --- Log area ---
        log_frame = ttk.LabelFrame(self, text="Log", padding=4)
        log_frame.pack(fill="both", expand=True, **pad)

        self._log_text = tk.Text(log_frame, wrap="word", state="disabled",
                                 height=14, font=("Consolas", 9))
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical",
                                  command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=scrollbar.set)
        self._log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    # --- Drag and drop ---

    def _setup_dnd(self):
        if not self._dnd_ok:
            return
        try:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            self._dnd_ok = False

    def _parse_dnd_paths(self, data):
        """Parse the space-separated path string from tkdnd.
        Paths with spaces are wrapped in curly braces on some platforms."""
        paths = []
        for match in re.finditer(r'\{([^}]+)\}|(\S+)', data):
            paths.append(match.group(1) or match.group(2))
        return paths

    def _on_drop(self, event):
        if self._packing:
            return
        paths = self._parse_dnd_paths(event.data)
        if not paths:
            return

        obj_files = []
        folders = []
        for p in paths:
            if os.path.isdir(p):
                folders.append(p)
            elif os.path.isfile(p) and p.lower().endswith(".obj"):
                obj_files.append(p)

        if folders:
            for folder in folders:
                obj_files.extend(find_obj_files(folder))

        if not obj_files:
            messagebox.showwarning(
                "No OBJ files",
                "No .obj files found in the dropped items.",
                parent=self)
            return

        obj_files = sorted(set(obj_files))
        self._obj_paths = obj_files

        if len(obj_files) == 1:
            self._input_var.set(obj_files[0])
            self._file_list_var.set("")
            self._mtl_var.set("(auto-detect)")
            self._mtl_frame.grid()
        else:
            self._input_var.set("{} OBJ file(s) dropped".format(len(obj_files)))
            names = [os.path.basename(p) for p in obj_files]
            self._file_list_var.set(
                "Found {} OBJ file(s): {}".format(len(obj_files), ", ".join(names))
            )
            self._mtl_var.set("(auto-detect)")
            self._mtl_frame.grid_remove()

    # --- File/folder browsing ---

    def _browse_obj(self):
        path = filedialog.askopenfilename(
            title="Select OBJ file",
            filetypes=[("OBJ files", "*.obj"), ("All files", "*.*")],
        )
        if path:
            self._obj_paths = [path]
            self._input_var.set(path)
            self._file_list_var.set("")
            self._mtl_var.set("(auto-detect)")
            self._mtl_frame.grid()

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Select folder containing OBJ models")
        if folder:
            objs = find_obj_files(folder)
            if not objs:
                messagebox.showwarning("No OBJ files",
                                       "No .obj files found in:\n" + folder,
                                       parent=self)
                return
            self._obj_paths = objs
            self._input_var.set(folder)
            names = [os.path.relpath(p, folder) for p in objs]
            self._file_list_var.set(
                "Found {} OBJ file(s): {}".format(len(objs), ", ".join(names))
            )
            self._mtl_var.set("(auto-detect)")
            self._mtl_frame.grid_remove()

    def _browse_mtl(self):
        path = filedialog.askopenfilename(
            title="Select MTL file",
            filetypes=[("MTL files", "*.mtl"), ("All files", "*.*")],
        )
        if path:
            self._mtl_var.set(path)

    def _browse_outdir(self):
        folder = filedialog.askdirectory(title="Select output directory")
        if folder:
            self._outdir_var.set(folder)

    def _reset_outdir(self):
        self._outdir_var.set("(same folder as input)")

    # --- Logging ---

    def _log(self, msg):
        self._log_queue.put(msg)

    def _poll_log(self):
        while True:
            try:
                msg = self._log_queue.get_nowait()
            except queue.Empty:
                break
            self._log_text.configure(state="normal")
            self._log_text.insert("end", msg + "\n")
            self._log_text.see("end")
            self._log_text.configure(state="disabled")
        self.after(100, self._poll_log)

    # --- Tile dialog (runs on main thread, waited on by worker) ---

    def _tile_callback(self, texture_name, h_tiles, v_tiles):
        self._tile_result = False
        self._tile_event.clear()
        self.after(0, self._show_tile_dialog, texture_name, h_tiles, v_tiles)
        self._tile_event.wait()
        return self._tile_result

    def _show_tile_dialog(self, texture_name, h_tiles, v_tiles):
        result = messagebox.askyesno(
            "Tiling Detected",
            "The texture '{}' has UV coordinates that imply it tiles "
            "{}x{} times.\n\n"
            "This may be intentional (e.g. tank tracks) or a sign of "
            "problematic UV coordinates.\n\n"
            "Do you want to tile this texture?".format(
                os.path.basename(str(texture_name)), h_tiles, v_tiles
            ),
            parent=self,
        )
        self._tile_result = result
        self._tile_event.set()

    # --- Pack execution ---

    def _start_pack(self):
        if not self._obj_paths:
            messagebox.showerror("Error",
                                 "Please select an OBJ file or folder first.",
                                 parent=self)
            return

        for p in self._obj_paths:
            if not os.path.isfile(p):
                messagebox.showerror("Error",
                                     "File not found:\n" + p,
                                     parent=self)
                return

        if self._packing:
            return

        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")

        mtl_val = self._mtl_var.get()
        mtl_path = mtl_val if os.path.isfile(mtl_val) else None

        outdir_val = self._outdir_var.get()
        output_dir = outdir_val if os.path.isdir(outdir_val) else None

        self._packing = True
        self._pack_btn.configure(state="disabled")
        self._status_var.set("Packing...")

        thread = threading.Thread(
            target=self._run_worker,
            args=(list(self._obj_paths), mtl_path, output_dir),
            daemon=True,
        )
        thread.start()

    def _run_worker(self, obj_paths, mtl_override, output_dir):
        succeeded = []
        failed = []

        for i, obj_path in enumerate(obj_paths, 1):
            label = os.path.basename(obj_path)
            if len(obj_paths) > 1:
                self._log("=" * 60)
                self._log("[{}/{}] {}".format(i, len(obj_paths), label))
                self._log("=" * 60)

            mtl_path = mtl_override if len(obj_paths) == 1 else None

            try:
                result_dir = run_pack(
                    obj_path=obj_path,
                    mtl_path=mtl_path,
                    output_dir=output_dir,
                    crop=self._crop_var.get(),
                    tile=self._tile_var.get(),
                    wrap=self._wrap_var.get(),
                    tile_callback=(self._tile_callback
                                   if self._tile_var.get() else None),
                    log_callback=self._log,
                )
                succeeded.append((label, result_dir))
            except PackError as e:
                self._log("ERROR: " + str(e))
                failed.append((label, str(e)))
            except Exception as e:
                self._log("UNEXPECTED ERROR: " + str(e))
                failed.append((label, str(e)))

        self.after(0, self._on_batch_done, succeeded, failed)

    def _on_batch_done(self, succeeded, failed):
        self._packing = False
        self._pack_btn.configure(state="normal")

        total = len(succeeded) + len(failed)

        if total == 1 and succeeded:
            self._status_var.set("Done!")
            messagebox.showinfo(
                "Success",
                "Packing complete!\n\nOutput written to:\n" + succeeded[0][1],
                parent=self,
            )
        elif total == 1 and failed:
            self._status_var.set("Error")
            messagebox.showerror("Packing Failed", failed[0][1], parent=self)
        else:
            self._status_var.set(
                "Done: {} succeeded, {} failed".format(len(succeeded), len(failed))
            )
            lines = ["{} of {} models packed successfully.".format(
                len(succeeded), total)]
            if failed:
                lines.append("\nFailed:")
                for name, err in failed:
                    lines.append("  {} -- {}".format(name, err.split('\n')[0]))
            if succeeded:
                lines.append("\nOutput directories:")
                for name, out_dir in succeeded:
                    lines.append("  " + out_dir)

            messagebox.showinfo("Batch Complete", "\n".join(lines), parent=self)


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
