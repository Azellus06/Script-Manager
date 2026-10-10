import json
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
        self.process = None  # step 2 will store the running process here

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
        self.entries.remove(entry)
        self.save()


class App:
    """The window only. It asks ScriptManager to do the real work."""

    def __init__(self, root):
        self.root = root
        self.manager = ScriptManager(DATA_FILE)

        root.title("Script Manager")
        root.geometry("650x350")

        # --- table ---
        self.tree = ttk.Treeview(root, columns=("name", "path"), show="headings")
        self.tree.heading("name", text="Script")
        self.tree.heading("path", text="Path")
        self.tree.column("name", width=150)
        self.tree.column("path", width=470)
        self.tree.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        # --- buttons ---
        bar = tk.Frame(root)
        bar.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(bar, text="Add Script", command=self.on_add).pack(side="left")
        tk.Button(bar, text="Remove Selected", command=self.on_remove).pack(
            side="left", padx=5
        )

        self.refresh_table()

    def refresh_table(self):
        self.tree.delete(*self.tree.get_children())  # clear all rows
        for i, entry in enumerate(self.manager.entries):
            # iid = the row's ID. Using the list index lets us find the entry again later
            self.tree.insert("", "end", iid=str(i), values=(entry.name, str(entry.path)))

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
        selected = self.tree.selection()  # e.g. ("2",)
        if not selected:
            return
        entry = self.manager.entries[int(selected[0])]
        self.manager.remove_script(entry)
        self.refresh_table()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
