"""
gui/preview_dialog.py - File preview dialog
"""

import os
import pandas as pd
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt

class PreviewDialog(QDialog):
    """Dialog for previewing file contents"""
    
    def __init__(self, parent, filepath):
        super().__init__(parent)
        self.filepath = filepath
        
        self.setWindowTitle(f"Preview - {os.path.basename(filepath)}")
        self.resize(1000, 600)
        
        self.setup_ui()
        self.load_data()
    
    def setup_ui(self):
        """Setup dialog UI"""
        layout = QVBoxLayout(self)
        
        # Info bar
        info_layout = QHBoxLayout()
        self.info_label = QLabel(f"Loading {os.path.basename(self.filepath)}...")
        info_layout.addWidget(self.info_label)
        info_layout.addStretch()
        layout.addLayout(info_layout)
        
        # Table view
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)
        
        # Bottom buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        button_layout.addWidget(btn_close)
        
        layout.addLayout(button_layout)
    
    def load_data(self):
        """Load and display file data"""
        try:
            ext = os.path.splitext(self.filepath)[1].lower()
            
            if ext == '.csv':
                df = pd.read_csv(self.filepath, dtype=str, nrows=1000)  # Limit rows for performance
            elif ext in ('.xlsx', '.xls'):
                df = pd.read_excel(self.filepath, dtype=str, nrows=1000)
            else:
                self.info_label.setText("Unsupported file format")
                return
            
            df = df.fillna("")
            
            # Setup table
            self.table.setRowCount(len(df))
            self.table.setColumnCount(len(df.columns))
            self.table.setHorizontalHeaderLabels([str(c) for c in df.columns])
            
            # Populate table
            for i in range(len(df)):
                for j in range(len(df.columns)):
                    item = QTableWidgetItem(str(df.iloc[i, j]))
                    self.table.setItem(i, j, item)
            
            # Auto-resize columns
            self.table.resizeColumnsToContents()
            
            # Limit column width
            for i in range(self.table.columnCount()):
                if self.table.columnWidth(i) > 200:
                    self.table.setColumnWidth(i, 200)
            
            self.info_label.setText(f"Loaded {len(df)} rows — {os.path.basename(self.filepath)}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load file:\n{e}")
            self.info_label.setText(f"Error: {e}")