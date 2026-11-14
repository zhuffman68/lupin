"""Digit-place transitions shared by widgets and the painted game overlay."""
import re
from PySide6.QtCore import QRectF, Qt


def columns(text):
    result=[];cursor=0
    for index,match in enumerate(re.finditer(r'\d[\d,]*(?:\.\d+)?',text)):
        result.extend((None,c) for c in text[cursor:match.start()])
        integer,_,fraction=match[0].partition('.')
        remaining=sum(c.isdigit() for c in integer)
        for char in integer:
            if char.isdigit():
                remaining-=1;result.append(((index,'integer',remaining),char))
            else:result.append((None,char))
        if fraction:
            result.append((None,'.'))
            result.extend(((index,'fraction',n),c) for n,c in enumerate(fraction))
        cursor=match.end()
    result.extend((None,c) for c in text[cursor:])
    return result


class NumberRoll:
    """An interrupted roll starts at the visible glyph positions, not its old target."""
    def __init__(self,text=''):
        self.text=text;self.columns=columns(text);self.before={};self.progress=1.0
        self.numeric=any(key is not None for key,_ in self.columns)
        self._layout_key=None;self._metrics=None;self._layout=None

    def layers(self,key,char):
        old=self.before.get(key,[])
        if self.progress>=.999 or old==[(char,0.0,1.0)]:return [(char,0.0,1.0)]
        p=self.progress
        return [(c,y-p,alpha*(1-p)) for c,y,alpha in old if alpha*(1-p)>.001]+[(char,1-p,p)]

    def set_text(self,text,animate=True):
        if text==self.text:return False
        self.before={key:self.layers(key,char) for key,char in self.columns if key is not None}
        self.text=text;self.columns=columns(text)
        self.numeric=any(key is not None for key,_ in self.columns)
        self.progress=0.0 if animate and any(key is not None for key,_ in self.columns) else 1.0
        return self.progress==0.0

    def finish(self):
        self.progress=1.0;self.before={}

    def layout(self,metrics,icons=False):
        """Keep glyph advances stable through a roll; measure only new content/fonts."""
        key=(self.text,bool(icons))
        if key!=self._layout_key or self._metrics is None or self._metrics!=metrics:
            cell=metrics.horizontalAdvance('0');height=metrics.height();advances={}
            widths=[]
            for digit,char in self.columns:
                if digit is not None:width=cell
                elif char=='\ufffc' and icons:width=max(12,min(18,height-2))+2
                else:
                    if char not in advances:advances[char]=metrics.horizontalAdvance(char)
                    width=advances[char]
                widths.append(width)
            self._layout_key=key;self._metrics=metrics;self._layout=(widths,sum(widths),height)
        return self._layout

    def paint(self,painter,rect,alignment=Qt.AlignmentFlag.AlignLeft,inline_icon=None):
        painter.save()
        widths,width,height=self.layout(painter.fontMetrics(),bool(inline_icon))
        if width>rect.width() and rect.width()>0:
            painter.translate(rect.x(),0);painter.scale(rect.width()/width,1)
            rect=QRectF(0,rect.y(),width,rect.height())
        left=rect.right()-width if alignment&Qt.AlignmentFlag.AlignRight else rect.x()+(rect.width()-width)/2 if alignment&Qt.AlignmentFlag.AlignHCenter else rect.x()
        top=rect.y()+(rect.height()-height)/2
        opacity=painter.opacity()
        painter.setClipRect(rect,Qt.ClipOperation.IntersectClip)
        for (key,char),w in zip(self.columns,widths):
            box=QRectF(left,top,w,height);left+=w
            if char=='\ufffc' and inline_icon:
                inline_icon(painter,box);continue
            if key is None:
                painter.drawText(box,Qt.AlignmentFlag.AlignCenter,char);continue
            painter.save();painter.setClipRect(box,Qt.ClipOperation.IntersectClip)
            for glyph,y,alpha in self.layers(key,char):
                painter.setOpacity(opacity*alpha)
                painter.drawText(box.translated(0,y*height),Qt.AlignmentFlag.AlignCenter,glyph)
            painter.restore()
        painter.restore()
