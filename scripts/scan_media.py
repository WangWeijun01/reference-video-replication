"""Inventory local media and make second-indexed visual review sheets."""
import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('video', type=Path)
    ap.add_argument('output', type=Path)
    ap.add_argument('--step', type=int, default=1)
    a = ap.parse_args()
    if a.step < 1:
        ap.error('step must be >= 1')
    if a.output.exists():
        ap.error('Choose a new output directory; existing evidence is preserved')
    a.output.mkdir(parents=True)
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(a.video)], encoding='utf-8'))
    streams = probe.get('streams', [])
    if not any(s['codec_type'] == 'video' for s in streams):
        raise ValueError('No video stream')
    subprocess.run(['ffmpeg','-n','-hide_banner','-loglevel','error','-i',str(a.video),'-vf',f'fps=1/{a.step},scale=432:-2',str(a.output/'frame_%04d.jpg')],check=True)
    frames = sorted(a.output.glob('frame_*.jpg'))
    sheets=[]
    # fps sampling positions are approximate; these labels are not exact source PTS.
    for page in range(math.ceil(len(frames)/20)):
        chunk=frames[page*20:(page+1)*20]
        im=Image.new('RGB',(5*216,4*414),'#202020')
        draw=ImageDraw.Draw(im)
        for j,f in enumerate(chunk):
            thumb=Image.open(f)
            thumb.thumbnail((216,384))
            x,y=(j%5)*216,(j//5)*414
            im.paste(thumb,(x,y+30))
            draw.text((x+6,y+8),f'~{(page*20+j)*a.step:03d} s',fill='white')
        sheet=a.output/f'contact_{page:02d}.jpg'
        im.save(sheet,quality=90)
        sheets.append(str(sheet.resolve()))
    sha=hashlib.sha256()
    with a.video.open('rb') as f:
        for c in iter(lambda:f.read(1024*1024),b''):
            sha.update(c)
    data=dict(path=str(a.video.resolve()),bytes=a.video.stat().st_size,sha256=sha.hexdigest(),
              duration=float(probe['format']['duration']),streams=streams,step_seconds=a.step,
              frame_count=len(frames),sheets=sheets,time_basis='approximate fps samples; refine trim boundaries separately')
    (a.output/'media.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'{len(frames)} frames, {len(sheets)} sheets; {data["duration"]:.3f} seconds')


if __name__=='__main__':
    main()
