#!/usr/bin/env python3
"""
CleaningWizard GUI (standalone) — GUI-only file.

- Provides a Toplevel "Clean Files Wizard" for selecting input files / directories
  and running the cleaning backend on them.
- Tries to call clean_wiz_backend.clean_backend(file, outputDir, percent=...)
  If that signature is not available it will attempt a couple of safe fallbacks,
  and will always pass the unified output dir:
      <base_dir>/output/Cleaned Files

Drop-in: save as cleaning_wizard_gui.py and run. The backend is expected to be
available as clean_wiz_backend.clean_backend (but the GUI will report if missing).
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime

BACKEND_AVAILABLE = True

try:
    import clean_wiz_backend
except:
    BACKEND_AVAILABLE = False


class CleaningWizard(tk.Toplevel):
    def __init__(self, parent, start_dir=None):
        super().__init__(parent)
        self.parent = parent
        self.title("Clean Files Wizard")
        self.geometry("980x620")
        self.minsize(860, 520)
        self.transient(parent)

        # state
        self.current_dir = tk.StringVar(value=start_dir or os.getcwd())
        self.custom_percent = tk.StringVar(value="85")
        self.status_text = tk.StringVar(value="Ready")
        self.clean_dir = os.path.join(self.current_dir.get(), "output", "Cleaned Files")
        self.file_list = []          # absolute paths
        self._display_order = []
        self._running = False
        self._buttons = []

        # backend pointer (may be None)
        self._backend = clean_wiz_backend.clean_backend

        # build UI & populate
        self._create_style()
        self._build_ui()
        self._bind_events()
        self.refresh_file_list()

    def _create_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TLabel", font=(None, 11))
        style.configure("TButton", font=(None, 11))
        style.configure("Accent.TButton", background="#2e7d32", foreground="#ffffff")

    def _build_ui(self):
        top = ttk.Frame(self, padding=(8, 8, 8, 0))
        top.pack(side="top", fill="x")

        ttk.Label(top, text="Directory:").pack(side="left", padx=(2, 4))
        self.dir_entry = ttk.Entry(top, textvariable=self.current_dir, width=72)
        self.dir_entry.pack(side="left", padx=(0, 6))

        self.btn_browse = ttk.Button(top, text="Browse...", command=self.choose_directory)
        self.btn_browse.pack(side="left", padx=(0, 6)); self._buttons.append(self.btn_browse)

        self.btn_add_files = ttk.Button(top, text="Add Files...", command=self.add_files_dialog)
        self.btn_add_files.pack(side="left", padx=(0, 6)); self._buttons.append(self.btn_add_files)

        self.btn_refresh = ttk.Button(top, text="Refresh", command=self.refresh_file_list)
        self.btn_refresh.pack(side="left", padx=(6, 0)); self._buttons.append(self.btn_refresh)

        ttk.Label(top, textvariable=self.status_text).pack(side="right", padx=(8, 4))

        main = ttk.Frame(self, padding=8)
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main)
        left.pack(side="left", fill="both", expand=True)

        ctrl_row = ttk.Frame(left)
        ctrl_row.pack(side="top", fill="x", pady=(0, 8))
        self.btn_select_all = ttk.Button(ctrl_row, text="Select All", command=self.select_all)
        self.btn_select_all.pack(side="left"); self._buttons.append(self.btn_select_all)
        self.btn_deselect = ttk.Button(ctrl_row, text="Deselect All", command=self.deselect_all)
        self.btn_deselect.pack(side="left", padx=(6, 0)); self._buttons.append(self.btn_deselect)
        self.btn_remove_selected = ttk.Button(ctrl_row, text="Remove Selected", command=self.remove_selected_from_list)
        self.btn_remove_selected.pack(side="left", padx=(6, 0)); self._buttons.append(self.btn_remove_selected)
        self.btn_clear_list = ttk.Button(ctrl_row, text="Clear List", command=self.clear_list)
        self.btn_clear_list.pack(side="left", padx=(6, 0)); self._buttons.append(self.btn_clear_list)

        list_frame = ttk.Frame(left)
        list_frame.pack(fill="both", expand=True)
        self.file_listbox = tk.Listbox(list_frame, selectmode="extended", activestyle="none")
        self.file_listbox.pack(side="left", fill="both", expand=True)
        self.lb_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.file_listbox.yview)
        self.lb_scroll.pack(side="left", fill="y")
        self.file_listbox.config(yscrollcommand=self.lb_scroll.set)

        right = ttk.Frame(main, width=340)
        right.pack(side="right", fill="y", padx=(12, 0))
        ttk.Label(right, text="Actions", font=(None, 12, "bold")).pack(anchor="w")
        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=(4, 8))

        self.btn_auto = ttk.Button(right, text="Auto (one-click)", style="Accent.TButton", command=self.action_auto)
        self.btn_auto.pack(fill="x", pady=(0, 8)); self._buttons.append(self.btn_auto)

        self.btn_normal = ttk.Button(right, text="Normal (post-process)", command=self.action_normal)
        self.btn_normal.pack(fill="x", pady=(0, 8)); self._buttons.append(self.btn_normal)

        ttk.Label(right, text="Extensometer removal", font=(None, 11, "bold")).pack(anchor="w", pady=(6, 6))
        ext_frame = ttk.Frame(right); ext_frame.pack(fill="x", pady=(0, 8))
        self.btn_noext = ttk.Button(ext_frame, text="No Ext", command=lambda: self.action_noext())
        self.btn_noext.pack(fill="x"); self._buttons.append(self.btn_noext)
        self.btn_ext50 = ttk.Button(ext_frame, text="50%", command=lambda: self.action_ext_remove(50))
        self.btn_ext50.pack(fill="x", pady=(6, 0)); self._buttons.append(self.btn_ext50)
        self.btn_ext95 = ttk.Button(ext_frame, text="95%", command=lambda: self.action_ext_remove(95))
        self.btn_ext95.pack(fill="x", pady=(6, 0)); self._buttons.append(self.btn_ext95)

        customfrm = ttk.Frame(right); customfrm.pack(fill="x", pady=(8, 6))
        ttk.Label(customfrm, text="Custom %:").pack(side="left")
        self.custom_entry = ttk.Entry(customfrm, textvariable=self.custom_percent, width=8)
        self.custom_entry.pack(side="left", padx=(6, 8))
        self.btn_apply_custom = ttk.Button(customfrm, text="Apply Custom", command=self.action_custom_ext)
        self.btn_apply_custom.pack(side="left"); self._buttons.append(self.btn_apply_custom)

        opts = ttk.LabelFrame(right, text="Options", padding=(8, 8))
        opts.pack(fill="x", pady=(12, 0))
        ttk.Label(opts, text="Output suffix (optional):").pack(anchor="w")
        self.suffix_entry = ttk.Entry(opts)
        self.suffix_entry.pack(fill="x", pady=(4, 0))

        bottom = ttk.Frame(self, padding=(8, 6))
        bottom.pack(side="bottom", fill="x")
        ttk.Label(bottom, text="Preview / Log", font=(None, 11, "bold")).pack(anchor="w")
        self.log_text = tk.Text(bottom, height=10, wrap="none")
        self.log_text.pack(fill="both", expand=False)
        self.log_text.insert("end", "Wizard started. Choose a directory or add files.\n")
        self.log_text.configure(state="disabled")

    def _bind_events(self):
        self.file_listbox.bind("<Double-Button-1>", self.on_list_double_click)
        self.file_listbox.bind("<Return>", self.on_list_double_click)
        self.file_listbox.bind("<<ListboxSelect>>", self.on_list_select)

    # file discovery & list management
    def choose_directory(self):
        d = filedialog.askdirectory(initialdir=self.current_dir.get(), parent=self)
        if d:
            self.current_dir.set(d)
            self.refresh_file_list()

    def add_files_dialog(self):
        files = filedialog.askopenfilenames(
            title="Add files to list",
            initialdir=self.current_dir.get(),
            filetypes=[("CSV files", "*.csv"), ("Excel files", "*.xlsx;*.xls"), ("All files", "*.*")],
            parent=self
        )
        if files:
            added = 0
            for f in files:
                if f not in self.file_list:
                    self.file_list.append(f)
                    added += 1
            self._repopulate_listbox()
            self.log(f"Added {added} new file(s).")

    def refresh_file_list(self):
        dirpath = self.current_dir.get()
        self.file_list = []
        if os.path.isdir(dirpath):
            exts = (".csv", ".xls", ".xlsx")
            try:
                for root, _, files in os.walk(dirpath):
                    for fn in files:
                        if fn.lower().endswith(exts) and "tensile" not in fn.lower() and "output" not in root:
                            self.file_list.append(os.path.join(root, fn))
            except Exception as e:
                messagebox.showwarning("Refresh failed", f"Could not read directory:\n{e}", parent=self)
        else:
            self.log(f"Directory not found: {dirpath}")
        self._repopulate_listbox()
        self.log(f"Found {len(self.file_list)} file(s) in '{dirpath}' (recursive=True)")

    def _repopulate_listbox(self):
        self.file_listbox.delete(0, "end")
        self._display_order = sorted(self.file_list)
        for p in self._display_order:
            self.file_listbox.insert("end", os.path.basename(p))
        self._update_selected_count()

    def select_all(self):
        self.file_listbox.select_set(0, "end")
        self._update_selected_count()

    def deselect_all(self):
        self.file_listbox.select_clear(0, "end")
        self._update_selected_count()

    def clear_list(self):
        self.file_list.clear()
        self._repopulate_listbox()
        self.log("List cleared.")

    def remove_selected_from_list(self):
        sel = list(self.file_listbox.curselection())
        if not sel:
            messagebox.showinfo("Remove selected", "No files selected in the list.", parent=self)
            return
        for i in sorted(sel, reverse=True):
            try:
                path = self._display_order[i]
                self.file_list.remove(path)
            except Exception:
                pass
            self.file_listbox.delete(i)
        self.log(f"Removed {len(sel)} selected file(s) from the list.")
        self._repopulate_listbox()

    def _get_selected_paths(self):
        sel = self.file_listbox.curselection()
        return [self._display_order[i] for i in sel]

    def on_list_double_click(self, event=None):
        sel = self.file_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        try:
            path = self._display_order[idx]
        except Exception:
            return
        self.preview_file(path)

    def on_list_select(self, event=None):
        self._update_selected_count()

    def _update_selected_count(self):
        sel = self.file_listbox.curselection()
        count = len(sel)
        self.status_text.set(f"{count} selected")

    def preview_file(self, path):
        try:
            win = tk.Toplevel(self)
            win.title(f"Preview: {os.path.basename(path)}")
            win.geometry("1920x1080")
            txt = tk.Text(win, wrap="none")
            txt.pack(fill="both", expand=True)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f):
                        txt.insert("end", line)
                        if i >= 400:
                            txt.insert("end", "\n...preview truncated...\n")
                            break
            except Exception as e:
                txt.insert("end", f"Could not open preview: {e}\n")
        except Exception as e:
            self.log(f"Preview failed: {e}")

    def log(self, text):
        try:
            self.log_text.configure(state="normal")
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert("end", f"[{ts}] {text}\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        except Exception:
            print(text)

    # Actions: Auto / Normal / Ext remove / Custom percent
    def action_auto(self):
        if not self.file_list:
            messagebox.showinfo("Auto", "No files in list to process.", parent=self)
            return
        files_to_process = list(self.file_list)
        self.clean_dir = os.path.join(self.current_dir.get(), "output", "Cleaned Files")
        for file in files_to_process:
            clean_wiz_backend.clean_backend(file=file, outputDir=self.clean_dir, percent=None)
        self._start_processing(files_to_process, percent=None, mode="AUTO")

    def action_normal(self):
        paths = self._get_selected_paths()
        if not paths:
            messagebox.showinfo("Normal", "No files selected. Select files on the left first.", parent=self)
            return
        self.clean_dir = os.path.join(self.current_dir.get(), "output", "Cleaned Files")
        for file in paths:
            clean_wiz_backend.clean_backend(file=file, outputDir=self.clean_dir, percent=None)

    def action_ext_remove(self, percent):
        paths = self._get_selected_paths()
        if not paths:
            messagebox.showinfo("Extensometer removal", "No files selected. Select files on the left first.", parent=self)
            return
        self.clean_dir = os.path.join(self.current_dir.get(), "output", "Cleaned Files")
        for file in paths:
            clean_wiz_backend.clean_backend(file=file, outputDir=self.clean_dir, percent=percent)

    def action_noext(self):
        paths = self._get_selected_paths()
        if not paths:
            messagebox.showinfo("Extensometer removal", "No files selected. Select files on the left first.", parent=self)
            return
        self.clean_dir = os.path.join(self.current_dir.get(), "output", "Cleaned Files")
        for file in paths:
            clean_wiz_backend.clean_backend_noext(file=file, outputDir=self.clean_dir)

    def action_custom_ext(self):
        try:
            pct = float(self.custom_percent.get())
        except Exception:
            messagebox.showerror("Invalid percent", "Custom percent value is invalid.", parent=self)
            return
        self.clean_dir = os.path.join(self.current_dir.get(), "output", "Cleaned Files")
        self.action_ext_remove(pct)

    # core processing
    def _start_processing(self, files, percent, mode="PROCESS"):
        if self._running:
            messagebox.showwarning("Processing", "Processing is already running. Wait for it to finish.", parent=self)
            return

        # Unified output dir: <base_dir>/output/Cleaned Files
        outdir = os.path.join(self.current_dir.get(), "output", "Cleaned Files")
        try:
            os.makedirs(outdir, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Output folder", f"Could not create output folder '{outdir}':\n{e}", parent=self)
            return

        if not BACKEND_AVAILABLE:
            # still allow user to queue, but inform them
            messagebox.showerror("Backend missing", "clean_wiz_backend.clean_backend not found. Please provide the backend.", parent=self)
            return

        self._running = True
        self._set_buttons_state("disabled")
        self.log(f"[{mode}] Queued {len(files)} file(s) for processing. Output dir: {outdir}")

        def worker():
            succeeded = 0
            failed = 0
            n = len(files)

            for i, fpath in enumerate(files, start=1):
                # update log (use direct function to capture correct variables)
                self.after(0, lambda p=fpath, ii=i, nn=n: self.log(f"[{mode}] Processing ({ii}/{nn}): {p}"))

                try:
                    # Preferred signature: clean_backend(file, outputDir, percent=...)
                    # Try safe calls and catch TypeError if signature differs.
                    try:
                        self._backend(fpath, outdir, percent=percent)
                    except TypeError:
                        # try without percent
                        try:
                            self._backend(fpath, outdir)
                        except TypeError:
                            # try single-argument call
                            self._backend(fpath)
                    succeeded += 1
                    self.after(0, lambda p=fpath: self.log(f"[{mode}] Done: {p}"))
                except Exception as e:
                    failed += 1
                    self.after(0, lambda p=fpath, err=e: self.log(f"[{mode}] ERROR on {p}: {err}"))

            # finish
            def finish():
                self.log(f"[{mode}] Finished. Success: {succeeded}, Failed: {failed}")
                self._set_buttons_state("normal")
                self._running = False
                # (Caller/backend should write into outdir; GUI won't merge JSONs here)
            self.after(0, finish)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _relocate_outputs(self, base_output_root, target_outdir):
        # left as a helper in case you implement relocation later
        if not os.path.isdir(base_output_root):
            return
        base_output_root = os.path.abspath(base_output_root)
        target_outdir = os.path.abspath(target_outdir)
        for root, dirs, files in os.walk(base_output_root):
            for fname in files:
                src = os.path.join(root, fname)
                try:
                    if os.path.commonpath([src, target_outdir]) == target_outdir:
                        continue
                except Exception:
                    if os.path.abspath(src).startswith(target_outdir):
                        continue
                rel = os.path.relpath(root, base_output_root)
                dest_dir = os.path.join(target_outdir, rel) if rel != "." else target_outdir
                os.makedirs(dest_dir, exist_ok=True)
                dest = os.path.join(dest_dir, fname)
                if os.path.exists(dest):
                    base, ext = os.path.splitext(dest)
                    dest = f"{base}_{int(datetime.now().timestamp())}{ext}"
                try:
                    os.replace(src, dest)
                    self.log(f"Moved output: {src} -> {dest}")
                except Exception as e:
                    self.log(f"Failed moving output {src}: {e}")

    def _set_buttons_state(self, state):
        for btn in getattr(self, "_buttons", []):
            try:
                btn.configure(state=state)
            except Exception:
                pass
        try:
            self.file_listbox.configure(state="disabled" if state == "disabled" else "normal")
        except Exception:
            pass

    # simple helpers
    def _on_drop(self, event):
        # placeholder for future DnD support
        pass

    def open_modal(self):
        try:
            self.grab_set()
        except Exception:
            pass
        self.wait_window(self)


# quick launcher for testing the GUI standalone
if __name__ == "__main__":
    root = tk.Tk()
    root.title("CleaningWizard Test Launcher")
    root.geometry("1920x1080")
    ttk.Label(root, text="Open Cleaning Wizard", font=(None, 12)).pack(pady=(10,6))
    def open_w():
        cw = CleaningWizard(root, start_dir=r"D:\For People\For Ashwath\AK_Tensile Python Processing\SLM_070625_SR.is_tens_Exports")
        # optional: make modal: cw.open_modal()
    ttk.Button(root, text="Open Wizard", command=open_w).pack(pady=(0,8))
    ttk.Button(root, text="Quit", command=root.destroy).pack()
    root.mainloop()
