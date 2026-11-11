"""Expose bundled OFL fonts to this process; never install system-wide fonts."""
import ctypes
import ctypes.util
import json
import os
from pathlib import Path

_loaded = set()
_families = set()
_memory_resources = []


def load_bundled_fonts(folder):
    folder = Path(folder)
    try:
        names = json.loads((folder / "font-families.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        names = {}
    paths = [path.resolve() for path in sorted(folder.rglob("*.ttf")) if path.resolve() not in _loaded]
    if not paths:
        return set(_families)
    def remember(path):
        _loaded.add(path)
        name = names.get(path.relative_to(folder.resolve()).as_posix())
        if isinstance(name, str):
            _families.add(name)
    try:
        if os.name == "nt":
            add = ctypes.windll.gdi32.AddFontResourceExW
            add.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
            add.restype = ctypes.c_int
            memory = ctypes.windll.gdi32.AddFontMemResourceEx
            memory.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
            memory.restype = ctypes.c_void_p
            for path in paths:
                if add(str(path), 0x10, None):  # FR_PRIVATE: this process only.
                    remember(path)
                else:
                    # Memory resources also work when GDI cannot read a virtual path.
                    # These fonts are private and are not enumerated by Tk families().
                    data = path.read_bytes()
                    buffer = ctypes.create_string_buffer(data)
                    count = ctypes.c_uint()
                    handle = memory(buffer, len(data), None, ctypes.byref(count))
                    if handle:
                        _memory_resources.append((handle, buffer))
                        remember(path)
        elif os.name == "posix":
            library = ctypes.util.find_library("fontconfig")
            if not library:
                return set(_families)
            config = ctypes.CDLL(library)
            config.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            config.FcConfigAppFontAddFile.restype = ctypes.c_int
            for path in paths:
                if config.FcConfigAppFontAddFile(None, os.fsencode(path)):
                    remember(path)
    except (OSError, AttributeError):
        # Theme family lists retain native fallbacks on unsupported platforms.
        pass
    return set(_families)
