"""Accepted shop observations and native-description identity, without widgets."""
from collections import OrderedDict,deque
from dataclasses import dataclass
import hashlib
from math import ceil
import re
import time

import numpy as np
from PySide6.QtCore import QPoint,QRect,Qt
from PySide6.QtGui import QImage,QPainter,QRegion

from .item_identity import observed_item,resolve_shop_item,shop_icon_rect
from .shop_rows import ShopRows
from .shop_source import RowProof,capture_proof,proof_state,cursor_rectangle,native_occlusion,selected_component_pixels
from .tooltip_geometry import still_present,description_bounds,shop_description_bounds
from .tooltip_names import TooltipNames,name_key


def _complete_ellipsis(ink,scale):
    """Three small, baseline-aligned native dot clusters, matching the reader."""
    columns=np.any(ink,axis=0);right=ink.shape[1];dots=[]
    while right and len(dots)<3:
        while right and not columns[right-1]:right-=1
        if not right:return False
        end=right
        while right and columns[right-1]:right-=1
        rows=np.flatnonzero(np.any(ink[:,right:end],axis=1))
        top,bottom=int(rows[0]),int(rows[-1])
        if end-right>ceil(3*scale) or bottom-top+1>ceil(3*scale):return False
        dots.append((right,end,top,bottom))
    return (len(dots)==3 and dots[0][1]-dots[2][0]<=ceil(18*scale)
        and all(abs(dot[2]-dots[0][2])<=ceil(scale) and abs(dot[3]-dots[0][3])<=ceil(scale)
                for dot in dots))


@dataclass(frozen=True)
class ShopRead:
    shop: dict | None
    changed: bool = False
    viewport_changed: bool = False
    retry: bool = False


@dataclass(frozen=True)
class ShopFrame:
    changed: bool = False
    panel_changed: bool = False
    retired: bool = False
    container_lost: bool = False


class PriceObservations:
    """Own current rows, page retention and shop-description identity evidence.

    The caller supplies current capture coordinates/exclusions.  This controller
    never schedules capture, accesses prices, builds widgets or draws overlays.
    """
    def __init__(self,*,catalog=None,thumbnail_image=None):
        self.catalog=catalog
        self.thumbnail_image=thumbnail_image or (lambda identity:QImage())
        self.tooltip_names=TooltipNames()
        self.shop_rows=ShopRows(self.shop_identity)
        self.browsing=None
        self.rows=[]
        self.identity_candidates=()
        self.identity_cache=OrderedDict()
        self.shop_open=False
        self._shop_tooltip_rect=None
        self.occlusion_trail=deque(maxlen=3)
        self.shop_description=None
        self.shop_description_proof=None
        self.shop_tooltip_from_shop=False
        self.cursor_point=None;self.cursor_trail=deque(maxlen=8)

    @property
    def shop_tooltip_rect(self):return self._shop_tooltip_rect

    @shop_tooltip_rect.setter
    def shop_tooltip_rect(self,value):
        previous=self._shop_tooltip_rect
        if previous is not None and previous!=value:
            self.occlusion_trail.append((QRect(previous),time.monotonic()+.35))
        self._shop_tooltip_rect=QRect(value) if value is not None else None

    def native_exclusions(self,panel=None):
        """Bridge native-panel movement across captured/submitted frames only."""
        now=time.monotonic()
        while self.occlusion_trail and self.occlusion_trail[0][1]<now:self.occlusion_trail.popleft()
        scale=(self.shop_rows.area or {}).get('width',199)/199
        return tuple(native_occlusion(rect,scale) for rect in (
            *((panel,) if panel is not None else ()),*(entry[0] for entry in self.occlusion_trail)))

    @staticmethod
    def merge_exclusions(*groups):
        """Keep repeated caller/controller masks within the proof's hard bound."""
        return tuple({rect.getRect():rect for group in groups for rect in group}.values())

    def cursor_exclusions(self,pointer,*,now=None):
        """Bridge ordinary pointer coordinates arriving ahead of captured pixels."""
        now=time.monotonic() if now is None else now
        if pointer!=self.cursor_point:
            if self.cursor_point is not None:self.cursor_trail.append((self.cursor_point,now+.75))
            self.cursor_point=pointer
        while self.cursor_trail and self.cursor_trail[0][1]<now:self.cursor_trail.popleft()
        scale=(self.shop_rows.area or {}).get('width',199)/199
        return tuple(rect for point in (pointer,*(entry[0] for entry in self.cursor_trail))
                     if (rect:=cursor_rectangle(point,scale)) is not None)

    def item_for(self,row):return observed_item(self.catalog,row)

    def shop_identity(self,row):
        item=self.item_for(row)
        return item.game_id if item else None

    @staticmethod
    def fingerprint(image,rect):
        patch=image.copy(rect)
        return hashlib.blake2b(patch.constBits(),digest_size=8).digest()

    def identify_shop_row(self,native,image,*,pointer=None,exclude=(),allow_description=True):
        row={key:value for key,value in native.items() if key!='_item_id' and not key.startswith('_identity_')}
        name_only=row.get('nameOnly') is True
        if name_only:
            row.update(price=None,tier=None)
            if not self.shop_open or not self.container_matches(image,self.shop_tooltip_rect,exclude):
                return {'area':row.get('area',{}),'covered':True,'name':None,'price':None}
        candidates=tuple(self.catalog.candidates(row.get('name'),row.get('tier'))) if self.catalog else ()
        icon=shop_icon_rect(row);cache_key=None
        if (not name_only and 1<len(candidates)<=8 and icon is not None and image.rect().contains(icon)
                and not any(row.get(key) for key in ('covered','retained','listing_old','presentation_held'))):
            cache_key=(id(self.catalog),row.get('name'),row.get('tier'),icon.size().toTuple(),self.fingerprint(image,icon),
                tuple(self.thumbnail_image(item.game_id).cacheKey() for item in candidates))
        result=self.identity_cache.get(cache_key) if cache_key is not None else None
        if result is None:
            result=resolve_shop_item(self.catalog,row,image,self.thumbnail_image)
            if cache_key is not None:
                self.identity_cache[cache_key]=result;self.identity_cache.move_to_end(cache_key)
                while len(self.identity_cache)>96:self.identity_cache.popitem(last=False)
        row['_identity_reason']=result.reason
        if result.item is not None:
            row['_item_id']=result.item.game_id;row['_identity_evidence']=result.evidence
        elif candidates and allow_description:
            saved=self.shop_rows.rows.get(self.shop_rows.slot(row))
            previous=saved[0] if saved else {}
            if (previous.get('_identity_evidence')=='shop-description'
                    and previous.get('_identity_epoch')==self.browsing.epoch
                    and (item:=self.item_for(previous)) in candidates
                    and self.container_matches(image,self.shop_tooltip_rect,exclude)
                    and proof_state(previous.get('_identity_source'),image,pointer=pointer,exclude=exclude) in ('same','occluded')):
                row.update(_item_id=item.game_id,_identity_evidence='shop-description',_identity_reason='')
        try:
            box=QRect(*(row['area'][key] for key in ('x','y','width','height')))
            if name_only:
                title=QRect(*(row['nameArea'][key] for key in ('x','y','width','height')))
                if (not box.adjusted(-2,-2,2,2).contains(title) or title.height()>box.height()*.65
                        or title.y()>box.y()+3 or title.width()<12):
                    return {'area':row['area'],'covered':True,'name':None,'price':None}
                box=title
            elif icon is not None:box=box.united(icon)
            if (row.get('name') and not row.get('covered')
                    and image.rect().contains(box) and not box.isEmpty()):
                row['_identity_source']=capture_proof(image,box,pointer=pointer,exclude=exclude,
                    scale=max(.25,min(4,row['area']['width']/162)))
                if row['_identity_source'] is not None:row['_identity_epoch']=self.browsing.epoch
        except (KeyError,TypeError,ValueError):pass
        return row

    @staticmethod
    def component_proof(row,kind,image,latest,*,pointer=None,read_point=None,exclude=()):
        """Prove a complete exposed native line, independently of its blank tail.

        OCR supplies the text/number; this verifies its current native pixels.
        Names and ordinary asking lines require a natural blank ending. The
        numeric path proves complete quantities/amounts and the native blank
        boundary where a continuation would appear. Currency supplies no proof.
        """
        if (not isinstance(image,QImage) or image.isNull()
                or not isinstance(latest,QImage) or latest.isNull()):return None
        try:
            def rectangle(value):
                if not isinstance(value,dict) or any(type(value.get(k)) is not int for k in ('x','y','width','height')):return None
                return QRect(*(value[k] for k in ('x','y','width','height')))
            band=rectangle(row.get('area'));read=rectangle(row.get('_shop_read_area')) or band
            if band is None or read is None or band.isEmpty() or len(exclude)>64:return None
            scale=band.width()/162
            if not .25<=scale<=4:return None
            hint=rectangle(row.get(kind+'Area'))
            if hint is None:
                if kind+'Area' in row:return None
                height=round(17*scale);top=read.y()+(round(18*scale) if kind=='price' else 0)
                hint=QRect(read.x(),top,read.width(),min(height,read.bottom()-top+1))
            if (hint.width()<12 or hint.height()<5 or hint.width()*hint.height()>65_536
                    or not band.adjusted(-2,-2,2,2).contains(hint)
                    or not read.adjusted(-2,-2,2,2).contains(hint)
                    or hint.height()>band.height()*.65
                    or kind=='name' and hint.y()>band.y()+max(3,round(3*scale))
                    or kind=='price' and hint.y()<band.y()+band.height()*.35
                    or not image.rect().contains(hint) or not latest.rect().contains(hint)):return None
            patch=image.copy(hint).convertToFormat(QImage.Format.Format_RGBA8888)
            pixels=np.frombuffer(patch.constBits(),dtype=np.uint8).reshape(patch.height(),patch.bytesPerLine())
            rgb=pixels[:,:patch.width()*4].reshape(patch.height(),patch.width(),4)[:,:,:3].astype(np.float32)
            choices=[]
            for selected,base in ((False,np.array((202,213,223))),(True,np.array((251,167,46)))):
                gain=(rgb*base).sum(axis=2)/float(base@base)
                native=(gain>=0)&(gain<=1.16)&(np.max(np.abs(rgb-gain[:,:,None]*base),axis=2)<=8)
                background=native&(gain>=.45)
                if int(background.sum())>=rgb.shape[0]*rgb.shape[1]*.30:
                    choices.append((int(background.sum()),gain,native,selected))
            if not choices:return None
            _,gain,native,selected=max(choices,key=lambda value:value[0])
            if selected:
                normalized=selected_component_pixels(rgb,scale)
                if normalized is None:return None
                gain,native=normalized
            white=np.min(rgb,axis=2)>=235
            heights=np.arange(hint.height())[:,None]
            # OCR ascent can include the native horizontal separator by one
            # pixel, both above a name and above its asking line. Recognize a
            # broad edge rule only; isolated white caption/description pixels
            # remain foreign. The returned source still includes the rule and
            # must match the newest frame exactly, just like every glyph.
            top_rule=(heights<max(1,round(2*scale)))&(white.sum(axis=1)[:,None]>=hint.width()*.85)
            white&=(heights>=hint.height()-3)|top_rule
            foreign=~native&~white
            bad=np.flatnonzero(foreign.sum(axis=0)*4>hint.height())
            width=int(bad[0]) if len(bad) else hint.width()
            # Native component OCR rounds this normalized value to 8-bit ink
            # and uses <160. Counting a fainter antialias fringe as another
            # glyph column here would demand blank pixels outside its proof.
            ink=native&(gain<(159.5/255))
            columns=np.flatnonzero(np.any(ink[:,:width],axis=0))
            if not len(columns) or int(ink[:,:width].sum())<8:return None
            semantic=kind=='price' and ('priceValueArea' in row or 'priceText' in row)
            if semantic:
                # Bind the two-pass numeric read to its current glyphs. Prove
                # the next possible comma/digit slot is blank independently of
                # the currency suffix, which may be covered or misread.
                value=rectangle(row.get('priceValueArea'))
                asking=row.get('price');text=row.get('priceText')
                match=re.fullmatch(r'([1-9][0-9]*) for ([1-9][0-9]{0,2}(?:,[0-9]{3})*)',text) if isinstance(text,str) and len(text)<=100 else None
                if (not isinstance(asking,dict) or match is None
                        or type(asking.get('quantity')) is not int or type(asking.get('mesos')) is not int
                        or int(match[1])!=asking['quantity'] or int(match[2].replace(',',''))!=asking['mesos']
                        or value is None or value!=hint or value.width()<12 or np.any(foreign)):return None
                occupied=ink.any(axis=0)
                edges=np.diff(np.r_[False,occupied,False].astype(np.int8))
                starts=np.flatnonzero(edges==1);ends=np.flatnonzero(edges==-1)
                if not len(starts):return None
                last_rows=np.flatnonzero(ink[:,int(starts[-1]):int(ends[-1])].any(axis=1))
                if not len(last_rows) or int(last_rows[-1])-int(last_rows[0])+1<ceil(5*scale):return None
                advance=max(1,int(11*band.width()/253+.5))
                # Adjacent native zeroes can share one ink run. Count their
                # measured digit cells, rather than mistaking a joined pair
                # for a single character or depending on currency letters.
                cells=max(1,int((int(ends[-1])-int(starts[-1]))/advance+.5))
                last_cell=int(starts[-1])+(cells-1)*advance
                grouped=len(match[2].rsplit(',',1)[-1])==3
                boundary=last_cell+advance+(max(1,ceil(2*scale)) if grouped else advance)
                if (hint.x()-band.x()+int(starts[0])>ceil(12*scale)
                        or boundary>hint.width() or boundary<=int(ends[-1])
                        or np.any(ink[:,int(ends[-1]):boundary])):return None
                measured=(int(ends[-1])-int(starts[0]))*253/band.width()
                expected=28+11*(len(match[1])+sum(c.isdigit() for c in match[2]))+4.7*match[2].count(',')
                if abs(measured-expected)>5.5:return None
                source=QRect(hint);semantic_source=value
            else:
                # Complete native ellipses have their own small blank margin.
                # Other names and ordinary asking lines keep the full guard.
                ellipsis=kind=='name' and str(row.get('name') or '').rstrip().endswith(('...','…'))
                if ellipsis and not _complete_ellipsis(ink[:,:width],scale):return None
                end=int(columns[-1])+1+max(4,ceil(4*scale) if ellipsis else round(10*scale))
                if end>width or np.any(foreign[:,:end]):return None
                source=QRect(hint.x(),hint.y(),end,hint.height());semantic_source=source
            # A cursor's black outline can fit the native ink palette. Never
            # treat ink within either footprint or any known cover as text.
            masks=(*exclude,*(rect for point in (pointer,read_point)
                if (rect:=cursor_rectangle(point,scale)) is not None))
            for mask in masks:
                part=semantic_source.intersected(mask)
                if not part.isEmpty() and np.any(ink[part.top()-hint.top():part.bottom()-hint.top()+1,
                        part.left()-hint.left():part.right()-hint.left()+1]):return None
            # Exact native component pixels must remain present in the newest
            # frame. A broad mask cannot hide a changed/blocked digit or suffix.
            if image.copy(source)!=latest.copy(source):return None
            return capture_proof(latest,source,scale=scale)
        except (KeyError,TypeError,ValueError,OverflowError):return None

    def component_row(self,row,image,latest,*,pointer=None,read_point=None,exclude=(),panel=None):
        """Recover fresh component authority, never a previous offer or title."""
        if not (self.shop_open and self.container_matches(image,panel,exclude)
                and self.container_matches(latest,panel,exclude)):return None
        name=self.component_proof(row,'name',image,latest,pointer=pointer,read_point=read_point,exclude=exclude)
        if name is None:return None
        price=(self.component_proof(row,'price',image,latest,pointer=pointer,read_point=read_point,exclude=exclude)
               if row.get('price') and not row.get('nameOnly') else None)
        native={key:value for key,value in row.items() if key!='_item_id'
                and not key.startswith(('_identity_','_shop_'))}
        native['nameArea']=dict(zip(('x','y','width','height'),name.rect))
        icon=shop_icon_rect(native)
        masks=(*exclude,*(rect for point in (pointer,read_point)
            if (rect:=cursor_rectangle(point,(row.get('area') or {}).get('width',162)/162)) is not None))
        icon_current=bool(icon is not None and image.rect().contains(icon) and latest.rect().contains(icon)
            and not any(icon.intersects(mask) for mask in masks) and image.copy(icon)==latest.copy(icon))
        if not icon_current:native['tier']=None
        candidates=self.catalog.candidates(native.get('name'),native.get('tier')) if self.catalog else ()
        if price is None or not icon_current and len(candidates)>1:
            native.update(nameOnly=True,price=None,tier=None)
            native.pop('priceArea',None)
            native.pop('priceValueArea',None);native.pop('priceText',None)
        else:native['priceArea']=dict(zip(('x','y','width','height'),price.rect))
        # A popup may still describe the old hovered item after a wheel. Only
        # the newly proved name and, when exposed, its current icon resolve this.
        return self.identify_shop_row(native,latest,pointer=pointer,exclude=exclude,allow_description=False)

    def refresh_identity_candidates(self):
        needed={}
        if self.catalog:
            for row in self.rows:
                if self.item_for(row) is not None:continue
                candidates=self.catalog.candidates(row.get('name'),row.get('tier'))
                if 1<len(candidates)<=8:
                    needed.update((item.game_id,item) for item in candidates)
        self.identity_candidates=tuple(needed.values())[:16]

    def refresh_identity(self,image,*,pointer=None,exclude=()):
        changed=False
        for index,row in enumerate(self.rows):
            proof=row.get('_identity_source')
            if (row.get('shop_page')!=self.shop_rows.page_revision or proof is None
                    or row.get('_identity_epoch')!=self.browsing.epoch
                    or proof_state(proof,image,pointer=pointer,exclude=exclude)!='same'):continue
            resolved=self.identify_shop_row(row,image,pointer=pointer,exclude=exclude)
            if resolved.get('_item_id')!=row.get('_item_id'):
                self.rows[index]=resolved
                slot=self.shop_rows.slot(row);saved=self.shop_rows.rows.get(slot)
                if saved is not None:self.shop_rows.rows[slot]=(dict(resolved),saved[1])
                changed=True
        if changed:self.refresh_identity_candidates()
        return changed

    def container_matches(self,image,panel=None,exclude=()):
        exclude=(*exclude,*self.native_exclusions())
        return bool(self.shop_rows.guards and (
            self.shop_rows.guards_match(image,exclude)
            or panel is not None and self.shop_rows.tooltip_guards_match(image,panel,exclude)))

    def page_hold_slots(self,image,panel=None,exclude=(),pointer=None):
        """Retain loaded references under hover while exposed names prove this page.

        This never verifies a current offer. A positive viewport change still
        clears every cached item, and an exposed changed title cannot inherit
        the previous slot's identity even when neighbouring rows are unchanged.
        """
        if not (self.shop_open and self.shop_rows.active and self.shop_rows._page_proven
                and self.browsing and not self.browsing.pending):return set()
        states=self.browsing.name_states(image,self.shop_rows.area,tooltip=panel,
            exclude=exclude,pointer=pointer)
        if 'same' not in states.values():return set()
        blocked=(*self.native_exclusions(panel),*self.cursor_exclusions(pointer))
        held=set()
        for slot in self.shop_rows.rows:
            rect=QRect(*slot)
            state=next((state for area,state in states.items()
                if all(abs(a-b)<=3 for a,b in zip(slot,area))),'unknown')
            # Unknown native ink under a pane cannot refute a loaded page.
            # Require a genuinely readable title in its original template;
            # uniform background must never become a page/item anchor.
            if state=='unknown' or state=='same' and any(rect.intersects(mask) for mask in blocked):held.add(slot)
        return held

    def restore_visible(self,image,rows,*,pointer=None,exclude=()):
        eligible=[]
        for index,row in enumerate(rows):
            saved=self.shop_rows.rows.get(self.shop_rows.slot(row))
            if saved and proof_state(saved[0].get('_identity_source'),image,pointer=pointer,exclude=exclude)=='same':eligible.append(index)
        restored=iter(self.shop_rows.restore_visible(image,[rows[index] for index in eligible],exclude=exclude))
        indices=set(eligible)
        return [next(restored) if index in indices else row for index,row in enumerate(rows)]

    def retire_source(self):
        self.rows=[];self.shop_open=False;self.identity_candidates=()
        self.shop_rows.retire_context()
        self.clear_description()
        self.shop_tooltip_from_shop=False
        self.occlusion_trail.clear()

    def viewport_changed(self):
        self.shop_rows.invalidate_viewport()
        self.rows=[];self.identity_candidates=()
        self.clear_description()
        self.occlusion_trail.clear()

    def observe_shop(self,shop,image,latest,*,pointer=None,read_point=None,panel=None,exclude=(),source_exclude=()):
        previous=self.rows;viewport_changed=False
        frame_exclude=tuple(exclude)
        scale=((shop or {}).get('area') or self.shop_rows.area or {}).get('width',199)/199
        cursors=self.cursor_exclusions(pointer)
        panels=self.native_exclusions(panel)
        source_exclude=self.merge_exclusions(source_exclude,cursors,panels)
        exclude=self.merge_exclusions(exclude,cursors,panels,tuple(rect for point in (read_point,)
            if (rect:=cursor_rectangle(point,scale)) is not None))
        had_container=self.container_matches(image,panel,exclude)
        native_priced_rows=sum(bool(row.get('name') and row.get('price') and not row.get('covered'))
                              for row in ((shop or {}).get('rows') or []) if isinstance(row,dict))
        if isinstance(shop,dict):
            # A native pane can truncate the OCR table at its visible edge.
            # Independent guards and the old row pixels retain the full list;
            # a smaller OCR crop cannot move labels or replace that geometry.
            if panel is not None and self.shop_rows.area and self.container_matches(latest,panel,exclude):
                saved_area=QRect(*(self.shop_rows.area[k] for k in ('x','y','width','height')))
                area=(shop.get('area') or {})
                candidate=QRect(*(area.get(k,0) for k in ('x','y','width','height')))
                if saved_area.adjusted(-6,-6,6,6).contains(candidate) and candidate.intersects(saved_area):
                    native=[]
                    for row in (shop.get('rows') or [])[:self.shop_rows.ROW_LIMIT]:
                        current=row.get('area') or {}
                        match=next((previous for previous,_ in self.shop_rows.rows.values()
                            if abs(current.get('x',-1000)-previous['area']['x'])<=4
                            and abs(current.get('y',-1000)-previous['area']['y'])<=4
                            and 0<current.get('width',0)<=previous['area']['width']+3
                            and 0<current.get('height',0)<=previous['area']['height']+3),None)
                        if match is not None:
                            clipped=(current.get('width',0)<match['area']['width']-3 or current.get('height',0)<match['area']['height']-3)
                            row={**row,'area':dict(match['area'])}
                            if clipped and QRect(*self.shop_rows.slot(match)).intersects(native_occlusion(panel,scale)):
                                # Canonical geometry is not a reason to discard
                                # exposed text. Preserve the original OCR extent
                                # so complete components can prove their own ink.
                                row.update(_shop_clipped=True,_shop_read_area=dict(current))
                        native.append(row)
                    shop={**shop,'area':dict(self.shop_rows.area),'rows':native}
            raw=[self.identify_shop_row(row,image,pointer=read_point,exclude=source_exclude)
                 for row in (shop.get('rows') or [])[:self.shop_rows.ROW_LIMIT]]
            states=[proof_state(row.get('_identity_source'),latest,pointer=pointer,exclude=source_exclude)
                    if not row.get('covered') and row.get('name') else 'occluded' for row in raw]
            for index,(row,state) in enumerate(zip(raw,states)):
                clipped=row.pop('_shop_clipped',False)
                semantic='priceValueArea' in row or 'priceText' in row
                if (row.get('name') and not row.get('covered') and state!='changed'
                        and (clipped or semantic or state in ('occluded','unknown'))):
                    repaired=self.component_row(row,image,latest,pointer=pointer,read_point=read_point,
                        exclude=source_exclude,panel=panel)
                    if repaired is not None:
                        raw[index]=row=repaired
                        states[index]=proof_state(row.get('_identity_source'),latest,pointer=pointer,exclude=source_exclude)
                    elif clipped or semantic:
                        raw[index]={'area':row['area'],'name':None,'price':None,'covered':True}
                        states[index]='occluded'
                row.pop('_shop_read_area',None)
            if 'changed' in states:
                # Reject this late/inconsistent OCR result independently of
                # accepted rows that still match the newest captured pixels.
                # A bad submission cannot blank a still-verified shop page.
                if self.rows:
                    frame=self.validate_frame(latest,pointer=pointer,exclude=frame_exclude,
                        source_exclusions=lambda panel:source_exclude)
                    return ShopRead(shop,changed=frame.changed,retry=True)
                return ShopRead(shop,retry=True)
            raw=[row if state=='same' or row.get('covered') else
                 {'area':row['area'],'name':None,'price':None,'covered':True} for row,state in zip(raw,states)]
            if self.container_matches(latest,panel,exclude):
                # Canonicalize before capturing browsing templates, not only
                # before merging rows. Otherwise 1px OCR rounding accumulates
                # duplicate slots whose shifted glyphs look like a new page.
                self.shop_rows.stable_slots(raw)
                saved=self.shop_rows.area;area=shop.get('area') or {}
                if saved and (any(row.get('nameOnly') for row in raw)
                        or all(abs(area.get(k,-1000)-saved[k])<=3 for k in ('x','y','width','height'))):
                    shop={**shop,'area':dict(saved)}
            shop={**shop,'rows':raw}
            if self.browsing.observe_rows(raw,image,area=shop.get('area') or self.shop_rows.area,
                    tooltip=panel,exclude=exclude,pointer=read_point,latest=latest):
                self.viewport_changed();viewport_changed=True
            for row in raw:
                if row.get('_identity_source') is not None:row['_identity_epoch']=self.browsing.epoch
            held=self.page_hold_slots(latest,panel,source_exclude,pointer)
            if self.container_matches(latest,panel,exclude):
                present={self.shop_rows.slot(row) for row in raw}
                for saved,_ in self.shop_rows.rows.values():
                    proof=saved.get('_identity_source')
                    state=proof_state(proof,latest,pointer=pointer,exclude=source_exclude)
                    hidden=(state=='unknown' and isinstance(proof,RowProof)
                        and latest.rect().contains(QRect(*proof.rect))
                        and any(rect.intersects(QRect(*self.shop_rows.slot(saved))) for rect in (*panels,*cursors)))
                    # No visible comparison is expected when a proven native
                    # pane/cursor covers the remaining source pixels. Retain
                    # only the last-seen presentation for this unchanged page.
                    if self.shop_rows.slot(saved) not in present and (state in ('same','occluded') or hidden
                            or self.shop_rows.slot(saved) in held):
                        raw.append({'area':dict(saved['area']),'covered':True,'name':None,'price':None})
                raw.sort(key=lambda row:row['area']['y'])
                shop={**shop,'rows':raw[:self.shop_rows.ROW_LIMIT]}
        # A visible row change can precede an exposed scrollbar or a usable OCR
        # reply. Never let the container-only recovery path resurrect those old
        # items while the new page is partly covered by a native description.
        held=self.page_hold_slots(latest,panel,source_exclude,pointer)
        for slot,(saved,_) in tuple(self.shop_rows.rows.items()):
            if slot not in held and proof_state(saved.get('_identity_source'),latest,pointer=pointer,exclude=source_exclude)=='changed':
                self.shop_rows.rows.pop(slot,None);self.shop_rows.row_pixels.pop(slot,None)
        rows=self.shop_rows.observe(shop,image,tooltip=panel,exclude=exclude)
        if panel is None:rows=self.restore_visible(latest,rows,pointer=pointer,exclude=source_exclude)
        self.shop_open=self.shop_rows.active
        if not self.shop_open and self.browsing.area is not None:self.browsing.reset()
        self.rows=rows;self.refresh_identity_candidates()
        # A first read can establish the table guards while its independently
        # recovered components still require that guard proof. Do the follow-up
        # immediately; an unchanged-shop fingerprint would otherwise postpone
        # it until the periodic locator pass. This transition occurs once per
        # newly proved container and never accepts an unverified component.
        retry=bool(not had_container and self.shop_open
            and native_priced_rows>sum(bool(row.get('name') and row.get('price')) for row in rows)
            and self.container_matches(latest,panel,exclude))
        return ShopRead(shop,changed=rows!=previous,viewport_changed=viewport_changed,retry=retry)

    def validate_frame(self,image,*,pointer=None,shop_context=None,exclude=(),source_exclusions=None):
        changed=panel_changed=False
        scale=(self.shop_rows.area or {}).get('width',199)/199
        # Cursor coordinates and captured pixels arrive independently. Never
        # erase a native header using a newer pointer position that happens to
        # land on it; geometry requires actual native frame/body pixels instead.
        # Source comparisons still exclude the bounded cursor footprints.
        geometry_exclude=tuple(exclude)
        cursors=self.cursor_exclusions(pointer)
        # The previous pane is an exclusion from source comparisons only. It
        # must not hide the current native body from geometry validation.
        exclude=tuple(exclude)+cursors
        def hidden_for(panel):
            return self.merge_exclusions(source_exclusions(panel) if source_exclusions else exclude,
                                         cursors,self.native_exclusions(panel))
        if self.shop_open:
            panel=self.shop_tooltip_rect
            hidden=hidden_for(panel)
            disrupted=(not self.container_matches(image,panel,exclude) or any(
                row.get('_identity_source') is not None and
                proof_state(row['_identity_source'],image,pointer=pointer,exclude=hidden)=='changed'
                for row in self.rows))
            if (panel is not None and not still_present(image,panel,geometry_exclude)) or disrupted:
                proof=self.shop_description_proof
                name=proof.get('name') if proof else None
                candidate=shop_description_bounds(image,pointer,scale=scale,exclude=geometry_exclude)
                if candidate is None and name is not None:
                    candidate=description_bounds(image,dict(zip(('x','y','width','height'),name.getRect())),geometry_exclude,source_verified=True)
                if candidate is not None and self.container_matches(image,candidate,exclude):
                    self.shop_tooltip_rect=candidate;changed=panel_changed=candidate!=panel
                    if self.source_row(self.rows,pointer,pointer)[0] is not None:self.shop_tooltip_from_shop=True
        if self.shop_tooltip_rect is not None and not still_present(image,self.shop_tooltip_rect,geometry_exclude):
            self.shop_tooltip_rect=None;changed=panel_changed=True
            self.shop_tooltip_from_shop=False
            self.rows=[{**row,'covered':False} for row in self.rows]
            hidden=hidden_for(None)
            self.rows=self.restore_visible(image,self.rows,pointer=pointer,exclude=hidden)
        hidden=hidden_for(self.shop_tooltip_rect)
        matches=self.container_matches(image,self.shop_tooltip_rect,exclude)
        if self.shop_open and not matches:
            self.retire_source()
            return ShopFrame(changed=True,panel_changed=panel_changed,retired=True,container_lost=True)
        rejected=[row for row in self.rows if matches and row.get('_identity_source') is not None
                  and proof_state(row['_identity_source'],image,pointer=pointer,exclude=hidden)=='changed']
        if rejected:
            # A different row is not a closed shop. Retain independent table
            # geometry even when every listing needs a fresh read; otherwise a
            # native shop description can escape into inventory-hover pricing.
            held=self.page_hold_slots(image,self.shop_tooltip_rect,hidden,pointer)
            slots={self.shop_rows.slot(row) for row in rejected}
            previous=self.rows;rows=[]
            for row in self.rows:
                slot=self.shop_rows.slot(row)
                if slot not in slots:rows.append(row)
                elif slot in held:
                    row={**row,'covered':True,'retained':True,'reference_only':True,
                        'listing_old':True,'price':None}
                    rows.append(self.shop_rows.decorate(row,time.monotonic()))
            self.rows=rows
            for slot in slots-held:
                self.shop_rows.rows.pop(slot,None);self.shop_rows.row_pixels.pop(slot,None)
            self.refresh_identity_candidates()
            changed=changed or self.rows!=previous
            return ShopFrame(changed=changed,panel_changed=panel_changed,retired=self.rows!=previous)
        if self.shop_description and not self.description_matches(image,pointer,shop_context=shop_context,exclude=exclude):
            self.clear_description();changed=True
        return ShopFrame(changed,panel_changed)

    def clear_description(self):
        changed=self.shop_description is not None
        self.shop_description=None;self.shop_description_proof=None
        return changed

    def description_matches(self,image,pointer,*,shop_context=None,exclude=()):
        proof=self.shop_description_proof
        if not proof or not self.shop_open or self.shop_tooltip_rect is None or proof['page']!=self.shop_rows.page_revision:return False
        if pointer is None or shop_context is None or not shop_context.contains(QPoint(*pointer)):return False
        source=proof['source']
        if source is not None and not source.contains(QPoint(*pointer)):return False
        if source is None and max(abs(a-b) for a,b in zip(pointer,proof['pointer']))>8:return False
        if not still_present(image,self.shop_tooltip_rect,exclude):return False
        return self.description_title_matches(image,proof,exclude) or self.description_source_matches(image,proof,exclude)

    def description_source_matches(self,image,proof,exclude):
        if not proof.get('item_id') or proof.get('source') is None or not self.shop_rows._page_proven:return False
        visible=QRegion(proof['name'])
        for rect in (*proof['exclude'],*exclude):visible=visible.subtracted(QRegion(rect))
        if sum(part.width()*part.height() for part in visible)>=proof['name'].width()*proof['name'].height()*.25:return False
        row,band=self.source_row(self.rows,proof['pointer'],proof['pointer']);item=self.item_for(row)
        return bool(item and item.game_id==proof['item_id'] and band==proof['source']
                    and self.shop_rows.tooltip_guards_match(image,self.shop_tooltip_rect,exclude))

    @staticmethod
    def source_row(rows,pointer,read_point):
        if pointer is None or read_point is None:return None,None
        for row in rows:
            area=row.get('area') or {}
            if not area:continue
            band=QRect(*(area[part] for part in ('x','y','width','height')))
            band=band.adjusted(-round(band.width()*.26),0,0,0)
            if band.contains(QPoint(*pointer)) and band.contains(QPoint(*read_point)):return row,band
        return None,None

    @staticmethod
    def description_title_matches(image,proof,exclude):
        rect=proof['name']
        if not image.rect().contains(rect):return False
        before=proof['pixels'].copy();after=image.copy(rect);hidden=[];visible=QRegion(rect)
        for excluded in (*proof['exclude'],*exclude):
            part=rect.intersected(excluded)
            if not part.isEmpty():hidden.append(part.translated(-rect.x(),-rect.y()));visible=visible.subtracted(QRegion(part))
        if sum(part.width()*part.height() for part in visible)<rect.width()*rect.height()*.25:return False
        for patch in (before,after):
            painter=QPainter(patch)
            for part in hidden:painter.fillRect(part,Qt.GlobalColor.black)
            painter.end()
        found={**proof['found'],'area':dict(x=0,y=0,width=rect.width(),height=rect.height())}
        signature=name_key(found,before)
        return signature is not None and signature==name_key(found,after)

    def update_description(self,native,rows,image,latest,pointer,read_point,*,allow,shop_context=None,exclude=()):
        if not allow or not self.shop_open or pointer is None or shop_context is None or not shop_context.contains(QPoint(*pointer)):
            self.clear_description();return
        matches=lambda:self.description_matches(latest,pointer,shop_context=shop_context,exclude=exclude)
        if matches() and not native:return
        found=self.tooltip_names.resolve(native,image,self.catalog) if isinstance(native,dict) else None
        item=self.item_for(found);row,source=self.source_row(rows,pointer,read_point);listed=self.item_for(row)
        if not item and found and listed and self.shop_rows._page_proven and self.shop_tooltip_rect is not None:
            try:
                rect=QRect(*(int(found['area'][part]) for part in ('x','y','width','height')))
                probe=dict(name=rect,exclude=tuple(exclude),source=source,pointer=pointer,item_id=listed.game_id)
                if self.description_source_matches(latest,probe,exclude):item=listed
            except (KeyError,TypeError,ValueError):pass
        if not item or self.shop_tooltip_rect is None or read_point is None or max(abs(a-b) for a,b in zip(pointer,read_point))>8:
            if not matches():self.clear_description()
            return
        try:name=QRect(*(int(found['area'][part]) for part in ('x','y','width','height')))
        except (KeyError,TypeError,ValueError):self.clear_description();return
        if not image.rect().contains(name) or not self.shop_tooltip_rect.contains(name):self.clear_description();return
        if listed and listed.game_id!=item.game_id and (row.get('_identity_evidence')!='shop-description'
                or item not in self.catalog.candidates(row.get('name'),row.get('tier'))):
            self.clear_description();return
        proof=dict(found=found,name=name,pixels=image.copy(name),exclude=tuple(exclude),source=source,pointer=pointer,
            page=self.shop_rows.page_revision,item_id=listed.game_id if listed else None)
        if not still_present(latest,self.shop_tooltip_rect,exclude) or not (
                self.description_title_matches(latest,proof,exclude) or self.description_source_matches(latest,proof,exclude)):
            self.clear_description();return
        # The description is identification evidence only, never another card.
        # A clipped visible listing may be resolved by its actual full header;
        # a hidden unknown row never borrows a guessed source identity.
        if row is not None and (listed is None or listed.game_id!=item.game_id) and row.get('name') and item in self.catalog.candidates(row['name'],row.get('tier')):
            row.update(_item_id=item.game_id,_identity_evidence='shop-description',_identity_reason='')
            slot=self.shop_rows.slot(row);saved=self.shop_rows.rows.get(slot)
            if saved is not None:
                cached={**saved[0],'_item_id':item.game_id,'_identity_evidence':'shop-description','_identity_reason':''}
                if listed is not None and listed.game_id!=item.game_id:cached['price']=row.get('price')
                self.shop_rows.rows[slot]=(cached,saved[1])
            proof['item_id']=item.game_id
            self.refresh_identity_candidates()
        self.shop_description={**found,'name':item.name,'_item_id':item.game_id}
        self.shop_description_proof=proof
