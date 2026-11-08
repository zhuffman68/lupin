//! Native description frames measured from raw captured pixels.
//! A repeated interior stroke is not a boundary: a positive frame needs the
//! horizontal cap to terminate at both corners. No text/market identity is used.
use crate::tooltip_surface::{Dot, rgb, title_light};
use minerva_core::{Frame, ItemCapture, ScreenPoint};
use serde_json::{Value, json};

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct BoxRect {
    pub x: u32,
    pub y: u32,
    pub w: u32,
    pub h: u32,
}
impl BoxRect {
    pub(crate) fn right(self) -> u32 { self.x + self.w }
    pub(crate) fn bottom(self) -> u32 { self.y + self.h }
    pub(crate) fn contains(self, x: i32, y: i32) -> bool {
        x >= self.x as i32 && y >= self.y as i32
            && x < self.right() as i32 && y < self.bottom() as i32
    }
    pub(crate) fn encloses(self, other: Self) -> bool {
        other.x >= self.x && other.y >= self.y && other.right() <= self.right()
            && other.bottom() <= self.bottom()
    }
    pub(crate) fn global(self, c: &ItemCapture) -> Value {
        json!({"x":i64::from(self.x)+i64::from(c.origin.x),"y":i64::from(self.y)+i64::from(c.origin.y),"width":self.w,"height":self.h})
    }
}

#[derive(Clone, Copy)]
pub(crate) struct Panel {
    pub rect: BoxRect,
    pub title: BoxRect,
    pub cap: bool,
    pub marker: bool,
}

pub(crate) fn edge(frame: &Frame, x: u32, y: u32, s: f32, horizontal: bool) -> bool {
    let outer = (2.0 * s).round().max(2.0) as u32;
    // Both outer strokes remain dark, with a real reversal at the middle.
    // Native translucent rims also blend with white inventory behind them at
    // 1x; the old near-equal endpoint rule lost their actual outer boundary.
    let tolerance = if (s - 1.0).abs() < 0.1 { 65 } else { 80 };
    for phase in 0..s.ceil().max(1.0) as u32 {
        let point = |d| if horizontal {(x,y+phase+d)} else {(x+phase+d,y)};
        let (ex,ey)=point(outer);
        if ex>=frame.width || ey>=frame.height {continue}
        let (ax,ay)=point(0);let a=rgb(frame,ax,ay);let c=rgb(frame,ex,ey);
        if !(0..3).all(|i|a[i]<180&&c[i]<180&&a[i].abs_diff(c[i])<=tolerance) {continue}
        for middle in [s.floor().max(1.0) as u32,s.ceil().max(1.0) as u32] {
            let (bx,by)=point(middle);let b=rgb(frame,bx,by);
            if (0..3).any(|i| {
                let d=i16::from(b[i])-i16::from(a[i]);
                let e=i16::from(b[i])-i16::from(c[i]);
                d>=18&&e>=18 || d<=-18&&e<=-18
            }) {return true}
        }
    }
    false
}

fn known_edge(frame: &Frame,x: u32,y: u32,s: f32,horizontal: bool,exclude: &[BoxRect]) -> Option<bool> {
    // Match Python's one-pixel mask margin and seven-pixel sample envelope.
    // Our own paint is unknown; it cannot supply or contradict a native rim.
    let (w,h)=if horizontal {(1,7)} else {(7,1)};
    if exclude.iter().any(|r| x.saturating_add(w)>r.x.saturating_sub(1)
        && x<r.right().saturating_add(1) && y.saturating_add(h)>r.y.saturating_sub(1)
        && y<r.bottom().saturating_add(1)) {None} else {Some(edge(frame,x,y,s,horizontal))}
}

fn closed_cap(frame: &Frame, left: u32, right: u32, top: u32, s: f32,exclude: &[BoxRect]) -> bool {
    // An inventory rail showing through the body cannot end the description's
    // cap. A real corner has a short break beyond it, including when another
    // description starts just a few pixels away.
    let step=s.round().max(1.0) as u32;
    let middle=(5.0*s).round() as u32;
    let offsets=[middle.saturating_sub(step),middle,middle+step];
    // Match Python's bounded two-of-three corner proof. A single changing
    // background pixel cannot erase an otherwise current translucent cap.
    if offsets.iter().filter(|&&d|known_edge(frame,left+d,top,s,true,exclude)==Some(true)).count()<2
        || offsets.iter().filter(|&&d|known_edge(frame,right.saturating_sub(d),top,s,true,exclude)==Some(true)).count()<2 {return false}
    let after=right+(3.0*s).ceil() as u32;
    let before=left.saturating_sub((4.0*s).ceil() as u32);
    let outside=[before,after,after+step];
    outside.iter().filter(|&&x|known_edge(frame,x,top,s,true,exclude)==Some(false)).count()>=2
}

pub(crate) fn panel_from_header(frame: &Frame, dot: Dot, s: f32, marker: bool) -> Option<Panel> {
    panel_with_exclusions(frame,dot,s,marker,&[])
}

pub(crate) fn panel_with_exclusions(frame: &Frame,dot: Dot,s: f32,marker: bool,exclude: &[BoxRect]) -> Option<Panel> {
    let from=dot.y1+(6.0*s).round() as u32;
    let end=(dot.y1+(100.0*s).round() as u32).min(frame.height);
    let ys=(from..end).step_by((6.0*s).round().max(3.0) as usize);
    let n=ys.clone().count();if n<8 {return None}
    let score=|x| {
        let mut seen=0;let mut hits=0;
        for y in ys.clone() {if let Some(hit)=known_edge(frame,x,y,s,false,exclude) {seen+=1;hits+=usize::from(hit)}}
        if seen<4 {0} else {hits*100/seen}
    };
    let lo=dot.x0.saturating_sub((28.0*s).ceil() as u32);
    let hi=dot.x0.saturating_sub((4.0*s).floor() as u32);
    let mut lefts:Vec<_>=(lo..hi).filter(|&x|score(x)>=65).collect();
    // A foreground frame may have less contrast than an inventory rail behind
    // it. Evaluate complete rectangles for all nearby left-edge hypotheses.
    let expected=dot.x0.saturating_sub((9.0*s).round() as u32);
    lefts.sort_by_key(|x|(x.abs_diff(expected),std::cmp::Reverse(score(*x))));
    let mut fallback=None;
    for left in lefts.into_iter().take(16) {
        // Bound plausible rails independently of scene complexity.
        let rights=(left+(140.0*s).round() as u32
            ..(left+(740.0*s).round() as u32).min(frame.width.saturating_sub(2)))
            .filter(|&x|score(x)>=65);
        for right in rights.take(64) {
            fallback.get_or_insert((left,right));
            let xs=(left+(5.0*s).round() as u32..right.saturating_sub((4.0*s).round() as u32))
                .step_by((6.0*s).round().max(3.0) as usize);
            let total=xs.clone().count();if total<10 {continue}
            // Owner tags can add header lines. Dark scenery can erase part of
            // a translucent cap; closed corners and both side rails still bind it.
            let caps=(dot.y0.saturating_sub((96.0*s).ceil() as u32)
                ..dot.y0.saturating_sub((5.0*s).floor() as u32))
                .filter(|&y| {
                    let known:Vec<_>=xs.clone().filter_map(|x|known_edge(frame,x,y,s,true,exclude)).collect();
                    known.len()>=10 && known.iter().filter(|&&hit|hit).count()*2>=known.len()
                        &&closed_cap(frame,left,right,y,s,exclude)
                });
            for top in caps.take(8) {
                if let Some(panel)=finish_panel(frame,dot,s,left,right,top,true,marker,exclude) {return Some(panel)}
            }
        }
    }
    // Incomplete framed bodies remain ambiguity evidence only. They never
    // authorize a standalone source or marker-free title read.
    let (left,right)=fallback?;
    finish_panel(frame,dot,s,left,right,dot.y0.saturating_sub((15.0*s).round() as u32),false,marker,exclude)
}

fn finish_panel(frame: &Frame, dot: Dot, s: f32, left: u32, right: u32, top: u32,
    cap: bool, marker: bool,exclude: &[BoxRect]) -> Option<Panel> {
    let (mut last,mut gap)=(dot.y1,0);
    for y in dot.y1..(dot.y1+(700.0*s).ceil() as u32).min(frame.height) {
        let a=known_edge(frame,left,y,s,false,exclude);let b=known_edge(frame,right,y,s,false,exclude);
        if a==Some(true)||b==Some(true) {last=y;gap=0}
        else if a.is_some()&&b.is_some() {gap+=1}
        if gap>(10.0*s).ceil() as u32 {break}
    }
    let bottom=(last+1).min(frame.height);
    if bottom<top+(80.0*s).round() as u32 {return None}
    if cap {
        // A short inventory rail through the translucent header can resemble
        // a side. Require both full-height rails before choosing this candidate
        // and continue searching if it fails, as Python's current proof does.
        let ys=(top+(12.0*s).round().max(6.0) as u32
            ..bottom.saturating_sub(1+(5.0*s).round().max(4.0) as u32))
            .step_by((8.0*s).round().max(3.0) as usize);
        if ys.clone().count()<5 || [left,right].into_iter().any(|x| {
            let known:Vec<_>=ys.clone().filter_map(|y|known_edge(frame,x,y,s,false,exclude)).collect();
            known.len()<4 || known.iter().filter(|&&hit|hit).count()*100<known.len()*55
        }) {return None}
    }
    let rect=BoxRect{x:left,y:top,w:(right+(3.0*s).ceil() as u32).min(frame.width)-left,h:bottom-top};
    let (mut dark,mut all)=(0,0);
    for y in (top+6..bottom.saturating_sub(5)).step_by(13) {
        for x in (left+6..right.saturating_sub(5)).step_by(13) {
            if exclude.iter().any(|r|r.contains(x as i32,y as i32)) {continue}
            all+=1;dark+=usize::from(rgb(frame,x,y).iter().all(|v|*v<185));
        }
    }
    let bright=(dot.y0.saturating_sub(4)..(dot.y1+4).min(frame.height))
        .flat_map(|y|(dot.x1+2..right.saturating_sub(4)).map(move|x|(x,y)))
        .filter(|&(x,y)|!exclude.iter().any(|r|r.contains(x as i32,y as i32))
            &&title_light(rgb(frame,x,y)).is_some_and(|v|v>=150)).count();
    if all<24||dark*10<all*6||marker&&bright<16 {return None}
    Some(Panel{rect,title:BoxRect{x:dot.x0,y:dot.y0.saturating_sub((6.0*s).ceil() as u32),
        w:rect.right().saturating_sub(dot.x0),h:((dot.y1-dot.y0)+(12.0*s).ceil() as u32)
            .min(frame.height-dot.y0.saturating_sub((6.0*s).ceil() as u32))},cap,marker})
}

pub(crate) fn around_title(frame: &Frame, name: BoxRect, s: f32) -> Option<Panel> {
    let dot=Dot{x0:name.x,y0:name.y+(name.h/2).saturating_sub(2),
        x1:name.x+5,y1:name.y+name.h/2+3};
    let panel=panel_from_header(frame,dot,s,false)?;
    (panel.cap&&panel.rect.encloses(name)).then_some(panel)
}

/// Complete one partly visible member of a current comparison family. The
/// independently capped neighbour constrains the seam/top; both current rails
/// and the dark body must still support the candidate. No title is borrowed.
pub(crate) fn fit_neighbour(frame: &Frame, candidate: Panel, anchor: Panel, s: f32) -> Option<Panel> {
    // A common top rim can also make a union of both descriptions look closed.
    // An independently framed enclosed neighbour supplies the real divider.
    if !anchor.cap||(candidate.cap&&!candidate.rect.encloses(anchor.rect)) {return None}
    let before=candidate.rect.x<anchor.rect.x;
    let left=candidate.rect.x;
    let y0=candidate.title.y+(6.0*s).ceil() as u32;
    if y0<anchor.rect.y || y0>anchor.rect.y+(96.0*s).ceil() as u32 {return None}
    let ys=(y0+(12.0*s).round() as u32..(y0+(100.0*s).round() as u32).min(frame.height))
        .step_by((6.0*s).round().max(3.0) as usize);
    let total=ys.clone().count();if total<8 {return None}
    let score=|x|ys.clone().filter(|&y|edge(frame,x,y,s,false)).count()*100/total;
    if score(left)<65 {return None}
    let lo=if before {anchor.rect.x.saturating_sub((11.0*s).ceil() as u32)}
        else {left+(anchor.rect.w as f32*0.7).floor() as u32};
    let hi=if before {anchor.rect.x.saturating_sub((3.0*s).round() as u32)}
        else {(left+(anchor.rect.w as f32*1.4).ceil() as u32).min(frame.width.saturating_sub(3))};
    let expected=if before {anchor.rect.x.saturating_sub((5.0*s).round() as u32)}
        else {left+anchor.rect.w-(3.0*s).ceil() as u32};
    let mut rights:Vec<_>=(lo..=hi).filter(|&x|x>left&&score(x)>=65).collect();
    rights.sort_by_key(|x|x.abs_diff(expected));
    for right in rights.into_iter().take(12) {
        let width=right+(3.0*s).ceil() as u32-left;
        let ratio=width as f32/anchor.rect.w as f32;
        if !(0.7..=1.4).contains(&ratio) {continue}
        if !before && (left<anchor.rect.right()||left-anchor.rect.right()>(8.0*s).ceil() as u32) {continue}
        let (mut last,mut gap)=(y0,0);
        for y in y0..(y0+(700.0*s).ceil() as u32).min(frame.height) {
            if edge(frame,left,y,s,false)||edge(frame,right,y,s,false) {last=y;gap=0} else {gap+=1}
            if gap>(10.0*s).ceil() as u32 {break}
        }
        let rect=BoxRect{x:left,y:anchor.rect.y,w:width,h:last+1-anchor.rect.y};
        if rect.h<(80.0*s).round() as u32||candidate.title.x>=rect.right() {continue}
        let (mut dark,mut all)=(0,0);
        for y in (rect.y+6..rect.bottom().saturating_sub(5)).step_by(13) {
            for x in (left+6..right.saturating_sub(5)).step_by(13) {
                all+=1;dark+=usize::from(rgb(frame,x,y).iter().all(|v|*v<185));
            }
        }
        if all>0&&dark*10>=all*6 {
            return Some(Panel{rect,title:BoxRect{w:rect.right()-candidate.title.x,..candidate.title},cap:false,..candidate})
        }
    }
    None
}

pub(crate) fn export_for_title(frame: &Frame, origin: ScreenPoint, area: &Value, s: f32) -> Option<Value> {
    let x=area["x"].as_i64()?.checked_sub(i64::from(origin.x))?;
    let y=area["y"].as_i64()?.checked_sub(i64::from(origin.y))?;
    let w=u32::try_from(area["width"].as_u64()?).ok()?;
    let h=u32::try_from(area["height"].as_u64()?).ok()?;
    if x<0||y<0||x+i64::from(w)>i64::from(frame.width)||y+i64::from(h)>i64::from(frame.height) {return None}
    let name=BoxRect{x:x as u32,y:y as u32,w,h};
    let panel=around_title(frame,name,s)?;
    Some(json!({"version":1,"panel":{"x":i64::from(panel.rect.x)+i64::from(origin.x),
        "y":i64::from(panel.rect.y)+i64::from(origin.y),"width":panel.rect.w,"height":panel.rect.h},
        "title":area,"scale":s}))
}
