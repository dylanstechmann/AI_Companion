import struct
import zlib
import os
from pathlib import Path

def create_png(width: int, height: int, path: Path):
    png_sig = b'\x89PNG\r\n\x1a\n'
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    ihdr_crc = struct.pack('>I', zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff)
    ihdr_chunk = struct.pack('>I', len(ihdr_data)) + b'IHDR' + ihdr_data + ihdr_crc

    raw_rows = []
    cx, cy = width / 2.0, height / 2.0
    r_max = width * 0.38
    for y in range(height):
        row = bytearray(b'\x00')
        for x in range(width):
            dx = x - cx
            dy = y - cy
            dist = (dx * dx + dy * dy) ** 0.5
            if dist <= r_max:
                t = dist / r_max
                r = int(147 * (1.0 - t * 0.5))
                g = int(129 * (1.0 - t * 0.3) + 200 * t * 0.3)
                b = 255
            else:
                r, g, b = 10, 10, 26
            row.extend((r, g, b))
        raw_rows.append(bytes(row))

    compressed = zlib.compress(b''.join(raw_rows), 9)
    idat_crc = struct.pack('>I', zlib.crc32(b'IDAT' + compressed) & 0xffffffff)
    idat_chunk = struct.pack('>I', len(compressed)) + b'IDAT' + compressed + idat_crc

    iend_crc = struct.pack('>I', zlib.crc32(b'IEND') & 0xffffffff)
    iend_chunk = struct.pack('>I', 0) + b'IEND' + iend_crc

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'wb') as f:
        f.write(png_sig + ihdr_chunk + idat_chunk + iend_chunk)

def main():
    root = Path(__file__).resolve().parents[1]
    icons_dir = root / "public" / "icons"
    create_png(192, 192, icons_dir / "icon-192x192.png")
    create_png(512, 512, icons_dir / "icon-512x512.png")
    print(f"Generated icons in {icons_dir}")

if __name__ == "__main__":
    main()
