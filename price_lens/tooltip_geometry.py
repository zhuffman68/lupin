"""Find the native item's description panel around a recognized name line.

Only captured colours are inspected. A known tooltip anchor is required; this
never searches desktop windows or treats arbitrary purple scenery as a tooltip.
"""
from PySide6.QtCore import QRect
from PySide6.QtGui import QRegion
from PySide6.QtGui import QImage
import numpy as np
import time
from math import ceil,floor


def _visible_region(rect,exclude):
    visible=QRegion(rect)
    for covered in exclude:
        if rect.intersects(covered):visible=visible.subtracted(QRegion(covered.adjusted(-1,-1,1,1)))
    return visible


def _description_body(image,rect,exclude=()):
    """A bright shop/chat pane is not a dark native item description.

    Never use our own dark price cards as evidence for a description behind
    them: that creates a dim/bright feedback loop on otherwise light shops.
    """
    if rect is None or not image.rect().contains(rect):return False
    interior=rect.adjusted(6,6,-6,-6)
    if interior.isEmpty():return False
    patch=image.copy(interior).convertToFormat(QImage.Format.Format_RGBA8888)
    pixels=np.frombuffer(patch.constBits(),dtype=np.uint8).reshape(patch.height(),patch.bytesPerLine())
    rgb=pixels[:,:patch.width()*4].reshape(patch.height(),patch.width(),4)[:,:,:3]
    visible=np.ones((patch.height(),patch.width()),dtype=bool)
    for covered in exclude:
        part=covered.adjusted(-1,-1,1,1).intersected(interior)
        if not part.isEmpty():
            visible[part.top()-interior.top():part.bottom()-interior.top()+1,
                    part.left()-interior.left():part.right()-interior.left()+1]=False
    # Dense native pixels avoid a one-pixel geometry shift moving a sparse
    # sample grid onto the item art/text and toggling an otherwise stable pane.
    total=int(visible.sum())
    return total>=24 and int(((rgb.max(axis=2)<185)&visible).sum())>=total*.60


def _rim_pixels(image,exclude=(),*,native_scale=None):
    """Paired dark strokes around Classic's translucent one-pixel frame gap."""
    rgba=image.convertToFormat(QImage.Format.Format_RGBA8888)
    pixels=rgba.constBits();stride=rgba.bytesPerLine();width=rgba.width();height=rgba.height()
    # Explicit reader metadata uses the same middle/outer/phase sampling as
    # Rust, including odd-width antialiasing at 125%. Legacy discovery retains
    # its existing three symmetric rim widths.
    endpoint_tolerance=64 if native_scale is None else 65 if abs(native_scale-1)<.1 else 80
    patterns=((1,2,0),(2,4,0),(3,6,0)) if native_scale is None else tuple(
        (middle,max(2,int(2*native_scale+.5)),phase)
        for phase in range(max(1,ceil(native_scale)))
        for middle in sorted({max(1,floor(native_scale)),max(1,ceil(native_scale))}))
    # Validate only queried rim lanes. Full-display masks used several MB and
    # twelve array shifts for every supplied panel, even for a distant label.
    covered=tuple(part for rect in exclude
                  if not (part:=rect.adjusted(-1,-1,1,1).intersected(image.rect())).isEmpty())
    def rim(x,y,horizontal=False,_keep=rgba):
        if not (0<=x<width and 0<=y<height):return False
        # A covered stroke is unknown. In particular, our own opaque cards
        # cannot establish a frame or end a previously verified native edge.
        lane=QRect(x,y,1,min(7,height-y)) if horizontal else QRect(x,y,min(7,width-x),1)
        if any(lane.intersects(rect) for rect in covered):return None
        at=y*stride+x*4
        step=stride if horizontal else 4
        # Antialiased/native UI scaling widens the same dark/light/dark rim.
        # Both contrast directions matter: scenery behind a translucent frame
        # can make its middle stroke darker, rather than lighter, than its sides.
        for middle,outer,phase in patterns:
            if (y+phase+outer>=height if horizontal else x+phase+outer>=width):continue
            start=at+step*phase;a=pixels[start:start+3]
            b=pixels[start+step*middle:start+step*middle+3];c=pixels[start+step*outer:start+step*outer+3]
            if max(a)>=180 or max(c)>=180 or any(abs(a[i]-c[i])>endpoint_tolerance for i in range(3)):continue
            if any((b[i]-a[i]>=18 and b[i]-c[i]>=18) or
                   (a[i]-b[i]>=18 and c[i]-b[i]>=18) for i in range(3)):return True
        return False
    def grid(xs,ys,horizontal):
        xs=np.asarray(list(xs),dtype=np.int32);ys=np.asarray(list(ys),dtype=np.int32)
        if not len(xs) or not len(ys):return xs,ys,None,None
        rgb=np.frombuffer(pixels,dtype=np.uint8).reshape(height,stride)[:,:width*4].reshape(height,width,4)[:,:,:3]
        xx,yy=np.meshgrid(xs,ys)
        found=np.zeros(xx.shape,dtype=bool)
        for middle,outer,phase in patterns:
            valid=(yy+phase+outer<height) if horizontal else (xx+phase+outer<width)
            ax=xx if horizontal else np.minimum(xx+phase,width-1)
            ay=np.minimum(yy+phase,height-1) if horizontal else yy
            bx=xx if horizontal else np.minimum(xx+phase+middle,width-1)
            by=np.minimum(yy+phase+middle,height-1) if horizontal else yy
            cx=xx if horizontal else np.minimum(xx+phase+outer,width-1)
            cy=np.minimum(yy+phase+outer,height-1) if horizontal else yy
            a=rgb[ay,ax].astype(np.int16)
            b=rgb[by,bx].astype(np.int16);c=rgb[cy,cx].astype(np.int16)
            paired=(a.max(axis=2)<180)&(c.max(axis=2)<180)&(np.abs(a-c).max(axis=2)<=endpoint_tolerance)
            contrast=np.any(((b-a>=18)&(b-c>=18))|((a-b>=18)&(c-b>=18)),axis=2)
            found|=valid&paired&contrast
        valid=np.ones(xx.shape,dtype=bool)
        for rect in covered:
            right=xx if horizontal else np.minimum(xx+6,width-1)
            bottom=np.minimum(yy+6,height-1) if horizontal else yy
            valid&=~((xx<=rect.right())&(right>=rect.left())&(yy<=rect.bottom())&(bottom>=rect.top()))
        return xs,ys,found,valid
    def axis_scores(xs,ys,horizontal=False,_keep=rgba):
        """The same stroke predicate, batched over a bounded search grid."""
        xs,ys,found,valid=grid(xs,ys,horizontal)
        if found is None:return {}
        axis=1 if horizontal else 0
        count=valid.sum(axis=axis);hits=(found&valid).sum(axis=axis)
        values=np.divide(hits,count,out=np.zeros(hits.shape,dtype=float),where=count>=4)
        return dict(zip((ys if horizontal else xs).tolist(),values.tolist()))
    def cap_scores(left,rights,ys,_keep=rgba):
        """Score every candidate cap from one shared native-pixel grid.

        The candidate widths share the same left edge and sample phase. Prefix
        sums avoid rebuilding that grid for every rail visible through a pane.
        """
        if not rights:return {}
        xs,ys,found,valid=grid(range(left+5,max(rights)-4,6),ys,True)
        if found is None:return {}
        hits=(found&valid).cumsum(axis=1);counts=valid.cumsum(axis=1)
        result={}
        for right in rights:
            n=len(range(left+5,right-4,6))
            if n<10:continue
            count=counts[:,n-1];hit=hits[:,n-1]
            scores=np.divide(hit,count,out=np.zeros(hit.shape,dtype=float),where=count>=4)
            result[right]=dict(zip(ys.tolist(),scores.tolist()))
        return result
    rim.axis_scores=axis_scores
    rim.cap_scores=cap_scores
    return rim


def _closed_cap(rim,left,right,y,scale=1.0):
    """A cap must end at its frame, rather than cross a background divider."""
    middle=floor(5*scale+.5);step=max(1,floor(scale+.5))
    # A single scenery/glyph pixel can erase the contrast at one sample in a
    # translucent cap. Both corners need two current strokes in a tiny lane;
    # neither a broad average nor a background divider can supply a corner.
    for corner,direction in ((left,1),(right,-1)):
        if sum(rim(corner+direction*offset,y,True) is True
               for offset in (middle-step,middle,middle+step))<2:return False
    after=right+max(1,ceil(3*scale))
    outside=(left-max(1,ceil(4*scale)),after,after+max(1,round(scale)))
    return sum(rim(x,y,True) is False for x in outside)>=2


def verified_frame(image,rect,*,scale=1.0,cap=True,exclude=()):
    """Revalidate a supplied native frame; never rediscover or lend identity."""
    if (image is None or image.isNull() or rect is None or rect.isEmpty()
            or not image.rect().contains(rect) or rect.width()*rect.height()>1_048_576
            or not .65<=scale<=2.1 or not _description_body(image,rect,exclude)):return False
    rim=_rim_pixels(image,exclude,native_scale=scale)
    right=rect.x()+rect.width()-max(2,ceil(3*scale))
    ys=range(rect.y()+max(6,round(12*scale)),rect.bottom()-max(4,round(5*scale)),max(3,round(8*scale)))
    side_scores=rim.axis_scores((rect.left(),right),ys)
    for x in (rect.left(),right):
        if len(ys)<5 or side_scores.get(x,0)<.55:return False
    if cap:
        xs=range(rect.left()+max(4,round(5*scale)),right-max(3,round(4*scale)),max(3,round(6*scale)))
        ys=range(max(0,rect.top()-1),min(image.height()-2,rect.top()+max(2,round(scale))+1))
        cap_scores=rim.axis_scores(xs,ys,True)
        for y in ys:
            if len(xs)>=10 and cap_scores.get(y,0)>=.5 and _closed_cap(rim,rect.left(),right,y,scale):return True
        return False
    return True


def native_panel(value,found,image,exclude=()):
    """Read the native reader's explicit, same-capture single/link geometry."""
    if (not isinstance(value,dict) or type(value.get('version')) is not int
            or value['version']!=1 or not isinstance(found,dict)):return None
    try:
        area=found['area'];title=value['title'];bounds=value['panel'];scale=value['scale']
        parts=tuple(bounds[k] for k in ('x','y','width','height'))
        if (title!=area or any(type(v) is not int for v in parts) or any(abs(v)>32768 for v in parts)
                or type(scale) not in (int,float)):return None
        rect=QRect(*parts);name=QRect(*(area[k] for k in ('x','y','width','height')))
    except (KeyError,TypeError,ValueError,OverflowError):return None
    return rect if rect.contains(name) and verified_frame(image,rect,scale=scale,exclude=exclude) else None


def _framed_bounds(image,name,exclude=(),*,allow_masked_edge=False,rim_pixels=None):
    # Require the recognized name plus two independently repeated frame edges.
    # Warm chat behind the panel can erase its purple hue, but not its geometry.
    rim=rim_pixels or _rim_pixels(image,exclude)
    ys=range(max(0,name.top()-1),min(image.height(),name.top()+123),2 if exclude else 6)
    if len(ys)<5:return None
    scores=(rim.axis_scores(range(max(0,name.left()-28),min(image.width()-7,name.left()+740)),ys)
            if hasattr(rim,'axis_scores') else {})
    def score(x):
        if x not in scores:
            samples=[value for y in ys if (value:=rim(x,y)) is not None]
            scores[x]=sum(samples)/len(samples) if len(samples)>=4 else 0
        return scores[x]
    left=max(((score(x),x) for x in range(max(0,name.left()-28),max(0,name.left()-3))),default=(0,0))
    if left[0]<.55:return None
    left=left[1]
    masked_edge=None
    if allow_masked_edge:
        for covered in sorted(exclude,key=lambda r:r.left()):
            edge=covered.left()-1
            if not name.right()+3<edge<left+740:continue
            samples=[rim(edge+2,y) for y in ys]
            if sum(value is None for value in samples)>=len(samples)*.65:
                masked_edge=edge;break
    # Ignore repeated strokes inside the name/body instead of abandoning the
    # framed path at the first one. The boundary must enclose the entire name
    # and repeat down the panel independently of those glyphs.
    limit=min(image.width()-7,left+740,masked_edge if masked_edge is not None else image.width())
    candidates=[x for x in range(max(left+70,name.right()-2),limit) if score(x)>=.65]
    def boundary(x):
        samples=[]
        for y in ys:
            if rim(x,y) is None or rim(x-5,y) is None:continue
            inside=image.pixelColor(x-4,y);outside=image.pixelColor(x+7,y)
            a=max(inside.red(),inside.green(),inside.blue());b=max(outside.red(),outside.green(),outside.blue())
            samples.append(a<185 and b-a>=25)
        return sum(samples)/len(samples) if len(samples)>=4 else 0
    # Translucent descriptions expose shop dividers behind their body. Prefer
    # the edge that actually exits that dark body, rather than an inner divider.
    # Prefer complete closed caps over an interior inventory edge visible
    # through a translucent body. Keep legacy clipped/masked geometry below.
    closed=None
    cap_ys=range(max(0,name.top()-96),max(0,name.top()-5))
    cap_scores=rim.cap_scores(left,candidates[:64],cap_ys) if hasattr(rim,'cap_scores') else {}
    for candidate in candidates[:64]:
        columns=range(left+5,candidate-4,6)
        if len(columns)<10:continue
        candidate_scores=(cap_scores[candidate] if candidate in cap_scores else rim.axis_scores(columns,cap_ys,True)
                          if hasattr(rim,'axis_scores') else {})
        top=next((y for y in cap_ys
                  if (candidate_scores.get(y,0) if candidate_scores else sum(rim(x,y,True) is True for x in columns)/len(columns))>=.5
                  and any(_closed_cap(rim,left,candidate,y,s) for s in (1.0,1.25,1.5,2.0))),None)
        if top is not None:closed=(candidate,top);break
    right=closed[0] if closed else next((x for x in candidates if boundary(x)>=.45),None)
    partial=False
    if masked_edge is not None and (right is None or masked_edge<right):
        right=masked_edge;partial=True
    if right is None:right=candidates[0] if candidates else None
    if right is None:return None
    seed=name.center().y();edges=[]
    for direction,limit in ((-1,max(-1,name.top()-96)),(1,min(image.height(),name.top()+900))):
        last=seed;gap=0
        for y in range(seed,limit,direction):
            a,b=rim(left,y),rim(right,y)
            if a is None and b is None:continue
            if a or b:last=y;gap=0
            else:gap+=1
            if gap>10:break
        edges.append(last)
    top,bottom=edges
    # An opaque price card can leave only a narrow native strip exposed.
    # Sample that strip densely enough to verify its independent horizontal
    # cap; the card itself remains entirely excluded from frame evidence.
    columns=(range(left+4,right-3,2) if partial and right-left<70
             else range(left+8,right-6,6))
    horizontal_scores=(rim.axis_scores(columns,range(max(0,name.top()-80),min(image.height()-2,bottom+6)),True)
                       if hasattr(rim,'axis_scores') else {})
    def horizontal_score(y):
        if y in horizontal_scores:return horizontal_scores[y]
        samples=[value for x in columns if (value:=rim(x,y,True)) is not None]
        return sum(samples)/len(samples) if len(samples)>=4 else 0
    caps=[y for y in range(max(0,name.top()-80),min(image.height()-2,name.top())) if horizontal_score(y)>=.55]
    def top_boundary(y):
        samples=[]
        if y<4 or y+7>=image.height():return False
        for x in columns:
            if rim(x,y-4,True) is None or rim(x,y+1,True) is None:continue
            inside=image.pixelColor(x,y+7);outside=image.pixelColor(x,y-4)
            a=(inside.red(),inside.green(),inside.blue());b=(outside.red(),outside.green(),outside.blue())
            samples.append(max(a)<185 and max(abs(p-q) for p,q in zip(a,b))>=25)
        return len(samples)>=4 and sum(samples)>=len(samples)*.6
    # Personalized equipment can have extra text above its item name. Prefer
    # the actual transition into the native dark body over an inner rule or
    # guessed title padding; neither the item name nor owner text fixes its top.
    boundaries=[y for y in caps if top_boundary(y)]
    cap=closed[1] if closed and right==closed[0] else min(boundaries) if boundaries else min(caps,key=lambda y:abs(y-(name.top()-name.height()*.85))) if caps else None
    bottom_cap=None
    if partial:
        def left_edge_ends(y):
            samples=[value for yy in range(y+6,min(image.height(),y+25),2)
                     if (value:=rim(left,yy)) is not None]
            return len(samples)>=4 and sum(samples)<=len(samples)*.2
        # The masked far edge may coincide with another shop border after the
        # real description ends. Its first horizontal cap and terminating left
        # edge take precedence over those unrelated strokes farther below.
        bottom_cap=next((y for y in range(seed+max(40,name.height()+8),min(image.height()-2,bottom+6))
                         if horizontal_score(y)>=.55 and left_edge_ends(y)),None)
        if bottom_cap is not None:bottom=bottom_cap+2
    if partial and cap is None:
        # Near the list's right edge, the cursor can cover the whole exposed
        # top corner while opaque annotations cover the far side. A native
        # bottom cap plus the repeated left edge independently proves the pane.
        if bottom_cap is None:return None
        top=min(top,name.top()-name.height())
    if cap is None and not partial and score(right)<.55:return None
    if cap is not None:top=cap
    if bottom-top<max(40,name.height()+8):return None
    return QRect(left,top-1,right-left+3,bottom-top+3).intersected(image.rect())


def description_bounds(image,area,exclude=(),*,source_verified=False):
    if image is None or image.isNull() or not area:return None
    name=QRect(*(int(area[k]) for k in ('x','y','width','height')))
    # A tooltip can extend past a cropped fixture or the shared display edge.
    # Its recognized name line is allowed to be clipped there as well.
    name=name.intersected(image.rect())
    if name.width()<12 or name.height()<8:return None
    visible=_visible_region(name,exclude)
    if not source_verified and sum(part.width()*part.height() for part in visible)<name.width()*name.height()*.25:return None
    framed=_framed_bounds(image,name,exclude)
    if framed is not None:return framed if _description_body(image,framed,exclude) else None
    def fill(x,y):
        if not(0<=x<image.width() and 0<=y<image.height()):return False
        c=image.pixelColor(x,y);r,g,b=c.red(),c.green(),c.blue()
        return 0<=r<=155 and 0<=g<=160 and b>=max(r,g)+18 and b*100>=max(r,g)*116
    best=None
    for y in (name.top()-4,name.top()-8,name.top()+2,name.bottom()+4,name.bottom()+12):
        if not 0<=y<image.height():continue
        for seed in (name.left()-5,name.left()-9,name.left()-13,name.left()+2):
            if not fill(seed,y):continue
            left=seed
            while left>0 and fill(left-1,y):left-=1
            right=seed;last=seed;gap=0
            while right<min(image.width(),left+760):
                if fill(right,y):last=right;gap=0
                else:gap+=1
                if gap>12:break
                right+=1
            if last-left>=60 and (best is None or last-left>best[1]-best[0]):best=(left,last,y)
    if best is None:return None
    left,right,seed_y=best
    # The colour fallback can cross a thin native border and join two adjacent
    # comparison descriptions. A repeated structural divider takes precedence
    # over a wider purple span, even if the other side of this panel is covered.
    rim=_rim_pixels(image)
    ys=range(max(0,name.top()-1),min(image.height(),name.top()+max(123,name.height()*8)),6)
    divider=next((x for x in range(max(left+60,name.right()+1),min(right,image.width()-6))
                  if len(ys)>=5 and sum(rim(x,y) for y in ys)>=max(3,len(ys)*.65)),None)
    if divider is not None:right=divider+2
    spans=[]
    # The cyan name bullet or item art can interrupt one gutter column.
    # Try both inner edges rather than treating that interruption as the end.
    for column in (left+1,min(right,left+3),min(right,left+5),max(left,right-2)):
        top=bottom=seed_y
        for direction in (-1,1):
            y=seed_y;last=y;gap=0
            while 0<=y<image.height():
                if fill(column,y):last=y;gap=0
                else:gap+=1
                if gap>4:break
                y+=direction
            if direction<0:top=last
            else:bottom=last
        spans.append((top,bottom))
    top,bottom=max(spans,key=lambda span:span[1]-span[0])
    if bottom-top<name.height()+8:return None
    # Our price cards may cover the name's right half. Inspect the visible gaps
    # between them, within the already anchored panel, to recover its full width.
    for covered in exclude:
        for y in (covered.top()-3,covered.bottom()+3):
            if not top+3<=y<=bottom-3 or not fill(left+3,y):continue
            end=left+3;last=end;gap=0
            while end<min(image.width(),left+760):
                if fill(end,y):last=end;gap=0
                else:gap+=1
                if gap>12:break
                end+=1
            right=max(right,last)
    if divider is not None:right=min(right,divider+2)
    rect=QRect(left-3,top-3,right-left+7,bottom-top+7).intersected(image.rect())
    return rect if _description_body(image,rect,exclude) else None


def still_present(image,rect,exclude=()):
    if not _description_body(image,rect,exclude):return False
    matches=0
    for fraction in (.2,.5,.8):
        point=(min(rect.right(),rect.left()+6),round(rect.top()+rect.height()*fraction))
        if any(hidden.contains(*point) for hidden in exclude):continue
        c=image.pixelColor(*point)
        if c.red()<=155 and c.green()<=160 and c.blue()>max(c.red(),c.green())+18:matches+=1
    if matches>=2:return True
    rim=_rim_pixels(image,exclude)
    ys=range(rect.top()+max(3,round(rect.height()*.1)),rect.bottom()-max(3,round(rect.height()*.1)),2)
    edges=[]
    for x in (rect.left(),rect.right()-2):
        samples=[value for y in ys if (value:=rim(x,y)) is not None]
        if len(samples)>=4:edges.append(sum(samples)/len(samples)>=.45)
    return bool(edges and all(edges))


def shop_description_bounds(image,pointer,*,scale=1.0,exclude=()):
    """Find a framed native header beside an already verified shop source.

    This bounded pixel-only probe supplies occlusion geometry, never an item or
    a price. Cyan scenery without paired frame strokes cannot establish a pane.
    """
    if image is None or image.isNull() or pointer is None:return None
    scale=max(.5,min(3.0,float(scale)))
    x,y=pointer
    search=QRect(round(x-700*scale),round(y-700*scale),round(1400*scale),round(1000*scale)).intersected(image.rect())
    if search.isEmpty() or search.width()*search.height()>1_500_000:return None
    patch=image.copy(search).convertToFormat(QImage.Format.Format_RGBA8888)
    pixels=np.frombuffer(patch.constBits(),dtype=np.uint8).reshape(patch.height(),patch.bytesPerLine())
    rgb=pixels[:,:patch.width()*4].reshape(patch.height(),patch.width(),4)[:,:,:3].astype(np.int16)
    mask=(rgb[:,:,2]>=200)&(rgb[:,:,1]>=140)&(rgb[:,:,0]<=140)&(rgb[:,:,1]-rgb[:,:,0]>=70)
    for hidden in exclude:
        part=search.intersected(hidden)
        if not part.isEmpty():mask[part.top()-search.top():part.bottom()-search.top()+1,part.left()-search.left():part.right()-search.left()+1]=False
    if np.count_nonzero(mask)<4:return None
    # Cyan scenery may occupy thousands of pixels. Locate short runs first,
    # then inspect only bounded local components instead of rejecting the pane
    # because unrelated scenery happens to use the same colour.
    starts=mask.copy();starts[:,1:]&=~mask[:,:-1]
    ends=mask.copy();ends[:,:-1]&=~mask[:,1:]
    ys,xs=np.nonzero(starts);_,last_x=np.nonzero(ends)
    maximum=max(2,round(13*scale));short=last_x-xs+1<=maximum
    ys,xs=ys[short],xs[short]
    if not len(xs):return None
    distances=np.abs(xs+search.x()-x)+np.abs(ys+search.y()-y)
    # Nearby character art can contain hundreds of cyan short runs. Bound
    # work by spatial cells so one patch of scenery cannot consume every
    # candidate before the actual native title marker is reached.
    order=[];cells={};cell_size=max(8,round(16*scale))
    for index in np.argsort(distances):
        cell=(int(xs[index])//cell_size,int(ys[index])//cell_size)
        if cells.get(cell,0)>=4:continue
        cells[cell]=cells.get(cell,0)+1;order.append(index)
        if len(order)>=256:break
    visited=set();dots=[]
    for index in order:
        first=(int(xs[index]),int(ys[index]))
        if first in visited:continue
        visited.add(first);stack=[first];points=[first];left=right=first[0];top=bottom=first[1];large=False
        while stack:
            xx,yy=stack.pop()
            for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
                neighbour=(xx+dx,yy+dy)
                nx,ny=neighbour
                if 0<=nx<mask.shape[1] and 0<=ny<mask.shape[0] and mask[ny,nx] and neighbour not in visited:
                    visited.add(neighbour);stack.append(neighbour);points.append(neighbour)
                    left=min(left,nx);right=max(right,nx);top=min(top,ny);bottom=max(bottom,ny)
                    if right-left+1>maximum or bottom-top+1>maximum:
                        large=True;break
            if large:break
        if not large and 4<=len(points) and 2<=right-left+1<=maximum and 2<=bottom-top+1<=maximum:
            dots.append(QRect(search.x()+left,search.y()+top,right-left+1,bottom-top+1))
    dots.sort(key=lambda dot:abs(dot.center().x()-x)+abs(dot.center().y()-y))
    rim=_rim_pixels(image,exclude)
    def beside_frame(dot):
        ys=range(max(0,dot.top()-1),min(image.height(),dot.top()+48),8)
        for xx in range(max(0,dot.left()-28),max(0,dot.left()-3)):
            samples=[value for yy in ys if (value:=rim(xx,yy)) is not None]
            if len(samples)>=4 and sum(samples)>=len(samples)*.4:return True
        return False
    candidates=[dot for dot in dots if beside_frame(dot)]
    for dot in candidates[:8]:
        # This anchor is the observed marker, not an estimated title width.
        # Extending it behind our own card can hide the only real native edge.
        name=QRect(dot.x(),dot.y()-round(3*scale),max(dot.width(),round(6*scale)),max(10,round(14*scale)))
        rect=_framed_bounds(image,name,exclude,allow_masked_edge=True,rim_pixels=rim)
        if rect is not None and rect.adjusted(-round(220*scale),-round(220*scale),round(220*scale),round(220*scale)).contains(x,y) and _description_body(image,rect,exclude):
            return rect
    return None


class TooltipReference:
    """Bridge a brief OCR miss only while the same captured name/panel remains."""
    def __init__(self):self.clear()

    def clear(self):
        self.found=None;self.name=None;self.panel=None;self.pixels=b'';self.pointer=None;self.at=0;self.context=None

    @staticmethod
    def signature(image,rect):
        if rect is None or not image.rect().contains(rect):return b''
        patch=image.copy(rect).convertToFormat(QImage.Format.Format_Grayscale8)
        return bytes(patch.constBits())

    def observe(self,found,image,pointer,allow=True,now=None,*,context=None,exclude=()):
        now=time.monotonic() if now is None else now
        if not allow:self.clear();return None
        if self.context is not None and (context is None or context.token!=self.context.token):self.clear()
        if context is not None and not context.matches(image,pointer,exclude=exclude):self.clear();return None
        if found:
            area=found['area'];self.name=QRect(*(area[k] for k in ('x','y','width','height'))).intersected(image.rect())
            self.panel=context.panel if context is not None else description_bounds(image,area);self.pixels=self.signature(image,self.name)
            self.found=found;self.pointer=pointer;self.at=now;self.context=context
            return found
        if self.found and pointer and self.pointer and now-self.at<=.4 and max(abs(a-b) for a,b in zip(pointer,self.pointer))<=8 and still_present(image,self.panel):
            current=self.signature(image,self.name)
            if current and len(current)==len(self.pixels) and sum(abs(a-b)>22 for a,b in zip(current,self.pixels))/len(current)<.04:
                return self.found
        self.clear();return None
