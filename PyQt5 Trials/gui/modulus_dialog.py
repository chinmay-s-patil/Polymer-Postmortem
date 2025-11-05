"""
gui/modulus_dialog.py - Complete modulus calculation dialog with point selection
"""

import os
import json
import numpy as np
import pandas as pd
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

class ModulusDialog(QDialog):
    """Dialog for calculating modulus with interactive point selection"""
    
    def __init__(self, parent, filepath, processor, output_dir):
        super().__init__(parent)
        self.filepath = filepath
        self.processor = processor
        self.output_dir = output_dir
        self.charl = parent.charl if hasattr(parent, 'charl') else 85.0
        self.area = parent.area if hasattr(parent, 'area') else 62.5
        
        self.setWindowTitle(f"Modulus - {os.path.basename(filepath)}")
        self.resize(920, 620)
        
        self.selected_x = []
        self.selected_y = []
        self.selection_artists = []
        self.calculated_mod = None
        
        self.setup_ui()
        self.load_data()
        self.draw_plot()
    
    def setup_ui(self):
        """Setup dialog UI"""
        layout = QHBoxLayout(self)
        
        # Left panel - plot
        left = QWidget()
        left_layout = QVBoxLayout(left)
        
        self.figure = Figure(figsize=(6, 4))
        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor('#1a1a1a')
        self.figure.patch.set_facecolor('#353535')
        
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, left)
        
        left_layout.addWidget(self.toolbar)
        left_layout.addWidget(self.canvas)
        
        # Right panel - controls
        right = QWidget()
        right.setMaximumWidth(280)
        right_layout = QVBoxLayout(right)
        
        # Plot type selection
        plot_group = QGroupBox("Plot Type")
        plot_layout = QVBoxLayout()
        self.rb_stress_strain = QRadioButton("Stress-Strain")
        self.rb_force_disp = QRadioButton("Force-Displacement")
        self.rb_stress_strain.setChecked(True)
        self.rb_stress_strain.toggled.connect(self.draw_plot)
        self.rb_force_disp.toggled.connect(self.draw_plot)
        plot_layout.addWidget(self.rb_stress_strain)
        plot_layout.addWidget(self.rb_force_disp)
        plot_group.setLayout(plot_layout)
        right_layout.addWidget(plot_group)
        
        # Specimen properties
        right_layout.addWidget(QLabel("Gauge Length L₀ (mm):"))
        self.length_entry = QLineEdit(str(self.charl))
        right_layout.addWidget(self.length_entry)
        
        right_layout.addWidget(QLabel("Area A (mm²):"))
        self.area_entry = QLineEdit(str(self.area))
        right_layout.addWidget(self.area_entry)
        
        self.slope_label = QLabel("Slope: N/A")
        self.slope_label.setStyleSheet("font-weight: bold; color: #2a82da;")
        right_layout.addWidget(self.slope_label)
        
        # Buttons
        btn_refresh = QPushButton("Refresh Graph")
        btn_refresh.clicked.connect(self.draw_plot)
        right_layout.addWidget(btn_refresh)
        
        btn_clear = QPushButton("Clear Selection")
        btn_clear.clicked.connect(self.clear_selection)
        right_layout.addWidget(btn_clear)
        
        btn_calc = QPushButton("Calculate Slope")
        btn_calc.clicked.connect(self.calc_slope)
        right_layout.addWidget(btn_calc)
        
        btn_save = QPushButton("Save & Close")
        btn_save.clicked.connect(self.save_and_close)
        right_layout.addWidget(btn_save)
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        right_layout.addWidget(btn_cancel)
        
        right_layout.addStretch()
        
        # Add to main layout
        layout.addWidget(left, stretch=3)
        layout.addWidget(right, stretch=1)
        
        # Connect click event
        self.canvas.mpl_connect('button_press_event', self.on_click)
    
    def load_data(self):
        """Load CSV data"""
        try:
            self.df = pd.read_csv(self.filepath)
            self.names = self.processor.detect_columns(self.df)
            
            # Try to load specimen area
            try:
                specjson = os.path.join(
                    self.output_dir, "Clean Files", "specimenSpecs",
                    os.path.splitext(os.path.basename(self.filepath))[0] + ".json"
                )
                if os.path.exists(specjson):
                    with open(specjson, 'r') as f:
                        specs = json.load(f)
                    if "Width" in specs and "Thickness" in specs:
                        area = float(specs["Width"]) * float(specs["Thickness"])
                        self.area_entry.setText(str(area))
            except:
                pass
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load data: {e}")
            self.reject()
    
    def draw_plot(self):
        """Draw the initial plot"""
        self.ax.clear()
        self.selected_x.clear()
        self.selected_y.clear()
        self.selection_artists.clear()
        
        try:
            if self.rb_stress_strain.isChecked() and self.names["strain"] and self.names["stress"]:
                x = self.df[self.names["strain"]].astype(float).values
                y = self.df[self.names["stress"]].astype(float).values
                self.ax.plot(x, y, '.', ms=1, color='#2a82da')
                self.ax.set_xlabel("Strain", color='white')
                self.ax.set_ylabel("Stress", color='white')
            elif self.rb_force_disp.isChecked() and self.names["disp"] and self.names["force"]:
                x = self.df[self.names["disp"]].astype(float).values
                y = self.df[self.names["force"]].astype(float).values
                self.ax.plot(x, y, '.', ms=1, color='#2a82da')
                self.ax.set_xlabel("Displacement", color='white')
                self.ax.set_ylabel("Force", color='white')
            else:
                nums = self.df.select_dtypes(include=[np.number]).columns.tolist()
                if len(nums) >= 2:
                    x = self.df[nums[0]].astype(float).values
                    y = self.df[nums[1]].astype(float).values
                    self.ax.plot(x, y, '.', ms=1, color='#2a82da')
                    self.ax.set_xlabel(nums[0], color='white')
                    self.ax.set_ylabel(nums[1], color='white')
            
            self.ax.set_title(f"{os.path.basename(self.filepath)} (Select 2 points)", color='white')
            self.ax.grid(True, alpha=0.3, color='white')
            self.ax.tick_params(colors='white')
            self.ax.set_facecolor('#1a1a1a')
            
        except Exception as e:
            self.ax.text(0.5, 0.5, f"Plot failed: {e}", ha='center', color='white')
        
        self.canvas.draw()
    
    def on_click(self, event):
        """Handle click on plot"""
        if event.inaxes != self.ax or event.xdata is None or event.ydata is None:
            return
        
        try:
            # Get current data
            if self.rb_stress_strain.isChecked() and self.names["strain"] and self.names["stress"]:
                xdata = self.df[self.names["strain"]].astype(float).values
                ydata = self.df[self.names["stress"]].astype(float).values
            elif self.rb_force_disp.isChecked() and self.names["disp"] and self.names["force"]:
                xdata = self.df[self.names["disp"]].astype(float).values
                ydata = self.df[self.names["force"]].astype(float).values
            else:
                nums = self.df.select_dtypes(include=[np.number]).columns.tolist()
                if len(nums) < 2:
                    return
                xdata = self.df[nums[0]].astype(float).values
                ydata = self.df[nums[1]].astype(float).values
            
            # Find nearest point
            dx = xdata - event.xdata
            dy = ydata - event.ydata
            dist = np.hypot(dx, dy)
            
            if dist.size == 0:
                return
            
            idx = int(np.nanargmin(dist))
            x_sel = float(xdata[idx])
            y_sel = float(ydata[idx])
            
            self.selected_x.append(x_sel)
            self.selected_y.append(y_sel)
            
            # Draw marker
            marker, = self.ax.plot([x_sel], [y_sel], 'o', ms=8, mec='red', mfc='none')
            self.selection_artists.append(marker)
            
            # Draw line if we have 2 points
            if len(self.selected_x) >= 2:
                x0, x1 = self.selected_x[-2], self.selected_x[-1]
                y0, y1 = self.selected_y[-2], self.selected_y[-1]
                line, = self.ax.plot([x0, x1], [y0, y1], 'r-', linewidth=2)
                self.selection_artists.append(line)
            
            self.canvas.draw()
            
        except Exception as e:
            print(f"Click error: {e}")
    
    def clear_selection(self):
        """Clear selected points"""
        self.selected_x.clear()
        self.selected_y.clear()
        for art in self.selection_artists:
            try:
                art.remove()
            except:
                pass
        self.selection_artists.clear()
        self.slope_label.setText("Slope: N/A")
        self.canvas.draw()
    
    def calc_slope(self):
        """Calculate modulus from selected points"""
        if len(self.selected_x) < 2:
            QMessageBox.information(self, "Info", "Select two points first.")
            return
        
        x0, x1 = self.selected_x[-2], self.selected_x[-1]
        y0, y1 = self.selected_y[-2], self.selected_y[-1]
        
        try:
            L0 = float(self.length_entry.text())
        except:
            L0 = self.charl
        
        try:
            A = float(self.area_entry.text())
        except:
            A = self.area
        
        if x1 == x0:
            self.slope_label.setText("Slope: ∞")
            return
        
        try:
            if self.rb_stress_strain.isChecked():
                # Stress-Strain: E = Δσ / Δε / 10 (GPa)
                MOD = round((y1 - y0) / ((x1 - x0) * 10.0), 3)
            else:
                # Force-Displacement: E = (ΔF * L0) / (A * Δδ) / 10 (GPa)
                denom = (x1 - x0)
                if denom == 0 or A == 0:
                    MOD = None
                else:
                    MOD = round(((y1 - y0) * L0) / (A * denom) / 10.0, 3)
            
            if MOD is not None:
                self.calculated_mod = MOD
                self.slope_label.setText(f"Slope: {MOD} GPa")
            else:
                self.slope_label.setText("Slope: Invalid")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Calculation failed: {e}")
    
    def save_and_close(self):
        """Save results and close dialog"""
        if self.calculated_mod is None:
            QMessageBox.warning(self, "Warning", "Calculate slope first.")
            return
        
        try:
            L0 = float(self.length_entry.text())
            A = float(self.area_entry.text())
        except:
            QMessageBox.critical(self, "Error", "Invalid gauge length or area.")
            return
        
        # Save to JSON
        self.processor.save_modulus_result(
            self.filepath, self.output_dir,
            self.calculated_mod, L0, A,
            selected_points=[[self.selected_x[-2], self.selected_y[-2]], 
                           [self.selected_x[-1], self.selected_y[-1]]],
            plot_type="Stress-Strain" if self.rb_stress_strain.isChecked() else "Force-Displacement"
        )
        
        # Save plot
        try:
            plot_dir = os.path.join(self.output_dir, "Modulus Plots")
            os.makedirs(plot_dir, exist_ok=True)
            self.figure.savefig(os.path.join(plot_dir, f"{os.path.basename(self.filepath)}_modulus.png"))
        except:
            pass
        
        QMessageBox.information(self, "Success", f"Modulus saved: {self.calculated_mod} GPa")
        self.accept()