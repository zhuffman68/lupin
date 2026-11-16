"""Paint only visible shop sightings; a 100-row response creates no row widgets."""
from bisect import bisect_right
from dataclasses import dataclass,field
import re
from PySide6.QtCore import QPoint,QRect,QRectF,Qt,QVariantAnimation,QEasingCurve
from PySide6.QtGui import QColor,QFont,QFontMetrics,QPainter
from PySide6.QtWidgets import QWidget,QSizePolicy

from .domain import age_text
from .gui_currency import paint_icon
from .ui_components import mesos
from .motion import enabled
from .number_motion import NumberRoll
from .slide_surface import invalidate_surface


@dataclass
class ListingRow:
    listing:object
    per_set:bool=False
    quantity:str=field(init=False)
    age:str=''
    roll:NumberRoll=field(default_factory=NumberRoll,repr=False)

    def __post_init__(self):
        self.quantity=(f'For {self.listing.quantity:,} {"sets" if self.per_set else "items"}'
                       if self.listing.quantity!=1 else 'For 1 set' if self.per_set else 'For 1 item')
        if self.listing.stock is not None:self.quantity+=f' · stock {self.listing.stock:,}'

    def formatted_age(self,now):return f'{self.quantity} · seen {age_text(max(0,now-self.listing.last_seen))} ago'

    def update_age(self,now):
        self.age=self.formatted_age(now)
        self.roll.set_text(self.age,False)


class ListingRows(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.rows=[];self.boxes=[];self.starts=[];self.alpha=1.0;self.lift=0.0;self.last_painted_count=0
        self.revealing=False;self.pending_reveal=False
        self.row_motion={}
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed);self.setMouseTracking(True)
        self.animation=QVariantAnimation(self);self.animation.setDuration(130)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic);self.animation.valueChanged.connect(self.advance)
        self.animation.finished.connect(self.finish_reveal)
        self.rolling=set();self.fading=set();self.age_alpha=1.0
        self.digits=QVariantAnimation(self);self.digits.setDuration(160)
        self.digits.setEasingCurve(QEasingCurve.Type.OutCubic);self.digits.valueChanged.connect(self.advance_ages)
        self.fade=QVariantAnimation(self);self.fade.setDuration(110)
        self.fade.setEasingCurve(QEasingCurve.Type.OutCubic);self.fade.valueChanged.connect(self.fade_ages)
        self.setFixedHeight(0)

    def fonts(self):
        regular=QFont(self.font());regular.setPixelSize(10)
        bold=QFont(regular);bold.setWeight(QFont.Weight.DemiBold)
        price=QFont(bold);price.setPixelSize(12)
        return regular,bold,price

    def set_rows(self,rows):
        def keys(values):
            counts={};result=[]
            for row in values:
                listing=row.listing
                offer=(listing.seller,listing.location,getattr(listing,'channel',None),
                       getattr(listing,'room',None),listing.price,listing.quantity,row.per_set)
                occurrence=counts.get(offer,0);counts[offer]=occurrence+1
                result.append((offer,occurrence))
            return result
        old_keys,new_keys=keys(self.rows),keys(rows)
        unchanged=(old_keys==new_keys and all(a.listing==b.listing for a,b in zip(self.rows,rows)))
        if unchanged:
            rows[:]=self.rows;self.rows=rows
            return
        before={key:(row,self.starts[index]+self.row_visual(index)[0],self.row_visual(index)[1])
                for index,(key,row) in enumerate(zip(old_keys,self.rows))}
        entering=bool(rows) and not self.rows
        self.animation.stop();self.finish_ages();self.finish_reveal()
        for index,key in enumerate(new_keys):
            previous=before.get(key)
            if previous is not None and previous[0].listing==rows[index].listing:rows[index]=previous[0]
        self.rows=rows;self.reflow()
        if enabled(self) and rows:
            if entering:self.start_reveal()
            else:
                for index,key in enumerate(new_keys):
                    previous=before.get(key)
                    if previous is None:motion=(8.,0.,220)
                    else:
                        old,top,alpha=previous
                        dy=top-self.starts[index]
                        changed=old.listing!=rows[index].listing
                        if changed and alpha==1:alpha=.55
                        if abs(dy)<.01 and alpha==1:continue
                        motion=(dy,alpha,130 if changed else 220)
                    self.row_motion[index]=motion
                if self.row_motion:
                    self.animation.setDuration(220 if any(dy or duration==220 for dy,_,duration in self.row_motion.values()) else 130)
                    self.animation.setStartValue(0.);self.animation.setEndValue(1.);self.advance(0.)
                    self.animation.start()
        else:self.pending_reveal=entering and not self.isVisible()

    def start_reveal(self):
        self.pending_reveal=False;self.revealing=True
        self.animation.setDuration(220)
        self.advance(0.0)
        self.animation.setStartValue(self.alpha);self.animation.setEndValue(1.0);self.animation.start()

    def finish_reveal(self):
        self.animation.stop();self.revealing=False;self.pending_reveal=False
        self.row_motion.clear()
        self.alpha=1.0;self.lift=0.0;self.redraw()

    def row_visual(self,index):
        motion=self.row_motion.get(index)
        if motion is None:return (self.lift,self.alpha) if self.revealing else (0.,1.)
        dy,alpha,duration=motion
        elapsed=min(1.,self.animation.currentTime()/duration)
        fade=1-(1-elapsed)**3
        return dy*(1-self.alpha),alpha+(1-alpha)*fade

    def refresh_ages(self,now):
        updates=[(index,row.age) for index,row in enumerate(self.rows) if row.age!=row.formatted_age(now)]
        if not updates:return
        self.finish_ages();visible=self.rect();parent=self.parentWidget();active=enabled(self)
        while parent is not None:
            visible=visible.intersected(QRect(self.mapFrom(parent,QPoint()),parent.size()));parent=parent.parentWidget()
        shape=lambda value:re.sub(r'\d+(?:[,.]\d+)*','#',value)
        metrics=QFontMetrics(self.fonts()[0])
        for index,before in updates:
            row=self.rows[index];row.update_age(now)
            if not active or not self.boxes[index][0].intersects(visible):continue
            if shape(before)==shape(row.age) and metrics.horizontalAdvance(row.age)<=self.width()-14:
                row.roll.set_text(before,False);row.roll.set_text(row.age,True);self.rolling.add(index)
            else:self.fading.add(index)
        self.reflow();self.redraw()
        if self.rolling:self.digits.setStartValue(0.0);self.digits.setEndValue(1.0);self.digits.start()
        if self.fading:self.fade.setStartValue(.55);self.fade.setEndValue(1.0);self.fade.start()

    def advance_ages(self,value):
        for index in self.rolling:self.rows[index].roll.progress=float(value)
        self.redraw()

    def fade_ages(self,value):self.age_alpha=float(value);self.redraw()

    def finish_ages(self):
        self.digits.stop();self.fade.stop()
        for index in self.rolling:self.rows[index].roll.finish()
        self.rolling.clear();self.fading.clear();self.age_alpha=1.0

    def reflow(self):
        regular,_,price=self.fonts();metrics=QFontMetrics(regular);top=0;self.boxes=[];self.starts=[]
        width=max(80,self.width()-14);head=QFontMetrics(price).height()
        flags=int(Qt.TextFlag.TextWordWrap)
        for row in self.rows:
            place=max(metrics.height(),metrics.boundingRect(QRect(0,0,width,1000),flags,row.listing.place).height())
            age=max(metrics.height(),metrics.boundingRect(QRect(0,0,width,1000),flags,row.age).height())
            height=14+head+place+age+6
            self.starts.append(top);self.boxes.append((QRect(0,top,self.width(),height),head,place,age));top+=height+5
        self.setFixedHeight(max(0,top-5));self.redraw()

    def advance(self,value):
        if not enabled(self):self.finish_reveal();return
        self.alpha=float(value);self.lift=8*(1-self.alpha) if self.revealing else 0.0;self.redraw()

    def redraw(self):invalidate_surface(self);self.update()

    def paintEvent(self,event):
        if self.alpha<1 and not enabled(self):self.finish_reveal()
        painter=QPainter(self)
        regular,bold,price=self.fonts();seller_metrics=QFontMetrics(bold);price_metrics=QFontMetrics(price);self.last_painted_count=0
        top=event.rect().top()-self.lift;bottom=event.rect().bottom()-self.lift
        first=max(0,bisect_right(self.starts,top)-1);visible=set(self.row_motion)
        for index in range(first,len(self.rows)):
            if self.boxes[index][0].top()>bottom:break
            visible.add(index)
        for index in sorted(visible):
            box,head,place_h,age_h=self.boxes[index]
            lift,alpha=self.row_visual(index);drawn=QRectF(box).translated(0,lift)
            if drawn.top()>event.rect().bottom() or drawn.bottom()<event.rect().top() or alpha<=0:continue
            painter.save();painter.setOpacity(alpha);painter.translate(0.,lift)
            self.last_painted_count+=1;row=self.rows[index]
            painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#263345'))
            painter.drawRoundedRect(QRectF(box),6,6)
            amount=mesos(row.listing.price);price_width=price_metrics.horizontalAdvance(amount)+21
            left=box.adjusted(7,7,-7,-7);painter.setFont(bold);painter.setPen(QColor('#e4eaf3'))
            seller=seller_metrics.elidedText(row.listing.seller,Qt.TextElideMode.ElideRight,max(20,left.width()-price_width-7))
            painter.drawText(QRect(left.x(),left.y(),max(20,left.width()-price_width-7),head),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,seller)
            painter.setFont(price);painter.setPen(QColor('#efd09a'))
            painter.drawText(QRect(left.right()-price_width,left.y(),price_width-19,head),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,amount)
            paint_icon(painter,QRectF(left.right()-15,left.y()+(head-14)/2,16,14))
            painter.setFont(regular);painter.setPen(QColor('#e4eaf3'))
            y=left.y()+head+3
            painter.drawText(QRect(left.x(),y,left.width(),place_h),int(Qt.TextFlag.TextWordWrap),row.listing.place)
            painter.setPen(QColor('#a7b7cd'))
            age_box=QRect(left.x(),y+place_h+3,left.width(),age_h)
            if index in self.rolling:row.roll.paint(painter,age_box,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
            else:
                painter.save()
                if index in self.fading:painter.setOpacity(alpha*self.age_alpha)
                painter.drawText(age_box,int(Qt.TextFlag.TextWordWrap),row.age);painter.restore()
            painter.restore()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if event.oldSize().width()!=event.size().width():self.reflow()

    def mouseMoveEvent(self,event):
        location=''
        for index in reversed(range(len(self.rows))):
            lift,alpha=self.row_visual(index)
            if alpha>0 and QRectF(self.boxes[index][0]).translated(0,lift).contains(event.position()):
                location=self.rows[index].listing.location;break
        self.setToolTip(location)
        super().mouseMoveEvent(event)

    def showEvent(self,event):
        super().showEvent(event)
        if self.pending_reveal:
            if enabled(self):self.start_reveal()
            else:self.finish_reveal()

    def hideEvent(self,event):
        self.finish_reveal();self.finish_ages();super().hideEvent(event)
