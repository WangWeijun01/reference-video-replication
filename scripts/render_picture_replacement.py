"""Render a frame-based picture replacement plan, then copy the reference audio."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def call(cmd):
    subprocess.run(cmd, check=True)


def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],encoding='utf8'))


def audio_hash(path):
    return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0','-c:a','pcm_s16le','-f','hash','-hash','sha256','-'],encoding='utf8').strip()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('plan',type=Path)
    ap.add_argument('--only',help='Render a single segment ID for visual review')
    a=ap.parse_args()
    plan=json.loads(a.plan.read_text(encoding='utf8'))
    work=Path(plan['work']); work.mkdir(parents=True,exist_ok=True)
    fps=plan['fps']; w=plan['width']; h=plan['height']; previous=0
    source_paths={x['path'] for x in plan['segments']}|{plan['reference']}
    before={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in source_paths}
    for s in plan['segments']:
        if s['start_frame']!=previous or s['end_frame']<=previous:
            raise ValueError('Plan must be contiguous and ordered')
        previous=s['end_frame']
    if previous!=plan['total_frames']:
        raise ValueError('Plan does not cover target frames')
    paths=[]
    for s in plan['segments']:
        if a.only and s['id']!=a.only:
            continue
        dest=work/(s['id']+'.mp4'); paths.append(dest)
        n=s['end_frame']-s['start_frame']
        key_payload=dict(segment=s,width=w,height=h,fps=fps,font=plan['font'],source_sha256=before[s['path']])
        key=hashlib.sha256(json.dumps(key_payload,ensure_ascii=False,sort_keys=True).encode('utf8')).hexdigest()
        cache=work/(s['id']+'-render-key.json')
        if dest.exists():
            if not cache.exists() or json.loads(cache.read_text(encoding='utf8')).get('key')!=key:
                raise ValueError(f'Existing segment belongs to a different or unknown plan: {s["id"]}; choose a new work directory')
            existing=probe(dest)
            v=next(x for x in existing['streams'] if x['codec_type']=='video')
            if int(v.get('nb_frames',-1))!=n:
                raise ValueError(f'Existing segment has wrong length: {s["id"]}')
            continue
        cmd=['ffmpeg','-n','-hide_banner','-loglevel','error','-ss',str(s['source_in']),'-i',s['path']]
        if s['mode']=='reference':
            cmd+=['-vf',f'setpts=PTS-STARTPTS,scale={w}:{h},fps={fps}']
        else:
            actual=probe(s['path']); v=next(x for x in actual['streams'] if x['codec_type']=='video')
            iw,ih=v['width'],v['height']
            roi=s['roi']; x=int(iw*roi[0])//2*2; y=int(ih*roi[1])//2*2
            cw=int(iw*roi[2])//2*2; ch=int(ih*roi[3])//2*2
            duration=n/fps; ratio=duration/s['source_span']
            pic=Image.new('RGBA',(w,h),(0,0,0,0)); draw=ImageDraw.Draw(pic)
            font=ImageFont.truetype(plan['font'],s.get('font_size',26))
            text=s.get('caption',''); lines=text.split('\n')
            line_h=s.get('line_height',s.get('font_size',26)+12)
            cy=s.get('caption_y',850)
            for i,line in enumerate(lines):
                box=draw.textbbox((0,0),line,font=font,stroke_width=2)
                tx=(w-(box[2]-box[0]))/2
                draw.text((tx,cy+i*line_h),line,font=font,fill='white',stroke_width=2,stroke_fill=(0,0,0,190))
            png=work/(s['id']+'-caption.png'); pic.save(png)
            cmd+=['-loop','1','-i',str(png)]
            fc=(f'[0:v]trim=duration={s["source_span"]},setpts=(PTS-STARTPTS)*{ratio:.10f},'
                f'crop={cw}:{ch}:{x}:{y},fps={fps},split=2[base][front];'
                f'[base]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=24:2[bg];'
                f'[front]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];'
                '[bg][fg]overlay=(W-w)/2:(H-h)/2[framed];'
                '[framed][1:v]overlay=0:0,setsar=1,tpad=stop_mode=clone:stop_duration=0.1[out]')
            cmd+=['-filter_complex',fc,'-map','[out]']
        cmd+=['-an','-frames:v',str(n),'-r',str(fps),'-c:v','libx264','-crf','18','-preset','fast','-pix_fmt','yuv420p','-video_track_timescale','15360','-movflags','+faststart',str(dest)]
        call(cmd)
        v=next(x for x in probe(dest)['streams'] if x['codec_type']=='video')
        if int(v['nb_frames'])!=n:
            raise ValueError(f'Wrong frame count: {s["id"]}')
        cache.write_text(json.dumps(dict(key=key,inputs=key_payload),ensure_ascii=False,indent=2),encoding='utf8')
        print('Rendered',s['id'],n,'frames',flush=True)
    if a.only:
        return
    concat=work/'concat.txt'
    concat.write_text('\n'.join("file '"+p.as_posix().replace("'","'\\''")+"'" for p in paths),encoding='utf8')
    silent=work/'picture.mp4'
    if not silent.exists():
        call(['ffmpeg','-n','-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',str(concat),'-c','copy',str(silent)])
    output=Path(plan['output'])
    if output.exists():
        raise FileExistsError('Output exists; use a new version or verify existing output')
    call(['ffmpeg','-n','-hide_banner','-loglevel','error','-i',str(silent),'-i',plan['reference'],'-map','0:v:0','-map','1:a:0','-c','copy','-movflags','+faststart',str(output)])
    after={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in source_paths}
    if before!=after:
        raise ValueError('Source content changed during render')
    audio_before=audio_hash(plan['reference']); audio_after=audio_hash(output)
    info=probe(output); vs=next(x for x in info['streams'] if x['codec_type']=='video')
    report=dict(output=str(output),reference=plan['reference'],source_hashes=before,sources_unchanged=before==after,
                reference_pcm_hash=audio_before,output_pcm_hash=audio_after,audio_identical=audio_before==audio_after,
                total_frames=int(vs['nb_frames']),expected_frames=plan['total_frames'],media=info,
                replacement_frames=sum(s['end_frame']-s['start_frame'] for s in plan['segments'] if s['mode']!='reference'))
    (output.parent/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    if not report['audio_identical'] or report['total_frames']!=plan['total_frames']:
        raise ValueError('Output failed audio or frame validation')
    call(['ffmpeg','-v','error','-i',str(output),'-f','null','-'])
    report['full_decode_pass']=True
    report['output_sha256']=hashlib.sha256(output.read_bytes()).hexdigest()
    (output.parent/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print('PASS: source hashes, copied audio PCM equality, target frames and full decode',flush=True)


if __name__=='__main__':
    main()
