"""Accepted shop observations and native-description transitions, without widgets."""
from collections import OrderedDict
from dataclasses import dataclass
import hashlib

from PySide6.QtCore import QPoint,QRect,Qt
from PySide6.QtGui import QImage,QPainter,QRegion

from .item_identity import observed_item,resolve_shop_item,shop_icon_rect
from .shop_rows import ShopRows
from .shop_source import capture_proof,proof_state
from .tooltip_geometry import still_present
from .tooltip_names import TooltipNames,name_key


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


class PriceObservations:
    """Own current rows, page retention, source proofs and shop-description focus.

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
        self.shop_tooltip_rect=None
        self.shop_description=None
        self.shop_description_proof=None

    def item_for(self,row):return observed_item(self.catalog,row)

    def shop_identity(self,row):
        item=self.item_for(row)
        return item.game_id if item else None

    @staticmethod
    def fingerprint(image,rect):
        patch=image.copy(rect)
        return hashlib.blake2b(patch.constBits(),digest_size=8).digest()

    def identify_shop_row(self,native,image,*,pointer=None,exclude=()):
        row={key:value for key,value in native.items() if key!='_item_id' and not key.startswith('_identity_')}
        candidates=tuple(self.catalog.candidates(row.get('name'),row.get('tier'))) if self.catalog else ()
        icon=shop_icon_rect(row);cache_key=None
        if (1<len(candidates)<=8 and icon is not None and image.rect().contains(icon)
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
        try:
            box=QRect(*(row['area'][key] for key in ('x','y','width','height')))
            if icon is not None:box=box.united(icon)
            if image.rect().contains(box) and not box.isEmpty():
                row['_identity_source']=capture_proof(image,box,pointer=pointer,exclude=exclude,
                    scale=max(.25,min(4,row['area']['width']/162)))
                if row['_identity_source'] is not None:row['_identity_epoch']=self.browsing.epoch
        except (KeyError,TypeError,ValueError):pass
        return row

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
        return bool(self.shop_rows.guards and (
            all(self.shop_rows.guard_matches(image,rect,proof,exclude) for rect,proof in self.shop_rows.guards)
            or panel is not None and self.shop_rows.tooltip_guards_match(image,panel,exclude)))

    def restore_visible(self,image,rows,*,pointer=None,exclude=()):
        eligible=[]
        for index,row in enumerate(rows):
            saved=self.shop_rows.rows.get(self.shop_rows.slot(row))
            if saved and proof_state(saved[0].get('_identity_source'),image,pointer=pointer,exclude=exclude)=='same':eligible.append(index)
        restored=iter(self.shop_rows.restore_visible(image,[rows[index] for index in eligible]))
        indices=set(eligible)
        return [next(restored) if index in indices else row for index,row in enumerate(rows)]

    def retire_source(self):
        self.rows=[];self.shop_open=False;self.identity_candidates=()
        self.shop_rows.retire_context()
        self.clear_description()

    def viewport_changed(self):
        self.shop_rows.invalidate_viewport()
        self.rows=[];self.identity_candidates=()
        self.clear_description()

    def observe_shop(self,shop,image,latest,*,pointer=None,read_point=None,panel=None,exclude=(),source_exclude=()):
        previous=self.rows;viewport_changed=False
        if isinstance(shop,dict):
            raw=[self.identify_shop_row(row,image,pointer=read_point,exclude=source_exclude)
                 for row in (shop.get('rows') or [])[:self.shop_rows.ROW_LIMIT]]
            states=[proof_state(row.get('_identity_source'),latest,pointer=pointer,exclude=source_exclude)
                    if not row.get('covered') and row.get('name') else 'occluded' for row in raw]
            if 'changed' in states:
                self.retire_source()
                return ShopRead(shop,changed=True,retry=True)
            raw=[row if state=='same' or row.get('covered') else
                 {'area':row['area'],'name':None,'price':None,'covered':True} for row,state in zip(raw,states)]
            shop={**shop,'rows':raw}
            if self.browsing.observe_rows(raw,image,area=shop.get('area') or self.shop_rows.area,
                    tooltip=panel,exclude=exclude,latest=latest):
                self.viewport_changed();viewport_changed=True
            for row in raw:
                if row.get('_identity_source') is not None:row['_identity_epoch']=self.browsing.epoch
        rows=self.shop_rows.observe(shop,image,tooltip=panel,exclude=exclude)
        if panel is None:rows=self.restore_visible(latest,rows,pointer=pointer,exclude=source_exclude)
        self.shop_open=self.shop_rows.active
        if not self.shop_open and self.browsing.area is not None:self.browsing.reset()
        self.rows=rows;self.refresh_identity_candidates()
        return ShopRead(shop,changed=rows!=previous,viewport_changed=viewport_changed)

    def validate_frame(self,image,*,pointer=None,shop_context=None,exclude=(),source_exclusions=None):
        changed=panel_changed=False
        if self.shop_tooltip_rect is not None and not still_present(image,self.shop_tooltip_rect,exclude):
            self.shop_tooltip_rect=None;changed=panel_changed=True
            self.rows=[{**row,'covered':False} for row in self.rows]
            hidden=source_exclusions(None) if source_exclusions else exclude
            self.rows=self.restore_visible(image,self.rows,pointer=pointer,exclude=hidden)
        hidden=source_exclusions(self.shop_tooltip_rect) if source_exclusions else exclude
        matches=self.container_matches(image,self.shop_tooltip_rect,exclude)
        if (self.rows and not matches) or (matches and any(row.get('_identity_source') is not None
                and proof_state(row['_identity_source'],image,pointer=pointer,exclude=hidden)=='changed' for row in self.rows)):
            self.retire_source()
            return ShopFrame(changed=True,panel_changed=panel_changed,retired=True)
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
        if listed and listed.game_id!=item.game_id:self.clear_description();return
        price=dict(row['price']) if listed and row.get('price') else None
        proof=dict(found=found,name=name,pixels=image.copy(name),exclude=tuple(exclude),source=source,pointer=pointer,
            page=self.shop_rows.page_revision,item_id=listed.game_id if listed else None)
        if not still_present(latest,self.shop_tooltip_rect,exclude) or not (
                self.description_title_matches(latest,proof,exclude) or self.description_source_matches(latest,proof,exclude)):
            self.clear_description();return
        self.shop_description={**found,'name':item.name,'price':price,'_shop_description':True,'_item_id':item.game_id}
        self.shop_description_proof=proof
