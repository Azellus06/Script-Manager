import json
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# scripts.json and the logs folder are saved in the same folder as this file
BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "scripts.json"
LOG_DIR = BASE_DIR / "logs"
MAX_LOG_LINES = 2000  # the output box only keeps the newest 2000 lines


class ScriptEntry:
    """One script in the list."""

    def __init__(self, name, path, description=""):
        self.name = name
        self.path = Path(path)
        self.description = description
        self.process = None  # holds the running process, or None when stopped

    @property
    def log_path(self):
        # e.g. autoclicker.py -> logs/autoclicker.log
        return LOG_DIR / f"{self.name}.log"

    def is_running(self):
        # poll() returns None while the script is still running.
        # When it ends, poll() returns its exit code (0 = finished normally, 1 = crashed)
        return self.process is not None and self.process.poll() is None

    def status_text(self):
        if self.process is None:
            return "Stopped"  # never started, or you stopped it yourself
        code = self.process.poll()
        if code is None:
            return "Running"
        if code == 0:
            return "Finished"  # ended on its own, no errors
        return f"Crashed ({code})"  # e.g. a missing library gives code 1

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
        LOG_DIR.mkdir(exist_ok=True)
        # Opening with "w" empties the old log, so each Start gives a fresh log.
        # The script gets its own copy of this file handle, so we can close ours
        # right after Popen (that's what the "with" block does).
        with open(entry.log_path, "w", encoding="utf-8") as log:
            entry.process = subprocess.Popen(
                # -u        : don't hold print() output in memory; write it right away
                # -X utf8   : so printing a character like "✓" doesn't crash the script
                [sys.executable, "-u", "-X", "utf8", str(entry.path)],
                cwd=entry.path.parent,  # script runs "from its own folder"
                stdout=log,  # print() goes into the log file
                stderr=subprocess.STDOUT,  # error tracebacks go to the same file
                # This app runs without a console, and Windows raises
                # "OSError: [WinError 6] The handle is invalid" if we redirect
                # output but leave stdin alone.
                stdin=subprocess.DEVNULL,
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

    def read_log(self, entry, pos):
        """Returns (new_text, new_pos).

        pos = how many bytes we've already shown. Example: the log was 120 bytes
        last time and is 150 now, so we read only bytes 120..150 (the new 30).
        """
        if not entry.log_path.exists():
            return "", 0
        with open(entry.log_path, "rb") as f:
            f.seek(0, 2)  # jump to the end to learn the file size
            if f.tell() < pos:
                pos = 0  # file is smaller than before -> it was restarted, read from top
            f.seek(pos)
            data = f.read()
        # errors="replace": never crash on a half-written character
        return data.decode("utf-8", errors="replace"), pos + len(data)


class App:
    """The window only. It asks ScriptManager to do the real work."""

    EMPTY_LOG_HINT = "Select a script to see its output."

    def __init__(self, root):
        self.root = root
        self.manager = ScriptManager(DATA_FILE)
        self.viewed_entry = None  # whose log is in the output box right now
        self.log_pos = 0  # how many bytes of that log we've already shown

        root.title("Script Manager")
        root.geometry("750x560")

        # --- table ---
        self.tree = ttk.Treeview(
            root, columns=("name", "status", "path"), show="headings", height=8
        )
        self.tree.heading("name", text="Script")
        self.tree.heading("status", text="Status")
        self.tree.heading("path", text="Path")
        self.tree.column("name", width=150)
        self.tree.column("status", width=80, anchor="center")
        self.tree.column("path", width=500)
        self.tree.pack(fill="both", expand=True, padx=10, pady=(10, 5))
        # Fires whenever you click a different row
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        # --- buttons ---
        bar = tk.Frame(root)
        bar.pack(fill="x", padx=10, pady=(0, 5))
        tk.Button(bar, text="Add Script", command=self.on_add).pack(side="left")
        tk.Button(bar, text="Remove Selected", command=self.on_remove).pack(
            side="left", padx=5
        )
        tk.Button(bar, text="Stop All", command=self.on_stop_all).pack(side="right")
        tk.Button(bar, text="Stop", command=self.on_stop).pack(side="right", padx=5)
        tk.Button(bar, text="Start", command=self.on_start).pack(side="right")

        # --- output box ---
        self.log_label = ttk.Label(root, text="Output")
        self.log_label.pack(anchor="w", padx=10)
        log_frame = tk.Frame(root)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        # state="disabled" makes it read-only (you can't type into it)
        self.log_text = tk.Text(
            log_frame, height=10, wrap="word", state="disabled", font=("Consolas", 10)
        )
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)

        # Clicking the window's X button sends an event named WM_DELETE_WINDOW.
        # We catch it so we can stop every script before the window closes.
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.refresh_table()
        self.clear_log_view()
        self.tick()  # starts the once-per-second loop

    def tick(self):
        """Runs once per second: refresh every status, then pull in new log text."""
        # Only change the Status cell of each row. We don't rebuild the table,
        # so your selection and scroll position don't flicker every second.
        for i, entry in enumerate(self.manager.entries):
            iid = str(i)
            if self.tree.exists(iid):
                self.tree.set(iid, "status", entry.status_text())
        self.update_log()
        # "Run this function again 1000 ms (1 second) from now".
        # It reschedules itself every time, so it repeats forever without freezing the window.
        self.root.after(1000, self.tick)

    def refresh_table(self):
        selected = self.tree.selection()  # remember it, e.g. ("2",)
        self.tree.delete(*self.tree.get_children())  # clear all rows
        for i, entry in enumerate(self.manager.entries):
            # iid = the row's ID. Using the list index lets us find the entry again later
            self.tree.insert(
                "",
                "end",
                iid=str(i),
                values=(entry.name, entry.status_text(), str(entry.path)),
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

    # ---------- output box ----------

    def set_log_text(self, text):
        self.log_text.configure(state="normal")  # unlock, change, lock again
        self.log_text.delete("1.0", "end")
        self.log_text.insert("end", text)
        self.log_text.configure(state="disabled")

    def append_log(self, text):
        # Is the view scrolled all the way down? yview() looks like (0.4, 1.0)
        # where the second number is how far down the visible part reaches.
        at_bottom = self.log_text.yview()[1] >= 0.999
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        # Keep only the newest MAX_LOG_LINES lines ("end-2000l" = 2000 lines before the end)
        self.log_text.delete("1.0", f"end-{MAX_LOG_LINES}l")
        self.log_text.configure(state="disabled")
        if at_bottom:  # follow new output, but don't yank you down if you scrolled up to read
            self.log_text.see("end")

    def clear_log_view(self):
        self.viewed_entry = None
        self.log_pos = 0
        self.log_label.config(text="Output")
        self.set_log_text(self.EMPTY_LOG_HINT)

    def show_log_for(self, entry):
        self.viewed_entry = entry
        self.log_pos = 0
        self.log_label.config(text=f"Output: {entry.name}")
        self.set_log_text("")
        self.update_log()

    def update_log(self):
        if self.viewed_entry is None:
            return
        text, self.log_pos = self.manager.read_log(self.viewed_entry, self.log_pos)
        if text:
            self.append_log(text)

    def on_select(self, event=None):
        entry = self.get_selected()
        # Rebuilding the table briefly empties the selection; ignore that so
        # the output box doesn't blank out every time you click a button.
        if entry is None or entry is self.viewed_entry:
            return
        self.show_log_for(entry)

    # ---------- buttons ----------

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
        if entry is self.viewed_entry:
            self.clear_log_view()
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
        elif entry is self.viewed_entry:
            self.show_log_for(entry)  # Start wiped the old log, so reload the box from the top
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
