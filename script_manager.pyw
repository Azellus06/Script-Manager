import hashlib
import json
import math
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import traceback
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# The emergency-stop hotkey needs the "keyboard" library (pip install keyboard).
# It's optional: without it, everything else still works.
try:
    import keyboard
except Exception:
    keyboard = None

# scripts.json and the logs folder are saved in the same folder as this file
BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "scripts.json"
LOG_DIR = BASE_DIR / "logs"
MAX_LOG_LINES = 2000  # the output box only keeps the newest 2000 lines
EMERGENCY_HOTKEY = "ctrl+alt+x"  # press this anywhere to stop every script

# ---------- look & feel (change a color here and the whole window follows) ----------
BG = "#15171c"  # window background
PANEL = "#1d2027"  # table background
PANEL_ALT = "#22262e"  # every second table row (stripes)
BORDER = "#2e333d"
TEXT = "#e7e9ee"
MUTED = "#8c94a6"
ACCENT = "#4c8dff"  # Restart button, ticked checkbox
ACCENT_HOVER = "#6aa1ff"  # when the mouse is over it
ACCENT_PRESS = "#3a78e6"  # while the mouse button is held down
# Action buttons: medium-dark tinted fills with softly colored text, so they stay calm on the dark background
GO = "#275c45"  # Start
GO_HOVER = "#2f6e54"
GO_PRESS = "#1f4a39"
GO_TEXT = "#8ee3b9"
INFO = "#2a4473"  # Restart
INFO_HOVER = "#335187"
INFO_PRESS = "#213960"
INFO_TEXT = "#a9c6f8"
WARN = "#754d23"  # Stop
WARN_HOVER = "#875c2c"
WARN_PRESS = "#5f3f1c"
WARN_TEXT = "#f2c58a"
DANGER = "#753038"  # Stop All
DANGER_HOVER = "#873c46"
DANGER_PRESS = "#5f262d"
DANGER_TEXT = "#f7a3ac"
BTN = "#2a2f39"  # normal buttons
BTN_HOVER = "#363c49"
BTN_PRESS = "#20242c"
OFF_TEXT = "#5d6474"  # text of a button that can't be clicked right now
BUTTON_RADIUS = 10  # how round the button corners are (0 = sharp, 18 = fully round ends)
GREEN = "#3ecf8e"  # running
RED = "#ff6b78"  # crashed / error lines
SELECT = "#2a3a5c"  # highlighted table row
LOG_BG = "#0f1115"  # output box
LOG_TEXT = "#d5d9e2"
SCROLL_THUMB = "#3a4150"  # scrollbar handle
SCROLL_HOVER = "#59637a"  # when the mouse is over it
SCROLL_DRAG = ACCENT  # while you are dragging it
CHECK_OFF_BORDER = "#586075"  # outline of an unticked checkbox
CHECK_OFF_FILL = "#0f1115"  # inside of an unticked checkbox

FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
TITLE_FONT = ("Segoe UI", 18, "bold")
MONO = ("Consolas", 10)

STATUS_ICONS = {"running": "●", "stopped": "○", "finished": "✓", "crashed": "✕"}


def open_in_system(path):
    """Open a file or folder the way double-clicking it would."""
    if sys.platform == "win32":
        os.startfile(path)  # Windows only
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def format_duration(seconds):
    """42 -> "42s", 312 -> "5m 12s", 3900 -> "1h 05m"."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)  # 312 -> 5 minutes and 12 seconds left over
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)  # 65 minutes -> 1 hour and 5 minutes left over
    return f"{hours}h {minutes:02d}m"


def plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def hex_to_rgb(color):
    return tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))


def draw_checkbox(master, size, checked, bg, width=None):
    """Draws a checkbox as a small image and returns it.

    A table cell can't hold a real checkbox widget, but it can hold a picture,
    so we paint one pixel by pixel. `bg` is the color of the row behind it.
    `width` = make the picture as wide as the table column, with the box in the
    middle, so the checkbox ends up centered under its heading.
    """
    SS = 4  # each final pixel = 4x4 sub-samples, averaged, so the edges look smooth
    bg_rgb = hex_to_rgb(bg)
    outline_rgb = hex_to_rgb(ACCENT if checked else CHECK_OFF_BORDER)
    inside_rgb = hex_to_rgb(ACCENT if checked else CHECK_OFF_FILL)
    white = (255, 255, 255)

    half = size / 2
    reach = half - 1  # half the box's width (1px margin so the smooth edge isn't cut off)
    radius = size * 0.26  # how round the box corners are
    border = max(1.4, size * 0.09)  # outline thickness of an unticked box
    stroke = max(1.6, size * 0.13) / 2  # half the thickness of the tick mark
    # The tick is two line segments: short one down-right, long one up-right
    tick = [(0.27 * size, 0.53 * size), (0.43 * size, 0.69 * size), (0.74 * size, 0.34 * size)]

    def box_distance(x, y):
        # Negative inside the rounded square, positive outside it
        dx = abs(x - half) - (reach - radius)
        dy = abs(y - half) - (reach - radius)
        return math.hypot(max(dx, 0), max(dy, 0)) + min(max(dx, dy), 0) - radius

    def segment_distance(x, y, a, b):
        ax, ay = a
        bx, by = b
        t = ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / ((bx - ax) ** 2 + (by - ay) ** 2)
        t = max(0, min(1, t))
        return math.hypot(x - (ax + t * (bx - ax)), y - (ay + t * (by - ay)))

    def color_at(x, y):
        d = box_distance(x, y)
        if d > 0:
            return bg_rgb
        if checked:
            on_tick = min(segment_distance(x, y, tick[0], tick[1]), segment_distance(x, y, tick[1], tick[2]))
            return white if on_tick <= stroke else inside_rgb
        return outline_rgb if d > -border else inside_rgb

    full_width = width or size
    image = tk.PhotoImage(master=master, width=full_width, height=size)
    image.put(bg, to=(0, 0, full_width, size))  # fill everything with the row color first
    rows = []
    for py in range(size):
        row = []
        for px in range(size):
            total = [0, 0, 0]
            for sy in range(SS):
                for sx in range(SS):
                    r, g, b = color_at(px + (sx + 0.5) / SS, py + (sy + 0.5) / SS)
                    total[0] += r
                    total[1] += g
                    total[2] += b
            n = SS * SS
            row.append("#%02x%02x%02x" % (total[0] // n, total[1] // n, total[2] // n))
        rows.append("{" + " ".join(row) + "}")
    image.put(" ".join(rows), to=((full_width - size) // 2, 0))  # box goes in the middle
    return image


class ScriptEntry:
    """One script in the list."""

    def __init__(self, name, path, autostart=False):
        self.name = name
        self.path = Path(path)
        self.autostart = autostart  # start this script when the manager opens?
        self.process = None  # holds the running process, or None when stopped
        self.started_at = 0.0  # when it was last started (time.monotonic), for the running time
        # Usually the same as name. ScriptManager adds a code when two scripts share a name.
        self.log_name = name

    @property
    def log_path(self):
        # e.g. autoclicker.py -> logs/autoclicker.log
        return LOG_DIR / f"{self.log_name}.log"

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

    def running_time(self):
        """How long it has been running, in seconds."""
        return time.monotonic() - self.started_at

    def status_text(self):
        kind = self.status_kind()
        if kind == "running":
            return f"Running · {format_duration(self.running_time())}"  # e.g. "Running · 5m 12s"
        if kind == "crashed":
            return f"Crashed (exit {self.process.poll()})"  # e.g. a missing library gives exit 1
        return kind.capitalize()

    def to_dict(self):
        # Path objects can't go into JSON, so we turn the path into plain text
        return {"name": self.name, "path": str(self.path), "autostart": self.autostart}

    @classmethod
    def from_dict(cls, d):
        # .get(..., False): old files saved before auto-start existed still load (unticked)
        return cls(d["name"], d["path"], d.get("autostart", False))


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
        self.update_log_names()

    def log_name_for(self, entry):
        """Picks the log file name for a script.

        Only one bot.py in the list -> "bot".
        Two different bot.py files (in folders a and b) -> "bot-3f9a1c" and "bot-8d02e7".
        The code comes from the full path, so the same file always gets the same code.
        """
        same_name = [e for e in self.entries if e.name.lower() == entry.name.lower()]
        if len(same_name) <= 1:
            return entry.name
        # md5 turns the path into a long fixed code; we keep the first 6 characters.
        # lower() because Windows treats "C:/Bots" and "c:/bots" as the same folder.
        code = hashlib.md5(str(entry.path).lower().encode("utf-8")).hexdigest()[:6]
        return f"{entry.name}-{code}"

    def update_log_names(self):
        for entry in self.entries:
            # A script that was started keeps its log name until it starts again,
            # so its output box doesn't suddenly switch to a different file.
            if entry.process is None:
                entry.log_name = self.log_name_for(entry)

    def save(self):
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump([e.to_dict() for e in self.entries], f, indent=2)

    def add_script(self, path, save=True):
        path = Path(path)
        if any(e.path == path for e in self.entries):
            return False  # already in the list
        self.entries.append(ScriptEntry(path.stem, path))
        self.update_log_names()
        if save:
            self.save()
        return True

    def add_folder(self, folder):
        """Adds every .py / .pyw file directly inside `folder` (not its subfolders).

        Returns (added, skipped). Example: a folder with a.py, b.pyw and notes.txt,
        where a.py is already in the list -> (1, 1).
        """
        own_file = Path(__file__).resolve()
        added = skipped = 0
        for path in sorted(Path(folder).iterdir(), key=lambda p: p.name.lower()):
            if not path.is_file() or path.suffix.lower() not in (".py", ".pyw"):
                continue
            if path.name.startswith("_") or path.resolve() == own_file:
                continue  # skip helper files like __init__.py, and this manager itself
            if self.add_script(path, save=False):
                added += 1
            else:
                skipped += 1
        if added:
            self.save()
        return added, skipped

    def set_autostart(self, entry, value):
        entry.autostart = value
        self.save()

    def remove_script(self, entry):
        self.stop(entry)  # don't leave a removed script running with no way to stop it
        self.entries.remove(entry)
        self.update_log_names()
        self.save()

    def start(self, entry):
        """Returns True if the script is running afterwards, False if the file is missing."""
        if entry.is_running():
            return True  # already running -> don't launch a second copy
        if not entry.path.exists():
            return False
        LOG_DIR.mkdir(exist_ok=True)
        entry.log_name = self.log_name_for(entry)  # pick it fresh on every start
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
        entry.started_at = time.monotonic()
        return True

    def restart(self, entry):
        """Stop it if it's running, then start it fresh. Returns False if the file is missing."""
        if not entry.path.exists():
            return False  # check first, so we don't stop it and then fail to start it
        self.stop(entry)
        return self.start(entry)

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


class RoundedScrollbar(tk.Canvas):
    """A slim scrollbar with a rounded handle, drawn on a Canvas.

    It plugs in exactly like a normal scrollbar:
        bar = RoundedScrollbar(parent, "vertical", command=text.yview, ...)
        text.configure(yscrollcommand=bar.set)
    The widget calls bar.set(first, last) to say what part is visible
    (example: 0.25, 0.75 = the middle half), and we call `command` when you scroll.
    """

    def __init__(self, parent, orient, command, track, thickness, thin, wide):
        self.vertical = orient == "vertical"
        super().__init__(
            parent,
            width=thickness if self.vertical else 1,
            height=1 if self.vertical else thickness,
            bg=track,  # the track is just the canvas background
            highlightthickness=0,
            borderwidth=0,
        )
        self.command = command
        self.thickness = thickness
        self.thin = thin  # handle thickness normally
        self.wide = wide  # handle thickness when hovered / dragged
        self.min_handle = wide * 3  # never let the handle get smaller than this
        self.first, self.last = 0.0, 1.0  # visible part, e.g. 0.25 and 0.75
        self.hovering = False
        self.dragging = False
        self.grab_offset = 0  # where inside the handle you grabbed it

        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<Motion>", self.on_motion)
        self.bind("<Leave>", self.on_leave)
        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<MouseWheel>", lambda e: self.wheel(-1 if e.delta > 0 else 1))  # Windows
        self.bind("<Button-4>", lambda e: self.wheel(-1))  # Linux
        self.bind("<Button-5>", lambda e: self.wheel(1))

    def set(self, first, last):
        # Called by the table / text box whenever the view changes
        self.first, self.last = float(first), float(last)
        self.draw()

    # --- geometry ---

    def track_length(self):
        return self.winfo_height() if self.vertical else self.winfo_width()

    def handle_span(self):
        """(start, end) of the handle in pixels along the bar, or None if all is visible.

        Example: bar is 200px long, 0.25..0.75 visible -> handle is 100px long.
        The handle can only travel 100px (200 - 100), and first=0.25 out of a possible
        0.5 (1 - 0.5 visible) is halfway, so it starts at 50px: (50, 150).
        """
        length = self.track_length()
        visible = self.last - self.first
        if visible >= 1 or length <= 1:
            return None
        size = min(max(visible * length, self.min_handle), length)
        start = self.first / (1 - visible) * (length - size)
        return start, start + size

    def draw(self):
        self.delete("all")
        span = self.handle_span()
        if span is None:
            return
        start, end = span
        thick = self.wide if (self.hovering or self.dragging) else self.thin
        color = SCROLL_DRAG if self.dragging else (SCROLL_HOVER if self.hovering else SCROLL_THUMB)
        r = thick / 2
        # A thick line with round ends is a perfect pill shape.
        # The round end sticks out by r, so we pull the line's ends in by r.
        if self.vertical:
            mid = self.winfo_width() / 2
            self.create_line(mid, start + r, mid, end - r, width=thick, fill=color, capstyle="round")
        else:
            mid = self.winfo_height() / 2
            self.create_line(start + r, mid, end - r, mid, width=thick, fill=color, capstyle="round")

    # --- mouse ---

    def along(self, event):
        return event.y if self.vertical else event.x

    def over_handle(self, event):
        span = self.handle_span()
        return span is not None and span[0] <= self.along(event) <= span[1]

    def on_motion(self, event):
        if self.dragging:
            return
        over = self.over_handle(event)
        if over != self.hovering:
            self.hovering = over
            self.draw()

    def on_leave(self, event):
        if not self.dragging and self.hovering:
            self.hovering = False
            self.draw()

    def on_press(self, event):
        span = self.handle_span()
        if span is None:
            return
        if span[0] <= self.along(event) <= span[1]:
            self.dragging = True
            self.grab_offset = self.along(event) - span[0]
            self.draw()
        else:
            # Click on the empty track: jump one page toward the click
            self.command("scroll", -1 if self.along(event) < span[0] else 1, "pages")

    def on_drag(self, event):
        span = self.handle_span()
        if not self.dragging or span is None:
            return
        room = self.track_length() - (span[1] - span[0])  # how far the handle can travel
        if room <= 0:
            return
        start = min(max(self.along(event) - self.grab_offset, 0), room)
        # Reverse of handle_span: pixels -> fraction. Example: start=50, room=100,
        # visible=0.5 -> first = 50/100 * (1 - 0.5) = 0.25
        self.command("moveto", start / room * (1 - (self.last - self.first)))

    def on_release(self, event):
        if self.dragging:
            self.dragging = False
            self.hovering = self.over_handle(event)
            self.draw()

    def wheel(self, direction):
        self.command("scroll", direction * 3, "units")


class RoundedButton(tk.Canvas):
    """A button with rounded corners.

    ttk buttons can't have round corners, so we draw our own on a Canvas
    (a blank drawing surface): a rounded rectangle with the text on top.
    """

    def __init__(
        self, parent, text, command, bg, hover, press, fg, font, padx, pady, radius, min_width
    ):
        # Measure the text so the button is exactly wide/tall enough for it
        label_font = tkfont.Font(font=font)
        width = max(label_font.measure(text) + 2 * padx, min_width)
        height = label_font.metrics("linespace") + 2 * pady
        # bg=BG makes the corner pixels we don't paint blend into the window.
        # highlightthickness=0 removes the canvas's own border.
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=BG,
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
        )
        self.command = command
        self.colors = {"normal": bg, "hover": hover, "press": press}
        self.pressed = False
        self.hovering = False
        self.enabled = True
        self.look = None  # remembers the last set_look() call, to skip repeats

        # r = corner size. It can't be more than half the button's height or width.
        r = min(radius, height // 2, width // 2)
        x1, y1, x2, y2 = 1, 1, width - 2, height - 2
        # The four corners of the rectangle, each listed twice. With smooth=True,
        # Tk bends the line around each corner, which is what makes it round.
        points = [
            x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1,
            x2, y1, x2, y1 + r, x2, y1 + r, x2, y2 - r, x2, y2 - r,
            x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r, x1, y1 + r,
            x1, y1,
        ]  # fmt: skip
        self.shape = self.create_polygon(points, smooth=True, fill=bg, outline=bg)
        self.label = self.create_text(width // 2, height // 2, text=text, fill=fg, font=font)

        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<ButtonRelease-1>", self.on_release)

    def set_look(self, text, bg, hover, press, fg, font, enabled=True):
        """Change the text and colors in place. Used by the Start/Stop button."""
        look = (text, bg, fg, enabled)
        if look == self.look:
            return  # nothing changed (this runs every second, so skip the work)
        self.look = look
        self.enabled = enabled
        self.colors = {"normal": bg, "hover": hover, "press": press}
        self.itemconfig(self.label, text=text, fill=fg, font=font)
        self.configure(cursor="hand2" if enabled else "arrow")
        self.paint("hover" if self.hovering else "normal")

    def paint(self, state):
        color = self.colors[state]
        self.itemconfig(self.shape, fill=color, outline=color)

    def on_enter(self, event):
        self.hovering = True
        self.paint("hover")

    def on_leave(self, event):
        self.hovering = False
        self.paint("normal")

    def on_press(self, event):
        self.pressed = True
        self.paint("press")

    def on_release(self, event):
        # Only count it as a click if you let go while still over the button.
        # (Press, drag away, release = cancelled, like a normal button.)
        inside = 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        self.paint("hover" if inside else "normal")
        if self.pressed and inside and self.enabled:
            self.command()
        self.pressed = False


class App:
    """The window only. It asks ScriptManager to do the real work."""

    EMPTY_LOG_HINT = "Select a script to see its output."

    def __init__(self, root):
        self.root = root
        self.manager = ScriptManager(DATA_FILE)
        self.viewed_entry = None  # whose log is in the output box right now
        self.log_pos = 0  # how many bytes of that log we've already shown
        self.in_traceback = False  # are we in the middle of printing an error report?
        self.flash_until = 0.0  # a red message in the header is shown until this time

        # On a high-resolution screen, 1 "pixel" in our code would look tiny.
        # scale = 1.0 on a normal screen, 1.5 on a 150% screen, and so on.
        self.scale = max(1.0, root.winfo_fpixels("1i") / 96)
        self.font_normal = tkfont.Font(font=FONT)  # used to measure text widths
        self.auto_col_width = self.px(96)  # width of the Auto-start column

        root.title("Script Manager")
        root.configure(bg=BG)
        root.geometry(f"{self.px(900)}x{self.px(680)}")
        root.minsize(self.px(860), self.px(520))

        self.setup_style()
        self.make_checkbox_images()
        self.build_window()

        # Clicking the window's X button sends an event named WM_DELETE_WINDOW.
        # We catch it so we can stop every script before the window closes.
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.refresh_table()
        self.clear_log_view()
        self.setup_emergency_hotkey()
        self.tick()  # starts the once-per-second loop
        self.start_autostart_scripts()

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
        # Each row = a picture + text. We drop the default little expand/collapse arrow
        # (we don't use it) so the checkbox picture sits where we want it.
        style.layout(
            "Treeview.Item",
            [
                (
                    "Treeitem.padding",
                    {
                        "sticky": "nswe",
                        "children": [
                            ("Treeitem.image", {"side": "left", "sticky": ""}),
                            ("Treeitem.text", {"side": "left", "sticky": ""}),
                        ],
                    },
                )
            ],
        )
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

    def make_checkbox_images(self):
        # One picture per (ticked or not) x (row background). The background matters
        # because the picture's corners must blend into the row behind it.
        size = self.px(18)
        self.checkbox_images = {}
        for checked in (False, True):
            for state, color in (("even", PANEL), ("odd", PANEL_ALT), ("select", SELECT)):
                self.checkbox_images[(checked, state)] = draw_checkbox(self.root, size, checked, color, self.auto_col_width)

    def make_scrollbar(self, parent, orient, command, track):
        return RoundedScrollbar(
            parent, orient, command, track, self.px(14), self.px(6), self.px(9)
        )

    # kind picks the colors: normal (gray), go (green), info (blue), warn (orange), danger (red),
    # off (gray with dim text, for a button that can't be clicked right now)
    BUTTON_COLORS = {
        "normal": (BTN, BTN_HOVER, BTN_PRESS, TEXT, FONT),
        "go": (GO, GO_HOVER, GO_PRESS, GO_TEXT, FONT_BOLD),
        "warn": (WARN, WARN_HOVER, WARN_PRESS, WARN_TEXT, FONT_BOLD),
        "info": (INFO, INFO_HOVER, INFO_PRESS, INFO_TEXT, FONT_BOLD),
        "accent": (ACCENT, ACCENT_HOVER, ACCENT_PRESS, "#ffffff", FONT_BOLD),
        "danger": (DANGER, DANGER_HOVER, DANGER_PRESS, DANGER_TEXT, FONT_BOLD),
        "off": (BTN, BTN, BTN, OFF_TEXT, FONT_BOLD),
    }

    def make_button(self, parent, text, command, kind="normal", small=False):
        bg, hover, press, fg, font = self.BUTTON_COLORS[kind]
        if small:
            padx, pady, radius, min_width = self.px(12), self.px(4), self.px(8), self.px(88)
        else:
            padx, pady, radius, min_width = (
                self.px(16),
                self.px(8),
                self.px(BUTTON_RADIUS),
                self.px(104),
            )
        return RoundedButton(
            parent, text, command, bg, hover, press, fg, font, padx, pady, radius, min_width
        )

    def build_window(self):
        root = self.root
        pad = self.px(18)
        gap = self.px(8)

        # --- header ---
        header = ttk.Frame(root)
        header.pack(fill="x", padx=pad, pady=(pad, self.px(12)))
        left = ttk.Frame(header)
        left.pack(side="left")
        ttk.Label(left, text="Script Manager", style="Title.TLabel").pack(anchor="w")
        self.hotkey_label = ttk.Label(left, text="", style="Muted.TLabel")
        self.hotkey_label.pack(anchor="w")
        self.summary_label = ttk.Label(header, text="", style="Muted.TLabel")
        self.summary_label.pack(side="right", anchor="s", pady=(0, 3))

        # --- table (a 1-pixel BORDER-colored frame around a PANEL-colored one = thin outline) ---
        table_border = tk.Frame(root, bg=BORDER)
        table_border.pack(fill="both", expand=True, padx=pad)
        table_inner = tk.Frame(table_border, bg=PANEL)
        table_inner.pack(fill="both", expand=True, padx=1, pady=1)

        # show="tree headings": the first column (called "#0") is where the checkbox pictures go
        self.tree = ttk.Treeview(
            table_inner,
            columns=("name", "status", "path"),
            show="tree headings",
            height=6,
            selectmode="browse",  # one row at a time
        )
        self.tree.heading("#0", text="Auto-start", anchor="center")
        self.tree.column("#0", width=self.auto_col_width, anchor="center", stretch=False)
        for col, title, width, stretch in (
            ("name", "Script", 170, False),
            ("status", "Status", 200, False),
            ("path", "Path", 420, False),  # width is set by fit_path_column
        ):
            self.tree.heading(col, text=title, anchor="w")
            self.tree.column(col, width=self.px(width), anchor="w", stretch=stretch)
        tree_scroll = self.make_scrollbar(table_inner, "vertical", self.tree.yview, PANEL)
        self.hscroll = self.make_scrollbar(table_inner, "horizontal", self.tree.xview, PANEL)
        # xscrollcommand = "tell me how much is visible"; we use it to hide the bar when not needed
        self.tree.configure(yscrollcommand=tree_scroll.set, xscrollcommand=self.on_hscroll)
        tree_scroll.pack(side="right", fill="y")
        self.hscroll.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)

        # Row colors. A row gets two tags: a stripe tag (background) and a status tag (text color).
        self.tree.tag_configure("even", background=PANEL)
        self.tree.tag_configure("odd", background=PANEL_ALT)
        self.tree.tag_configure("running", foreground=GREEN)
        self.tree.tag_configure("crashed", foreground=RED)
        # Fires whenever you click a different row
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        # Clicks in the checkbox column toggle auto-start; the hand cursor shows it's clickable
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<Motion>", self.on_tree_motion)
        # Re-fit the Path column whenever the window is resized
        self.tree.bind("<Configure>", self.fit_path_column)

        # Shown on top of the empty table
        self.empty_label = tk.Label(
            self.tree,
            text='No scripts yet.\nClick "Add Script" or "Add Folder" to get started.',
            bg=PANEL,
            fg=MUTED,
            font=FONT,
            justify="center",
        )

        # --- buttons ---
        bar = ttk.Frame(root)
        bar.pack(fill="x", padx=pad, pady=(self.px(14), self.px(14)))
        self.make_button(bar, "Add Script", self.on_add).pack(side="left")
        self.make_button(bar, "Add Folder", self.on_add_folder).pack(side="left", padx=(gap, 0))
        self.make_button(bar, "Remove", self.on_remove).pack(side="left", padx=(gap, 0))
        self.make_button(bar, "Stop All", self.on_stop_all, "danger").pack(side="right")
        self.make_button(bar, "Restart", self.on_restart, "info").pack(side="right", padx=gap)
        # One button for Start and Stop. sync_toggle() swaps its text and color.
        self.toggle_btn = self.make_button(bar, "Start", self.on_toggle, "go")
        self.toggle_btn.pack(side="right")

        # --- output box ---
        log_header = ttk.Frame(root)
        log_header.pack(fill="x", padx=pad)
        self.log_label = ttk.Label(log_header, text="Output", style="Section.TLabel")
        self.log_label.pack(side="left")
        self.make_button(log_header, "Open Folder", self.on_open_folder, small=True).pack(side="right")
        self.make_button(log_header, "Open Log", self.on_open_log, small=True).pack(
            side="right", padx=(0, gap)
        )
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
        log_scroll = self.make_scrollbar(log_inner, "vertical", self.log_text.yview, LOG_BG)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)
        # Tags are named "styles" for pieces of text
        self.log_text.tag_configure("error", foreground=RED)
        self.log_text.tag_configure("hint", foreground=MUTED)

    # ---------- emergency stop ----------

    def setup_emergency_hotkey(self):
        # threading.Event = a flag that is safe to raise from any thread
        self.emergency = threading.Event()
        ok = False
        if keyboard is not None:
            try:
                # The keyboard library calls this function from ITS OWN thread when you
                # press the keys. tkinter must only be touched from the main thread, so
                # the callback does just one safe thing: raise the flag.
                keyboard.add_hotkey(EMERGENCY_HOTKEY, self.emergency.set)
                ok = True
            except Exception:
                pass  # e.g. on Linux the keyboard library needs root
        if ok:
            pretty = "+".join(part.capitalize() for part in EMERGENCY_HOTKEY.split("+"))
            self.hotkey_label.config(text=f"Emergency stop: {pretty}")
        else:
            self.hotkey_label.config(text="Emergency stop hotkey unavailable (pip install keyboard)")
        self.check_emergency()

    def check_emergency(self):
        # The main thread looks at the flag 10 times a second
        if self.emergency.is_set():
            self.emergency.clear()
            running = sum(1 for e in self.manager.entries if e.is_running())
            self.manager.stop_all()
            self.refresh_table()
            self.flash_message(f"Emergency stop: stopped {plural(running, 'script')}")
        self.root.after(100, self.check_emergency)

    def flash_message(self, text, seconds=5):
        # Show a red message in the header for a few seconds
        self.flash_until = time.time() + seconds
        self.summary_label.config(text=text, foreground=RED)

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
        self.sync_toggle()  # a script that ended by itself flips the button back to Start
        # "Run this function again 1000 ms (1 second) from now".
        # It reschedules itself every time, so it repeats forever without freezing the window.
        self.root.after(1000, self.tick)

    @staticmethod
    def status_label(entry):
        # e.g. "● Running", "✕ Crashed (exit 1)"  (the icon helps even if you can't tell the colors apart)
        return f"{STATUS_ICONS[entry.status_kind()]} {entry.status_text()}"

    @staticmethod
    def row_tags(i, entry):
        # e.g. row 3 that is running -> ("odd", "running")
        return ("odd" if i % 2 else "even", entry.status_kind())

    def update_summary(self):
        if time.time() < self.flash_until:
            return  # a red message is being shown; don't overwrite it yet
        total = len(self.manager.entries)
        running = sum(1 for e in self.manager.entries if e.is_running())
        self.summary_label.config(
            text=f"{plural(total, 'script')}  ·  {running} running", foreground=MUTED
        )

    def checkbox_image(self, i, entry, selected):
        state = "select" if selected else ("odd" if i % 2 else "even")
        return self.checkbox_images[(entry.autostart, state)]

    def refresh_checkboxes(self):
        # A highlighted row has a different background, so it needs its own checkbox picture
        selected = self.tree.selection()
        for i, entry in enumerate(self.manager.entries):
            iid = str(i)
            if self.tree.exists(iid):
                self.tree.item(iid, image=self.checkbox_image(i, entry, iid in selected))

    def fit_path_column(self, event=None):
        # The Path column is as wide as the longest path, or as wide as the leftover
        # window space if that's bigger (so a short path doesn't leave a gap).
        # If the longest path is wider than the window, the horizontal scrollbar appears.
        longest = max((self.font_normal.measure(str(e.path)) for e in self.manager.entries), default=0)
        needed = max(self.px(420), longest + self.px(32))
        others = sum(self.tree.column(c, "width") for c in ("#0", "name", "status"))
        leftover = self.tree.winfo_width() - others
        self.tree.column("path", width=max(needed, leftover))

    def on_hscroll(self, first, last):
        # first/last = which part of the table is visible, from 0.0 to 1.0.
        # Example: (0.0, 0.6) = the left 60% is visible, so there IS more to scroll to.
        self.hscroll.set(first, last)
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.hscroll.pack_forget()  # everything fits -> no scrollbar needed
        else:
            self.hscroll.pack(side="bottom", fill="x", before=self.tree)

    def on_tree_click(self, event):
        if self.tree.identify_column(event.x) != "#0":
            return  # a click anywhere else: let the table select the row as usual
        iid = self.tree.identify_row(event.y)
        if not iid:
            return  # clicked the column header
        entry = self.manager.entries[int(iid)]
        self.manager.set_autostart(entry, not entry.autostart)
        self.refresh_checkboxes()
        return "break"  # handled: don't also select the row

    def on_tree_motion(self, event):
        over_checkbox = (
            self.tree.identify_column(event.x) == "#0" and self.tree.identify_row(event.y) != ""
        )
        self.tree.configure(cursor="hand2" if over_checkbox else "")

    def refresh_table(self):
        selected = self.tree.selection()  # remember it, e.g. ("2",)
        self.tree.delete(*self.tree.get_children())  # clear all rows
        for i, entry in enumerate(self.manager.entries):
            # iid = the row's ID. Using the list index lets us find the entry again later
            self.tree.insert(
                "",
                "end",
                iid=str(i),
                text="",
                image=self.checkbox_image(i, entry, False),
                values=(entry.name, self.status_label(entry), str(entry.path)),
                tags=self.row_tags(i, entry),
            )
        # Rebuilding the table clears the highlight, so put it back.
        # Otherwise after clicking Start you'd have to click the row again to Stop it.
        for iid in selected:
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
        self.refresh_checkboxes()
        self.fit_path_column()
        # Show the "No scripts yet" hint only when the table is empty
        if self.manager.entries:
            self.empty_label.place_forget()
        else:
            self.empty_label.place(relx=0.5, rely=0.55, anchor="center")
        self.update_summary()
        self.sync_toggle()

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
        self.refresh_checkboxes()  # the highlighted row needs its own checkbox picture
        self.sync_toggle()
        entry = self.get_selected()
        # Rebuilding the table briefly empties the selection; ignore that so
        # the output box doesn't blank out every time you click a button.
        if entry is None or entry is self.viewed_entry:
            return
        self.show_log_for(entry)

    # ---------- buttons ----------

    def sync_toggle(self):
        """Make the Start/Stop button match the selected script.

        No row selected  -> gray "Start", does nothing
        bot.py stopped   -> green "Start"
        bot.py running   -> orange "Stop"
        """
        entry = self.get_selected()
        if entry is None:
            self.toggle_btn.set_look("Start", *self.BUTTON_COLORS["off"], enabled=False)
        elif entry.is_running():
            self.toggle_btn.set_look("Stop", *self.BUTTON_COLORS["warn"])
        else:
            self.toggle_btn.set_look("Start", *self.BUTTON_COLORS["go"])

    def on_toggle(self):
        entry = self.get_selected()
        if entry is None:
            return
        if entry.is_running():
            self.on_stop()
        else:
            self.on_start()

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

    def on_add_folder(self):
        folder = filedialog.askdirectory(title="Choose a folder of scripts")
        if not folder:  # Cancel
            return
        try:
            added, skipped = self.manager.add_folder(folder)
        except OSError as error:
            messagebox.showerror("Can't read folder", str(error))
            return
        self.refresh_table()
        if added == 0 and skipped == 0:
            message = "No .py or .pyw files found in that folder."
        else:
            message = f"Added {plural(added, 'script')}."
            if skipped:
                message += f"\n{skipped} already in the list."
        messagebox.showinfo("Add Folder", message)

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

    def on_restart(self):
        entry = self.get_selected()
        if entry is None:
            return
        if not self.manager.restart(entry):
            messagebox.showerror("Can't restart", f"File not found:\n{entry.path}")
        elif entry is self.viewed_entry:
            self.show_log_for(entry)  # fresh log, reload the box from the top
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

    def on_open_log(self):
        entry = self.viewed_entry
        if entry is None:
            messagebox.showinfo("Open Log", "Select a script first.")
        elif not entry.log_path.exists():
            messagebox.showinfo("Open Log", f"{entry.name} has no log yet. Start it first.")
        else:
            self.open_path(entry.log_path)

    def on_open_folder(self):
        entry = self.viewed_entry
        if entry is None:
            messagebox.showinfo("Open Folder", "Select a script first.")
        elif not entry.path.parent.exists():
            messagebox.showerror("Open Folder", f"Folder not found:\n{entry.path.parent}")
        else:
            self.open_path(entry.path.parent)

    @staticmethod
    def open_path(path):
        try:
            open_in_system(path)
        except OSError as error:
            messagebox.showerror("Can't open", str(error))

    def start_autostart_scripts(self):
        # Only scripts whose Auto-start box you ticked. Nothing runs by itself otherwise.
        for entry in self.manager.entries:
            if entry.autostart:
                self.manager.start(entry)
        self.refresh_table()

    def on_close(self):
        self.manager.stop_all()
        if keyboard is not None:
            try:
                keyboard.unhook_all()
            except Exception:
                pass
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
