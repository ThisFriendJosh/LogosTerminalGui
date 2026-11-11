"""A lightweight, modular desktop terminal host. Tk + standard library only."""
from __future__ import annotations

from datetime import datetime
import json
import math
import os
from pathlib import Path
import queue
import re
import shlex
import threading
import time
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk
import uuid

from terminal_core import ANSI, TerminalModule, TerminalProcess, console_python, discover, read_preferences, write_preferences
from terminal_diagnostics import check, finish_connection_check, preflight
from terminal_protocol import API_VERSION, HOST_VERSION
from terminal_themes import RAIN_LIMITS, ThemeCatalog
from terminal_visuals import Atmosphere, NeonScrollbar, PhosphorText, RainCanvas, draw_icon
from calculator_workspace import CalculatorWorkspace, workspace_engine

ROOT = Path(__file__).resolve().parent


def set_app_icon(window):
    try:
        window.terminal_app_icon = tk.PhotoImage(master=window, file=str(ROOT/"assets/icons/logos-terminal.png"))
        window.iconphoto(True, window.terminal_app_icon)
        if os.name == "nt":
            window.iconbitmap(str(ROOT/"assets/icons/logos-terminal.ico"))
            window.iconbitmap(default=str(ROOT/"assets/icons/logos-terminal.ico"))
    except (tk.TclError, OSError):
        pass  # The host also runs from minimal SDK/test checkouts without assets.
BG = "#040907"
PANEL = "#07100c"
FIELD = "#09170f"
GREEN = "#8df6a5"
BRIGHT = "#b9ffc6"
TEXT = "#d1e8d6"
MUTED = "#7e9d86"
EDGE = "#244e32"
ERROR = "#ffb19d"
FONT_FAMILY = "Consolas"
PALETTE = {"selection": "#265339", "selection_text": BRIGHT, "code_background": "#0d2116", "placeholder": "#5f7e68",
           "disabled": "#4d6654", "button_fill": "#184229", "button_disabled": "#183323", "footer": "#536d5b"}


def activate_palette(theme, window):
    """Resolve a data-only theme for this single host and its owned dialogs."""
    global BG, PANEL, FIELD, GREEN, BRIGHT, TEXT, MUTED, EDGE, ERROR, FONT_FAMILY, PALETTE
    PALETTE = theme.palette
    BG, PANEL, FIELD = (PALETTE[k] for k in ("background", "panel", "field"))
    GREEN, BRIGHT, TEXT, MUTED, EDGE, ERROR = (PALETTE[k] for k in ("accent", "accent_bright", "text", "muted", "edge", "error"))
    available = set(tkfont.families(window))
    FONT_FAMILY = next((f for f in theme.data["typography"]["families"] if f in available), "Courier")
    window.terminal_theme, window.terminal_font_family = theme, FONT_FAMILY


def mix(a, b, amount):
    return "#" + "".join(f"{round(int(a[i:i+2],16)*(1-amount)+int(b[i:i+2],16)*amount):02x}" for i in (1, 3, 5))


def native_frame(window, border=None):
    """Style only this app window; unsupported DWM attributes are harmless."""
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        get_parent = ctypes.windll.user32.GetParent
        get_parent.argtypes, get_parent.restype = [wintypes.HWND], wintypes.HWND
        hwnd = get_parent(window.winfo_id())
        setter = ctypes.windll.dwmapi.DwmSetWindowAttribute
        setter.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        setter.restype = ctypes.c_long
        if border:
            value = ctypes.c_uint(int(border[5:7]+border[3:5]+border[1:3],16))
            setter(hwnd, 34, ctypes.byref(value), ctypes.sizeof(value))
        else:
            def dwm_color(color):
                return int(color[5:7]+color[3:5]+color[1:3], 16)
            for attribute, color in [(20, 1), (34, dwm_color(EDGE)), (35, dwm_color(PANEL)), (36, dwm_color(GREEN))]:
                value = ctypes.c_uint(color)
                setter(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value))
    except (OSError, AttributeError):
        pass


class NeonButton(tk.Canvas):
    """Small canvas buttons: color interpolation, no image assets or shader loop."""
    def __init__(self, parent, text, command, width=105, height=36, primary=False, small=False, icon=None):
        super().__init__(parent, width=width, height=height, bg=parent.cget("bg"), highlightthickness=0,
                         bd=0, takefocus=1, cursor="hand2")
        self.label, self.command, self.primary = text, command, primary
        self.active = self.hover = False
        self.enabled, self.level, self.job = True, 0.0, None
        self.small = small
        self.icon, self.pulse = icon, 0.0
        top = self.winfo_toplevel()
        self.theme = top.terminal_theme
        self.font_family = top.terminal_font_family
        top.terminal_buttons.append(self)
        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<Enter>", lambda e: self.target(True))
        self.bind("<Leave>", lambda e: self.target(False))
        self.bind("<FocusIn>", lambda e: self.target(True))
        self.bind("<FocusOut>", lambda e: self.target(False))
        self.bind("<Button-1>", lambda e: self.invoke())
        self.bind("<Return>", lambda e: self.invoke())
        self.bind("<space>", lambda e: self.invoke())
        def first_draw():
            self.initial_draw = None
            self.draw()
        self.initial_draw = self.after_idle(first_draw)

    def invoke(self):
        if self.enabled:
            self.command()

    def configure_state(self, enabled=True, active=None, text=None):
        previous = self.enabled, self.active, self.label
        self.enabled = enabled
        if active is not None:
            self.active = active
        if text is not None:
            self.label = text
        if previous == (self.enabled, self.active, self.label):
            return
        self.configure(cursor="hand2" if enabled else "arrow")
        self.draw()

    def target(self, value):
        self.hover = value
        if self.job:
            self.after_cancel(self.job)
        self.fade()

    def fade(self):
        goal = 1.0 if self.hover and self.enabled else 0.0
        self.level += (goal - self.level) * 0.48
        if abs(goal - self.level) < 0.03:
            self.level = goal
            self.job = None
        else:
            self.job = self.after(24, self.fade)
        self.draw()

    def draw(self):
        if not self.winfo_exists():
            return
        self.delete("all")
        w, h = self.winfo_width() if self.winfo_width() > 1 else int(self.cget("width")), int(self.cget("height"))
        palette = self.theme.palette
        BG, PANEL, GREEN, BRIGHT, TEXT, EDGE = (palette[k] for k in ("background", "panel", "accent", "accent_bright", "text", "edge"))
        selected = self.active or self.primary
        amount = max(self.level, 0.5 if selected else 0)
        outline = mix(EDGE, GREEN, amount) if self.enabled else palette["button_disabled"]
        fill = mix(PANEL, palette["button_fill"], amount * 0.85)
        color = BRIGHT if self.level > .3 else GREEN if selected else TEXT
        if not self.enabled:
            color = palette["disabled"]
        if self.theme.components["button_style"] == "phosphor":
            intensity = min(1, amount+.22+self.pulse*.14) if self.enabled else .08
            for offset, power in ((0, .06), (1, .15), (2, .30)):
                self.create_rectangle(1+offset, 1+offset, w-2-offset, h-2-offset,
                                      outline=mix(BG, GREEN, intensity*power))
            self.create_polygon(7, 4, w-8, 4, w-4, 8, w-4, h-8, w-8, h-4, 7, h-4, 4, h-8, 4, 8,
                                fill=fill, outline=mix(EDGE, GREEN, intensity), width=1)
            if self.active:
                self.create_line(6, 11, 6, h-11, fill=GREEN, width=2)
            x, anchor = (w/2, "center")
            if self.icon and self.theme.components["module_icons"]:
                size = 27 if h >= 45 else 18
                draw_icon(self, self.icon, 14, (h-size)/2, size, color, mix(BG, GREEN, .16+amount*.16))
                x, anchor = 53 if h >= 45 else 39, "w"
            font = (self.font_family, 10 if self.small else 11, "bold" if selected else "normal")
            options = {"text": self.label, "anchor": anchor, "font": font}
            if anchor == "w":
                options["width"] = max(24, w-x-9)
            if self.enabled:
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    self.create_text(x+dx, h/2+dy, fill=mix(BG, color, .17+amount*.10), **options)
            self.create_text(x, h/2, fill=color, **options)
            return
        # A faint second outline gives a restrained glow on hover.
        if self.level > .2:
            self.create_rectangle(1, 1, w-2, h-2, outline=mix(BG, GREEN, self.level*.15))
        self.create_polygon(7, 3, w-8, 3, w-4, 7, w-4, h-7, w-8, h-3, 7, h-3, 3, h-7, 3, 7,
                            fill=fill, outline=outline, width=1)
        if self.active:
            self.create_line(5, 10, 5, h-10, fill=GREEN, width=3)
        self.create_text(w/2, h/2, text=self.label, fill=color,
                         font=(self.font_family, 10 if self.small else 11, "bold" if selected else "normal"))

    def set_pulse(self, phase):
        phase = round(phase*12)/12
        if phase != self.pulse:
            self.pulse = phase
            if self.theme.components["button_style"] == "phosphor":
                self.draw()

    def destroy(self):
        if self.initial_draw:
            self.after_cancel(self.initial_draw)
            self.initial_draw = None
        if self.job:
            self.after_cancel(self.job)
            self.job = None
        super().destroy()


class TerminalGUI:
    def __init__(self, root, app_root=ROOT):
        self.window, self.root = root, Path(app_root)
        self.preference_path = self.root / "state/terminal_ui.json"
        self.preferences = read_preferences(self.preference_path)
        self.theme_catalog = ThemeCatalog(self.root)
        self.theme = self.theme_catalog.selected(self.preferences.get("theme", "logos-classic"))
        self.preferences["theme"] = self.theme.id
        activate_palette(self.theme, root)
        root.terminal_buttons = []
        self.atmosphere = None
        self.modules, errors = discover(self.root, self.preferences["modules"])
        order = self.preferences["module_order"]
        self.modules = dict(sorted(((i, m) for i, m in self.modules.items() if i not in self.preferences["hidden_modules"]),
                                   key=lambda item: order.index(item[0]) if item[0] in order else len(order)))
        self.events, self.processes, self.workspaces = queue.Queue(), {}, {}
        self.management_events = queue.Queue()
        self.stopping_processes, self.reconnecting, self.connection_checks = {}, {}, {}
        self.manager = None
        self.current = None
        self.panels, self.module_buttons, self.action_buttons = [], {}, {}
        self.calculator_views = {}
        self.closing = False
        self.last_animation = time.monotonic()
        self.last_lighting = self.last_native_border = 0.0
        self.animation_was_active = False
        self.metrics = {"animation_ticks": 0, "poll_cycles": 0}
        root.title("Logos Terminal — Modular Workspace")
        set_app_icon(root)
        root.geometry("1320x850")
        root.minsize(980, 650)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.body_font = tkfont.Font(family=FONT_FAMILY, size=self.preferences["font_size"])
        self.bold_font = tkfont.Font(family=FONT_FAMILY, size=self.preferences["font_size"], weight="bold")
        self.small_font = (FONT_FAMILY, 10)
        self.configure_style()
        self.build_layout()
        self.draw_modules()
        selected = self.preferences.get("selected")
        if self.modules:
            self.select_module(selected if selected in self.modules else next(iter(self.modules)))
        else:
            self.empty_workspace()
        self.setup_atmosphere()
        for error in errors + self.theme_catalog.errors:
            self.show_system(error, "error")
        self.window.after(70, self.poll)
        self.window.after(120, self.animate)
        self.window.after(80, lambda: native_frame(self.window))

    def configure_style(self):
        root = self.window
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=FIELD, background=FIELD, foreground=GREEN,
                        arrowcolor=GREEN, bordercolor=EDGE, lightcolor=EDGE, darkcolor=EDGE, padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", GREEN)], selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", GREEN)])
        root.option_add("*TCombobox*Listbox.background", FIELD)
        root.option_add("*TCombobox*Listbox.foreground", TEXT)
        root.option_add("*TCombobox*Listbox.selectBackground", PALETTE["selection"])
        root.option_add("*TCombobox*Listbox.font", f"{{{FONT_FAMILY}}} 11")

    def label(self, parent, text, color=None, size=11, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color or TEXT,
                        font=(FONT_FAMILY, size, "bold" if bold else "normal"), **kwargs)

    def panel(self, parent, **kwargs):
        frame = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=EDGE, **kwargs)
        self.panels.append(frame)
        return frame

    def build_layout(self):
        outer = tk.Frame(self.window, bg=BG, padx=20, pady=15)
        self.outer = outer
        outer.pack(fill="both", expand=True)
        header = tk.Frame(outer, bg=BG)
        header.pack(fill="x", pady=(0, 17))
        logo = tk.Canvas(header, width=45, height=49, bg=BG, highlightthickness=0)
        logo.pack(side="left", padx=(0, 12))
        logo.create_polygon(22, 3, 41, 14, 41, 36, 22, 47, 3, 36, 3, 14, outline=GREEN, fill=PANEL, width=1)
        logo.create_line(14, 16, 14, 34, 31, 34, fill=GREEN, width=2)
        logo.create_line(23, 14, 23, 25, 32, 25, fill=GREEN, width=2)
        brand = tk.Frame(header, bg=BG)
        brand.pack(side="left")
        self.brand = self.label(brand, "LOGOS / TERMINAL", GREEN, 20, True)
        self.brand.pack(anchor="w")
        self.label(brand, "M O D U L A R   W O R K S P A C E", MUTED, 9).pack(anchor="w", pady=(3, 0))
        self.effects_button = NeonButton(header, "◈ Effects on", self.toggle_effects, width=130, small=True)
        self.effects_button.pack(side="right", padx=(10, 0))
        NeonButton(header, "Settings", self.settings, width=105, small=True, icon="gear").pack(side="right")
        body = tk.Frame(outer, bg=BG)
        body.pack(fill="both", expand=True)
        sidebar = self.panel(body, width=212)
        sidebar.pack(side="left", fill="y", padx=(0, 17))
        sidebar.pack_propagate(False)
        self.sidebar = sidebar
        self.module_count = self.label(sidebar, "TERMINALS", MUTED, 10, True, anchor="w")
        self.module_count.pack(fill="x", padx=17, pady=(21, 18))
        module_area = tk.Frame(sidebar, bg=PANEL)
        module_area.pack(fill="both", expand=True, padx=9)
        self.module_canvas = RainCanvas(module_area, bg=PANEL, width=180)
        self.module_canvas.pack(side="left", fill="both", expand=True)
        self.module_list = tk.Frame(self.module_canvas, bg=PANEL)
        self.module_canvas_item = self.module_canvas.create_window(0, 0, window=self.module_list, anchor="nw")
        self.module_list.bind("<Configure>", lambda e: self.module_canvas.configure(scrollregion=self.module_canvas.bbox(self.module_canvas_item)))
        self.module_canvas.bind("<Configure>", lambda e: self.module_canvas.itemconfigure(self.module_canvas_item, width=e.width))
        self.module_canvas.bind("<MouseWheel>", lambda e: self.module_canvas.yview_scroll(-int(e.delta/120), "units"))
        bottom = tk.Frame(sidebar, bg=PANEL)
        bottom.pack(side="bottom", fill="x", padx=12, pady=15)
        NeonButton(bottom, "+ Load terminal", self.load_dialog, width=184, primary=True).pack(fill="x", pady=(0, 14))
        self.label(bottom, "LOCAL WORKSPACE", MUTED, 9, anchor="w").pack(fill="x", padx=5)
        self.label(bottom, "Your tools. One interface.", PALETTE["footer"], 8, anchor="w").pack(fill="x", padx=5, pady=(5, 0))
        main = tk.Frame(body, bg=BG)
        main.pack(side="left", fill="both", expand=True)
        module_head = tk.Frame(main, bg=BG)
        module_head.pack(fill="x", pady=(2, 13))
        title_block = tk.Frame(module_head, bg=BG)
        title_block.pack(side="left", fill="x", expand=True)
        self.title = self.label(title_block, "Choose a terminal", GREEN, 21, True, anchor="w")
        self.title.pack(fill="x")
        self.subtitle = self.label(title_block, "Load a module to begin", MUTED, 10, anchor="w")
        self.subtitle.pack(fill="x", pady=(5, 0))
        self.connect_button = NeonButton(module_head, "Connect", self.connect_or_stop, width=112, primary=True)
        self.connect_button.pack(side="right", padx=(8, 0))
        self.logs_button = NeonButton(module_head, "Logs", self.show_logs, width=64, small=True)
        self.logs_button.pack(side="right", padx=(8, 0))
        self.history_button = NeonButton(module_head, "History", lambda: self.send_control("sessions"), width=85, small=True)
        self.history_button.pack(side="right", padx=(8, 0))
        self.new_button = NeonButton(module_head, "+ New", lambda: self.send_control("new"), width=80, small=True)
        self.new_button.pack(side="right")
        # Reserve control widths first; long module names cannot hide Connect.
        title_block.pack_forget()
        title_block.pack(side="left", fill="x", expand=True)
        self.view_bar = tk.Frame(main, bg=BG)
        self.content = tk.Frame(main, bg=BG)
        self.content.pack(fill="both", expand=True)
        self.toolbar = tk.Frame(self.content, bg=BG)
        self.toolbar.pack(fill="x", pady=(0, 10))
        self.text_area = tk.Frame(self.content, bg=BG)
        self.text_area.pack(fill="both", expand=True)
        self.visual_area = tk.Frame(self.content, bg=BG)
        transcript_panel = self.panel(self.text_area)
        transcript_panel.pack(fill="both", expand=True)
        transcript_top = tk.Frame(transcript_panel, bg=PANEL)
        transcript_top.pack(fill="x", padx=18, pady=(12, 0))
        self.status_label = self.label(transcript_top, "○ DISCONNECTED", MUTED, 9, anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True)
        self.copy_button = NeonButton(transcript_top, "Copy", self.copy_transcript, width=64, height=29, small=True)
        self.copy_button.pack(side="right")
        text_wrap = tk.Frame(transcript_panel, bg=PANEL)
        text_wrap.pack(fill="both", expand=True, padx=13, pady=(8, 10))
        self.transcript = PhosphorText(text_wrap, bg=PANEL, fg=TEXT, font=self.body_font, wrap="word", bd=0,
            highlightthickness=0, padx=12, pady=10, spacing1=1, spacing3=4, selectbackground=PALETTE["selection"],
            selectforeground=PALETTE["selection_text"], cursor="arrow", state="disabled", exportselection=False)
        self.transcript.set_theme(self.theme, self.preferences["effects"])
        self.transcript.pack(side="left", fill="both", expand=True)
        if self.theme.components["button_style"] == "phosphor":
            scrollbar = NeonScrollbar(text_wrap, self.transcript.yview, PALETTE)
        else:
            scrollbar = tk.Scrollbar(text_wrap, command=self.transcript.yview, bg=EDGE, troughcolor=PANEL,
                                    activebackground=GREEN, width=9, bd=0, highlightthickness=0)
        scrollbar.pack(side="right", fill="y")
        self.transcript.configure(yscrollcommand=scrollbar.set)
        self.transcript.tag_configure("label", foreground=GREEN, font=(FONT_FAMILY, 9, "bold"), spacing1=18, spacing3=7)
        self.transcript.tag_configure("body", foreground=TEXT, lmargin1=12, lmargin2=12)
        self.transcript.tag_configure("user", foreground=PALETTE["user"], lmargin1=12, lmargin2=12)
        self.transcript.tag_configure("bold", foreground=BRIGHT, font=self.bold_font)
        self.transcript.tag_configure("code", background=PALETTE["code_background"], foreground=GREEN)
        self.transcript.tag_configure("muted", foreground=MUTED)
        self.transcript.tag_configure("error", foreground=ERROR, lmargin1=12, lmargin2=12)
        self.transcript.tag_configure("welcome", foreground=GREEN, font=(FONT_FAMILY, 21, "bold"), spacing1=20, spacing3=15)
        composer = self.panel(self.text_area)
        composer.pack(fill="x", pady=(12, 0))
        composer_top = tk.Frame(composer, bg=PANEL)
        composer_top.pack(fill="x", padx=17, pady=(12, 4))
        self.input_label = self.label(composer_top, "MESSAGE", MUTED, 9, True)
        self.input_label.pack(side="left")
        self.translation = tk.StringVar(value="KJV")
        self.translation_box = ttk.Combobox(composer_top, textvariable=self.translation, values=["KJV"], width=8, state="readonly", font=(FONT_FAMILY, 10))
        self.hint = self.label(composer_top, "Enter to send  ·  Shift+Enter for a new line", MUTED, 9)
        self.hint.pack(side="right")
        row = tk.Frame(composer, bg=PANEL)
        row.pack(fill="x", padx=17, pady=(4, 13))
        self.input = tk.Text(row, height=3, bg=FIELD, fg=BRIGHT, insertbackground=GREEN, font=self.body_font,
            bd=0, highlightthickness=1, highlightbackground=EDGE, highlightcolor=GREEN, padx=12, pady=10,
            wrap="word", selectbackground=PALETTE["selection"], undo=True, exportselection=False,
            insertwidth=self.body_font.measure("M") if self.theme.effects["block_cursor"] else 2,
            insertofftime=500 if self.preferences["effects"] else 0, insertontime=600)
        self.input.pack(side="left", fill="both", expand=True)
        self.input.bind("<Return>", self.enter)
        self.input.bind("<Shift-Return>", lambda e: None)
        self.input.bind("<FocusIn>", lambda e: self.hide_placeholder())
        self.input.bind("<FocusOut>", lambda e: self.show_placeholder())
        self.input.bind("<KeyPress>", self.input_key, add=True)
        self.placeholder = False
        self.send_button = NeonButton(row, "Send →", self.send_input, width=110, height=58, primary=True)
        self.send_button.pack(side="right", padx=(13, 0))
        self.input.pack_forget()
        self.input.pack(side="left", fill="both", expand=True)
        footer = tk.Frame(main, bg=BG)
        footer.pack(fill="x", pady=(9, 0))
        self.footer = self.label(footer, "Ready to load a terminal", MUTED, 9, anchor="w")
        self.footer.pack(side="left", fill="x", expand=True)
        self.label(footer, f"HOST {HOST_VERSION}  /  MODULE API {API_VERSION}", PALETTE["footer"], 8).pack(side="right")
        # Reserve the composer and footer before allocating the flexible transcript.
        # This keeps input visible at the minimum window size and larger DPI scales.
        transcript_panel.pack_forget()
        composer.pack_forget()
        footer.pack_forget()
        footer.pack(side="bottom", fill="x", pady=(9, 0))
        composer.pack(side="bottom", fill="x", pady=(12, 0))
        transcript_panel.pack(fill="both", expand=True)
        self.window.bind("<Control-l>", lambda e: self.focus_input())
        self.window.bind("<Control-n>", lambda e: self.send_control("new"))
        self.window.bind("<Escape>", lambda e: self.stop_current() if self.current and self.workspace()["busy"] else None)
        self.update_effect_label()

    def workspace(self, identifier=None):
        identifier = identifier or self.current
        if identifier not in self.workspaces:
            self.workspaces[identifier] = {"entries": [], "input": "", "ready": False, "busy": False,
                "status": "Disconnected", "action": self.modules[identifier].actions[0]["id"],
                "pending": None, "request": None, "logs": [], "translations": ["KJV"], "capabilities": [], "info": ""}
        return self.workspaces[identifier]

    def draw_modules(self):
        for child in self.module_list.winfo_children():
            child.destroy()
        self.module_buttons.clear()
        self.module_count.configure(text=f"TERMINALS  /  {len(self.modules):02d}")
        icons = ("reticle", "network", "chip", "document", "gear")
        for index, (identifier, module) in enumerate(self.modules.items()):
            label = module.name if self.theme.components["module_icons"] else ">_  " + module.name
            button = NeonButton(self.module_list, label, lambda i=identifier: self.select_module(i), width=190, height=49, icon=icons[index % len(icons)])
            button.pack(fill="x", pady=(0, 4))
            button.bind("<MouseWheel>", lambda e: self.module_canvas.yview_scroll(-int(e.delta/120), "units"))
            self.module_buttons[identifier] = button
        if not self.modules:
            self.label(self.module_list, "No modules loaded.\nUse Load terminal below.", MUTED, 10, justify="left").pack(padx=9, pady=10)

    def empty_workspace(self):
        self.current = None
        self.update_workspace_view()
        self.title.configure(text="YOUR TERMINAL WORKSPACE")
        self.subtitle.configure(text="Load a terminal to get started.")
        for child in self.toolbar.winfo_children():
            child.destroy()
        self.action_buttons.clear()
        self.input.delete("1.0", "end")
        self.placeholder = False
        self.input_label.configure(text="INPUT")
        self.translation_box.pack_forget()
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.insert("end", "\nLoad a terminal to begin.\n", "welcome")
        self.transcript.configure(state="disabled")
        self.refresh_controls()

    def terminal_manager(self):
        from terminal_manager import TerminalManager
        if self.manager and self.manager.dialog.winfo_exists():
            self.manager.dialog.lift()
            return self.manager
        self.manager = TerminalManager(self, NeonButton, {"bg": BG, "field": FIELD, "text": TEXT, "muted": MUTED,
                                                        "green": GREEN, "edge": EDGE, "selection": PALETTE["selection"], "font": FONT_FAMILY})
        return self.manager

    def move_module(self, identifier, direction):
        order = list(self.modules)
        index = order.index(identifier)
        target = index+direction
        if not 0 <= target < len(order):
            return
        order[index], order[target] = order[target], order[index]
        self.modules = {i: self.modules[i] for i in order}
        self.preferences["module_order"] = order
        self.draw_modules()
        for i, button in self.module_buttons.items():
            button.configure_state(active=i == self.current)
        self.save()

    def unload_module(self, identifier):
        module = self.modules[identifier]
        if identifier == self.current:
            self.workspace()["input"] = self.input_text()
        self.reconnecting.pop(identifier, None)
        self.stop(identifier)
        if identifier in self.calculator_views:
            self.calculator_views.pop(identifier).destroy()
        self.connection_checks.pop(identifier, None)
        del self.modules[identifier]
        self.preferences["modules"] = [p for p in self.preferences["modules"] if Path(p).resolve() != module.path]
        if identifier not in self.preferences["hidden_modules"]:
            self.preferences["hidden_modules"].append(identifier)
        self.preferences["module_order"] = list(self.modules)
        if identifier == self.current:
            self.current = None
            if self.modules:
                self.select_module(next(iter(self.modules)))
            else:
                self.preferences["selected"] = ""
                self.empty_workspace()
        self.draw_modules()
        for i, button in self.module_buttons.items():
            button.configure_state(active=i == self.current)
        self.save()

    def reconnect_module(self, identifier):
        if identifier not in self.modules or identifier in self.reconnecting:
            return
        state = self.workspace(identifier)
        process = self.processes.get(identifier)
        if state["busy"] or (process and not state["ready"]):
            return
        if not process:
            self.connect(identifier)
            return
        self.reconnecting[identifier] = process.generation
        self.stop(identifier)
        state["status"] = "Reconnecting..."

    def validate_module(self, identifier):
        record = {"status": "validated", "started": time.monotonic(), "elapsed_seconds": 0,
                  "checks": preflight(self.modules[identifier], self.root)}
        if any(c["status"] == "fail" for c in record["checks"]):
            record["status"] = "failed"
        self.connection_checks[identifier] = record
        return record

    def test_connection(self, identifier):
        previous = self.connection_checks.get(identifier)
        if identifier in self.reconnecting or (previous and previous["status"] == "checking"):
            return previous
        record = self.validate_module(identifier)
        if record["status"] == "failed":
            return record
        record["status"] = "checking"
        if identifier not in self.processes:
            self.connect(identifier)
        record["generation"] = self.processes[identifier].generation if identifier in self.processes else None
        self.advance_connection_checks()
        return record

    def advance_connection_checks(self):
        for identifier, record in list(self.connection_checks.items()):
            if record["status"] != "checking" or identifier not in self.modules:
                continue
            if identifier in self.reconnecting and time.monotonic()-record["started"] < 30:
                continue
            process, state = self.processes.get(identifier), self.workspace(identifier)
            if process and record.get("generation") is None:
                record["generation"] = process.generation
            if not process or process.generation != record.get("generation") or state["ready"]:
                finish_connection_check(record, self.modules[identifier], process, state)
            elif time.monotonic()-record["started"] >= 30:
                record["checks"].append(check("handshake", "fail", "Startup exceeded the 30-second compatibility limit.", state.get("last_error", "Check Logs, then reconnect.")))
                record.update(status="failed", elapsed_seconds=round(time.monotonic()-record["started"], 2))

    def select_module(self, identifier):
        if self.current:
            self.workspace()["input"] = self.input_text()
            if self.current in self.calculator_views:
                self.calculator_views[self.current].snapshot()
        self.current = identifier
        self.preferences["selected"] = identifier
        module, state = self.modules[identifier], self.workspace()
        self.title.configure(text=module.name.upper())
        self.subtitle.configure(text=module.description)
        for key, button in self.module_buttons.items():
            button.configure_state(active=key == identifier)
        for child in self.toolbar.winfo_children():
            child.destroy()
        self.action_buttons.clear()
        for action in module.actions:
            button = NeonButton(self.toolbar, action["label"], lambda a=action["id"]: self.select_action(a), width=max(82, len(action["label"])*8+27), height=34, small=True)
            button.pack(side="left", padx=(0, 6))
            self.action_buttons[action["id"]] = button
        self.input.configure(fg=BRIGHT)
        self.input.delete("1.0", "end")
        self.input.insert("1.0", state["input"])
        self.placeholder = False
        self.select_action(state["action"])
        self.render_transcript()
        self.update_workspace_view()
        self.refresh_controls()
        self.save()
        if self.atmosphere:
            self.window.after_idle(self.refresh_atmosphere)

    def update_workspace_view(self, visual=None):
        for child in self.view_bar.winfo_children():
            child.destroy()
        module = self.modules.get(self.current)
        engine = workspace_engine(module) if module else None
        state = self.workspace() if module else {}
        if visual is not None:
            state["visual"] = visual
        use_visual = bool(engine and state.get("visual", True))
        if engine:
            self.view_bar.pack(fill="x", pady=(0, 8), before=self.content)
            for label, selected in [("Visual workspace", True), ("Terminal", False)]:
                button = NeonButton(self.view_bar, label, lambda v=selected: self.update_workspace_view(v),
                                    width=160 if selected else 100, height=32, small=True)
                button.configure_state(active=use_visual == selected)
                button.pack(side="left", padx=(0, 7))
        else:
            self.view_bar.pack_forget()
        for view in self.calculator_views.values():
            view.pack_forget()
        if use_visual:
            self.toolbar.pack_forget()
            self.text_area.pack_forget()
            self.visual_area.pack(fill="both", expand=True)
            if self.current not in self.calculator_views:
                self.calculator_views[self.current] = CalculatorWorkspace(self.visual_area, self, self.current, PALETTE)
            self.calculator_views[self.current].pack(fill="both", expand=True)
        else:
            self.visual_area.pack_forget()
            if self.text_area.winfo_manager():
                self.toolbar.pack(fill="x", pady=(0, 10), before=self.text_area)
            else:
                self.toolbar.pack(fill="x", pady=(0, 10))
            self.text_area.pack(fill="both", expand=True)
        if self.atmosphere:
            self.window.after_idle(self.refresh_atmosphere)

    def action(self):
        return next(a for a in self.modules[self.current].actions if a["id"] == self.workspace()["action"])

    def select_action(self, action):
        self.workspace()["action"] = action
        for key, button in self.action_buttons.items():
            button.configure_state(active=key == action)
        descriptor = self.action()
        label = descriptor["label"].upper()
        self.input_label.configure(text=f"> {self.current}:~$  {label}" if self.theme.components["terminal_prompts"] else label)
        self.send_button.configure_state(text=descriptor.get("button", "Send") + " →")
        self.hide_placeholder()
        self.show_placeholder()
        self.translation_box.pack_forget()
        if descriptor.get("translations"):
            values = list(self.workspace()["translations"])
            if action == "search":
                values.append("ALL")
            self.translation_box.configure(values=values)
            if self.translation.get() not in values:
                self.translation.set(values[0])
            self.translation_box.pack(side="left", padx=12)

    def show_placeholder(self):
        if not self.current or self.input.get("1.0", "end-1c").strip() or self.input.focus_get() == self.input:
            return
        self.input.insert("1.0", self.action().get("placeholder", "Type a message…"))
        self.input.configure(fg=PALETTE["placeholder"])
        self.placeholder = True

    def hide_placeholder(self):
        if self.placeholder:
            self.input.delete("1.0", "end")
            self.input.configure(fg=BRIGHT)
            self.placeholder = False

    def input_key(self, event):
        if self.placeholder and event.keysym not in {"Tab", "Shift_L", "Shift_R"}:
            self.hide_placeholder()

    def input_text(self):
        return "" if self.placeholder else self.input.get("1.0", "end-1c")

    def focus_input(self):
        self.hide_placeholder()
        self.input.focus_set()

    def enter(self, event):
        if event.state & 0x1:
            return None
        self.send_input()
        return "break"

    def append(self, identifier, role, text):
        state = self.workspace(identifier)
        state["entries"].append((role, str(text)))
        # Keep the visible scrollback bounded; model conversations persist separately.
        state["entries"] = state["entries"][-300:]
        if identifier == self.current:
            self.render_entry(role, str(text))

    def show_system(self, text, role="system"):
        if self.current:
            self.append(self.current, role, text)

    def render_transcript(self):
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        state = self.workspace()
        if not state["entries"]:
            if self.theme.components["terminal_prompts"]:
                self.transcript.insert("end", "\n> WORKSPACE READY\n", "welcome")
                self.transcript.insert("end", "> " + self.modules[self.current].description + "\n\n", "body")
                self.transcript.insert("end", "> Module registered. Send a command to connect.\n\n> Awaiting input.\n", "muted")
            else:
                self.transcript.insert("end", "\nMake room for clear thinking.\n", "welcome")
                self.transcript.insert("end", self.modules[self.current].description + ".\n\n", "body")
                self.transcript.insert("end", "Type below to begin. The terminal connects when you send.\n\nSwitch terminals in the sidebar, or load another module at any time.\n", "muted")
        self.transcript.configure(state="disabled")
        for role, text in state["entries"]:
            self.render_entry(role, text)

    def render_entry(self, role, text):
        self.transcript.configure(state="normal")
        if len(self.workspace()["entries"]) == 1:
            self.transcript.delete("1.0", "end")
        labels = {"user": "YOU", "assistant": self.modules[self.current].name.upper(), "source": "REFERENCE", "system": "WORKSPACE", "error": "ATTENTION", "terminal": "TERMINAL"}
        prefix = "> " if self.theme.components["terminal_prompts"] else ""
        self.transcript.insert("end", prefix + labels.get(role, role.upper()) + "\n", "label")
        tag = "error" if role == "error" else "user" if role == "user" else "body"
        in_code = False
        for line in text.splitlines():
            if line.startswith("```"):
                in_code = not in_code
                continue
            line = re.sub(r"^#{1,6}\s+", "", line)
            if prefix and role == "system":
                self.transcript.insert("end", prefix, tag)
            for piece in re.split(r"(\*\*.+?\*\*|`[^`]+`)", line):
                if piece.startswith("**") and piece.endswith("**"):
                    self.transcript.insert("end", piece[2:-2], (tag, "bold"))
                elif piece.startswith("`") and piece.endswith("`"):
                    self.transcript.insert("end", piece[1:-1], (tag, "code"))
                else:
                    self.transcript.insert("end", piece, (tag, "code") if in_code else tag)
            self.transcript.insert("end", "\n", tag)
        self.transcript.insert("end", "\n")
        self.transcript.configure(state="disabled")
        self.transcript.see("end")

    def send_input(self):
        if not self.current or self.workspace()["busy"]:
            return
        action, text = self.action(), self.input_text().strip()
        if not text and not action.get("allow_empty"):
            self.focus_input()
            return
        self.hide_placeholder()
        self.input.delete("1.0", "end")
        self.workspace()["input"] = ""
        self.submit(action["id"], text, translation=self.translation.get())

    def send_control(self, action):
        if self.current and action in self.workspace()["capabilities"] and not self.workspace()["busy"]:
            self.submit(action)

    def submit(self, action, text="", **payload):
        state = self.workspace()
        if state["busy"]:
            return
        if text:
            self.append(self.current, "user", text)
        state["pending"] = (action, text, payload)
        state["busy"] = True
        if self.current not in self.processes:
            self.connect()
        elif state["ready"]:
            self.dispatch(self.current)
        self.refresh_controls()

    def dispatch(self, identifier):
        state, process = self.workspace(identifier), self.processes[identifier]
        pending = state["pending"]
        if not pending:
            return
        action, text, payload = pending
        try:
            state["request"] = process.send(action, text, **payload)
            state["status"] = "Working…"
            if process.module.protocol == "text":
                state["pending"], state["busy"] = None, False
                state["status"] = "Connected"
        except (OSError, ValueError, RuntimeError) as exc:
            self.fail(identifier, str(exc))

    def connect_or_stop(self):
        if self.current in self.processes:
            self.stop_current()
        else:
            self.connect()

    def connect(self, identifier=None):
        identifier = identifier or self.current
        if not identifier or identifier not in self.modules or identifier in self.processes or identifier in self.reconnecting:
            return
        state = self.workspace(identifier)
        previous = next((p for p in self.stopping_processes.values() if p.module.id == identifier), None)
        if previous:
            self.reconnecting[identifier] = previous.generation
            state["status"] = "Waiting for the previous worker to stop..."
            return
        session = self.preferences["sessions"].setdefault(identifier, uuid.uuid4().hex)
        process = TerminalProcess(self.modules[identifier], self.root, session, self.events)
        self.processes[identifier] = process
        state.update(status="Connecting...", last_error="", connection_error="")
        self.refresh_controls()
        def start():
            try:
                process.start()
            except Exception as exc:
                process.emit({"event": "error", "text": str(exc)})
                process.emit({"event": "exit", "code": -1})
        threading.Thread(target=start, daemon=False).start()
        self.window.after(30000, lambda: self.check_start(identifier, process.generation))

    def check_start(self, identifier, generation):
        process = self.processes.get(identifier)
        if process and process.generation == generation and not self.workspace(identifier)["ready"]:
            self.fail(identifier, "Terminal did not finish its compatibility check within 30 seconds. Check Logs or reconnect.")
            self.stop(identifier)

    def stop_current(self):
        if self.current:
            self.stop(self.current)

    def stop(self, identifier):
        process = self.processes.pop(identifier, None)
        state = self.workspace(identifier)
        interrupted = state["busy"]
        state.update(ready=False, busy=False, pending=None, request=None, status="Disconnected")
        if process:
            self.stopping_processes[process.generation] = process
            def finish():
                error = ""
                try:
                    process.stop()
                    if process.process and process.process.poll() is None:
                        error = "The previous worker is still stopping. Try reconnecting shortly."
                except Exception as exc:
                    error = str(exc)
                self.management_events.put((identifier, process.generation, error))
            threading.Thread(target=finish, daemon=True).start()
        if interrupted:
            self.append(identifier, "system", "Request stopped. Previously saved conversations are preserved.")
        self.refresh_controls()

    def fail(self, identifier, message):
        state = self.workspace(identifier)
        state["last_error"] = message
        pending = state.get("pending")
        if pending and pending[1] and identifier == self.current and not self.input_text():
            self.hide_placeholder()
            self.input.insert("1.0", pending[1])
        state.update(busy=False, pending=None, request=None, status="Ready" if state["ready"] else "Connection failed")
        self.append(identifier, "error", message)
        if identifier in self.calculator_views:
            self.calculator_views[identifier].error(message)
        self.refresh_controls()

    def poll(self):
        if self.closing:
            return
        self.metrics["poll_cycles"] += 1
        for generation, previous in list(self.stopping_processes.items()):
            if previous.process and previous.process.poll() is not None:
                self.management_events.put((previous.module.id, generation, ""))
        while not self.management_events.empty():
            identifier, generation, error = self.management_events.get_nowait()
            previous = self.stopping_processes.get(generation)
            still_running = bool(previous and previous.process and previous.process.poll() is None)
            if not still_running:
                self.stopping_processes.pop(generation, None)
            elif not error:
                error = "The previous worker has not finished stopping. A replacement was not started."
            if self.reconnecting.get(identifier) == generation:
                self.reconnecting.pop(identifier)
                if identifier in self.modules and identifier not in self.processes:
                    if error:
                        self.fail(identifier, error)
                    else:
                        self.connect(identifier)
        for _ in range(200):
            try:
                identifier, generation, event = self.events.get_nowait()
            except queue.Empty:
                break
            process = self.processes.get(identifier)
            if not process or process.generation != generation:
                continue
            state, kind = self.workspace(identifier), event.get("event")
            if kind == "ready":
                state.update(ready=True, status="Connected", info=event.get("model", "Local process"),
                             translations=event.get("translations") or ["KJV"], capabilities=event.get("capabilities", []),
                             connection_error=event.get("connection_error", ""))
                if event.get("session"):
                    self.preferences["sessions"][identifier] = event["session"]
                if state["pending"]:
                    self.dispatch(identifier)
                if identifier == self.current:
                    self.select_action(state["action"])
            elif kind == "history":
                # The ready event may arrive while a first message is queued.
                pending_text = state["pending"][1] if state.get("pending") else ""
                state["entries"] = [(m.get("role", "assistant"), m.get("content", "")) for m in event.get("messages", [])]
                if pending_text:
                    state["entries"].append(("user", pending_text))
                if event.get("session"):
                    self.preferences["sessions"][identifier] = event["session"]
                if event.get("id"):
                    state.update(busy=False, pending=None, request=None, status="Connected")
                if identifier == self.current:
                    self.render_transcript()
                self.save()
            elif kind == "status":
                state["status"] = event.get("text", "Working…")
            elif kind == "result":
                state.update(busy=False, pending=None, request=None, status="Connected")
                if identifier in self.calculator_views:
                    try:
                        self.calculator_views[identifier].receive(event)
                    except (ValueError, TypeError, KeyError, tk.TclError) as exc:
                        self.append(identifier, "error", "Invalid calculator view data: " + str(exc))
                if event.get("kind") in {"session_list", "module_list"}:
                    if identifier == self.current:
                        self.choose_item(identifier, event)
                elif event.get("text"):
                    self.append(identifier, "assistant" if event.get("kind") == "assistant" else "source", event["text"])
                    audit = event.get("audit", {})
                    if audit.get("output_complete") is False:
                        self.append(identifier, "system", "This response reached the model's limit and is partial.")
            elif kind == "error":
                self.fail(identifier, event.get("text", "The terminal could not complete the request"))
            elif kind == "exit":
                self.processes.pop(identifier, None)
                state.update(ready=False, busy=False, pending=None, status="Disconnected")
                if not event.get("stopped"):
                    self.append(identifier, "system" if event.get("code") == 0 else "error", f"Terminal process exited (code {event.get('code')}). You can reconnect.")
            elif kind == "log":
                state["logs"].append(event.get("text", ""))
                state["logs"] = state["logs"][-400:]
            elif kind == "stream":
                text = ANSI.sub("", event.get("text", "")).replace("\r\n", "\n").replace("\r", "")
                if state["entries"] and state["entries"][-1][0] == "terminal":
                    role, previous = state["entries"][-1]
                    state["entries"][-1] = (role, (previous + text)[-150000:])
                else:
                    state["entries"].append(("terminal", text))
                if identifier == self.current:
                    self.render_transcript()
        self.refresh_controls()
        self.advance_connection_checks()
        self.window.after(70, self.poll)

    def refresh_controls(self):
        if not self.current:
            for button in (self.connect_button, self.send_button, self.history_button, self.new_button):
                button.configure_state(enabled=False)
            self.status_label.configure(text="NO TERMINAL SELECTED", fg=MUTED)
            self.footer.configure(text=f"{len(self.modules)} terminals loaded")
            return
        state = self.workspace()
        if self.current in self.calculator_views:
            self.calculator_views[self.current].set_busy(state["busy"])
        running = self.current in self.processes
        self.connect_button.configure_state(enabled=self.current not in self.reconnecting,
            text="Stop" if state["busy"] and running else "Disconnect" if running else "Connect")
        self.send_button.configure_state(enabled=not state["busy"])
        supports_history = "sessions" in state["capabilities"]
        self.history_button.configure_state(enabled=supports_history and not state["busy"])
        self.new_button.configure_state(enabled="new" in state["capabilities"] and not state["busy"])
        self.status_label.configure(text=("● " if state["ready"] else "○ ") + state["status"].upper(), fg=GREEN if state["ready"] else MUTED)
        self.footer.configure(text=(state["info"] + "  ·  " if state["info"] else "") + f"{len(self.modules)} terminals loaded")

    def copy_transcript(self):
        if self.current:
            text = "\n\n".join(role.upper() + "\n" + value for role, value in self.workspace()["entries"])
            self.window.clipboard_clear()
            self.window.clipboard_append(text)
            self.copy_button.configure_state(text="Copied")
            self.window.after(1200, lambda: self.copy_button.configure_state(text="Copy"))

    def dialog(self, title, geometry="620x400"):
        dialog = tk.Toplevel(self.window, bg=BG)
        dialog.terminal_theme, dialog.terminal_font_family = self.theme, FONT_FAMILY
        dialog.terminal_buttons = self.window.terminal_buttons
        dialog.title(title)
        dialog.geometry(geometry)
        dialog.transient(self.window)
        dialog.minsize(480, 260)
        dialog.update_idletasks()
        dialog.geometry(f"+{self.window.winfo_rootx()+100}+{self.window.winfo_rooty()+90}")
        dialog.after(80, lambda: native_frame(dialog))
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        return dialog

    def choose_item(self, identifier, event):
        dialog = self.dialog(event.get("text", "Choose an item"), "720x420")
        self.label(dialog, event.get("text", "Choose an item"), GREEN, 15, True).pack(anchor="w", padx=23, pady=20)
        items = event.get("items", [])
        box = tk.Listbox(dialog, bg=FIELD, fg=TEXT, selectbackground=PALETTE["selection"], selectforeground=BRIGHT,
                          font=(FONT_FAMILY, 11), bd=0, highlightthickness=1, highlightbackground=EDGE, activestyle="none")
        box.pack(fill="both", expand=True, padx=23, pady=(0, 15))
        for item in items:
            box.insert("end", (item.get("date", "") + "  " if item.get("date") else "") + item.get("label", item["id"]))
        if not items:
            box.insert("end", "No saved conversations yet.")
        def choose():
            selected = box.curselection()
            if selected and items:
                self.select_module(identifier)
                if event["kind"] == "session_list":
                    self.submit("resume", session=items[selected[0]]["id"])
                else:
                    self.submit("modules", items[selected[0]]["id"])
                dialog.destroy()
        NeonButton(dialog, "Open selected", choose, width=150, primary=True).pack(anchor="e", padx=23, pady=(0, 17))
        box.bind("<Double-Button-1>", lambda e: choose())
        box.bind("<Return>", lambda e: choose())

    def show_logs(self):
        if not self.current:
            return
        dialog = self.dialog(self.modules[self.current].name + " — Logs", "850x470")
        self.label(dialog, "TERMINAL LOGS", GREEN, 15, True).pack(anchor="w", padx=22, pady=17)
        text = tk.Text(dialog, bg=FIELD, fg=MUTED, font=(FONT_FAMILY, 10), bd=0, padx=14, pady=12, wrap="word")
        text.pack(fill="both", expand=True, padx=22, pady=(0, 22))
        text.insert("1.0", "\n".join(self.workspace()["logs"]) or "No diagnostics have been emitted by this terminal.")
        text.configure(state="disabled")

    def load_dialog(self):
        dialog = self.dialog("Load a terminal", "620x325")
        self.label(dialog, "ADD A TERMINAL", GREEN, 17, True).pack(anchor="w", padx=25, pady=(25, 10))
        self.label(dialog, "Load a module with its own tools and settings,\nor link a terminal program you already have.", TEXT, 11, justify="left").pack(anchor="w", padx=25, pady=(0, 22))
        def load():
            path = filedialog.askopenfilename(parent=dialog, title="Choose a terminal module", filetypes=[("Terminal module", "*.json")], initialdir=self.root / "terminals")
            if path:
                try:
                    self.register(path)
                    dialog.destroy()
                except (OSError, ValueError, TypeError) as exc:
                    messagebox.showerror("Cannot load terminal", str(exc), parent=dialog)
        NeonButton(dialog, "Load a module…", load, width=260, height=42, primary=True).pack(anchor="w", padx=25, pady=(0, 10))
        NeonButton(dialog, "Link an existing terminal…", lambda: (dialog.destroy(), self.link_dialog()), width=260, height=42).pack(anchor="w", padx=25)
        self.label(dialog, "Loading registers a module. It starts when you connect or send.", MUTED, 9).pack(anchor="w", padx=25, pady=20)

    def register(self, path):
        module = TerminalModule.load(path)
        if module.id in self.modules and self.modules[module.id].path != module.path:
            raise ValueError("A different module already uses that terminal id. Keep ids unique.")
        self.modules[module.id] = module
        self.preferences["hidden_modules"] = [i for i in self.preferences["hidden_modules"] if i != module.id]
        self.preferences["module_order"] = list(self.modules)
        if str(module.path) not in self.preferences["modules"]:
            self.preferences["modules"].append(str(module.path))
        self.draw_modules()
        self.select_module(module.id)
        return module

    def entry_row(self, parent, label, variable, browse=None):
        self.label(parent, label, MUTED, 10).pack(anchor="w", pady=(11, 5))
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x")
        entry = tk.Entry(row, textvariable=variable, bg=FIELD, fg=TEXT, insertbackground=GREEN,
                         relief="flat", highlightthickness=1, highlightbackground=EDGE, highlightcolor=GREEN, font=(FONT_FAMILY, 11))
        entry.pack(side="left", fill="x", expand=True, ipady=8)
        if browse:
            NeonButton(row, "Browse", browse, width=83, height=34, small=True).pack(side="right", padx=(8, 0))
        return entry

    def link_dialog(self):
        dialog = self.dialog("Link an existing terminal", "690x500")
        body = tk.Frame(dialog, bg=BG, padx=25, pady=15)
        body.pack(fill="both", expand=True)
        self.label(body, "LINK A TERMINAL", GREEN, 16, True).pack(anchor="w")
        name, program, arguments, folder = (tk.StringVar() for _ in range(4))
        self.entry_row(body, "Terminal name", name)
        def choose_program():
            path = filedialog.askopenfilename(parent=dialog, title="Choose a terminal program", filetypes=[("Terminal program", "*.exe *.py *.cmd *.bat"), ("All files", "*.*")])
            if path:
                program.set(path)
                folder.set(str(Path(path).parent))
                if not name.get():
                    name.set(Path(path).stem)
        self.entry_row(body, "Program or Python script", program, choose_program)
        self.entry_row(body, "Arguments (optional; quote paths containing spaces)", arguments)
        self.entry_row(body, "Working folder", folder, lambda: folder.set(filedialog.askdirectory(parent=dialog) or folder.get()))
        self.label(body, "Uses a plain-text terminal adapter. Module packages can add richer controls.", MUTED, 9, wraplength=620, justify="left").pack(anchor="w", pady=18)
        def save_link():
            try:
                if not name.get().strip() or not Path(program.get()).is_file():
                    raise ValueError("Provide a name and an existing program")
                argv = [x[1:-1] if len(x)>1 and x[0]==x[-1] and x[0] in "\"'" else x for x in shlex.split(arguments.get(), posix=False)]
                command = [program.get(), *argv]
                if Path(program.get()).suffix.lower() == ".py":
                    command = ["{python}", "-u", *command]
                identifier = "linked-" + uuid.uuid4().hex[:12]
                data = {"schema": "logos-terminal/1", "id": identifier, "name": name.get().strip(), "version": "1.0.0", "api_version": API_VERSION,
                    "min_host_version": HOST_VERSION, "description": "Linked terminal · plain text", "protocol": "text", "command": command,
                    "cwd": folder.get() or str(Path(program.get()).parent), "actions": [{"id": "input", "label": "Terminal", "placeholder": "Type input for this terminal…", "button": "Send"}]}
                path = self.root / "state/linked-terminals" / (identifier + ".json")
                write_preferences(path, data)
                self.register(path)
                dialog.destroy()
            except (OSError, ValueError) as exc:
                messagebox.showerror("Cannot link terminal", str(exc), parent=dialog)
        NeonButton(body, "Add terminal", save_link, width=150, primary=True).pack(anchor="e")

    def settings(self):
        self.theme_catalog.reload()
        dialog = self.dialog("Workspace settings", "700x535")
        body = tk.Frame(dialog, bg=BG, padx=25, pady=22)
        body.pack(fill="both", expand=True)
        self.label(body, "WORKSPACE SETTINGS", GREEN, 16, True).pack(anchor="w", pady=(0, 14))
        self.label(body, "Theme", MUTED, 10).pack(anchor="w", pady=(2, 6))
        theme_choice = tk.StringVar()
        themes = {}
        choice = ttk.Combobox(body, textvariable=theme_choice, state="readonly", font=(FONT_FAMILY, 11))
        choice.pack(fill="x")
        description = self.label(body, "", MUTED, 10, wraplength=640, justify="left", anchor="w", height=3)
        description.pack(fill="x", pady=(5, 0))
        def refresh_themes(selected):
            themes.clear()
            for theme in sorted(self.theme_catalog.themes.values(), key=lambda t: (t.id != "logos-classic", t.name.casefold())):
                themes[f"{theme.name}  [{theme.id}]"] = theme
            choice.configure(values=list(themes))
            theme_choice.set(next(label for label, theme in themes.items() if theme.id == selected))
            describe()
        def describe(event=None):
            description.configure(text=themes[theme_choice.get()].data["description"])
            rain_button.configure_state(enabled=bool(themes[theme_choice.get()].rain))
        choice.bind("<<ComboboxSelected>>", describe)
        def import_theme():
            path = filedialog.askopenfilename(parent=dialog, title="Import a theme definition", filetypes=[("Theme definition", "*.json")])
            if path:
                try:
                    imported = self.theme_catalog.import_file(path)
                    refresh_themes(imported.id)
                except (OSError, ValueError, TypeError) as exc:
                    messagebox.showerror("Cannot import theme", str(exc), parent=dialog)
        tools = tk.Frame(body, bg=BG)
        tools.pack(fill="x", pady=(5, 13))
        NeonButton(tools, "Theme elements", lambda: self.inspect_theme(themes[theme_choice.get()]), width=156, small=True).pack(side="left")
        NeonButton(tools, "Import theme", import_theme, width=140, small=True).pack(side="left", padx=8)
        NeonButton(tools, "Export theme", lambda: self.export_theme(themes[theme_choice.get()], dialog), width=140, small=True).pack(side="left")
        rain_button = NeonButton(tools, "Rain settings", lambda: self.rain_settings(themes[theme_choice.get()],
            lambda saved: refresh_themes(saved.id)), width=140, small=True)
        rain_button.pack(side="left", padx=(8, 0))
        refresh_themes(self.theme_catalog.selected(self.theme.id).id)
        effects = tk.BooleanVar(value=self.preferences["effects"])
        tk.Checkbutton(body, text="Enable this theme's animated effects", variable=effects, bg=BG, fg=TEXT, activebackground=BG, activeforeground=GREEN,
                       selectcolor=FIELD, font=(FONT_FAMILY, 11)).pack(anchor="w", pady=(0, 7))
        self.label(body, "Animations pause when the app is inactive. Hover feedback stays available.", MUTED, 9).pack(anchor="w")
        size = tk.StringVar(value=str(self.preferences["font_size"]))
        self.entry_row(body, "Reading font size (10–18)", size)
        row = tk.Frame(body, bg=BG)
        row.pack(fill="x", pady=(23, 0))
        NeonButton(row, "Terminal Manager", self.terminal_manager, width=175).pack(side="left", padx=(0, 8))
        if self.current and self.modules[self.current].settings.get("fields"):
            NeonButton(row, "Terminal settings…", lambda: self.module_settings(), width=185).pack(side="left")
        def apply():
            try:
                value = int(size.get())
                if not 10 <= value <= 18:
                    raise ValueError("Choose a font size from 10 to 18")
                self.preferences.update(effects=effects.get(), font_size=value, theme=themes[theme_choice.get()].id)
                dialog.destroy()
                self.apply_theme(self.preferences["theme"])
            except ValueError as exc:
                messagebox.showerror("Check settings", str(exc), parent=dialog)
        NeonButton(row, "Apply", apply, width=110, primary=True).pack(side="right")

    def rain_settings(self, theme, on_saved):
        if not theme.rain:
            return
        dialog = self.dialog(theme.name+" - Rain settings", "760x620")
        self.label(dialog, "RAIN SETTINGS", GREEN, 16, True).pack(anchor="w", padx=24, pady=(20, 8))
        self.label(dialog, "Save a personal theme, then choose Apply in Settings to use it.", MUTED, 10).pack(anchor="w", padx=24)
        fields = tk.Frame(dialog, bg=BG)
        fields.pack(fill="both", expand=True, padx=24, pady=18)
        fields.columnconfigure(0, weight=1)
        fields.columnconfigure(1, weight=1)
        labels = {"column_spacing": "Column spacing (pixels)", "row_spacing": "Row spacing (pixels)",
                  "fall_speed": "Fall speed (pixels/second)", "morph_rate": "Symbol changes per second",
                  "brightness": "Character brightness", "content_brightness": "Rain behind text (brightness)", "glow_radius": "Soft glow radius (pixels)",
                  "glow_strength": "Soft glow strength", "trail_seconds": "After-image fade (seconds)",
                  "frame_rate": "Animation frames per second"}
        values = {}
        for index, (key, (low, high)) in enumerate({**RAIN_LIMITS, "frame_rate": (4, 30)}.items()):
            cell = tk.Frame(fields, bg=BG)
            cell.grid(row=index//2, column=index % 2, sticky="ew", padx=(0, 18), pady=(0, 14))
            self.label(cell, labels[key], MUTED, 10).pack(anchor="w", pady=(0, 6))
            variable = tk.StringVar(value=str(theme.effects[key] if key == "frame_rate" else theme.rain[key]))
            values[key] = variable
            step = .05 if key in {"brightness", "content_brightness", "glow_strength", "trail_seconds"} else 1
            tk.Spinbox(cell, from_=low, to=high, increment=step, textvariable=variable, bg=FIELD, fg=TEXT,
                       buttonbackground=EDGE, insertbackground=GREEN, font=(FONT_FAMILY, 11),
                       highlightthickness=1, highlightbackground=EDGE, relief="flat", width=22).pack(fill="x", ipady=6)
        bottom = tk.Frame(dialog, bg=BG)
        bottom.pack(fill="x", padx=24, pady=(0, 20))
        def save():
            try:
                changed = {key: int(values[key].get()) if key == "glow_radius" else float(values[key].get()) for key in RAIN_LIMITS}
                saved = self.theme_catalog.customize_rain(theme, changed, frame_rate=int(values["frame_rate"].get()))
                on_saved(saved)
                dialog.destroy()
            except (OSError, ValueError, TypeError) as exc:
                messagebox.showerror("Check rain settings", str(exc), parent=dialog)
        NeonButton(bottom, "Save custom theme", save, width=196, primary=True).pack(side="right")
        return dialog

    def export_theme(self, theme, parent=None):
        path = filedialog.asksaveasfilename(parent=parent or self.window, title="Export theme definition",
            initialfile=theme.id+".theme.json", defaultextension=".json", filetypes=[("Theme definition", "*.json")])
        if path:
            try:
                Path(path).write_text(theme.to_json(), encoding="utf-8")
            except OSError as exc:
                messagebox.showerror("Cannot export theme", str(exc), parent=parent or self.window)

    def inspect_theme(self, theme):
        dialog = self.dialog(theme.name + " - Theme elements", "820x615")
        self.label(dialog, theme.name.upper(), GREEN, 16, True).pack(anchor="w", padx=22, pady=(20, 7))
        self.label(dialog, "Versioned, data-only elements. Export a definition to create another theme.", MUTED, 10).pack(anchor="w", padx=22)
        row = tk.Frame(dialog, bg=BG)
        row.pack(fill="x", padx=22, pady=13)
        group = tk.StringVar(value="All elements")
        options = {"All elements": None, "Palette": "palette", "Typography": "typography", "Components": "components", "Effects": "effects", "Rain": "rain", "Flat tokens": "tokens"}
        selector = ttk.Combobox(row, textvariable=group, values=list(options), state="readonly", width=22, font=(FONT_FAMILY, 10))
        selector.pack(side="left")
        text = tk.Text(dialog, bg=FIELD, fg=TEXT, font=(FONT_FAMILY, 11), wrap="word", bd=0, padx=12, pady=12)
        text.pack(fill="both", expand=True, padx=22)
        def render(event=None):
            selected = options[group.get()]
            data = theme.tokens() if selected == "tokens" else theme.elements(selected)
            text.configure(state="normal")
            text.delete("1.0", "end")
            text.insert("1.0", json.dumps(data, indent=2))
            text.configure(state="disabled")
        selector.bind("<<ComboboxSelected>>", render)
        render()
        bottom = tk.Frame(dialog, bg=BG)
        bottom.pack(fill="x", padx=22, pady=14)
        def copy():
            dialog.clipboard_clear()
            dialog.clipboard_append(text.get("1.0", "end-1c"))
        NeonButton(bottom, "Copy elements", copy, width=150, small=True).pack(side="left")
        NeonButton(bottom, "Export theme", lambda: self.export_theme(theme, dialog), width=150, small=True).pack(side="right")
        text.pack_forget()
        bottom.pack_forget()
        bottom.pack(side="bottom", fill="x", padx=22, pady=14)
        text.pack(fill="both", expand=True, padx=22)

    def apply_theme(self, identifier):
        """Rebuild only the view, retaining the existing host/module state."""
        selected = self.current
        scroll = self.transcript.yview()[0]
        translation = self.translation.get()
        if selected:
            self.workspace()["input"] = self.input_text()
        for view in self.calculator_views.values():
            view.snapshot()
        self.calculator_views = {}
        self.current = None
        self.atmosphere = None
        self.outer.destroy()
        self.panels, self.module_buttons, self.action_buttons = [], {}, {}
        self.theme = self.theme_catalog.selected(identifier)
        self.preferences["theme"] = self.theme.id
        activate_palette(self.theme, self.window)
        self.window.configure(bg=BG)
        self.body_font.configure(family=FONT_FAMILY, size=self.preferences["font_size"])
        self.bold_font.configure(family=FONT_FAMILY, size=self.preferences["font_size"])
        self.configure_style()
        self.build_layout()
        self.draw_modules()
        if selected in self.modules:
            self.select_module(selected)
            if translation in self.translation_box.cget("values"):
                self.translation.set(translation)
        else:
            self.empty_workspace()
        self.window.update_idletasks()
        self.transcript.yview("moveto", scroll)
        self.setup_atmosphere()
        native_frame(self.window)
        self.save()

    def setup_atmosphere(self):
        if self.theme.effects["digital_rain"] or self.theme.effects["scanlines"]:
            self.atmosphere = Atmosphere(self.window, self.theme)
            self.atmosphere.decorate(self.outer, skip=(self.module_list,))
            self.atmosphere.register(self.transcript.screen)
            self.atmosphere.register(self.module_canvas)
            self.window.after_idle(self.refresh_atmosphere)
        self.update_effect_label()

    def refresh_atmosphere(self):
        if self.closing or not self.atmosphere:
            return
        self.atmosphere.decorate(self.outer, skip=(self.module_list,))
        if self.preferences["effects"]:
            self.atmosphere.tick(0)

    def module_settings(self, identifier=None):
        module = self.modules[identifier or self.current]
        descriptor = module.settings
        if not descriptor.get("fields"):
            return
        path = module.settings_path(self.root)
        try:
            existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            if not isinstance(existing, dict):
                raise ValueError("Terminal settings must be a JSON object")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Cannot read terminal settings", str(exc), parent=self.window)
            return
        fields = descriptor.get("fields", [])
        dialog = self.dialog(module.name + " — Settings", f"760x{min(650, 190+len(fields)*74)}")
        body = tk.Frame(dialog, bg=BG, padx=25, pady=20)
        body.pack(fill="both", expand=True)
        self.label(body, module.name.upper() + " SETTINGS", GREEN, 16, True).pack(anchor="w")
        values = {}
        for field in fields:
            var = tk.StringVar(value=str(existing.get(field["key"], "")))
            values[field["key"]] = var
            self.entry_row(body, field["label"], var, (lambda v=var: v.set(filedialog.askopenfilename(parent=dialog) or v.get())) if field.get("type") == "file" else None)
        self.label(body, "Saved changes apply the next time this terminal connects.", MUTED, 10).pack(anchor="w", pady=17)
        def apply():
            try:
                changed = dict(existing)
                for field in fields:
                    text = values[field["key"]].get().strip()
                    if not text:
                        changed.pop(field["key"], None)
                        continue
                    value = int(text) if field.get("type") == "integer" else float(text) if field.get("type") == "number" else text
                    if isinstance(value, (int, float)) and (not math.isfinite(value) or value < field.get("min", -math.inf) or value > field.get("max", math.inf)):
                        raise ValueError("Check the range for " + field["label"])
                    if field.get("type") == "file" and not Path(value).is_file():
                        raise ValueError("Choose an existing file for " + field["label"])
                    changed[field["key"]] = value
                write_preferences(path, changed)
                dialog.destroy()
            except (OSError, ValueError) as exc:
                messagebox.showerror("Cannot save terminal settings", str(exc), parent=dialog)
        NeonButton(body, "Save settings", apply, width=160, primary=True).pack(anchor="e")

    def toggle_effects(self):
        self.preferences["effects"] = not self.preferences["effects"]
        self.update_effect_label()
        self.save()

    def update_effect_label(self):
        self.effects_button.configure_state(text="◈ Effects on" if self.preferences["effects"] else "◇ Effects off")
        self.transcript.set_effects(self.preferences["effects"] and self.theme.effects["text_glow"])
        self.input.configure(insertofftime=500 if self.preferences["effects"] else 0)
        if self.atmosphere:
            self.atmosphere.set_enabled(self.preferences["effects"])
        if not self.preferences["effects"]:
            for panel in self.panels:
                panel.configure(highlightbackground=EDGE)
            self.brand.configure(fg=GREEN)
            native_frame(self.window, EDGE)
            for button in self.window.terminal_buttons:
                if button.winfo_exists():
                    button.set_pulse(0)

    def animate(self):
        if self.closing:
            return
        active = self.window.state() != "iconic" and self.window.focus_displayof() is not None
        now = time.monotonic()
        enabled = self.preferences["effects"] and active
        if enabled:
            self.metrics["animation_ticks"] += 1
            phase = (math.sin(now * 1.2) + 1) / 2
            if self.theme.effects["pulse"] and (not self.theme.rain or now-self.last_lighting >= .125):
                self.last_lighting = now
                color = mix(EDGE, PALETTE["border_glow"], .15 + phase*.3)
                for panel in self.panels:
                    panel.configure(highlightbackground=color)
                self.brand.configure(fg=mix(PALETTE["brand"], BRIGHT, phase*.45))
                self.window.terminal_buttons[:] = [b for b in self.window.terminal_buttons if b.winfo_exists()]
                for button in self.window.terminal_buttons:
                    button.set_pulse(phase)
                if now-self.last_native_border >= .4:
                    self.last_native_border = now
                    native_frame(self.window, color)
            if self.atmosphere:
                self.atmosphere.tick(now-self.last_animation if self.animation_was_active else 0)
        self.transcript.pulse_cursor(now, enabled and self.theme.effects["block_cursor"])
        self.last_animation = now
        self.animation_was_active = enabled
        interval = 1000/self.theme.effects["frame_rate"]
        if enabled and self.theme.rain:
            # Account for rendering time instead of adding it to every interval.
            interval = max(1, interval-(time.monotonic()-now)*1000)
        self.window.after(round(interval) if enabled else 500, self.animate)

    def save(self):
        try:
            write_preferences(self.preference_path, self.preferences)
        except OSError as exc:
            self.footer.configure(text="Preferences could not be saved: " + str(exc))

    def close(self):
        if self.closing:
            return
        self.closing = True
        self.save()
        # Stop only workers owned by this host; no unrelated terminal is touched.
        processes = list(self.processes.values()) + list(self.stopping_processes.values())
        self.window.withdraw()
        def finish():
            for process in processes:
                try:
                    process.stop()
                except Exception:
                    pass
            self.events.put(("__host__", "close", {}))
        threading.Thread(target=finish, daemon=False).start()
        def check():
            if all(not p.process or p.process.poll() is not None for p in processes):
                self.window.destroy()
            else:
                self.window.after(100, check)
        check()


def main():
    if os.name == "nt":
        import ctypes
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Logos.Terminal.GUI")
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    TerminalGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
