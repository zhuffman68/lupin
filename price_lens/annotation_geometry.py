"""Annotation rectangles and protected-pixel placement, without drawing widgets."""
import math
from PySide6.QtCore import QRect,QPoint


def place_item_away_from_proof(row,requested,bounds,*,canvas):
    """Keep our item card off native identity pixels at every paint step.

    Candidate edges are projections of the requested pointer-following box
    and the protected rectangles.  Unblocked axes still follow the pointer;
    a small side preference prevents jitter between equally close spaces.
    """
    values=row.get('avoid_regions')
    if not isinstance(values,(tuple,list)) or len(values)>32:return None
    bounds=bounds.intersected(canvas).adjusted(2,2,-2,-2)
    width,height=requested.width(),requested.height()
    if bounds.width()<width or bounds.height()<height:return None
    protected=[]
    for value in values:
        if (not isinstance(value,(tuple,list)) or len(value)!=4
                or any(type(part) is not int for part in value) or value[2]<=0 or value[3]<=0):return None
        rect=QRect(*value).adjusted(-4,-4,4,4)
        if rect.intersects(bounds):protected.append(rect)
    left,right=bounds.left(),bounds.right()-width+1
    top,bottom=bounds.top(),bounds.bottom()-height+1
    clamp_x=lambda x:max(left,min(x,right))
    clamp_y=lambda y:max(top,min(y,bottom))
    target=QPoint(clamp_x(requested.x()),clamp_y(requested.y()))
    xs=[(('target',),target.x()),(('low',),left),(('high',),right)]
    ys=[(('target',),target.y()),(('low',),top),(('high',),bottom)]
    for index,rect in enumerate(protected):
        xs.extend(((('before',index),clamp_x(rect.left()-width)),(('after',index),clamp_x(rect.right()+1))))
        ys.extend(((('before',index),clamp_y(rect.top()-height)),(('after',index),clamp_y(rect.bottom()+1))))
    choices={}
    for xkey,x in xs:
        for ykey,y in ys:
            candidate=QRect(x,y,width,height)
            if any(candidate.intersects(rect) for rect in protected):continue
            distance=math.hypot(x-target.x(),y-target.y())
            choices[(xkey,ykey)]=(distance,candidate)
    if not choices:return None
    key=min(choices,key=lambda key:(choices[key][0],choices[key][1].y(),choices[key][1].x()))
    signature=(bounds.getRect(),width,height,tuple(rect.getRect() for rect in protected))
    previous=row.get('_avoid_placement')
    if previous and previous[0]==signature and previous[1] in choices:
        if choices[previous[1]][0]<=choices[key][0]+8:key=previous[1]
    row['_avoid_placement']=(signature,key)
    return choices[key][1]


def label_rectangle(row,point,canvas,window_origin):
    if row.get("_retired_rect") is not None:
        return row["_retired_rect"]
    x, y = int(row["x"]), int(row["y"])
    if row.get("follow_pointer") is not None:
        origin = row["follow_pointer"]
        region = row.get("pointer_region")
        if ((region and not QRect(*region).contains(point)) or
                max(abs(point.x() - origin[0]), abs(point.y() - origin[1])) > 64):
            return None
        dx, dy = row["_cursor_offset"]
        x, y = point.x() - window_origin.x() + dx, point.y() - window_origin.y() + dy
    elif row.get("_draw_pos") is not None:
        position = row["_draw_pos"]
        x, y = round(position.x()), round(position.y())
    width = row["_width"]
    height = 36+17*len(row.get('extra','').splitlines())
    if row.get('kind')=='notification':
        height=row.get('_notice_height',48)
        notice_box=row.get('notification_box')
        if notice_box:
            requested=QRect(*notice_box);bounds=QRect(*row['bounds']).intersected(canvas).adjusted(2,2,-2,-2)
            width=min(width,max(1,bounds.width()));height=min(height,max(1,bounds.height()))
            return QRect(max(bounds.left(),min(requested.right()-width+1,bounds.right()-width+1)),
                max(bounds.top(),min(requested.bottom()-height+1,bounds.bottom()-height+1)),width,height)
    if row.get('kind')=='tracking':height=row['_height']
    if row.get("kind")=="translation":
        height=row["_height"]
        bounds=QRect(*row.get("bounds",[0,0,canvas.width(),canvas.height()])).intersected(canvas)
        width=min(width,max(1,bounds.width()-4));height=min(height,max(1,bounds.height()-4))
        return QRect(max(bounds.x()+2,min(x,bounds.right()-width-2)),
                     max(bounds.y()+2,min(y,bounds.bottom()-height-2)),width,height)
    if row.get("anchor") in ('bottom_left','bottom_right') and row.get("bounds"):
        bounds=QRect(*row["bounds"])
        width=min(width,max(1,bounds.width()-8))
        height=min(height,max(1,bounds.height()-8))
        left=bounds.left()+4+int(row.get('left_offset',0)) if row['anchor']=='bottom_left' else bounds.right()-width-3
        top=max(bounds.top()+4,bounds.bottom()-height-3-int(row.get('bottom_offset',0)))
        return QRect(left,top,width,height)
    if row.get('kind')=='item' and row.get('bounds'):
        bounds=QRect(*row['bounds']).intersected(canvas)
        width=min(width,max(1,bounds.width()-4))
        requested=QRect(max(bounds.left()+2,min(x,bounds.right()-width-2)),
                        max(bounds.top()+2,min(y-5,bounds.bottom()-height-2)),width,height)
        return place_item_away_from_proof(row,requested,bounds,canvas=canvas) if row.get('avoid_regions') else requested
    x = min(max(2, x), max(2, canvas.width() - width - 2))
    y = min(max(7, y), max(7, canvas.height() - 33))
    requested=QRect(x,y-5,width,height)
    return place_item_away_from_proof(row,requested,canvas,canvas=canvas) if row.get('kind')=='item' and row.get('avoid_regions') else requested
