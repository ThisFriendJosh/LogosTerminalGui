"""Galactic 2.0: time-based character animation and cached soft phosphor masks.

The raster uses 16-bit lanes in Python integers to accumulate monochrome light
in C-speed integer operations. An indexed PNG colors the intensity plane without
a Python loop over every RGB pixel. No graphics packages or GPU are required.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
import random
import struct
import zlib


@dataclass(slots=True)
class Character:
    uid: int
    glyph: int
    countdown: float
    shimmer: float
    ghost_glyph: int = -1
    ghost_y: float = 0
    ghost_age: float = 0
    ghost_level: int = 0


class AnimatedRain:
    """Stable moving characters, each with an independent symbol-change clock."""
    MAX_CELLS = 4096

    def __init__(self, settings, seed=91):
        self.settings = settings
        self.random = random.Random(seed)
        self.width = self.height = 0
        self.columns, self.cells = [], []
        self.elapsed = 0.0
        self.sequence = 0

    def _character(self):
        self.sequence += 1
        rate = self.settings["morph_rate"]
        return Character(self.sequence, self.random.randrange(26), self.random.uniform(0, 1/rate) if rate else math.inf,
                         self.random.random()*math.tau)

    def resize(self, width, height):
        if (width, height) == (self.width, self.height):
            return
        self.width, self.height = max(1, width), max(1, height)
        scale = 1.0
        while True:
            self.column_pitch = self.settings["column_spacing"]*scale
            self.row_pitch = self.settings["row_spacing"]*scale
            count = min(128, math.ceil(self.width/self.column_pitch))
            rows = math.ceil(self.height/self.row_pitch)+2
            if count*rows <= self.MAX_CELLS//2:
                break
            scale *= 1.05
        self.columns = [{"offset": self.random.uniform(0, self.row_pitch),
                         "speed": self.settings["fall_speed"]*self.random.uniform(.65, 1.35),
                         "head": self.random.randrange(rows), "tail": self.random.randint(7, 16),
                         "characters": [self._character() for _ in range(rows)]} for _ in range(count)]
        self._project()

    def advance(self, dt):
        dt = max(0.0, min(.15, dt))
        if not dt:
            return
        self.elapsed += dt
        rate = self.settings["morph_rate"]
        for column in self.columns:
            column["offset"] += column["speed"]*dt
            while column["offset"] >= self.row_pitch:
                column["offset"] -= self.row_pitch
                column["characters"].insert(0, self._character())
                column["characters"].pop()
                column["head"] = (column["head"]+1) % len(column["characters"])
            for row, character in enumerate(column["characters"]):
                character.ghost_age += dt
                character.countdown -= dt
                if character.countdown <= 0 and rate:
                    character.ghost_glyph = character.glyph
                    character.ghost_y = (row-1)*self.row_pitch+column["offset"]
                    character.ghost_age = 0
                    character.ghost_level = self._level(column, row, character)
                    character.glyph = (character.glyph+self.random.randrange(1, 26)) % 26
                    while character.countdown <= 0:
                        character.countdown += self.random.uniform(.6, 1.4)/rate
        self._project()

    def _level(self, column, row, character):
        tail = (column["head"]-row) % len(column["characters"])
        energy = max(0, 1-tail/column["tail"])
        y = (row-1)*self.row_pitch+column["offset"]
        depth = .96-.35*max(0, y)/self.height
        shimmer = .94+.06*math.sin(self.elapsed*2.4+character.shimmer)
        return max(1, min(31, round((.16+.84*energy)*depth*shimmer*31)))

    def _project(self):
        ghosts, current = [], []
        lifetime = self.settings["trail_seconds"]
        for index, column in enumerate(self.columns):
            x = (index+.5)*self.column_pitch
            for row, character in enumerate(column["characters"]):
                if lifetime and character.ghost_glyph >= 0 and character.ghost_age < lifetime:
                    level = round(character.ghost_level*.22*(1-character.ghost_age/lifetime))
                    if level > 1:
                        ghosts.append((-character.uid, x, character.ghost_y, character.ghost_glyph, level))
                current.append((character.uid, x, (row-1)*self.row_pitch+column["offset"], character.glyph,
                                self._level(column, row, character)))
        self.cells = ghosts+current


@lru_cache(maxsize=8)
def cached_glow_atlas(strokes, radius, strength, brightness):
    return SoftGlyphAtlas(strokes, radius, strength, brightness)


class SoftGlyphAtlas:
    """Gaussian halos and four vertical subpixel phases, calculated once."""
    LEVELS = 32
    PHASES = 4

    def __init__(self, alphabet, radius, strength, brightness):
        self.width, self.height = 9+2*radius, 12+2*radius
        self.origin_x, self.origin_y = 4+radius, 5+radius
        self.tables = []
        sigma = max(.8, radius*.55)
        for strokes in alphabet:
            lit = set()
            for stroke in strokes:
                if len(stroke) == 1:
                    lit.add(stroke[0])
                for a, b in zip(stroke, stroke[1:]):
                    count = max(abs(b[0]-a[0]), abs(b[1]-a[1]))
                    for step in range(count+1):
                        t = step/max(1, count)
                        lit.add((round(a[0]+(b[0]-a[0])*t), round(a[1]+(b[1]-a[1])*t)))
            coverage = []
            for y in range(self.height):
                line = []
                for x in range(self.width):
                    distance = min((x-radius-px)**2+(y-radius-py)**2 for px, py in lit)
                    value = 1.0 if distance == 0 else min(.75, strength*.36*math.exp(-distance/(2*sigma*sigma))) if distance <= radius*radius else 0
                    line.append(value)
                coverage.append(line)
            levels = []
            for level in range(self.LEVELS):
                phases = []
                for phase in range(self.PHASES):
                    fraction = phase/self.PHASES
                    rows = []
                    for y, line in enumerate(coverage):
                        above = coverage[y-1] if y else [0]*self.width
                        values = [min(255, round(255*brightness*level/(self.LEVELS-1)*(v*(1-fraction)+a*fraction))) for v, a in zip(line, above)]
                        packed = sum(value << (16*x) for x, value in enumerate(values))
                        if packed:
                            rows.append((y, packed))
                    phases.append(tuple(rows))
                levels.append(tuple(phases))
            self.tables.append(tuple(levels))


class GlowRaster:
    """Additive light composition with saturation and a shared PNG data plane."""
    def __init__(self, atlas):
        self.atlas = atlas
        self.size = None
        self.palette_cache = {}
        self.last_indices = b""

    def indices(self, cells, width, height, scanlines=False):
        if self.size != (width, height):
            self.size = width, height
            self.mask = (1 << (width*16))-1
            self.low = int.from_bytes(b"\xff\x00"*width, "little")
            self.high = self.low << 8
            self.overbit = int.from_bytes(b"\x00\x01"*width, "little")
        rows = [0]*height
        atlas = self.atlas
        for _, x, y, glyph, level in cells:
            floor_y = math.floor(y)
            phase = min(atlas.PHASES-1, int((y-floor_y)*atlas.PHASES))
            left, top = math.floor(x)-atlas.origin_x, floor_y-atlas.origin_y
            if left >= width or left+atlas.width <= 0 or top >= height or top+atlas.height <= 0:
                continue
            stamps = atlas.tables[glyph][level][phase]
            if left >= 0:
                shift = left*16
                for offset, bits in stamps:
                    py = top+offset
                    if 0 <= py < height:
                        rows[py] += bits << shift
            else:
                shift = -left*16
                for offset, bits in stamps:
                    py = top+offset
                    if 0 <= py < height:
                        rows[py] += bits >> shift
        scan = bytes(round(i*.92) for i in range(256))
        result = []
        for y, row in enumerate(rows):
            row &= self.mask
            overflow = row & self.high
            overflow |= overflow >> 4
            overflow |= overflow >> 2
            overflow |= overflow >> 1
            overflow &= self.overbit
            saturated = (row & self.low) | (overflow-(overflow >> 8))
            pixels = saturated.to_bytes(width*2, "little")[::2]
            result.append(pixels.translate(scan) if scanlines and y % 4 == 2 else pixels)
        self.last_indices = b"".join(result)
        return self.last_indices

    @staticmethod
    def _chunk(kind, data):
        return struct.pack("!I", len(data))+kind+data+struct.pack("!I", zlib.crc32(kind+data) & 0xffffffff)

    def prepare(self, cells, width, height, scanlines=False):
        pixels = self.indices(cells, width, height, scanlines)
        rows = b"".join(b"\0"+pixels[y*width:(y+1)*width] for y in range(height))
        self.header = b"\x89PNG\r\n\x1a\n"+self._chunk(b"IHDR", struct.pack("!2I5B", width, height, 8, 3, 0, 0, 0))
        # Small local textures favor decode speed over file compression.
        self.body = self._chunk(b"IDAT", zlib.compress(rows, 0))+self._chunk(b"IEND", b"")

    def image_bytes(self, background, accent, strength=1.0):
        key = background, accent, strength
        if key not in self.palette_cache:
            a = tuple(int(background[i:i+2], 16) for i in (1, 3, 5))
            b = tuple(int(accent[i:i+2], 16) for i in (1, 3, 5))
            palette = bytes(round(low+(high-low)*v*strength/255) for v in range(256) for low, high in zip(a, b))
            self.palette_cache[key] = self._chunk(b"PLTE", palette)
        return self.header+self.palette_cache[key]+self.body
