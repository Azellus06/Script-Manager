import tkinter as tk
import subprocess
import sys
from pathlib import Path

# ---- Settings ----
# Add one entry per script here: "Button label": "filename.py"
SCRIPTS = {
    "Auto-clicker": "autoclicker.py",
    "Text expander": "expander.py",
    # "Another script": "another_script.py",
}

# Folder this launcher file lives in, so it finds scripts next to it
BASE_DIR = Path(__file__).parent

# Keep track of every process we start, so "Stop all" can kill them
running_processes = []


def run_script(filename):
    script_path = BASE_DIR / filename
    if not script_path.exists():
        status_label.config(text=f"Not found: {filename}")
        return

    # sys.executable = the same Python running this launcher
    # Popen starts it as its own separate process (doesn't block the window)
    process = subprocess.Popen([sys.executable, str(script_path)])
    running_processes.append(process)
    status_label.config(text=f"Started: {filename}")


def stop_all():
    for process in running_processes:
        if process.poll() is None:  # None means it's still running
            process.terminate()
    running_processes.clear()
    status_label.config(text="Stopped all scripts")


# ---- Build the window ----
root = tk.Tk()
root.title("Script Launcher")
root.geometry("250x300")

tk.Label(root, text="Choose a script to run:", font=("Segoe UI", 10, "bold")).pack(pady=10)

# One button per entry in SCRIPTS — add a script to the dict above,
# no need to touch this loop
for label, filename in SCRIPTS.items():
    tk.Button(
        root,
        text=label,
        width=25,
        command=lambda f=filename: run_script(f),  # f=filename "freezes" the value for this button
    ).pack(pady=4)

tk.Button(root, text="Stop All", width=25, bg="#e74c3c", fg="white", command=stop_all).pack(pady=15)

status_label = tk.Label(root, text="Ready", fg="gray")
status_label.pack(pady=5)

root.mainloop()
