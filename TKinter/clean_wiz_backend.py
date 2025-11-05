# clean_wiz_backend.py (logging-enabled)
# Reworked to use Python's logging system instead of print(),
# and to (best-effort) forward log messages into a CleaningWizard
# "Preview / Log" Text widget when a GUI is present. No GUI file
# changes required — the backend will look for a Text widget and
# schedule insertions via root.after() so it's thread-safe.

import os
import re
import math
import json
import shutil
import threading
import numpy as np
import pandas as pd
from datetime import datetime

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import logging

# ---------------------- GUI log discovery & handler ----------------------

def _find_log_text_widget():
    """Recursively search the Tk default root for a tk.Text widget which
    looks like the cleaning wizard's log area. This is heuristic: we look
    for the first Text widget (depth-first) and prefer ones that have
    height==10 (the wizard sets height=10). Returns the Text widget or None.
    """
    root = getattr(tk, "_default_root", None)
    if not root:
        return None

    def recurse(w):
        # prefer Text widgets with height==10
        try:
            if isinstance(w, tk.Text):
                try:
                    if int(w.cget("height")) == 10:
                        return w
                except Exception:
                    return w
        except Exception:
            pass

        for ch in w.winfo_children():
            found = recurse(ch)
            if found:
                return found
        return None

    try:
        return recurse(root)
    except Exception:
        return None


def _gui_insert(text_widget, msg):
    """Insert a single log line into the given tk.Text widget (handles state)."""
    try:
        text_widget.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        text_widget.insert("end", f"[{ts}] {msg}\n")
        text_widget.see("end")
        text_widget.configure(state="disabled")
    except Exception:
        # fallback to console if anything goes wrong
        print(msg)


class GuiLogHandler(logging.Handler):
    """A logging handler that attempts to write log records into the
    CleaningWizard log Text widget. It uses root.after(0, ...) so it's
    safe to call from worker threads.
    """

    def emit(self, record):
        try:
            msg = self.format(record)
            root = getattr(tk, "_default_root", None)
            txt = _find_log_text_widget()
            if txt and root:
                try:
                    root.after(0, lambda: _gui_insert(txt, msg))
                    return
                except Exception:
                    # try direct insert as fallback
                    _gui_insert(txt, msg)
                    return
        except Exception:
            pass
        # if GUI not available or failed, print to console as fallback
        try:
            print(self.format(record))
        except Exception:
            pass


# module-level logger
logger = logging.getLogger("clean_wiz_backend")
if not logger.handlers:
    logger.setLevel(logging.DEBUG)
    ghl = GuiLogHandler()
    ghl.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(levelname)s: %(message)s")
    ghl.setFormatter(formatter)
    logger.addHandler(ghl)

# optional: also add a StreamHandler to stderr so logs are visible in
# the console if the GUI handler fails (comment/uncomment as desired)
if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

# ------------------------- Cleaning backend ------------------------------

def clean_backend(file, outputDir, percent=None):
    os.makedirs(outputDir, exist_ok=True)
    try:
        if file.endswith('.csv'):
            with open(file, 'r') as f:
                line = f.readline()
                while line:
                    
                    if "time" in line.lower().split(','):
                        cols = []
                        for i in line.strip().split(','):
                            if i:
                                if "stress" in i.lower():
                                    cols.append("Stress")
                                elif "strain" in i.lower():
                                    cols.append("Strain")
                                else:
                                    cols.append(i)
                        
                        for i in range(len(cols)):
                            if "Strain" in cols[i]:
                                straincol = i
                        
                        f.readline()
                        
                        datalin = [i for i in f.readlines() if i]
                        
                        data = []
                        
                        for dat in datalin:
                            if dat:
                                # replace prints with logger.debug/info
                                dataindiv = [float(i) for i in dat.strip().replace('"', '').split(',') if i]
                                data.append(dataindiv)

                                if percent:
                                    try:
                                        if dataindiv:
                                            if dataindiv[straincol] > percent:
                                                print(percent)
                                                print(dataindiv[straincol])
                                                data = pd.DataFrame(data, columns=cols).dropna()
                                                data.to_csv(os.path.join(outputDir, os.path.basename(file).split(".csv")[0] + ".csv"))
                                                logger.info("Wrote truncated CSV for %s (percent threshold reached)", file)
                                                return
                                    except Exception:
                                        print(dataindiv)
                                        # if indexing or conversion fails, log and continue
                                        logger.debug("Failed percent check for row in %s", file)
                        data = pd.DataFrame(data, columns=cols).dropna()
                        data.to_csv(os.path.join(outputDir, os.path.basename(file).split(".csv")[0] + ".csv"))
                        logger.info("Wrote CSV output for %s", file)
                    
                    line = f.readline()

        elif file.endswith(".xlsx"):
            # NOTE: preserved original logic; minor variable name fixes not applied
            outputFileName = os.path.join(outputDir, os.path.basename(file).split('.xlsx')[0].strip() + '.csv')
            boo = False
            head = 0
            while not boo:
                df = pd.read_excel(file, header=head)
                if "Time" in df.columns:
                    colnum = len([i for i in df.columns if (i and "unnamed" not in i.lower())])
                    df = df.drop(0)
                    df = df.iloc[:,:colnum]
                    boo = True
                head += 1
            
            cols = list(df.columns)
            for i in range(len(cols)):
                if "stress" in cols[i].lower(): cols[i] = ('stress')
            cols = [c.split(" ")[0].strip().lower() for c in cols if c.strip()]
            df.columns = cols
            
            df.to_csv(outputFileName, columns= cols)
            logger.info("Wrote XLSX->CSV output for %s", file)

    except Exception as e:
        # Use logger.exception so traceback is recorded in the GUI log + console.
        logger.exception("Exception while processing file %s: %s", file, str(e))

def clean_backend_noext(file, outputDir, percent=None):
    try:
        if file.endswith('.csv'):
            with open(file, 'r') as f:
                line = f.readline()
                while line:
                    
                    if "time" in line.lower().split(','):
                        cols = []
                        for i in line.strip().split(','):
                            if i:
                                if "stress" in i.lower():
                                    cols.append("Stress")
                                elif "strain" in i.lower():
                                    cols.append("Strain")
                                else:
                                    cols.append(i)
                        
                        for i in range(len(cols)):
                            if "Strain" in cols[i]:
                                straincol = i
                        
                        f.readline()
                        
                        datalin = [i for i in f.readlines() if i]
                        
                        data = []
                        
                        for dat in datalin:
                            # replace prints with logger.debug/info
                            dataindiv = [float(i) for i in dat.strip().replace('"', '').split(',') if i]
                            data.append(dataindiv)

                            if percent is not None:
                                try:
                                    if dataindiv:
                                        if dataindiv[straincol] > percent:
                                            data = pd.DataFrame(data, columns=cols).dropna()
                                            data.to_csv(os.path.join(outputDir, os.path.basename(file).split(".csv")[0] + ".csv"))
                                            logger.info("Wrote truncated CSV for %s (percent threshold reached)", file)
                                            return
                                except Exception:
                                    print(dataindiv)
                                    print(cols)
                                    # if indexing or conversion fails, log and continue
                                    logger.debug("Failed percent check for row in %s", file)
                        
                        print()
                        print(cols)
                        print()

                        data = pd.DataFrame(data, columns=cols).dropna()
                        data['Strain'] = [None for i in data['Strain']]
                        data.to_csv(os.path.join(outputDir, os.path.basename(file).split(".csv")[0] + ".csv"))
                        logger.info("Wrote CSV output for %s", file)
                    
                    line = f.readline()

        elif file.endswith(".xlsx"):
            # NOTE: preserved original logic; minor variable name fixes not applied
            outputFileName = os.path.join(outputDir, os.path.basename(file).split('.xlsx')[0].strip() + '.csv')
            boo = False
            head = 0
            while not boo:
                df = pd.read_excel(file, header=head)
                if "Time" in df.columns:
                    colnum = len([i for i in df.columns if (i and "unnamed" not in i.lower())])
                    df = df.drop(0)
                    df = df.iloc[:,:colnum]
                    boo = True
                head += 1
            
            cols = list(df.columns)
            for i in range(len(cols)):
                if "stress" in cols[i].lower(): cols[i] = ('stress')
            cols = [c.split(" ")[0].strip().lower() for c in cols if c.strip()]
            df.columns = cols
            
            df.to_csv(outputFileName, columns= cols)
            logger.info("Wrote XLSX->CSV output for %s", file)

    except Exception as e:
        # Use logger.exception so traceback is recorded in the GUI log + console.
        logger.exception("Exception while processing file %s: %s", file, str(e))


# If desired: expose a small helper to let other code log via the backend logger
def log(msg, level='info'):
    """Convenience wrapper so GUI or other modules can call clean_wiz_backend.log(msg). """
    if level == 'debug':
        logger.debug(msg)
    elif level == 'warning':
        logger.warning(msg)
    elif level == 'error':
        logger.error(msg)
    else:
        logger.info(msg)
