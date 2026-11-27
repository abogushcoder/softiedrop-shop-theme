#!/usr/bin/env python3
"""
Softie Drop: turn the owner's product sheet into a Shopify product import CSV.

  python3 sheet_to_csv.py product-sheet.csv shopify-products.csv [--image-base-url https://.../photos --photos-dir photos-out]

Reads the sheet (columns as in product-sheet-template.csv) and writes Shopify's product CSV:
one product per design, one variant, store inventory only, no compare-at price ever.
Metafields written (create these definitions in Shopify first, see README):
  softie.squish_meter  integer 1-5        (shown as the squish meter)
  softie.live_price    money              (admin only; never shown on the storefront)
  softie.size_cm       decimal number     (shown as a size pill)
  softie.safety_note   single line text   (shown under the notes, only if filled in)
Photos: Shopify imports images from web addresses only. With --image-base-url, each product gets
<base>/<photo-folder>/1.jpg, 2.jpg ... (the files square_photos.py makes). Without it, add photos in the admin.
Stops with a clear list of problems instead of writing a half-right file.
"""
import csv, html, json, re, sys, os

TEXTURES = {'foam': 'Foam', 'mochi & silicone': 'Mochi & silicone', 'mochi': 'Mochi & silicone',
            'silicone': 'Mochi & silicone', 'mochi and silicone': 'Mochi & silicone', 'gel': 'Gel'}
SHOPIFY_COLS = ['Handle', 'Title', 'Body (HTML)', 'Vendor', 'Type', 'Tags', 'Published', 'Status',
    'Option1 Name', 'Option1 Value', 'Variant SKU', 'Variant Grams', 'Variant Inventory Tracker', 'Variant Inventory Qty',
    'Variant Inventory Policy', 'Variant Fulfillment Service', 'Variant Price', 'Variant Compare At Price',
    'Variant Requires Shipping', 'Variant Taxable', 'Variant Weight Unit', 'Image Src', 'Image Position', 'Image Alt Text',
    'SEO Title', 'SEO Description', 'Gift Card',
    'Squish meter (product.metafields.softie.squish_meter)',
    'Live price (product.metafields.softie.live_price)',
    'Size cm (product.metafields.softie.size_cm)',
    'Safety note (product.metafields.softie.safety_note)']

def money(v):
    s = str(v).strip().replace('$', '').replace(',', '')
    return round(float(s), 2) if s else None

def slug(t):
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', t.lower())).strip('-')

def pick(row, *names):
    for k, v in row.items():
        kk = (k or '').strip().lower()
        if any(kk.startswith(n) for n in names):
            return (v or '').strip()
    return ''

def convert(rows, image_base=None, photo_counts=None):
    problems, warnings, out, handles = [], [], [], set()
    for i, row in enumerate(rows, start=2):
        if not any((v or '').strip() for v in row.values()):
            continue
        name = pick(row, 'design name')
        where = f'Row {i} ({name or "no name"})'
        if not name: problems.append(f'{where}: design name is empty'); continue
        tex = TEXTURES.get(pick(row, 'texture').lower())
        if not tex: problems.append(f'{where}: texture must be Foam, Mochi & silicone or Gel (got "{pick(row, "texture")}")')
        try: rating = int(float(pick(row, 'slow-rise') or 0))
        except ValueError: rating = 0
        if not 1 <= rating <= 5: problems.append(f'{where}: slow-rise rating must be a whole number from 1 to 5')
        try:
            live, store = money(pick(row, 'typical live')), money(pick(row, 'store price'))
        except ValueError:
            problems.append(f'{where}: prices must be numbers like 7.99'); continue
        if not store or store <= 0: problems.append(f'{where}: store price is missing')
        if not live or live <= 0: problems.append(f'{where}: typical live price is missing')
        if live and store:
            gap = (store / live - 1) * 100
            if gap < 50 - 0.5 or gap > 75 + 0.5:
                warnings.append(f'{where}: store price ${store:.2f} is {gap:.0f}% above the live price ${live:.2f} (plan: 50-75%)')
            cents = round(store * 100) % 100
            if cents not in (99, 0):
                warnings.append(f'{where}: store price ${store:.2f} does not end in .99 or .00')
        units_s = pick(row, 'units set aside')
        try: units = int(float(units_s or 0))
        except ValueError: units = -1
        if units < 0: problems.append(f'{where}: units set aside must be 0 or more')
        try: oz = float(pick(row, 'weight') or 0)
        except ValueError: oz = 0
        if oz <= 0: problems.append(f'{where}: packed weight (oz) is missing')
        size = pick(row, 'size')
        try: size_v = round(float(size), 1) if size else None
        except ValueError: size_v = None; problems.append(f'{where}: size must be a number of cm')
        notes = pick(row, 'squish notes')
        if not notes: warnings.append(f'{where}: squish notes are empty')
        folder = pick(row, 'photo folder')
        safety = pick(row, 'safety')
        handle = slug(name)
        if handle in handles: problems.append(f'{where}: another design has the same name/handle "{handle}"')
        handles.add(handle)
        if problems and problems[-1].startswith(where): continue
        body = ''.join(f'<p>{html.escape(p.strip())}</p>' for p in re.split(r'\n\s*\n|\r\n\s*\r\n', notes) if p.strip())
        base = {c: '' for c in SHOPIFY_COLS}
        base.update({
            'Handle': handle, 'Title': name, 'Body (HTML)': body, 'Vendor': 'Softie Drop', 'Type': tex or '',
            'Tags': ', '.join(t for t in [tex, f'slow-rise-{rating}'] if t), 'Published': 'TRUE', 'Status': 'active',
            'Option1 Name': 'Title', 'Option1 Value': 'Default Title', 'Variant SKU': f'SD-{handle[:24].upper()}',
            'Variant Grams': str(round(oz * 28.3495)), 'Variant Inventory Tracker': 'shopify', 'Variant Inventory Qty': str(max(units, 0)),
            'Variant Inventory Policy': 'deny', 'Variant Fulfillment Service': 'manual', 'Variant Price': f'{store:.2f}',
            'Variant Compare At Price': '',            # never a crossed-out "was" price
            'Variant Requires Shipping': 'TRUE', 'Variant Taxable': 'TRUE', 'Variant Weight Unit': 'oz', 'Gift Card': 'FALSE',
            'SEO Title': f'{name} squishy | Softie Drop', 'SEO Description': re.sub(r'\s+', ' ', notes)[:155],
            'Squish meter (product.metafields.softie.squish_meter)': str(rating),
            'Live price (product.metafields.softie.live_price)': json.dumps({'amount': f'{live:.2f}', 'currency_code': 'USD'}),
            'Size cm (product.metafields.softie.size_cm)': '' if size_v is None else str(size_v),
            'Safety note (product.metafields.softie.safety_note)': safety,
        })
        n = (photo_counts or {}).get(folder, 0) if image_base else 0
        if image_base and folder and n == 0:
            warnings.append(f'{where}: no photos found for folder "{folder}"')
        if n:
            base.update({'Image Src': f'{image_base.rstrip("/")}/{slug(folder)}/1.jpg', 'Image Position': '1', 'Image Alt Text': f'{name} squishy'})
        out.append(base)
        for k in range(2, n + 1):                  # extra photos: image-only rows under the same handle
            extra = {c: '' for c in SHOPIFY_COLS}
            extra.update({'Handle': handle, 'Image Src': f'{image_base.rstrip("/")}/{slug(folder)}/{k}.jpg', 'Image Position': str(k), 'Image Alt Text': f'{name} squishy, photo {k}'})
            out.append(extra)
    designs = sum(1 for r in out if r['Title'])
    if designs >= 20: warnings.append(f'{designs} designs: the plan says under 20 at launch')
    return out, problems, warnings

def main(argv):
    args = [a for a in argv if not a.startswith('--')]
    image_base, photos_dir = None, None
    if '--image-base-url' in argv: image_base = argv[argv.index('--image-base-url') + 1]; args.remove(image_base)
    if '--photos-dir' in argv: photos_dir = argv[argv.index('--photos-dir') + 1]; args.remove(photos_dir)
    if len(args) != 2: print(__doc__); return 2
    with open(args[0], newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    counts = {}                                    # photos per squared folder (made by square_photos.py)
    if photos_dir:
        for folder in os.listdir(photos_dir):
            p = os.path.join(photos_dir, folder)
            if os.path.isdir(p): counts[folder] = len([x for x in os.listdir(p) if x.endswith('.jpg')])
    lookup = {pick(r, 'photo folder'): counts.get(slug(pick(r, 'photo folder')), 0) for r in rows}
    out, problems, warnings = convert(rows, image_base, lookup)
    for w in warnings: print('Check:', w)
    if problems:
        print('\nNot written. Fix these first:'); [print(' -', p) for p in problems]; return 1
    with open(args[1], 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=SHOPIFY_COLS); w.writeheader(); w.writerows(out)
    print(f'Wrote {args[1]}: {sum(1 for r in out if r["Title"])} designs, {sum(1 for r in out if r["Image Src"])} photo links.')
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
