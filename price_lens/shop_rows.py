"""Stable shop slots and conservative retention across native tooltip occlusion."""
from copy import deepcopy
import time
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage,QRegion
from .domain import glyph_key,item_words,unclipped_name
from .shop_source import native_occlusion


class ShopRows:
    ROW_LIMIT=24

    def __init__(self,identity=None):self.resolve_identity=identity;self.reset()

    def reset(self):
        self.page_revision=getattr(self,'page_revision',-1)+1
        self.area=None;self.guards=[];self.rows={};self.row_pixels={};self.active=False;self.last_verified=0
        self._page_proven=False

    def invalidate_viewport(self):
        """Retire prior-page offers immediately, retaining only shop geometry."""
        self.page_revision+=1
        # Scrolling changes listing authority, not the fixed table rims. Keep
        # their independent container proof so a partly covered new page can
        # still be scanned at full size without borrowing any previous item.
        self.rows={};self.row_pixels={}
        self._page_proven=False
        self.last_verified=0

    def retire_context(self):
        """Keep bounded recovery data without authorizing a visible offer."""
        self.active=False;self._page_proven=False

    @staticmethod
    def slot(row):
        a=row.get('area') or {}
        return tuple(a.get(k) for k in ('x','y','width','height'))

    @staticmethod
    def visible_identity(row):
        return (glyph_key(item_words(unclipped_name(row.get('name') or ''))).rstrip(': '),row.get('tier'))

    def identity(self,row):
        if self.resolve_identity:
            resolved=self.resolve_identity(row)
            if resolved is not None:return resolved
        return self.visible_identity(row)

    def identities_compatible(self,previous,current):
        """Uncertainty is not a new identity; two proven different IDs are."""
        if self.resolve_identity:
            before=self.resolve_identity(previous);after=self.resolve_identity(current)
            if before is not None and after is not None:return before==after
        return self.visible_identity(previous)==self.visible_identity(current)

    def reference_copy(self,saved,current):
        """Never lend an old icon identity to a currently visible weak row."""
        row=deepcopy(saved)
        if current.get('name') and self.resolve_identity and self.resolve_identity(current) is None:
            for key in tuple(row):
                if key=='_item_id' or key.startswith('_identity_'):row.pop(key,None)
            row['name']=current['name']
            if 'tier' in current:row['tier']=current['tier']
            else:row.pop('tier',None)
            for key,value in current.items():
                if key.startswith('_identity_') and key!='_identity_evidence':row[key]=deepcopy(value)
        return row

    def relative_slot(self,row):
        """A list-local slot survives shop dragging and OCR order changes."""
        x,y,w,h=self.slot(row)
        if self.area is None or any(value is None for value in (x,y,w,h)):return None
        return (x-self.area['x'],y-self.area['y'],w,h)

    def presentation_for(self,row,now=None):
        """Retain the last seen amount for this verified page, not a new offer."""
        if row.get('shop_page',self.page_revision)!=self.page_revision:return None
        slot=self.slot(row)
        if self.resolve_identity and self.resolve_identity(row) is None:return None
        if row.get('price'):
            return deepcopy(row['price'])
        if not self.active or not self._page_proven or row.get('shop_slot')!=self.relative_slot(row):return None
        saved=self.rows.get(slot)
        if saved is None or not self.identities_compatible(saved[0],row):return None
        now=time.monotonic() if now is None else now
        if now<saved[1]:return None
        return deepcopy(saved[0].get('price') or saved[0].get('_last_seen_price'))

    def decorate(self,row,now):
        row['shop_page']=self.page_revision;row['shop_slot']=self.relative_slot(row)
        presentation=self.presentation_for(row,now)
        row['presentation_held']=bool(presentation and not row.get('price'))
        return row

    @staticmethod
    def guard_matches(image,rect,reference,exclude=()):
        if reference is None or image is None or not image.rect().contains(rect):return False
        previous,old_exclusions=reference
        visible=QRegion(rect)
        for covered in (*old_exclusions,*exclude):
            if rect.intersects(covered):visible=visible.subtracted(QRegion(covered))
        if visible.isEmpty():return False
        current=image.copy(rect).convertToFormat(QImage.Format.Format_RGBA8888)
        return all(current.copy(part.translated(-rect.x(),-rect.y()))==previous.copy(part.translated(-rect.x(),-rect.y())) for part in visible)

    def guards_match(self,image,exclude=()):
        """Require independent exposed guards; masked pixels are unknown."""
        if not self.guards:return False
        verified=False
        for rect,reference in self.guards:
            visible=QRegion(rect)
            for hidden in (*reference[1],*exclude):
                visible=visible.subtracted(QRegion(hidden))
            if sum(part.width()*part.height() for part in visible)<32:continue
            if not self.guard_matches(image,rect,reference,exclude):return False
            verified=True
        return verified

    def tooltip_guards_match(self,image,tooltip,exclude=()):
        """A tooltip excuses only its own pixels, with another visible proof."""
        return tooltip is not None and self.guards_match(image,(*exclude,native_occlusion(tooltip,(self.area or {}).get('width',199)/199)))

    def stable_slots(self,raw):
        for row in raw:
            slot=self.slot(row)
            for previous,_ in self.rows.values():
                old=self.slot(previous)
                if all(a is not None and b is not None and abs(a-b)<=3 for a,b in zip(slot,old)):
                    row['area']=dict(previous['area']);break

    def set_guards(self,area,image,exclude=()):
        x,y,w,h=(area[k] for k in ('x','y','width','height'))
        # The owner portrait above the list animates; the table rim does not.
        # The scroll rail includes a moving/highlighted thumb. Only the fixed
        # top and left table rims establish the container; scrolling has its
        # own thumb/row proofs and must not be confused with hover animation.
        # The outer shadow reaches into the scenery. Sampling it made a
        # character blinking behind a stationary shop repeatedly close/reopen
        # the whole annotation page. Stay within the native inner bevel,
        # including the one-pixel rounding of the reader's table coordinate.
        scale=w/199
        bevel=max(1,round(2*scale))
        # The innermost bevel pixel is alpha-blended with the listing. A
        # sold-out row or selection changes it when the viewport scrolls.
        # Sample the two solid frame strokes immediately outside that pixel.
        rects=[QRect(x,y-6,w,4),QRect(x-max(2,round(3*scale)),y-4,bevel,h+8)]
        self.guards=[(r,(image.copy(r).convertToFormat(QImage.Format.Format_RGBA8888),tuple(QRect(e) for e in exclude)))
                     for r in rects if image is not None and image.rect().contains(r)]
        if len(self.guards)!=len(rects):self.guards=[]

    def observe(self,shop,image,now=None,tooltip=None,exclude=()):
        now=time.monotonic() if now is None else now
        raw=deepcopy((shop or {}).get('rows') or []);area=(shop or {}).get('area')
        # Presentation history is controller-owned, never accepted from a new
        # native read or copied into its current asking-price field.
        for row in raw:row.pop('_last_seen_price',None)
        guard_exclude=tuple(exclude)+((native_occlusion(tooltip,(area or self.area or {}).get('width',199)/199),) if tooltip is not None else ())
        guard_ok=self.guards_match(image,exclude)
        # A recognized native tooltip may cover a guard, but a changed guard
        # elsewhere still invalidates the page. Hidden rows carry a bounded
        # last-seen presentation, independently of current listing proof.
        guard_safe=self.tooltip_guards_match(image,tooltip,exclude)
        self.active=bool(area)
        if not area:
            if self.area and (guard_ok or guard_safe):
                area=dict(self.area);self.active=True
                raw=[{'area':dict(row['area']),'covered':True} for row,_ in self.rows.values()]
            else:
                # Keep an invisible recovery cache briefly; it must not draw labels
                # or block inventory pricing after an unverified shop disappears.
                self._page_proven=False
                if self.area and now-self.last_verified>6:self.reset()
                return []
        contained=bool(self.area and QRect(*(self.area[k] for k in ('x','y','width','height'))).adjusted(-3,-3,3,3).contains(
            QRect(*(area[k] for k in ('x','y','width','height')))))
        close=bool(self.area and abs(area['x']-self.area['x'])<=3 and abs(area['width']-self.area['width'])<=3
                   and (abs(area['y']-self.area['y'])<=3 or contained))
        if close:
            self.stable_slots(raw)
            area=dict(self.area)
        clean=[r for r in raw if not r.get('covered') and r.get('name') and r.get('price')]
        known=clean+[r for r in raw if not r.get('covered') and r.get('name') and r.get('nameOnly')
                     and r.get('_identity_source') is not None and not r.get('price')]
        contradiction=False
        if close:
            for row in clean:
                previous=self.rows.get(self.slot(row))
                if previous and ((previous[0].get('price') is not None and previous[0].get('price')!=row.get('price'))
                        or not self.identities_compatible(previous[0],row)):
                    contradiction=True;break
        same=close and guard_ok and not contradiction
        # A tooltip may hide a guard. Retain recovery data without inheriting an
        # unverified covered listing; restore it when the same page is visible.
        all_verified=bool(clean and len(clean)==len(raw) and close and not contradiction)
        if not close or contradiction:
            # Compare proven listing identities/prices, never tooltip pixels or
            # absolute coordinates: moving the same shop is not a new page.
            previous=[row for row,_ in sorted(self.rows.values(),key=lambda saved:self.slot(saved[0])[1])]
            current=sorted(clean,key=lambda row:self.slot(row)[1])
            same_listings=len(previous)==len(current) and all(self.identities_compatible(before,after)
                and before.get('price')==after.get('price') for before,after in zip(previous,current))
            if contradiction or (previous and (not clean or len(clean)!=len(raw) or not same_listings)):
                self.page_revision+=1
            self.rows={};self.row_pixels={};self.area=dict(area);self.set_guards(area,image,guard_exclude)
        elif all_verified:
            if not self.guards or not (guard_ok or guard_safe) and tooltip is None:
                self.set_guards(area,image,guard_exclude)
            same=True
        for row in known:
            slot=self.slot(row)
            cached=deepcopy(row);previous=self.rows.get(slot)
            if row.get('nameOnly') and not row.get('price') and previous:
                before=self.resolve_identity(previous[0]) if self.resolve_identity else self.visible_identity(previous[0])
                after=self.resolve_identity(row) if self.resolve_identity else self.visible_identity(row)
                if before is not None and before==after:
                    price=previous[0].get('price') or previous[0].get('_last_seen_price')
                    if price:cached['_last_seen_price']=deepcopy(price)
            self.rows[slot]=(cached,now)
            rect=QRect(*slot)
            if image is not None and image.rect().contains(rect):
                self.row_pixels[slot]=image.copy(rect).convertToFormat(QImage.Format.Format_RGBA8888)
        if len(self.rows)>self.ROW_LIMIT:
            for slot in sorted(self.rows,key=lambda key:self.rows[key][1])[:-self.ROW_LIMIT]:
                self.rows.pop(slot,None);self.row_pixels.pop(slot,None)
        if clean or same:self.last_verified=now
        references=bool(close and not contradiction and (guard_ok or guard_safe))
        self._page_proven=bool(references or (clean and len(clean)==len(raw)))
        if references:
            present={self.slot(row) for row in raw}
            for saved,_ in self.rows.values():
                if self.slot(saved) not in present and tooltip and QRect(*self.slot(saved)).intersects(tooltip):
                    raw.append({'area':dict(saved['area']),'covered':True})
            raw.sort(key=lambda row:row['area']['y'])
        result=[]
        for row in raw:
            saved=self.rows.get(self.slot(row))
            if references and (row.get('covered') or not row.get('name')) and saved:
                covered=bool(row.get('covered'))
                row=self.reference_copy(saved[0],row);row.update(retained=True,covered=covered,reference_only=True,listing_old=True,price=None)
            elif row.get('covered'):
                # Identity remains unknown when the page cannot be verified.
                row['price']=None
            result.append(self.decorate(row,now))
        return result

    def restore_visible(self,image,rows,now=None,exclude=()):
        """Restore a listing only when its exact, previously read pixels return."""
        if not self.guards_match(image,exclude):return rows
        now=time.monotonic() if now is None else now
        result=[]
        for row in rows:
            slot=self.slot(row);pixels=self.row_pixels.get(slot);saved=self.rows.get(slot)
            if (saved and pixels is not None and (row.get('covered') or row.get('listing_old'))
                    and image.rect().contains(QRect(*slot))
                    and image.copy(QRect(*slot)).convertToFormat(QImage.Format.Format_RGBA8888)==pixels):
                row=self.reference_copy(saved[0],row);self.rows[slot]=(deepcopy(row),now)
                row=self.decorate(row,now)
            result.append(row)
        return result
