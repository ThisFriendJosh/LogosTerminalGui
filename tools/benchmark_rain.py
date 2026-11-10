"""Measure rain rendering in a temporary workspace, without a model or saved UI state."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
import tkinter as tk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terminal_gui import TerminalGUI


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--theme", choices=("galactic-phosphor", "galactic-2"), default="galactic-2")
    parser.add_argument("--frames", type=int, default=60)
    args = parser.parse_args()
    if not 10 <= args.frames <= 600:
        parser.error("Choose 10-600 measured frames")
    scratch = ROOT/"work"
    scratch.mkdir(exist_ok=True)
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        parser.exit(1, "A Tk display is required: "+str(exc)+"\n")
    with tempfile.TemporaryDirectory(dir=scratch) as temp:
        app = TerminalGUI(window, app_root=Path(temp))
        try:
            app.register(ROOT/"terminals/scratchpad/terminal.json")
            app.apply_theme(args.theme)
            app.closing = True
            window.update()
            durations, cpu = [], []
            for frame in range(args.frames+5):
                start, cpu_start = time.perf_counter(), time.process_time()
                app.atmosphere.tick(1/app.theme.effects["frame_rate"])
                window.update_idletasks()
                if frame >= 5:
                    durations.append((time.perf_counter()-start)*1000)
                    cpu.append((time.process_time()-cpu_start)*1000)
            print(json.dumps({"theme": app.theme.id, "target_fps": app.theme.effects["frame_rate"],
                "frames": args.frames, "window": [window.winfo_width(), window.winfo_height()],
                "median_render_ms": round(statistics.median(durations), 2),
                "p95_render_ms": round(sorted(durations)[int((args.frames-1)*.95)], 2),
                "average_cpu_ms": round(sum(cpu)/len(cpu), 2), "field_cells": len(app.atmosphere.field.cells)}, indent=2))
        finally:
            app.closing = True
            app.outer.destroy()
            for pending in window.tk.call("after", "info"):
                window.after_cancel(pending)
            window.destroy()


if __name__ == "__main__":
    main()
