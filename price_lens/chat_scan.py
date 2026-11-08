"""Incremental full-window scans with a small cache of verified text pixels."""
from collections import OrderedDict
import hashlib
import re
import time

from PySide6.QtCore import QRect

from .chat_text import HANGUL, normalize, supported_ocr_alternative
from .chat_tracking import stamp, locate_offset, move_source


class ScanMemory:
    def __init__(self):
        self.reads=OrderedDict();self.sources=[];self.geometry=None;self.visits=OrderedDict();self.serial=0

    def prepare(self,image):
        geometry=(image.width(),image.height())
        if geometry!=self.geometry:self.sources=[];self.visits.clear();self.geometry=geometry
        now=time.monotonic()
        self.sources=[source for source in self.sources if now-source['seen']<=12][-12:]

    def priority(self,image,exclude,contexts,role_for):
        self.prepare(image);rows=[]
        for source in self.sources[-4:]:
            offset=locate_offset(image,source)
            if offset is None:continue
            dx,dy=offset;move_source(source,dx,dy)
            area=QRect(*source['box'])
            if not image.rect().contains(area) or any(area.intersects(QRect(*r)) for r in exclude):continue
            row=dict(source['row'])
            role,verified=role_for(source['box'],f"{row['speaker']}: {row['original']}",
                row['source_role']=='bubble',contexts,(image.width(),image.height()))
            if (role,verified)!=(row['source_role'],row['role_verified']):continue
            for key in ('box','track_box','speaker_box'):
                if source.get(key):row[key]=list(source[key])
            source['seen']=time.monotonic();rows.append(row)
        return rows

    def remember(self,row,image):
        track=row.get('track_box') or row['box']
        if track[2]*track[3]>100000:return
        reference=stamp(image,track)
        if not reference or max(reference)-min(reference)<45:return
        before=next((source for source in self.sources if source['row']['speaker']==row['speaker']
                     and source['row']['original']==row['original']
                     and source['row']['source_role']==row['source_role']
                     and QRect(*source['box']).intersects(QRect(*row['box']))),None)
        if before:self.sources.remove(before)
        source=dict(box=list(row['box']),track_box=list(track),track_stamp=reference,
            stamp=stamp(image,row['box']),track_pixels=image.copy(QRect(*track)),row=dict(row),seen=time.monotonic(),
            source_role=row['source_role'])
        if row.get('speaker_box'):
            source.update(speaker_box=list(row['speaker_box']),speaker_stamp=stamp(image,row['speaker_box']))
        self.sources.append(source);self.sources=self.sources[-12:]

    @staticmethod
    def key(crop,is_bubble,*,history=False):
        from .chat_ocr import pixels
        if history:
            from .chat_history import prepare_line
            crop=prepare_line(crop)
        return (is_bubble,crop.width(),crop.height(),hashlib.blake2s(pixels(crop).tobytes(),digest_size=16).digest())

    def visited(self,key):
        self.serial+=1;self.visits[key]=self.serial;self.visits.move_to_end(key)
        while len(self.visits)>192:self.visits.popitem(last=False)

    def read(self,crop,is_bubble,recognizer,cancelled,deadline,*,key=None,history=False):
        from .chat_ocr import lines, contrast_line
        from .chat_history import parse_prefix,header_without_badges,body_bounds,speaker_bounds,prepare_line
        key=key or self.key(crop,is_bubble,history=history)
        if history:key=('history',*key)
        if key in self.reads:
            self.reads.move_to_end(key);return self.reads[key]
        result=[];incomplete=False
        for line,height in (lines(crop) if is_bubble else [(crop,crop.height())]):
            if cancelled():return []
            # Stable glyph pixels identify history work, but primary recognition
            # retains the captured antialiasing. Binary-only first reads can
            # lose small sender/body details that the original image preserves.
            initial=line
            text,confidence=recognizer.read(initial)
            if cancelled():return []
            detail=recognizer.detail(initial) if hasattr(recognizer,'detail') else {}
            if history and confidence>=.97 and not HANGUL.search(text):continue
            prepared=line
            if not is_bubble:
                cleaned=header_without_badges(line,text,detail,history=history)
                if cleaned is not None:
                    if time.perf_counter()>=deadline:incomplete=True;continue
                    prepared=cleaned;clean_input=cleaned
                    text,confidence=recognizer.read(clean_input)
                    if cancelled():return []
                    detail=recognizer.detail(clean_input) if hasattr(recognizer,'detail') else {}
            prefix=parse_prefix(text) if not is_bubble else None
            if not is_bubble and (confidence<.92 or history and prefix is None):
                alternatives=(prepare_line(prepared),contrast_line(prepared)) if history else (contrast_line(prepared),)
                for alternate in alternatives:
                    if time.perf_counter()>=deadline:
                        if confidence<.90 or history and prefix is None:incomplete=True
                        break
                    other=recognizer.read(alternate)
                    if cancelled():return []
                    other_prefix=parse_prefix(other[0])
                    # A higher average must not replace an intact history
                    # header with a broken timestamp/name. A complete, clear
                    # alternate header can recover an otherwise unusable row.
                    if (other[1]>confidence and (not history or prefix is None or other_prefix is not None)
                            or history and prefix is None and other_prefix is not None and other[1]>=.90):
                        text,confidence=other
                        detail=recognizer.detail(alternate) if hasattr(recognizer,'detail') else {}
                    prefix=parse_prefix(text)
                    if confidence>=.92 and (not history or prefix is not None):break
            prefix=parse_prefix(text) if not is_bubble else None
            # A malformed timestamp is metadata, never Korean prose to send
            # to the translation model. Unprefixed continuation text is kept.
            if history and prefix is None and re.match(r'^\s*\[\d{1,2}:',text):continue
            sender=speaker_bounds(prefix,detail) if history and prefix else None
            sender_rect=([line.offset().x()+sender[0],line.offset().y(),sender[1]-sender[0],line.height()]
                         if sender and sender[1]>sender[0] else None)
            rescue=confidence<.90
            left=(body_bounds(prefix,detail,minimum=0 if history and not rescue else .90)
                  if prefix and (rescue or history) and HANGUL.search(prefix.body) else None)
            if left is not None:
                if time.perf_counter()>=deadline:
                    if rescue:incomplete=True;continue
                else:
                    body=line.copy(left,0,line.width()-left,line.height())
                    body_input=body
                    other=recognizer.read(body_input);body_detail=recognizer.detail(body_input) if hasattr(recognizer,'detail') else {}
                    if cancelled():return []
                    if other[1]<.90 and time.perf_counter()<deadline:
                        alternate=contrast_line(body);normalized=recognizer.read(alternate)
                        if cancelled():return []
                        if normalized[1]>other[1]:
                            other=normalized;body_detail=recognizer.detail(alternate) if hasattr(recognizer,'detail') else {}
                    elif other[1]<.90 and rescue:incomplete=True
                    if other[1]>=.90:
                        text=text[:prefix.body_start]+other[0];confidence=other[1];detail=body_detail
                        from PySide6.QtCore import QPoint
                        body.setOffset(line.offset()+QPoint(left,0));line=body
            if confidence<(.80 if is_bubble else .90):continue
            result.append(dict(text=text,confidence=confidence,rect=[line.offset().x(),line.offset().y(),line.width(),line.height()],
                speaker_rect=sender_rect,
                alternatives=detail.get('alternatives',()),content_right=detail.get('content_right',line.width()),
                meaningful=detail.get('meaningful',bool(re.search(r'[A-Za-z0-9가-힣ㄱ-ㅣ]',text)))))
        if incomplete and not result:return None
        self.reads[key]=result
        while len(self.reads)>128:self.reads.popitem(last=False)
        return result


def make_row(image,box,is_bubble,read,translator,contexts,role_for,cancelled):
    if not read:return None
    words=[line['text'] for line in read]
    role,verified=role_for(box,' '.join(words),is_bubble,contexts,(image.width(),image.height()))
    sender=''
    prefix=None
    if role=='chat':
        from .chat_history import parse_prefix
        prefix=parse_prefix(words[0])
        if prefix:sender=prefix.speaker;words[0]=prefix.body
    elif role=='bubble':
        prefix=re.match(r'^([^:]{1,24})\s*:\s*(.*)$',words[0])
        if prefix:sender=prefix[1].strip();words[0]=prefix[2]
    original=normalize(' '.join(words))
    if not HANGUL.search(original):return None
    korean=len(HANGUL.findall(original))
    if korean<2 and not re.fullmatch(r'[ㄱ-ㅣ가-힣]{1,8}',original):return None
    if (not is_bubble and korean<4 and korean/max(1,len(re.findall(r'[A-Za-zㄱ-ㅣ가-힣]',original)))<.20
            and not re.search(r'팝니다|삽니다|구함|구해|판매|구매|주세요',original)):return None
    alternatives=[]
    for index,line in enumerate(read):
        if prefix and index==0:continue  # Never correct a speaker identity.
        for text,confidence in line['alternatives']:
            changed=words.copy();changed[index]=text
            alternatives.append((normalize(' '.join(changed)),confidence))
    corrected=supported_ocr_alternative(original,alternatives)
    if cancelled():return None
    english,note=translator.translate(corrected or original)
    if cancelled():return None
    row=dict(box=list(box),speaker=sender,original=corrected or original,text=english,note=note,
             source_role=role,role_verified=verified)
    if corrected:row.update(ocr_original=original,note=note+' · Possible OCR correction')
    # Track the meaningful lines, excluding repeated emphasis and blank padding.
    # The speaker is confirmed separately so equal phrases from nearby players
    # cannot exchange anchors.
    inset=1 if is_bubble else 0;body=[]
    for index,line in enumerate(read):
        x,y,w,h=line['rect'];area=QRect(box[0]+inset+x,box[1]+inset+y,min(w,line['content_right']),h)
        area=area.intersected(QRect(*box))
        if index==0 and prefix and line.get('speaker_rect'):
            speaker=QRect(*line['speaker_rect']).translated(box[0]+inset,box[1]+inset).intersected(QRect(*box))
            if not speaker.isEmpty():row['speaker_box']=list(speaker.getRect())
        if prefix and index==0 and not words[0]:
            if not area.isEmpty():row['speaker_box']=list(area.getRect())
        elif line['meaningful'] and not area.isEmpty():body.append(area)
    if body:
        bounds=body[0]
        for area in body[1:]:bounds=bounds.united(area)
        if bounds.width()*bounds.height()<=100000:row['track_box']=list(bounds.getRect())
    return row


def scan_frame(image,recognizer,translator,emit,role_for,*,budget=.75,cancelled=lambda:False,
               exclude=(),contexts=(),memory=None,hud=None):
    from .chat_ocr import bubbles, text_regions
    from .chat_history import history_regions
    start=time.perf_counter();memory=memory or ScanMemory()
    count=readable=korean=processed=0;emitted=[]
    def result():
        return dict(count=count,bubbles=len(bubble_boxes),regions=region_count,processed=processed,
            readable=readable,korean=korean,elapsed_ms=round((time.perf_counter()-start)*1000,1))
    bubble_boxes=[];region_count=0
    if cancelled():return result()
    for row in memory.priority(image,exclude,contexts,role_for):
        if cancelled():return result()
        emit({**row,'elapsed_ms':round((time.perf_counter()-start)*1000,1)})
        emitted.append(row);count+=1
        if time.perf_counter()-start>budget:return result()
        if count>=2:break  # Reserve work for newly visible full-window text.
    if cancelled():return result()
    bubble_boxes=bubbles(image)
    history,panels=history_regions(image,hud,exclude=exclude)
    history_slots={tuple(box) for box in history}
    bubble_candidates=[(box,True) for box in bubble_boxes
        if not any(QRect(*box).intersects(QRect(*r)) for r in (*exclude,*panels))]
    def crop_for(box,is_bubble):
        x,y,w,h=box;crop=image.copy(x+1,y+1,w-2,h-2) if is_bubble else image.copy(x,y,w,h)
        return crop

    def inspect(box,is_bubble,key,crop=None):
        nonlocal processed,readable,korean,count
        if any(max(abs(a-b) for a,b in zip(box,row['box']))<=2 for row in emitted):return
        processed+=1
        # An unfinished contrast/header retry must yield to untouched rows on
        # the next frame. Its exact OCR work remains cached by the recognizer.
        memory.visited(key)
        read=memory.read(crop if crop is not None else crop_for(box,is_bubble),is_bubble,recognizer,cancelled,start+budget,key=key,history=tuple(box) in history_slots)
        if cancelled():return
        if read is None:return
        readable+=len(read)
        row=make_row(image,box,is_bubble,read,translator,contexts,role_for,cancelled)
        if row is not None:
            korean+=1;memory.remember(row,image)
            emit({**row,'elapsed_ms':round((time.perf_counter()-start)*1000,1)})
            emitted.append(row);count+=1

    # A new first bubble can still emit before full-window text detection.
    # Unchanged first bubbles no longer reset progress or starve later text.
    early=set()
    if bubble_candidates:
        box,is_bubble=bubble_candidates[0];crop=crop_for(box,is_bubble);key=memory.key(crop,is_bubble)
        if key not in memory.visits:
            early.add((tuple(box),is_bubble));inspect(box,is_bubble,key,crop)
            if cancelled() or count>=4 or time.perf_counter()-start>budget:return result()
    # Untouched rows come first; among them, short reads can finish without a
    # long English banner consuming the entire pass. Deferred work rotates
    # behind other rows instead of restarting at the newest one indefinitely.
    pending=[]
    for position,box in enumerate(history):
        crop=crop_for(box,False);key=memory.key(crop,False,history=True)
        if ('history',*key) in memory.reads:continue
        pending.append((memory.visits.get(key,0),crop.width()/crop.height(),position,box,crop,key))
    for _,_,_,box,crop,key in sorted(pending,key=lambda row:row[:3])[:1]:
        early.add((tuple(box),False));inspect(box,False,key,crop)
        if cancelled() or count>=4 or time.perf_counter()-start>budget:return result()
    generic=[(box,False) for box in text_regions(image,exclude=(*exclude,*bubble_boxes,*panels))
        if not any(QRect(*box).intersects(QRect(*r)) for r in exclude)]
    candidates=[]
    for position in range(max(len(bubble_candidates),len(generic),len(history))):
        if position<len(history):candidates.append((history[position],False))
        if position<len(bubble_candidates):candidates.append(bubble_candidates[position])
        if position<len(generic):candidates.append(generic[position])
    region_count=len(candidates);queue=[]
    for position,(box,is_bubble) in enumerate(candidates):
        if cancelled():return result()
        if (tuple(box),is_bubble) in early:continue
        key=memory.key(crop_for(box,is_bubble),is_bubble,history=tuple(box) in history_slots)
        queue.append((memory.visits.get(key,0),position,box,is_bubble,key))
    # Exact new/changed pixels first, then least recently examined candidates.
    # Positional cursors cannot reset this bounded progress on a new hotkey.
    for _,_,box,is_bubble,key in sorted(queue,key=lambda value:value[:2]):
        if cancelled() or count>=4 or processed and time.perf_counter()-start>budget:break
        inspect(box,is_bubble,key)
    return result()
