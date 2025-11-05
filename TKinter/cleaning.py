# cleaning.py
import os
import re
import numpy as np
import pandas as pd
import json

NUMERIC_RE = re.compile(r'[+\-]?\d*\.?\d+(?:[eE][+\-]?\d+)?')

def _extract_number_from_token(tok):
    """Return float parsed from token or np.nan (robust to stray chars)."""
    if tok is None:
        return np.nan
    s = str(tok).strip().replace('"', '').replace("'", "")
    try:
        return float(s)
    except Exception:
        m = NUMERIC_RE.search(s)
        if m:
            try:
                return float(m.group(0))
            except Exception:
                return np.nan
        return np.nan

def cleanfiles(dirpath, files):
    """
    Writes cleaned CSVs to <dirpath>/output/Clean Files and creates specimenSpecs JSONs.
    Ported from GUI7.py with same behavior.
    """
    outputDir = os.path.join(dirpath, "output", "Clean Files")
    os.makedirs(outputDir, exist_ok=True)
    specimenJsonDir = os.path.join(outputDir, "specimenSpecs")
    os.makedirs(specimenJsonDir, exist_ok=True)

    header_keywords = ("time", "strain", "stress", "displacement")

    for file in files:
        try:
            if not os.path.isabs(file):
                candidate = os.path.join(dirpath, file)
                if os.path.exists(candidate):
                    file_path = candidate
                else:
                    file_path = file
            else:
                file_path = file

            _, ext = os.path.splitext(file_path)
            ext = ext.lower()

            if ext == ".csv" or ext == ".txt":
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                except Exception as e:
                    print(f"cleanfiles: unable to read {file_path}: {e}")
                    continue

                header_idx = None
                for i, ln in enumerate(lines):
                    low = ln.lower()
                    if any(w in low for w in header_keywords):
                        header_idx = i
                        break

                data_lines = []
                cols = None
                if header_idx is not None:
                    cols = [c.strip() for c in lines[header_idx].strip().split(",") if c.strip()]
                    for ln in lines[header_idx+1:]:
                        tok = [t.strip() for t in ln.strip().split(",") if t.strip()]
                        if not tok:
                            continue
                        nums = []
                        for t in tok:
                            val = _extract_number_from_token(t)
                            nums.append(val)
                        if any(not np.isnan(x) for x in nums):
                            data_lines.append(nums)

                if not cols and data_lines:
                    cols = [f"col{i}" for i in range(len(data_lines[0]))]

                try:
                    df = pd.DataFrame(data_lines, columns=cols) if cols else pd.DataFrame(data_lines)
                except Exception:
                    df = pd.DataFrame(data_lines)

                out_csv = os.path.join(outputDir, os.path.basename(file_path))
                try:
                    df.to_csv(out_csv, index=False)
                except Exception as e:
                    print(f"cleanfiles: failed to write CSV for {file_path}: {e}")

                jsonpath = os.path.join(specimenJsonDir, os.path.basename(file_path).replace(ext, "") + ".json")
                try:
                    with open(jsonpath, "w", encoding="utf-8") as jf:
                        json.dump({}, jf, indent=4)
                except Exception as e:
                    print(f"cleanfiles: failed to write JSON for {file_path}: {e}")

            elif ext in (".xlsx", ".xls"):
                found = False
                max_header_attempts = 10
                last_exc = None
                for head in range(max_header_attempts):
                    try:
                        df = pd.read_excel(file_path, header=head, engine=None)
                    except Exception as e:
                        last_exc = e
                        try:
                            df = pd.read_excel(file_path, header=head, engine='openpyxl')
                        except Exception as e2:
                            last_exc = e2
                            continue

                    cols_raw = [str(c) for c in df.columns]
                    if any('time' in str(c).lower() for c in cols_raw):
                        found = True
                        colnum = len([i for i in df.columns if (i and "unnamed" not in str(i).lower())])
                        if 0 in df.index:
                            df = df.drop(index=df.index[0])
                        if colnum > 0:
                            df = df.iloc[:, :colnum]
                        break
                if not found:
                    try:
                        df = pd.read_excel(file_path, header=0, engine=None)
                    except Exception as e:
                        print(f"cleanfiles: couldn't parse excel {file_path}: {e}")
                        continue

                cols = list(df.columns)
                for i in range(len(cols)):
                    if 'stress' in str(cols[i]).lower():
                        cols[i] = 'stress'
                cols = [str(c).split(" ")[0].strip().lower() for c in cols if str(c).strip()]
                df.columns = cols
                for c in df.columns:
                    try:
                        df[c] = pd.to_numeric(df[c], errors='ignore')
                    except Exception:
                        pass

                out_name = os.path.basename(file_path).replace(ext, ".csv")
                out_csv = os.path.join(outputDir, out_name)
                try:
                    df.to_csv(out_csv, index=False)
                except Exception as e:
                    print(f"cleanfiles: failed to write CSV for {file_path}: {e}")

                jsonpath = os.path.join(specimenJsonDir, os.path.basename(file_path).replace(ext, "") + ".json")
                try:
                    with open(jsonpath, "w", encoding="utf-8") as jf:
                        json.dump({}, jf, indent=4)
                except Exception as e:
                    print(f"cleanfiles: failed to write JSON for {file_path}: {e}")
            else:
                print(f"cleanfiles: skipping unsupported extension for '{file_path}'")
        except Exception as e:
            print(f"cleanfiles: failed to process '{file}': {e}")

def clear_clean_files_csvs(base_dir):
    """
    Remove .csv files directly inside any <...>/output/Clean Files folders under base_dir.
    """
    removed = []
    if not base_dir or not os.path.isdir(base_dir):
        return removed

    for root, dirs, files in os.walk(base_dir):
        for d in dirs:
            if d.lower() == "clean files" and os.path.basename(root).lower() == "output":
                clean_dir = os.path.join(root, d)
                try:
                    for name in os.listdir(clean_dir):
                        path = os.path.join(clean_dir, name)
                        if os.path.isfile(path) and name.lower().endswith(".csv"):
                            try:
                                os.remove(path)
                                removed.append(path)
                            except Exception as e:
                                print(f"Failed to remove {path}: {e}")
                except Exception as e:
                    print(f"Error listing '{clean_dir}': {e}")
    return removed
