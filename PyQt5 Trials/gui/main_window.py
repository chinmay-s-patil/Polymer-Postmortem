"""
gui/main_window.py - Complete main application window with all functionality
"""

import os
import json
import threading
from datetime import datetime
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QPixmap, QImage, QIcon
from PyQt5.QtGui import QColor
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import pandas as pd
import numpy as np

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from constants import VERSION, BASEDIR, DEFAULT_CHARL, DEFAULT_AREA, ICON_PIXELS
from core.data_processor import DataProcessor

class WorkerSignals(QObject):
    """Signals for worker threads"""
    finished = pyqtSignal()
    error = pyqtSignal(str)
    result = pyqtSignal(object)
    progress = pyqtSignal(str)

class MainWindow(QMainWindow):
    """Modern PyQt5 main window for Polymer PostMortem"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Polymer PostMortem v{VERSION}")
        self.setGeometry(100, 100, 1280, 780)
        
        # State management
        self.current_dir = BASEDIR
        self.output_dir = None
        self.current_file = None
        self.all_files = []
        self.item_paths = {}
        self.master_data = {}
        self.charl = DEFAULT_CHARL
        self.area = DEFAULT_AREA
        self.batch_stop = False
        
        # Initialize data processor
        self.processor = DataProcessor()
        
        # Create flag icons
        self._create_flag_icons()
        
        # Setup UI
        self._setup_ui()
        self._setup_menu()
        self._setup_connections()
        
        # File watcher timer
        self._master_mtime = None
        self._watching = False
        self.watch_timer = QTimer()
        self.watch_timer.timeout.connect(self._poll_master)
        
        # Initial population
        if os.path.isdir(self.current_dir):
            self.populate_cleaned_files(self.current_dir)
    
    def _create_flag_icons(self):
        """Create flag icons for tree display"""
        # Flag ON (red flag)
        self.flag_on_pixmap = QPixmap(ICON_PIXELS, ICON_PIXELS)
        self.flag_on_pixmap.fill(Qt.white)
        from PyQt5.QtGui import QPainter, QColor, QBrush
        painter = QPainter(self.flag_on_pixmap)
        # Draw pole
        painter.fillRect(2, 2, 2, ICON_PIXELS-4, QColor("#333333"))
        # Draw red flag
        painter.fillRect(3, 3, ICON_PIXELS-5, 5, QColor("#d92b2b"))
        painter.end()
        self.flag_on_icon = QIcon(self.flag_on_pixmap)
        
        # Flag OFF (light gray)
        self.flag_off_pixmap = QPixmap(ICON_PIXELS, ICON_PIXELS)
        self.flag_off_pixmap.fill(QColor("#f3f3f3"))
        self.flag_off_icon = QIcon(self.flag_off_pixmap)
    
    def _setup_ui(self):
        """Setup the main UI layout"""
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)
        
        # Top toolbar
        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(QLabel("Directory:"))
        
        self.dir_entry = QLineEdit(self.current_dir)
        self.dir_entry.setMinimumWidth(400)
        toolbar_layout.addWidget(self.dir_entry)
        
        self.btn_browse = QPushButton("Browse")
        toolbar_layout.addWidget(self.btn_browse)
        
        self.btn_set = QPushButton("Set")
        toolbar_layout.addWidget(self.btn_set)
        
        self.btn_clean = QPushButton("Clean Files")
        toolbar_layout.addWidget(self.btn_clean)
        
        self.btn_refresh = QPushButton("Refresh")
        toolbar_layout.addWidget(self.btn_refresh)
        
        self.btn_reset_all = QPushButton("Reset All")
        toolbar_layout.addWidget(self.btn_reset_all)
        
        toolbar_layout.addStretch()
        main_layout.addLayout(toolbar_layout)
        
        # Main content splitter
        splitter = QSplitter(Qt.Horizontal)
        
        # Left panel
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)
        
        # Right panel
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)
        
        splitter.setSizes([500, 780])
        main_layout.addWidget(splitter)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("Ready")
        self.status_bar.addWidget(self.status_label)
        
        # Metrics labels
        self.metric_labels = {
            'modulus': QLabel("Modulus: N/A"),
            'yield': QLabel("Yield: N/A"),
            'breakpoint': QLabel("Break: N/A"),
            'ultimate': QLabel("Ultimate: N/A")
        }
        for label in self.metric_labels.values():
            self.status_bar.addPermanentWidget(label)
        
        # Attribution
        attr_label = QLabel(f"CC BY 4.0 — Polymer PostMortem v{VERSION} — Chinmay Patil")
        attr_label.setStyleSheet("color: #888888; font-size: 9pt;")
        self.status_bar.addPermanentWidget(attr_label)
    
    def _create_left_panel(self):
        """Create left panel with file tree"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Search box
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Filter:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search files...")
        search_layout.addWidget(self.search_box)
        layout.addLayout(search_layout)
        
        # File tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["File", "M", "Y", "B", "U"])
        self.tree.setColumnWidth(0, 380)
        self.tree.setColumnWidth(1, 30)
        self.tree.setColumnWidth(2, 30)
        self.tree.setColumnWidth(3, 30)
        self.tree.setColumnWidth(4, 30)
        self.tree.setAlternatingRowColors(True)
        layout.addWidget(self.tree)
        
        return panel
    
    def _create_right_panel(self):
        """Create right panel with actions and preview"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Action buttons row 1
        action_row1 = QHBoxLayout()
        self.btn_modulus = QPushButton("Modulus")
        self.btn_yield = QPushButton("Yield")
        self.btn_breakpoint = QPushButton("Break Point")
        self.btn_ultimate = QPushButton("Ultimate")
        self.btn_reset = QPushButton("Reset")
        self.btn_flag = QPushButton("Flag")
        self.btn_preview = QPushButton("Preview Data")
        
        for btn in [self.btn_modulus, self.btn_yield, self.btn_breakpoint, 
                   self.btn_ultimate, self.btn_reset, self.btn_flag, 
                   self.btn_preview]:
            action_row1.addWidget(btn)
        
        self.btn_save_excel = QPushButton("Save All → Excel")
        action_row1.addWidget(self.btn_save_excel)
        layout.addLayout(action_row1)
        
        # Action buttons row 2 (batch operations)
        action_row2 = QHBoxLayout()
        self.btn_batch_mod = QPushButton("Batch Modulus")
        self.btn_batch_yield = QPushButton("Batch Yield")
        self.btn_batch_break = QPushButton("Batch Break")
        self.btn_batch_auto_mod = QPushButton("Batch Auto Modulus")
        self.btn_batch_auto_yield = QPushButton("Batch Auto Yield")
        self.btn_batch_auto_ult = QPushButton("Batch Auto Ultimate")
        self.btn_batch_manual_all = QPushButton("Batch Manual All")
        self.btn_stop_batch = QPushButton("Stop Batch")
        self.btn_stop_batch.setStyleSheet("background-color: #d32f2f;")
        
        for btn in [self.btn_batch_mod, self.btn_batch_yield, self.btn_batch_break,
                   self.btn_batch_auto_mod, self.btn_batch_auto_yield, 
                   self.btn_batch_auto_ult, self.btn_batch_manual_all]:
            action_row2.addWidget(btn)
        action_row2.addWidget(self.btn_stop_batch)
        layout.addLayout(action_row2)
        
        # Matplotlib preview
        preview_frame = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_frame)
        
        self.figure = Figure(figsize=(8, 5))
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor('#1a1a1a')
        self.figure.patch.set_facecolor('#353535')
        
        self.toolbar = NavigationToolbar(self.canvas, preview_frame)
        preview_layout.addWidget(self.toolbar)
        preview_layout.addWidget(self.canvas)
        
        layout.addWidget(preview_frame)
        
        return panel
    
    def _setup_menu(self):
        """Setup menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        open_action = QAction("Open Directory", self)
        open_action.triggered.connect(self.browse_folder)
        file_menu.addAction(open_action)
        
        clean_action = QAction("Clean Files", self)
        clean_action.triggered.connect(self.start_cleaning)
        file_menu.addAction(clean_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("Tools")
        
        refresh_action = QAction("Refresh", self)
        refresh_action.triggered.connect(self.manual_refresh)
        tools_menu.addAction(refresh_action)
        
        reset_action = QAction("Reset All", self)
        reset_action.triggered.connect(self.reset_all_files)
        tools_menu.addAction(reset_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def _setup_connections(self):
        """Setup signal/slot connections"""
        self.btn_browse.clicked.connect(self.browse_folder)
        self.btn_set.clicked.connect(self.set_directory)
        self.btn_clean.clicked.connect(self.start_cleaning)
        self.btn_refresh.clicked.connect(self.manual_refresh)
        self.btn_reset_all.clicked.connect(self.reset_all_files)
        
        self.btn_modulus.clicked.connect(self.action_modulus)
        self.btn_yield.clicked.connect(self.action_yield)
        self.btn_breakpoint.clicked.connect(self.action_breakpoint)
        self.btn_ultimate.clicked.connect(self.action_ultimate)
        self.btn_reset.clicked.connect(self.reset_file)
        self.btn_flag.clicked.connect(self.toggle_flag)
        self.btn_preview.clicked.connect(self.preview_file_open)
        self.btn_save_excel.clicked.connect(self.save_all_to_excel)
        
        self.btn_batch_mod.clicked.connect(self.batch_manual_modulus)
        self.btn_batch_yield.clicked.connect(self.batch_manual_yield)
        self.btn_batch_break.clicked.connect(self.batch_manual_break)
        self.btn_batch_auto_mod.clicked.connect(self.batch_auto_modulus)
        self.btn_batch_auto_yield.clicked.connect(self.batch_auto_yield)
        self.btn_batch_auto_ult.clicked.connect(self.batch_auto_ultimate)
        self.btn_batch_manual_all.clicked.connect(self.batch_manual_all)
        self.btn_stop_batch.clicked.connect(self.stop_batch)
        
        self.tree.itemSelectionChanged.connect(self.on_tree_select)
        self.tree.itemDoubleClicked.connect(self.on_tree_double_click)
        self.search_box.textChanged.connect(self.filter_list)
    
    # ==================== Directory Operations ====================
    
    def browse_folder(self):
        """Open folder browser"""
        folder = QFileDialog.getExistingDirectory(
            self, "Select Directory", self.current_dir
        )
        if folder:
            self.dir_entry.setText(folder)
            self.current_dir = folder
    
    def set_directory(self):
        """Set working directory"""
        chosen = self.dir_entry.text().strip()
        if not chosen or not os.path.isdir(chosen):
            self.status_label.setText("Path does not exist.")
            return
        
        self.current_dir = chosen
        self.output_dir = os.path.join(chosen, "output")
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Initial merge and populate
        self.processor.merge_individual_jsons(self.output_dir)
        self.populate_cleaned_files(chosen)
        
        # Start watcher
        self._start_master_watcher()
        self.status_label.setText(f"Directory set: {chosen}")
    
    def start_cleaning(self):
        """Open cleaning wizard"""
        if not self.current_dir or not os.path.isdir(self.current_dir):
            self.status_label.setText("Set a valid directory first.")
            return
        
        from gui.cleaning_wizard import CleaningWizard
        wizard = CleaningWizard(self, self.current_dir)
        wizard.exec_()
        
        # Refresh after cleaning
        self.manual_refresh()
    
    def populate_cleaned_files(self, directory):
        """Populate tree with files from directory"""
        files = []
        for root, _, fls in os.walk(directory):
            for f in fls:
                if (f.lower().endswith((".csv", ".xlsx")) and 
                    "output" in root.lower() and 
                    "tensile_results" not in f.lower()):
                    files.append(os.path.join(root, f))
        
        files = sorted(files)
        self.all_files = files
        self._refresh_tree(files)
    
    def _refresh_tree(self, files):
        """Refresh tree widget with files"""
        self.tree.clear()
        self.item_paths.clear()
        
        master = self.processor.load_master(self.output_dir) if self.output_dir else {}
        
        for path in files:
            basename = os.path.basename(path)
            entry = master.get(basename, {})
            
            # Check completion status
            m_done = "✓" if entry.get("modulus") else "✗"
            y_done = "✓" if entry.get("yield") else "✗"
            b_done = "✓" if entry.get("breakpoint") else "✗"
            u_done = "✓" if entry.get("ultimate") else "✗"
            
            # Create tree item
            item = QTreeWidgetItem([basename, m_done, y_done, b_done, u_done])
            
            # Set flag icon
            flag_bool = bool(entry.get("flag", False))
            item.setIcon(0, self.flag_on_icon if flag_bool else self.flag_off_icon)
            
            # Color code based on completion
            done_count = sum(1 for x in [m_done, y_done, b_done, u_done] if x == "✓")
            if done_count == 4:
                item.setBackground(0, QColor("#e6ffeb"))
            elif done_count > 0:
                item.setBackground(0, QColor("#fff7e6"))
            else:
                item.setBackground(0, QColor("#ffecec"))
            
            self.tree.addTopLevelItem(item)
            self.item_paths[id(item)] = path
        
        self.status_label.setText(f"{len(files)} files found.")
    
    def on_tree_select(self):
        """Handle tree selection"""
        items = self.tree.selectedItems()
        if not items:
            return
        
        item = items[0]
        path = self.item_paths.get(id(item))
        if not path:
            return
        
        self.current_file = path
        self.status_label.setText(f"Selected: {os.path.basename(path)}")
        
        # Update metrics
        if self.output_dir:
            self.master_data = self.processor.load_master(self.output_dir)
        
        info = self.master_data.get(os.path.basename(path), {})
        self.metric_labels['modulus'].setText(f"Modulus: {info.get('modulus', 'N/A')}")
        self.metric_labels['yield'].setText(f"Yield: {info.get('yield', 'N/A')}")
        self.metric_labels['breakpoint'].setText(f"Break: {info.get('breakpoint', 'N/A')}")
        self.metric_labels['ultimate'].setText(f"Ultimate: {info.get('ultimate', 'N/A')}")
        
        # Update preview
        self._draw_preview(path)
    
    def _draw_preview(self, path):
        """Draw preview plot"""
        self.ax.clear()
        try:
            df = pd.read_csv(path)
            names = self.processor.detect_columns(df)
            
            if names["strain"] and names["stress"]:
                x = df[names["strain"]].astype(float)
                y = df[names["stress"]].astype(float)
                self.ax.plot(x, y, '.', ms=2, color='#2a82da')
                self.ax.set_xlabel("Strain", color='white')
                self.ax.set_ylabel("Stress", color='white')
            else:
                nums = df.select_dtypes(include=[np.number]).columns.tolist()
                if len(nums) >= 2:
                    x = df[nums[0]].astype(float)
                    y = df[nums[1]].astype(float)
                    self.ax.plot(x, y, '.', ms=2, color='#2a82da')
                    self.ax.set_xlabel(nums[0], color='white')
                    self.ax.set_ylabel(nums[1], color='white')
            
            self.ax.tick_params(colors='white')
            self.ax.grid(True, alpha=0.3)
            
        except Exception as e:
            self.ax.text(0.5, 0.5, f"Preview failed: {e}", ha='center', color='white')
        
        self.canvas.draw()
    
    # ==================== Action Methods ====================
    
    def action_modulus(self):
        if not self.current_file:
            QMessageBox.information(self, "Info", "Select a file first.")
            return
        from gui.modulus_dialog import ModulusDialog
        dialog = ModulusDialog(self, self.current_file, self.processor, self.output_dir)
        if dialog.exec_():
            self.manual_refresh()
    
    def action_yield(self):
        if not self.current_file:
            QMessageBox.information(self, "Info", "Select a file first.")
            return
        from gui.yield_dialog import YieldDialog
        dialog = YieldDialog(self, self.current_file, self.processor, self.output_dir)
        if dialog.exec_():
            self.manual_refresh()
    
    def action_breakpoint(self):
        if not self.current_file:
            QMessageBox.information(self, "Info", "Select a file first.")
            return
        from gui.breakpoint_dialog import BreakpointDialog
        dialog = BreakpointDialog(self, self.current_file, self.processor, self.output_dir)
        if dialog.exec_():
            self.manual_refresh()
    
    def action_ultimate(self):
        if not self.current_file:
            QMessageBox.information(self, "Info", "Select a file first.")
            return
        
        def worker():
            try:
                u = self.processor.compute_ultimate_stress(self.current_file)
                if u is not None:
                    master = self.processor.load_master(self.output_dir)
                    master.setdefault(os.path.basename(self.current_file), {})["ultimate"] = u
                    self.processor.save_master(self.output_dir, master)
                    self.processor.merge_individual_jsons(self.output_dir)
                    return f"Ultimate: {u}"
                return "Ultimate computation failed"
            except Exception as e:
                return f"Error: {e}"
        
        self.status_label.setText("Computing ultimate...")
        threading.Thread(target=lambda: self._run_worker(worker), daemon=True).start()
    
    def _run_worker(self, worker_func):
        """Run a worker function and update UI"""
        result = worker_func()
        QTimer.singleShot(0, lambda: (
            self.status_label.setText(result),
            self.manual_refresh()
        ))
    
    def reset_file(self):
        if not self.current_file or not self.output_dir:
            return
        
        reply = QMessageBox.question(self, 'Confirm Reset',
            f"Reset data for '{os.path.basename(self.current_file)}'?",
            QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            fname = os.path.basename(self.current_file)
            # Delete from metric JSONs
            for metric in ["modulus_results.json", "yield_results.json", "break_results.json"]:
                path = os.path.join(self.output_dir, metric)
                if os.path.exists(path):
                    try:
                        with open(path, 'r') as f:
                            data = json.load(f)
                        data.pop(fname, None)
                        self.processor.write_json_safe(path, data)
                    except:
                        pass
            
            self.processor.merge_individual_jsons(self.output_dir)
            self.manual_refresh()
            self.status_label.setText(f"Reset complete for {fname}")
    
    def toggle_flag(self):
        if not self.current_file or not self.output_dir:
            return
        
        fname = os.path.basename(self.current_file)
        master = self.processor.load_master(self.output_dir)
        entry = master.setdefault(fname, {})
        entry["flag"] = not bool(entry.get("flag", False))
        self.processor.save_master(self.output_dir, master)
        self.processor.merge_individual_jsons(self.output_dir)
        self.manual_refresh()
    
    def preview_file_open(self):
        if not self.current_file:
            return
        from gui.preview_dialog import PreviewDialog
        dialog = PreviewDialog(self, self.current_file)
        dialog.exec_()
    
    def save_all_to_excel(self):
        if not self.output_dir:
            QMessageBox.warning(self, "Warning", "Set directory first.")
            return
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Results", 
            f"tensile_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            "Excel Files (*.xlsx)"
        )
        
        if not filename:
            return
        
        try:
            master = self.processor.load_master(self.output_dir)
            
            # Load individual metric files
            mods = {}
            ylds = {}
            brks = {}
            
            for metric, data_dict in [
                ("modulus_results.json", mods),
                ("yield_results.json", ylds),
                ("break_results.json", brks)
            ]:
                path = os.path.join(self.output_dir, metric)
                if os.path.exists(path):
                    with open(path, 'r') as f:
                        data_dict.update(json.load(f))
            
            # Create summary
            rows = []
            all_files = sorted(set(list(mods.keys()) + list(ylds.keys()) + list(brks.keys()) + list(master.keys())))
            
            for fname in all_files:
                m = mods.get(fname, {})
                y = ylds.get(fname, {})
                b = brks.get(fname, [])
                master_entry = master.get(fname, {})
                
                mod_val = m.get("modulus") if isinstance(m, dict) else m
                y_strain = y.get("strain") if isinstance(y, dict) else None
                y_stress = y.get("stress") if isinstance(y, dict) else None
                b_strain = b[0] if isinstance(b, list) and len(b) >= 2 else None
                b_stress = b[1] if isinstance(b, list) and len(b) >= 2 else None
                
                rows.append({
                    "File": fname,
                    "Modulus": mod_val,
                    "Yield Strain": y_strain,
                    "Yield Stress": y_stress,
                    "Ultimate Stress": master_entry.get("ultimate"),
                    "Break Strain": b_strain,
                    "Break Stress": b_stress
                })
            
            df = pd.DataFrame(rows)
            df.to_excel(filename, index=False)
            
            QMessageBox.information(self, "Success", f"Saved to {filename}")
            self.status_label.setText(f"Exported to {filename}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Export failed: {e}")
    
    def manual_refresh(self):
        if self.output_dir:
            self.processor.merge_individual_jsons(self.output_dir)
            self.populate_cleaned_files(self.current_dir)
            self.status_label.setText("Refreshed.")
    
    def reset_all_files(self):
        reply = QMessageBox.question(self, 'Confirm Reset All',
            "Delete all result JSONs? This removes all computed data.",
            QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes and self.output_dir:
            for fname in ["modulus_results.json", "yield_results.json", "break_results.json", "gui_master.json"]:
                path = os.path.join(self.output_dir, fname)
                if os.path.exists(path):
                    os.remove(path)
            
            self.processor.merge_individual_jsons(self.output_dir)
            self.manual_refresh()
            self.status_label.setText("Reset all complete.")
    
    def filter_list(self):
        """Filter file list based on search"""
        query = self.search_box.text().lower()
        if not query:
            self._refresh_tree(self.all_files)
            return
        
        filtered = [p for p in self.all_files if query in os.path.basename(p).lower()]
        self._refresh_tree(filtered)
    
    def on_tree_double_click(self, item, column):
        """Handle double click on tree item"""
        self.preview_file_open()
    
    def _start_master_watcher(self):
        """Start file watcher"""
        if self._watching:
            return
        self._watching = True
        self._update_master_mtime()
        self.watch_timer.start(800)
    
    def _update_master_mtime(self):
        """Update master file modification time"""
        p = self.processor.master_json_path(self.output_dir) if self.output_dir else None
        try:
            self._master_mtime = os.path.getmtime(p) if p and os.path.exists(p) else None
        except:
            self._master_mtime = None
    
    def _poll_master(self):
        """Poll for master file changes"""
        if not self._watching or not self.output_dir:
            return
        
        p = self.processor.master_json_path(self.output_dir)
        try:
            new_m = os.path.getmtime(p) if p and os.path.exists(p) else None
        except:
            new_m = None
        
        if new_m != self._master_mtime:
            self._master_mtime = new_m
            self.processor.merge_individual_jsons(self.output_dir)
            self.populate_cleaned_files(self.current_dir)
    
    # ==================== Batch Operations ====================
    
    def batch_manual_modulus(self):
        QMessageBox.information(self, "Info", "Batch manual operations not yet implemented")
    
    def batch_manual_yield(self):
        QMessageBox.information(self, "Info", "Batch manual operations not yet implemented")
    
    def batch_manual_break(self):
        QMessageBox.information(self, "Info", "Batch manual operations not yet implemented")
    
    def batch_auto_modulus(self):
        if not self.all_files or not self.output_dir:
            return
        
        self.batch_stop = False
        self.status_label.setText("Batch Auto Modulus started...")
        
        def worker():
            jpath = os.path.join(self.output_dir, "modulus_results.json")
            data = {}
            if os.path.exists(jpath):
                try:
                    with open(jpath, 'r') as f:
                        data = json.load(f)
                except:
                    pass
            
            total = len(self.all_files)
            for idx, f in enumerate(self.all_files, start=1):
                if self.batch_stop:
                    break
                
                fname = os.path.basename(f)
                if fname in data and data.get(fname, {}).get("modulus"):
                    continue
                
                QTimer.singleShot(0, lambda idx=idx, f=f: 
                    self.status_label.setText(f"Auto Modulus {idx}/{total}: {os.path.basename(f)}"))
                
                mod = self.processor.compute_auto_modulus(f)
                if mod is not None:
                    data[fname] = {"modulus": mod, "length": None, "area": None}
                    self.processor.write_json_safe(jpath, data)
            
            self.processor.merge_individual_jsons(self.output_dir)
            QTimer.singleShot(0, lambda: (
                self.status_label.setText("Batch Auto Modulus completed."),
                self.manual_refresh()
            ))
        
        threading.Thread(target=worker, daemon=True).start()
    
    def batch_auto_yield(self):
        if not self.all_files or not self.output_dir:
            return
        
        self.batch_stop = False
        self.status_label.setText("Batch Auto Yield started...")
        
        def worker():
            jmod = os.path.join(self.output_dir, "modulus_results.json")
            jyield = os.path.join(self.output_dir, "yield_results.json")
            
            mods = {}
            ylds = {}
            
            if os.path.exists(jmod):
                try:
                    with open(jmod, 'r') as f:
                        mods = json.load(f)
                except:
                    pass
            
            if os.path.exists(jyield):
                try:
                    with open(jyield, 'r') as f:
                        ylds = json.load(f)
                except:
                    pass
            
            total = len(self.all_files)
            for idx, f in enumerate(self.all_files, start=1):
                if self.batch_stop:
                    break
                
                fname = os.path.basename(f)
                if fname in ylds:
                    continue
                
                mod_entry = mods.get(fname)
                mod_val = None
                if isinstance(mod_entry, dict):
                    mod_val = mod_entry.get("modulus")
                elif isinstance(mod_entry, (int, float)):
                    mod_val = mod_entry
                
                if not mod_val:
                    continue
                
                QTimer.singleShot(0, lambda idx=idx, f=f: 
                    self.status_label.setText(f"Auto Yield {idx}/{total}: {os.path.basename(f)}"))
                
                ystr, yst = self.processor.compute_yield_from_mod(f, mod_val)
                if ystr is not None:
                    ylds[fname] = {"strain": ystr, "stress": yst}
                    self.processor.write_json_safe(jyield, ylds)
            
            self.processor.merge_individual_jsons(self.output_dir)
            QTimer.singleShot(0, lambda: (
                self.status_label.setText("Batch Auto Yield completed."),
                self.manual_refresh()
            ))
        
        threading.Thread(target=worker, daemon=True).start()
    
    def batch_auto_ultimate(self):
        if not self.all_files or not self.output_dir:
            return
        
        self.batch_stop = False
        self.status_label.setText("Batch Auto Ultimate started...")
        
        def worker():
            master = self.processor.load_master(self.output_dir)
            total = len(self.all_files)
            
            for idx, f in enumerate(self.all_files, start=1):
                if self.batch_stop:
                    break
                
                fname = os.path.basename(f)
                QTimer.singleShot(0, lambda idx=idx, f=f: 
                    self.status_label.setText(f"Auto Ultimate {idx}/{total}: {os.path.basename(f)}"))
                
                u = self.processor.compute_ultimate_stress(f)
                if u is not None:
                    master.setdefault(fname, {})["ultimate"] = u
                    self.processor.save_master(self.output_dir, master)
            
            self.processor.merge_individual_jsons(self.output_dir)
            QTimer.singleShot(0, lambda: (
                self.status_label.setText("Batch Auto Ultimate completed."),
                self.manual_refresh()
            ))
        
        threading.Thread(target=worker, daemon=True).start()
    
    def batch_manual_all(self):
        self.batch_manual_modulus()
    
    def stop_batch(self):
        self.batch_stop = True
        self.status_label.setText("Batch stop requested...")
    
    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(
            self,
            "About Polymer PostMortem",
            f"<h2>Polymer PostMortem v{VERSION}</h2>"
            f"<p>Modern material testing analysis tool</p>"
            f"<p>CC BY 4.0 — Chinmay Patil</p>"
            f"<p>Built with PyQt5 and Python</p>"
        )