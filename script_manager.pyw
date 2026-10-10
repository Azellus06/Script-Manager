import json
import subprocess
import sys
import tkinter as tk
import traceback
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# scripts.json and the logs folder are saved in the same folder as this file
BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "scripts.json"
LOG_DIR = BASE_DIR / "logs"
MAX_LOG_LINES = 2000  # the output box only keeps the newest 2000 lines

# ---------- look & feel (change a color here and the whole window follows) ----------
BG = "#15171c"  # window background
PANEL = "#1d2027"  # table background
PANEL_ALT = "#22262e"  # every second table row (stripes)
BORDER = "#2e333d"
TEXT = "#e7e9ee"
MUTED = "#8c94a6"
ACCENT = "#4c8dff"  # Start button
ACCENT_HOVER = "#6aa1ff"
DANGER = "#d64550"  # Stop All button
DANGER_HOVER = "#e5636d"
BTN = "#2a2f39"  # normal buttons
BTN_HOVER = "#363c49"
GREEN = "#3ecf8e"  # running
RED = "#ff6b78"  # crashed / error lines
SELECT = "#2a3a5c"  # highlighted table row
LOG_BG = "#0f1115"  # output box
LOG_TEXT = "#d5d9e2"

FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
TITLE_FONT = ("Segoe UI", 18, "bold")
MONO = ("Consolas", 10)

STATUS_ICONS = {"running": "●", "stopped": "○", "finished": "✓", "crashed": "✕"}


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

    def status_kind(self):
        """One word for the state: running / stopped / finished / crashed."""
        if self.process is None:
            return "stopped"  # never started, or you stopped it yourself
        code = self.process.poll()
        if code is None:
            return "running"
        return "finished" if code == 0 else "crashed"

    def status_text(self):
        kind = self.status_kind()
        if kind == "crashed":
            return f"Crashed ({self.process.poll()})"  # e.g. a missing library gives code 1
        return kind.capitalize()

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
        self.in_traceback = False  # are we in the middle of printing an error report?

        # On a high-resolution screen, 1 "pixel" in our code would look tiny.
        # scale = 1.0 on a normal screen, 1.5 on a 150% screen, and so on.
        self.scale = max(1.0, root.winfo_fpixels("1i") / 96)

        root.title("Script Manager")
        root.configure(bg=BG)
        root.geometry(f"{self.px(780)}x{self.px(620)}")
        root.minsize(self.px(640), self.px(480))

        self.setup_style()
        self.build_window()

        # Clicking the window's X button sends an event named WM_DELETE_WINDOW.
        # We catch it so we can stop every script before the window closes.
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.refresh_table()
        self.clear_log_view()
        self.tick()  # starts the once-per-second loop

    def px(self, n):
        return int(n * self.scale)

    # ---------- look ----------

    def setup_style(self):
        style = ttk.Style(self.root)
        # "clam" is the one built-in theme that obeys color settings.
        # Windows' default theme ("vista") ignores most of them.
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=TEXT, font=FONT)

        # labels
        style.configure("Title.TLabel", font=TITLE_FONT)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Section.TLabel", foreground=MUTED, font=FONT_BOLD)

        # buttons: same recipe three times, only the colors change
        pad = (self.px(16), self.px(8))
        self.button_style(style, "TButton", BTN, BTN_HOVER, TEXT, FONT, pad)
        self.button_style(style, "Accent.TButton", ACCENT, ACCENT_HOVER, "#ffffff", FONT_BOLD, pad)
        self.button_style(style, "Danger.TButton", DANGER, DANGER_HOVER, "#ffffff", FONT_BOLD, pad)

        # table
        style.configure(
            "Treeview",
            background=PANEL,
            fieldbackground=PANEL,
            foreground=TEXT,
            borderwidth=0,
            rowheight=self.px(36),
            font=FONT,
        )
        style.map(
            "Treeview",
            background=[("selected", SELECT)],
            foreground=[("selected", TEXT)],
        )
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])  # no outer border
        style.configure(
            "Treeview.Heading",
            background=BG,
            foreground=MUTED,
            borderwidth=0,
            relief="flat",
            font=FONT_BOLD,
            padding=(self.px(10), self.px(8)),
        )
        style.map("Treeview.Heading", background=[("active", BG)])

        # scrollbars (one for the table, one for the darker output box)
        for name, trough in (("Vertical.TScrollbar", PANEL), ("Log.Vertical.TScrollbar", LOG_BG)):
            style.configure(
                name,
                background=BTN,
                troughcolor=trough,
                bordercolor=trough,
                lightcolor=BTN,
                darkcolor=BTN,
                arrowcolor=MUTED,
                relief="flat",
                gripcount=0,
                arrowsize=self.px(14),
            )
            style.map(name, background=[("active", BTN_HOVER)])

    @staticmethod
    def button_style(style, name, bg, hover, fg, font, padding):
        # lightcolor/darkcolor/bordercolor are the 3D edges of a clam button.
        # Setting them to the background color makes the button look flat.
        style.configure(
            name,
            background=bg,
            foreground=fg,
            bordercolor=bg,
            lightcolor=bg,
            darkcolor=bg,
            focuscolor=bg,
            borderwidth=1,
            padding=padding,
            font=font,
        )
        style.map(
            name,
            background=[("active", hover)],
            bordercolor=[("active", hover)],
            lightcolor=[("active", hover)],
            darkcolor=[("active", hover)],
        )

    def build_window(self):
        root = self.root
        pad = self.px(18)
        gap = self.px(8)

        # --- header ---
        header = ttk.Frame(root)
        header.pack(fill="x", padx=pad, pady=(pad, self.px(12)))
        ttk.Label(header, text="Script Manager", style="Title.TLabel").pack(side="left")
        self.summary_label = ttk.Label(header, text="", style="Muted.TLabel")
        self.summary_label.pack(side="right", anchor="s", pady=(0, 3))

        # --- table (a 1-pixel BORDER-colored frame around a PANEL-colored one = thin outline) ---
        table_border = tk.Frame(root, bg=BORDER)
        table_border.pack(fill="both", expand=True, padx=pad)
        table_inner = tk.Frame(table_border, bg=PANEL)
        table_inner.pack(fill="both", expand=True, padx=1, pady=1)

        self.tree = ttk.Treeview(
            table_inner,
            columns=("name", "status", "path"),
            show="headings",
            height=6,
            selectmode="browse",  # one row at a time
        )
        for col, title, width, stretch in (
            ("name", "Script", 170, False),
            ("status", "Status", 160, False),
            ("path", "Path", 420, True),
        ):
            self.tree.heading(col, text=title, anchor="w")
            self.tree.column(col, width=self.px(width), anchor="w", stretch=stretch)
        tree_scroll = ttk.Scrollbar(table_inner, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        # Row colors. A row gets two tags: a stripe tag (background) and a status tag (text color).
        self.tree.tag_configure("even", background=PANEL)
        self.tree.tag_configure("odd", background=PANEL_ALT)
        self.tree.tag_configure("running", foreground=GREEN)
        self.tree.tag_configure("crashed", foreground=RED)
        # Fires whenever you click a different row
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        # Shown on top of the empty table
        self.empty_label = tk.Label(
            self.tree,
            text='No scripts yet.\nClick "Add Script" to add your first one.',
            bg=PANEL,
            fg=MUTED,
            font=FONT,
            justify="center",
        )

        # --- buttons ---
        bar = ttk.Frame(root)
        bar.pack(fill="x", padx=pad, pady=(self.px(14), self.px(14)))
        ttk.Button(bar, text="Add Script", cursor="hand2", command=self.on_add).pack(side="left")
        ttk.Button(bar, text="Remove", cursor="hand2", command=self.on_remove).pack(
            side="left", padx=(gap, 0)
        )
        ttk.Button(
            bar, text="Stop All", style="Danger.TButton", cursor="hand2", command=self.on_stop_all
        ).pack(side="right")
        ttk.Button(bar, text="Stop", cursor="hand2", command=self.on_stop).pack(side="right", padx=gap)
        ttk.Button(
            bar, text="Start", style="Accent.TButton", cursor="hand2", command=self.on_start
        ).pack(side="right")

        # --- output box ---
        self.log_label = ttk.Label(root, text="Output", style="Section.TLabel")
        self.log_label.pack(anchor="w", padx=pad)
        log_border = tk.Frame(root, bg=BORDER)
        log_border.pack(fill="both", expand=True, padx=pad, pady=(self.px(8), pad))
        log_inner = tk.Frame(log_border, bg=LOG_BG)
        log_inner.pack(fill="both", expand=True, padx=1, pady=1)
        # state="disabled" makes it read-only (you can't type into it)
        self.log_text = tk.Text(
            log_inner,
            height=10,
            wrap="word",
            state="disabled",
            font=MONO,
            bg=LOG_BG,
            fg=LOG_TEXT,
            insertbackground=LOG_TEXT,
            selectbackground=SELECT,
            selectforeground=TEXT,
            borderwidth=0,
            highlightthickness=0,
            padx=self.px(12),
            pady=self.px(10),
        )
        log_scroll = ttk.Scrollbar(
            log_inner, orient="vertical", style="Log.Vertical.TScrollbar", command=self.log_text.yview
        )
        self.log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)
        # Tags are named "styles" for pieces of text
        self.log_text.tag_configure("error", foreground=RED)
        self.log_text.tag_configure("hint", foreground=MUTED)

    # ---------- table ----------

    def tick(self):
        """Runs once per second: refresh every status, then pull in new log text."""
        # Only change the Status cell and colors of each row. We don't rebuild the table,
        # so your selection and scroll position don't flicker every second.
        for i, entry in enumerate(self.manager.entries):
            iid = str(i)
            if self.tree.exists(iid):
                self.tree.set(iid, "status", self.status_label(entry))
                self.tree.item(iid, tags=self.row_tags(i, entry))
        self.update_summary()
        self.update_log()
        # "Run this function again 1000 ms (1 second) from now".
        # It reschedules itself every time, so it repeats forever without freezing the window.
        self.root.after(1000, self.tick)

    @staticmethod
    def status_label(entry):
        # e.g. "● Running", "✕ Crashed (1)"  (the icon helps even if you can't tell the colors apart)
        return f"{STATUS_ICONS[entry.status_kind()]} {entry.status_text()}"

    @staticmethod
    def row_tags(i, entry):
        # e.g. row 3 that is running -> ("odd", "running")
        return ("odd" if i % 2 else "even", entry.status_kind())

    def update_summary(self):
        total = len(self.manager.entries)
        running = sum(1 for e in self.manager.entries if e.is_running())
        word = "script" if total == 1 else "scripts"
        self.summary_label.config(text=f"{total} {word}  ·  {running} running")

    def refresh_table(self):
        selected = self.tree.selection()  # remember it, e.g. ("2",)
        self.tree.delete(*self.tree.get_children())  # clear all rows
        for i, entry in enumerate(self.manager.entries):
            # iid = the row's ID. Using the list index lets us find the entry again later
            self.tree.insert(
                "",
                "end",
                iid=str(i),
                values=(entry.name, self.status_label(entry), str(entry.path)),
                tags=self.row_tags(i, entry),
            )
        # Rebuilding the table clears the highlight, so put it back.
        # Otherwise after clicking Start you'd have to click the row again to Stop it.
        for iid in selected:
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
        # Show the "No scripts yet" hint only when the table is empty
        if self.manager.entries:
            self.empty_label.place_forget()
        else:
            self.empty_label.place(relx=0.5, rely=0.55, anchor="center")
        self.update_summary()

    def get_selected(self):
        selected = self.tree.selection()  # e.g. ("2",)
        if not selected:
            return None
        return self.manager.entries[int(selected[0])]

    # ---------- output box ----------

    def set_log_text(self, text, tag=None):
        self.log_text.configure(state="normal")  # unlock, change, lock again
        self.log_text.delete("1.0", "end")
        if text:
            self.log_text.insert("end", text, (tag,) if tag else ())
        self.log_text.configure(state="disabled")

    def log_tag_for(self, line):
        """Decides if a line of output is part of an error report (shown in red)."""
        if line.startswith("Traceback"):
            self.in_traceback = True
            return "error"
        if self.in_traceback:
            # Inside a traceback, the "File ..." and code lines are indented.
            # The first line that isn't indented is the last one, e.g. "ModuleNotFoundError: ..."
            if not line.startswith((" ", "\t")):
                self.in_traceback = False
            return "error"
        return "error" if ("Error" in line or "Exception" in line) else None

    def append_log(self, text):
        # Is the view scrolled all the way down? yview() looks like (0.4, 1.0)
        # where the second number is how far down the visible part reaches.
        at_bottom = self.log_text.yview()[1] >= 0.999
        self.log_text.configure(state="normal")
        for line in text.splitlines(keepends=True):
            tag = self.log_tag_for(line)
            self.log_text.insert("end", line, (tag,) if tag else ())
        # Keep only the newest MAX_LOG_LINES lines ("end-2000l" = 2000 lines before the end)
        self.log_text.delete("1.0", f"end-{MAX_LOG_LINES}l")
        self.log_text.configure(state="disabled")
        if at_bottom:  # follow new output, but don't yank you down if you scrolled up to read
            self.log_text.see("end")

    def clear_log_view(self):
        self.viewed_entry = None
        self.log_pos = 0
        self.in_traceback = False
        self.log_label.config(text="Output")
        self.set_log_text(self.EMPTY_LOG_HINT, "hint")

    def show_log_for(self, entry):
        self.viewed_entry = entry
        self.log_pos = 0
        self.in_traceback = False
        self.log_label.config(text=f"Output  ·  {entry.name}")
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
    try:
        try:
            # Without this, Windows stretches the whole window on high-resolution
            # screens and the text looks blurry.
            from ctypes import windll

            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass  # not Windows (or an old Windows): just skip it
        root = tk.Tk()
        App(root)
        root.mainloop()
    except Exception:
        # A .pyw has no console, so an error would just make the window never appear.
        # Save it to logs/_manager_crash.log so you can read what went wrong.
        LOG_DIR.mkdir(exist_ok=True)
        (LOG_DIR / "_manager_crash.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise
