import json
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# scripts.json is saved in the same folder as this file
DATA_FILE = Path(__file__).parent / "scripts.json"


class ScriptEntry:
    """One script in the list."""

    def __init__(self, name, path, description=""):
        self.name = name
        self.path = Path(path)
        self.description = description
        self.process = None  # holds the running process, or None when stopped

    def is_running(self):
        # poll() returns None while the script is still running.
        # When it ends, poll() returns its exit code (0 = finished normally, 1 = crashed)
        return self.process is not None and self.process.poll() is None

    def to_dict(self):
        # Path objects can't go into JSON, so we turn the path into plain text
        return {
            "name": self.name,
            "path": str(self.path),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(d["name"], d["path"], d.get("description", ""))


class ScriptManager:
    """All the logic. Nothing in here touches tkinter."""

    def __init__(self, data_file):
        self.data_file = data_file
        self.entries = []
        self.load()

    def load(self):
        if not self.data_file.exists():
            return
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                self.entries = [ScriptEntry.from_dict(d) for d in json.load(f)]
        except (json.JSONDecodeError, KeyError):
            self.entries = []  # broken file -> start with an empty list

    def save(self):
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump([e.to_dict() for e in self.entries], f, indent=2)

    def add_script(self, path):
        path = Path(path)
        if any(e.path == path for e in self.entries):
            return False  # already in the list
        self.entries.append(ScriptEntry(path.stem, path))
        self.save()
        return True

    def remove_script(self, entry):
        self.stop(entry)  # don't leave a removed script running with no way to stop it
        self.entries.remove(entry)
        self.save()

    def start(self, entry):
        """Returns True if the script is running afterwards, False if the file is missing."""
        if entry.is_running():
            return True  # already running -> don't launch a second copy
        if not entry.path.exists():
            return False
        # sys.executable = the Python that is running this manager.
        # cwd = the script's own folder, so if autoclicker.py opens "settings.txt",
        # it finds the settings.txt sitting next to it.
        entry.process = subprocess.Popen(
            [sys.executable, str(entry.path)],
            cwd=entry.path.parent,
        )
        return True

    def stop(self, entry):
        if entry.is_running():
            entry.process.terminate()
            try:
                entry.process.wait(timeout=2)  # give it 2 seconds to actually exit
            except subprocess.TimeoutExpired:
                # On Linux a script can ignore terminate(); kill() can't be ignored
                entry.process.kill()
        entry.process = None

    def stop_all(self):
        for entry in self.entries:
            self.stop(entry)


class App:
    """The window only. It asks ScriptManager to do the real work."""

    def __init__(self, root):
        self.root = root
        self.manager = ScriptManager(DATA_FILE)

        root.title("Script Manager")
        root.geometry("750x380")

        # --- table ---
        self.tree = ttk.Treeview(
            root, columns=("name", "status", "path"), show="headings"
        )
        self.tree.heading("name", text="Script")
        self.tree.heading("status", text="Status")
        self.tree.heading("path", text="Path")
        self.tree.column("name", width=150)
        self.tree.column("status", width=80, anchor="center")
        self.tree.column("path", width=500)
        self.tree.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        # --- buttons ---
        bar = tk.Frame(root)
        bar.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(bar, text="Add Script", command=self.on_add).pack(side="left")
        tk.Button(bar, text="Remove Selected", command=self.on_remove).pack(
            side="left", padx=5
        )
        tk.Button(bar, text="Stop All", command=self.on_stop_all).pack(side="right")
        tk.Button(bar, text="Stop", command=self.on_stop).pack(side="right", padx=5)
        tk.Button(bar, text="Start", command=self.on_start).pack(side="right")

        # Clicking the window's X button sends an event named WM_DELETE_WINDOW.
        # We catch it so we can stop every script before the window closes.
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.refresh_table()

    def refresh_table(self):
        selected = self.tree.selection()  # remember it, e.g. ("2",)
        self.tree.delete(*self.tree.get_children())  # clear all rows
        for i, entry in enumerate(self.manager.entries):
            status = "Running" if entry.is_running() else "Stopped"
            # iid = the row's ID. Using the list index lets us find the entry again later
            self.tree.insert(
                "", "end", iid=str(i), values=(entry.name, status, str(entry.path))
            )
        # Rebuilding the table clears the highlight, so put it back.
        # Otherwise after clicking Start you'd have to click the row again to Stop it.
        for iid in selected:
            if self.tree.exists(iid):
                self.tree.selection_set(iid)

    def get_selected(self):
        selected = self.tree.selection()  # e.g. ("2",)
        if not selected:
            return None
        return self.manager.entries[int(selected[0])]

    def on_add(self):
        path = filedialog.askopenfilename(
            title="Choose a script",
            filetypes=[("Python scripts", "*.py *.pyw"), ("All files", "*.*")],
        )
        if not path:  # user pressed Cancel -> path is ""
            return
        if not self.manager.add_script(path):
            messagebox.showinfo("Already added", "That script is already in the list.")
        self.refresh_table()

    def on_remove(self):
        entry = self.get_selected()
        if entry is None:
            return
        self.manager.remove_script(entry)
        # After a removal the row numbers shift (row "3" becomes "2"),
        # so clear the highlight instead of highlighting the wrong script.
        self.tree.selection_set(())
        self.refresh_table()

    def on_start(self):
        entry = self.get_selected()
        if entry is None:
            return
        if not self.manager.start(entry):
            messagebox.showerror("Can't start", f"File not found:\n{entry.path}")
        self.refresh_table()

    def on_stop(self):
        entry = self.get_selected()
        if entry is None:
            return
        self.manager.stop(entry)
        self.refresh_table()

    def on_stop_all(self):
        self.manager.stop_all()
        self.refresh_table()

    def on_close(self):
        self.manager.stop_all()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
