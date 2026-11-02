//! Bind a horizontal native comparison pair to its captured inventory source.
//! No names, market data, game state or input are used to choose the panel.
use crate::tooltip_surface::{Dot, rgb, title_light};
use minerva_core::{Frame, ItemCapture};
use serde_json::{Value, json};
pub(crate) use crate::tooltip_frame::{BoxRect, Panel, edge, panel_from_header};

#[derive(Clone)]
struct Inventory {
    rect: BoxRect,
    tab: u32,
    scale: f32,
    guard: Vec<u8>,
}
#[derive(Clone)]
struct PairBinding {
    source: BoxRect,
    scope: (i32, i32, u32, u32),
    panels: [Panel; 2],
    comparison_ink: Vec<u8>,
    scale: f32,
}

pub struct Association {
    pub panel: Option<BoxRect>,
    /// Current header of a structurally proven primary whose marker is hidden.
    /// This authorizes bounded title OCR only inside the selected primary.
    pub primary_header: Option<BoxRect>,
    pub rejected: bool,
    pub metadata: Value,
}
#[derive(Default)]
pub struct Selector {
    inventory: Option<Inventory>,
    bound_source: Option<(BoxRect, (i32, i32, u32, u32))>,
    pair: Option<PairBinding>,
}

fn pink(p: [u8; 3]) -> bool {
    p[0] >= 180 && p[0].saturating_sub(p[1]) >= 35 && p[1].abs_diff(p[2]) < 55 && p[2] >= 60
}
fn header_guard(frame: &Frame, r: BoxRect, s: f32) -> Vec<u8> {
    let h = (45.0 * s).round() as u32;
    (r.y..(r.y + h).min(frame.height))
        .flat_map(|y| (r.x..r.right()).flat_map(move |x| rgb(frame, x, y)))
        .collect()
}
fn count(
    frame: &Frame,
    x: u32,
    y: u32,
    w: u32,
    h: u32,
    predicate: impl Fn([u8; 3]) -> bool,
) -> usize {
    (y..(y + h).min(frame.height))
        .flat_map(|row| (x..(x + w).min(frame.width)).map(move |col| (col, row)))
        .filter(|&(col, row)| predicate(rgb(frame, col, row)))
        .count()
}
fn source(
    frame: &Frame,
    px: i32,
    py: i32,
    old: Option<&Inventory>,
    scale_hint: Option<f32>,
) -> Option<Inventory> {
    if let Some(old) = old {
        if old.rect.right() <= frame.width
            && old.rect.bottom() <= frame.height
            && old.rect.contains(px, py)
            && crate::inventory_pixels::same_header(&old.guard,&header_guard(frame,old.rect,old.scale),old.rect.w,old.tab)
        {
            return Some(old.clone());
        }
    }
    // Search only the bounded neighbourhood which can contain this source's
    // header. Its distance from any game/capture edge does not identify the
    // hovered item: a fitted description pair may end well beyond its window.
    if px < 0 || py < 0 || px as u32 >= frame.width || py as u32 >= frame.height {
        return None;
    }
    let search_scale = scale_hint.filter(|s| (0.65..=2.1).contains(s)).unwrap_or(2.1);
    let reach_x = (220.0 * search_scale).ceil() as u32;
    let reach_y = (300.0 * search_scale).ceil() as u32;
    let x0 = (px as u32).saturating_sub(reach_x);
    let x1 = ((px as u32) + reach_x).min(frame.width);
    let y0 = (py as u32).saturating_sub(reach_y);
    let y1 = (py as u32).min(frame.height);
    let w = x1 - x0;
    let h = y1 - y0;
    if w == 0 || h == 0 {
        return None;
    }
    let mut mask: Vec<u8> = (0..w * h)
        .map(|i| u8::from(pink(rgb(frame, x0 + i % w, y0 + i / w))))
        .collect();
    let mut candidates = Vec::new();
    let mut queue = Vec::new();
    for start in 0..mask.len() {
        if mask[start] == 0 {
            continue;
        }
        mask[start] = 0;
        queue.push(start);
        let (mut a, mut b, mut top, mut bottom, mut n) = (w, 0, h, 0, 0);
        while let Some(i) = queue.pop() {
            let x = i as u32 % w;
            let y = i as u32 / w;
            a = a.min(x);
            b = b.max(x + 1);
            top = top.min(y);
            bottom = bottom.max(y + 1);
            n += 1;
            for next in [
                x.checked_sub(1).map(|_| i - 1),
                (x + 1 < w).then_some(i + 1),
                y.checked_sub(1).map(|_| i - w as usize),
                (y + 1 < h).then_some(i + w as usize),
            ]
            .into_iter()
            .flatten()
            {
                if mask[next] != 0 {
                    mask[next] = 0;
                    queue.push(next)
                }
            }
        }
        let bw = b - a;
        let bh = bottom - top;
        if !(18..=62).contains(&bw) || !(11..=36).contains(&bh) || n * 3 < (bw * bh) as usize {
            continue;
        }
        // Fit the source controls themselves. A one-pixel HUD estimate error
        // must not shrink every later inventory column. Nearby common scales
        // absorb antialiased tab endpoints, with all controls checked below.
        let measured=(bw as f32/29.0+bh as f32/17.0)/2.0;
        let s=[1.0_f32,1.25,1.5,2.0].into_iter()
            .min_by(|a,b|(a-measured).abs().total_cmp(&(b-measured).abs()))
            .filter(|s|(s-measured).abs()<=s*0.045).unwrap_or(measured);
        if ((bw as f32) / (29.0 * s) - 1.0).abs() > 0.18 {
            continue;
        }
        for tab in [0_u32, 4] {
            let dx = ((6.0 + 33.0 * tab as f32) * s).round() as u32;
            let dy = (23.0 * s).round() as u32;
            if x0 + a < dx || y0 + top < dy {
                continue;
            }
            let r = BoxRect {
                x: x0 + a - dx,
                y: y0 + top - dy,
                w: (207.0 * s).round() as u32,
                h: (285.0 * s).round() as u32,
            };
            if r.right() > frame.width
                || r.bottom() > frame.height
                || !r.contains(px, py)
            {
                continue;
            }
            let at = |x: f32, y: f32| {
                rgb(
                    frame,
                    r.x + (x * s).round() as u32,
                    r.y + (y * s).round() as u32,
                )
            };
            if ![20.0, 80.0, 135.0].into_iter().all(|x| {
                let p = at(x, 4.0);
                p.iter().all(|v| *v >= 210)
                    && p.iter().max().unwrap() - p.iter().min().unwrap() < 25
            }) {
                continue;
            }
            let mut buttons = true;
            for (cx, blue) in [(168.0, false), (181.0, false), (194.0, true)] {
                let size = (8.0 * s).round().max(4.0) as u32;
                let hits = count(
                    frame,
                    r.x + ((cx - 4.0) * s).round() as u32,
                    r.y + (5.0 * s).round() as u32,
                    size,
                    (10.0 * s).round() as u32,
                    |p| {
                        if blue {
                            p[2] >= 140
                                && p[1] >= 100
                                && p[0] <= 150
                                && p[1].saturating_sub(p[0]) >= 40
                        } else {
                            p[0] >= 150
                                && p[0].saturating_sub(p[1]) >= 45
                                && p[0].saturating_sub(p[2]) >= 35
                        }
                    },
                );
                buttons &= hits >= ((8.0 * s * s).round() as usize).max(4);
            }
            if !buttons {
                continue;
            }
            if !(0..6).filter(|i| *i != tab).all(|i| {
                let p = at(9.0 + 33.0 * i as f32, 29.0);
                p.iter().max().unwrap() - p.iter().min().unwrap() < 35
            }) {
                continue;
            }
            let ink = count(
                frame,
                r.x + (7.0 * s).round() as u32,
                r.y + (6.0 * s).round() as u32,
                (125.0 * s).round() as u32,
                (11.0 * s).round() as u32,
                |p| p.iter().all(|v| *v < 100),
            );
            if ink < ((30.0 * s * s).round() as usize).max(12) {
                continue;
            }
            candidates.push(Inventory {
                rect: r,
                tab,
                scale: s,
                guard: header_guard(frame, r, s),
            });
        }
    }
    candidates.sort_by_key(|s| (s.rect.x, s.rect.y));
    candidates.dedup_by_key(|s| (s.rect.x, s.rect.y));
    if candidates.len() == 1 {
        candidates.pop()
    } else {
        None
    }
}

fn adjoining(a: Panel, b: Panel, s: f32) -> bool {
    a.rect.right() <= b.rect.x
        && b.rect.x - a.rect.right() <= (8.0 * s).ceil() as u32
        && a.rect.y.abs_diff(b.rect.y) <= (4.0 * s).ceil() as u32
        && a.rect.w as f32 / b.rect.w as f32 >= 0.7
        && a.rect.w as f32 / b.rect.w as f32 <= 1.4
}

fn paired(a: Panel, b: Panel, s: f32) -> bool {
    adjoining(a,b,s) && (a.cap || b.cap)
}

fn near_pair(a: Panel, b: Panel, x: i32, y: i32, s: f32) -> bool {
    let margin = (48.0 * s).ceil() as i64;
    i64::from(x) + margin >= i64::from(a.rect.x)
        && i64::from(x) <= i64::from(b.rect.right()) + margin
        && i64::from(y) + margin >= i64::from(a.rect.y.min(b.rect.y))
        && i64::from(y) <= i64::from(a.rect.bottom().max(b.rect.bottom())) + margin
        && !a.rect.contains(x,y) && !b.rect.contains(x,y)
}

/// Find only an adjoining native frame in the existing comparison family.
/// Width/top/rail probes are bounded by the visible panel, not screen edges,
/// item names or previously read popup identity. The cyan bullet is optional.
fn sibling(frame: &Frame, anchor: Panel, s: f32, before: bool) -> Option<Panel> {
    let ys = (anchor.rect.y + (26.0*s).round() as u32
        ..(anchor.rect.y + (96.0*s).round() as u32).min(frame.height))
        .step_by((6.0*s).round().max(3.0) as usize);
    let count=ys.clone().count();
    if count<8 {return None}
    let score=|x| ys.clone().filter(|&y| edge(frame,x,y,s,false)).count()*100/count;
    let min_width=(anchor.rect.w as f32*0.7).floor() as u32;
    let max_width=(anchor.rect.w as f32*1.4).ceil() as u32;
    let mut lefts=Vec::new();
    if before {
        let right_lo=anchor.rect.x.saturating_sub((11.0*s).ceil() as u32);
        let right_hi=anchor.rect.x.saturating_sub((3.0*s).round() as u32);
        for right in right_lo..=right_hi {
            if score(right)<65 {continue}
            for left in right.saturating_sub(max_width)..=right.saturating_sub(min_width) {
                if score(left)>=65 {lefts.push(left)}
            }
        }
    } else {
        let end=(anchor.rect.right()+(8.0*s).ceil() as u32).min(frame.width.saturating_sub(3));
        for left in anchor.rect.right()..=end {
            if score(left)>=65 {lefts.push(left)}
        }
    }
    lefts.sort_unstable();lefts.dedup();
    let expected=if before {anchor.rect.x.saturating_sub(anchor.rect.w+(3.0*s).round() as u32)}
        else {anchor.rect.right()+(3.0*s).round() as u32};
    lefts.sort_by_key(|x| x.abs_diff(expected));
    for left in lefts.into_iter().take(12) {
        let x0=left+(9.0*s).round() as u32;
        let y0=anchor.title.y+(6.0*s).ceil() as u32;
        let dot=Dot{x0,y0,x1:x0+(5.0*s).round() as u32,y1:y0+(5.0*s).round() as u32};
        let Some(mut candidate)=panel_from_header(frame,dot,s,false) else {continue};
        let (a,b)=if before {(candidate,anchor)} else {(anchor,candidate)};
        // Incomplete caps are still a two-body ambiguity. They cannot select
        // a positive role, but must not reopen nearest-comparison fallback.
        if !adjoining(a,b,s) {continue}
        // The independent current cap and corresponding title lane bound the
        // marker-free OCR. No comparison title or old item name is borrowed.
        candidate.title=BoxRect{x:candidate.rect.x+(17.0*s).round() as u32,
            y:anchor.title.y,w:candidate.rect.w.saturating_sub((24.0*s).round() as u32),
            h:anchor.title.h};
        return Some(candidate)
    }
    None
}

fn current_panels(frame: &Frame, markers: &[Dot], px: i32, py: i32, s: f32,exclude: &[BoxRect]) -> Option<Vec<Panel>> {
    let candidates: Vec<_> = markers.iter().filter(|d| {
        (d.x0 as i32-px).abs() as f32<=640.0*s
            && (d.y0 as i32-py).abs() as f32<=640.0*s
    }).filter(|&&d| title_marker(frame,d) && !exclude.iter().any(|r|
        r.x<d.x1&&r.right()>d.x0&&r.y<d.y1&&r.bottom()>d.y0)).take(25).copied().collect();
    if candidates.len()>24 {return None}
    let mut panels:Vec<_>=candidates.into_iter().filter_map(|d|
        crate::tooltip_frame::panel_with_exclusions(frame,d,s,true,exclude)).collect();
    panels.sort_by_key(|p|p.rect.x);
    panels.dedup_by(|a,b|a.rect.x.abs_diff(b.rect.x)<4&&a.rect.y.abs_diff(b.rect.y)<4);
    if panels.len()==2 && !paired(panels[0],panels[1],s) {
        for i in 0..2 {
            if let Some(fitted)=crate::tooltip_frame::fit_neighbour(frame,panels[i],panels[1-i],s) {
                panels[i]=fitted;
            }
        }
    }
    if panels.len()==1 {
        let anchor=panels[0];
        for before in [true,false] {
            if let Some(other)=sibling(frame,anchor,s,before) {panels.push(other)}
        }
        panels.sort_by_key(|p|p.rect.x);
        panels.dedup_by(|a,b|a.rect.x.abs_diff(b.rect.x)<4&&a.rect.y.abs_diff(b.rect.y)<4);
    }
    Some(panels)
}

fn title_ink_guard(frame: &Frame, rect: BoxRect) -> Vec<u8> {
    // Retain the captured title's bright ink, not its translucent background:
    // moving scenery cannot make an unchanged equipped item a new source.
    (rect.y..rect.bottom()).flat_map(|y| (rect.x..rect.right()).map(move |x| {
        u8::from(title_light(rgb(frame, x, y)).is_some_and(|v| v >= 150))
    })).collect()
}

fn title_marker(frame: &Frame, dot: Dot) -> bool {
    if dot.x0 < 5 || dot.y0 == 0 {
        return false;
    }
    let mid = (dot.y0 + dot.y1) / 2;
    (dot.x0 - 5..dot.x0 - 2).all(|x| {
        (mid - 1..=mid + 1).all(|y| {
            if y >= frame.height {
                return false;
            }
            let p = rgb(frame, x, y);
            u32::from(p[0]) * 30 + u32::from(p[1]) * 59 + u32::from(p[2]) * 11 < 13000
                && p[2] >= p[0]
        })
    })
}

fn panel_still_present(frame: &Frame, panel: Panel, s: f32) -> bool {
    let r = panel.rect;
    if r.right() > frame.width || r.bottom() > frame.height {
        return false;
    }
    let right = r.right().saturating_sub((3.0 * s).ceil() as u32);
    let ys = (r.y + (24.0 * s).round() as u32..r.bottom().saturating_sub(6))
        .step_by((10.0 * s).round().max(6.0) as usize);
    let total = ys.clone().count();
    if total < 5 || ys.clone().filter(|&y| edge(frame, r.x, y, s, false)).count() * 10 < total * 6
        || ys.filter(|&y| edge(frame, right, y, s, false)).count() * 10 < total * 6 {
        return false;
    }
    let (mut dark, mut total) = (0, 0);
    for y in (r.y + 24..r.bottom().saturating_sub(6)).step_by(17) {
        for x in (r.x + 6..right.saturating_sub(5)).step_by(17) {
            total += 1;
            dark += usize::from(rgb(frame, x, y).iter().all(|v| *v < 185));
        }
    }
    total > 0 && dark * 10 >= total * 6
}

impl Selector {
    #[cfg(test)]
    pub fn select(
        &mut self,
        capture: &ItemCapture,
        markers: &[Dot],
        scale_hint: Option<f32>,
    ) -> Association {
        self.select_with_exclusions(capture,markers,scale_hint,&[])
    }

    pub fn select_with_exclusions(&mut self,capture: &ItemCapture,markers: &[Dot],
        scale_hint: Option<f32>,exclude: &[BoxRect]) -> Association {
        let (px, py) = (
            capture.pointer.x - capture.origin.x,
            capture.pointer.y - capture.origin.y,
        );
        let frame = &capture.frame;
        let scope = (capture.origin.x, capture.origin.y, frame.width, frame.height);
        let found = source(frame, px, py, self.inventory.as_ref(), scale_hint);
        self.inventory = found.clone();
        let Some(inv) = found else {
            // A temporarily covered header must not make the second identical
            // frame fall back to the comparison nearest the pointer. Retain one
            // bounded source until proof returns or this pointer/capture leaves
            // its scope; no stale source can choose an item.
            let mut rejected = self.bound_source.is_some_and(|(rect, previous)| {
                previous == scope && rect.contains(px, py)
            });
            // A cold reader has no old binding to protect it. Two independently
            // framed adjoining descriptions are still a comparison ambiguity:
            // losing an inventory header cannot make the nearest equipped title
            // an ordinary single-item observation.
            if !rejected && px>=0 && py>=0 && px<frame.width as i32 && py<frame.height as i32 {
                let scales=scale_hint.filter(|s|(0.65..=2.1).contains(s))
                    .map(|s|vec![s]).unwrap_or_else(||vec![1.0,1.25,1.5,2.0]);
                for s in scales {
                    let Some(panels)=current_panels(frame,markers,px,py,s,exclude) else {rejected=true;break};
                    if panels.windows(2).any(|p|adjoining(p[0],p[1],s)&&near_pair(p[0],p[1],px,py,s)) {
                        rejected=true;break
                    }
                    if !panels.is_empty() {break}
                }
            }
            if !rejected {
                self.bound_source = None;
                self.pair = None;
            }
            return Association {
                panel: None,
                primary_header: None,
                rejected,
                metadata: json!({"state":if rejected {"rejected"} else {"normal"},"token":null,"guards":[]}),
            };
        };
        let s = inv.scale;
        if self.pair.as_ref().is_some_and(|pair| pair.scope != scope || pair.source != inv.rect) {
            self.pair = None;
        }
        let gx = inv.rect.x + (7.0 * s).round() as u32;
        let gy = inv.rect.y + (47.0 * s).round() as u32;
        let pitch = 36.0 * s;
        let (dx, dy) = (px - gx as i32, py - gy as i32);
        let valid = dx >= 0
            && dy >= 0
            && (dx as f32) < pitch * 5.0
            && (dy as f32) < pitch * 6.0
            && (dx as f32) % pitch < 32.0 * s
            && (dy as f32) % pitch < 32.0 * s;
        let slot = if valid {
            Some(BoxRect {
                x: gx + ((dx as f32 / pitch).floor() * pitch).round() as u32,
                y: gy + ((dy as f32 / pitch).floor() * pitch).round() as u32,
                w: (32.0 * s).round() as u32,
                h: (32.0 * s).round() as u32,
            })
        } else {
            None
        };
        let context = format!(
            "{}:{}:{}:{}:{}:{}:{}:{}:{}",
            capture.origin.x,
            capture.origin.y,
            frame.width,
            frame.height,
            inv.rect.x,
            inv.rect.y,
            inv.tab,
            slot.map(|r| r.x).unwrap_or(0),
            slot.map(|r| r.y).unwrap_or(0)
        );
        let header = BoxRect {
            h: (45.0 * s).round() as u32,
            ..inv.rect
        };
        let mut metadata = json!({"state":"normal","token":context,"source":inv.rect.global(capture),"slot":slot.map(|r|r.global(capture)),"guards":[header.global(capture)]});
        self.bound_source = Some((inv.rect, scope));
        if !valid {
            metadata["state"] = json!("rejected");
            return Association {
                panel: None,
                primary_header: None,
                rejected: true,
                metadata,
            };
        }
        let Some(panels)=current_panels(frame,markers,px,py,s,exclude) else {
            metadata["state"] = json!("rejected");
            return Association {
                panel: None,
                primary_header: None,
                rejected: true,
                metadata,
            };
        };
        let mut chosen = None;
        if panels.len() < 2 {
            // A known pair can briefly lose one cyan marker while both native
            // frames remain. That is not proof of an ordinary single popup:
            // nearest-marker fallback could then price the equipped comparison.
            if self.pair.as_ref().is_some_and(|pair| {
                let comparison = pair.panels[1];
                pair.panels.into_iter().all(|panel| panel_still_present(frame, panel, pair.scale))
                    || (panel_still_present(frame, comparison, pair.scale)
                        && title_ink_guard(frame, comparison.title) == pair.comparison_ink)
            }) {
                metadata["state"] = json!("rejected");
                return Association { panel: None, primary_header: None, rejected: true, metadata };
            }
            self.pair = None;
            if let Some(single)=panels.first().filter(|p|p.cap&&p.marker) {
                let margin=(48.0*s).ceil() as i64;
                let near=slot.is_some_and(|slot| {
                    i64::from(single.rect.x)<=i64::from(slot.right())+margin
                        &&i64::from(single.rect.right())+margin>=i64::from(slot.x)
                        &&i64::from(single.rect.y)<=i64::from(slot.bottom())+margin
                        &&i64::from(single.rect.bottom())+margin>=i64::from(slot.y)
                });
                if near&&!single.rect.contains(px,py) {chosen=Some(single.rect)}
            }
            if chosen.is_none() {
                self.bound_source=None;
                return Association{panel:None,primary_header:None,rejected:false,metadata}
            }
        }
        if panels.len() == 2 {
            let (a, b) = (panels[0], panels[1]);
            // This proven layout family always places the hovered item's
            // primary description on the left and the equipped comparison on
            // the right. Bind it to the actual grid cell, not to a screen edge
            // or whichever marker happens to be nearest. The envelope must be
            // adjacent to that cell, so an unrelated clicked pair cannot win.
            let margin = (48.0 * s).ceil() as i64;
            let near_source = slot.is_some_and(|slot| {
                i64::from(a.rect.x) <= i64::from(slot.right()) + margin
                    && i64::from(b.rect.right()) + margin >= i64::from(slot.x)
                    && i64::from(a.rect.y) <= i64::from(slot.bottom()) + margin
                    && i64::from(a.rect.bottom().max(b.rect.bottom())) + margin >= i64::from(slot.y)
            });
            if paired(a,b,s) && near_source && (a.marker || a.cap)
                    && !panels.iter().any(|p| p.rect.contains(px, py)) {
                chosen = Some(a.rect);
                self.pair = Some(PairBinding { source: inv.rect, scope, panels: [a, b],
                    comparison_ink: title_ink_guard(frame, b.title), scale: s });
            }
        }
        let rejected = chosen.is_none();
        metadata["state"] = json!(if rejected {
            "rejected"
        } else {
            "inventory-primary"
        });
        if let Some(rect) = chosen {
            let single=panels.len()==1;
            metadata["version"] = json!(3);
            metadata["sourceKind"] = json!("inventory");
            metadata["sourceTab"] = json!(inv.tab);
            metadata["layout"] = json!(if single {"single"} else {"primary-left"});
            metadata["panel"] = rect.global(capture);
            metadata["comparison"] = if single {Value::Null} else {panels[1].rect.global(capture)};
            metadata["pointer"] = json!({"x":capture.pointer.x,"y":capture.pointer.y});
            // The frontend compares the cell outside the union of old/new
            // cursor footprints. Exact whole-cell hashes would flicker merely
            // because a captured hand moves within an otherwise stable slot.
            let inset = (6.0 * s).ceil() as u32;
            let cursor_x = (px as u32).saturating_sub(inset);
            // The animated hand has a black outline seven pixels above the
            // hotspot. Include that top scanline while keeping the old bottom
            // bound; otherwise a stationary hand invalidates the item cell.
            let top_inset = (7.0 * s).ceil() as u32;
            let cursor_y = (py as u32).saturating_sub(top_inset);
            let cursor_height = (36.0 * s).ceil() as u32 + top_inset - inset;
            metadata["cursor"] = BoxRect {
                x: cursor_x,
                y: cursor_y,
                w: (32.0 * s).ceil().min((frame.width - cursor_x) as f32) as u32,
                h: cursor_height.min(frame.height - cursor_y),
            }.global(capture);
            // The source header/cell stay exact. Translucent frame rails are
            // verified structurally by the frontend, never byte-hashed against
            // moving scenery. The canonical title retains its own ink proof.
            metadata["frameCaps"]=json!(panels.iter().map(|p|p.cap).collect::<Vec<_>>());
        }
        Association {
            panel: chosen,
            primary_header: chosen.and_then(|_|panels.first().filter(|p|!p.marker).map(|p|p.title)),
            rejected,
            metadata,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use minerva_core::ScreenPoint;

    fn paint(f: &mut Frame, x: u32, y: u32, w: u32, h: u32, p: [u8; 3]) {
        assert!(x + w <= f.width && y + h <= f.height, "fixture paint outside captured pixels");
        for yy in y..y + h {
            for xx in x..x + w {
                let at = ((yy * f.width + xx) * 4) as usize;
                f.rgba[at..at + 3].copy_from_slice(&p)
            }
        }
    }
    fn fixture(tab: u32, gap: u32) -> (ItemCapture, Vec<Dot>, BoxRect) {
        fixture_at(tab, gap, 1500, 900, 1293, 90, 1024, 180)
    }
    fn fixture_at(tab: u32, gap: u32, width: u32, height: u32,
                  inventory_x: u32, inventory_y: u32, primary_x: u32, primary_y: u32)
        -> (ItemCapture, Vec<Dot>, BoxRect) {
        let mut f = Frame {
            width,
            height,
            rgba: [20, 35, 20, 255].repeat((width * height) as usize),
            at_ms: 1000,
        };
        let inv = BoxRect {
            x: inventory_x,
            y: inventory_y,
            w: 207,
            h: 285,
        };
        paint(&mut f, inv.x, inv.y, inv.w, inv.h, [245, 246, 247]);
        paint(&mut f, inv.x + 4, inv.y + 2, 199, 17, [255, 255, 255]);
        for x in (inv.x + 8..inv.x + 128).step_by(6) {
            paint(&mut f, x, inv.y + 7, 2, 6, [0, 0, 0]);
        }
        for (cx, colour) in [
            (168, [220, 85, 68]),
            (181, [220, 85, 68]),
            (194, [51, 153, 204]),
        ] {
            paint(&mut f, inv.x + cx - 4, inv.y + 5, 8, 10, colour);
        }
        for i in 0..6 {
            paint(
                &mut f,
                inv.x + 6 + 33 * i,
                inv.y + 23,
                29,
                17,
                if i == tab {
                    [234, 101, 129]
                } else {
                    [180, 180, 180]
                },
            );
        }
        let b = BoxRect {
            x: primary_x + gap + 236,
            y: primary_y,
            w: 236,
            h: 240,
        };
        let a = BoxRect {
            x: b.x - gap - 236,
            y: primary_y,
            w: 236,
            h: 270,
        };
        let mut dots = Vec::new();
        for r in [a, b] {
            paint(&mut f, r.x, r.y, r.w, r.h, [30, 30, 70]);
            paint(&mut f, r.x + 1, r.y, 1, r.h, [190, 190, 205]);
            paint(&mut f, r.right() - 2, r.y, 1, r.h, [190, 190, 205]);
            paint(&mut f, r.x, r.y + 1, r.w, 1, [190, 190, 205]);
            let d = Dot {
                x0: r.x + 9,
                y0: r.y + 15,
                x1: r.x + 14,
                y1: r.y + 20,
            };
            for y in d.y0..d.y1 {
                for x in d.x0..d.x1 {
                    if (x as i32 - (d.x0 + 2) as i32).abs() + (y as i32 - (d.y0 + 2) as i32).abs()
                        <= 2
                    {
                        paint(&mut f, x, y, 1, 1, [85, 204, 255]);
                    }
                }
            }
            for x in (d.x1 + 3..d.x1 + 75).step_by(5) {
                paint(&mut f, x, r.y + 12, 2, 12, [240, 240, 240]);
            }
            dots.push(d);
        }
        (
            ItemCapture {
                frame: f,
                origin: ScreenPoint { x: 1700, y: -200 },
                pointer: ScreenPoint {
                    x: 1700 + inventory_x as i32 + 85,
                    y: -200 + inventory_y as i32 + 62,
                },
            },
            dots,
            a,
        )
    }

    #[test]
    fn source_slot_and_horizontal_pair_choose_primary_before_ocr() {
        for tab in [0, 4] {
            let (capture, dots, expected) = fixture(tab, 3);
            let mut selector = Selector::default();
            let result = selector.select(&capture, &dots, None);
            assert!(!result.rejected);
            assert_eq!(result.panel, Some(expected));
            assert_eq!(result.metadata["state"], "inventory-primary");
            assert_eq!(result.metadata["panel"]["x"], expected.x + 1700);
            assert_eq!(result.metadata["source"]["y"], -110);
            assert_eq!(result.metadata["slot"]["width"], 32);
            assert_eq!(result.metadata["guards"].as_array().unwrap().len(), 1);
            assert_eq!(result.metadata["version"], 3);
            assert_eq!(result.metadata["frameCaps"],json!([true,true]));
            assert_eq!(result.metadata["layout"], "primary-left");
            assert_eq!(result.metadata["sourceKind"], "inventory");
            assert_eq!(result.metadata["comparison"]["x"], 1700 + 1263);
            assert_eq!(result.metadata["pointer"]["x"], capture.pointer.x);
            assert_eq!(
                selector.select(&capture, &dots, None).metadata["token"],
                result.metadata["token"]
            );
        }
    }

    #[test]
    fn inset_sources_and_pairs_at_multiple_edges_keep_the_hovered_primary() {
        // The first case has the inventory 263px inside the right boundary;
        // neither its right edge nor the comparison's right edge are equal.
        // The other cases exercise left/top/bottom placement and a small game.
        for (width, height, ix, iy, ax, ay) in [
            (1500, 900, 1030, 90, 1024, 180),
            (900, 600, 0, 0, 100, 90),
            (900, 900, 600, 580, 200, 330),
            (800, 600, 500, 30, 320, 120),
        ] {
            let (capture, dots, expected) = fixture_at(0, 3, width, height, ix, iy, ax, ay);
            let result = Selector::default().select(&capture, &dots, Some(1.0));
            assert_eq!(result.panel, Some(expected), "{}", result.metadata);
            assert_eq!(result.metadata["state"], "inventory-primary");
            // Unequal description heights are expected equipment comparisons.
            assert_ne!(result.metadata["panel"]["height"], result.metadata["comparison"]["height"]);
        }
    }

    #[test]
    fn a_real_inventory_does_not_claim_a_remote_clicked_pair() {
        let (capture, dots, _) = fixture_at(0, 3, 1500, 900, 100, 90, 500, 180);
        let result = Selector::default().select(&capture, &dots, Some(1.0));
        assert!(result.rejected);
        assert!(result.panel.is_none());
    }

    #[test]
    fn changed_cell_pixels_are_returned_as_fresh_source_proofs_not_old_item_names() {
        let (mut capture, dots, expected) = fixture_at(0, 3, 1500, 900, 1030, 90, 1024, 180);
        let mut selector = Selector::default();
        let initial = selector.select(&capture, &dots, Some(1.0));
        paint(&mut capture.frame, 1030 + 79, 90 + 47, 32, 32, [80, 10, 30]);
        let current = selector.select(&capture, &dots, Some(1.0));
        assert_eq!(current.panel, Some(expected));
        assert_eq!(initial.metadata["slot"], current.metadata["slot"]);
        // There is intentionally no retained OCR identity in this selector.
        // The frontend compares these same-frame cell pixels independently of
        // the primary name and the unchanged equipped comparison.
        assert!(current.metadata.get("name").is_none());
        assert_eq!(current.metadata["cursor"]["width"], 32);
        assert_eq!(current.metadata["cursor"]["height"], 37);
        assert_eq!(current.metadata["cursor"]["y"], capture.pointer.y - 7);
    }

    #[test]
    fn unsafe_cell_gutter_and_ambiguous_pairs_are_rejected() {
        let (mut capture, dots, _) = fixture(0, 3);
        capture.pointer.y = capture.origin.y + 225; // Real native comparison covers this cell.
        let result = Selector::default().select(&capture, &dots, None);
        assert!(result.rejected);
        assert!(result.panel.is_none());
        capture.pointer.y = capture.origin.y + 152;
        capture.pointer.x = capture.origin.x + 1293 + 7 + 33; // Four-pixel grid gutter.
        assert!(Selector::default().select(&capture, &dots, None).rejected);
        // Keep both complete panels inside the capture. The 18px gap extends
        // the comparison beyond fixture()'s 1500px edge, which is a different
        // (single visible title) case, not evidence of a nonadjacent pair.
        let (capture, dots, _) = fixture_at(0, 18, 1540, 900, 1293, 90, 1024, 180);
        assert!(Selector::default().select(&capture, &dots, None).rejected);
    }

    #[test]
    fn nearby_inventory_does_not_override_linked_or_single_equipped_titles() {
        let (mut capture, dots, primary) = fixture(0, 3);
        capture.pointer.x = capture.origin.x + 700;
        let result = Selector::default().select(&capture, &dots, None);
        assert!(!result.rejected);
        assert!(result.panel.is_none());
        capture.pointer.x = capture.origin.x + 1378;
        // A genuinely departed primary is a single-panel case. Merely hiding
        // its marker while its frame remains is now independently recognized.
        paint(&mut capture.frame,primary.x,primary.y,primary.w,primary.h,[20,35,20]);
        let result = Selector::default().select(&capture, &dots[1..], None);
        assert!(!result.rejected);
        assert!(result.panel.is_some());
        assert_eq!(result.metadata["layout"],"single");
        paint(&mut capture.frame, 1293, 90, 207, 45, [245, 246, 247]);
        let result = Selector::default().select(&capture, &dots[1..], None);
        assert!(!result.rejected);
        assert!(result.panel.is_none());
    }

    #[test]
    fn lost_source_and_slot_changes_invalidate_context() {
        let (mut capture, dots, _) = fixture(0, 3);
        let mut selector = Selector::default();
        let first = selector.select(&capture, &dots, None);
        assert!(first.panel.is_some());
        capture.pointer.x += 36;
        let second = selector.select(&capture, &dots, None);
        assert!(second.panel.is_some());
        assert_ne!(first.metadata["token"], second.metadata["token"]);
        paint(&mut capture.frame, 1293, 90, 207, 45, [245, 246, 247]);
        let rejected = selector.select(&capture, &dots, None);
        assert!(rejected.rejected);
        assert!(rejected.metadata["token"].is_null());
        for _ in 0..3 {
            assert!(selector.select(&capture, &dots, None).rejected);
        }
        let (recovered, fresh_dots, _) = fixture(0, 3);
        assert!(selector.select(&recovered, &fresh_dots, None).panel.is_some());
        capture.pointer.x = capture.origin.x + 700;
        assert!(!selector.select(&capture, &dots, None).rejected);
    }

    #[test]
    fn a_new_capture_rechecks_current_pair_ambiguity_without_leaking_old_denials() {
        let (mut capture, dots, primary) = fixture(0, 3);
        let mut selector = Selector::default();
        assert!(selector.select(&capture, &dots, None).panel.is_some());
        paint(&mut capture.frame, 1293, 90, 207, 45, [245, 246, 247]);
        assert!(selector.select(&capture, &dots, None).rejected);
        capture.origin.x += 100;
        capture.pointer.x += 100;
        // The new scope independently contains the same ambiguous two panels.
        assert!(selector.select(&capture, &dots, None).rejected);
        paint(&mut capture.frame,primary.x,primary.y,primary.w,primary.h,[20,35,20]);
        assert!(!selector.select(&capture, &dots[1..], None).rejected);
    }

    #[test]
    fn current_primary_frame_recovers_a_missing_marker_without_borrowing_comparison_identity() {
        let (mut capture, dots, expected) = fixture(0, 3);
        let mut selector = Selector::default();
        assert_eq!(selector.select(&capture, &dots, None).panel, Some(expected));
        let primary = dots[0];
        paint(&mut capture.frame, primary.x0, primary.y0,
            primary.x1 - primary.x0, primary.y1 - primary.y0, [30, 30, 70]);
        for _ in 0..3 {
            let held = selector.select(&capture, &dots[1..], None);
            assert!(!held.rejected);
            assert_eq!(held.metadata["state"], "inventory-primary");
            assert_eq!(held.panel,Some(expected));
            assert!(held.primary_header.is_some());
        }
        // Losing the upper cap as well does not make the still-framed dark
        // primary body an ordinary single comparison description.
        paint(&mut capture.frame, expected.x, expected.y, expected.w, 3, [20, 35, 20]);
        assert!(selector.select(&capture, &dots[1..], None).rejected);
        let (mut restored, fresh_dots, _) = fixture(0, 3);
        restored.pointer.x += 36;
        assert_eq!(selector.select(&restored, &fresh_dots, None).panel, Some(expected));
    }

    #[test]
    fn cold_marker_loss_recovers_only_the_independently_framed_primary() {
        for fraction in [false,true] {
            let (mut capture,dots,expected)=fixture(0,3);
            let primary=dots[0];
            let width=if fraction {2} else {primary.x1-primary.x0};
            paint(&mut capture.frame,primary.x0,primary.y0,width,primary.y1-primary.y0,[30,30,70]);
            let (_,markers)=crate::tooltip_surface::prepare(&capture.frame);
            let result=Selector::default().select(&capture,&markers,Some(1.0));
            assert_eq!(result.panel,Some(expected),"{}",result.metadata);
            assert!(!result.rejected);
            assert_eq!(result.metadata["state"],"inventory-primary");
            assert!(result.metadata.get("name").is_none());
            if !fraction {assert!(result.primary_header.is_some())}
        }
    }

    #[test]
    fn a_cold_obscured_inventory_header_cannot_authorize_the_equipped_comparison() {
        for hide_marker in [false,true] {
            let (mut capture,dots,_)=fixture(0,3);
            // Cover only the selected tab; both full native description frames
            // and all their actual title letters remain present.
            paint(&mut capture.frame,1293+4,90+21,33,21,[40,40,70]);
            if hide_marker {
                let d=dots[0];paint(&mut capture.frame,d.x0,d.y0,d.x1-d.x0,d.y1-d.y0,[30,30,70]);
            }
            let markers=if hide_marker {&dots[1..]} else {&dots[..]};
            let result=Selector::default().select(&capture,markers,Some(1.0));
            assert!(result.rejected,"{}",result.metadata);
            assert!(result.panel.is_none());
            assert_eq!(result.metadata["state"],"rejected");
        }
    }

    #[test]
    fn missing_marker_and_caps_keep_two_body_ambiguity_separate_from_positive_role() {
        for primary_cap in [false,true] {
            let (mut capture,dots,expected)=fixture(0,3);
            let d=dots[0];paint(&mut capture.frame,d.x0,d.y0,d.x1-d.x0,d.y1-d.y0,[30,30,70]);
            paint(&mut capture.frame,1263,180,236,3,[30,30,70]);
            if !primary_cap {paint(&mut capture.frame,expected.x,expected.y,expected.w,3,[30,30,70]);}
            let result=Selector::default().select(&capture,&dots[1..],Some(1.0));
            assert_eq!(result.rejected,!primary_cap,"{}",result.metadata);
            assert_eq!(result.panel,if primary_cap {Some(expected)} else {None});
            if primary_cap {assert!(result.primary_header.is_some())}
        }
    }

    #[test]
    fn comparison_departure_releases_primary_but_primary_departure_cannot_authorize_comparison() {
        for removed in [0, 1] {
            let (mut capture, dots, primary) = fixture(0, 3);
            let mut selector = Selector::default();
            assert!(selector.select(&capture, &dots, None).panel.is_some());
            let gone = if removed == 0 { primary } else { BoxRect { x: 1263, y: 180, w: 236, h: 240 } };
            paint(&mut capture.frame, gone.x, gone.y, gone.w, gone.h, [20, 35, 20]);
            let remaining = if removed == 0 { &dots[1..] } else { &dots[..1] };
            let single = selector.select(&capture, remaining, None);
            assert_eq!(single.rejected, removed == 0);
            assert!(single.panel.is_none());
            assert_eq!(single.metadata["state"], if removed == 0 { "rejected" } else { "normal" });
            if removed == 0 {
                for _ in 0..3 {
                    assert!(selector.select(&capture, remaining, None).rejected);
                }
                // The same denial does not leak into an independent equipped
                // or linked-item read outside the inventory source.
                capture.pointer.x = capture.origin.x + 700;
                assert!(!selector.select(&capture, remaining, None).rejected);
            }
        }
    }

    #[test]
    fn genuinely_new_single_title_does_not_inherit_the_old_comparison_denial() {
        let (mut capture, dots, primary) = fixture(0, 3);
        let mut selector = Selector::default();
        assert!(selector.select(&capture, &dots, None).panel.is_some());
        paint(&mut capture.frame, primary.x, primary.y, primary.w, primary.h, [20, 35, 20]);
        let remaining = &dots[1..];
        assert!(selector.select(&capture, remaining, None).rejected);
        // Fresh independently visible title pixels establish a new ordinary
        // single description, rather than the unchanged equipped comparison.
        let x = 1263 + 17;
        paint(&mut capture.frame, x, 192, 75, 12, [30, 30, 70]);
        paint(&mut capture.frame, x, 192, 5, 12, [240, 240, 240]);
        let single = selector.select(&capture, remaining, None);
        assert!(!single.rejected);
        assert_eq!(single.metadata["state"], "inventory-primary");
    }

    #[test]
    fn pointers_outside_the_captured_image_do_not_enter_source_search() {
        let (mut capture, dots, _) = fixture(0, 3);
        for (x, y) in [(3000, 200), (200, 2000), (-1, 150)] {
            capture.pointer.x = capture.origin.x + x;
            capture.pointer.y = capture.origin.y + y;
            let result = Selector::default().select(&capture, &dots, None);
            assert!(!result.rejected);
            assert!(result.panel.is_none());
        }
    }

    #[test]
    fn interior_inventory_rails_do_not_truncate_translucent_description_frames() {
        let (mut capture,dots,expected)=fixture(0,3);
        for x in [expected.x+170,1263+160] {
            paint(&mut capture.frame,x,184,3,224,[45,45,80]);
            paint(&mut capture.frame,x+1,184,1,224,[95,95,130]);
        }
        let result=Selector::default().select(&capture,&dots,Some(1.0));
        assert_eq!(result.panel,Some(expected),"{}",result.metadata);
        assert_eq!(result.metadata["comparison"]["width"],236);
    }

    #[test]
    fn owner_line_above_the_primary_title_keeps_the_physical_top_and_item_role() {
        let (mut capture,mut dots,expected)=fixture(0,3);
        paint(&mut capture.frame,expected.x+4,expected.y+4,expected.w-8,54,[30,30,70]);
        paint(&mut capture.frame,expected.x+70,expected.y+12,60,7,[225,180,50]);
        let d=&mut dots[0];d.y0+=26;d.y1+=26;
        paint(&mut capture.frame,d.x0,d.y0,5,5,[85,204,255]);
        paint(&mut capture.frame,d.x1+3,d.y0-3,72,12,[240,240,240]);
        let result=Selector::default().select(&capture,&dots,Some(1.0));
        assert_eq!(result.panel,Some(expected),"{}",result.metadata);
        assert_eq!(result.metadata["panel"]["y"],result.metadata["comparison"]["y"]);
    }

    #[test]
    fn dark_scenery_can_erase_part_of_the_cap_but_not_its_closed_corners() {
        let (mut capture,dots,expected)=fixture(0,3);
        paint(&mut capture.frame,expected.x+80,expected.y,105,3,[30,30,70]);
        let result=Selector::default().select(&capture,&dots,Some(1.0));
        assert_eq!(result.panel,Some(expected),"{}",result.metadata);
        assert_eq!(result.metadata["comparison"]["width"],236);
    }

    #[test]
    fn a_single_blended_pixel_near_each_cap_corner_keeps_the_current_panel() {
        let (mut capture,dots,expected)=fixture(0,3);
        for x in [expected.x+5,expected.right()-8] {
            paint(&mut capture.frame,x,expected.y+1,1,1,[30,30,70]);
        }
        let result=Selector::default().select(&capture,&dots,Some(1.0));
        assert_eq!(result.panel,Some(expected),"{}",result.metadata);
        assert_eq!(result.metadata["frameCaps"],json!([true,true]));
    }

    #[test]
    fn a_short_header_rail_cannot_replace_the_complete_side_two_pixels_away() {
        let (mut capture,dots,expected)=fixture(0,3);
        paint(&mut capture.frame,expected.right()-4,expected.y+3,1,108,[190,190,205]);
        let result=Selector::default().select(&capture,&dots,Some(1.0));
        assert_eq!(result.panel,Some(expected),"{}",result.metadata);
        assert_eq!(result.metadata["panel"]["width"],236);
    }

    #[test]
    fn owned_price_labels_are_unknown_and_still_need_exposed_native_rims() {
        let (mut capture,dots,expected)=fixture(0,3);
        let hidden:Vec<_>=[45,90,135,180,225].into_iter().map(|dy|
            BoxRect{x:expected.x-12,y:expected.y+dy,w:36,h:35}).collect();
        for r in &hidden {paint(&mut capture.frame,r.x,r.y,r.w,r.h,[23,28,38])}
        let result=Selector::default().select_with_exclusions(&capture,&dots,Some(1.0),&hidden);
        assert_eq!(result.panel,Some(expected),"{}",result.metadata);
        let all=[BoxRect{x:expected.x-3,y:expected.y,w:12,h:expected.h}];
        let missing=crate::tooltip_frame::panel_with_exclusions(&capture.frame,dots[0],1.0,true,&all);
        assert!(!missing.is_some_and(|p|p.cap));
    }

    #[test]
    fn an_enclosing_common_rim_is_split_at_the_independently_framed_comparison() {
        let (mut capture,dots,expected)=fixture(0,3);
        paint(&mut capture.frame,expected.right()-12,expected.y,10,3,[30,30,70]);
        let result=Selector::default().select(&capture,&dots,Some(1.0));
        assert_eq!(result.panel,Some(expected),"{}",result.metadata);
        assert_eq!(result.metadata["comparison"]["width"],236);
        assert_eq!(result.metadata["frameCaps"],json!([false,true]));
    }

    #[test]
    fn a_single_description_binds_to_the_source_cell_and_ignores_a_noisy_hud_scale() {
        let (mut capture,dots,primary)=fixture(0,3);
        paint(&mut capture.frame,primary.x,primary.y,primary.w,primary.h,[20,35,20]);
        let single=BoxRect{x:1263,y:180,w:236,h:240};
        // Keep the source header intact; only the comparison body disappears.
        for hint in [None,Some(35.0/36.0),Some(1.0)] {
            let result=Selector::default().select(&capture,&dots[1..],hint);
            assert_eq!(result.panel,Some(single),"{}",result.metadata);
            assert_eq!(result.metadata["source"]["width"],207);
            assert_eq!(result.metadata["version"],3);
            assert_eq!(result.metadata["layout"],"single");
            assert!(result.metadata["comparison"].is_null());
        }
    }

    #[test]
    fn a_pair_without_caps_is_not_bound_and_coloured_titles_keep_their_role() {
        let (mut capture, dots, expected) = fixture(0, 3);
        for d in &dots {
            paint(
                &mut capture.frame,
                d.x1 + 3,
                d.y0 - 3,
                72,
                12,
                [255, 153, 0],
            );
        }
        assert_eq!(
            Selector::default().select(&capture, &dots, None).panel,
            Some(expected)
        );
        for x in [expected.x, 1263] {
            paint(&mut capture.frame, x, 180, 236, 3, [30, 30, 70]);
        }
        let result = Selector::default().select(&capture, &dots, None);
        assert!(result.rejected);
        assert!(result.panel.is_none());
    }

    #[test]
    fn association_uses_frame_pixels_with_fractional_dpi_and_nonzero_origin() {
        let (capture, _, _) = fixture(0, 3);
        let original = image::RgbaImage::from_raw(
            capture.frame.width,
            capture.frame.height,
            capture.frame.rgba.clone(),
        )
        .unwrap();
        for scale in [1.0_f32, 1.25, 1.5, 2.0] {
            let resized = image::imageops::resize(
                &original,
                (original.width() as f32 * scale).round() as u32,
                (original.height() as f32 * scale).round() as u32,
                image::imageops::FilterType::Triangle,
            );
            let scaled = ItemCapture {
                frame: Frame {
                    width: resized.width(),
                    height: resized.height(),
                    rgba: resized.into_raw(),
                    at_ms: 2000,
                },
                origin: capture.origin,
                pointer: ScreenPoint {
                    x: capture.origin.x
                        + ((capture.pointer.x - capture.origin.x) as f32 * scale).round() as i32,
                    y: capture.origin.y
                        + ((capture.pointer.y - capture.origin.y) as f32 * scale).round() as i32,
                },
            };
            let (_, dots) = crate::tooltip_surface::prepare(&scaled.frame);
            let result = Selector::default().select(&scaled, &dots, Some(scale));
            if result.panel.is_none() {
                eprintln!(
                    "scale={scale}, candidates={:?}",
                    dots.iter()
                        .map(|d| (
                            (d.x0, d.y0, d.x1, d.y1),
                            title_marker(&scaled.frame, *d),
                            panel_from_header(&scaled.frame, *d, scale,true).map(|p| p.rect)
                        ))
                        .collect::<Vec<_>>()
                );
            }
            assert!(result.panel.is_some(), "scale {scale}: {}", result.metadata);
            let slot = &result.metadata["slot"];
            assert!(
                (slot["x"].as_i64().unwrap() - (1700 + (1372.0 * scale).round() as i64)).abs() <= 2,
                "{scale}: {slot}"
            );
        }
    }


}
