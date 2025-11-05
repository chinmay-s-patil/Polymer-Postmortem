"""
core/data_processor.py - Core data processing logic
Refactored from original data_helpers.py and json_utils.py
"""

import os
import json
import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple, List

class DataProcessor:
    """Handles all data processing, file I/O, and analysis operations"""
    
    def __init__(self):
        pass
    
    # ==================== JSON Operations ====================
    
    def master_json_path(self, output_dir: str) -> Optional[str]:
        """Get path to master JSON file"""
        return os.path.join(output_dir, "gui_master.json") if output_dir else None
    
    def load_master(self, output_dir: str) -> Dict:
        """Load master JSON data"""
        path = self.master_json_path(output_dir)
        if not path or not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading master: {e}")
            return {}
    
    def save_master(self, output_dir: str, data: Dict):
        """Save master JSON data"""
        path = self.master_json_path(output_dir)
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving master: {e}")
    
    def write_json_safe(self, path: str, data: Dict):
        """Safely write JSON to file"""
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error writing JSON to {path}: {e}")
    
    def merge_individual_jsons(self, output_dir: str, master: Optional[Dict] = None) -> Dict:
        """Merge individual metric JSONs into master"""
        if not output_dir:
            return {}
        
        if master is None:
            master_path = self.master_json_path(output_dir)
            master = self.load_master(output_dir) if os.path.exists(master_path or "") else {}
        
        # Specimen specs
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
        
        # Per-metric JSONs
        metric_files = {
            "modulus_results.json": "modulus",
            "yield_results.json": "yield",
            "break_results.json": "breakpoint"
        }
        
        for root, _, files in os.walk(output_dir):
            for fname in files:
                lname = fname.lower()
                if lname in metric_files:
                    try:
                        jp = os.path.join(root, fname)
                        with open(jp, "r", encoding="utf-8") as f:
                            d = json.load(f)
                        for k, v in d.items():
                            master.setdefault(k, {})
                            master[k][metric_files[lname]] = v
                    except Exception:
                        pass
        
        self.save_master(output_dir, master)
        return master
    
    # ==================== Column Detection ====================
    
    def detect_columns(self, df: pd.DataFrame) -> Dict[str, Optional[str]]:
        """Detect standard column names in DataFrame"""
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
    
    # ==================== Modulus Calculation ====================
    
    def compute_auto_modulus(self, filepath: str) -> Optional[float]:
        """
        Compute modulus automatically from file data
        Returns modulus in GPa (rounded) or None
        """
        try:
            df = pd.read_csv(filepath)
            names = self.detect_columns(df)
            if not names["strain"] or not names["stress"]:
                return None
            
            x = df[names["strain"]].astype(float).values
            y = df[names["stress"]].astype(float).values
            
            if len(x) < 5:
                return None
            
            # Use first 2% strain or first 50 points
            mask = x <= 0.02
            if mask.sum() >= 5:
                xi = x[mask]
                yi = y[mask]
            else:
                n = min(50, len(x))
                xi = x[:n]
                yi = y[:n]
            
            # Remove NaN values
            ok = ~np.isnan(xi) & ~np.isnan(yi)
            xi = xi[ok]
            yi = yi[ok]
            
            if len(xi) < 5:
                return None
            
            # Linear fit
            coef = np.polyfit(xi, yi, 1)
            slope = coef[0]
            mod_gpa = round(slope / 10.0, 3)
            
            return mod_gpa
        except Exception as e:
            print(f"Error computing modulus: {e}")
            return None
    
    # ==================== Yield Calculation ====================
    
    def compute_yield_from_mod(
        self, 
        filepath: str, 
        mod_val: float, 
        offset_pct: float = 0.2, 
        resolution: float = 0.0001
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Compute yield point using offset method
        Returns (yield_strain, yield_stress) or (None, None)
        """
        try:
            df = pd.read_csv(filepath)
            names = self.detect_columns(df)
            if not names["strain"] or not names["stress"]:
                return (None, None)
            
            X = df[names["strain"]].astype(float).values
            Y = df[names["stress"]].astype(float).values
            
            mod = float(mod_val) * 10.0  # Convert GPa to stress units
            max_strain = 7
            base_strains = np.arange(0.0, max_strain, resolution)
            Xlin = base_strains + offset_pct
            Ylin = mod * (Xlin - offset_pct)
            
            valid_idxs = np.where(X <= Xlin[-1])[0]
            if len(valid_idxs) == 0:
                return (None, None)
            
            Xcurv = X[valid_idxs]
            Ycurv = Y[valid_idxs]
            
            # Calculate perpendicular distance from each point to offset line
            denom = np.sqrt(mod ** 2 + 1.0)
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
        except Exception as e:
            print(f"Error computing yield: {e}")
            return (None, None)
    
    # ==================== Breakpoint Calculation ====================
    
    def compute_breakpoint_auto(self, filepath: str) -> Tuple[Optional[float], Optional[float]]:
        """
        Compute breakpoint automatically (point of maximum strain)
        Returns (break_strain, break_stress) or (None, None)
        """
        try:
            df = pd.read_csv(filepath)
            names = self.detect_columns(df)
            
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
        except Exception as e:
            print(f"Error computing breakpoint: {e}")
        
        return (None, None)
    
    # ==================== Ultimate Stress ====================
    
    def compute_ultimate_stress(self, filepath: str) -> Optional[float]:
        """
        Compute ultimate stress (maximum stress value)
        Returns ultimate stress or None
        """
        try:
            df = pd.read_csv(filepath)
            names = self.detect_columns(df)
            
            if names.get("stress"):
                u = float(df[names["stress"]].astype(float).max())
                return round(u, 3)
            else:
                # Fallback: search for any stress column
                for c in df.columns:
                    if "stress" in str(c).lower():
                        u = float(df[c].astype(float).max())
                        return round(u, 3)
            
            return None
        except Exception as e:
            print(f"Error computing ultimate stress: {e}")
            return None
    
    # ==================== File Operations ====================
    
    def get_specimen_specs(self, filepath: str, output_dir: str) -> Dict:
        """Load specimen specifications from JSON"""
        try:
            basename = os.path.splitext(os.path.basename(filepath))[0]
            spec_path = os.path.join(
                output_dir, "Clean Files", "specimenSpecs", f"{basename}.json"
            )
            if os.path.exists(spec_path):
                with open(spec_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading specimen specs: {e}")
        return {}
    
    def save_modulus_result(
        self, 
        filepath: str, 
        output_dir: str,
        modulus_val: float, 
        length_val: float, 
        area_val: float,
        selected_points: Optional[List] = None,
        plot_type: Optional[str] = None
    ):
        """Save modulus result to JSON"""
        jpath = os.path.join(output_dir, "modulus_results.json")
        
        if os.path.exists(jpath):
            try:
                with open(jpath, "r", encoding="utf-8") as jf:
                    data = json.load(jf)
            except Exception:
                data = {}
        else:
            data = {}
        
        key = os.path.basename(filepath)
        entry = {
            "modulus": modulus_val,
            "length": length_val,
            "area": area_val
        }
        
        if selected_points is not None:
            try:
                entry["points"] = [
                    [float(selected_points[0][0]), float(selected_points[0][1])],
                    [float(selected_points[1][0]), float(selected_points[1][1])]
                ]
            except Exception:
                pass
        
        if plot_type is not None:
            entry["plot_type"] = plot_type
        
        data[key] = entry
        self.write_json_safe(jpath, data)
        self.merge_individual_jsons(output_dir)
    
    def save_yield_result(
        self,
        filepath: str,
        output_dir: str,
        yield_strain: float,
        yield_stress: float
    ):
        """Save yield result to JSON"""
        jpath = os.path.join(output_dir, "yield_results.json")
        
        if os.path.exists(jpath):
            try:
                with open(jpath, "r", encoding="utf-8") as jf:
                    data = json.load(jf)
            except Exception:
                data = {}
        else:
            data = {}
        
        key = os.path.basename(filepath)
        data[key] = {
            "strain": yield_strain,
            "stress": yield_stress
        }
        
        self.write_json_safe(jpath, data)
        self.merge_individual_jsons(output_dir)
    
    def save_breakpoint_result(
        self,
        filepath: str,
        output_dir: str,
        break_strain: float,
        break_stress: float
    ):
        """Save breakpoint result to JSON"""
        jpath = os.path.join(output_dir, "break_results.json")
        
        if os.path.exists(jpath):
            try:
                with open(jpath, "r", encoding="utf-8") as jf:
                    data = json.load(jf)
            except Exception:
                data = {}
        else:
            data = {}
        
        key = os.path.basename(filepath)
        data[key] = [break_strain, break_stress]
        
        self.write_json_safe(jpath, data)
        self.merge_individual_jsons(output_dir)