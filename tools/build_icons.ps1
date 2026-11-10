param([Parameter(Mandatory=$true)][string]$SourcePng)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$iconRoot = Join-Path (Split-Path $PSScriptRoot -Parent) 'assets\icons'
New-Item -ItemType Directory -Path $iconRoot -Force | Out-Null
$source = [System.Drawing.Image]::FromFile((Resolve-Path -LiteralPath $SourcePng))
$frames = [System.Collections.Generic.List[object]]::new()
try {
    foreach ($size in @(16,24,32,48,64,128,256,512)) {
        $bitmap = [System.Drawing.Bitmap]::new($size, $size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
            $graphics.DrawImage($source, 0, 0, $size, $size)
            $memory = [System.IO.MemoryStream]::new()
            try {
                $bitmap.Save($memory, [System.Drawing.Imaging.ImageFormat]::Png)
                $bytes = $memory.ToArray()
                if ($size -lt 256) {
                    # Small ICO entries use DIB data for native Tk/Windows readers.
                    $bmpStream = [System.IO.MemoryStream]::new()
                    try {
                        $bitmap.Save($bmpStream, [System.Drawing.Imaging.ImageFormat]::Bmp)
                        $bmpBytes = $bmpStream.ToArray()
                        $maskBytes = [int]([math]::Ceiling($size/32)*4*$size)
                        $dib = [byte[]]::new($bmpBytes.Length-14+$maskBytes)
                        [Array]::Copy($bmpBytes, 14, $dib, 0, $bmpBytes.Length-14)
                        [BitConverter]::GetBytes([int]($size*2)).CopyTo($dib, 8)
                        $frames.Add(@{Size=$size; Bytes=$dib})
                    } finally { $bmpStream.Dispose() }
                } elseif ($size -eq 256) { $frames.Add(@{Size=$size; Bytes=$bytes}) }
                if ($size -eq 256) { [System.IO.File]::WriteAllBytes((Join-Path $iconRoot 'logos-terminal.png'), $bytes) }
                if ($size -eq 512) { [System.IO.File]::WriteAllBytes((Join-Path $iconRoot 'logos-terminal-512.png'), $bytes) }
            } finally { $memory.Dispose() }
        } finally { $graphics.Dispose(); $bitmap.Dispose() }
    }
    $stream = [System.IO.File]::Create((Join-Path $iconRoot 'logos-terminal.ico'))
    $writer = [System.IO.BinaryWriter]::new($stream)
    try {
        $writer.Write([UInt16]0); $writer.Write([UInt16]1); $writer.Write([UInt16]$frames.Count)
        $offset = 6 + 16*$frames.Count
        foreach ($frame in $frames) {
            $dimension = if ($frame.Size -eq 256) { 0 } else { $frame.Size }
            $writer.Write([byte]$dimension); $writer.Write([byte]$dimension)
            $writer.Write([byte]0); $writer.Write([byte]0)
            $writer.Write([UInt16]1); $writer.Write([UInt16]32)
            $writer.Write([UInt32]$frame.Bytes.Length); $writer.Write([UInt32]$offset)
            $offset += $frame.Bytes.Length
        }
        foreach ($frame in $frames) { $writer.Write([byte[]]$frame.Bytes) }
    } finally { $writer.Dispose(); $stream.Dispose() }
} finally { $source.Dispose() }
Write-Output 'Created PNG and multi-size Windows ICO assets.'
