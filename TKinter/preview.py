import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd
import math

def preview_file(file):
    """
    Open a Toplevel window and preview the entire CSV or XLSX file.
    - Streams CSVs chunk-by-chunk to avoid loading whole file at once.
    - Inserts rows in UI-friendly batches so UI remains responsive.
    Usage: command=lambda: preview_file(filename)
    """
    import os
    import tkinter as tk
    from tkinter import ttk, messagebox
    import pandas as pd

    # === Ensure there's a Tk root to attach to ===
    if not tk._default_root:
        root = tk.Tk()
        root.withdraw()
    parent = tk._default_root

    basename = os.path.basename(file)
    win = tk.Toplevel(parent)
    win.title(f"Preview — {basename}")
    win.geometry("1000x600")
    win.minsize(600, 320)

    # Top: info + progress
    top = ttk.Frame(win, padding=(8,6))
    top.pack(fill="x")
    info_var = tk.StringVar(value=f"Loading {basename} ...")
    info_lbl = ttk.Label(top, textvariable=info_var, font=("Segoe UI", 9))
    info_lbl.pack(side="left")

    # Middle: Treeview container with scrollbars
    container = ttk.Frame(win)
    container.pack(fill="both", expand=True, padx=8, pady=6)

    vscroll = ttk.Scrollbar(container, orient="vertical")
    hscroll = ttk.Scrollbar(container, orient="horizontal")
    tv = ttk.Treeview(container, show="headings", yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
    vscroll.config(command=tv.yview)
    hscroll.config(command=tv.xview)
    vscroll.pack(side="right", fill="y")
    hscroll.pack(side="bottom", fill="x")
    tv.pack(fill="both", expand=True, side="left")

    # Bottom: controls
    bottom = ttk.Frame(win, padding=(8,6))
    bottom.pack(fill="x")
    close_btn = ttk.Button(bottom, text="Close", command=win.destroy)
    close_btn.pack(side="right")

    # Progressbar (determinate only when we know total rows)
    prog = ttk.Progressbar(bottom, mode="indeterminate")
    prog.pack(side="left", padx=(4,10))
    prog.start(80)

    # Zebra striping
    tv.tag_configure("oddrow", background="#fafafa")
    tv.tag_configure("evenrow", background="#ffffff")

    # Batch insertion helpers
    insert_batch_after_id = None

    def insert_rows_in_batches(rows_iterable, columns, batch_size=500):
        """
        rows_iterable: iterator yielding tuples (rowvalues)
        columns: list of column names
        Inserts rows in batches using .after to keep UI responsive.
        """
        # Setup tree columns (done once)
        tv["columns"] = columns
        for c in columns:
            tv.heading(c, text=c, anchor="w")
            tv.column(c, width=120, anchor="w", stretch=False)

        # Allow small column stretch if few columns
        if len(columns) <= 6:
            for c in columns:
                tv.column(c, stretch=True)

        # internal state
        buffer = []
        count = 0

        def flush_buffer():
            nonlocal buffer, count
            if not buffer:
                return
            for i, r in enumerate(buffer):
                tag = "evenrow" if ((count + i) % 2 == 0) else "oddrow"
                try:
                    tv.insert("", "end", values=r, tags=(tag,))
                except Exception:
                    # fallback: insert truncated row to keep going
                    vals = tuple(str(x) for x in r)
                    tv.insert("", "end", values=vals, tags=(tag,))
            count += len(buffer)
            buffer = []
            # update info
            info_var.set(f"Loaded {count} rows — {basename}")
            # keep the last inserted visible
            tv.yview_moveto(1.0)

        # generator driving insertion with after scheduling
        def drive():
            nonlocal buffer
            try:
                for _ in range(batch_size):
                    row = next(rows_iterable)
                    buffer.append(row)
            except StopIteration:
                # flush remaining and finish
                flush_buffer()
                prog.stop()
                prog.pack_forget()
                info_var.set(f"Loaded {count} rows — {basename}")
                return
            # flush this batch and schedule next
            flush_buffer()
            win.after(1, drive)

        # start driver
        win.after(1, drive)

    # === File reading & streaming logic ===
    try:
        ext = os.path.splitext(file)[1].lower()
        if ext in (".xls", ".xlsx"):
            # Excel: pandas cannot easily stream — read full sheet into DataFrame
            df = pd.read_excel(file, dtype=str)
            df = df.fillna("")
            cols = list(df.columns.astype(str))
            # make iterator of tuples
            def row_iter():
                for r in df.itertuples(index=False, name=None):
                    yield tuple("" if (x is None) else x for x in r)
            insert_rows_in_batches(row_iter(), cols, batch_size=500)
            info_var.set(f"Loading {len(df)} rows — {basename}")
        else:
            # CSV: stream via chunks to avoid loading everything
            # first read a small chunk to get columns
            chunk_size = 2000
            csv_reader = pd.read_csv(file, dtype=str, chunksize=chunk_size, iterator=True, low_memory=False)
            first_chunk = next(csv_reader)
            first_chunk = first_chunk.fillna("")
            cols = list(first_chunk.columns.astype(str))

            # Build a combined iterator that yields rows from first_chunk then subsequent chunks
            def combined_row_iter():
                for r in first_chunk.itertuples(index=False, name=None):
                    yield tuple("" if (x is None) else x for x in r)
                for chunk in csv_reader:
                    chunk = chunk.fillna("")
                    for r in chunk.itertuples(index=False, name=None):
                        yield tuple("" if (x is None) else x for x in r)

            # Try to estimate total rows quickly (optional): count newline characters
            total_rows = None
            try:
                # cheap line count: may be faster for plain csvs
                with open(file, "rb") as fh:
                    # count newlines in blocks
                    total = 0
                    for block in iter(lambda: fh.read(1024*1024), b""):
                        total += block.count(b"\n")
                if total > 0:
                    total_rows = total  # rough estimate (includes header)
                    info_var.set(f"Loading — approx {total_rows - 1} rows — {basename}")
            except Exception:
                # ignore counting errors
                pass

            insert_rows_in_batches(combined_row_iter(), cols, batch_size=500)

    except Exception as e:
        prog.stop()
        prog.pack_forget()
        messagebox.showerror("Failed to open file", f"Could not open '{basename}':\n{e}", parent=win)
        win.destroy()
        return

    # Done — window remains open for user to browse/copy/close



# -----------------------
# Example usage (remove or adapt in your app):
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Demo")
    btn = tk.Button(root, command=preview_file(r"D:\For People\For Ashwath\AK_Tensile Python Processing\SLM_070625_SR.is_tens_Exports\output\Cleaned Files\SLM_070625_SR_2_2.csv"))
    btn.pack(padx=20, pady=20)
    root.mainloop()
