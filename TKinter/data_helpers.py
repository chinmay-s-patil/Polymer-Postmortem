
# data_helpers.py
import math
import os
import numpy as np
import pandas as pd

# try to reuse mainPostProc if available (same behavior as original)
try:
    import mainPostProc as mp
    MP_AVAILABLE = True
except Exception:
    mp = None
    MP_AVAILABLE = False

def detect_columns(df):
    names = {"strain": None, "stress": None, "disp": None, "force": None}
    for c in df.columns:
        lc = str(c).lower()
        if "strain" in lc:
            names["strain"] = c
        if "stress" in lc:
            names["stress"] = c
        if "displacement" in lc or "disp" in lc:
            names["disp"] = c
        if "force" in lc:
            names["force"] = c
    return names

def compute_auto_modulus(filepath):
    """
    Returns modulus in GPa (rounded) or None.
    Mirrors logic in original GUI7.py (uses mainPostProc.readMod if available).
    """
    try:
        if MP_AVAILABLE and hasattr(mp, "readMod"):
            try:
                outdir = None
                p = os.path.dirname(filepath)
                while p and p != os.path.dirname(p):
                    if os.path.basename(p).lower() == "output":
                        outdir = p
                        break
                    p = os.path.dirname(p)
                res = mp.readMod(filepath, outdir) if outdir is not None else mp.readMod(filepath, None)
                if res is not None:
                    return round(float(res), 3)
            except Exception:
                pass

        df = pd.read_csv(filepath)
        names = detect_columns(df)
        if not names["strain"] or not names["stress"]:
            return None
        x = df[names["strain"]].astype(float).values
        y = df[names["stress"]].astype(float).values
        if len(x) < 5:
            return None
        mask = x <= 0.02
        if mask.sum() >= 5:
            xi = x[mask]; yi = y[mask]
        else:
            n = min(50, len(x))
            xi = x[:n]; yi = y[:n]
        ok = ~np.isnan(xi) & ~np.isnan(yi)
        xi = xi[ok]; yi = yi[ok]
        if len(xi) < 5:
            return None
        coef = np.polyfit(xi, yi, 1)
        slope = coef[0]
        mod_gpa = round(slope / 10.0, 3)
        return mod_gpa
    except Exception:
        return None

def compute_yield_from_mod(filepath, mod_val, offset_pct=0.2, resolution=0.0001):
    try:
        df = pd.read_csv(filepath)
        names = detect_columns(df)
        if not names["strain"] or not names["stress"]:
            return (None, None)
        X = df[names["strain"]].astype(float).values
        Y = df[names["stress"]].astype(float).values
        mod = float(mod_val) * 10.0
        max_strain = 7
        base_strains = np.arange(0.0, max_strain, resolution)
        Xlin = base_strains + offset_pct
        Ylin = mod * (Xlin - offset_pct)
        valid_idxs = np.where(X <= Xlin[-1])[0]
        if len(valid_idxs) == 0:
            return (None, None)
        Xcurv = X[valid_idxs]
        Ycurv = Y[valid_idxs]
        denom = math.sqrt(mod ** 2 + 1.0)
        dist_list = []
        for x, y in zip(Xcurv, Ycurv):
            dist = abs(mod * (x - offset_pct) - y) / denom
            dist_list.append(dist)
        if not dist_list:
            return (None, None)
        idx_min = int(np.argmin(dist_list))
        yield_strain = round(float(Xcurv[idx_min]), 3)
        yield_stress = round(float(Ycurv[idx_min]), 3)
        return (yield_strain, yield_stress)
    except Exception:
        return (None, None)

def compute_breakpoint_auto(filepath):
    try:
        if MP_AVAILABLE and hasattr(mp, "breakpoint_from_file"):
            try:
                return mp.breakpoint_from_file(filepath)
            except Exception:
                pass
        df = pd.read_csv(filepath)
        names = detect_columns(df)
        if names["strain"] and names["stress"]:
            x = df[names["strain"]].astype(float).values
            y = df[names["stress"]].astype(float).values
            idx = np.argmax(x)
            return (round(float(x[idx]), 6), round(float(y[idx]), 3))
        else:
            nums = df.select_dtypes(include=[np.number]).columns.tolist()
            if len(nums) >= 2:
                x = df[nums[0]].astype(float).values
                y = df[nums[1]].astype(float).values
                idx = np.argmax(x)
                return (round(float(x[idx]), 6), round(float(y[idx]), 3))
    except Exception:
        pass
    return (None, None)
