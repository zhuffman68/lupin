"""Exact negative discovery cache; it never establishes an item or an offer."""
from dataclasses import dataclass
import hashlib

from PySide6.QtCore import QRect
from PySide6.QtGui import QImage


def _digest(image,area):
    patch=image.copy(area).convertToFormat(QImage.Format.Format_RGBA8888)
    return hashlib.blake2b(patch.constBits(),digest_size=16).digest()


@dataclass(frozen=True)
class InventoryAbsence:
    area: QRect
    pointer: tuple
    size: tuple
    pixels: bytes

    @classmethod
    def capture(cls,value,image,pointer):
        if (not isinstance(value,dict) or value.get('absent') is not True
                or not isinstance(pointer,(tuple,list)) or len(pointer)!=2
                or any(type(n) is not int for n in pointer) or image.isNull()):return None
        parts=value.get('area')
        if not isinstance(parts,dict):return None
        coords=[parts.get(k) for k in ('x','y','width','height')]
        if any(type(n) is not int or abs(n)>32768 for n in coords):return None
        area=QRect(*coords)
        if area.isEmpty() or area.width()*area.height()>1_048_576 or not image.rect().contains(area):return None
        return cls(area,tuple(pointer),(image.width(),image.height()),_digest(image,area))

    def matches(self,image,pointer):
        return (pointer is not None and tuple(pointer)==self.pointer
                and (image.width(),image.height())==self.size and image.rect().contains(self.area)
                and _digest(image,self.area)==self.pixels)
