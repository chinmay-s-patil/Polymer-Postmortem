"""
gui/yield_dialog.py - Complete yield point calculation dialog
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

class YieldDialog(QDialog):
    """Dialog for calculating yield point"""
    
    def __init__(self, parent, filepath, processor, output_dir):
        super().__init__(parent)
        self.filepath = filepath
        self.processor = processor
        self.output_dir = output_dir
        
        self.setWindowTitle(f"Yield - {os.path.basename(filepath)}")
        self.resize(1000, 700)
        
        self.setup_ui()
        self.load_data()
        self.draw_initial()
    
    def setup_ui(self):
        """Setup dialog UI"""
        layout = QHBoxLayout(self)
        
        # Left panel - plot
        left = QWidget()
        left_layout = QVBoxLayout(left)
        
        self.figure = Figure(figsize=(7, 5))
        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor('#1a1a1a')
        self.figure.patch.set_facecolor('#353535')
        
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, left)
        
        left_layout.addWidget(self.toolbar)
        left_layout.addWidget(self.canvas)
        
        # Right panel - controls
        right = QWidget()
        right.setMaximumWidth(320)
        right_layout = QVBoxLayout(right)
        
        # Plot type
        plot_group = QGroupBox("Plot Type")
        plot_layout = QVBoxLayout()
        self.rb_stress_strain = QRadioButton("Stress-Strain")
        self.rb_force_disp = QRadioButton("Force-Displacement")
        self.rb_stress_strain.setChecked(True)
        plot_layout.addWidget(self.rb_stress_strain)
        plot_layout.addWidget(self.rb_force_disp)
        plot_group.setLayout(plot_layout)
        right_layout.addWidget(plot_group)
        
        # Parameters
        right_layout.addWidget(QLabel("Offset % (default 0.2):"))
        self.offset_entry = QLineEdit("0.2")
        right_layout.addWidget(self.offset_entry)
        
        right_layout.addWidget(QLabel("Resolution:"))
        self.resolution_entry = QLineEdit("0.0001")
        right_layout.addWidget(self.resolution_entry)
        
        self.result_label = QLabel("Yield result: N/A")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet("color: #2a82da; font-weight: bold;")
        right_layout.addWidget(self.result_label)
        
        # Buttons
        btn_compute = QPushButton("Compute & Save")
        btn_compute.clicked.connect(self.compute_and_save)
        right_layout.addWidget(btn_compute)
        
        btn_refresh = QPushButton("Refresh Graph")
        btn_refresh.clicked.connect(self.draw_initial)
        right_layout.addWidget(btn_refresh)
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        right_layout.addWidget(btn_cancel)
        
        right_layout.addStretch()
        
        # Add to main layout
        layout.addWidget(left, stretch=3)
        layout.addWidget(right, stretch=1)
    
    def load_data(self):
        """Load CSV data"""
        try:
            self.df = pd.read_csv(self.filepath)
            try:
                self.df = self.df.drop(0)  # Drop first row if needed
            except:
                pass
            self.names = self.processor.detect_columns(self.df)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load data: {e}")
            self.reject()
    
    def draw_initial(self):
        """Draw initial plot"""
        self.ax.clear()
        
        try:
            if self.rb_stress_strain.isChecked() and self.names["strain"] and self.names["stress"]:
                x = self.df[self.names["strain"]].astype(float).values
                y = self.df[self.names["stress"]].astype(float).values
                self.ax.scatter(x, y, s=10, alpha=0.6, color='#2a82da')
                self.ax.set_xlabel("Strain", color='white')
                self.ax.set_ylabel("Stress", color='white')
            elif self.rb_force_disp.isChecked() and self.names["disp"] and self.names["force"]:
                x = self.df[self.names["disp"]].astype(float).values
                y = self.df[self.names["force"]].astype(float).values
                self.ax.scatter(x, y, s=10, alpha=0.6, color='#2a82da')
                self.ax.set_xlabel("Displacement", color='white')
                self.ax.set_ylabel("Force", color='white')
            
            self.ax.set_title(os.path.basename(self.filepath), color='white')
            self.ax.grid(True, alpha=0.3, color='white')
            self.ax.tick_params(colors='white')
            
        except Exception as e:
            self.ax.text(0.5, 0.5, f"Plot failed: {e}", ha='center', color='white')
        
        self.canvas.draw()
    
    def compute_and_save(self):
        """Compute yield point and save"""
        try:
            offset = float(self.offset_entry.text())
        except:
            offset = 0.2
        
        try:
            resolution = float(self.resolution_entry.text())
        except:
            resolution = 0.0001
        
        # Get modulus
        jpath = os.path.join(self.output_dir, "modulus_results.json")
        mod_val = None
        
        if os.path.exists(jpath):
            try:
                with open(jpath, 'r') as f:
                    d = json.load(f)
                entry = d.get(os.path.basename(self.filepath))
                if isinstance(entry, dict):
                    mod_val = entry.get("modulus")
                elif isinstance(entry, (int, float)):
                    mod_val = float(entry)
            except:
                pass
        
        if not mod_val:
            QMessageBox.critical(self, "Error", 
                "Modulus not found. Calculate modulus first.")
            return
        
        try:
            # Compute yield
            if self.rb_stress_strain.isChecked():
                yield_strain, yield_stress = self.processor.compute_yield_from_mod(
                    self.filepath, mod_val, offset, resolution
                )
            else:
                # For Force-Displacement (simplified)
                yield_strain, yield_stress = self.processor.compute_yield_from_mod(
                    self.filepath, mod_val, offset, resolution
                )
            
            if yield_strain is None:
                QMessageBox.critical(self, "Error", "Yield computation failed.")
                return
            
            # Save results
            self.processor.save_yield_result(
                self.filepath, self.output_dir,
                yield_strain, yield_stress
            )
            
            # Update plot
            self.ax.clear()
            
            if self.rb_stress_strain.isChecked():
                X = self.df[self.names["strain"]].astype(float).values
                Y = self.df[self.names["stress"]].astype(float).values
                
                # Draw offset line
                mod = float(mod_val) * 10.0
                max_strain = yield_strain + 0.1
                base_strains = np.arange(0.0, max_strain, resolution)
                Xlin = base_strains + offset
                Ylin = mod * (Xlin - offset)
                
                mask = X <= max_strain
                self.ax.scatter(X[mask], Y[mask], s=20, alpha=0.6, label="Data", color='#2a82da')
                self.ax.plot(Xlin, Ylin, '-', linewidth=2, label="Offset Line", color='orange')
                self.ax.plot([yield_strain], [yield_stress], 'ro', ms=12, label=f"Yield")
                
                self.ax.set_xlabel("Strain", color='white')
                self.ax.set_ylabel("Stress", color='white')
            
            self.ax.set_title(f"Yield: Strain={yield_strain}, Stress={yield_stress}", color='white')
            self.ax.legend()
            self.ax.grid(True, alpha=0.3, color='white')
            self.ax.tick_params(colors='white')
            self.canvas.draw()
            
            self.result_label.setText(f"Yield: strain={yield_strain:.4f}, stress={yield_stress:.3f}")
            
            QMessageBox.information(self, "Success", 
                f"Yield saved: Strain={yield_strain}, Stress={yield_stress}")
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Computation failed: {e}")