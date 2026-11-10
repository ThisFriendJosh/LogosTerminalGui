"""Terminal management and diagnostic preview, separate from the main workspace."""
from datetime import datetime
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from terminal_diagnostics import build_report, local_details, write_report


class TerminalManager:
    def __init__(self, host, button, colors):
        self.host, self.button, self.colors = host, button, colors
        self.dialog = host.dialog("Terminal Manager", "1000x650")
        self.dialog.minsize(860, 570)
        self.last_details = None
        self.job = None
        self.buttons = {}
        body = tk.Frame(self.dialog, bg=colors["bg"], padx=22, pady=18)
        body.pack(fill="both", expand=True)
        heading = tk.Frame(body, bg=colors["bg"])
        heading.pack(fill="x", pady=(0, 10))
        host.label(heading, "TERMINAL MANAGER", colors["green"], 17, True).pack(side="left")
        button(heading, "Load terminal", host.load_dialog, width=145, small=True).pack(side="right")
        host.label(body, "Select a terminal to inspect its setup, check the connection, or manage its place in the sidebar.",
                   colors["muted"], 10, anchor="w").pack(fill="x", pady=(0, 12))
        style = ttk.Style(self.dialog)
        style.configure("TerminalManager.Treeview", background=colors["field"], fieldbackground=colors["field"],
                        foreground=colors["text"], rowheight=29, borderwidth=0, font=(colors["font"], 10))
        style.configure("TerminalManager.Treeview.Heading", background=colors["bg"], foreground=colors["green"],
                        font=(colors["font"], 10, "bold"))
        style.map("TerminalManager.Treeview", background=[("selected", colors["selection"])], foreground=[("selected", colors["green"])])
        listing = tk.Frame(body, bg=colors["bg"])
        listing.pack(fill="x")
        self.tree = ttk.Treeview(listing, columns=("version", "status", "protocol", "check"), show="tree headings",
                                 selectmode="browse", height=5, style="TerminalManager.Treeview")
        for key, label, width in (("#0", "Terminal", 230), ("version", "Version", 85), ("status", "Connection", 160),
                                  ("protocol", "Protocol", 95), ("check", "Last check", 120)):
            self.tree.heading(key, text=label, anchor="w")
            self.tree.column(key, width=width, minwidth=60, stretch=key in {"#0", "status"})
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="x", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda event: self.refresh_details())
        self.tree.bind("<Double-Button-1>", lambda event: self.invoke("open"))
        host.label(body, "SELECTED TERMINAL", colors["muted"], 9, True).pack(anchor="w", pady=(13, 5))
        details_frame = tk.Frame(body, bg=colors["bg"])
        details_frame.pack(fill="both", expand=True)
        self.details = tk.Text(details_frame, bg=colors["field"], fg=colors["text"], font=(colors["font"], 10),
                               height=8, bd=0, padx=12, pady=10, wrap="word", state="disabled")
        detail_scroll = ttk.Scrollbar(details_frame, orient="vertical", command=self.details.yview)
        detail_scroll.pack(side="right", fill="y")
        self.details.configure(yscrollcommand=detail_scroll.set)
        self.details.pack(fill="both", expand=True)
        controls = tk.Frame(body, bg=colors["bg"])
        controls.pack(fill="x", pady=(12, 8))
        for index, (key, label, action) in enumerate((
            ("open", "Open workspace", self.open_workspace), ("test", "Test connection", host.test_connection),
            ("reconnect", "Reconnect", host.reconnect_module), ("settings", "Settings", host.module_settings),
            ("validate", "Validate files", host.validate_module), ("up", "Move up", lambda i: host.move_module(i, -1)),
            ("down", "Move down", lambda i: host.move_module(i, 1)), ("unload", "Unload", host.unload_module),
            ("report", "Export report", lambda i: self.report_dialog()))):
            control = button(controls, label, lambda a=action: self.run(a), width=166, small=True, primary=key == "test")
            control.grid(row=index//5, column=index % 5, sticky="ew", padx=(0, 8), pady=(0, 7))
            controls.columnconfigure(index % 5, weight=1)
            self.buttons[key] = control
        note = host.label(body, "Test starts a disconnected terminal and checks startup; it sends no command.\n"
                   "Unload removes the sidebar entry and stops its worker. Files, settings and saved conversations remain.",
                   colors["muted"], 9, justify="left", anchor="w", wraplength=920)
        note.pack(side="bottom", fill="x")
        # Reserve actions before the flexible detail panel on compact displays.
        details_frame.pack_forget()
        controls.pack_forget()
        controls.pack(side="bottom", fill="x", pady=(12, 8))
        details_frame.pack(fill="both", expand=True)
        self.dialog.bind("<Destroy>", self.destroyed, add=True)
        self.refresh()

    def selected(self):
        selection = self.tree.selection()
        return selection[0] if selection and selection[0] in self.host.modules else None

    def refresh(self):
        if not self.dialog.winfo_exists() or self.host.closing:
            return
        for identifier in self.tree.get_children():
            if identifier not in self.host.modules:
                self.tree.delete(identifier)
        for index, (identifier, module) in enumerate(self.host.modules.items()):
            state = self.host.workspace(identifier)
            process = self.host.processes.get(identifier)
            status = "Reconnecting" if identifier in self.host.reconnecting else "Busy" if state["busy"] else "Connected" if state["ready"] else "Connecting" if process else "Disconnected"
            if state.get("connection_error") or (process and process.metadata.get("model_available") is False):
                status = "Needs setup"
            checked = self.host.connection_checks.get(identifier, {}).get("status", "Not run")
            values = (module.version, status, module.protocol, checked.capitalize())
            if self.tree.exists(identifier):
                self.tree.item(identifier, text=module.name, values=values)
                self.tree.move(identifier, "", index)
            else:
                self.tree.insert("", index, iid=identifier, text=module.name, values=values)
        if not self.selected() and self.host.modules:
            identifier = self.host.current if self.host.current in self.host.modules else next(iter(self.host.modules))
            self.tree.selection_set(identifier)
        self.refresh_details()
        self.job = self.dialog.after(350, self.refresh)

    def refresh_details(self):
        identifier = self.selected()
        host = self.host
        state = host.workspace(identifier) if identifier else {}
        record = host.connection_checks.get(identifier)
        content = local_details(host.modules[identifier], host.root, host.processes.get(identifier), state, record) if identifier else "No terminals loaded. Use Load terminal to add one."
        if content != self.last_details:
            self.details.configure(state="normal")
            self.details.delete("1.0", "end")
            self.details.insert("1.0", content)
            self.details.configure(state="disabled")
            self.last_details = content
        order = list(host.modules)
        starting = bool(identifier and identifier in host.processes and not state.get("ready"))
        changing = identifier in host.reconnecting or starting or (record and record["status"] == "checking")
        for key, control in self.buttons.items():
            enabled = bool(identifier)
            if key in {"validate", "test"}:
                enabled = enabled and not changing
            elif key in {"reconnect", "unload"}:
                enabled = enabled and not state.get("busy") and not changing
            elif key == "settings":
                enabled = enabled and bool(host.modules[identifier].settings.get("fields"))
            elif key == "up":
                enabled = enabled and order.index(identifier) > 0
            elif key == "down":
                enabled = enabled and order.index(identifier) < len(order)-1
            elif key == "report":
                enabled = True
            control.configure_state(enabled=enabled)

    def invoke(self, key):
        self.buttons[key].invoke()

    def run(self, action):
        identifier = self.selected()
        try:
            action(identifier)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            messagebox.showerror("Terminal Manager", str(exc), parent=self.dialog)
        self.refresh_details()

    def open_workspace(self, identifier):
        self.host.select_module(identifier)
        self.dialog.destroy()

    def destroyed(self, event):
        if event.widget is self.dialog and self.job:
            self.dialog.after_cancel(self.job)
            self.job = None

    def report_dialog(self):
        host, colors = self.host, self.colors
        dialog = host.dialog("Review diagnostic report", "940x620")
        dialog.minsize(720, 480)
        host.label(dialog, "REVIEW DIAGNOSTIC REPORT", colors["green"], 16, True).pack(anchor="w", padx=22, pady=(18, 9))
        host.label(dialog, "Default report: versions, connection states and check results. No conversations, drafts or settings values.\n"
                   "Review any included diagnostic text before sharing the saved file.", colors["muted"], 10,
                   justify="left", wraplength=875, anchor="w").pack(fill="x", padx=22)
        include = tk.BooleanVar(value=False)
        preview_frame = tk.Frame(dialog, bg=colors["bg"])
        preview = tk.Text(preview_frame, bg=colors["field"], fg=colors["text"], font=(colors["font"], 10),
                          wrap="word", bd=0, padx=12, pady=12)
        scroll = ttk.Scrollbar(preview_frame, orient="vertical", command=preview.yview)
        scroll.pack(side="right", fill="y")
        preview.configure(yscrollcommand=scroll.set)
        preview.pack(fill="both", expand=True)
        report = {}
        def update_preview():
            report.clear()
            report.update(build_report(host.modules, host.root, host.processes, host.workspaces, host.connection_checks,
                          selected=self.selected(), include_details=include.get(), tk_version=host.window.tk.call("info", "patchlevel")))
            preview.configure(state="normal")
            preview.delete("1.0", "end")
            preview.insert("1.0", json.dumps(report, ensure_ascii=False, indent=2))
            preview.configure(state="disabled")
        tk.Checkbutton(dialog, text="Include recent diagnostics (paths and common credentials redacted; review other text)",
                       variable=include, command=update_preview, bg=colors["bg"], fg=colors["text"], activebackground=colors["bg"],
                       activeforeground=colors["green"], selectcolor=colors["field"], font=(colors["font"], 10)).pack(anchor="w", padx=22, pady=12)
        bottom = tk.Frame(dialog, bg=colors["bg"])
        bottom.pack(side="bottom", fill="x", padx=22, pady=16)
        preview_frame.pack(fill="both", expand=True, padx=22)
        notice = host.label(bottom, "Nothing is uploaded automatically.", colors["muted"], 9)
        notice.pack(side="left")
        def export():
            path = filedialog.asksaveasfilename(parent=dialog, title="Save diagnostic report", defaultextension=".json",
                initialfile="logos-terminal-diagnostics-"+datetime.now().strftime("%Y%m%d-%H%M%S")+".json", filetypes=[("Diagnostic report", "*.json")])
            if not path:
                return
            try:
                write_report(path, report)
                notice.configure(text="Diagnostic report saved.")
            except (OSError, ValueError) as exc:
                messagebox.showerror("Cannot save diagnostic report", str(exc), parent=dialog)
        self.button(bottom, "Save report", export, width=150, primary=True).pack(side="right")
        update_preview()
        # Exposed widget references also let display tests exercise the reviewed export.
        dialog.report_preview, dialog.report_include = preview, include
        return dialog
