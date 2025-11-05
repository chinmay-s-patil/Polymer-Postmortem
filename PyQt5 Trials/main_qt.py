"""
main_qt.py - PyQt5 Modern Material Design Polymer PostMortem
Main entry point for the application
"""

import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from gui.main_window import MainWindow

VERSION = "2.0.0"

def main():
    """Initialize and run the PyQt5 application"""
    # Enable high DPI scaling
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    
    # Set application-wide style
    app.setStyle('Fusion')
    
    # Modern dark theme palette
    from PyQt5.QtGui import QPalette, QColor
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ToolTipBase, Qt.white)
    palette.setColor(QPalette.ToolTipText, Qt.white)
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(palette)
    
    # Custom stylesheet for modern look
    app.setStyleSheet("""
        QMainWindow {
            background-color: #353535;
        }
        QPushButton {
            background-color: #2a82da;
            border: none;
            color: white;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
            min-height: 28px;
        }
        QPushButton:hover {
            background-color: #3b92ea;
        }
        QPushButton:pressed {
            background-color: #1a72ca;
        }
        QPushButton:disabled {
            background-color: #555555;
            color: #888888;
        }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
            background-color: #2b2b2b;
            border: 1px solid #555555;
            border-radius: 3px;
            padding: 6px;
            color: white;
            min-height: 24px;
        }
        QLineEdit:focus, QComboBox:focus {
            border: 1px solid #2a82da;
        }
        QTreeWidget, QListWidget, QTableWidget {
            background-color: #2b2b2b;
            border: 1px solid #555555;
            border-radius: 3px;
            alternate-background-color: #323232;
            color: white;
        }
        QTreeWidget::item:selected, QListWidget::item:selected {
            background-color: #2a82da;
            color: white;
        }
        QTreeWidget::item:hover, QListWidget::item:hover {
            background-color: #3a3a3a;
        }
        QHeaderView::section {
            background-color: #2b2b2b;
            color: white;
            padding: 4px;
            border: 1px solid #555555;
        }
        QGroupBox {
            border: 1px solid #555555;
            border-radius: 5px;
            margin-top: 10px;
            font-weight: bold;
            color: #2a82da;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
        }
        QRadioButton {
            color: white;
        }
        QRadioButton::indicator {
            width: 13px;
            height: 13px;
        }
        QProgressBar {
            border: 1px solid #555555;
            border-radius: 3px;
            text-align: center;
            color: white;
        }
        QProgressBar::chunk {
            background-color: #2a82da;
            border-radius: 2px;
        }
        QStatusBar {
            background-color: #2b2b2b;
            color: white;
        }
        QMenuBar {
            background-color: #2b2b2b;
            color: white;
        }
        QMenuBar::item:selected {
            background-color: #2a82da;
        }
        QMenu {
            background-color: #2b2b2b;
            color: white;
            border: 1px solid #555555;
        }
        QMenu::item:selected {
            background-color: #2a82da;
        }
        QLabel {
            color: white;
        }
    """)
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()