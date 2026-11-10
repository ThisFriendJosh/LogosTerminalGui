"""Portable phosphor effects. Tk canvases, bounded sprites, no runtime packages.

The read-only transcript still uses Tk's Text engine for wrapping, scrolling,
selection and copy. A canvas projects its visible text above the shared rain.
The command editor stays a native Text widget.
"""
from __future__ import annotations

import math
import random
import tkinter as tk
from tkinter import font as tkfont

BLACK = "#000000"
PHOSPHOR = "#00ff41"
INK = "#00e83b"
DIM = "#008529"
EDGE = "#075c24"


def blend(a, b, amount):
    return "#" + "".join(f"{round(int(a[i:i+2], 16) * (1-amount) + int(b[i:i+2], 16) * amount):02x}" for i in (1, 3, 5))


# Original small stroke drawings of the 26 Standard Galactic Alphabet forms,
# in A-Z order. Rendering strokes avoids missing-glyph boxes and font installs.
# Coordinates use a 0..8 x 0..10 design grid; a one-point stroke is a dot.
SGA = (
    (((1, 7), (1, 3), (4, 1), (7, 3), (7, 7)), ((1, 5), (7, 5))),
    (((2, 1), (2, 9)), ((2, 5), (6, 5), (7, 7), (6, 9), (2, 9))),
    (((7, 2), (2, 2), (2, 8), (7, 8)),),
    (((1, 2), (5, 2), (5, 5), (7, 5), (7, 9)), ((1, 5), (5, 5))),
    (((1, 2), (6, 2), (3, 5), (6, 8), (1, 8)), ((1, 5), (5, 5))),
    (((2, 9), (2, 2), (7, 2)), ((1, 5), (5, 5))),
    (((2, 2), (2, 8)), ((2, 5), (7, 5))),
    (((1, 2), (1, 8)), ((6, 1), (6, 9)), ((1, 5), (7, 5))),
    (((4, 1), (4, 7)), ((4, 9),)),
    (((3, 1),), ((3, 5),), ((3, 9),)),
    (((1, 1), (1, 9)), ((2, 5), (7, 1)), ((2, 5), (7, 9)), ((5, 4), (7, 4))),
    (((2, 1), (2, 8), (7, 8)), ((1, 6), (5, 6))),
    (((1, 8), (1, 2), (4, 5), (7, 2), (7, 8)),),
    (((1, 2), (1, 6), (3, 8)), ((6, 1), (6, 6), (4, 9))),
    (((2, 2), (6, 2), (6, 8), (2, 8), (2, 2)),),
    (((1, 4), (1, 9)), ((1, 1),), ((5, 2), (5, 8)), ((7, 2), (7, 8))),
    (((2, 2), (6, 2), (6, 7), (2, 7), (2, 2)), ((4, 7), (4, 10))),
    (((2, 2),), ((6, 2),), ((2, 7),), ((6, 7),)),
    (((7, 2), (2, 2), (2, 5), (6, 5), (6, 8), (1, 8)),),
    (((2, 1), (2, 8), (6, 8)), ((1, 3), (6, 3)), ((7, 10),)),
    (((1, 2), (1, 7), (4, 7)), ((5, 2), (5, 7), (7, 7))),
    (((1, 2), (4, 9), (7, 2)), ((4, 2), (4, 6))),
    (((2, 2),), ((6, 2),), ((4, 5),), ((2, 8),), ((6, 8),)),
    (((1, 8), (7, 2)), ((2, 1),)),
    (((2, 1), (2, 9)), ((6, 1), (6, 9))),
    (((1, 8), (1, 2), (7, 2), (7, 8)), ((4, 2), (4, 8))),
)


class GlyphAtlas:
    """Cached RGB stroke spans; no per-glyph Tk items or font downloads."""
    def __init__(self, master, accent=PHOSPHOR):
        self.rgb = tuple(int(accent[i:i+2], 16) for i in (1, 3, 5))
        self.cache = {}
        self.coverage = []
        for strokes in SGA:
            lit = set()
            for stroke in strokes:
                if len(stroke) == 1:
                    lit.add((stroke[0][0]+3, stroke[0][1]+3))
                for a, b in zip(stroke, stroke[1:]):
                    steps = max(abs(b[0]-a[0]), abs(b[1]-a[1]))
                    for step in range(steps+1):
                        t = step/max(steps, 1)
                        lit.add((round(a[0]+(b[0]-a[0])*t)+3, round(a[1]+(b[1]-a[1])*t)+3))
            rows = []
            for y in range(17):
                for x in range(15):
                    strength = 1.0 if (x, y) in lit else .16 if any((x+dx, y+dy) in lit for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0))) else 0
                    if strength:
                        rows.append((y, x, strength))
            self.coverage.append(rows)

    def for_background(self, background):
        if background not in self.cache:
            base = tuple(int(background[i:i+2], 16) for i in (1, 3, 5))
            tables = []
            for coverage in self.coverage:
                levels = []
                for level in (.035, .065, .11, .16, .22, .30, .40, .53):
                    pixels = {}
                    for y, x, strength in coverage:
                        pixels.setdefault(y, {})[x] = bytes(round(b*(1-strength)+c*level*strength) for b, c in zip(base, self.rgb))
                    spans = []
                    for y, row in pixels.items():
                        x = min(row)
                        end = max(row)
                        spans.append((y, x, b"".join(row.get(i, bytes(base)) for i in range(x, end+1))))
                    levels.append(spans)
                tables.append(levels)
            self.cache[background] = tables
        return self.cache[background]


class RainField:
    """A bounded, shared world model; drawing never changes module state."""
    MAX_CELLS = 1800

    def __init__(self, seed=91):
        self.random = random.Random(seed)
        self.width = self.height = 0
        self.columns = []
        self.cells = []
        self.elapsed = 0.0
        self.ghosts = []
        self.sequence = 0

    def resize(self, width, height):
        if (width, height) == (self.width, self.height):
            return
        self.width, self.height = max(1, width), max(1, height)
        self.pitch = max(23, math.ceil(math.sqrt(self.width*self.height/self.MAX_CELLS)))
        rows = math.ceil(self.height/self.pitch) + 2
        count = min(96, math.ceil(self.width/self.pitch))
        while count*rows > self.MAX_CELLS-240:
            self.pitch += 1
            rows = math.ceil(self.height/self.pitch) + 2
            count = min(96, math.ceil(self.width/self.pitch))
        self.columns = [{"offset": self.random.uniform(0, self.pitch), "speed": self.random.uniform(19, 55),
                         "head": self.random.randrange(rows), "tail": self.random.randint(7, 17),
                         "glyphs": [self.random.randrange(26) for _ in range(rows)]} for _ in range(count)]
        self.ghosts.clear()
        self._project()

    def advance(self, dt):
        dt = max(0, min(.15, dt))
        self.elapsed += dt
        self.ghosts = [(key, x, y, glyph, remaining-dt) for key, x, y, glyph, remaining in self.ghosts if remaining > dt]
        for index, column in enumerate(self.columns):
            column["offset"] += column["speed"]*dt
            if column["offset"] >= self.pitch:
                column["offset"] -= self.pitch
                column["glyphs"].insert(0, self.random.randrange(26))
                column["glyphs"].pop()
                column["head"] = (column["head"] + 1) % len(column["glyphs"])
            # Morph a small subset; the persistent dim tail acts as after-image.
            if self.random.random() < .75:
                row = self.random.randrange(len(column["glyphs"]))
                self.sequence += 1
                self.ghosts.append((1000000+self.sequence, index*self.pitch+11, (row-1)*self.pitch+column["offset"], column["glyphs"][row], .8))
                column["glyphs"][row] = self.random.randrange(26)
        self.ghosts = self.ghosts[-240:]
        self._project()

    def _project(self):
        self.cells = [(key, x, y, glyph, max(0, round(remaining*2))) for key, x, y, glyph, remaining in self.ghosts]
        for x, column in enumerate(self.columns):
            for row, glyph in enumerate(column["glyphs"]):
                y = (row-1)*self.pitch + column["offset"]
                tail = (column["head"] - row) % len(column["glyphs"])
                energy = max(0.0, 1-tail/column["tail"])
                depth = .95 - .50*max(0, y)/self.height
                level = max(0, min(7, round((1+6*energy)*depth)))
                self.cells.append((x*1000+row, x*self.pitch+11, y, glyph, level))


class RainCanvas(tk.Canvas):
    """Project a shared bounded raster tile; only a few canvas items per surface."""
    def __init__(self, parent, **kwargs):
        kwargs.setdefault("bg", BLACK)
        super().__init__(parent, highlightthickness=0, bd=0, **kwargs)
        self.sprites = {}
        self.exclusions = []
        self.last_size = None

    def paint(self, atmosphere):
        if not self.winfo_ismapped():
            return
        width, height = self.winfo_width(), self.winfo_height()
        if width < 3 or height < 3:
            return
        dx = self.winfo_rootx()-atmosphere.window.winfo_rootx()
        dy = self.winfo_rooty()-atmosphere.window.winfo_rooty()
        vx, vy = self.canvasx(0), self.canvasy(0)
        tw, th = atmosphere.field.width, atmosphere.field.height
        picture = atmosphere.images[atmosphere.picture_key(self)]
        visible = set()
        for tx in range(math.floor(dx/tw), math.ceil((dx+width)/tw)):
            for ty in range(math.floor(dy/th), math.ceil((dy+height)/th)):
                key = tx, ty
                px, py = tx*tw-dx+vx, ty*th-dy+vy
                visible.add(key)
                if key not in self.sprites:
                    self.sprites[key] = (self.create_image(px, py, image=picture, anchor="nw", tags=("rain",)), px, py)
                else:
                    item, old_x, old_y = self.sprites[key]
                    if (px, py) != (old_x, old_y):
                        self.coords(item, px, py)
                        self.sprites[key] = item, px, py
        for key in self.sprites.keys()-visible:
            self.delete(self.sprites.pop(key)[0])
        self.tag_lower("rain")
        if self.last_size != (width, height):
            self.delete("crt")
            base, accent = self.cget("bg"), atmosphere.theme.palette["accent"]
            for offset in range(3):
                self.create_rectangle(offset, offset, width-offset-1, height-offset-1,
                                      outline=blend(base, accent, offset*.01), tags=("crt",))
            self.tag_lower("crt")
            self.last_size = width, height

    def clear_rain(self):
        self.delete("rain")
        self.sprites.clear()


class Atmosphere:
    """One animation clock drives all surfaces, with a fixed sprite ceiling."""
    def __init__(self, window, theme):
        self.window = window
        self.theme = theme
        self.glow_raster = None
        if theme.rain:
            from galactic_rain import AnimatedRain, GlowRaster, cached_glow_atlas
            options = theme.rain
            self.atlas = cached_glow_atlas(SGA, options["glow_radius"], options["glow_strength"], options["brightness"])
            self.field = AnimatedRain(options)
            self.glow_raster = GlowRaster(self.atlas)
        else:
            self.atlas = GlyphAtlas(window, theme.palette["accent"])
            self.field = RainField()
        self.layers = []
        self.backgrounds = []
        self.enabled = True
        self.images, self.bases = {}, {}

    def decorate(self, parent, skip=()):
        for child in list(parent.winfo_children()):
            if child in skip or isinstance(child, (RainCanvas, PhosphorText)):
                continue
            if isinstance(child, tk.Frame):
                if not any(p == child and layer.winfo_exists() for p, layer in self.backgrounds):
                    layer = RainCanvas(child, takefocus=0, bg=child.cget("bg"))
                    layer.place(x=0, y=0, relwidth=1, relheight=1)
                    layer.tk.call("lower", str(layer))
                    self.layers.append(layer)
                    self.backgrounds.append((child, layer))
            self.decorate(child, skip)

    def register(self, layer):
        self.layers.append(layer)

    def picture_key(self, layer):
        background = layer.cget("bg")
        if self.glow_raster:
            strength = self.theme.rain["content_brightness"] if getattr(layer, "reading_surface", False) else 1.0
            return background, strength
        return background

    def tick(self, dt):
        # A bounded tile is shared by every canvas. This keeps raster memory and
        # upload cost fixed on large monitors instead of growing with screen area.
        max_width, max_height = (768, 480) if self.glow_raster else (960, 720)
        width, height = min(max_width, self.window.winfo_width()), min(max_height, self.window.winfo_height())
        self.field.resize(width, height)
        self.field.advance(dt)
        if self.glow_raster:
            self.glow_raster.prepare(self.field.cells if self.theme.effects["digital_rain"] else (), width, height,
                                     self.theme.effects["scanlines"])
        self.backgrounds = [(p, layer) for p, layer in self.backgrounds if p.winfo_exists() and layer.winfo_exists()]
        self.layers = [layer for layer in self.layers if layer.winfo_exists()]
        backgrounds = {self.picture_key(layer) for layer in self.layers if layer.winfo_ismapped()}
        for background in backgrounds:
            if self.glow_raster:
                self._raster(background[0], width, height, strength=background[1])
            else:
                self._raster(background, width, height)
        for layer in self.layers:
            layer.paint(self)

    def _raster(self, background, width, height, strength=1.0):
        if self.glow_raster:
            key = background, strength
            if key not in self.images:
                self.images[key] = tk.PhotoImage(master=self.window)
            self.images[key].configure(data=self.glow_raster.image_bytes(background, self.theme.palette["accent"], strength), format="PNG")
            return
        key = background, width, height
        if key not in self.bases:
            base = bytes(int(background[i:i+2], 16) for i in (1, 3, 5))
            scan = blend(background, self.theme.palette["accent"], .018)
            scan = bytes(int(scan[i:i+2], 16) for i in (1, 3, 5))
            self.bases = {k: v for k, v in self.bases.items() if k[0] != background}
            self.bases[key] = b"".join((scan if self.theme.effects["scanlines"] and y % 4 == 2 else base)*width for y in range(height))
        frame = bytearray(self.bases[key])
        if self.theme.effects["digital_rain"]:
            table = self.atlas.for_background(background)
            # Ghosts are drawn first; new symbols remain sharp above their trail.
            for _, x, y, glyph, level in self.field.cells:
                left, top = round(x)-7, round(y)-8
                if 0 <= left and left+15 <= width and 0 <= top and top+17 <= height:
                    origin = (top*width+left)*3
                    for row, start, pixels in table[glyph][level]:
                        offset = origin+(row*width+start)*3
                        frame[offset:offset+len(pixels)] = pixels
                    continue
                for row, start, pixels in table[glyph][level]:
                    py, px = top+row, left+start
                    if not 0 <= py < height or px >= width:
                        continue
                    if px < 0:
                        pixels, px = pixels[-px*3:], 0
                    pixels = pixels[:max(0, width-px)*3]
                    offset = (py*width+px)*3
                    frame[offset:offset+len(pixels)] = pixels
        if background not in self.images:
            self.images[background] = tk.PhotoImage(master=self.window)
        header = chr(10).join(("P6", f"{width} {height}", "255", "")).encode()
        self.images[background].configure(data=header+frame, format="PPM")

    def set_enabled(self, value):
        self.enabled = value
        if not value:
            for layer in self.layers:
                if layer.winfo_exists():
                    layer.clear_rain()


class NeonScrollbar(tk.Canvas):
    """A small, platform-independent scrollbar for the phosphor skin."""
    def __init__(self, parent, command, palette):
        super().__init__(parent, width=9, height=80, bg=palette["panel"], highlightthickness=0, bd=0, takefocus=1)
        self.command, self.palette = command, palette
        self.first, self.last, self.grab = 0.0, 1.0, 0.0
        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<Button-1>", self.start)
        self.bind("<B1-Motion>", self.drag_thumb)
        self.bind("<Up>", lambda e: self.command("scroll", -1, "units"))
        self.bind("<Down>", lambda e: self.command("scroll", 1, "units"))
        self.bind("<Prior>", lambda e: self.command("scroll", -1, "pages"))
        self.bind("<Next>", lambda e: self.command("scroll", 1, "pages"))

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self.draw()

    def draw(self):
        self.delete("all")
        height = max(1, self.winfo_height())
        self.create_line(4, 0, 4, height, fill=self.palette["edge"])
        if self.last-self.first < .999:
            self.create_rectangle(2, self.first*height, 7, max(self.first*height+12, self.last*height),
                                  fill=self.palette["accent"], outline="")

    def start(self, event):
        self.focus_set()
        position = event.y/max(1, self.winfo_height())
        if self.first <= position <= self.last:
            self.grab = position-self.first
        else:
            self.grab = (self.last-self.first)/2
            self.command("moveto", max(0, position-self.grab))

    def drag_thumb(self, event):
        self.command("moveto", max(0, min(1, event.y/max(1, self.winfo_height())-self.grab)))


class PhosphorText(tk.Text):
    """Native read-only Text behavior with a transparent, glowing canvas view."""
    def __init__(self, parent, **kwargs):
        self.redraw_job = None
        self._fonts = {}
        super().__init__(parent, **kwargs)
        self.screen = RainCanvas(self, cursor="xterm", takefocus=0)
        self.screen.reading_surface = True
        self.screen.place(x=0, y=0, relwidth=1, relheight=1)
        self.anchor = None
        self.cursor_item = None
        self.effects = True
        self.canvas_mode = False
        self.block_cursor = False
        self.accent, self.selection_color = PHOSPHOR, "#075e24"
        self.bind("<Configure>", lambda e: self.refresh(), add=True)
        self.screen.bind("<Button-1>", self._select_start)
        self.screen.bind("<B1-Motion>", self._select_drag)
        self.screen.bind("<Double-Button-1>", self._select_word)
        self.screen.bind("<MouseWheel>", self._wheel)
        self.screen.bind("<Button-4>", lambda e: self.yview_scroll(-3, "units"))
        self.screen.bind("<Button-5>", lambda e: self.yview_scroll(3, "units"))
        self.bind("<Control-a>", self._select_all)
        self.bind("<<Copy>>", self._copy)
        self.bind("<KeyRelease>", lambda e: self.refresh(), add=True)

    def refresh(self):
        if self.redraw_job is None and self.winfo_exists() and self.canvas_mode:
            self.redraw_job = self.after_idle(self._render)

    def insert(self, *args):
        super().insert(*args)
        self.refresh()

    def delete(self, *args):
        super().delete(*args)
        self.refresh()

    def see(self, *args):
        super().see(*args)
        self.refresh()

    def yview(self, *args):
        value = super().yview(*args)
        if args:
            self.refresh()
        return value

    def yview_scroll(self, *args):
        super().yview_scroll(*args)
        self.refresh()

    def _wheel(self, event):
        self.yview_scroll(-int(event.delta/120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1), "units")
        return "break"

    def _select_start(self, event):
        self.focus_set()
        self.anchor = self.index(f"@{event.x},{event.y}")
        self.tag_remove("sel", "1.0", "end")
        self.refresh()

    def _select_drag(self, event):
        if self.anchor is None:
            return
        if event.y < 0 or event.y > self.winfo_height():
            self.yview_scroll(-1 if event.y < 0 else 1, "units")
        end = self.index(f"@{event.x},{event.y}")
        a, b = (self.anchor, end) if self.compare(self.anchor, "<=", end) else (end, self.anchor)
        self.tag_remove("sel", "1.0", "end")
        self.tag_add("sel", a, b)
        self.refresh()

    def _select_word(self, event):
        index = self.index(f"@{event.x},{event.y}")
        self.tag_remove("sel", "1.0", "end")
        self.tag_add("sel", index+" wordstart", index+" wordend")
        self.refresh()
        return "break"

    def _select_all(self, event=None):
        self.tag_add("sel", "1.0", "end-1c")
        self.refresh()
        return "break"

    def _copy(self, event=None):
        if self.tag_ranges("sel"):
            self.clipboard_clear()
            self.clipboard_append(self.get("sel.first", "sel.last"))
        return "break"

    def _font(self, name):
        name = str(name)
        if name not in self._fonts:
            self._fonts[name] = tkfont.Font(root=self, font=name)
        return self._fonts[name]

    def _render(self):
        self.redraw_job = None
        if not self.winfo_exists() or not self.winfo_ismapped() or not self.canvas_mode:
            return
        self.screen.delete("ink")
        self.cursor_item = None
        # Font objects may have been resized in Settings.
        self._fonts.clear()
        index = self.index("@0,0 display linestart")
        limit = self.index("end-1c")
        for _ in range(220):
            info = self.dlineinfo(index)
            if not info:
                break
            x, y, width, height, baseline = info
            if y > self.winfo_height():
                break
            next_index = self.index(index+" +1 display lines display linestart")
            end = next_index if self.compare(next_index, ">", index) else self.index("end")
            for segment in reflow_segments(self, index, end):
                text, tags, position = segment
                text = text.rstrip("\n").replace("\t", "    ")
                if not text:
                    continue
                color, name = str(self.cget("fg")), str(self.cget("font"))
                for tag in tags:
                    color = self.tag_cget(tag, "foreground") or color
                    name = self.tag_cget(tag, "font") or name
                font = self._font(name)
                top = y + baseline - font.metrics("ascent")
                length = font.measure(text)
                if "sel" in tags:
                    self.screen.create_rectangle(x, y, x+length, y+height, fill=self.selection_color, outline="", tags=("ink",))
                elif self.effects:
                    halo = blend(self.screen.cget("bg"), color, .18)
                    for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        self.screen.create_text(x+ox, top+oy, text=text, anchor="nw", fill=halo, font=font, tags=("ink",))
                self.screen.create_text(x, top, text=text, anchor="nw", fill=color, font=font, tags=("ink",))
                x += length
            if self.block_cursor and self.compare(limit, ">=", index) and self.compare(limit, "<", end):
                font = self._font(self.cget("font"))
                self.cursor_item = self.screen.create_rectangle(x+2, y+1, x+2+font.measure("M"), y+font.metrics("linespace"),
                                                                 fill=self.accent, outline="", tags=("ink",))
            if self.compare(end, ">=", "end") or self.compare(next_index, "<=", index):
                break
            index = next_index

    def set_effects(self, enabled):
        if self.effects != enabled:
            self.effects = enabled
            self.refresh()

    def set_theme(self, theme, enabled=True):
        self.canvas_mode = any(theme.effects[key] for key in ("digital_rain", "text_glow", "scanlines"))
        self.block_cursor = theme.effects["block_cursor"]
        self.effects = enabled and theme.effects["text_glow"]
        self.accent, self.selection_color = theme.palette["accent"], theme.palette["selection"]
        self.screen.configure(bg=theme.palette["panel"])
        if self.canvas_mode:
            self.screen.place(x=0, y=0, relwidth=1, relheight=1)
        else:
            self.screen.place_forget()
        self.refresh()

    def pulse_cursor(self, now, animate):
        if self.cursor_item:
            self.screen.itemconfigure(self.cursor_item, state="normal" if not animate or int(now*2) % 2 == 0 else "hidden")

    def destroy(self):
        if self.redraw_job:
            self.after_cancel(self.redraw_job)
            self.redraw_job = None
        super().destroy()


def reflow_segments(widget, start, end):
    """Yield style runs from native Text indices, preserving tag priority."""
    for kind, value, index in widget.dump(start, end, text=True, tag=True):
        if kind == "text":
            yield value, widget.tag_names(index), index


def draw_icon(canvas, kind, x, y, size, color, halo):
    """The five icon motifs are decoration, never a fixed set of modules."""
    def points(seq):
        return [value for px, py in seq for value in (x+px*size, y+py*size)]

    paths, circles, boxes = [], [], []
    if kind == "reticle":
        circles = [(.18, .18, .82, .82)]
        paths = [[(.5, 0), (.5, .32)], [(.5, .68), (.5, 1)], [(0, .5), (.32, .5)], [(.68, .5), (1, .5)]]
        boxes = [(.47, .47, .53, .53)]
    elif kind == "network":
        paths = [[(.2, .2), (.5, .52), (.8, .2)], [(.5, .52), (.5, .88)]]
        circles = [(.08, .08, .32, .32), (.68, .08, .92, .32), (.38, .4, .62, .64), (.38, .76, .62, 1)]
    elif kind == "chip":
        boxes = [(.22, .22, .78, .78), (.37, .37, .63, .63)]
        for value in (.3, .5, .7):
            paths.extend([[(value, .03), (value, .22)], [(value, .78), (value, .97)],
                          [(.03, value), (.22, value)], [(.78, value), (.97, value)]])
    elif kind == "document":
        paths = [[(.2, .04), (.65, .04), (.85, .25), (.85, .96), (.2, .96), (.2, .04)],
                 [(.65, .04), (.65, .25), (.85, .25)]]
        paths.extend([[(.32, v), (.72, v)] for v in (.44, .62, .8)])
    else:
        gear = []
        for i in range(64):
            angle = i*math.tau/64
            radius = .47 if i % 8 in (1, 2, 3, 4) else .34
            gear.append((.5+math.cos(angle)*radius, .5+math.sin(angle)*radius))
        paths = [gear+[gear[0]]]
        circles = [(.34, .34, .66, .66)]
    for width, fill in ((4, halo), (1.3, color)):
        for path in paths:
            canvas.create_line(*points(path), fill=fill, width=width, capstyle="round", joinstyle="round")
        for a, b, c, d in circles:
            canvas.create_oval(x+a*size, y+b*size, x+c*size, y+d*size, outline=fill, width=width)
        for a, b, c, d in boxes:
            canvas.create_rectangle(x+a*size, y+b*size, x+c*size, y+d*size, outline=fill, width=width)
