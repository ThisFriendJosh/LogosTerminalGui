"""Native visual calculator workspaces. Calculation stays in module processes."""
import csv
from datetime import datetime, timezone
import io
import json
import math
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk


def workspace_engine(module):
    extension = module.extensions.get("workspace", {})
    if isinstance(extension, dict) and extension.get("type") == "calculator":
        engine = extension.get("engine")
        if engine in {"cryptocalc", "statcalc"}:
            return engine
    return None


def number(value):
    if value is None:
        return "-"
    return f"{value:.8g}" if isinstance(value, (int, float)) else str(value)


class CalculatorWorkspace(tk.Frame):
    def __init__(self, parent, host, identifier, palette):
        self.host, self.identifier, self.p = host, identifier, palette
        self.engine = workspace_engine(host.modules[identifier])
        self.data = host.workspace(identifier).setdefault("calculator", {})
        self.family = host.window.terminal_font_family
        super().__init__(parent, bg=palette["background"])
        self.dirty = self.data.get("dirty", False)
        self.result = self.data.get("result", {})
        self.busy = None
        style = ttk.Style(self)
        style.configure("Calculator.TEntry", fieldbackground=palette["field"], foreground=palette["text"],
                        insertcolor=palette["accent"], bordercolor=palette["edge"], lightcolor=palette["edge"],
                        darkcolor=palette["edge"], padding=4)
        style.map("Calculator.TEntry", fieldbackground=[("!disabled", palette["field"])], foreground=[("!disabled", palette["text"])])
        for orientation in ("Vertical", "Horizontal"):
            style.configure(f"Calculator.{orientation}.TScrollbar", background=palette["edge"],
                            troughcolor=palette["field"], arrowcolor=palette["accent"],
                            bordercolor=palette["edge"], lightcolor=palette["edge"], darkcolor=palette["edge"])
        style.configure("Calculator.Treeview", background=palette["field"], fieldbackground=palette["field"],
                        foreground=palette["text"], rowheight=27, font=(self.family, 10),
                        bordercolor=palette["edge"], lightcolor=palette["edge"], darkcolor=palette["edge"])
        style.configure("Calculator.Treeview.Heading", background=palette["panel"], foreground=palette["accent"],
                        font=(self.family, 10, "bold"))
        style.map("Calculator.Treeview", background=[("selected", palette["selection"])],
                  foreground=[("selected", palette["selection_text"])])
        style.configure("Calculator.TNotebook", background=palette["background"], borderwidth=0,
                        bordercolor=palette["edge"], lightcolor=palette["edge"], darkcolor=palette["edge"])
        style.configure("Calculator.TNotebook.Tab", background=palette["panel"], foreground=palette["text"], padding=(12, 8),
                        bordercolor=palette["edge"], lightcolor=palette["edge"], darkcolor=palette["edge"])
        style.map("Calculator.TNotebook.Tab", background=[("selected", palette["field"])], foreground=[("selected", palette["accent_bright"])])
        controls = self.frame(self)
        controls.pack(fill="x", pady=(0, 9))
        self.run_button = self.button(controls, "Run recipe" if self.engine == "cryptocalc" else "Analyze data", self.run, primary=True)
        self.run_button.pack(side="left")
        if self.engine == "statcalc":
            self.label(controls, "Confidence %").pack(side="left", padx=(14, 5))
            self.confidence = tk.StringVar(value=self.data.get("confidence", "95"))
            tk.Spinbox(controls, from_=50, to=99.99, increment=1, width=6, textvariable=self.confidence,
                       bg=palette["field"], fg=palette["text"], insertbackground=palette["accent"],
                       buttonbackground=palette["panel"], font=(self.family, 10)).pack(side="left")
            self.confidence.trace_add("write", lambda *_: self.changed())
        self.button(controls, "Full HTML app", lambda: self.send("open")).pack(side="right")
        self.button(controls, "Copy result", self.copy_result).pack(side="right", padx=6)
        self.status = self.label(self, "Build a recipe and run it." if self.engine == "cryptocalc" else "Enter or import data, then Analyze.")
        self.status.pack(side="bottom", fill="x", pady=(7, 0))
        if self.engine == "cryptocalc":
            self.build_crypto()
        else:
            self.build_stats()
        if self.result:
            self.receive({"audit": {"calculator": self.result}})
        if self.engine == "statcalc":
            self.tabs.select(self.data.get("tab", 0))
            if self.data.get("chart_column"):
                self.chart_column.set(self.data["chart_column"])
                self.draw_chart()
        else:
            self.output_tabs.select(self.data.get("output_tab", 0))
        self.set_busy(False)

    def frame(self, parent, card=False):
        return tk.Frame(parent, bg=self.p["panel"] if card else self.p["background"],
                        highlightthickness=1 if card else 0, highlightbackground=self.p["edge"])

    def label(self, parent, text, bold=False):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=self.p["text"], anchor="w",
                        font=(self.family, 10, "bold" if bold else "normal"))

    def button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, bg=self.p["button_fill"] if primary else self.p["panel"],
                         fg=self.p["accent_bright"] if primary else self.p["text"], activebackground=self.p["selection"],
                         activeforeground=self.p["selection_text"], relief="flat", bd=0, padx=9, pady=7,
                         highlightthickness=1, highlightbackground=self.p["edge"], font=(self.family, 10), cursor="hand2")

    def text(self, parent, height=5, readonly=False):
        area = tk.Frame(parent, bg=self.p["field"])
        area.pack(fill="both", expand=True, padx=7, pady=6)
        widget = tk.Text(area, height=height, width=15, wrap="word", bg=self.p["field"], fg=self.p["text"],
                         insertbackground=self.p["accent"], selectbackground=self.p["selection"],
                         bd=0, padx=9, pady=8, font=(self.family, 10), undo=not readonly)
        widget.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(area, command=widget.yview, style="Calculator.Vertical.TScrollbar")
        scroll.pack(side="right", fill="y")
        widget.configure(yscrollcommand=scroll.set, state="disabled" if readonly else "normal")
        return widget

    def table(self, parent, columns):
        area = self.frame(parent)
        area.pack(fill="both", expand=True, padx=7, pady=6)
        tree = ttk.Treeview(area, columns=[key for key, _ in columns], show="headings", style="Calculator.Treeview", height=5)
        for key, label in columns:
            tree.heading(key, text=label)
            tree.column(key, width=110, minwidth=65, stretch=True)
        tree.grid(row=0, column=0, sticky="nsew")
        sy = ttk.Scrollbar(area, command=tree.yview, style="Calculator.Vertical.TScrollbar")
        sy.grid(row=0, column=1, sticky="ns")
        sx = ttk.Scrollbar(area, orient="horizontal", command=tree.xview, style="Calculator.Horizontal.TScrollbar")
        sx.grid(row=1, column=0, sticky="ew")
        tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        area.rowconfigure(0, weight=1)
        area.columnconfigure(0, weight=1)
        return tree

    def notebook(self, parent, names):
        tabs = ttk.Notebook(parent, style="Calculator.TNotebook")
        tabs.pack(fill="both", expand=True)
        pages = {}
        for name in names:
            page = self.frame(tabs, card=True)
            tabs.add(page, text=name)
            pages[name] = page
        return tabs, pages

    def changed(self):
        self.dirty = True
        if hasattr(self, "status"):
            self.status.configure(text="Input changed. Run again to update the result.")

    def send(self, action, text=""):
        if self.host.current == self.identifier and not self.host.workspace(self.identifier)["busy"]:
            self.host.submit(action, text)

    def set_busy(self, busy):
        if self.busy and not busy and self.status.cget("text") == "Calculating locally...":
            self.status.configure(text=self.host.workspace(self.identifier)["status"])
        if self.busy != busy:
            self.run_button.configure(state="disabled" if busy else "normal")
            self.busy = busy
        if busy:
            self.status.configure(text="Calculating locally...")

    def error(self, message):
        self.status.configure(text=message, fg=self.p["error"])

    def build_crypto(self):
        try:
            catalog = json.loads((self.host.modules[self.identifier].path.parent / "operations.json").read_text(encoding="utf-8"))
            if not isinstance(catalog, list) or len(catalog) > 200:
                raise ValueError("Invalid operation catalogue")
            self.catalog = {item["id"]: item for item in catalog}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.catalog = {}
            self.error("Could not load visual operations: " + str(exc))
        self.recipe = self.data.get("recipe", [])
        self.selected_step = None
        self.parameter_vars = []
        panes = self.frame(self)
        panes.pack(fill="both", expand=True)
        for index, weight in enumerate([1, 1, 2]):
            panes.columnconfigure(index, weight=weight, uniform="crypto" if index < 2 else "output")
        panes.rowconfigure(0, weight=1)
        operations = self.frame(panes, card=True)
        operations.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        self.label(operations, "1 / OPERATIONS", True).pack(fill="x", padx=8, pady=8)
        self.search = tk.StringVar(value=self.data.get("search", ""))
        ttk.Entry(operations, textvariable=self.search, style="Calculator.TEntry").pack(fill="x", padx=7, pady=(0, 7))
        self.operation_list = tk.Listbox(operations, bg=self.p["field"], fg=self.p["text"], selectbackground=self.p["selection"],
                                        bd=0, width=18, exportselection=False, font=(self.family, 10), activestyle="none")
        self.operation_list.pack(fill="both", expand=True, padx=7)
        self.operation_list.bind("<Double-Button-1>", lambda _: self.add_operation())
        self.operation_list.bind("<<ListboxSelect>>", lambda _: self.operation_hint())
        self.hint = self.label(operations, "Search or select an operation.")
        self.hint.configure(wraplength=180, justify="left")
        self.hint.pack(fill="x", padx=8, pady=7)
        self.button(operations, "+ Add operation", self.add_operation).pack(fill="x", padx=7, pady=(0, 7))
        self.search.trace_add("write", lambda *_: self.filter_operations())
        self.filter_operations()
        recipe = self.frame(panes, card=True)
        recipe.grid(row=0, column=1, sticky="nsew", padx=(0, 7))
        self.label(recipe, "2 / RECIPE", True).pack(fill="x", padx=8, pady=8)
        self.recipe_list = tk.Listbox(recipe, bg=self.p["field"], fg=self.p["text"], selectbackground=self.p["selection"],
                                     exportselection=False, bd=0, width=18, height=5, font=(self.family, 10))
        self.recipe_list.pack(fill="x", padx=7)
        self.recipe_list.bind("<<ListboxSelect>>", lambda _: self.edit_step())
        move = self.frame(recipe)
        move.pack(fill="x", padx=7, pady=6)
        for label, command in [("Up", lambda: self.move_step(-1)), ("Down", lambda: self.move_step(1)), ("Remove", self.remove_step)]:
            self.button(move, label, command).pack(side="left", expand=True, fill="x")
        files = self.frame(recipe)
        files.pack(side="bottom", fill="x", padx=7, pady=7)
        self.button(files, "Save", self.save_recipe).pack(side="left", expand=True, fill="x")
        self.button(files, "Load", self.load_recipe).pack(side="left", expand=True, fill="x")
        self.params_canvas = tk.Canvas(recipe, bg=self.p["panel"], highlightthickness=0, width=130)
        self.params_canvas.pack(side="left", fill="both", expand=True, padx=(7, 0))
        param_scroll = ttk.Scrollbar(recipe, command=self.params_canvas.yview, style="Calculator.Vertical.TScrollbar")
        param_scroll.pack(side="right", fill="y")
        self.params_canvas.configure(yscrollcommand=param_scroll.set)
        self.params = self.frame(self.params_canvas)
        item = self.params_canvas.create_window(0, 0, anchor="nw", window=self.params)
        self.params.bind("<Configure>", lambda _: self.params_canvas.configure(scrollregion=self.params_canvas.bbox("all")))
        self.params_canvas.bind("<Configure>", lambda e: self.params_canvas.itemconfigure(item, width=e.width))
        right = self.frame(panes)
        right.grid(row=0, column=2, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        source = self.frame(right, card=True)
        source.grid(row=0, column=0, sticky="nsew", pady=(0, 7))
        bar = self.frame(source)
        bar.pack(fill="x", padx=7, pady=4)
        self.label(bar, "3 / INPUT", True).pack(side="left")
        self.button(bar, "Load file", self.load_crypto_file).pack(side="right")
        self.source = self.text(source)
        self.source.insert("1.0", self.data.get("input", ""))
        self.source.bind("<KeyRelease>", lambda _: self.changed())
        output = self.frame(right, card=True)
        output.grid(row=1, column=0, sticky="nsew")
        bar = self.frame(output)
        bar.pack(fill="x", padx=7, pady=4)
        self.label(bar, "4 / OUTPUT", True).pack(side="left")
        self.button(bar, "Save output", self.save_output).pack(side="right")
        self.output_tabs, pages = self.notebook(output, ["Text", "Hex", "Steps"])
        self.output_text = self.text(pages["Text"], readonly=True)
        self.output_hex = self.text(pages["Hex"], readonly=True)
        self.step_table = self.table(pages["Steps"], [("name", "Operation"), ("input", "Input bytes"), ("output", "Output bytes")])
        self.refresh_recipe(self.data.get("selected_step", 0) or 0)

    def filter_operations(self):
        query = self.search.get().lower()
        self.visible_operations = [item for item in self.catalog.values() if query in (item["name"] + " " + item["id"] + " " + item["category"]).lower()]
        self.operation_list.delete(0, "end")
        for item in self.visible_operations:
            self.operation_list.insert("end", item["name"])

    def operation_hint(self):
        selected = self.operation_list.curselection()
        if selected:
            self.hint.configure(text=self.visible_operations[selected[0]]["hint"])

    def add_operation(self):
        selected = self.operation_list.curselection()
        if selected and len(self.recipe) < 50:
            self.save_parameters()
            item = self.visible_operations[selected[0]]
            self.recipe.append({"op": item["id"], "args": json.loads(json.dumps(item["defaults"]))})
            self.refresh_recipe(len(self.recipe)-1)
            self.changed()

    def refresh_recipe(self, selection=0):
        self.selected_step = None
        self.recipe_list.delete(0, "end")
        for index, step in enumerate(self.recipe):
            self.recipe_list.insert("end", f"{index+1}. {self.catalog.get(step['op'], {}).get('name', step['op'])}" + (" (off)" if step.get("disabled") else ""))
        if self.recipe:
            self.recipe_list.selection_set(min(selection, len(self.recipe)-1))
        self.edit_step()

    def save_parameters(self, strict=False):
        if self.selected_step is None:
            return
        self.recipe[self.selected_step]["disabled"] = not self.step_enabled.get()
        values = {}
        for key, kind, variable in self.parameter_vars:
            value = variable.get() if kind != "key" else {"value": variable[0].get(), "format": variable[1].get()}
            if kind == "number":
                try:
                    value = float(value)
                    if not math.isfinite(value):
                        raise ValueError()
                    if value.is_integer():
                        value = int(value)
                except (ValueError, OverflowError):
                    if strict:
                        raise ValueError(key + " must be a finite number")
            values[key] = value
        self.recipe[self.selected_step]["args"] = values

    def edit_step(self):
        self.save_parameters()
        for child in self.params.winfo_children():
            child.destroy()
        self.parameter_vars = []
        selected = self.recipe_list.curselection()
        self.selected_step = selected[0] if selected else None
        if self.selected_step is None:
            self.label(self.params, "Add an operation\nto start a recipe.").pack(anchor="w", pady=8)
            return
        step = self.recipe[self.selected_step]
        self.step_enabled = tk.BooleanVar(value=not step.get("disabled", False))
        tk.Checkbutton(self.params, text="Enabled step", variable=self.step_enabled, bg=self.p["background"],
                       fg=self.p["text"], selectcolor=self.p["field"], activebackground=self.p["panel"],
                       command=self.changed).pack(anchor="w", pady=5)
        definition = self.catalog.get(step["op"], {})
        for param in definition.get("params", []):
            key, kind = param["key"], param["type"]
            value = step.get("args", {}).get(key, param.get("default", ""))
            self.label(self.params, param["label"]).pack(anchor="w", pady=(7, 3))
            if kind == "checkbox":
                variable = tk.BooleanVar(value=value)
                tk.Checkbutton(self.params, text="Enabled", variable=variable, bg=self.p["background"], fg=self.p["text"],
                               selectcolor=self.p["field"], activebackground=self.p["panel"], command=self.changed).pack(anchor="w")
            elif kind == "key":
                value = value if isinstance(value, dict) else {"value": str(value), "format": "utf-8"}
                variable = (tk.StringVar(value=value.get("value", "")), tk.StringVar(value=value.get("format", "utf-8")))
                ttk.Entry(self.params, textvariable=variable[0], style="Calculator.TEntry").pack(fill="x")
                ttk.Combobox(self.params, textvariable=variable[1], values=["utf-8", "hex", "base64"], state="readonly", width=10).pack(fill="x", pady=3)
                for var in variable:
                    var.trace_add("write", lambda *_: self.changed())
            else:
                variable = tk.StringVar(value=value)
                if kind == "select":
                    ttk.Combobox(self.params, textvariable=variable, values=param.get("options", []), state="readonly", width=10).pack(fill="x")
                else:
                    ttk.Entry(self.params, textvariable=variable, style="Calculator.TEntry").pack(fill="x")
                variable.trace_add("write", lambda *_: self.changed())
            self.parameter_vars.append((key, kind, variable))
        if not definition.get("params"):
            self.label(self.params, "No settings needed.").pack(anchor="w", pady=8)

    def move_step(self, direction):
        self.save_parameters()
        index = self.selected_step
        if index is not None and 0 <= index+direction < len(self.recipe):
            self.recipe[index], self.recipe[index+direction] = self.recipe[index+direction], self.recipe[index]
            self.refresh_recipe(index+direction)
            self.changed()

    def remove_step(self):
        index = self.selected_step
        if index is not None:
            self.recipe.pop(index)
            self.refresh_recipe(max(0, index-1))
            self.changed()

    def save_recipe(self):
        try:
            self.save_parameters(strict=True)
            filename = filedialog.asksaveasfilename(parent=self, defaultextension=".json", filetypes=[("Recipe", "*.json")])
            if filename:
                payload = {"app": "CryptoCalc", "format": 1, "savedUtc": datetime.now(timezone.utc).isoformat(),
                           "recipe": {"name": self.data.get("recipe_name", "Untitled recipe"), "steps": self.recipe}}
                Path(filename).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except (ValueError, OSError) as exc:
            self.error(str(exc))

    def load_recipe(self):
        filename = filedialog.askopenfilename(parent=self, filetypes=[("Recipe", "*.json")])
        if not filename:
            return
        try:
            if Path(filename).stat().st_size > 100_000:
                raise ValueError("Recipe exceeds 100 KB")
            payload = json.loads(Path(filename).read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Choose a CryptoCalc recipe file")
            if "app" in payload and (payload["app"] != "CryptoCalc" or payload.get("format") != 1):
                raise ValueError("Choose a CryptoCalc format 1 recipe file")
            recipe = payload.get("recipe", payload)
            steps = recipe["steps"]
            if not isinstance(steps, list) or not 1 <= len(steps) <= 50 or any(
                    not isinstance(s, dict) or s.get("op") not in self.catalog or not isinstance(s.get("args", {}), dict) or
                    not isinstance(s.get("disabled", False), bool) for s in steps):
                raise ValueError("Choose a recipe with 1-50 supported operations")
            self.data["recipe_name"] = str(recipe.get("name", "Untitled recipe"))[:120]
            self.recipe = steps
            self.refresh_recipe()
            self.changed()
        except (ValueError, OSError, KeyError, TypeError) as exc:
            self.error(str(exc))

    def load_crypto_file(self):
        filename = filedialog.askopenfilename(parent=self)
        if not filename:
            return
        try:
            if Path(filename).stat().st_size > 120_000:
                raise ValueError("Use the full HTML app for files above 120 KB")
            payload = Path(filename).read_bytes()
            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError:
                text = payload.hex()
                self.save_parameters()
                self.recipe.insert(0, {"op": "from_hex", "args": {}})
                self.refresh_recipe()
            self.source.delete("1.0", "end")
            self.source.insert("1.0", text)
            self.changed()
        except (ValueError, OSError) as exc:
            self.error(str(exc))

    def save_output(self):
        if self.result.get("type") != "cryptocalc":
            return
        filename = filedialog.asksaveasfilename(parent=self, defaultextension=".txt" if self.result["isText"] else ".bin")
        if filename:
            try:
                Path(filename).write_bytes(bytes.fromhex(self.result["hex"]))
            except (OSError, ValueError) as exc:
                self.error(str(exc))

    def build_stats(self):
        self.tabs, pages = self.notebook(self, ["Data", "Overview", "Intervals", "Findings", "Chart"])
        controls = self.frame(pages["Data"])
        controls.pack(fill="x", padx=7, pady=7)
        for text, command in [("Import file", self.load_stats_file), ("Paste data", self.paste_data),
                              ("+ Row", self.add_row), ("+ Column", self.add_column), ("Clear", self.clear_grid)]:
            self.button(controls, text, command).pack(side="left", padx=(0, 5))
        self.data_tabs, inputs = self.notebook(pages["Data"], ["Enter by hand", "CSV / pasted text"])
        grid = self.frame(inputs["Enter by hand"])
        grid.pack(fill="both", expand=True)
        self.grid_canvas = tk.Canvas(grid, bg=self.p["field"], highlightthickness=0)
        self.grid_canvas.grid(row=0, column=0, sticky="nsew")
        sy = ttk.Scrollbar(grid, command=self.grid_canvas.yview, style="Calculator.Vertical.TScrollbar")
        sy.grid(row=0, column=1, sticky="ns")
        sx = ttk.Scrollbar(grid, orient="horizontal", command=self.grid_canvas.xview, style="Calculator.Horizontal.TScrollbar")
        sx.grid(row=1, column=0, sticky="ew")
        self.grid_canvas.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        grid.rowconfigure(0, weight=1)
        grid.columnconfigure(0, weight=1)
        self.grid_body = self.frame(self.grid_canvas)
        self.grid_item = self.grid_canvas.create_window(0, 0, anchor="nw", window=self.grid_body)
        self.grid_canvas.bind("<Configure>", lambda e: self.grid_canvas.itemconfigure(
            self.grid_item, width=max(e.width, self.grid_body.winfo_reqwidth())))
        self.grid_body.bind("<Configure>", lambda _: self.grid_canvas.configure(scrollregion=self.grid_canvas.bbox("all")))
        self.headers = self.data.get("headers", ["column_1", "column_2"])
        self.cells = self.data.get("cells", [["", ""] for _ in range(5)])
        self.draw_grid()
        self.raw = self.text(inputs["CSV / pasted text"], height=8)
        self.raw.insert("1.0", self.data.get("raw", ""))
        self.raw.bind("<KeyRelease>", lambda _: self.changed())
        self.data_tabs.select(self.data.get("data_tab", 0))
        self.overview = self.table(pages["Overview"], [("column", "Column"), ("kind", "Type"), ("n", "n"), ("mean", "Mean"), ("median", "Median"), ("sd", "Std. dev.")])
        self.intervals = self.table(pages["Intervals"], [("column", "Column"), ("method", "Method"), ("target", "Target"), ("lower", "Lower"), ("upper", "Upper"), ("level", "Achieved %")])
        self.findings = self.text(pages["Findings"], readonly=True)
        bar = self.frame(pages["Chart"])
        bar.pack(fill="x", padx=8, pady=8)
        self.label(bar, "Column").pack(side="left", padx=(0, 8))
        self.chart_column = tk.StringVar()
        self.chart_choice = ttk.Combobox(bar, textvariable=self.chart_column, state="readonly")
        self.chart_choice.pack(side="left")
        self.chart_choice.bind("<<ComboboxSelected>>", lambda _: self.draw_chart())
        self.chart = tk.Canvas(pages["Chart"], bg=self.p["field"], highlightthickness=0, height=180)
        self.chart.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.chart.bind("<Configure>", lambda _: self.draw_chart())
        self.chart.create_text(25, 30, anchor="w", text="Run an analysis to draw a distribution.", fill=self.p["muted"])
        self.tabs.select(self.data.get("tab", 0))

    def read_grid(self):
        self.headers = [var.get() for var in self.header_vars]
        self.cells = [[var.get() for var in row] for row in self.cell_vars]

    def draw_grid(self):
        for child in self.grid_body.winfo_children():
            child.destroy()
        for column in range(1, 21):
            self.grid_body.columnconfigure(column, weight=0)
        self.header_vars, self.cell_vars, self.grid_entries = [], [], []
        for column, name in enumerate(self.headers):
            self.grid_body.columnconfigure(column+1, weight=1)
            variable = tk.StringVar(value=name)
            self.header_vars.append(variable)
            entry = ttk.Entry(self.grid_body, textvariable=variable, width=19, style="Calculator.TEntry")
            entry.grid(row=0, column=column+1, padx=2, pady=4, ipady=4, sticky="ew")
            variable.trace_add("write", lambda *_: self.changed())
        for index, row in enumerate(self.cells):
            self.label(self.grid_body, str(index+1)).grid(row=index+1, column=0, padx=8)
            variables, entries = [], []
            for column, value in enumerate(row):
                variable = tk.StringVar(value=value)
                entry = ttk.Entry(self.grid_body, textvariable=variable, width=19, style="Calculator.TEntry")
                entry.grid(row=index+1, column=column+1, padx=2, pady=2, ipady=4, sticky="ew")
                entry.bind("<<Paste>>", self.grid_paste)
                entry.bind("<Return>", lambda _, r=index, c=column: self.next_cell(r, c))
                variable.trace_add("write", lambda *_: self.changed())
                variables.append(variable)
                entries.append(entry)
            self.cell_vars.append(variables)
            self.grid_entries.append(entries)

    def next_cell(self, row, column):
        if row+1 < len(self.grid_entries):
            self.grid_entries[row+1][column].focus_set()
        return "break"

    def grid_paste(self, event):
        try:
            text = self.clipboard_get()
        except tk.TclError:
            return
        if "\n" in text or "\t" in text:
            self.paste_data(text)
            return "break"

    def add_row(self):
        self.read_grid()
        if len(self.cells) < 200:
            self.cells.append([""] * len(self.headers))
            self.draw_grid()
            self.changed()

    def add_column(self):
        self.read_grid()
        if len(self.headers) < 20:
            self.headers.append("column_" + str(len(self.headers)+1))
            for row in self.cells:
                row.append("")
            self.draw_grid()
            self.changed()

    def clear_grid(self):
        self.headers, self.cells = ["column_1", "column_2"], [["", ""] for _ in range(5)]
        self.draw_grid()
        self.raw.delete("1.0", "end")
        self.changed()

    def paste_data(self, text=None):
        try:
            text = self.clipboard_get() if text is None else text
            self.raw.delete("1.0", "end")
            self.raw.insert("1.0", text)
            self.data_tabs.select(1)
            self.changed()
        except tk.TclError:
            self.error("Clipboard has no text to paste")

    def load_stats_file(self):
        filename = filedialog.askopenfilename(parent=self, filetypes=[("Data", "*.csv *.tsv *.txt"), ("All files", "*.*")])
        if filename:
            try:
                if Path(filename).stat().st_size > 250_000:
                    raise ValueError("Use the full HTML app for files above 250 KB")
                self.paste_data(Path(filename).read_text(encoding="utf-8-sig"))
            except (ValueError, OSError) as exc:
                self.error(str(exc))

    def run(self):
        if self.host.workspace(self.identifier)["busy"]:
            return
        try:
            if self.engine == "cryptocalc":
                self.save_parameters(strict=True)
                if not self.recipe:
                    raise ValueError("Add an operation to the recipe first")
                payload = {"input": self.source.get("1.0", "end-1c"), "steps": self.recipe}
                action = "run"
            else:
                percent = float(self.confidence.get())
                if not math.isfinite(percent) or not 50 <= percent <= 99.99:
                    raise ValueError("Confidence must be from 50 to 99.99 percent")
                if self.data_tabs.index("current") == 0:
                    self.read_grid()
                    rows = [row for row in self.cells if any(value.strip() for value in row)]
                    if not rows:
                        raise ValueError("Enter data in the grid or paste a dataset first")
                    output = io.StringIO()
                    csv.writer(output).writerows([self.headers, *rows])
                    text = output.getvalue()
                else:
                    text = self.raw.get("1.0", "end-1c")
                if not text.strip():
                    raise ValueError("Paste a dataset first")
                payload = {"data": text, "confidence": percent}
                action = "analyze"
            self.dirty = False
            self.status.configure(fg=self.p["text"])
            self.send(action, json.dumps(payload, ensure_ascii=False))
        except (ValueError, tk.TclError) as exc:
            self.error(str(exc))

    @staticmethod
    def put_text(widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def receive(self, event):
        result = event.get("audit", {}).get("calculator", {})
        if not isinstance(result, dict) or result.get("type") != self.engine:
            return
        self.result = result
        self.data["result"] = result
        if self.engine == "cryptocalc":
            self.put_text(self.output_text, result["output"])
            self.put_text(self.output_hex, result["hex"])
            self.step_table.delete(*self.step_table.get_children())
            for step in result["steps"]:
                self.step_table.insert("", "end", values=(step["name"], step["inputBytes"], step["outputBytes"]))
            description = f"Completed {len(result['steps'])} steps / {result['bytes']} output bytes"
        else:
            analysis = result["analysis"]
            self.overview.delete(*self.overview.get_children())
            self.intervals.delete(*self.intervals.get_children())
            for report in analysis["reports"]:
                summary = report["summary"] or {}
                self.overview.insert("", "end", values=[report["column"]["name"], report["column"]["kind"],
                    *[number(summary.get(key)) for key in ["n", "mean", "median", "sd"]]])
                for iv in report["intervals"]:
                    self.intervals.insert("", "end", values=(report["column"]["name"], iv["method"],
                        iv.get("category") or iv["target"], number(iv["lower"]), number(iv["upper"]),
                        number(iv.get("achievedPercent") or analysis["level"]["percent"])))
            self.put_text(self.findings, event.get("text") or self.data.get("display", ""))
            self.data["display"] = event.get("text") or self.data.get("display", "")
            names = [report["column"]["name"] for report in analysis["reports"]]
            self.chart_choice.configure(values=names)
            if self.chart_column.get() not in names:
                self.chart_column.set(names[0] if names else "")
            self.draw_chart()
            self.tabs.select(1)
            description = f"{analysis['dataset']['rowCount']} rows / {analysis['level']['percent']}% confidence"
        self.status.configure(text="Input changed; these results are from the previous run." if self.dirty else description,
                              fg=self.p["text"])

    def draw_chart(self):
        self.chart.delete("all")
        analysis = self.result.get("analysis")
        if not analysis:
            return
        reports = analysis.get("reports", [])
        report = next((r for r in reports if r["column"]["name"] == self.chart_column.get()), None)
        if not report or not report["summary"]:
            return
        width, height = max(250, self.chart.winfo_width()), max(180, self.chart.winfo_height())
        left, top, bottom = 55, 35, height-75
        summary, column = report["summary"], report["column"]
        if column["kind"] == "qualitative":
            categories = sorted(summary["categories"], key=lambda c: c["count"], reverse=True)
            bars = [(c["category"], c["count"]) for c in categories[:11]]
            if len(categories) > 11:
                bars.append(("Other", sum(c["count"] for c in categories[11:])))
            title = "Category frequencies"
        else:
            values = column["values"]
            if not values:
                return
            lo, hi = min(values), max(values)
            bins = min(12, max(1, math.ceil(math.sqrt(len(values))))) if hi > lo else 1
            counts = [0]*bins
            for value in values:
                counts[min(bins-1, int((value-lo)/(hi-lo)*bins)) if hi > lo else 0] += 1
            bars = [(number(lo + (hi-lo)*i/bins), count) for i, count in enumerate(counts)]
            title = f"Histogram / {len(values)} values / {number(lo)} to {number(hi)}"
        maximum = max((count for _, count in bars), default=1) or 1
        self.chart.create_text(left, 15, text=title, anchor="w", fill=self.p["text"], font=(self.family, 11, "bold"))
        self.chart.create_line(left, top, left, bottom, width-15, bottom, fill=self.p["muted"])
        self.chart.create_text(left-8, top, text=str(maximum), anchor="e", fill=self.p["muted"])
        self.chart.create_text(left-8, bottom, text="0", anchor="e", fill=self.p["muted"])
        step = (width-left-22)/max(1, len(bars))
        for index, (label, count) in enumerate(bars):
            x = left+index*step+5
            y = bottom-(bottom-top)*count/maximum
            self.chart.create_rectangle(x, y, x+max(2, step-9), bottom, fill=self.p["accent"], outline="", tags="bar")
            self.chart.create_text(x+step/2-5, y-10, text=str(count), fill=self.p["text"], font=(self.family, 9))
            self.chart.create_text(x+step/2-5, bottom+12, text=label[:20], width=max(25, step-2), anchor="n", fill=self.p["muted"], font=(self.family, 9))
        self.chart.create_text(width-15, height-9, text="Bar height = count", anchor="se", fill=self.p["muted"], font=(self.family, 9))

    def copy_result(self):
        if not self.result:
            return
        if self.engine == "cryptocalc":
            text = self.result["hex"] if self.output_tabs.index("current") == 1 else self.result["output"]
        else:
            text = self.data.get("display", "")
        self.clipboard_clear()
        self.clipboard_append(text)

    def snapshot(self):
        self.data.update(dirty=self.dirty, result=self.result)
        if self.engine == "cryptocalc":
            self.save_parameters()
            self.data.update(recipe=self.recipe, input=self.source.get("1.0", "end-1c"), search=self.search.get(),
                             selected_step=self.selected_step, output_tab=self.output_tabs.index("current"))
        else:
            self.read_grid()
            self.data.update(headers=self.headers, cells=self.cells, raw=self.raw.get("1.0", "end-1c"),
                             confidence=self.confidence.get(), data_tab=self.data_tabs.index("current"), tab=self.tabs.index("current"),
                             chart_column=self.chart_column.get())
