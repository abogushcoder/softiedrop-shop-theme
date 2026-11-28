#!/usr/bin/env python3
"""
Softie Drop: turn the owner's product sheet into a Shopify product import CSV.

  python3 sheet_to_csv.py product-sheet.csv shopify-products.csv [--image-base-url https://.../photos --photos-dir photos-out]

Reads the sheet (columns as in product-sheet-template.csv; save it as "CSV UTF-8" if you can) and writes
Shopify's product CSV: one product per design, one variant, store inventory only, no compare-at price ever.
Metafields written (create these definitions in Shopify first: Settings > Custom data > Products):
  softie.squish_meter  Integer 1-5         (shown as the squish meter)
  softie.live_price    Money               (admin only; never shown on the storefront) e.g. "8.00 USD"
  softie.size_cm       Decimal             (shown as a size pill)
  softie.safety_note   Single line text    (shown under the notes, only if filled in)
Photos: Shopify imports images from web addresses only. With --image-base-url and --photos-dir, each product
gets <base>/<handle>/<handle>-1.jpg, -2.jpg ... (the files square_photos.py makes). Without them, add photos
in the admin. Stops with a clear list of problems instead of writing a half-right file.
"""
import csv, html, io, os, re, sys, unicodedata

TEXTURES = {'foam': 'Foam', 'mochi & silicone': 'Mochi & silicone', 'mochi': 'Mochi & silicone',
            'silicone': 'Mochi & silicone', 'mochi and silicone': 'Mochi & silicone', 'gel': 'Gel'}
CURRENCY = 'USD'          # must match the store currency
SHOPIFY_COLS = ['Handle', 'Title', 'Body (HTML)', 'Vendor', 'Type', 'Tags', 'Published', 'Status',
    'Option1 Name', 'Option1 Value', 'Variant SKU', 'Variant Grams', 'Variant Inventory Tracker', 'Variant Inventory Qty',
    'Variant Inventory Policy', 'Variant Fulfillment Service', 'Variant Price', 'Variant Compare At Price',
    'Variant Requires Shipping', 'Variant Taxable', 'Variant Weight Unit', 'Image Src', 'Image Position', 'Image Alt Text',
    'SEO Title', 'SEO Description', 'Gift Card',
    'Squish meter (product.metafields.softie.squish_meter)',
    'Live price (product.metafields.softie.live_price)',
    'Size cm (product.metafields.softie.size_cm)',
    'Safety note (product.metafields.softie.safety_note)']

def slug(t):
    """URL handle: accents folded to plain letters (Café -> cafe), anything else becomes '-'."""
    t = unicodedata.normalize('NFKD', t)
    t = ''.join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', t)).strip('-')

def money(v):
    s = str(v).strip().replace('$', '').replace(',', '')
    return round(float(s), 2) if s else None

def whole(v):
    """'4' or '4.0' -> 4; '4.5', 'x' or blank -> None."""
    try:
        f = float(str(v).strip())
    except ValueError:
        return None
    return int(f) if f == int(f) else None

def one_line(t):
    return re.sub(r'\s+', ' ', t).strip()

def pick(row, *names):
    for k, v in row.items():
        if k is None: continue                      # extra cells past the last header
        kk = k.strip().lower()
        if any(kk.startswith(n) for n in names):
            return (v or '').strip()
    return ''

def seo_title(name):
    t = f'{name} squishy | Softie Drop'
    return t if len(t) <= 70 else (name[:67].rstrip() + '...')

def notes_html(notes):
    paras = [p.strip() for p in re.split(r'\r?\n\s*\r?\n', notes) if p.strip()]
    return ''.join('<p>' + '<br>'.join(html.escape(line.strip()) for line in p.splitlines() if line.strip()) + '</p>' for p in paras)

def convert(rows, image_base=None, photos=None):
    problems, warnings, out, handles, skus = [], [], [], set(), set()
    for i, row in enumerate(rows, start=2):
        if not any(isinstance(v, str) and v.strip() for k, v in row.items() if k is not None):
            continue                                  # blank row
        name = one_line(pick(row, 'design name'))
        where = f'Row {i} ({name or "no name"})'
        mine = []
        if not name:
            problems.append(f'{where}: design name is empty'); continue
        handle = slug(name)
        if not handle: mine.append('the name needs at least one letter or number from A-Z or 0-9 to make a web address')
        elif handle in handles: mine.append(f'another design has the same web address "{handle}"; make the names more different')
        tex = TEXTURES.get(pick(row, 'texture').lower())
        if not tex: mine.append(f'texture must be Foam, Mochi & silicone or Gel (got "{pick(row, "texture")}")')
        rating = whole(pick(row, 'slow-rise'))
        if rating is None or not 1 <= rating <= 5: mine.append('slow-rise rating must be a whole number from 1 to 5')
        try:
            live, store = money(pick(row, 'typical live')), money(pick(row, 'store price'))
        except ValueError:
            live = store = None; mine.append('prices must be numbers like 7.99')
        else:
            if not store or store <= 0: mine.append('store price is missing')
            if not live or live <= 0: mine.append('typical live price is missing')
        units = whole(pick(row, 'units set aside') or '0')
        if units is None or units < 0: mine.append('units set aside must be a whole number, 0 or more')
        try: oz = float(pick(row, 'weight') or 0)
        except ValueError: oz = 0
        if oz <= 0: mine.append('packed weight (oz) is missing')
        size = pick(row, 'size')
        try: size_v = round(float(size), 1) if size else None
        except ValueError: size_v = None; mine.append('size must be a number of cm')
        if mine:
            problems += [f'{where}: {m}' for m in mine]; continue
        handles.add(handle)
        gap = (store / live - 1) * 100
        if gap < 49.5 or gap > 75.5:
            warnings.append(f'{where}: store price ${store:.2f} is {gap:.0f}% above the live price ${live:.2f} (plan: 50-75%)')
        if round(store * 100) % 100 not in (99, 0):
            warnings.append(f'{where}: store price ${store:.2f} does not end in .99 or .00')
        notes = pick(row, 'squish notes')
        if not notes: warnings.append(f'{where}: squish notes are empty')
        safety = one_line(pick(row, 'safety'))
        sku = f'SD-{handle.upper()}'[:60]
        n = 2
        while sku in skus: sku = f'SD-{handle.upper()}'[:56] + f'-{n}'; n += 1
        skus.add(sku)
        if len(seo_title(name)) < len(f'{name} squishy | Softie Drop'):
            warnings.append(f'{where}: name is long, so the search-engine title was shortened to 70 characters')
        base = {c: '' for c in SHOPIFY_COLS}
        base.update({
            'Handle': handle, 'Title': name, 'Body (HTML)': notes_html(notes), 'Vendor': 'Softie Drop', 'Type': tex,
            'Tags': f'{tex}, slow-rise-{rating}', 'Published': 'TRUE', 'Status': 'active',
            'Option1 Name': 'Title', 'Option1 Value': 'Default Title', 'Variant SKU': sku,
            'Variant Grams': str(round(oz * 28.3495)), 'Variant Inventory Tracker': 'shopify', 'Variant Inventory Qty': str(units),
            'Variant Inventory Policy': 'deny', 'Variant Fulfillment Service': 'manual', 'Variant Price': f'{store:.2f}',
            'Variant Compare At Price': '',            # never a crossed-out "was" price
            'Variant Requires Shipping': 'TRUE', 'Variant Taxable': 'TRUE', 'Variant Weight Unit': 'oz', 'Gift Card': 'FALSE',
            'SEO Title': seo_title(name), 'SEO Description': one_line(notes)[:155],
            'Squish meter (product.metafields.softie.squish_meter)': str(rating),
            'Live price (product.metafields.softie.live_price)': f'{live:.2f} {CURRENCY}',   # Shopify CSV money format, e.g. "5.99 CAD"
            'Size cm (product.metafields.softie.size_cm)': '' if size_v is None else f'{size_v:g}',
            'Safety note (product.metafields.softie.safety_note)': safety,
        })
        files = (photos or {}).get(handle, []) if image_base else []
        if image_base and not files:
            warnings.append(f'{where}: no squared photos found for this design')
        if files:
            base.update({'Image Src': f'{image_base.rstrip("/")}/{handle}/{files[0]}', 'Image Position': '1', 'Image Alt Text': f'{name} squishy'})
        out.append(base)
        for k, f in enumerate(files[1:], start=2):     # extra photos: image-only rows under the same handle
            extra = {c: '' for c in SHOPIFY_COLS}
            extra.update({'Handle': handle, 'Image Src': f'{image_base.rstrip("/")}/{handle}/{f}', 'Image Position': str(k), 'Image Alt Text': f'{name} squishy, photo {k}'})
            out.append(extra)
    designs = sum(1 for r in out if r['Title'])
    if designs >= 20: warnings.append(f'{designs} designs: the plan says under 20 at launch')
    return out, problems, warnings

def read_sheet(path):
    raw = open(path, 'rb').read()
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('cp1252')                    # Excel's plain "CSV" export
        print('Note: the sheet was not saved as UTF-8, read it as Windows text. "CSV UTF-8" is safer.')
    return list(csv.DictReader(io.StringIO(text, newline='')))      # keeps line breaks inside cells

def find_photos(photos_dir):
    """{handle: [handle-1.jpg, handle-2.jpg, ...]} from square_photos.py output."""
    found = {}
    if photos_dir and os.path.isdir(photos_dir):
        for folder in os.listdir(photos_dir):
            p = os.path.join(photos_dir, folder)
            if os.path.isdir(p):
                files = [f for f in os.listdir(p) if re.fullmatch(re.escape(folder) + r'-\d+\.jpg', f)]
                found[folder] = sorted(files, key=lambda f: int(f.rsplit('-', 1)[1][:-4]))
    return found

def main(argv):
    args, opts = [], {}
    it = iter(argv)
    for a in it:
        if a in ('--image-base-url', '--photos-dir'): opts[a] = next(it, '')
        else: args.append(a)
    if len(args) != 2: print(__doc__); return 2
    if bool(opts.get('--image-base-url')) != bool(opts.get('--photos-dir')):
        print('Use --image-base-url and --photos-dir together.'); return 2
    rows = read_sheet(args[0])
    out, problems, warnings = convert(rows, opts.get('--image-base-url'), find_photos(opts.get('--photos-dir')))
    for w in warnings: print('Check:', w)
    if problems:
        print('\nNot written. Fix these first:'); [print(' -', p) for p in problems]; return 1
    with open(args[1], 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=SHOPIFY_COLS, lineterminator='\n'); w.writeheader(); w.writerows(out)
    print(f'Wrote {args[1]}: {sum(1 for r in out if r["Title"])} designs, {sum(1 for r in out if r["Image Src"])} photo links.')
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
