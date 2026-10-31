"""One immutable snapshot for each request sent to our pixel reader."""
from dataclasses import dataclass
from typing import Literal

from PySide6.QtCore import QRect
from PySide6.QtGui import QImage


RequestMode=Literal['prices','location','tracking-location','experience']


@dataclass(frozen=True)
class SubmittedRequest:
    mode: RequestMode
    frame: QImage
    pointer: tuple[int,int] | None
    sequence: int
    generation: int
    started_at: float
    shop_epoch: int | None = None
    tracking_epoch: int | None = None
    crop: tuple[int,int,int,int] | None = None
    analysis_rect: tuple[int,int,int,int] | None = None
    using_roi: bool = False
    local_roi: bool = False
    locate_game: bool = False
    deadline_at: float | None = None

    def __post_init__(self):
        if self.mode not in ('prices','location','tracking-location','experience'):raise ValueError('Invalid reader request mode')
        # Qt's implicit sharing keeps the captured frame stable if the live
        # QImage is later painted/replaced, without a full-workspace deep copy.
        object.__setattr__(self,'frame',QImage(self.frame))
        if self.pointer is not None:object.__setattr__(self,'pointer',tuple(self.pointer))
        for field in ('crop','analysis_rect'):
            value=getattr(self,field)
            if value is not None:object.__setattr__(self,field,tuple(value))
        if self.deadline_at is None:object.__setattr__(self,'deadline_at',self.started_at+25)

    def source_image(self):
        return self.frame.copy(QRect(*self.crop)) if self.crop is not None else QImage(self.frame)

    def analysis_image(self):
        return self.frame.copy(QRect(*self.analysis_rect)) if self.analysis_rect is not None else self.source_image()

    @property
    def analysis_origin(self):
        rect=self.analysis_rect or self.crop
        return (rect[0],rect[1]) if rect is not None else (0,0)
