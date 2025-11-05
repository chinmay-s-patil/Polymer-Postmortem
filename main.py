# main.py
import tkinter as tk
from gui_core import TensileGUI

if __name__ == "__main__":
    root = tk.Tk()
    app = TensileGUI(root)
    root.mainloop()
