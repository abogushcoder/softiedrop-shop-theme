#!/usr/bin/env python3
"""
Softie Drop: make square 2048 px product photos.

  python3 square_photos.py photos-in/ photos-out/

photos-in has one subfolder per design, named like the design (e.g. "Lazy Cat"). Each photo is padded
(never cropped) to a square on a background matched to the photo's own edges, resized to 2048 x 2048 and
saved as photos-out/<handle>/<handle>-1.jpg, -2.jpg ... in file-name order (case-insensitive). <handle> is
the same web address sheet_to_csv.py makes from the design name, so the two line up.
Each design's output folder is emptied first, so removed photos don't linger. EXIF rotation is applied,
transparent areas become white, the color profile is kept. iPhone HEIC photos need the pillow-heif package;
without it they are skipped with a message (export them as JPEG instead).
"""
import os, sys
from PIL import Image, ImageOps
from sheet_to_csv import slug

SIZE, SMALL = 2048, 800
EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff', '.heic', '.heif')
try:
    from pillow_heif import register_heif_opener
    register_heif_opener(); HEIC = True
except ImportError:
    HEIC = False

def to_rgb(im):
    if im.mode in ('I;16', 'I;16B', 'I;16L', 'I'):            # 16/32-bit grayscale: scale down to 8-bit
        lo, hi = im.getextrema()
        im = im.point(lambda v: (v - lo) * 255 / max(1, hi - lo)).convert('L')
    if im.mode in ('RGBA', 'LA', 'PA') or (im.mode == 'P' and 'transparency' in im.info):
        im = im.convert('RGBA')
        bg = Image.new('RGB', im.size, (255, 255, 255))
        bg.paste(im, mask=im.getchannel('A'))
        return bg
    return im.convert('RGB')

def edge_color(im):
    w, h = im.size
    px = [im.getpixel((x, y)) for x in (0, w // 2, w - 1) for y in (0, h - 1)] + [im.getpixel((0, h // 2)), im.getpixel((w - 1, h // 2))]
    return tuple(sorted(c[i] for c in px)[len(px) // 2] for i in range(3))   # median of the edges

def square(path):
    src = Image.open(path)
    icc = src.info.get('icc_profile')
    im = to_rgb(ImageOps.exif_transpose(src))
    w, h = im.size
    side = max(w, h)
    canvas = Image.new('RGB', (side, side), edge_color(im))
    canvas.paste(im, ((side - w) // 2, (side - h) // 2))
    return canvas.resize((SIZE, SIZE), Image.LANCZOS), icc, min(w, h)

def main(src, dst):
    done = skipped = 0
    folders = sorted((f for f in os.listdir(src) if os.path.isdir(os.path.join(src, f))), key=str.lower)
    seen = {}
    for folder in folders:
        h = slug(folder)
        if not h:
            print(f'Skipped folder "{folder}": its name needs a letter or number from A-Z or 0-9.'); continue
        if h in seen:
            print(f'Skipped folder "{folder}": it makes the same web address as "{seen[h]}". Rename one.'); continue
        seen[h] = folder
        p = os.path.join(src, folder)
        files = sorted((f for f in os.listdir(p) if f.lower().endswith(EXTS) and not f.startswith('.')), key=str.lower)
        out = os.path.join(dst, h); os.makedirs(out, exist_ok=True)
        for old in os.listdir(out):                                  # start clean for this design
            if old.lower().endswith('.jpg'): os.remove(os.path.join(out, old))
        n = 0
        for f in files:
            if f.lower().endswith(('.heic', '.heif')) and not HEIC:
                print(f'Skipped {folder}/{f}: HEIC needs the pillow-heif package; export it as JPEG instead.'); skipped += 1; continue
            try:
                im, icc, short = square(os.path.join(p, f))
            except Exception as e:
                print(f'Skipped {folder}/{f}: {e}'); skipped += 1; continue
            if short < SMALL:
                print(f'Check {folder}/{f}: only {short} px on its short side, so it will look soft when enlarged.')
            n += 1
            im.save(os.path.join(out, f'{h}-{n}.jpg'), 'JPEG', quality=85, optimize=True, progressive=True, icc_profile=icc)
            done += 1
        print(f'{folder}: {n} photo(s) -> {out}')
    print(f'Done: {done} photos squared, {skipped} skipped.')

if __name__ == '__main__':
    if len(sys.argv) != 3: print(__doc__); sys.exit(2)
    main(sys.argv[1], sys.argv[2])
