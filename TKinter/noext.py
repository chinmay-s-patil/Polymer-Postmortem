#!/usr/bin/env python3
"""
dual_file_gui_demo.py

Lightweight demo GUI that opens from a launcher button.
Layout:
 - Left: file list (bottom half), search/filter and controls (top-left)
 - Right: matplotlib plot area with toolbar
 - Top-left controls: Select (from list), Percent entry + Refresh, Process Selected Pair
 - Footer: unobtrusive CC BY + version + your name

All button callback functions are defined right after imports so they're easy to edit.
"""

# -------------------------
# Imports & callback hooks
# -------------------------
import os
import glob
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

# optional: pandas for CSV reading (falls back to simple CSV)
try:
    import pandas as pd
except Exception:
    pd = None

import numpy as np

# You use VERSION in your gui_core; keeping same value here for attribution.
# Value taken from your gui_core.py. :contentReference[oaicite:1]{index=1}
VERSION = "1.26.8"

# -------------------------
# Button callback functions (edit these freely)
# -------------------------
def browse_folder(gui):
    """Open a folder dialog and refresh the file list for that folder."""
    sel = filedialog.askdirectory(initialdir=os.getcwd())
    if not sel:
        return
    gui.current_dir.set(sel)
    refresh_file_list(gui)

def refresh_file_list(gui):
    """Populate the listbox with CSV/XLSX files found under the chosen directory."""
    folder = gui.current_dir.get().strip()
    gui.file_paths.clear()
    gui.listbox.delete(0, tk.END)
    if not folder or not os.path.isdir(folder):
        gui.status_var.set("Set a valid directory first.")
        return
    # gather files (non-recursive). change to recursive if needed.
    patterns = ["*.csv", "*.CSV", "*.xlsx", "*.XLSX", "*.xls", "*.XLS"]
    files = []
    for p in patterns:
        files.extend(sorted(glob.glob(os.path.join(folder, p))))
    if not files:
        gui.status_var.set("No csv/xlsx files found in directory.")
        return
    for i, p in enumerate(files):
        name = os.path.basename(p)
        gui.file_paths[i] = p
        gui.listbox.insert(tk.END, name)
    gui.status_var.set(f"{len(files)} files listed.")

def select_file_from_list(gui):
    """Select current file (single-select behavior); updates graph with selected file."""
    sel = gui.listbox.curselection()
    if not sel:
        gui.status_var.set("No file selected in list.")
        return
    idx = sel[0]
    path = gui.file_paths.get(idx)
    gui.current_file_path = path
    gui.status_var.set(f"Selected: {os.path.basename(path)}")
    # update plot in background
    threading.Thread(target=update_plot_for_file, args=(gui, path), daemon=True).start()

def set_percent_and_refresh(gui):
    """Read percent entry, store value, and refresh (placeholder)."""
    txt = gui.percent_var.get().strip()
    try:
        val = float(txt)
        gui.percent_value = val
        gui.status_var.set(f"Percent set to {val}%. Refreshing list...")
        # You can modify this to actually filter/process files based on percent
        refresh_file_list(gui)
    except Exception:
        gui.status_var.set("Invalid percent value. Enter a number.")

def process_selected_pair(gui):
    """Take exactly two selected items and process them together (editable)."""
    sel = gui.listbox.curselection()
    if not sel or len(sel) < 2:
        gui.status_var.set("Select exactly two files (Ctrl+Click) to process as a pair.")
        return
    # take first two selected indices (you can alter to pick any two)
    idx0, idx1 = sel[0], sel[1]
    p0 = gui.file_paths.get(idx0)
    p1 = gui.file_paths.get(idx1)
    if not p0 or not p1:
        gui.status_var.set("Couldn't resolve selected file paths.")
        return
    gui.status_var.set(f"Processing pair: {os.path.basename(p0)} + {os.path.basename(p1)}")
    # run processing in a thread so UI remains responsive
    threading.Thread(target=process_two_files, args=(gui, p0, p1), daemon=True).start()

def process_two_files(gui, path_a, path_b):
    """
    Placeholder: process two files together.
    Replace this function with your real processing logic.
    """
    try:
        # simulate work
        import time
        time.sleep(1.0)
        # example: compute number of rows in each (if pandas available)
        ra = rb = None
        if pd is not None:
            try:
                da = pd.read_csv(path_a)
                db = pd.read_csv(path_b)
                ra, rb = len(da), len(db)
            except Exception:
                ra = rb = "?"
        gui.status_var.set(f"Processed pair: {os.path.basename(path_a)} ({ra}), {os.path.basename(path_b)} ({rb})")
    except Exception as e:
        gui.status_var.set(f"Pair processing failed: {e}")

def update_plot_for_file(gui, filepath):
    """
    Read a CSV (or first sheet of xlsx) and plot first two numeric columns.
    Keeps the plotting code separate so it's easy to edit.
    """
    ax = gui.fig_ax
    ax.clear()
    try:
        if pd is not None and filepath.lower().endswith((".csv", ".xlsx", ".xls")):
            if filepath.lower().endswith(".csv"):
                df = pd.read_csv(filepath)
            else:
                df = pd.read_excel(filepath)
            nums = df.select_dtypes(include=[np.number]).columns.tolist()
            if len(nums) >= 2:
                x = df[nums[0]].astype(float).values
                y = df[nums[1]].astype(float).values
                ax.plot(x, y, ".", ms=3)
                ax.set_xlabel(nums[0]); ax.set_ylabel(nums[1])
                ax.set_title(os.path.basename(filepath))
            else:
                # fallback: plot index vs first numeric conversion attempt
                ax.text(0.5, 0.5, "No numeric columns to preview", ha="center")
        else:
            # not pandas or not a known file: draw a sample sine wave
            t = np.linspace(0, 2 * np.pi, 200)
            ax.plot(t, np.sin(t))
            ax.set_title("Sample plot (no data available)")
    except Exception as e:
        ax.text(0.5, 0.5, f"Plot error: {e}", ha="center")
    gui.canvas.draw_idle()

# -------------------------
# The main GUI class
# -------------------------
class DualFileProcessorGUI(tk.Toplevel):
    def __init__(self, master=None, start_dir=os.getcwd()):
        super().__init__(master)
        self.title("Dual File Processor — Demo")
        self.geometry("1280x780")
        self.minsize(900, 600)

        # state
        self.current_dir = tk.StringVar(value=start_dir)
        self.percent_var = tk.StringVar(value="10")
        self.percent_value = 10.0
        self.current_file_path = None
        self.file_paths = {}  # index -> fullpath
        self.status_var = tk.StringVar(value="Ready.")

        # layout: left + right frames
        main = ttk.Frame(self, padding=8)
        main.pack(fill="both", expand=True)

        left_frame = ttk.Frame(main, width=420)
        left_frame.pack(side="left", fill="y", padx=(0,8), pady=4)

        # top-left controls
        controls = ttk.Frame(left_frame)
        controls.pack(fill="x", pady=(0,8))
        ttk.Label(controls, text="Directory:").pack(side="left")
        dir_entry = ttk.Entry(controls, textvariable=self.current_dir, width=40)
        dir_entry.pack(side="left", padx=(6,6))
        ttk.Button(controls, text="Browse", command=lambda: browse_folder(self)).pack(side="left")
        ttk.Button(controls, text="Refresh List", command=lambda: refresh_file_list(self)).pack(side="left", padx=(6,0))

        # second control row (Select + percent + Process Pair)
        controls2 = ttk.Frame(left_frame)
        controls2.pack(fill="x", pady=(0,6))
        ttk.Button(controls2, text="Select from list → Plot", command=lambda: select_file_from_list(self)).pack(side="left", padx=(0,6))
        ttk.Label(controls2, text="%:").pack(side="left")
        self.percent_var = tk.StringVar(value="10")
        ttk.Entry(controls2, width=6, textvariable=self.percent_var).pack(side="left", padx=(2,6))
        ttk.Button(controls2, text="Set % & Refresh", command=lambda: set_percent_and_refresh(self)).pack(side="left", padx=(0,6))
        ttk.Button(controls2, text="Process Selected Pair", command=lambda: process_selected_pair(self)).pack(side="right")

        # file list (lower half of left)
        list_label = ttk.Label(left_frame, text="Files")
        list_label.pack(anchor="w")
        listbox_frame = ttk.Frame(left_frame)
        listbox_frame.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(listbox_frame, selectmode="extended", activestyle="none")
        self.listbox.pack(side="left", fill="both", expand=True)
        lb_scroll = ttk.Scrollbar(listbox_frame, orient="vertical", command=self.listbox.yview)
        lb_scroll.pack(side="left", fill="y")
        self.listbox.configure(yscrollcommand=lb_scroll.set)

        # right frame: plotting area
        right_frame = ttk.Frame(main)
        right_frame.pack(side="left", fill="both", expand=True)

        self.fig = Figure(figsize=(6,4))
        self.fig_ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        toolbar = NavigationToolbar2Tk(self.canvas, right_frame)
        toolbar.update()
        toolbar.pack(fill="x")

        # footer / status
        footer = ttk.Frame(self)
        footer.pack(side="bottom", fill="x", padx=8, pady=(6,8))
        ttk.Label(footer, textvariable=self.status_var).pack(side="left")

        # unobtrusive CC attribution centered
        cc_text = f"CC BY 4.0 — Polymer PostMortem v{VERSION} — Chinmay Patil"
        tiny = tk.Label(self, text=cc_text, font=("Segoe UI", 9), fg="#777777")
        tiny.place(relx=0.5, rely=0.995, anchor="s")

        # initial population
        refresh_file_list(self)

# -------------------------
# Minimal launcher / demo
# -------------------------
def open_demo_gui():
    """Opens the DualFileProcessorGUI from a launcher window."""
    root = tk.Tk()
    root.title("Launcher (Demo)")
    root.geometry("420x180")
    ttk.Label(root, text="Demo launcher for Dual File Processor GUI", font=("Segoe UI", 11)).pack(pady=12)
    ttk.Button(root, text="Open Dual File Processor GUI", command=lambda: DualFileProcessorGUI(root)).pack(pady=8)
    ttk.Button(root, text="Quit", command=root.destroy).pack(pady=(6,0))
    root.mainloop()

# -------------------------
# Run demo if executed directly
# -------------------------
if __name__ == "__main__":
    open_demo_gui()