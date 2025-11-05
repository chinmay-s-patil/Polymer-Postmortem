# gui_core.py
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib
from matplotlib.backends.backend_tkagg import (FigureCanvasTkAgg,
                                               NavigationToolbar2Tk)
from matplotlib.figure import Figure

matplotlib.use("TkAgg")
import json
from datetime import datetime

import numpy as np
import pandas as pd

# import helpers & constants (keeps original function names)
from cleaning import *
from constants import *
from json_utils import *
from data_helpers import *
from clean_wizard import CleaningWizard
from preview import preview_file

VERSION = "1.32.0"

# --- GUI ---
class TensileGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Polymer PostMortem")
        self.root.geometry("1280x780")
        # prefer true fullscreen; fall back to zoomed or fixed size if not available
        try:
            # start fullscreen (works cross-platform for most setups)
            self.root.attributes("-fullscreen", True)
            self._is_fullscreen = True
        except Exception:
            try:
                # Windows-like zoomed state
                self.root.state("zoomed")
                self._is_fullscreen = False
            except Exception:
                # last resort
                self.root.geometry("1920x1080")
                self._is_fullscreen = False

        # allow toggling fullscreen with F11 and exit with Escape
        def _toggle_fullscreen(event=None):
            self._is_fullscreen = not getattr(self, "_is_fullscreen", False)
            try:
                self.root.attributes("-fullscreen", self._is_fullscreen)
            except Exception:
                # if attributes not supported, try state zoomed / normal
                try:
                    self.root.state("zoomed" if self._is_fullscreen else "normal")
                except Exception:
                    pass

        self.root.bind("<F11>", _toggle_fullscreen)
        self.root.bind("<Escape>", lambda e: (setattr(self, "_is_fullscreen", False), self.root.attributes("-fullscreen", False) if hasattr(self.root, "attributes") else self.root.state("normal")))

        self.dir_var = tk.StringVar(value = BASEDIR)
        self.output_dir = None
        self.current_file = None
        self.all_files = []
        self.item_paths = {}
        self.master_data = {}
        self.charl = DEFAULT_CHARL
        self.area = DEFAULT_AREA

        # file watcher state
        self._master_mtime = None
        self._watching = False

        # batch stop
        self.batch_stop = False

        # icons
        self._create_flag_icons()

        # top
        top = ttk.Frame(root, padding=(8,6))
        top.pack(side="top", fill="x")
        ttk.Label(top, text="Directory:").pack(side="left")
        self.dir_entry = ttk.Entry(top, textvariable=self.dir_var, width=70)
        self.dir_entry.pack(side="left", padx=(6,6))
        ttk.Button(top, text="Browse", command=self.browse_folder).pack(side="left", padx=4)
        ttk.Button(top, text="Set", command=self.set_directory).pack(side="left", padx=4)
        # --------- Modified: Clean Files now opens embedded CleaningWizard ----------
        ttk.Button(top, text="Clean Files", command=self.start_cleaning).pack(side="left", padx=6)
        # -------------------------------------------------------------------------
        ttk.Button(top, text="Refresh", command=self.manual_refresh).pack(side="left", padx=6)
        ttk.Button(top, text="Reset All", command=self.reset_all_files).pack(side="left", padx=6)

        ttk.Separator(root, orient="horizontal").pack(fill="x", pady=(4,6))

        body = ttk.Frame(root)
        body.pack(fill="both", expand=True, padx=8, pady=4)

        left = ttk.Frame(body)
        left.pack(side="left", fill="y", padx=(0,8))

        ttk.Label(left, text="Filter:").pack(anchor="w")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.filter_list())
        ttk.Entry(left, textvariable=self.search_var, width=30).pack(anchor="w", pady=(0,6))

        # Tree: use #0 for icon-only flag column, File then metrics
        cols = ("File", "M", "Y", "B", "U")
        self.tree = ttk.Treeview(left, columns=cols, show="tree headings", height=36)
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=50, anchor="center", stretch=True)
        for c in cols:
            self.tree.heading(c, text=c)
        self.tree.column("File", width=480, anchor="w")
        self.tree.column("M", width=30, anchor="center")
        self.tree.column("Y", width=30, anchor="center")
        self.tree.column("B", width=30, anchor="center")
        self.tree.column("U", width=30, anchor="center")
        self.tree.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        sb.pack(side="left", fill="y")
        self.tree.configure(yscrollcommand=sb.set)

        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)

        # action row (preserve your layout — change commands only)
        action_row = ttk.Frame(right)
        action_row.pack(fill="x", pady=(0,6))
        ttk.Button(action_row, text="Modulus", command=self.action_modulus).pack(side="left", padx=4)
        ttk.Button(action_row, text="Yield", command=self.action_yield).pack(side="left", padx=4)
        ttk.Button(action_row, text="Break Point", command=self.action_breakpoint).pack(side="left", padx=4)
        ttk.Button(action_row, text="Ultimate", command=self.action_ultimate).pack(side="left", padx=4)
        ttk.Button(action_row, text="Reset", command=self.reset_file).pack(side="left", padx=4)
        ttk.Button(action_row, text="Flag", command=self.toggle_flag_for_selected).pack(side="left", padx=4)
        ttk.Button(action_row, text="Preview Data", command=self.preview_file_open).pack(side="left", padx=4)
        ttk.Button(action_row, text="Save All → Excel", command=self.save_all_to_excel).pack(side="right", padx=4)

        batch_row = ttk.Frame(right)
        batch_row.pack(fill="x", pady=(0,6))
        ttk.Button(batch_row, text="Batch Modulus", command=self.batch_manual_modulus).pack(side="left", padx=4)
        ttk.Button(batch_row, text="Batch Yield", command=self.batch_manual_yield).pack(side="left", padx=4)
        ttk.Button(batch_row, text="Batch Break Point", command=self.batch_manual_break).pack(side="left", padx=4)
        ttk.Button(batch_row, text="Batch Auto Modulus", command=self.batch_auto_modulus).pack(side="left", padx=4)
        ttk.Button(batch_row, text="Batch Auto Yield", command=self.batch_auto_yield).pack(side="left", padx=4)
        ttk.Button(batch_row, text="Batch Auto Ultimate", command=self.batch_auto_ultimate).pack(side="left", padx=4)
        ttk.Button(batch_row, text="Batch Manual All", command=self.batch_manual_all).pack(side="left", padx=4)
        ttk.Button(batch_row, text="Stop Batch", command=self.stop_batch).pack(side="right", padx=4)

        preview_frame = ttk.LabelFrame(right, text="Preview")
        preview_frame.pack(fill="both", expand=True)

        self.preview_fig = Figure(figsize=(5,3))
        self.preview_ax = self.preview_fig.add_subplot(111)
        self.preview_canvas = FigureCanvasTkAgg(self.preview_fig, master=preview_frame)
        self.preview_canvas.get_tk_widget().pack(fill="both", expand=True)
        self.preview_toolbar = NavigationToolbar2Tk(self.preview_canvas, preview_frame)
        self.preview_toolbar.update()
        self.preview_toolbar.pack(fill="x")

        bottom = ttk.Frame(root)
        bottom.pack(side="bottom", fill="x", padx=8, pady=(6,8))
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(bottom, textvariable=self.status_var).pack(side="left")
        self.metric_vars = {
            'modulus': tk.StringVar(value="Modulus: N/A"),
            'yield': tk.StringVar(value="Yield: N/A"),
            'breakpoint': tk.StringVar(value="Break: N/A"),
            'ultimate': tk.StringVar(value="Ultimate: N/A")
        }
        for v in self.metric_vars.values():
            ttk.Label(bottom, textvariable=v).pack(side="right", padx=(8,0))
        
        # subtle easter-egg attribution centered at the bottom (unobtrusive)
        try:
            cc_text = f"CC BY 4.0 — Polymer PostMortem v{VERSION} — Chinmay Patil"
            footer = tk.Label(self.root, text=cc_text, font=("Segoe UI", 10), fg="#8a8a8a")
            # center horizontally, sit just above the bottom edge
            footer.place(relx=0.5, rely=0.995, anchor="s")
        except Exception:
            pass


        # initial populate if path exists
        if os.path.isdir(self.dir_var.get()):
            self.populate_cleaned_files(self.dir_var.get())

    # ---------------- icons ----------------
    def _create_flag_icons(self):
        self.flag_on = tk.PhotoImage(width=ICON_PIXELS, height=ICON_PIXELS)
        self.flag_off = tk.PhotoImage(width=ICON_PIXELS, height=ICON_PIXELS)
        # fill off light gray
        for y in range(ICON_PIXELS):
            for x in range(ICON_PIXELS):
                self.flag_off.put("#f3f3f3", (x, y))
        # draw red flag on flag_on
        for y in range(ICON_PIXELS):
            for x in range(ICON_PIXELS):
                self.flag_on.put("#ffffff", (x, y))
        # pole
        for y in range(2, ICON_PIXELS-2):
            self.flag_on.put("#333333", (2, y))
        # red rectangle
        for x in range(3, ICON_PIXELS-2):
            for y in range(3, 8):
                self.flag_on.put("#d92b2b", (x, y))

    # ---------------- directory / cleaning / refresh ----------------
    def browse_folder(self):
        sel = filedialog.askdirectory(initialdir=os.getcwd())
        if sel:
            self.dir_var.set(sel)

    def set_directory(self):
        chosen = self.dir_var.get().strip()
        if not chosen or not os.path.isdir(chosen):
            self.status_var.set("Path does not exist.")
            return
        self.output_dir = os.path.join(chosen, "output")
        os.makedirs(self.output_dir, exist_ok=True)
        # initial merge and populate
        merge_individual_jsons(self.output_dir)
        self.populate_cleaned_files(chosen)
        # start master watcher
        self._start_master_watcher()
        self.status_var.set(f"Directory set: {chosen} (watching master json)")

    # --------- START: Modified start_cleaning to open CleaningWizard ----------
    def start_cleaning(self):
        chosen = self.dir_var.get().strip()
        if not chosen or not os.path.isdir(chosen):
            self.status_var.set("Set a valid directory first.")
            return

        # Clear existing outputs (keeps previous behavior)
        self.status_var.set("Clearing existing output directories...")
        try:
            clear_clean_files_csvs(chosen)
        except Exception as e:
            print("clear_output_dirs failed:", e)

        # Launch embedded CleaningWizard Toplevel
        try:
            cw = CleaningWizard(self.root, start_dir=chosen)
            # do not block mainloop — allow user to interact; optionally make modal:
            # cw.open_modal()
            self.status_var.set("Opened Clean Files Wizard.")
        except Exception as e:
            self.status_var.set(f"Failed to open Clean Wizard: {e}")
    # --------- END: Modified start_cleaning ----------
    
    def _clean_thread(self, chosen, files):
        try:
            if MP_AVAILABLE and hasattr(mp, "cleanfiles"):
                try:
                    mp.cleanfiles(chosen, files)
                except Exception:
                    cleanfiles(chosen, files)
            else:
                cleanfiles(chosen, files)
        except Exception:
            pass
        # ensure output_dir set and re-merge
        self.output_dir = os.path.join(chosen, "output")
        merge_individual_jsons(self.output_dir)
        self.root.after(0, lambda: (self.populate_cleaned_files(chosen), self.status_var.set("Cleaning completed.")))

    def manual_refresh(self):
        if not self.output_dir:
            self.status_var.set("Set directory first.")
            return
        try:
            merge_individual_jsons(self.output_dir)
            self.populate_cleaned_files(self.dir_var.get())
            self.status_var.set("Refreshed.")
        except Exception as e:
            self.status_var.set(f"Refresh failed: {e}")

    # ---------------- master watcher ----------------
    def _start_master_watcher(self):
        """Start polling for gui_master.json changes."""
        if self._watching:
            return
        self._watching = True
        # set initial mtime
        self._update_master_mtime()
        self._poll_master()

    def _update_master_mtime(self):
        p = master_json_path(self.output_dir) if self.output_dir else None
        try:
            self._master_mtime = os.path.getmtime(p) if p and os.path.exists(p) else None
        except Exception:
            self._master_mtime = None

    def _poll_master(self):
        if not self._watching or not self.output_dir:
            return
        p = master_json_path(self.output_dir)
        try:
            new_m = os.path.getmtime(p) if p and os.path.exists(p) else None
        except Exception:
            new_m = None
        if new_m != self._master_mtime:
            # master changed — refresh tree + internal master_data
            self._master_mtime = new_m
            try:
                merge_individual_jsons(self.output_dir)
            except Exception:
                pass
            try:
                # refresh visible list maintaining selection if possible
                cur_sel = self.current_file
                self.populate_cleaned_files(self.dir_var.get())
                if cur_sel:
                    self.select_file_and_refresh(cur_sel)
                self.status_var.set("Master changed — refreshed.")
            except Exception:
                pass
        # schedule next poll
        self.root.after(MASTER_POLL_MS, self._poll_master)

    # ---------------- tree population / selection ----------------
    def populate_cleaned_files(self, db):
        files = []
        for root, _, fls in os.walk(db):
            for f in fls:
                if (f.lower().endswith(".csv") or f.lower().endswith(".xlsx")) and "output" in root.lower() and "tensile_results" not in f:
                    files.append(os.path.join(root, f))
        files = sorted(files)
        self.all_files = files
        self._refresh_tree(files)

    def _refresh_tree(self, files):
        # clear
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.item_paths.clear()

        master = load_master(self.output_dir) if self.output_dir else {}

        for p in files:
            basename = os.path.basename(p)
            entry = master.get(basename, {})
            m_done = "✓" if ("modulus" in entry and entry.get("modulus") is not None) else "✗"
            y_done = "✓" if ("yield" in entry and entry.get("yield") is not None) else "✗"
            b_done = "✓" if ("breakpoint" in entry and entry.get("breakpoint") is not None) else "✗"
            u_done = "✓" if (entry.get("ultimate") is not None) else "✗"
            flag_bool = bool(entry.get("flag")) if isinstance(entry.get("flag"), bool) else False
            img = self.flag_on if flag_bool else self.flag_off
            item = self.tree.insert("", "end", text="", image=img, values=(basename, m_done, y_done, b_done, u_done))
            self.item_paths[item] = p
            done_count = sum(1 for t in (m_done, y_done, b_done, u_done) if t == "✓")
            if done_count == 4:
                self.tree.item(item, tags=("all_done",))
            elif done_count > 0:
                self.tree.item(item, tags=("some_done",))
            else:
                self.tree.item(item, tags=("none_done",))

        self.tree.tag_configure("all_done", background="#e6ffeb")
        self.tree.tag_configure("some_done", background="#fff7e6")
        self.tree.tag_configure("none_done", background="#ffecec")

        self.status_var.set(f"{len(files)} cleaned files found.")

    def filter_list(self):
        q = self.search_var.get().strip().lower()
        if not hasattr(self, "all_files"):
            return
        if not q:
            self._refresh_tree(self.all_files)
            return
        filtered = [p for p in self.all_files if q in os.path.basename(p).lower()]
        self._refresh_tree(filtered)

    def on_tree_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        item = sel[0]
        path = self.item_paths.get(item)
        if not path:
            return
        self.current_file = path
        self.status_var.set(f"Selected: {os.path.basename(path)}")
        if self.output_dir:
            self.master_data = load_master(self.output_dir)
        info = self.master_data.get(os.path.basename(path), {})
        self.metric_vars['modulus'].set(f"Modulus: {info.get('modulus', 'N/A')}")
        self.metric_vars['yield'].set(f"Yield: {info.get('yield', 'N/A')}")
        self.metric_vars['breakpoint'].set(f"Break: {info.get('breakpoint', 'N/A')}")
        self.metric_vars['ultimate'].set(f"Ultimate: {info.get('ultimate', 'N/A')}")
        self._draw_preview(path)

    def select_file_and_refresh(self, filepath):
        # select item corresponding to filepath and refresh preview & metrics
        if not filepath or not os.path.exists(filepath):
            return
        for iid, p in self.item_paths.items():
            if os.path.normpath(p) == os.path.normpath(filepath):
                try:
                    self.tree.selection_set(iid)
                    self.tree.see(iid)
                except Exception:
                    pass
                break
        if self.output_dir:
            self.master_data = load_master(self.output_dir)
        info = self.master_data.get(os.path.basename(filepath), {})
        self.metric_vars['modulus'].set(f"Modulus: {info.get('modulus', 'N/A')}")
        self.metric_vars['yield'].set(f"Yield: {info.get('yield', 'N/A')}")
        self.metric_vars['breakpoint'].set(f"Break: {info.get('breakpoint', 'N/A')}")
        self.metric_vars['ultimate'].set(f"Ultimate: {info.get('ultimate', 'N/A')}")
        self._draw_preview(filepath)

    # ---------------- preview ----------------
    def _draw_preview(self, path):
        self.preview_ax.clear()
        try:
            df = pd.read_csv(path)
            names = detect_columns(df)
            if names["strain"] and names["stress"]:
                x = df[names["strain"]].astype(float)
                y = df[names["stress"]].astype(float)
                self.preview_ax.plot(x, y, '.', ms=2)
                self.preview_ax.set_xlabel("Strain"); self.preview_ax.set_ylabel("Stress")
            elif names["disp"] and names["force"]:
                x = df[names["disp"]].astype(float)
                y = df[names["force"]].astype(float)
                self.preview_ax.plot(x, y, '.', ms=2)
                self.preview_ax.set_xlabel("Disp"); self.preview_ax.set_ylabel("Force")
            else:
                nums = df.select_dtypes(include=[np.number]).columns.tolist()
                if len(nums) >= 2:
                    x = df[nums[0]].astype(float); y = df[nums[1]].astype(float)
                    self.preview_ax.plot(x, y, '.', ms=2)
                    self.preview_ax.set_xlabel(nums[0]); self.preview_ax.set_ylabel(nums[1])
                else:
                    self.preview_ax.text(0.5, 0.5, "No preview available", ha='center')
        except Exception:
            self.preview_ax.text(0.5, 0.5, "Preview failed", ha='center')
        self.preview_canvas.draw_idle()
    
    
    # ---------------- File Previewing ----------------
    def preview_file_open(self):
        if not self.current_file:
            self.status_var.set("Select a file first.")
            return
        if not self.output_dir:
            self.status_var.set("Set directory first.")
            return
        file = self.current_file
        preview_file(file)
            

    # ---------------- flag toggling ----------------
    def toggle_flag_for_selected(self):
        if not self.current_file:
            self.status_var.set("Select a file first.")
            return
        if not self.output_dir:
            self.status_var.set("Set directory first.")
            return
        fname = os.path.basename(self.current_file)
        master = load_master(self.output_dir)
        entry = master.setdefault(fname, {})
        current = bool(entry.get("flag")) if isinstance(entry.get("flag"), bool) else False
        entry["flag"] = not current
        save_master(self.output_dir, master)
        # update mtime to trigger polling refresh immediately
        try:
            p = master_json_path(self.output_dir)
            if p:
                os.utime(p, None)
        except Exception:
            pass
        merge_individual_jsons(self.output_dir)
        self.populate_cleaned_files(self.dir_var.get())
        self.select_file_and_refresh(self.current_file)
        self.status_var.set(f"Flag toggled for {fname} -> {entry['flag']}")

    # ---------------- Reset (per-file) ----------------
    def reset_file(self):
        if not self.current_file:
            self.status_var.set("Select a file first.")
            return
        if not self.output_dir:
            self.status_var.set("Set directory first.")
            return
        fname = os.path.basename(self.current_file)
        ok = messagebox.askyesno("Confirm Reset",
                                 f"Reset computed data and specs for '{fname}'?\nThis will delete JSON entries and the specimen spec file.")
        if not ok:
            return
        try:
            # delete entries in per-metric jsons
            names = ["modulus_results.json", "yield_results.json", "break_results.json"]
            for nm in names:
                p = os.path.join(self.output_dir, nm)
                if os.path.exists(p):
                    try:
                        with open(p, "r", encoding="utf-8") as jf:
                            d = json.load(jf)
                    except Exception:
                        d = {}
                    if fname in d:
                        d.pop(fname, None)
                        write_json_safe(p, d)
            # delete specimen spec json
            spdir = os.path.join(self.output_dir, "Clean Files", "specimenSpecs")
            if os.path.isdir(spdir):
                spec_file = os.path.join(spdir, os.path.splitext(fname)[0] + ".json")
                if os.path.exists(spec_file):
                    try:
                        os.remove(spec_file)
                    except Exception:
                        pass
            # remove computed keys from master but keep flag if present
            master = load_master(self.output_dir)
            entry = master.get(fname, {})
            flag_val = entry.get("flag") if isinstance(entry.get("flag"), bool) else None
            new_entry = {}
            if flag_val is not None:
                new_entry["flag"] = flag_val
            if new_entry:
                master[fname] = new_entry
            else:
                master.pop(fname, None)
            save_master(self.output_dir, master)
            # ensure file mtime updated to trigger watcher
            try:
                p = master_json_path(self.output_dir)
                if p:
                    os.utime(p, None)
            except Exception:
                pass
            # re-merge & refresh
            merge_individual_jsons(self.output_dir)
            self.populate_cleaned_files(self.dir_var.get())
            self.select_file_and_refresh(self.current_file)
            self.status_var.set(f"Reset complete for {fname}")
        except Exception as e:
            self.status_var.set(f"Reset failed: {e}")

    # ---------------- Reset All ----------------
    def reset_all_files(self):
        if not self.output_dir:
            self.status_var.set("Set directory first.")
            return
        ok = messagebox.askyesno("Confirm Reset All",
                                 "Delete all result JSONs and specimenSpecs? This will remove all computed data.")
        if not ok:
            return
        try:
            names = ["modulus_results.json", "yield_results.json", "break_results.json", "gui_master.json"]
            for nm in names:
                p = os.path.join(self.output_dir, nm)
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            spdir = os.path.join(self.output_dir, "Clean Files", "specimenSpecs")
            if os.path.isdir(spdir):
                for fn in os.listdir(spdir):
                    if fn.lower().endswith(".json"):
                        try:
                            os.remove(os.path.join(spdir, fn))
                        except Exception:
                            pass
            # re-merge (will create fresh empty master)
            merge_individual_jsons(self.output_dir)
            # update watcher mtime base
            self._update_master_mtime()
            self.populate_cleaned_files(self.dir_var.get())
            if getattr(self, "current_file", None):
                self.select_file_and_refresh(self.current_file)
            self.status_var.set("Reset All: removed JSON data and specimen specs.")
        except Exception as e:
            self.status_var.set(f"Reset All failed: {e}")

    # ---------------- ultimate (single-file) ----------------
    def action_ultimate(self):
        if not self.current_file:
            self.status_var.set("Select a file first.")
            return
        self.status_var.set("Computing ultimate...")
        t = threading.Thread(target=self._worker_ultimate, args=(self.current_file,), daemon=True)
        t.start()

    def _worker_ultimate(self, filepath):
        try:
            df = pd.read_csv(filepath)
            names = detect_columns(df)
            if names.get("stress"):
                u = float(df[names["stress"]].astype(float).max())
            else:
                u = None
                for c in df.columns:
                    if "stress" in str(c).lower():
                        u = float(df[c].astype(float).max())
                        break
            if u is None:
                self.root.after(0, lambda: self.status_var.set("Ultimate failed: no stress column"))
                return
            if not self.output_dir:
                self.root.after(0, lambda: self.status_var.set("Set output dir first."))
                return
            master = load_master(self.output_dir)
            master.setdefault(os.path.basename(filepath), {})["ultimate"] = u
            save_master(self.output_dir, master)
            # touch to ensure watcher picks it up immediately
            try:
                p = master_json_path(self.output_dir)
                if p:
                    os.utime(p, None)
            except Exception:
                pass
            merge_individual_jsons(self.output_dir)
            self.root.after(0, lambda: (self.select_file_and_refresh(filepath), self.status_var.set(f"Ultimate: {u}")))
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"Ultimate failed: {e}"))

    # ---------------- batch auto ultimate (separate from single-file) ----------------
    def batch_auto_ultimate(self):
        if not hasattr(self, "all_files") or not self.all_files:
            self.status_var.set("No files to process.")
            return
        if not self.output_dir:
            self.status_var.set("Set directory first.")
            return
        self._batch_start("Batch Auto Ultimate started...")
        def worker():
            try:
                master = load_master(self.output_dir) if self.output_dir else {}
                total = len(self.all_files)
                for idx, f in enumerate(self.all_files, start=1):
                    if self.batch_stop:
                        break
                    fname = os.path.basename(f)
                    self.root.after(0, lambda f=f, idx=idx: self.status_var.set(f"Auto Ultimate {idx}/{total}: {os.path.basename(f)}"))
                    try:
                        df = pd.read_csv(f)
                        names = detect_columns(df)
                        if names.get("stress"):
                            u = float(df[names["stress"]].astype(float).max())
                        else:
                            u = None
                            for c in df.columns:
                                if "stress" in str(c).lower():
                                    u = float(df[c].astype(float).max())
                                    break
                        if u is None:
                            continue
                        master.setdefault(fname, {})["ultimate"] = u
                        save_master(self.output_dir, master)
                        # touch file for watcher
                        try:
                            p = master_json_path(self.output_dir)
                            if p:
                                os.utime(p, None)
                        except Exception:
                            pass
                        merge_individual_jsons(self.output_dir)
                        self.root.after(0, lambda f=f: self.select_file_and_refresh(f))
                    except Exception:
                        pass
                self.root.after(0, lambda: self._batch_end("Batch Auto Ultimate completed.", "Batch Auto Ultimate stopped."))
            except Exception as e:
                self.root.after(0, lambda: self.status_var.set(f"Batch Auto Ultimate failed: {e}"))
        t = threading.Thread(target=worker, daemon=True)
        t.start()

    # ---------------- batch controls / helpers ----------------
    def _batch_start(self, msg):
        self.batch_stop = False
        self.status_var.set(msg)

    def _batch_end(self, finished_message, stopped_message=None):
        if self.batch_stop:
            self.status_var.set(stopped_message or "Batch stopped.")
        else:
            self.status_var.set(finished_message)
        # ensure stop cleared after short delay
        def clear():
            self.batch_stop = False
        self.root.after(500, clear)

    def stop_batch(self):
        self.batch_stop = True
        self.status_var.set("Batch stop requested...")

    # Minimal placeholders to preserve UI; they open the full interactive windows implemented below
    def batch_auto_modulus(self):
        if not hasattr(self, "all_files") or not self.all_files:
            self.status_var.set("No files to process.")
            return
        if not self.output_dir:
            self.status_var.set("Set directory first.")
            return
        self._batch_start("Batch Auto Modulus started...")
        t = threading.Thread(target=self._batch_modulus_thread, daemon=True)
        t.start()

    def _batch_modulus_thread(self):
        try:
            jpath = os.path.join(self.output_dir, "modulus_results.json")
            data = {}
            if os.path.exists(jpath):
                try:
                    with open(jpath, "r", encoding="utf-8") as jf:
                        data = json.load(jf)
                except Exception:
                    data = {}
            total = len(self.all_files)
            for idx, f in enumerate(self.all_files, start=1):
                if self.batch_stop:
                    break
                fname = os.path.basename(f)
                if fname in data and data.get(fname, {}).get("modulus") is not None:
                    continue
                self.root.after(0, lambda f=f, idx=idx: self.status_var.set(f"Auto Modulus {idx}/{total}: {os.path.basename(f)}"))
                mod = compute_auto_modulus(f)
                if mod is not None:
                    data[fname] = {"modulus": mod, "length": None, "area": None}
                    write_json_safe(jpath, data)
                    merge_individual_jsons(self.output_dir)
                    # touch master
                    try:
                        p = master_json_path(self.output_dir)
                        if p:
                            os.utime(p, None)
                    except Exception:
                        pass
                    self.root.after(0, lambda f=f: self.select_file_and_refresh(f))
            self.root.after(0, lambda: self._batch_end("Batch Auto Modulus completed.", "Batch Auto Modulus stopped."))
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"Batch auto modulus failed: {e}"))

    def batch_auto_yield(self):
        if not hasattr(self, "all_files") or not self.all_files:
            self.status_var.set("No files to process.")
            return
        if not self.output_dir:
            self.status_var.set("Set directory first.")
            return
        self._batch_start("Batch Auto Yield started...")
        t = threading.Thread(target=self._batch_yield_thread, daemon=True)
        t.start()

    def _batch_yield_thread(self):
        try:
            jmod = os.path.join(self.output_dir, "modulus_results.json")
            jpath = os.path.join(self.output_dir, "yield_results.json")
            mods = {}
            if os.path.exists(jmod):
                try:
                    with open(jmod, "r", encoding="utf-8") as jf:
                        mods = json.load(jf)
                except Exception:
                    mods = {}
            yld = {}
            if os.path.exists(jpath):
                try:
                    with open(jpath, "r", encoding="utf-8") as jf:
                        yld = json.load(jf)
                except Exception:
                    yld = {}
            total = len(self.all_files)
            for idx, f in enumerate(self.all_files, start=1):
                if self.batch_stop:
                    break
                fname = os.path.basename(f)
                if fname in yld:
                    continue
                mod_entry = mods.get(fname)
                mod_val = None
                if isinstance(mod_entry, dict):
                    mod_val = mod_entry.get("modulus")
                elif isinstance(mod_entry, (int, float, str)):
                    try:
                        mod_val = float(mod_entry)
                    except Exception:
                        mod_val = None
                if not mod_val:
                    continue
                self.root.after(0, lambda f=f, idx=idx: self.status_var.set(f"Auto Yield {idx}/{total}: {os.path.basename(f)}"))
                ystr, yst = compute_yield_from_mod(f, mod_val)
                if ystr is not None:
                    yld[fname] = {"strain": ystr, "stress": yst}
                    write_json_safe(jpath, yld)
                    merge_individual_jsons(self.output_dir)
                    try:
                        p = master_json_path(self.output_dir)
                        if p:
                            os.utime(p, None)
                    except Exception:
                        pass
                    self.root.after(0, lambda f=f: self.select_file_and_refresh(f))
            self.root.after(0, lambda: self._batch_end("Batch Auto Yield completed.", "Batch Auto Yield stopped."))
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"Batch auto yield failed: {e}"))

    # Manual batch wrappers that step through files and call UI windows
    def batch_manual_modulus(self):
        if not hasattr(self, "all_files") or not self.all_files:
            self.status_var.set("No files to process.")
            return
        if not self.output_dir:
            self.status_var.set("Set directory first.")
            return
        self._batch_start("Batch Manual Modulus started...")
        files = list(self.all_files)
        idx = 0
        def process_next():
            nonlocal idx
            if self.batch_stop:
                self._batch_end("Batch Manual Modulus completed.", "Batch Manual Modulus stopped.")
                self.populate_cleaned_files(self.dir_var.get()); return
            if idx >= len(files):
                self._batch_end("Batch Manual Modulus completed.", "Batch Manual Modulus stopped.")
                self.populate_cleaned_files(self.dir_var.get()); return
            f = files[idx]; idx += 1
            self.status_var.set(f"Processing {idx}/{len(files)}: {os.path.basename(f)} (Modulus)")
            self._create_modulus_window(f, on_next=process_next)
        process_next()

    def batch_manual_yield(self):
        if not hasattr(self, "all_files") or not self.all_files: self.status_var.set("No files to process."); return
        if not self.output_dir: self.status_var.set("Set directory first."); return
        self._batch_start("Batch Manual Yield started...")
        files = list(self.all_files); idx = 0
        def process_next():
            nonlocal idx
            if self.batch_stop:
                self._batch_end("Batch Manual Yield completed.", "Batch Manual Yield stopped."); self.populate_cleaned_files(self.dir_var.get()); return
            if idx >= len(files):
                self._batch_end("Batch Manual Yield completed.", "Batch Manual Yield stopped."); self.populate_cleaned_files(self.dir_var.get()); return
            f = files[idx]; idx += 1
            self.status_var.set(f"Processing {idx}/{len(files)}: {os.path.basename(f)} (Yield)")
            self._create_yield_window(f, on_next=process_next)
        process_next()

    def batch_manual_break(self):
        if not hasattr(self, "all_files") or not self.all_files: self.status_var.set("No files to process."); return
        if not self.output_dir: self.status_var.set("Set directory first."); return
        self._batch_start("Batch Manual Break started...")
        files = list(self.all_files); idx = 0
        def process_next():
            nonlocal idx
            if self.batch_stop:
                self._batch_end("Batch Manual Break completed.", "Batch Manual Break stopped."); self.populate_cleaned_files(self.dir_var.get()); return
            if idx >= len(files):
                self._batch_end("Batch Manual Break completed.", "Batch Manual Break stopped."); self.populate_cleaned_files(self.dir_var.get()); return
            f = files[idx]; idx += 1
            self.status_var.set(f"Processing {idx}/{len(files)}: {os.path.basename(f)} (Break)")
            self._create_break_window(f, on_next=process_next)
        process_next()

    def batch_manual_all(self): self.status_var.set("Batch Manual All started."); self._batch_start("Batch Manual All started..."); self.batch_manual_modulus()

    # ---------------- Modulus / Yield / Breakpoint windows ----------------
    def action_modulus(self):
        if not self.current_file:
            self.status_var.set("Select a file first."); return
        if not self.output_dir:
            self.status_var.set("Set directory first (press Set)."); return
        self._create_modulus_window(self.current_file)

    def _create_modulus_window(self, filepath, on_next=None):
        win = tk.Toplevel(self.root)
        win.title(f"Modulus — {os.path.basename(filepath)}")
        win.geometry("920x620")
        left = ttk.Frame(win); left.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        right = ttk.Frame(win, width=260); right.pack(side="right", fill="y", padx=6, pady=6)

        fig = Figure(figsize=(6,4)); ax = fig.add_subplot(111)
        canvas = FigureCanvasTkAgg(fig, master=left); canvas.get_tk_widget().pack(fill="both", expand=True)
        toolbar = NavigationToolbar2Tk(canvas, left); toolbar.update(); toolbar.pack(fill="x")

        df = pd.read_csv(filepath)
        names = detect_columns(df)
        ss_ok = bool(names["strain"] and names["stress"])
        fd_ok = bool(names["disp"] and names["force"])
        plot_choice = tk.StringVar(value="Stress–Strain" if ss_ok else ("Force–Displacement" if fd_ok else "Auto"))

        ttk.Label(right, text="Plot Type").pack(anchor="w", pady=(4,2))
        ttk.Radiobutton(right, text="Stress–Strain", variable=plot_choice, value="Stress–Strain").pack(anchor="w")
        ttk.Radiobutton(right, text="Force–Displacement", variable=plot_choice, value="Force–Displacement").pack(anchor="w")
        ttk.Separator(right).pack(fill="x", pady=6)

        len_var = tk.DoubleVar(value=self.charl)
        ttk.Label(right, text="Gauge length L0 (mm):").pack(anchor="w", pady=(6,0))
        ttk.Entry(right, textvariable=len_var).pack(fill="x")

        area_var = tk.DoubleVar(value=self.area)
        ttk.Label(right, text="Area A (mm²):").pack(anchor="w", pady=(6,0))
        ttk.Entry(right, textvariable=area_var).pack(fill="x")

        slope_label_var = tk.StringVar(value="Slope: N/A")
        ttk.Label(right, textvariable=slope_label_var, font=("Segoe UI", 10, "bold")).pack(pady=10)

        # attempt to pre-load specimen area
        try:
            specjson = os.path.join(self.output_dir or "", "Clean Files", "specimenSpecs", os.path.splitext(os.path.basename(filepath))[0] + ".json")
            if os.path.exists(specjson):
                with open(specjson, "r", encoding="utf-8") as sf:
                    specs = json.load(sf)
                if "Width" in specs and "Thickness" in specs:
                    area_var.set(float(specs["Width"]) * float(specs["Thickness"]))
        except Exception:
            pass

        SELECT_X = []; SELECT_Y = []; selection_artists = []
        prev_artists = []  # overlay for previously saved points/line

        # try to read previously saved points (if any) so we can show them on load/redraw:
        win._previous_points = None
        try:
            jpath = os.path.join(self.output_dir or os.path.dirname(filepath), "modulus_results.json")
            if os.path.exists(jpath):
                with open(jpath, "r", encoding="utf-8") as jf:
                    _tmp = json.load(jf)
                entry = _tmp.get(os.path.basename(filepath))
                if entry and "points" in entry:
                    win._previous_points = entry["points"]  # list of [ [x,y], [x,y] ]
                    win._previous_plot_type = entry.get("plot_type")
        except Exception:
            win._previous_points = None

        def draw_plot():
            ax.clear()
            try:
                if plot_choice.get() == "Stress–Strain" and ss_ok:
                    x = df[names["strain"]].astype(float).values; y = df[names["stress"]].astype(float).values
                    ax.plot(x, y, '.', ms=1); ax.set_xlabel("Strain"); ax.set_ylabel("Stress")
                elif plot_choice.get() == "Force–Displacement" and fd_ok:
                    x = df[names["disp"]].astype(float).values; y = df[names["force"]].astype(float).values
                    ax.plot(x, y, '.', ms=1); ax.set_xlabel("Displacement"); ax.set_ylabel("Force")
                else:
                    nums = df.select_dtypes(include=[np.number]).columns.tolist()
                    if len(nums) >= 2:
                        ax.plot(df[nums[0]].astype(float).values, df[nums[1]].astype(float).values, '.', ms=1)
                        ax.set_xlabel(nums[0]); ax.set_ylabel(nums[1])
                ax.set_title(f"{os.path.basename(filepath)}\n{plot_choice.get()} (Select two points)")
                ax.legend(); ax.grid(True, linestyle=':', linewidth=0.5)
            except Exception:
                ax.text(0.5,0.5,"Plot failed", ha='center')

            # clear interactive selections
            SELECT_X.clear(); SELECT_Y.clear()
            for art in selection_artists:
                try: art.remove()
                except Exception: pass
            selection_artists.clear()
            slope_label_var.set("Slope: N/A")

            # remove old prev_artists and redraw previous saved overlay if present
            for art in prev_artists:
                try: art.remove()
                except Exception: pass
            prev_artists.clear()
            if getattr(win, "_previous_points", None):
                pts = win._previous_points
                if isinstance(pts, list) and len(pts) >= 2:
                    try:
                        x0, y0 = float(pts[0][0]), float(pts[0][1])
                        x1, y1 = float(pts[1][0]), float(pts[1][1])
                        pa = ax.plot([x0, x1], [y0, y1], '-', linewidth=2)[0]; prev_artists.append(pa)
                        ca = ax.plot([x0, x1], [y0, y1], 'o', ms=8, mec='blue', mfc='none', linestyle='')[0]; prev_artists.append(ca)
                    except Exception:
                        pass

            canvas.draw_idle()

        draw_plot()

        def onclick(event):
            if event.inaxes != ax: return
            try:
                if plot_choice.get() == "Stress–Strain" and ss_ok:
                    xdata = df[names["strain"]].astype(float).values; ydata = df[names["stress"]].astype(float).values
                elif plot_choice.get() == "Force–Displacement" and fd_ok:
                    xdata = df[names["disp"]].astype(float).values; ydata = df[names["force"]].astype(float).values
                else:
                    nums = df.select_dtypes(include=[np.number]).columns.tolist()
                    if len(nums) < 2: return
                    xdata = df[nums[0]].astype(float).values; ydata = df[nums[1]].astype(float).values
            except Exception:
                return
            if event.xdata is None or event.ydata is None:
                return
            dx = xdata - event.xdata; dy = ydata - event.ydata
            dist = np.hypot(dx, dy)
            if dist.size == 0 or not np.isfinite(dist).any(): return
            idx = int(np.nanargmin(dist))
            x_sel = float(xdata[idx]); y_sel = float(ydata[idx])
            SELECT_X.append(x_sel); SELECT_Y.append(y_sel)
            art = ax.plot([x_sel], [y_sel], marker='o', ms=8, mec='red', mfc='none', linestyle='')[0]; selection_artists.append(art)
            if len(SELECT_X) >= 2:
                x0, x1 = SELECT_X[-2], SELECT_X[-1]; y0, y1 = SELECT_Y[-2], SELECT_Y[-1]
                try:
                    ln = ax.plot([x0, x1], [y0, y1], 'r-', linewidth=2)[0]; selection_artists.append(ln)
                except Exception: pass
            canvas.draw_idle()

        canvas.mpl_connect('button_press_event', onclick)

        def clear_selection():
            SELECT_X.clear(); SELECT_Y.clear()
            for art in selection_artists:
                try: art.remove()
                except Exception: pass
            selection_artists.clear(); slope_label_var.set("Slope: N/A"); canvas.draw_idle()

        ttk.Button(right, text="Refresh Graph", command=draw_plot).pack(pady=(6,4), fill="x")
        ttk.Button(right, text="Clear", command=clear_selection).pack(pady=(0,4), fill="x")

        def calc_slope():
            if len(SELECT_X) < 2:
                messagebox.showinfo("Info", "Select two points first."); return
            x0, x1 = SELECT_X[-2], SELECT_X[-1]; y0, y1 = SELECT_Y[-2], SELECT_Y[-1]
            try: L0 = float(len_var.get())
            except Exception: L0 = float(self.charl)
            try: A = float(area_var.get())
            except Exception: A = float(self.area)
            MOD = None
            try:
                if x1 == x0:
                    MOD = None
                elif plot_choice.get() == "Stress–Strain":
                    MOD = round((y1 - y0) / ((x1 - x0) * 10.0), 3)
                else:
                    denom = (x1 - x0)
                    if denom == 0 or A == 0:
                        MOD = None
                    else:
                        MOD_val = ((y1 - y0) * float(L0)) / (float(A) * denom)
                        MOD = round(MOD_val / 10.0, 3)
            except Exception:
                MOD = None

            slope_label_var.set(f"Slope: {MOD}" if MOD is not None else "Slope: ∞")
            win._last_mod = MOD

            # store selected points & chosen plot type on the window for saving later
            try:
                win._selected_points = [[float(SELECT_X[-2]), float(SELECT_Y[-2])], [float(SELECT_X[-1]), float(SELECT_Y[-1])]]
            except Exception:
                win._selected_points = None
            win._plot_type = plot_choice.get()

        ttk.Button(right, text="Calc Slope", command=calc_slope).pack(pady=(0,6), fill="x")

        def finish_save_and_next():
            MOD = getattr(win, "_last_mod", None)
            if MOD is None:
                messagebox.showinfo("No slope", "No slope to save."); return
            selected_pts = getattr(win, "_selected_points", None)
            plot_t = getattr(win, "_plot_type", plot_choice.get())
            self._save_modulus_result(filepath, MOD, float(len_var.get()), float(area_var.get()),
                                    selected_points=selected_pts, plot_type=plot_t)
            plot_dir = os.path.join(self.output_dir or os.path.dirname(filepath), "Modulus Plots"); os.makedirs(plot_dir, exist_ok=True)
            try: fig.savefig(os.path.join(plot_dir, f"{os.path.basename(filepath)}_modulus.png"))
            except Exception: pass
            self.select_file_and_refresh(filepath); win.destroy()
            if callable(on_next): self.root.after(50, on_next)

        def skip_and_next():
            win.destroy()
            if callable(on_next): self.root.after(50, on_next)

        def finish_save_only():
            MOD = getattr(win, "_last_mod", None)
            if MOD is None:
                messagebox.showinfo("No slope", "No slope to save."); return
            selected_pts = getattr(win, "_selected_points", None)
            plot_t = getattr(win, "_plot_type", plot_choice.get())
            self._save_modulus_result(filepath, MOD, float(len_var.get()), float(area_var.get()),
                                    selected_points=selected_pts, plot_type=plot_t)
            try: fig.savefig(os.path.join(self.output_dir or os.path.dirname(filepath), "Modulus Plots", f"{os.path.basename(filepath)}_modulus.png"))
            except Exception: pass
            self.select_file_and_refresh(filepath); win.destroy()
            if callable(on_next): self.root.after(50, on_next)

        ttk.Button(right, text="Save & Next", command=finish_save_and_next).pack(pady=(6,4), fill="x")
        ttk.Button(right, text="Skip / Next", command=skip_and_next).pack(pady=(0,4), fill="x")
        ttk.Button(right, text="Save Only & Close", command=finish_save_only).pack(pady=(0,4), fill="x")
        ttk.Button(right, text="Exit", command=lambda: (win.destroy())).pack(pady=6, fill="x")

        def see_previous():
            # load saved result for this file and overlay on current plot
            jpath = os.path.join(self.output_dir or os.path.dirname(filepath), "modulus_results.json")
            if not os.path.exists(jpath):
                messagebox.showinfo("No previous", "No saved modulus results found.")
                return
            try:
                with open(jpath, "r", encoding="utf-8") as jf:
                    data = json.load(jf)
                entry = data.get(os.path.basename(filepath))
                if not entry or "points" not in entry:
                    messagebox.showinfo("No previous", "No saved selection found for this file.")
                    return
                pts = entry["points"]
                win._previous_points = pts
                win._previous_plot_type = entry.get("plot_type")
                # redraw plot (draw_plot will pick up win._previous_points)
                draw_plot()
            except Exception:
                messagebox.showwarning("Error", "Failed to read previous saved points.")

        ttk.Button(right, text="See Previous", command=see_previous).pack(pady=(4,4), fill="x")

        def on_close():
            try: win.destroy()
            except Exception: pass
            if callable(on_next): self.root.after(50, on_next)

        win.protocol("WM_DELETE_WINDOW", on_close)


    def _save_modulus_result(self, filepath, modulus_val, length_val, area_val, selected_points=None, plot_type=None):
        """
        Saves modulus result into modulus_results.json. New fields:
        - points: [[x0, y0], [x1, y1]] (if provided)
        - plot_type: "Stress–Strain" or "Force–Displacement" (if provided)
        """
        jpath = os.path.join(self.output_dir or os.path.dirname(filepath), "modulus_results.json")
        if os.path.exists(jpath):
            try:
                with open(jpath, "r", encoding="utf-8") as jf:
                    data = json.load(jf)
            except Exception:
                data = {}
        else:
            data = {}

        key = os.path.basename(filepath)
        entry = data.get(key, {})
        entry.update({"modulus": modulus_val, "length": length_val, "area": area_val})
        if selected_points is not None:
            # ensure it's serializable floats
            try:
                entry["points"] = [[float(selected_points[0][0]), float(selected_points[0][1])],
                                [float(selected_points[1][0]), float(selected_points[1][1])]]
            except Exception:
                # fallback: ignore if malformed
                entry.pop("points", None)
        if plot_type is not None:
            entry["plot_type"] = plot_type

        data[key] = entry
        write_json_safe(jpath, data)

        # merge and touch master
        merge_individual_jsons(self.output_dir)
        try:
            p = master_json_path(self.output_dir)
            if p: os.utime(p, None)
        except Exception:
            pass

    # --- Yield and Break windows (kept fully featured) ---
    def action_yield(self):
        if not self.current_file:
            self.status_var.set("Select a file first."); return
        if not self.output_dir:
            self.status_var.set("Set directory first."); return
        self._create_yield_window(self.current_file)

    def _create_yield_window(self, filepath, on_next=None):
        win = tk.Toplevel(self.root); win.title(f"Yield — {os.path.basename(filepath)}"); win.geometry("1000x700")
        left = ttk.Frame(win); left.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        right = ttk.Frame(win, width=320); right.pack(side="right", fill="y", padx=6, pady=6)
        fig = Figure(figsize=(7,5)); ax = fig.add_subplot(111)
        canvas = FigureCanvasTkAgg(fig, master=left); canvas.get_tk_widget().pack(fill="both", expand=True)
        toolbar = NavigationToolbar2Tk(canvas, left); toolbar.update(); toolbar.pack(fill="x")

        try:
            df = pd.read_csv(filepath).drop(0)
        except Exception:
            df = pd.read_csv(filepath)

        names = detect_columns(df)
        ss_ok = bool(names["strain"] and names["stress"])
        fd_ok = bool(names["disp"] and names["force"])
        plot_choice = tk.StringVar(value="Stress–Strain" if ss_ok else ("Force–Displacement" if fd_ok else "Stress–Strain"))
        ttk.Label(right, text="Plot Type").pack(anchor="w")
        ttk.Radiobutton(right, text="Stress–Strain", variable=plot_choice, value="Stress–Strain").pack(anchor="w")
        ttk.Radiobutton(right, text="Force–Displacement", variable=plot_choice, value="Force–Displacement").pack(anchor="w")
        ttk.Separator(right).pack(fill="x", pady=6)

        # Gauge length and area (defaults -> global, but try specimen specs json first)
        len_var = tk.DoubleVar(value=self.charl)
        ttk.Label(right, text="Gauge length L0 (mm):").pack(anchor="w", pady=(6,0))
        ttk.Entry(right, textvariable=len_var).pack(fill="x")

        area_var = tk.DoubleVar(value=self.area)
        ttk.Label(right, text="Area A (mm²):").pack(anchor="w", pady=(6,0))
        ttk.Entry(right, textvariable=area_var).pack(fill="x")

        # try to pre-load specimen area (and optionally length) from specimenSpecs json like in modulus window
        try:
            specjson = os.path.join(self.output_dir or "", "Clean Files", "specimenSpecs", os.path.splitext(os.path.basename(filepath))[0] + ".json")
            if os.path.exists(specjson):
                with open(specjson, "r", encoding="utf-8") as sf:
                    specs = json.load(sf)
                # If Width and Thickness present, set area (this overrides default)
                if "Width" in specs and "Thickness" in specs:
                    try:
                        area_var.set(float(specs["Width"]) * float(specs["Thickness"]))
                    except Exception:
                        pass
                # If GaugeLength present in specs, set len_var (optional field name - adapt if yours differs)
                if "GaugeLength" in specs or "L0" in specs:
                    val = specs.get("GaugeLength", specs.get("L0"))
                    try:
                        len_var.set(float(val))
                    except Exception:
                        pass
        except Exception:
            pass

        ttk.Label(right, text="Offset %").pack(anchor="w", pady=(8,0))
        offset_var = tk.DoubleVar(value=0.2); ttk.Entry(right, textvariable=offset_var).pack(fill="x")
        ttk.Separator(right).pack(fill="x", pady=6)

        ttk.Label(right, text="Plot / Save options").pack(anchor="w", pady=(6,2))
        res_var = tk.DoubleVar(value=0.0001); ttk.Label(right, text="Resolution (strain step)").pack(anchor="w"); ttk.Entry(right, textvariable=res_var).pack(fill="x")
        result_var = tk.StringVar(value="Yield result: N/A"); ttk.Label(right, textvariable=result_var, wraplength=300).pack(pady=(8,8))

        def draw_initial():
            ax.clear()
            try:
                if plot_choice.get() == "Stress–Strain" and ss_ok:
                    x = df[names["strain"]].astype(float).values; y = df[names["stress"]].astype(float).values
                    ax.scatter(x, y, s=10, label="Stress-Strain"); ax.set_xlabel("Strain"); ax.set_ylabel("Stress")
                elif plot_choice.get() == "Force–Displacement" and fd_ok:
                    x = df[names["disp"]].astype(float).values; y = df[names["force"]].astype(float).values
                    ax.scatter(x, y, s=10, label="Force-Disp"); ax.set_xlabel("Displacement"); ax.set_ylabel("Force")
                else:
                    nums = df.select_dtypes(include=[np.number]).columns.tolist()
                    if len(nums) >= 2:
                        x = df[nums[0]].astype(float).values; y = df[nums[1]].astype(float).values; ax.scatter(x, y, s=10)
                ax.grid(True, linestyle=':', linewidth=0.6); ax.set_title(os.path.basename(filepath)); canvas.draw_idle()
            except Exception:
                ax.text(0.5,0.5,"Plot failed", ha='center'); canvas.draw_idle()
        draw_initial()

        def compute_and_save_internal_ss():
            try: offset = float(offset_var.get())
            except Exception: offset = 0.2
            try: resolution = float(res_var.get())
            except Exception: resolution = 0.0001

            # get modulus (same as before)
            mod_val = None
            try:
                jpath = os.path.join(self.output_dir, "modulus_results.json")
                if os.path.exists(jpath):
                    with open(jpath, "r", encoding="utf-8") as jf:
                        d = json.load(jf)
                    entry = d.get(os.path.basename(filepath))
                    if isinstance(entry, dict):
                        mod_val = entry.get("modulus")
                    elif isinstance(entry, (int, float, str)):
                        try: mod_val = float(entry)
                        except Exception: mod_val = None
            except Exception:
                mod_val = None

            if not mod_val:
                messagebox.showerror("Missing Modulus", "Modulus not calculated for this file. Compute modulus first.")
                self.status_var.set("Yield skipped: modulus missing."); return False

            try:
                try:
                    df_local = pd.read_csv(filepath).drop(0)
                except Exception:
                    df_local = pd.read_csv(filepath)
                names_local = detect_columns(df_local)
                if not names_local["strain"] or not names_local["stress"]:
                    messagebox.showerror("Data error", "Stress-Strain data not present."); return False

                X = df_local[names_local["strain"]].astype(float).values
                Y = df_local[names_local["stress"]].astype(float).values

                mod = float(mod_val) * 10.0
                max_strain = 7
                base_strains = np.arange(0.0, max_strain, resolution)
                Xlin = base_strains + offset
                Ylin = mod * (Xlin - offset)

                valid_idxs = np.where(X <= Xlin[-1])[0]
                Xcurv = X[valid_idxs]; Ycurv = Y[valid_idxs]

                denom = np.sqrt(mod ** 2 + 1.0)
                dist_list = []; strains = []; stresses = []
                for x, y in zip(Xcurv, Ycurv):
                    dist = abs(mod * (x - offset) - y) / denom
                    dist_list.append(dist); strains.append(x); stresses.append(y)
                idx_min = int(np.argmin(dist_list))
                yield_strain = round(strains[idx_min], 3); yield_stress = round(stresses[idx_min], 3)

                Xlin_trim = [i for i in Xlin if i <= yield_strain + 0.1]; Ylin_trim = Ylin[:len(Xlin_trim)]
                Xcurv_trim = [i for i in Xcurv if i <= yield_strain + 0.1]; Ycurv_trim = Ycurv[:len(Xcurv_trim)]

                ax.clear()
                ax.plot(Xlin_trim, Ylin_trim, '-', label="Offset Line", linewidth=2)
                ax.scatter(Xcurv_trim, Ycurv_trim, s=20, label="Stress-Strain Curve", alpha=0.9)
                ax.plot([yield_strain], [yield_stress], 'ro', markersize=12, label=f"Yield ({yield_strain}, {yield_stress})")
                ax.set_xlabel("Tensile Strain"); ax.set_ylabel("Tensile Stress"); ax.set_title(f"Yield Point: Strain = {yield_strain}, Stress = {yield_stress}")
                ax.legend(); ax.grid(True, linestyle=':', linewidth=0.6); canvas.draw_idle()

                # save json
                jpath_y = os.path.join(self.output_dir, "yield_results.json")
                if os.path.exists(jpath_y):
                    try:
                        with open(jpath_y, "r", encoding="utf-8") as jf:
                            yield_dict = json.load(jf)
                    except Exception:
                        yield_dict = {}
                else:
                    yield_dict = {}
                yield_dict[os.path.basename(filepath)] = {"strain": yield_strain, "stress": yield_stress}
                write_json_safe(jpath_y, yield_dict)
                merge_individual_jsons(self.output_dir)
                try:
                    p = master_json_path(self.output_dir)
                    if p: os.utime(p, None)
                except Exception:
                    pass
                result_var.set(f"Yield: strain={yield_strain:.4f}, stress={yield_stress:.3f}")
                self.select_file_and_refresh(filepath); self.status_var.set(f"Yield computed & saved: {os.path.basename(filepath)}")
                return True
            except Exception as e:
                messagebox.showerror("Error", f"Yield computation failed: {e}")
                self.status_var.set("Yield computation failed."); return False

        def compute_and_save_internal_fd():
            # Read offset/resolution
            try:
                offset_pct = float(offset_var.get())
            except Exception:
                offset_pct = 0.2
            try:
                resolution = float(res_var.get())
            except Exception:
                resolution = 0.0001

            # get modulus (assumed stored as GPa)
            mod_val = None
            try:
                jpath = os.path.join(self.output_dir, "modulus_results.json")
                if os.path.exists(jpath):
                    with open(jpath, "r", encoding="utf-8") as jf:
                        d = json.load(jf)
                    entry = d.get(os.path.basename(filepath))
                    if isinstance(entry, dict):
                        mod_val = entry.get("modulus")
                    elif isinstance(entry, (int, float, str)):
                        try:
                            mod_val = float(entry)
                        except Exception:
                            mod_val = None
            except Exception:
                mod_val = None

            if not mod_val:
                messagebox.showerror("Missing Modulus", "Modulus not calculated for this file. Compute modulus first.")
                self.status_var.set("Yield skipped: modulus missing.")
                return False

            # Determine L0 and A: prefer specimen spec json, else global, allow GUI override
            try:
                L0_val = float(self.charl)
            except Exception:
                L0_val = 1.0
            try:
                A_val = float(self.area)
            except Exception:
                A_val = 1.0

            try:
                specjson = os.path.join(self.output_dir or "", "Clean Files", "specimenSpecs",
                                        os.path.splitext(os.path.basename(filepath))[0] + ".json")
                if os.path.exists(specjson):
                    with open(specjson, "r", encoding="utf-8") as sf:
                        specs = json.load(sf)
                    if "Width" in specs and "Thickness" in specs:
                        try:
                            A_val = float(specs["Width"]) * float(specs["Thickness"])
                        except Exception:
                            pass
                    if "GaugeLength" in specs or "L0" in specs:
                        val = specs.get("GaugeLength", specs.get("L0"))
                        try:
                            L0_val = float(val)
                        except Exception:
                            pass
            except Exception:
                pass

            # GUI overrides if user changed fields
            try:
                L0_val = float(len_var.get())
            except Exception:
                pass
            try:
                A_val = float(area_var.get())
            except Exception:
                pass

            # Basic validation
            if not np.isfinite(L0_val) or L0_val == 0.0:
                messagebox.showerror("Invalid gauge length", "Invalid gauge length (L0).")
                return False
            if not np.isfinite(A_val) or A_val == 0.0:
                messagebox.showerror("Invalid area", "Invalid specimen area (A).")
                return False

            # convert offset percentage to displacement (mm)
            offset_disp = offset_pct * L0_val/100

            try:
                try:
                    df_local = pd.read_csv(filepath).drop(0)
                except Exception:
                    df_local = pd.read_csv(filepath)
                names_local = detect_columns(df_local)
                if not names_local["disp"] or not names_local["force"]:
                    messagebox.showerror("Data error", "Force-Displacement data not present.")
                    return False

                # Read raw FD arrays (disp in mm, force in kN)
                X_disp = df_local[names_local["disp"]].astype(float).values
                Y_force = df_local[names_local["force"]].astype(float).values

                # Convert modulus to FD stiffness in kN/mm (assume mod_val is GPa)
                # k_kN_per_mm = E_GPa * A_mm2 / L0_mm
                E_GPa = float(mod_val)
                E_kN_per_mm = (E_GPa * float(A_val)) / float(L0_val)
                
                print("E_GPa: " + str(E_GPa))
                print("E_kN_per_mm: " + str(E_kN_per_mm))

                # Build offset line in FD units: force = k * (disp - offset_disp)
                max_disp = float(L0_val)  # search up to gauge length by default
                base_disps = np.arange(0.0, max_disp, resolution)
                Xlin = base_disps + offset_disp
                Ylin = E_kN_per_mm * (Xlin - offset_disp)

                # restrict measured points to same domain as the line
                valid_idxs = np.where(X_disp <= Xlin[-1])[0]
                if valid_idxs.size == 0:
                    messagebox.showerror("Data range", "No FD points fall within offset/line search range.")
                    return False
                Xcurv = X_disp[valid_idxs]
                Ycurv = Y_force[valid_idxs]

                # distance from point (x,y) to line y = k*(x - offset_disp)  -> rewrite as k*x - y - k*offset_disp = 0
                b = -E_kN_per_mm * offset_disp
                denom = np.sqrt(E_kN_per_mm ** 2 + 1.0)
                dist_list = []
                disp_list = []
                force_list = []
                for x, y in zip(Xcurv, Ycurv):
                    # y and Ylin are in kN, x in mm
                    dist = abs(E_kN_per_mm * x + b - y) / denom
                    dist_list.append(dist)
                    disp_list.append(x)
                    force_list.append(y)

                idx_min = int(np.argmin(dist_list))
                yield_disp_mm = round(disp_list[idx_min], 3)    # displacement in mm
                yield_force_kN = round(force_list[idx_min], 3)  # force in kN

                # compute equivalent strain & stress for record (strain = disp/L0, stress = force/A)
                yield_strain = round(yield_disp_mm*100 / float(L0_val), 6)
                yield_stress = round(yield_force_kN*1000 / float(A_val), 6)  # force(kN)/area(mm2) -> kN/mm2; user may convert elsewhere

                # Trim for plotting
                Xlin_trim = [i for i in Xlin if i <= yield_disp_mm + 0.1]
                Ylin_trim = Ylin[:len(Xlin_trim)]
                Xcurv_trim = [i for i in Xcurv if i <= yield_disp_mm + 0.1]
                Ycurv_trim = Ycurv[:len(Xcurv_trim)]

                ax.clear()
                ax.plot(Xlin_trim, Ylin_trim, '-', label=f"Offset Line (k={E_kN_per_mm:.3f} kN/mm)", linewidth=2)
                ax.scatter(Xcurv_trim, Ycurv_trim, s=20, label="Force-Displacement (kN/mm)", alpha=0.9)
                ax.plot([yield_disp_mm], [yield_force_kN], 'ro', markersize=12,
                        label=f"Yield disp={yield_disp_mm} mm, force={yield_force_kN} kN")
                ax.set_xlabel("Displacement (mm)")
                ax.set_ylabel("Force (kN)")
                ax.set_title(f"Yield Point (from FD): Disp = {yield_disp_mm} mm, Force = {yield_force_kN} kN \n Yield Strain = {yield_strain} %, Yield Stress = {yield_stress} MPa")
                ax.legend(); ax.grid(True, linestyle=':', linewidth=0.6); canvas.draw_idle()

                # save json (store both FD and equivalent strain/stress and the L0/A used)
                jpath_y = os.path.join(self.output_dir, "yield_results.json")
                if os.path.exists(jpath_y):
                    try:
                        with open(jpath_y, "r", encoding="utf-8") as jf:
                            yield_dict = json.load(jf)
                    except Exception:
                        yield_dict = {}
                else:
                    yield_dict = {}

                yield_entry = {
                    "strain": float(yield_strain),
                    "stress": float(yield_stress),
                }
                yield_dict[os.path.basename(filepath)] = yield_entry
                write_json_safe(jpath_y, yield_dict)
                merge_individual_jsons(self.output_dir)
                try:
                    p = master_json_path(self.output_dir)
                    if p:
                        os.utime(p, None)
                except Exception:
                    pass

                result_var.set(f"Yield: disp={yield_disp_mm:.3f} mm, force={yield_force_kN:.3f} kN")
                self.select_file_and_refresh(filepath)
                self.status_var.set(f"Yield computed & saved: {os.path.basename(filepath)}")
                return True

            except Exception as e:
                messagebox.showerror("Error", f"Yield computation failed: {e}")
                self.status_var.set("Yield computation failed.")
                return False

        
        
        def compute_and_save_and_next():
            saved = compute_and_save_internal_fd() if plot_choice.get() == "Force–Displacement" else compute_and_save_internal_ss
            if saved: win.destroy()
            if callable(on_next): self.root.after(50, on_next)

        def skip_and_next():
            win.destroy()
            if callable(on_next): self.root.after(50, on_next)

        def compute_and_save_only():
            # default uses SS routine; if user selected FD, call FD routine instead
            if plot_choice.get() == "Force–Displacement":
                compute_and_save_internal_fd()
            else:
                compute_and_save_internal_ss()

        ttk.Button(right, text="Refresh Graph", command=draw_initial).pack(pady=6, fill="x")
        ttk.Button(right, text="Recompute Modulus", command=self.action_modulus).pack(pady=6, fill="x")
        ttk.Button(right, text="Skip / Next", command=skip_and_next).pack(pady=6, fill="x")
        ttk.Button(right, text="Compute & Save Only", command=compute_and_save_only).pack(pady=6, fill="x")
        ttk.Button(right, text="Exit", command=lambda: (win.destroy(), None)).pack(pady=6, fill="x")

        def on_close():
            try: win.destroy()
            except Exception: pass
            if callable(on_next): self.root.after(50, on_next)

        win.protocol("WM_DELETE_WINDOW", on_close)

    def action_breakpoint(self):
        if not self.current_file:
            self.status_var.set("Select a file first."); return
        if not self.output_dir:
            self.status_var.set("Set directory first."); return
        self._create_break_window(self.current_file)

    def _create_break_window(self, filepath, on_next=None):
        win = tk.Toplevel(self.root); win.title(f"Break Point — {os.path.basename(filepath)}"); win.geometry("920x620")
        left = ttk.Frame(win); left.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        right = ttk.Frame(win, width=260); right.pack(side="right", fill="y", padx=6, pady=6)
        fig = Figure(figsize=(6,4)); ax = fig.add_subplot(111)
        canvas = FigureCanvasTkAgg(fig, master=left); canvas.get_tk_widget().pack(fill="both", expand=True)
        toolbar = NavigationToolbar2Tk(canvas, left); toolbar.update(); toolbar.pack(fill="x")
        df = pd.read_csv(filepath); names = detect_columns(df); ss_ok = bool(names["strain"] and names["stress"]); fd_ok = bool(names["disp"] and names["force"])
        mode_var = tk.StringVar(value="Select")
        ttk.Label(right, text="Mode").pack(anchor="w"); ttk.Radiobutton(right, text="Select", variable=mode_var, value="Select").pack(anchor="w")
        ttk.Radiobutton(right, text="Pan/Zoom", variable=mode_var, value="Pan").pack(anchor="w")
        sel = {"x": None, "y": None}
        def draw():
            ax.clear()
            try:
                if ss_ok:
                    x = df[names["strain"]].astype(float).values; y = df[names["stress"]].astype(float).values; ax.plot(x, y, '.', ms=2, label="Stress-Strain"); ax.set_xlabel("Strain"); ax.set_ylabel("Stress")
                elif fd_ok:
                    x = df[names["disp"]].astype(float).values; y = df[names["force"]].astype(float).values; ax.plot(x, y, '.', ms=2, label="Disp-Force"); ax.set_xlabel("Disp"); ax.set_ylabel("Force")
                else:
                    nums = df.select_dtypes(include=[np.number]).columns.tolist()
                    if len(nums) >= 2:
                        x = df[nums[0]].astype(float).values; y = df[nums[1]].astype(float).values; ax.plot(x, y, '.', ms=2)
                ax.set_title(os.path.basename(filepath)); ax.grid(True, linestyle=':', linewidth=0.6)
            except Exception:
                ax.text(0.5,0.5,"Plot failed", ha='center')
            canvas.draw_idle()
        draw()
        ttk.Button(right, text="Refresh Graph", command=draw).pack(pady=6, fill="x")
        def onclick(event):
            try:
                if event.inaxes != ax or mode_var.get() != "Select":
                    return
                if event.xdata is None or event.ydata is None:
                    return
                lines = [ln for ln in ax.lines if ln.get_xdata().size > 0]
                if not lines:
                    return
                line = lines[0]
                xdata = np.asarray(line.get_xdata(), dtype=float); ydata = np.asarray(line.get_ydata(), dtype=float)
                dx = xdata - event.xdata; dy = ydata - event.ydata
                dist = np.hypot(dx, dy)
                if dist.size == 0 or not np.isfinite(dist).any():
                    return
                idx = int(np.nanargmin(dist)); sel["x"], sel["y"] = float(xdata[idx]), float(ydata[idx])
                ax.plot([sel["x"]], [sel["y"]], 'ro', ms=8); canvas.draw_idle()
            except Exception:
                return
        canvas.mpl_connect("button_press_event", onclick)
        def save_break_and_next():
            if sel["x"] is None:
                messagebox.showinfo("No selection", "Select a break point first."); return
            json_path = os.path.join(self.output_dir, "break_results.json")
            fname = os.path.basename(filepath)
            bd = {}
            if os.path.exists(json_path):
                try:
                    with open(json_path, "r", encoding="utf-8") as jf:
                        bd = json.load(jf)
                except Exception:
                    bd = {}
            bd[fname] = [round(sel["x"], 6), round(sel["y"], 3)]
            write_json_safe(json_path, bd)
            try:
                merge_individual_jsons(self.output_dir)
                p = master_json_path(self.output_dir)
                if p: os.utime(p, None)
            except Exception:
                pass
            self.select_file_and_refresh(filepath); win.destroy()
            if callable(on_next): self.root.after(50, on_next)
        def skip_break_and_next():
            win.destroy(); 
            if callable(on_next): self.root.after(50, on_next)
        ttk.Button(right, text="Save Break Point & Next", command=save_break_and_next).pack(pady=6, fill="x")
        ttk.Button(right, text="Skip / Next", command=skip_break_and_next).pack(pady=6, fill="x")
        ttk.Button(right, text="Exit", command=lambda: (win.destroy())).pack(pady=6, fill="x")
        def on_close():
            try: win.destroy()
            except Exception: pass
            if callable(on_next): self.root.after(50, on_next)
        win.protocol("WM_DELETE_WINDOW", on_close)

    # ---------------- Save All to Excel (simple summary) ----------------
    def save_all_to_excel(self):
        if not self.output_dir:
            self.status_var.set("Set directory first.")
            return
        out = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel workbook","*.xlsx")],
                                           initialfile=f"tensile_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        if not out:
            return
        try:
            master = load_master(self.output_dir)
            modp = os.path.join(self.output_dir, "modulus_results.json")
            yldp = os.path.join(self.output_dir, "yield_results.json")
            brkp = os.path.join(self.output_dir, "break_results.json")
            mods = json.load(open(modp)) if os.path.exists(modp) else {}
            ylds = json.load(open(yldp)) if os.path.exists(yldp) else {}
            brks = json.load(open(brkp)) if os.path.exists(brkp) else {}

            rows = []
            all_files = sorted(set(list(mods.keys()) + list(ylds.keys()) + list(brks.keys()) + list(master.keys())))
            for fname in all_files:
                
                m = mods.get(fname)
                y = ylds.get(fname)
                b = brks.get(fname)
                master_entry = master.get(fname, {})
                if isinstance(m, dict):
                    mod_val = m.get("modulus")
                else:
                    mod_val = m
                y_strain = None; y_stress = None
                if isinstance(y, dict):
                    y_strain = y.get("strain"); y_stress = y.get("stress")
                elif isinstance(y, list) and len(y) >= 2:
                    y_strain = y[0]; y_stress = y[1]
                
                b_strain = None; b_stress = None
                if isinstance(b, list) and len(b) >= 2:
                    b_strain = b[0]; b_stress = b[1]
                elif isinstance(b, dict):
                    b_strain = b.get("strain"); b_stress = b.get("stress")
                rows.append({
                    "File": fname,
                    "Modulus": mod_val,
                    "Yield Strain": y_strain,
                    "Yield Stress": y_stress,
                    "Ultimate Stress": master_entry.get("ultimate"),
                    "Break Strain": b_strain,
                    "Break Stress": b_stress
                })

            df_summary = pd.DataFrame(rows, columns=["File", "Modulus", "Yield Strain", "Yield Stress", "Ultimate Stress", "Break Strain", "Break Stress"])

            with pd.ExcelWriter(out, engine="openpyxl") as writer:
                df_summary.to_excel(writer, sheet_name="Summary", index=False)
                if mods:
                    pd.DataFrame.from_dict(mods, orient="index").to_excel(writer, sheet_name="Modulus")
                if ylds:
                    pd.DataFrame.from_dict(ylds, orient="index").to_excel(writer, sheet_name="Yield")
                if brks:
                    pd.DataFrame.from_dict(brks, orient="index").to_excel(writer, sheet_name="Breakpoints")
                if master:
                    pd.DataFrame.from_dict(master, orient="index").to_excel(writer, sheet_name="Master")

            self.status_var.set(f"Saved Excel: {out}")
            messagebox.showinfo("Saved", f"Results saved to:\n{out}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

