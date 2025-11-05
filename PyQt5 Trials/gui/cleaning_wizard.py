"""
gui/cleaning_wizard.py - File cleaning wizard dialog
"""

import os
import sys
from datetime import datetime
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, QThread, pyqtSignal

# Import backend cleaning functions
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class CleaningWorker(QThread):
    """Worker thread for file cleaning"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(int, int)  # succeeded, failed
    
    def __init__(self, files, output_dir, percent=None):
        super().__init__()
        self.files = files
        self.output_dir = output_dir
        self.percent = percent
        self.stop_requested = False
    
    def run(self):
        """Run cleaning process"""
        succeeded = 0
        failed = 0
        
        try:
            clean_func = self.simple_clean
            
            total = len(self.files)
            for idx, filepath in enumerate(self.files, start=1):
                if self.stop_requested:
                    break
                
                self.progress.emit(f"Processing ({idx}/{total}): {os.path.basename(filepath)}")
                
                try:
                    clean_func(filepath, self.output_dir, self.percent)
                    succeeded += 1
                except Exception as e:
                    self.progress.emit(f"ERROR: {filepath} - {e}")
                    failed += 1
        
        except Exception as e:
            self.progress.emit(f"Worker error: {e}")
        
        self.finished.emit(succeeded, failed)
    
    def simple_clean(self, filepath, output_dir, percent=None):
        """Simple fallback cleaning function"""
        import pandas as pd
        import shutil
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Just copy CSV files
        if filepath.endswith('.csv'):
            dest = os.path.join(output_dir, os.path.basename(filepath))
            shutil.copy2(filepath, dest)
        elif filepath.endswith(('.xlsx', '.xls')):
            # Convert Excel to CSV
            df = pd.read_excel(filepath)
            dest = os.path.join(output_dir, os.path.basename(filepath).replace('.xlsx', '.csv').replace('.xls', '.csv'))
            df.to_csv(dest, index=False)
    
    def stop(self):
        """Request stop"""
        self.stop_requested = True

class CleaningWizard(QDialog):
    """Wizard for cleaning and processing raw data files"""
    
    def __init__(self, parent, start_dir):
        super().__init__(parent)
        self.start_dir = start_dir
        self.current_dir = start_dir
        self.file_list = []
        self.worker = None
        
        self.setWindowTitle("Clean Files Wizard")
        self.resize(980, 620)
        
        self.setup_ui()
        self.refresh_file_list()
    
    def setup_ui(self):
        """Setup wizard UI"""
        layout = QVBoxLayout(self)
        
        # Top toolbar
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Directory:"))
        
        self.dir_entry = QLineEdit(self.current_dir)
        toolbar.addWidget(self.dir_entry)
        
        btn_browse = QPushButton("Browse")
        btn_browse.clicked.connect(self.choose_directory)
        toolbar.addWidget(btn_browse)
        
        btn_add = QPushButton("Add Files")
        btn_add.clicked.connect(self.add_files)
        toolbar.addWidget(btn_add)
        
        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.refresh_file_list)
        toolbar.addWidget(btn_refresh)
        
        layout.addLayout(toolbar)
        
        # Main content
        main_splitter = QSplitter(Qt.Horizontal)
        
        # Left - file list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        
        # File list controls
        list_controls = QHBoxLayout()
        btn_select_all = QPushButton("Select All")
        btn_select_all.clicked.connect(lambda: self.file_list_widget.selectAll())
        list_controls.addWidget(btn_select_all)
        
        btn_deselect = QPushButton("Deselect All")
        btn_deselect.clicked.connect(lambda: self.file_list_widget.clearSelection())
        list_controls.addWidget(btn_deselect)
        
        btn_remove = QPushButton("Remove Selected")
        btn_remove.clicked.connect(self.remove_selected)
        list_controls.addWidget(btn_remove)
        
        btn_clear = QPushButton("Clear List")
        btn_clear.clicked.connect(self.clear_list)
        list_controls.addWidget(btn_clear)
        
        left_layout.addLayout(list_controls)
        
        # File list
        self.file_list_widget = QListWidget()
        self.file_list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        left_layout.addWidget(self.file_list_widget)
        
        # Right - actions
        right = QWidget()
        right.setMaximumWidth(340)
        right_layout = QVBoxLayout(right)
        
        right_layout.addWidget(QLabel("<b>Actions</b>"))
        
        btn_auto = QPushButton("Auto (one-click)")
        btn_auto.setStyleSheet("background-color: #2e7d32;")
        btn_auto.clicked.connect(self.action_auto)
        right_layout.addWidget(btn_auto)
        
        btn_normal = QPushButton("Normal (post-process)")
        btn_normal.clicked.connect(self.action_normal)
        right_layout.addWidget(btn_normal)
        
        right_layout.addWidget(QLabel("<b>Extensometer Removal</b>"))
        
        btn_noext = QPushButton("No Ext")
        btn_noext.clicked.connect(lambda: self.action_ext_remove(None))
        right_layout.addWidget(btn_noext)
        
        btn_50 = QPushButton("50%")
        btn_50.clicked.connect(lambda: self.action_ext_remove(50))
        right_layout.addWidget(btn_50)
        
        btn_95 = QPushButton("95%")
        btn_95.clicked.connect(lambda: self.action_ext_remove(95))
        right_layout.addWidget(btn_95)
        
        # Custom percent
        custom_layout = QHBoxLayout()
        custom_layout.addWidget(QLabel("Custom %:"))
        self.custom_percent = QLineEdit("85")
        self.custom_percent.setMaximumWidth(60)
        custom_layout.addWidget(self.custom_percent)
        btn_custom = QPushButton("Apply")
        btn_custom.clicked.connect(self.action_custom)
        custom_layout.addWidget(btn_custom)
        right_layout.addLayout(custom_layout)
        
        right_layout.addStretch()
        
        # Add to splitter
        main_splitter.addWidget(left)
        main_splitter.addWidget(right)
        main_splitter.setSizes([640, 340])
        
        layout.addWidget(main_splitter)
        
        # Bottom - log
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        log_layout.addWidget(self.log_text)
        
        layout.addWidget(log_group)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Bottom buttons
        bottom_buttons = QHBoxLayout()
        bottom_buttons.addStretch()
        
        self.btn_stop = QPushButton("Stop Processing")
        self.btn_stop.setStyleSheet("background-color: #d32f2f;")
        self.btn_stop.clicked.connect(self.stop_processing)
        self.btn_stop.setVisible(False)
        bottom_buttons.addWidget(self.btn_stop)
        
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        bottom_buttons.addWidget(btn_close)
        
        layout.addLayout(bottom_buttons)
        
        self.log("Wizard started. Choose a directory or add files.")
    
    def log(self, message):
        """Add log message"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
    
    def choose_directory(self):
        """Choose directory"""
        folder = QFileDialog.getExistingDirectory(self, "Select Directory", self.current_dir)
        if folder:
            self.current_dir = folder
            self.dir_entry.setText(folder)
            self.refresh_file_list()
    
    def refresh_file_list(self):
        """Refresh file list from directory"""
        self.file_list.clear()
        directory = self.dir_entry.text()
        
        if not os.path.isdir(directory):
            self.log(f"Directory not found: {directory}")
            return
        
        exts = ('.csv', '.xls', '.xlsx')
        try:
            for root, _, files in os.walk(directory):
                for fn in files:
                    if fn.lower().endswith(exts) and "output" not in root.lower():
                        self.file_list.append(os.path.join(root, fn))
        except Exception as e:
            self.log(f"Error scanning directory: {e}")
        
        self._repopulate_list()
        self.log(f"Found {len(self.file_list)} file(s) in '{directory}'")
    
    def add_files(self):
        """Add files dialog"""
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add Files", self.current_dir,
            "Data Files (*.csv *.xlsx *.xls);;All Files (*.*)"
        )
        
        if files:
            added = 0
            for f in files:
                if f not in self.file_list:
                    self.file_list.append(f)
                    added += 1
            self._repopulate_list()
            self.log(f"Added {added} file(s)")
    
    def _repopulate_list(self):
        """Repopulate list widget"""
        self.file_list_widget.clear()
        for path in sorted(self.file_list):
            self.file_list_widget.addItem(os.path.basename(path))
    
    def remove_selected(self):
        """Remove selected files from list"""
        selected = self.file_list_widget.selectedItems()
        if not selected:
            return
        
        # Get indices and remove from file_list
        indices = [self.file_list_widget.row(item) for item in selected]
        sorted_files = sorted(self.file_list)
        
        for idx in sorted(indices, reverse=True):
            path = sorted_files[idx]
            self.file_list.remove(path)
        
        self._repopulate_list()
        self.log(f"Removed {len(indices)} file(s)")
    
    def clear_list(self):
        """Clear file list"""
        self.file_list.clear()
        self._repopulate_list()
        self.log("List cleared")
    
    def action_auto(self):
        """Auto processing (all files)"""
        if not self.file_list:
            QMessageBox.information(self, "Info", "No files to process")
            return
        
        output_dir = os.path.join(self.current_dir, "output", "Cleaned Files")
        self._start_processing(list(self.file_list), output_dir, None, "AUTO")
    
    def action_normal(self):
        """Normal processing (selected files)"""
        selected = self._get_selected_paths()
        if not selected:
            QMessageBox.information(self, "Info", "No files selected")
            return
        
        output_dir = os.path.join(self.current_dir, "output", "Cleaned Files")
        self._start_processing(selected, output_dir, None, "NORMAL")
    
    def action_ext_remove(self, percent):
        """Extensometer removal"""
        selected = self._get_selected_paths()
        if not selected:
            QMessageBox.information(self, "Info", "No files selected")
            return
        
        output_dir = os.path.join(self.current_dir, "output", "Cleaned Files")
        self._start_processing(selected, output_dir, percent, f"EXT-{percent}")
    
    def action_custom(self):
        """Custom percent"""
        try:
            pct = float(self.custom_percent.text())
            self.action_ext_remove(pct)
        except:
            QMessageBox.warning(self, "Warning", "Invalid percent value")
    
    def _get_selected_paths(self):
        """Get selected file paths"""
        selected_items = self.file_list_widget.selectedItems()
        if not selected_items:
            return []
        
        sorted_files = sorted(self.file_list)
        indices = [self.file_list_widget.row(item) for item in selected_items]
        return [sorted_files[i] for i in indices]
    
    def _start_processing(self, files, output_dir, percent, mode):
        """Start processing worker"""
        os.makedirs(output_dir, exist_ok=True)
        
        self.log(f"[{mode}] Starting processing of {len(files)} file(s)")
        self.log(f"Output: {output_dir}")
        
        self.worker = CleaningWorker(files, output_dir, percent)
        self.worker.progress.connect(self.log)
        self.worker.finished.connect(self._on_finished)
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(0)  # Indeterminate
        self.btn_stop.setVisible(True)
        
        self.worker.start()
    
    def _on_finished(self, succeeded, failed):
        """Handle worker finished"""
        self.log(f"Finished. Success: {succeeded}, Failed: {failed}")
        self.progress_bar.setVisible(False)
        self.btn_stop.setVisible(False)
        
        QMessageBox.information(self, "Complete", 
            f"Processing complete.\n\nSucceeded: {succeeded}\nFailed: {failed}")
    
    def stop_processing(self):
        """Stop processing"""
        if self.worker:
            self.worker.stop()
            self.log("Stop requested...")