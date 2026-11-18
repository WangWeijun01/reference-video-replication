"""Gate video delivery with source reuse, framing, media, and signed-off visual review.

prepare: check plan/source constraints and emit first/middle/last preview frames.
final: audit actual output, copied audio, and a plan/output-bound agent visual review.
Exit 2 means blocked: adjust, use a fresh audit directory, audit again before delivery.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import subprocess
from fractions import Fraction
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def digest(path):
    with open(path,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def call(cmd):return subprocess.run(cmd,check=True,capture_output=True)


def media(path):return json.loads(call(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]).stdout)


def pcm(path):return call(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0','-c:a','pcm_s16le','-f','hash','-hash','sha256','-']).stdout.decode().strip()


def area(box):return box[2]*box[3]


def intersection(a,b):
    return max(0,min(a[0]+a[2],b[0]+b[2])-max(a[0],b[0]))*max(0,min(a[1]+a[3],b[1]+b[3])-max(a[1],b[1]))


def active(rule,start,end):return start<rule.get('end',float('inf')) and end>rule.get('start',0)


def phash(image):
    # Small DCT-based perceptual candidate finder. It does not decide semantics.
    import numpy as np
    a=np.asarray(image.convert('L').resize((32,32)),dtype=float)
    c=np.cos((np.arange(32)[None,:]+.5)*np.arange(8)[:,None]*math.pi/32)
    v=(c@a@c.T).ravel(); median=np.median(v[1:])
    return sum((1<<i) for i,x in enumerate(v) if x>median)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('plan',type=Path);ap.add_argument('registry',type=Path);ap.add_argument('audit_dir',type=Path)
    ap.add_argument('--stage',choices=['prepare','final'],default='prepare')
    ap.add_argument('--review',type=Path,help='Required final agent visual-review JSON')
    ap.add_argument('--no-previews',action='store_true',help='Structural regression audit only; never sufficient for delivery')
    a=ap.parse_args()
    plan=json.loads(a.plan.read_text(encoding='utf8')); reg=json.loads(a.registry.read_text(encoding='utf8'))
    a.audit_dir.mkdir(parents=True,exist_ok=False)
    errors=[]; checks=[]; warnings=[]; segments=plan['segments']; fps=plan['fps']; prev=0
    assets={str(Path(x['path']).resolve()):x for x in reg['assets']}
    # Talking-head A-roll families may recur, but only moving forward through the same source.
    aroll={(str(Path(x['path']).resolve()),z['family']) for x in reg['assets'] for z in x['families'] if z.get('a_roll')}
    usage=[]; hashes={}; mcache={}
    for s in segments:
        sid=s['id']; start=s['start_frame']; end=s['end_frame']
        if start!=prev or end<=start:errors.append(f'{sid}: 时间轴不连续')
        prev=end
        if s['mode']!='footage':
            warnings.append(f'{sid}: 自制图形须专门视觉复核');continue
        p=str(Path(s['path']).resolve())
        if p not in assets:errors.append(f'{sid}: 缺源镜头登记');continue
        if p not in hashes:
            hashes[p]=digest(p);mcache[p]=media(p)
            if assets[p].get('sha256') and assets[p]['sha256']!=hashes[p]:errors.append(f'{sid}: 登记后的源文件内容发生变化')
        v=next(x for x in mcache[p]['streams'] if x['codec_type']=='video')
        x,y,w,h=s['crop']; si=s['source_in']; span=s.get('source_span',(end-start)/fps); so=si+span
        if min(x,y)<0 or w<=0 or h<=0 or x+w>v['width'] or y+h>v['height']:errors.append(f'{sid}: 取景超出源边界')
        if abs(w/h-plan['width']/plan['height'])>.004:errors.append(f'{sid}: 取景比例导致拉伸')
        if si<0 or so>float(mcache[p]['format']['duration'])+.01:errors.append(f'{sid}: 源区间越界')
        for rule in assets[p].get('brand_boxes',[]):
            n=intersection(s['crop'],rule['box'])
            if active(rule,si,so) and 0<n<area(rule['box']):errors.append(f'{sid}: 品牌包围区被部分裁断 ({rule["label"]})')
        for rule in assets[p].get('forbidden_boxes',[]):
            if active(rule,si,so) and intersection(s['crop'],rule['box'])>0:errors.append(f'{sid}: 取景接触禁入文字区 ({rule["label"]})')
        fams=[z['family'] for z in assets[p]['families'] if min(so,z['end'])-max(si,z['start'])>.04]
        covered=sum(max(0,min(so,z['end'])-max(si,z['start'])) for z in assets[p]['families'])
        if covered<span-.05:errors.append(f'{sid}: 源区间未完整标注镜头族，需先看片登记')
        usage.append(dict(id=sid,path=p,source_sha256=hashes[p],start=si,end=so,families=fams,start_frame=start,end_frame=end))
    if prev!=plan['total_frames']:errors.append('总帧数覆盖不完整')
    families_by_id={u['id']:set(u['families']) for u in usage}
    segment_index={s['id']:i for i,s in enumerate(segments)}
    for i,u in enumerate(usage):
        for z in usage[:i]:
            overlap=min(u['end'],z['end'])-max(u['start'],z['start'])
            if u['source_sha256']==z['source_sha256'] and overlap>.04:errors.append(f'{z["id"]}/{u["id"]}: 重用源时间区间 {overlap:.3f}秒')
            repeated=set(u['families'])&set(z['families'])
            returned=[fam for fam in repeated if any(fam not in families_by_id.get(segments[k]['id'],set()) for k in range(segment_index[z['id']]+1,segment_index[u['id']]))]
            forward=[fam for fam in returned if (u['path'],fam) in aroll and u['path']==z['path'] and u['start']>=z['end']-.04]
            backward=[fam for fam in returned if (u['path'],fam) in aroll and fam not in forward]
            returned=[fam for fam in returned if (u['path'],fam) not in aroll]
            if backward:errors.append(f'{z["id"]}/{u["id"]}: 口播主镜头源时间回退 {sorted(backward)}')
            if forward:warnings.append(f'{z["id"]}/{u["id"]}: 口播主镜头按源时间向前返回 {sorted(forward)}，须视觉复审确认口型同步')
            if returned:errors.append(f'{z["id"]}/{u["id"]}: 非连续地再次使用同一镜头族 {sorted(returned)}')
    baseline=Path(reg['baseline_plan']) if reg.get('baseline_plan') else None
    if baseline:
        b=json.loads(baseline.read_text(encoding='utf8'))
        if Path(plan.get('audio') or plan['reference']).resolve()!=Path(b.get('audio') or b['reference']).resolve():errors.append('音轨来源偏离已确认基线')
        if plan['captions']!=b['captions']:errors.append('字幕文本或时码偏离已确认基线')
        if [(s['start_frame'],s['end_frame']) for s in segments]!=[(s['start_frame'],s['end_frame']) for s in b['segments']]:errors.append('段落时间偏离已确认基线')
    checks+=['源区间与帧时间轴','完整或避开的品牌包围区','源字幕禁入区','同源时间重叠','同动作与机位镜头族跨段复用（口播主镜头仅可向前返回）','已确认字幕与时码']

    actual_hash=None
    if a.stage=='final':
        output=Path(plan['output']); info=media(output)
        actual_hash=digest(output)
        v=next(x for x in info['streams'] if x['codec_type']=='video')
        if int(v.get('nb_frames',-1))!=plan['total_frames']:errors.append('实际导出帧数不符')
        if (v['width'],v['height'])!=(plan['width'],plan['height']):errors.append('实际导出尺寸不符')
        if abs(float(Fraction(v['r_frame_rate']))-fps)>.001:errors.append('实际导出帧率不符')
        if abs(float(v['duration'])-plan['total_frames']/fps)>1/fps:errors.append('实际视频轨时长不符')
        if pcm(output)!=pcm(plan.get('audio') or plan['reference']):errors.append('解码音轨与计划音轨不一致')
        verification_path=output.parent/'verification.json'
        if not verification_path.exists():errors.append('缺渲染时源文件和音轨核验记录')
        else:
            verification=json.loads(verification_path.read_text(encoding='utf8'))
            if verification.get('output_sha256')!=actual_hash or not all(verification.get(k) for k in ['sources_unchanged','audio_identical','full_decode_pass']):errors.append('渲染核验记录不属于当前文件或未通过')
            reported={str(Path(p).resolve()):h for p,h in verification.get('source_hashes',{}).items()}
            if any(reported.get(p)!=h for p,h in hashes.items()):errors.append('渲染时与当前源文件哈希不一致')
        call(['ffmpeg','-v','error','-i',str(output),'-f','null','-'])
        checks+=['实际导出音轨一致','实际导出帧数与尺寸','全文件解码']

    previews=[]; candidates=[]
    if not a.no_previews:
        spec=importlib.util.spec_from_file_location('mix_renderer',Path(__file__).with_name('render_fullscreen_mix.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.configure(plan)
        overlays=[module.caption_for(c,plan.get('caption_style','bar')) for c in plan['captions']]
        frames_dir=a.audit_dir/'frames';frames_dir.mkdir()
        labels=[]
        for s in segments:
            n=s['end_frame']-s['start_frame']
            for label,frame in [('入点',s['start_frame']+min(3,n//4)),('中点',s['start_frame']+n//2),('尾点',s['end_frame']-min(3,n//4))]:labels.append((s,label,frame))
        if a.stage=='final':
            selection='+'.join(f'eq(n\\,{z[2]})' for z in labels)
            call(['ffmpeg','-n','-v','error','-i',plan['output'],'-vf','select='+selection,'-fps_mode','vfr','-q:v','2',str(frames_dir/'actual-%03d.jpg')])
        thumb_tiles=[]; font=ImageFont.truetype(plan.get('font','C:/Windows/Fonts/msyh.ttc'),16)
        for index,(s,label,frame) in enumerate(labels):
            if a.stage=='final':
                im=Image.open(frames_dir/f'actual-{index+1:03}.jpg').convert('RGB')
            else:
                t=(frame-s['start_frame'])/fps
                if s['mode']=='footage':
                    span=s.get('source_span',(s['end_frame']-s['start_frame'])/fps)
                    src=s['source_in']+span*(frame-s['start_frame'])/(s['end_frame']-s['start_frame'])
                    raw=call(['ffmpeg','-v','error','-ss',str(src),'-i',s['path'],'-vf',module.vf(s,fps),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-']).stdout
                    im=Image.frombytes('RGB',(plan['width'],plan['height']),raw[:plan['width']*plan['height']*3])
                else:im=module.graphic(s,t)
                im=module.compose(im,frame,plan,overlays)
                im.save(frames_dir/f'{s["id"]}-{label}.jpg',quality=94)
            tile=Image.new('RGB',(192,374),'white');tile.paste(im.resize((192,341)),(0,0))
            ImageDraw.Draw(tile).text((3,347),f'{s["id"]} {label} {frame/fps:.2f}s',font=font,fill='#173C32')
            thumb_tiles.append(tile)
            if label=='中点':previews.append(dict(id=s['id'],start_frame=s['start_frame'],end_frame=s['end_frame'],hash=phash(im)))
        for page in range(math.ceil(len(thumb_tiles)/12)):
            sheet=Image.new('RGB',(768,1122),'#DCE7DF')
            for i,tile in enumerate(thumb_tiles[page*12:page*12+12]):sheet.paste(tile,((i%4)*192,(i//4)*374))
            sheet.save(a.audit_dir/f'contact-{page+1:02}.jpg',quality=94)
        for i,u in enumerate(previews):
            for z in previews[:i]:
                distance=(u['hash']^z['hash']).bit_count()
                if distance<=8 and z['end_frame']!=u['start_frame']:candidates.append(dict(pair=[z['id'],u['id']],distance=distance))

    review_status='pending'; reused_evidence_frames=0
    if a.stage=='final':
        if not a.review:errors.append('缺导出后视觉复审，禁止交付')
        else:
            review=json.loads(a.review.read_text(encoding='utf8'))
            evidence_path=Path(review.get('evidence_audit','missing'))
            if not evidence_path.is_file():errors.append('缺当前导出93帧等实际画面证据，不接受只填通过结论')
            else:
                evidence=json.loads(evidence_path.read_text(encoding='utf8'))
                if evidence.get('stage')!='final' or evidence.get('plan_sha256')!=digest(a.plan) or evidence.get('output_sha256')!=actual_hash or evidence.get('preview_frames',0)<len(segments)*3:errors.append('视觉证据不属于当前计划和导出，或镜头取样不完整')
                if a.no_previews:
                    candidates=evidence.get('visual_similarity_candidates',[])
                    reused_evidence_frames=evidence.get('preview_frames',0)
            if review.get('plan_sha256')!=digest(a.plan) or review.get('output_sha256')!=actual_hash:errors.append('视觉复审不属于当前计划或导出，必须重审')
            inspected={x['id'] for x in review.get('segments',[]) if x.get('status')=='pass' and x.get('observations')}
            if inspected!={s['id'] for s in segments}:errors.append('有镜头未完成视觉复审或未写观察依据')
            required=['branding','source_captions','subject_framing','repetition','naturalness']
            if any(review.get('checks',{}).get(k)!='pass' for k in required):errors.append('品牌/字幕/主体/重复/自然度检查未全部通过')
            resolved={tuple(sorted(x['pair'])) for x in review.get('similarity_dispositions',[]) if x.get('decision')=='distinct' and x.get('reason')}
            if any(tuple(sorted(c['pair'])) not in resolved for c in candidates):errors.append('感知相似候选未逐项复核')
            review_status='pass' if not errors else 'blocked'
    status='blocked' if errors else ('ready_for_export_and_review' if a.stage=='prepare' else 'pass')
    result=dict(status=status,stage=a.stage,plan_sha256=digest(a.plan),registry_sha256=digest(a.registry),output_sha256=actual_hash,checks=checks,errors=errors,warnings=warnings,source_hashes=hashes,source_usage=usage,visual_similarity_candidates=candidates,visual_review=review_status,visual_review_file=str(a.review) if a.review else None,reused_evidence_frames=reused_evidence_frames,preview_frames=0 if a.no_previews else len(segments)*3,delivery_allowed=a.stage=='final' and not errors)
    (a.audit_dir/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(status=status,errors=errors,visual_similarity_candidates=candidates,delivery_allowed=result['delivery_allowed']),ensure_ascii=False,indent=2))
    if errors:raise SystemExit(2)


if __name__=='__main__':main()
