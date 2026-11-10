# Logos Terminal app icon

The phosphor-green hexagonal L mark follows the supplied reference. The app uses the PNG on Tk platforms and the ICO on Windows, including inherited dialog icons. The black tile keeps the green outline readable on desktop surfaces.

- logos-terminal.png: 256 x 256.
- logos-terminal-512.png: 512 x 512.
- logos-terminal.ico: 16, 24, 32, 48, 64, 128 and 256 pixel entries. Small sizes use native DIB data; the 256 pixel entry uses PNG.

To rebuild the size/format package on Windows, run tools/build_icons.ps1 with -SourcePng assets/icons/logos-terminal-512.png. Runtime use needs no graphics dependency.
