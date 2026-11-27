#!/usr/bin/env python3
"""
Softie Drop: make square 2048 px product photos.

  python3 square_photos.py photos-in/ photos-out/

photos-in has one subfolder per design. Each photo is padded (never cropped) to a square on a
background matched to the photo's own edges, resized to 2048 x 2048, and saved as 1.jpg, 2.jpg ...
in photos-out/<design-folder-slug>/, in file-name order. EXIF rotation is applied first.
"""
import os, re, sys
from PIL import Image, ImageOps

SIZE = 2048
EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.heic', '.tif', '.tiff')

def slug(t):
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', t.lower())).strip('-')

def edge_color(im):
    w, h = im.size
    px = [im.getpixel((x, y)) for x in (0, w // 2, w - 1) for y in (0, h - 1)] + [im.getpixel((0, h // 2)), im.getpixel((w - 1, h // 2))]
    return tuple(sorted(c[i] for c in px)[len(px) // 2] for i in range(3))   # median of the edges

def square(path):
    im = ImageOps.exif_transpose(Image.open(path)).convert('RGB')
    w, h = im.size
    side = max(w, h)
    canvas = Image.new('RGB', (side, side), edge_color(im))
    canvas.paste(im, ((side - w) // 2, (side - h) // 2))
    return canvas.resize((SIZE, SIZE), Image.LANCZOS)

def main(src, dst):
    done = skipped = 0
    for folder in sorted(os.listdir(src)):
        p = os.path.join(src, folder)
        if not os.path.isdir(p): continue
        files = sorted(f for f in os.listdir(p) if f.lower().endswith(EXTS) and not f.startswith('.'))
        out = os.path.join(dst, slug(folder)); os.makedirs(out, exist_ok=True)
        n = 0
        for f in files:
            try:
                im = square(os.path.join(p, f))
            except Exception as e:
                print(f'Skipped {folder}/{f}: {e}'); skipped += 1; continue
            n += 1; im.save(os.path.join(out, f'{n}.jpg'), 'JPEG', quality=85, optimize=True, progressive=True); done += 1
        print(f'{folder}: {n} photo(s) -> {out}')
    print(f'Done: {done} photos squared, {skipped} skipped.')

if __name__ == '__main__':
    if len(sys.argv) != 3: print(__doc__); sys.exit(2)
    main(sys.argv[1], sys.argv[2])
