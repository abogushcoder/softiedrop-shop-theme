#!/usr/bin/env python3
"""Structural checks for the Softie Drop theme (no Shopify needed):
JSON files parse; every {% schema %} parses; block tags are balanced; every section, snippet and
asset that is referenced exists; template/group settings and block types exist in the section schema."""
import json, os, re, sys
root = sys.argv[1]; errs = []; warn = []
def rd(p): return open(os.path.join(root, p), encoding='utf-8').read()
def strip_json_comment(s): return re.sub(r'^\s*/\*.*?\*/', '', s, flags=re.S)
files = [os.path.join(d, f)[len(root)+1:] for d, _, fs in os.walk(root) for f in fs if not d.startswith(os.path.join(root, '.git')) and not d.startswith(os.path.join(root, 'catalog'))]
# 1 JSON
for f in files:
    if f.endswith('.json'):
        try: json.loads(strip_json_comment(rd(f)))
        except Exception as e: errs.append(f'{f}: bad JSON ({e})')
# 2 schemas + tag balance
PAIRS = {'if':'endif','unless':'endunless','for':'endfor','case':'endcase','capture':'endcapture','form':'endform',
         'comment':'endcomment','schema':'endschema','style':'endstyle','javascript':'endjavascript','stylesheet':'endstylesheet',
         'paginate':'endpaginate','raw':'endraw','tablerow':'endtablerow'}
schemas = {}
for f in files:
    if not f.endswith('.liquid'): continue
    s = rd(f)
    if '{% schema %}' in s:
        try: schemas[f] = json.loads(s[s.index('{% schema %}')+12:s.index('{% endschema %}')])
        except Exception as e: errs.append(f'{f}: schema JSON ({e})')
    body = re.sub(r'\{%-?\s*comment\s*-?%\}.*?\{%-?\s*endcomment\s*-?%\}', '', s, flags=re.S)
    body = re.sub(r'\{%-?\s*raw\s*-?%\}.*?\{%-?\s*endraw\s*-?%\}', '', body, flags=re.S)
    body = re.sub(r'\{%-?\s*schema\s*-?%\}.*?\{%-?\s*endschema\s*-?%\}', '', body, flags=re.S)
    tokens = []
    for m in re.finditer(r'\{%-?\s*(liquid\b.*?|[a-z_]+)(?:\s.*?)?-?%\}', body, flags=re.S):
        inner = m.group(1)
        if inner.startswith('liquid'):
            for line in inner[6:].split('\n'):
                w = line.strip().split(' ')[0] if line.strip() else ''
                if w: tokens.append(w)
        else: tokens.append(inner)
    stack = []
    for t in tokens:
        if t in PAIRS: stack.append(t)
        elif t in PAIRS.values():
            if not stack or PAIRS[stack[-1]] != t: errs.append(f'{f}: unexpected {t} (open: {stack[-3:]})'); break
            stack.pop()
    else:
        if stack: errs.append(f'{f}: unclosed {stack}')
# 3 references
names = {os.path.basename(f) for f in files}
for f in files:
    if not f.endswith(('.liquid', '.json')): continue
    s = rd(f).replace('\\"', '"')
    for m in re.finditer(r"\{%-?\s*render\s+'([^']+)'", s):
        if f'{m.group(1)}.liquid' not in names: errs.append(f"{f}: render '{m.group(1)}' has no snippet")
    for m in re.finditer(r"render\s+'([^']+)'", s):
        if f'{m.group(1)}.liquid' not in names: errs.append(f"{f}: render '{m.group(1)}' has no snippet")
    for m in re.finditer(r"\{%-?\s*section\s+'([^']+)'", s):
        if f'{m.group(1)}.liquid' not in names: errs.append(f"{f}: section '{m.group(1)}' missing")
    for m in re.finditer(r"'([\w.-]+\.(?:css|js|svg|png))'\s*\|\s*(?:asset_url|inline_asset_content)", s):
        if not os.path.exists(os.path.join(root, 'assets', m.group(1))): errs.append(f"{f}: asset {m.group(1)} missing")
# 4 templates and section groups against schemas
def check_section(where, sec):
    t = sec.get('type', '')
    if t.startswith('apps') or t == '@app': return
    if not os.path.exists(os.path.join(root, 'sections', f'{t}.liquid')): errs.append(f'{where}: section type "{t}" does not exist'); return
    sch = schemas.get(f'sections/{t}.liquid')
    if sch is None: return
    ids = {x['id'] for x in sch.get('settings', []) if 'id' in x}
    for k in sec.get('settings', {}): 
        if k not in ids: errs.append(f'{where}: setting "{k}" not in {t} schema')
    btypes = {b['type']: {x['id'] for x in b.get('settings', []) if 'id' in x} for b in sch.get('blocks', [])}
    for bid, b in sec.get('blocks', {}).items():
        if b['type'] not in btypes and '@app' not in btypes: errs.append(f'{where}: block type "{b["type"]}" not allowed in {t}'); continue
        for k in b.get('settings', {}):
            if b['type'] in btypes and k not in btypes[b['type']]: errs.append(f'{where}: block {bid} setting "{k}" not in {t}/{b["type"]}')
    order = sec.get('block_order')
    if order is not None and set(order) != set(sec.get('blocks', {})): errs.append(f'{where}: block_order does not match blocks')
for f in files:
    if (f.startswith('templates/') and f.endswith('.json')) or (f.startswith('sections/') and f.endswith('.json')):
        d = json.loads(strip_json_comment(rd(f)))
        for k, sec in d.get('sections', {}).items(): check_section(f'{f} [{k}]', sec)
        if set(d.get('order', [])) != set(d.get('sections', {})): errs.append(f'{f}: order does not match sections')
# 5 theme settings used by Softie code exist
gs = {x['id'] for g in json.loads(rd('config/settings_schema.json')) for x in g.get('settings', []) if 'id' in x}
for f in files:
    if f.endswith('.liquid') and ('softie' in f or 'squish' in f or 'texture' in f or 'live-' in f or 'free-shipping' in f or 'next-live' in f):
        for m in re.finditer(r'settings\.(softie_\w+)', rd(f)):
            if m.group(1) not in gs: errs.append(f'{f}: theme setting {m.group(1)} missing')
cur = json.loads(rd('config/settings_data.json'))['current']
for k in cur:
    if k not in gs and k not in ('color_schemes', 'sections', 'content_for_index', 'blocks'): warn.append(f'settings_data: "{k}" is not a theme setting')

# 6 values Shopify itself rejects: link defaults, range steps, select options
def _fits(d, v):
    t = d.get('type')
    if t == 'range':
        k = (v - d['min']) / d['step']
        return d['min'] <= v <= d['max'] and abs(k - round(k)) < 1e-9
    if t in ('select', 'radio'): return v in [o['value'] for o in d['options']]
    return True
schema_all = json.loads(rd('config/settings_schema.json'))
if not schema_all: errs.append('config/settings_schema.json is empty')
for g in schema_all:
    for x in g.get('settings', []):
        if x.get('type') == 'url' and 'default' in x and x['default'] not in ('/collections', '/collections/all'):
            errs.append(f'settings_schema: link setting {x["id"]} may only default to /collections or /collections/all')
gdefs = {x['id']: x for g in schema_all for x in g.get('settings', []) if 'id' in x}
for k, v in json.loads(rd('config/settings_data.json'))['current'].items():
    if k in gdefs and not _fits(gdefs[k], v): errs.append(f'settings_data: {k}={v!r} is not allowed by its setting')
for f, sch in schemas.items():
    for x in sch.get('settings', []) + [y for b in sch.get('blocks', []) for y in b.get('settings', [])]:
        if x.get('type') == 'url' and 'default' in x and x['default'] not in ('/collections', '/collections/all'):
            errs.append(f'{f}: link setting {x.get("id")} has a default Shopify rejects')
        if 'default' in x and x.get('type') in ('range', 'select', 'radio') and not _fits(x, x['default']):
            errs.append(f'{f}: default of {x.get("id")} is not allowed')
print(f'{len(files)} files checked, {len(schemas)} schemas')
for w in warn: print('warn:', w)
for e in errs: print('ERROR:', e)
sys.exit(1 if errs else 0)
