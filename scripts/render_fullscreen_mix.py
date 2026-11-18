"""Render full-screen footage and native animated illustrations, with a copied audio track.

The audio track is the reference audio by default, or plan['audio'] when the script was rewritten
and a new voiceover/music mix replaces the original sound.
Inputs are a frame-based JSON plan. This script performs no online acquisition.
Use --preview to inspect representative frames before rendering the entire film.
"""
import argparse
import hashlib
import json
import math
import subprocess
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H = 576, 1024  # Layout units for all drawing; plan width/height set the pixels actually rendered.
S = 1.0
PW, PH = W, H
ENHANCE = False
GREEN = '#08765E'
INK = '#183C33'
MUTED = '#6B8177'
LIGHT = '#E4EFE8'
GOLD = '#D4AC55'
FONT = 'C:/Windows/Fonts/msyh.ttc'
BOLD = 'C:/Windows/Fonts/msyhbd.ttc'


def run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True)


def sha(path):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def probe(path):
    return json.loads(run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)]).stdout)


def pcm(path):
    return run(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0','-c:a','pcm_s16le','-f','hash','-hash','sha256','-']).stdout.decode().strip()


@lru_cache(maxsize=30)
def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, round(size*S))


def configure(plan):
    # Graphics and captions are redrawn at the output size, so they stay sharp instead of being upscaled.
    global S,PW,PH,ENHANCE,FONT,BOLD
    PW,PH=plan.get('width',W),plan.get('height',H)
    if abs(PW/PH-W/H)>.001: raise ValueError('Output must be 9:16')
    S=PW/W; ENHANCE=plan.get('enhance',False)
    FONT=plan.get('font',FONT); BOLD=plan.get('font_bold',BOLD)
    font.cache_clear()


class Canvas:
    # ImageDraw addressed in layout units and rasterised at the output resolution.
    def __init__(self, im): self.d=ImageDraw.Draw(im)
    def _xy(self, xy):
        flat=[v for p in xy for v in (p if isinstance(p,(tuple,list)) else (p,))]
        return [v*S for v in flat]
    def _w(self, width): return max(1,round(width*S))
    def textlength(self, value, font): return self.d.textlength(value,font=font)/S
    def text(self, xy, value, font, fill=None, stroke_width=0, stroke_fill=None, anchor=None):
        self.d.text(self._xy(xy),value,font=font,fill=fill,anchor=anchor,stroke_width=round(stroke_width*S),stroke_fill=stroke_fill)
    def line(self, xy, fill=None, width=1, joint=None): self.d.line(self._xy(xy),fill=fill,width=self._w(width),joint=joint)
    def rectangle(self, xy, fill=None): self.d.rectangle(self._xy(xy),fill=fill)
    def rounded_rectangle(self, xy, radius=0, fill=None, outline=None, width=1):
        self.d.rounded_rectangle(self._xy(xy),round(radius*S),fill=fill,outline=outline,width=self._w(width))
    def ellipse(self, xy, fill=None, outline=None, width=1): self.d.ellipse(self._xy(xy),fill=fill,outline=outline,width=self._w(width))
    def arc(self, xy, start, end, fill=None, width=1): self.d.arc(self._xy(xy),start,end,fill=fill,width=self._w(width))
    def chord(self, xy, start, end, fill=None): self.d.chord(self._xy(xy),start,end,fill=fill)
    def polygon(self, xy, fill=None): self.d.polygon(self._xy(xy),fill=fill)


def text(d, xy, value, size=28, color=INK, bold=False, center=False):
    f = font(size,bold)
    x,y = xy
    if center:
        x -= d.textlength(value,font=f)/2
    d.text((x,y),value,font=f,fill=color)


def ease(t):
    t=max(0,min(1,t))
    return 1-(1-t)**3


def panel(d, box, fill='white', radius=24, outline=None):
    x0,y0,x1,y1=box
    d.rounded_rectangle((x0+1,y0+7,x1+1,y1+7),radius,fill='#DDE7DF')
    d.rounded_rectangle(box,radius,fill=fill,outline=outline,width=2)


def wave(d, box, t, color=GREEN, bars=29):
    x,y,w,h=box
    for i in range(bars):
        a=(0.22+0.78*abs(math.sin(i*1.76+t*3.3)))*h
        bx=x+i*w/(bars-1)
        d.rounded_rectangle((bx-3,y+(h-a)/2,bx+3,y+(h+a)/2),3,fill=color)


def headphones(d, x, y, scale=1, t=0):
    # Deliberately generic line illustration, not a product rendering.
    def box(a,b,c,e): return (x+a*scale,y+b*scale,x+c*scale,y+e*scale)
    d.arc(box(0,0,220,240),180,360,fill=GREEN,width=max(2,int(15*scale)))
    d.rounded_rectangle(box(-5,105,43,210),int(16*scale),fill=GREEN)
    d.rounded_rectangle(box(177,105,225,210),int(16*scale),fill=GREEN)
    d.arc(box(165,165,255,225),0,100,fill=GREEN,width=max(2,int(7*scale)))
    d.ellipse(box(220,218,239,230),fill=GOLD)


def book(d, box):
    x,y,w,h=box
    d.rounded_rectangle((x,y,x+w,y+h),18,fill='white',outline=GREEN,width=3)
    d.line((x+w/2,y+8,x+w/2,y+h-8),fill=LIGHT,width=3)
    for side in range(2):
        for j in range(5):
            d.rounded_rectangle((x+22+side*w/2,y+35+j*25,x+w/2-20+side*w/2,y+41+j*25),3,fill=LIGHT)


def pictogram(d, kind, cx, cy):
    # Generic line pictograms for illustrative cards; not photos of any real facility.
    if kind=='phone':
        d.rounded_rectangle((cx-26,cy-46,cx+26,cy+46),10,outline=GREEN,width=5)
        d.line((cx-8,cy+34,cx+8,cy+34),fill=GREEN,width=4)
        d.rounded_rectangle((cx+18,cy-6,cx+52,cy+40),8,fill=GOLD)
    elif kind=='bed':
        d.rounded_rectangle((cx-60,cy-4,cx+60,cy+26),8,fill=GREEN)
        d.rounded_rectangle((cx-54,cy-26,cx-18,cy-4),8,fill=LIGHT,outline=GREEN,width=3)
        d.line((cx-60,cy-36,cx-60,cy+44),fill=GREEN,width=6)
        d.line((cx+60,cy+26,cx+60,cy+44),fill=GREEN,width=6)
    elif kind=='bowl':
        d.chord((cx-56,cy-40,cx+56,cy+52),0,180,fill=GREEN)
        for k in (-20,0,20):
            d.arc((cx+k-8,cy-42,cx+k+8,cy-10),90,270,fill=GOLD,width=3)
    elif kind=='clock':
        d.ellipse((cx-48,cy-48,cx+48,cy+48),outline=GREEN,width=6)
        d.line((cx,cy,cx,cy-30),fill=GREEN,width=5)
        d.line((cx,cy,cx+22,cy+10),fill=GOLD,width=5)
    elif kind=='chat':
        d.rounded_rectangle((cx-58,cy-40,cx+40,cy+16),16,fill=GREEN)
        d.polygon([(cx-36,cy+16),(cx-20,cy+16),(cx-38,cy+34)],fill=GREEN)
        d.rounded_rectangle((cx-14,cy-6,cx+60,cy+42),14,fill=GOLD)
    elif kind=='target':
        for r,c in ((50,GREEN),(34,'white'),(18,GOLD)):
            d.ellipse((cx-r,cy-r,cx+r,cy+r),fill=c,outline=GREEN,width=3)
    elif kind=='chart':
        for k,h in enumerate((30,52,78)):
            d.rounded_rectangle((cx-50+k*36,cy+40-h,cx-24+k*36,cy+40),5,fill=GREEN if k<2 else GOLD)
    elif kind=='book':
        d.rounded_rectangle((cx-56,cy-38,cx+56,cy+38),10,outline=GREEN,width=5)
        d.line((cx,cy-34,cx,cy+34),fill=GREEN,width=4)
    else:
        d.ellipse((cx-40,cy-40,cx+40,cy+40),fill=LIGHT)
        d.line((cx-18,cy,cx-4,cy+14,cx+20,cy-14),fill=GREEN,width=6)


def graphic(s,t):
    im=Image.new('RGB',(PW,PH),'#F5F7F1')
    d=Canvas(im)
    # Full-frame geometric field, with no blurred or padded video regions.
    d.ellipse((270,-180,750,300),fill='#E2EDE3')
    d.ellipse((-260,610,220,1120),fill='#EAF0E5')
    d.line((36,104,540,104),fill='#CDDCD2',width=1)
    if s.get('header'): text(d,(36,48),s['header'],20,GREEN,bold=True)
    tag=s.get('tag','功能示意')
    if tag:
        d.rounded_rectangle((428,45,540,81),18,fill='white')
        text(d,(484,49),tag,18,MUTED,center=True)
    text(d,(36,139),s.get('eyebrow','AI LEARNING'),18,MUTED)
    title=s['title']
    for k,line in enumerate(title.split('\n')):
        text(d,(36,179+k*53),line,40,INK,True)
    kind=s['scene']
    p=ease(t/0.5)
    offset=int((1-p)*38)
    if kind=='tools':
        panel(d,(36,328+offset,540,739+offset))
        headphones(d,95,365+offset,1.10,t)
        d.rounded_rectangle((424,397+offset,457,620+offset),16,fill=GREEN)
        d.rounded_rectangle((429,422+offset,452,480+offset),5,fill=LIGHT)
        d.polygon([(429,620+offset),(452,620+offset),(440,650+offset)],fill=GOLD)
        text(d,(288,679+offset),'听 · 说 · 读 · 写',27,GREEN,center=True)
    elif kind=='book':
        panel(d,(36,327+offset,540,747+offset))
        book(d,(82,389+offset,412,216))
        for i,label in enumerate(s.get('tags',['标签A','标签B'])):
            d.rounded_rectangle((117+i*185,650+offset,267+i*185,702+offset),26,fill=LIGHT)
            text(d,(192+i*185,656+offset),label,25,GREEN,center=True)
    elif kind in ('words','topics'):
        items=s['items']
        # Optional top/gap keep longer lists clear of the lower-third caption.
        top,gap=s.get('top',330),s.get('gap',116)
        for i,label in enumerate(items):
            yy=top+i*gap+int((1-ease((t-i*.14)/.45))*35)
            panel(d,(36,yy,540,yy+min(91,gap-10)))
            d.ellipse((58,yy+25,94,yy+61),fill=LIGHT)
            text(d,(76,yy+26),str(i+1),21,GREEN,True,True)
            text(d,(116,yy+23),label,27,INK)
            if kind=='words':
                x=478
                d.line((x,yy+37,x+7,yy+44,x+20,yy+29),fill=GREEN,width=3)
    elif kind=='wave':
        panel(d,(36,334+offset,540,713+offset))
        d.ellipse((232,365+offset,344,477+offset),fill=LIGHT)
        d.polygon([(279,396+offset),(279,447+offset),(316,421+offset)],fill=GREEN)
        wave(d,(84,522+offset,408,83),t)
        text(d,(288,651+offset),s.get('label','听力练习'),26,GREEN,center=True)
    elif kind=='sync':
        # Explicit conceptual flow, not a facsimile application screen.
        panel(d,(36,322,540,481))
        headphones(d,61,349,.42,t)
        text(d,(204,365),s.get('source_name','应用'),38,GREEN,True)
        text(d,(204,419),'学习记录',23,MUTED)
        for j in range(3):
            yy=505+j*19+((t*29)%19)
            d.line((282,yy,288,yy+6,294,yy),fill=GREEN,width=3)
        panel(d,(36,589,540,748),fill=GREEN)
        text(d,(288,609),s.get('target_name','平台'),38,'white',True,True)
        text(d,(288,676),'记录同步 · 功能示意',23,'#DCEBE4',center=True)
    elif kind=='archive':
        for i in range(3):
            yy=330+i*123+int((1-ease((t-i*.14)/.4))*30)
            panel(d,(36,yy,540,yy+100))
            text(d,(59,yy+25),f'0{i+1}',30,GREEN,True)
            wave(d,(138,yy+28,282,43),t+i, bars=21)
            d.line((463,yy+44,470,yy+51,487,yy+34),fill=GREEN,width=3)
    elif kind=='records':
        panel(d,(36,330+offset,540,736+offset))
        text(d,(70,359+offset),'学习记录',30,GREEN,True)
        for i,label in enumerate(['跟读音频','练习内容','学习进度']):
            yy=431+i*77+offset
            d.ellipse((73,yy+7,93,yy+27),fill=GREEN if i<=int(t*2)%4 else LIGHT)
            text(d,(116,yy),label,26,INK)
            d.line((117,yy+49,485,yy+49),fill=LIGHT,width=2)
    elif kind=='dialog':
        panel(d,(36,326+offset,540,733+offset))
        for cx,cy in [(166,427),(402,573)]:
            d.ellipse((cx-31,cy-49+offset,cx+31,cy+13+offset),fill=GREEN)
            d.rounded_rectangle((cx-54,cy+25+offset,cx+54,cy+88+offset),22,fill=LIGHT)
        d.rounded_rectangle((252,375+offset,488,461+offset),20,fill=LIGHT)
        wave(d,(275,399+offset,187,34),t,bars=15)
        d.rounded_rectangle((85,542+offset,318,628+offset),20,fill='#EAF0DF')
        wave(d,(109,566+offset,185,34),t+2,bars=15)
        text(d,(288,675+offset),'口语模拟练习',25,GREEN,center=True)
    elif kind=='feedback':
        for i,label in enumerate(['估分参考','修改建议','标准发音参考']):
            yy=329+i*124
            active=min(2,int(t/1.08))
            panel(d,(36,yy,540,yy+99),fill=GREEN if active==i else 'white')
            text(d,(65,yy+27),f'0{i+1}',28,'#D6E9DE' if active==i else MUTED,True)
            text(d,(137,yy+27),label,29,'white' if active==i else INK,True)
    elif kind=='analysis':
        panel(d,(36,330+offset,540,751+offset))
        text(d,(68,361+offset),'Practice makes',31,INK,True)
        text(d,(68,409+offset),'progress.',31,INK,True)
        items=['词汇','语法','句式']
        for i,label in enumerate(items):
            yy=504+i*70+offset
            active=min(2,int(t/1.35))
            d.rounded_rectangle((66,yy,160,yy+46),12,fill=GREEN if active==i else LIGHT)
            text(d,(113,yy+5),label,23,'white' if active==i else GREEN,True,True)
            width=int(260*ease((t-i*.25)/.6))
            if width:
                d.rounded_rectangle((190,yy+18,190+width,yy+25),3,fill=GOLD if active==i else LIGHT)
    elif kind=='end':
        headphones(d,178,326,1,t)
        wave(d,(124,598,328,57),t,bars=25)
        text(d,(288,711),s.get('name','品牌'),48,GREEN,True,True)
    elif kind=='scorecard':
        # Illustrative score card; values come from the plan and are marked as a demonstration.
        # Kept above y=700 so the lower-third caption never covers the card.
        panel(d,(36,300+offset,540,690+offset))
        text(d,(288,320+offset),s.get('label','Overall'),24,MUTED,center=True)
        total=float(s['score'])
        shown=total*ease(t/0.8)
        text(d,(288,352+offset),f'{shown:.1f}',112,'#C8453B',True,True)
        for i,(name,value) in enumerate(s.get('parts',[])):
            cx=158+(i%2)*260; cy=528+(i//2)*76+offset
            text(d,(cx,cy),name,22,MUTED,center=True)
            text(d,(cx,cy+28),str(value),34,INK,True,True)
    elif kind=='icons':
        items=s['items']
        cols=2 if len(items)>1 else 1
        for i,(icon,label) in enumerate(items):
            p_i=ease((t-i*.18)/.45)
            cw=232 if cols==2 else 504
            x0=36+(i%cols)*272; y0=300+(i//cols)*184+int((1-p_i)*40)
            panel(d,(x0,y0,x0+cw,y0+164))
            pictogram(d,icon,x0+cw/2,y0+64)
            text(d,(x0+cw/2,y0+116),label,26,INK,True,True)
    elif kind=='keyword':
        im.paste(s.get('bg',GREEN),(0,0,PW,PH))
        d=Canvas(im)
        for i,word in enumerate(s['items']):
            p_i=ease((t-i*.35)/.3)
            if p_i<=0: continue
            size=int(96*(1.25-0.25*p_i))
            text(d,(288,360+i*170-size/2+48),word,size,s.get('color','#FFE14D'),True,True)
        return im
    elif kind=='brand':
        im.paste(GREEN,(0,0,PW,PH))
        d=Canvas(im)
        text(d,(288,402+offset),s['title'].split('\n')[0],50,'white',True,True)
        for k,line in enumerate(s.get('lines',[])):
            text(d,(288,492+k*52+offset),line,30,'#DCEBE4',center=True)
        d.line((228,470+offset,348,470+offset),fill=GOLD,width=3)
        return im
    else:
        raise ValueError('Unknown scene: '+kind)
    return im


def rich_runs(line, emphasis):
    # Split one caption line into (text, is_emphasis) runs; emphasis only styles, it never edits words.
    runs=[]; rest=line
    while rest:
        hits=[(rest.find(w),w) for w in emphasis if w in rest]
        if not hits:
            runs.append((rest,False)); break
        at,word=min(hits,key=lambda h:(h[0],-len(h[1])))
        if at: runs.append((rest[:at],False))
        runs.append((word,True)); rest=rest[at+len(word):]
    return runs


def draw_runs(d, runs, x, baseline, size, big, color, accent, stroke=0, stroke_fill=None):
    for run,hit in runs:
        f=font(big if hit else size,True)
        d.text((x,baseline),run,font=f,fill=accent if hit else color,anchor='ls',stroke_width=stroke,stroke_fill=stroke_fill)
        x+=d.textlength(run,font=f)
    return x


def runs_width(d, runs, size, big):
    return sum(d.textlength(run,font=font(big if hit else size,True)) for run,hit in runs)


def fit_size(d, lines, size, big, limit):
    while size>24 and max(runs_width(d,r,size,big) for r in lines)>limit:
        size-=2; big-=2
    return size,big


def caption_pop(lines, variant):
    # Bold white text with a heavy outline; punch lines put the keyword on a tilted red sticker.
    out=Image.new('RGBA',(PW,PH)); d=Canvas(out)
    pad=24 if variant=='punch' else 0  # The sticker takes its padding out of the line, or it covers the next word.
    size,big=fit_size(d,lines,38,46,520-2*pad)
    y0=770-29*(len(lines)-1)
    for k,runs in enumerate(lines):
        base=y0+k*62
        if variant!='punch':
            draw_runs(d,runs,(W-runs_width(d,runs,size,big))/2,base,size,big,'white','#FFE14D',5,(16,16,16,255))
            continue
        x=(W-runs_width(d,runs,size,big)-2*pad*sum(hit for _,hit in runs))/2
        for run,hit in runs:
            f=font(big if hit else size,True); tw=d.textlength(run,font=f)
            if hit:
                tw_box,th_box=int(tw)+2*pad,big+40
                tag=Image.new('RGBA',(round(tw_box*S),round(th_box*S)))
                t=Canvas(tag)
                t.rounded_rectangle((2,6,tw_box-3,th_box-7),10,fill=(214,48,49,255),outline=(255,255,255,255),width=3)
                t.text((tw_box/2,th_box/2),run,font=f,fill='white',anchor='mm')
                tag=tag.rotate(3,resample=Image.BICUBIC,expand=True)
                out.alpha_composite(tag,(int((x+tw/2+pad)*S-tag.width/2),int((base-big*.38)*S-tag.height/2)))
                x+=tw+2*pad
            else:
                d.text((x,base),run,font=f,fill='white',anchor='ls',stroke_width=5,stroke_fill=(16,16,16,255))
                x+=tw
    return out


def caption_band(lines, variant):
    # Full-width translucent band; the pain half of a script sits on slate, the answer half on green.
    out=Image.new('RGBA',(PW,PH)); d=Canvas(out)
    size,big=fit_size(d,lines,33,37,500)
    fill,accent=((27,42,61,215),'#FFB454') if variant=='pain' else ((6,92,74,225),'#FFE08A')
    # Centre stays low enough that cards still sliding into place are not covered on their entry.
    pitch=50; top=752-pitch*(len(lines)-1)/2-34
    bottom=top+pitch*len(lines)+22
    d.rectangle((0,top,W,bottom),fill=fill)
    d.rectangle((0,top,9,bottom),fill=accent)
    for k,runs in enumerate(lines):
        base=top+49+k*pitch
        draw_runs(d,runs,(W-runs_width(d,runs,size,big))/2,base,size,big,'white',accent)
    return out


def caption_paper(lines, variant):
    # Answer-sheet card: dark ink on paper, keyword in teacher's red with a hand-drawn underline.
    out=Image.new('RGBA',(PW,PH)); d=Canvas(out)
    size,big=fit_size(d,lines,32,35,440)
    width=max(runs_width(d,r,size,big) for r in lines)+64
    pitch=50; top=752-pitch*(len(lines)-1)/2-36; bottom=top+pitch*len(lines)+26
    x0=26 if variant=='left' else W-26-width
    d.rounded_rectangle((x0+4,top+6,x0+width+4,bottom+6),8,fill=(0,0,0,70))
    d.rounded_rectangle((x0,top,x0+width,bottom),8,fill=(250,247,238,250))
    d.rectangle((x0,top+8,x0+7,bottom-8),fill='#08765E')
    for k,runs in enumerate(lines):
        base=top+50+k*pitch; x=x0+34
        for run,hit in runs:
            f=font(big if hit else size,True); tw=d.textlength(run,font=f)
            d.text((x,base),run,font=f,fill='#D63031' if hit else '#20302A',anchor='ls')
            if hit:
                d.line([(x,base+9),(x+tw*.34,base+6),(x+tw*.7,base+10),(x+tw,base+7)],fill='#D63031',width=3,joint='curve')
            x+=tw
    return out


RICH_STYLES={'pop':caption_pop,'band':caption_band,'paper':caption_paper}


def caption_for(c, style):
    # One overlay per caption; a caption's emphasis/variant only apply to the rich styles.
    if style in RICH_STYLES:
        lines=[rich_runs(l,c.get('emphasis',[])) for l in c['text'].split('\n') if l]
        return RICH_STYLES[style](lines,c.get('variant'))
    return caption_overlay(c['text'],style)


def caption_entry(layer, age, style):
    # Short entrance on the caption's first frames; the settled overlay is left untouched.
    if style not in RICH_STYLES or age>=5: return layer
    p=ease((age+1)/5)
    if style=='pop':
        box=layer.getbbox()
        if not box: return layer
        crop=layer.crop(box); s=1+.16*(1-p)
        big=crop.resize((int(crop.width*s),int(crop.height*s)),Image.BICUBIC)
        out=Image.new('RGBA',(PW,PH))
        out.alpha_composite(big,(max(0,(box[0]+box[2]-big.width)//2),max(0,(box[1]+box[3]-big.height)//2)))
        return out
    out=Image.new('RGBA',(PW,PH))
    out.alpha_composite(layer,(0,round(18*S*(1-p))))
    out.putalpha(out.getchannel('A').point(lambda v:round(v*p)))
    return out


def caption_overlay(text_value, style='bar'):
    out=Image.new('RGBA',(PW,PH))
    d=Canvas(out)
    if style=='box':
        # Bold dark text on a bright rounded label in the lower third, one label per line.
        f=font(34,True)
        lines=[l for l in text_value.split('\n') if l]
        y0=736-31*(len(lines)-1)
        for k,line in enumerate(lines):
            tw=d.textlength(line,font=f); x=(W-tw)/2; y=y0+k*62
            d.rounded_rectangle((x-18,y-8,x+tw+18,y+50),12,fill=(255,225,77,245),outline=(24,24,24,255),width=3)
            d.text((x,y-2),line,font=f,fill=(24,24,24))
        return out
    # Readability fade over the full underlying picture, no padded borders.
    for y in range(785,H):
        a=round(100*((y-785)/(H-785))**1.2)
        d.line((0,y,W,y),fill=(9,22,18,a))
    f=font(28)
    lines=[]
    line=''
    for ch in text_value:
        if ch=='\n' or (line and d.textlength(line+ch,font=f)>508):
            lines.append(line); line='' if ch=='\n' else ch
        else:
            line+=ch
    if line: lines.append(line)
    y0=904-39*(len(lines)-1)
    for k,line in enumerate(lines):
        xx=(W-d.textlength(line,font=f))/2
        d.text((xx,y0+k*39),line,font=f,fill='white',stroke_width=2,stroke_fill=(16,36,29,225))
    return out


def vf(s,fps):
    x,y,w,h=s['crop']
    if abs(w/h-9/16)>.004:
        raise ValueError(f'Crop must be 9:16 to avoid stretching: {s["id"]}')
    duration=(s['end_frame']-s['start_frame'])/fps
    span=s.get('source_span',duration)
    # Only footage being enlarged is cleaned up; downscaled footage already has detail to spare.
    soft=ENHANCE and w<PW*.9
    return f'trim=duration={span},setpts=(PTS-STARTPTS)*{duration/span:.10f},{"hqdn3d=1.5:1.5:4:4," if soft else ""}crop={w}:{h}:{x}:{y},scale={PW}:{PH}:flags=lanczos,{"cas=0.6," if soft else ""}fps={fps},tpad=stop_mode=clone:stop_duration=0.15,setsar=1'


def compose(im,frame,plan,overlays):
    segment=next(s for s in plan['segments'] if s['start_frame']<=frame<s['end_frame'])
    accent=segment.get('accent')
    if accent:
        layer=Image.new('RGBA',(PW,PH)); d=Canvas(layer)
        labels=accent['labels']
        local=(frame-segment['start_frame'])/max(1,segment['end_frame']-segment['start_frame'])
        label=labels[min(len(labels)-1,int(local*len(labels)))]
        shift=round(16*(1-ease(((frame-segment['start_frame'])/plan['fps'])/.35)))
        for y in range(100,300):
            d.line((0,y,W,y),fill=(8,26,20,round(55*math.sin((y-100)/200*math.pi))))
        f=font(32,True)
        d.text((36,160+shift),label,font=f,fill='white',stroke_width=1,stroke_fill=(15,40,30,200))
        d.line((36,215+shift,36+int(100*ease(local*4)),215+shift),fill='#D4AC55',width=3)
        im=Image.alpha_composite(im.convert('RGBA'),layer).convert('RGB')
    cue=next((i for i,c in enumerate(plan['captions']) if c['start_frame']<=frame<c['end_frame']),None)
    if cue is not None:
        layer=caption_entry(overlays[cue],frame-plan['captions'][cue]['start_frame'],plan.get('caption_style','bar'))
        im=Image.alpha_composite(im.convert('RGBA'),layer).convert('RGB')
    return im


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('plan',type=Path)
    ap.add_argument('--preview',action='store_true')
    a=ap.parse_args()
    plan=json.loads(a.plan.read_text(encoding='utf8'))
    configure(plan)
    fps=plan['fps']; previous=0
    audio=plan.get('audio') or plan['reference']
    sources={audio}
    if plan.get('reference'): sources.add(plan['reference'])
    for s in plan['segments']:
        assert s['start_frame']==previous and s['end_frame']>previous
        previous=s['end_frame']
        if s['mode']=='footage':
            if plan.get('reference') and Path(s['path']).resolve()==Path(plan['reference']).resolve() and not plan.get('allow_reference_pictures',False):
                raise ValueError('This mix mode excludes reference pictures')
            sources.add(s['path'])
    assert previous==plan['total_frames']
    before={p:sha(p) for p in sorted(sources)}
    work=Path(plan['work']); work.mkdir(parents=True,exist_ok=True)
    overlays=[caption_for(c,plan.get('caption_style','bar')) for c in plan['captions']]
    if a.preview:
        thumbs=[]
        for s in plan['segments']:
            n=s['end_frame']-s['start_frame']; t=n/(2*fps)
            if s['mode']=='graphic':
                im=graphic(s,t)
            else:
                tmp=dict(s)
                tmp['source_in']=s['source_in']+s.get('source_span',n/fps)/2
                result=run(['ffmpeg','-v','error','-ss',str(tmp['source_in']),'-i',tmp['path'],'-vf',vf(s,fps),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
                im=Image.frombytes('RGB',(PW,PH),result.stdout[:PW*PH*3])
            im=compose(im,s['start_frame']+n//2,plan,overlays)
            im.save(work/(s['id']+'-preview.jpg'),quality=94)
            th=im.resize((192,341))
            tile=Image.new('RGB',(192,374),'white'); tile.paste(th,(0,0))
            ImageDraw.Draw(tile).text((4,347),f'{s["id"]} {s["start_frame"]/fps:.2f}s',font=ImageFont.truetype(FONT,16),fill=INK)
            thumbs.append(tile)
        for page in range(math.ceil(len(thumbs)/12)):
            batch=thumbs[page*12:(page+1)*12]
            sheet=Image.new('RGB',(192*4,374*math.ceil(len(batch)/4)),'#DDE6DF')
            for i,tile in enumerate(batch): sheet.paste(tile,((i%4)*192,(i//4)*374))
            sheet.save(work/f'preview-contact-{page+1}.jpg',quality=94)
        print('Previewed',len(thumbs),'segments',flush=True)
        return
    output=Path(plan['output'])
    if output.exists(): raise FileExistsError(output)
    silent=work/'picture.mp4'
    if silent.exists(): raise FileExistsError('Use a new work directory for changed render plans')
    (work/'source-hashes-before.json').write_text(json.dumps(before,ensure_ascii=False,indent=2),encoding='utf8')
    log=open(work/'encode.log','wb')
    enc=subprocess.Popen(['ffmpeg','-n','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{PW}x{PH}','-r',str(fps),'-i','-','-an','-c:v','libx264','-crf','18','-preset','fast','-pix_fmt','yuv420p','-movflags','+faststart',str(silent)],stdin=subprocess.PIPE,stderr=log)
    try:
        for s in plan['segments']:
            n=s['end_frame']-s['start_frame']
            dec=None
            if s['mode']=='footage':
                dec=subprocess.Popen(['ffmpeg','-v','error','-ss',str(s['source_in']),'-i',s['path'],'-vf',vf(s,fps),'-frames:v',str(n),'-f','rawvideo','-pix_fmt','rgb24','-'],stdout=subprocess.PIPE,stderr=log)
            for i in range(n):
                if dec:
                    raw=dec.stdout.read(PW*PH*3)
                    if len(raw)!=PW*PH*3: raise ValueError('Incomplete decoded frame: '+s['id'])
                    im=Image.frombytes('RGB',(PW,PH),raw)
                else:
                    im=graphic(s,i/fps)
                enc.stdin.write(compose(im,s['start_frame']+i,plan,overlays).tobytes())
            if dec:
                dec.stdout.close()
                if dec.wait()!=0: raise RuntimeError('Source decode failed')
            print('Rendered',s['id'],n,'frames',flush=True)
        enc.stdin.close()
        if enc.wait()!=0: raise RuntimeError('Encoder failed')
    finally:
        if enc.poll() is None: enc.kill()
        log.close()
    run(['ffmpeg','-n','-v','error','-i',str(silent),'-i',audio,'-map','0:v:0','-map','1:a:0','-c','copy','-movflags','+faststart',str(output)])
    media=probe(output)
    video=next(x for x in media['streams'] if x['codec_type']=='video')
    after={p:sha(p) for p in before}
    pa,pb=pcm(audio),pcm(output)
    run(['ffmpeg','-v','error','-i',str(output),'-f','null','-'])
    result=dict(output=str(output),source_hashes=before,sources_unchanged=before==after,
                audio_source=audio,audio_replaces_reference=bool(plan.get('audio')),
                reference_pcm_hash=pa,output_pcm_hash=pb,audio_identical=pa==pb,
                total_frames=int(video['nb_frames']),expected_frames=plan['total_frames'],
                full_decode_pass=True,reference_picture_frames=sum(s['end_frame']-s['start_frame'] for s in plan['segments'] if plan.get('reference') and s.get('path') and Path(s['path']).resolve()==Path(plan['reference']).resolve()),
                graphic_frames=sum(s['end_frame']-s['start_frame'] for s in plan['segments'] if s['mode']=='graphic'),
                footage_frames=sum(s['end_frame']-s['start_frame'] for s in plan['segments'] if s['mode']=='footage'),
                accent_frames=sum(s['end_frame']-s['start_frame'] for s in plan['segments'] if s.get('accent')),
                output_sha256=sha(output),media=media)
    (output.parent/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    assert result['sources_unchanged'] and result['audio_identical'] and result['total_frames']==plan['total_frames']
    print('PASS: copied audio PCM, source hashes, total frames and full decode',flush=True)


if __name__=='__main__': main()
