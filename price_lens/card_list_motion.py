"""Keep existing listing pixels steady while neighboring cards enter or leave."""
from PySide6.QtCore import QPoint,QRect,Qt
from PySide6.QtGui import QPainter,QPixmap,QRegion
from PySide6.QtWidgets import QWidget

from .card_morph import CardMorph,background


class _Block:
    def __init__(self,pixels,rect):
        self.rect=QRect(rect);self.pixels=QPixmap(pixels)

    def paint(self,painter,position):
        if self.pixels.isNull():return
        painter.save();painter.translate(position-self.rect.topLeft())
        painter.setClipRect(self.rect,Qt.ClipOperation.IntersectClip)
        painter.drawPixmap(0,0,self.pixels);painter.restore()


class ListingFrame(QWidget):
    """One existing CardArea clock; snapshots never supply item/offer authority."""
    def __init__(self,before,after,old_items,new_items,parent,old_card=None,new_card=None):
        super().__init__(parent)
        self.progress=0.;self.colour=background(parent)
        old_hover = {key for key in old_items if key[0]}
        new_hover = {key for key in new_items if key[0]}
        moved_hover = old_card is not None and new_card is not None and old_card.rect != new_card.rect
        # Morph the described item by itself. The shop rows stay in their own
        # layer even when the inventory card changes the entire list's offset.
        self.morph = None
        if (old_hover != new_hover or moved_hover) and (old_card or new_card):
            self.morph = CardMorph(QPixmap(), QPixmap(), old_card, new_card, self)
        self.old={key:_Block(before,rect) for key,rect in old_items.items()}
        self.new={key:_Block(after,rect) for key,rect in new_items.items()}
        self.before=QPixmap(before);self.after=QPixmap(after)
        self.before_body=self.body(before,old_items);self.after_body=self.body(after,new_items)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

    @staticmethod
    def body(pixels,items):
        dpr=pixels.devicePixelRatioF()
        region=QRegion(0,0,round(pixels.width()/dpr),round(pixels.height()/dpr))
        for rect in items.values():region-=QRegion(rect)
        return region

    def item_rect(self,key):
        old=self.old.get(key);new=self.new.get(key);p=self.progress
        if old and new:
            a,b=old.rect.topLeft(),new.rect.topLeft()
            return QRect(QPoint(round(a.x()+(b.x()-a.x())*p),round(a.y()+(b.y()-a.y())*p)),new.rect.size())
        block=new or old
        return block.rect.translated(0,round(5*(1-p) if new else -5*p))

    def current_items(self):
        return {key:self.item_rect(key) for key in (*self.new,*(key for key in self.old if key not in self.new))}

    def replace_after(self,pixels,card):
        items=self.parentWidget().frame_items()
        self.new={key:_Block(pixels,rect) for key,rect in items.items()}
        self.after=QPixmap(pixels);self.after_body=self.body(pixels,items)
        if self.morph and card is not None:
            self.morph.new=card

    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),self.colour);p=self.progress
        # QPixmap copies are shared handles. Clip the two existing snapshots;
        # never allocate a separate image or timer for each listing.
        for pixels,region,opacity in ((self.before,self.before_body,1.),(self.after,self.after_body,p)):
            painter.save();painter.setClipRegion(region,Qt.ClipOperation.IntersectClip)
            painter.setOpacity(opacity);painter.drawPixmap(0,0,pixels);painter.restore()
        # Departing/new rows stay underneath retained rows while a gap opens.
        # Matched content crossfades at one shared position, without shifting
        # two copies of unchanged text in opposite directions.
        if self.morph:
            self.morph.paint_card(painter,p)
        for key,old in self.old.items():
            if key not in self.new and not (key[0] and self.morph and self.morph.old):
                painter.setOpacity(1-p);old.paint(painter,self.item_rect(key).topLeft())
        for key,new in self.new.items():
            if key not in self.old and not (key[0] and self.morph and self.morph.new):
                painter.setOpacity(p);new.paint(painter,self.item_rect(key).topLeft())
        for key,new in self.new.items():
            old=self.old.get(key)
            if old and not (key[0] and self.morph):
                position=self.item_rect(key).topLeft()
                painter.setOpacity(1.);old.paint(painter,position)
                painter.setOpacity(p);new.paint(painter,position)


def incremental(old,new):
    """Match retained cards with stable sizes and ordering."""
    if old is None or new is None:return False
    common=old.keys()&new.keys()
    if not common:return False
    # A returning inventory card may still be at an intermediate size.
    # Stable shop rows can continue their motion while that card retargets.
    common={key for key in common if not key[0]} or common
    if any(old[key].size()!=new[key].size() for key in common):return False
    ordered=lambda items:[key for key in sorted(items,key=lambda key:items[key].top()) if key in common]
    return ordered(old)==ordered(new)
