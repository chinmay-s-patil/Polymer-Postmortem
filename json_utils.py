# json_utils.py
import os
import json

def master_json_path(output_dir):
    return os.path.join(output_dir, "gui_master.json") if output_dir else None

def load_master(output_dir):
    p = master_json_path(output_dir)
    if not p or not os.path.exists(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_master(output_dir, data):
    p = master_json_path(output_dir)
    if not p:
        return
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print("save_master failed:", e)

def write_json_safe(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print("write_json_safe failed:", path, e)

def merge_individual_jsons(output_dir, master=None):
    """
    Build/update master from specimenSpecs and per-metric jsons.
    Behaves like original: preserves 'flag' if present.
    """
    if not output_dir:
        return {}
    if master is None:
        master = load_master(output_dir) if os.path.exists(master_json_path(output_dir) or "") else {}

    # specimen specs
    specimen_dir = os.path.join(output_dir, "Clean Files", "specimenSpecs")
    if os.path.isdir(specimen_dir):
        for fname in os.listdir(specimen_dir):
            if fname.lower().endswith(".json"):
                key_csv = os.path.splitext(fname)[0] + ".csv"
                try:
                    with open(os.path.join(specimen_dir, fname), "r", encoding="utf-8") as f:
                        specs = json.load(f)
                    master.setdefault(key_csv, {}).setdefault("specs", {}).update(specs)
                except Exception:
                    pass

    # per-metric jsons (scan recursively)
    wanted = {
        "modulus_results.json": "modulus",
        "yield_results.json": "yield",
        "break_results.json": "breakpoint"
    }
    for root, _, files in os.walk(output_dir):
        for fname in files:
            lname = fname.lower()
            if lname in wanted:
                try:
                    jp = os.path.join(root, fname)
                    with open(jp, "r", encoding="utf-8") as f:
                        d = json.load(f)
                    for k, v in d.items():
                        master.setdefault(k, {})
                        master[k][wanted[lname]] = v
                except Exception:
                    pass

    save_master(output_dir, master)
    return master
