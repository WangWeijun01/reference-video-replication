"""Validate local files, ranges and references in a material-delivery.json."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('manifest',type=Path)
    a=ap.parse_args()
    d=json.loads(a.manifest.read_text(encoding='utf-8'))
    assets={x['asset_id']:x for x in d['assets']}
    ranges={x['id']:x for x in d['ranges']}
    lines={x['line_id']:x for x in d['mapping']}
    errors=[]
    if len(assets)!=len(d['assets']) or len(ranges)!=len(d['ranges']) or len(lines)!=len(d['mapping']):
        errors.append('Duplicate IDs')
    for aid,x in assets.items():
        p=Path(x['path'])
        if not p.is_file() or p.stat().st_size==0:
            errors.append(f'{aid}: file missing or empty')
            continue
        if p.stat().st_size!=x['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=x['sha256']:
            errors.append(f'{aid}: content no longer matches manifest')
        if not {'audio','video'}.issubset({s['codec_type'] for s in x['streams']}):
            errors.append(f'{aid}: expected audio and video streams')
    for sid,r in ranges.items():
        if r['asset_id'] not in assets or not 0<=r['in']<r['out']<=assets[r['asset_id']]['duration']:
            errors.append(f'{sid}: invalid asset or range')
        if any(n not in lines for n in r['line_ids']):
            errors.append(f'{sid}: unknown line reference')
    for lid,line in lines.items():
        for sid in line['shot_ids']:
            if sid not in ranges or lid not in ranges[sid]['line_ids']:
                errors.append(f'Line {lid}: inconsistent shot reference {sid}')
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'PASS: {len(assets)} local assets, {len(ranges)} ranges, {len(lines)} lines; scene meaning still requires review.')


if __name__=='__main__':
    main()
