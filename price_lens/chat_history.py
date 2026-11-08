"""Chat-history prefixes and bounded, pixel-only row proposals above the HUD."""
from dataclasses import dataclass
import re

STAMP=re.compile(r'\[(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?\]\s*')
NAME=r'[A-Za-z0-9_가-힣]{2,16}'
HEADER=re.compile(r'(?:(?P<bracketed>\['+NAME+r'\])|(?P<name>'+NAME+r'))'
    r'(?:\s*(?:\[(?:CH|채널)\s*\d{1,3}\]|\bCH\s*\d{1,3}\b))?\s*:\s*(?P<body>.+)',re.IGNORECASE)
RESERVED={'판매','구매','모집','공지','알림','내용','sell','buy','notice'}


@dataclass(frozen=True)
class Prefix:
    speaker:str
    body:str
    body_start:int
    speaker_start:int
    speaker_end:int
    timestamp:bool


def parse_prefix(text):
    if not isinstance(text,str):return None
    start=len(text)-len(text.lstrip());stamp=STAMP.match(text,start)
    if re.match(r'\[\d{1,2}:',text[start:]) and stamp is None:return None
    position=stamp.end() if stamp else start
    match=HEADER.fullmatch(text,position)
    if match is None:return None
    key='bracketed' if match['bracketed'] else 'name';speaker=match[key].strip('[]')
    if speaker.casefold() in RESERVED:return None
    left,right=match.span(key)
    if key=='bracketed':left+=1;right-=1
    return Prefix(speaker,match['body'],match.start('body'),left,right,stamp is not None)


def header_without_badges(image,text,detail,*,history=False):
    """Remove only a native pale channel badge between timestamp and colon.

    Recognition positions bound this operation to the header. Complete pale
    capsule pixels plus red badge ink are required; message pixels are untouched.
    """
    import numpy as np
    from PySide6.QtGui import QImage
    from .chat_ocr import pixels,components
    stamp=STAMP.match(text);glyphs=detail.get('glyphs',())
    if not glyphs:return None
    if stamp is None and (not history or not re.match(r'\[?[A-Za-z0-9_가-힣]{2,32}',text)):return None
    separator=text.find(':',stamp.end() if stamp else 0)
    before=[r for r in glyphs if stamp and r[1]<=stamp.end()];after=[r for r in glyphs if r[0]<=separator<r[1]]
    if separator<0 or stamp and not before or len(after)!=1:return None
    low=max(r[3] for r in before) if before else 0;high=after[0][3]
    if high<=low:return None
    rgb=pixels(image).copy();neutral=rgb.max(2).astype('int16')-rgb.min(2)<85
    pale=neutral&(rgb.min(2)>180);scale=image.height()/15;changed=False
    background=np.median(rgb,axis=1).astype('uint8')
    for (x,y,right,bottom),count in components(pale,min_run=1):
        w,h=right-x,bottom-y
        if not (12*scale<=w<=48*scale and 4*scale<=h<=15*scale and count/(w*h)>.18):continue
        if x<low or right>high or x-low>160*scale:continue
        frame=pale[y:bottom,x:right];edge=max(1,round(2*scale))
        if min(frame[:edge].mean(1).max(),frame[-edge:].mean(1).max())<.65:continue
        badge=rgb[y:bottom,x:right].astype('int16')
        red=(badge[:,:,0]>140)&(badge[:,:,0]-badge[:,:,1]>35)&(badge[:,:,0]-badge[:,:,2]>45)
        if red.sum()<max(2,round(2*scale*scale)):continue
        x0=max(low,x-1);x1=min(high,right+1);y0=max(0,y-1);y1=min(image.height(),bottom+1)
        rgb[y0:y1,x0:x1]=background[y0:y1,None,:];changed=True;break
    if not changed:return None
    return QImage(rgb.tobytes(),image.width(),image.height(),image.width()*3,QImage.Format.Format_RGB888).copy()


def body_bounds(prefix,detail,*,minimum=.90):
    """Locate the body; rescuing a weak row also needs a confident sender."""
    glyphs=detail.get('glyphs',())
    header=[g for g in glyphs if g[0]<prefix.speaker_end and g[1]>prefix.speaker_start]
    body=[g for g in glyphs if g[1]>prefix.body_start]
    if not header or not body or min(g[4] for g in header)<minimum:return None
    return max(0,min(g[2] for g in body)-2)


def speaker_bounds(prefix,detail):
    """Measured sender pixels, independent of timestamp and message pixels."""
    glyphs=[g for g in detail.get('glyphs',())
            if g[0]<prefix.speaker_end and g[1]>prefix.speaker_start]
    if not glyphs:return None
    return min(g[2] for g in glyphs),max(g[3] for g in glyphs)


def row_ink(data,scale=1):
    """Find native text cores without treating translucent scenery as text.

    Ordinary chat uses pale neutral text over a darkened scene; its repeated
    foreground in the timestamp/name gutter establishes that palette. Bright
    channel rows retain their local contrast mask, including coloured links.
    This mask proposes geometry only; OCR still establishes language/content.
    """
    import numpy as np
    background=np.median(data,axis=1).astype('int16')
    ink=np.max(np.abs(data.astype('int16')-background[:,None,:]),axis=2)>55
    pale=(data.min(2)>185)&(data.max(2).astype('int16')-data.min(2)<45)
    gutter=pale[:,:min(data.shape[1],round(80*scale))]
    if np.median(background)<145 and gutter.sum()>=max(8,round(8*scale*scale)):
        # Preserve bright coloured item links beside the pale native text.
        return pale|((data.max(2)>185)&ink)
    return ink


def prepare_line(image):
    """Canonical current glyph pixels for a structurally detected history row.

    Source visibility still uses the captured image. Cache identity and optional
    OCR retries remove background variation; changed strokes make a new key.
    Unknown/empty/dense palettes retain their original pixels.
    """
    import numpy as np
    from PySide6.QtGui import QImage
    from .chat_ocr import pixels
    if image.isNull():return image
    ink=row_ink(pixels(image),max(.5,image.height()/14))
    if ink.sum()<8 or ink.mean()>.60:return image
    gray=np.where(ink,0,255).astype('uint8')
    result=QImage(gray.tobytes(),image.width(),image.height(),image.width(),QImage.Format.Format_Grayscale8).copy()
    result.setOffset(image.offset());return result


def history_regions(image,hud,exclude=()):
    """Propose complete lines using a paired native scrollbar above the HUD.

    The HUD is a search hint only. Scrollbar/frame pixels and separated text
    baselines are required; recognized prefixes establish a chat source later.
    """
    from PySide6.QtCore import QRect
    import numpy as np
    from .chat_ocr import pixels,components
    if not isinstance(hud,(list,tuple)) or len(hud)!=4 or any(type(v) is not int for v in hud):return [],[]
    footer=QRect(*hud)
    if not image.rect().contains(footer) or footer.width()<240 or footer.height()<8:return [],[]
    scale=footer.width()/800
    if not .5<=scale<=3:return [],[]
    left=footer.x();top=max(0,footer.y()-round(400*scale));bottom=max(top,footer.y()-round(18*scale))
    area=QRect(left,top,min(footer.width(),image.width()-left),bottom-top)
    if area.width()<120 or area.height()<20:return [],[]
    rgb=pixels(image.copy(area));r,g,b=(rgb[:,:,i].astype('int16') for i in range(3))
    blue=(b-r>35)&(g-r>20)&(b>110)&(g>75)
    buttons=[]
    for (x,y,right,end),count in components(blue,min_run=1):
        w,h=right-x,end-y
        if not (4*scale<=w<=15*scale and 4*scale<=h<=15*scale and .45<=count/(w*h)<=.96):continue
        pad=max(2,round(3*scale));patch=rgb[max(0,y-pad):end+pad,max(0,x-pad):right+pad]
        if not patch.size:continue
        neutral=patch.max(2).astype('int16')-patch.min(2)<45
        if (neutral&(patch.min(2)>170)).mean()<.24:continue
        buttons.append((x,y,w,h))
    pairs=[]
    for lower in buttons:
        x,y,w,h=lower;gap=footer.y()-(area.y()+y+h)
        if not 20*scale<=gap<=56*scale or x<120*scale:continue
        for upper in buttons:
            ux,uy,uw,uh=upper;span=y-(uy+uh)
            if abs(x-ux)>2*scale or abs(w-uw)>2*scale or not 10*scale<=span<=380*scale:continue
            pad=max(2,round(3*scale));rails=rgb[uy+uh:y,max(0,x-pad):x+w+pad]
            if not rails.size:continue
            neutral=rails.max(2).astype('int16')-rails.min(2)<60
            light=(neutral&(rails.min(2)>130)).mean(0)
            if min(float(light[:pad].max()),float(light[-pad:].max()))<.65:continue
            pairs.append((gap,-span,upper,lower))
    if not pairs:return [],[]
    _,_,upper,lower=min(pairs)
    ux,uy,uw,uh=upper;x,y,w,h=lower
    inset=max(3,round(4*scale))
    panel=QRect(area.x()+inset,area.y()+max(0,uy-1),max(0,ux-2*inset),y+h-max(0,uy-1))
    if panel.width()<100 or panel.height()<10:return [],[]
    data=pixels(image.copy(panel));background=np.median(data,axis=1).astype('int16')
    ink=np.max(np.abs(data.astype('int16')-background[:,None,:]),axis=2)>55
    margin=max(3,round(3*scale));ink[:,:margin]=False;ink[:,-margin:]=False
    gutter=ink[:,:min(panel.width(),round(60*scale))]
    counts=gutter.sum(1);active=(counts>=max(2,round(2*scale)))&(counts<gutter.shape[1]*.7)
    rows={};start=None
    for index,on in enumerate(np.r_[active,False]):
        if on and start is None:start=index
        if not on and start is not None:
            height=index-start
            if 6*scale<=height<=28*scale:
                # Native history rows are bottom-aligned on a 16 px baseline
                # grid. The 14 px text box retains taller Korean glyphs even
                # when the Latin sender/timestamp starts lower in that row.
                slot=round((panel.height()-7*scale-(start+index)/2)/(16*scale))
                y0=panel.height()-round((14+16*slot)*scale);end=min(panel.height(),y0+round(14*scale))
                if y0>=0:
                    band=row_ink(data[y0:end],scale);band[:,:margin]=False;band[:,-margin:]=False
                    columns=np.flatnonzero(band.any(0))
                else:columns=[]
                if len(columns)>=8:
                    right=min(panel.width(),int(columns[-1])+3);x0=max(margin,int(columns[0])-1)
                    box=[panel.x()+x0,panel.y()+y0,right-x0,end-y0]
                    if right>=40 and not any(QRect(*box).intersects(QRect(*r)) for r in exclude):rows[slot]=box
            start=None
    return ([rows[key] for key in sorted(rows)[:32]],[list(panel.getRect())]) if rows else ([],[])
