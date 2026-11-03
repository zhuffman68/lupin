//! One complete page, reusable only with the same epoch and byte-exact current
//! table/pictures/rim pixels. The UI still validates the current source proofs.
use crate::shop_names::RecoveredComponents;
use minerva_core::{Frame, ScreenRect, ShopCapture, ShopReading};

const MAX_PIXELS: u64 = 1_000_000;

#[derive(Default)]
pub struct PageCache {
    scope: Option<(u64, u64)>,
    area: Option<ScreenRect>,
    pixels: Vec<u8>,
    reading: Option<ShopReading>,
    components: Vec<RecoveredComponents>,
}

fn pixels(frame: &Frame, capture: &ShopCapture, area: ScreenRect) -> Option<Vec<u8>> {
    let left = i64::from(area.x) - i64::from(capture.origin.x) - 4;
    let top = i64::from(area.y) - i64::from(capture.origin.y) - 4;
    let right = area.right() - i64::from(capture.origin.x) + 4;
    let bottom = area.bottom() - i64::from(capture.origin.y) + 4;
    if left < 0 || top < 0 || right > i64::from(frame.width) || bottom > i64::from(frame.height)
        || right <= left || bottom <= top || ((right-left)*(bottom-top)) as u64 > MAX_PIXELS {
        return None;
    }
    let mut result = Vec::with_capacity(((right-left)*(bottom-top)*4) as usize);
    for y in top..bottom {
        result.extend_from_slice(&frame.rgba[((y*i64::from(frame.width)+left)*4) as usize
            ..((y*i64::from(frame.width)+right)*4) as usize]);
    }
    Some(result)
}

impl PageCache {
    pub fn get(&mut self, capture: &ShopCapture, scope: Option<(u64, u64)>, hint: Option<ScreenRect>)
        -> Option<(ShopReading, Vec<RecoveredComponents>)> {
        if scope != self.scope { *self = Self::default(); return None; }
        let hint = hint?;
        if scope.is_none() || self.area != Some(hint) { return None; }
        let reading = self.reading.as_ref()?;
        // Clipped names can need a newly exposed description to establish exact
        // identity. Never retain that description's old title on a cache hit.
        if reading.shop.as_ref()?.rows.iter().any(|row| row.name.as_ref()
            .is_some_and(|name| name.ends_with("...") || name.ends_with('…'))) { return None; }
        if pixels(&capture.frame, capture, hint)? != self.pixels { return None; }
        let mut reading = reading.clone();
        reading.at_ms = capture.frame.at_ms;
        reading.hover = None;
        // Capture may omit the cursor. Its current footprint can still hide a
        // scroll picture; name/amount proofs are independently checked in Python.
        if let Some(pointer) = capture.pointer {
            for row in &mut reading.shop.as_mut()?.rows {
                let s = row.area.width as f32 / 162.0;
                let cursor = ScreenRect { x: pointer.x-(6.0*s).ceil() as i32,
                    y: pointer.y-(7.0*s).ceil() as i32,
                    width: (32.0*s).ceil() as u32, height: (37.0*s).ceil() as u32 };
                let picture = ScreenRect { x: row.area.x-(36.0*s).ceil() as i32,
                    width: (34.0*s).ceil() as u32, ..row.area };
                if picture.overlaps(cursor) { row.tier = None; }
            }
        }
        Some((reading, self.components.clone()))
    }

    pub fn store(&mut self, capture: &ShopCapture, scope: Option<(u64, u64)>,
                 hint: Option<ScreenRect>, reading: &ShopReading, components: &[RecoveredComponents]) {
        let Some(shop) = &reading.shop else { *self = Self::default(); return; };
        if scope.is_none() || shop.rows.is_empty() || shop.rows.len() > 24
            || shop.rows.iter().any(|row| row.covered || row.name.is_none() || row.price.is_none()) {
            *self = Self::default(); return;
        }
        let area = hint.unwrap_or(shop.area);
        if !area.contains(shop.area) { *self = Self::default(); return; }
        let Some(pixels) = pixels(&capture.frame, capture, area) else { *self = Self::default(); return; };
        self.scope = scope; self.area = Some(area); self.pixels = pixels;
        self.reading = Some(reading.clone()); self.components = components.to_vec();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use minerva_core::{ListedPrice, ScreenPoint, ShopList, ShopRow};

    fn fixture() -> (ShopCapture, ShopReading) {
        let area = ScreenRect { x: 20, y: 20, width: 199, height: 100 };
        (ShopCapture { frame: Frame { width: 260, height: 160,
            rgba: vec![180;260*160*4], at_ms: 10 }, origin: ScreenPoint { x:0,y:0 }, pointer: None },
         ShopReading { shop:Some(ShopList { area, rows:vec![ShopRow { area,
            name:Some("Example sword".into()), price:Some(ListedPrice { quantity:1,mesos:123_456 }),
            covered:false,tier:None }] }), hover:None,at_ms:10,near_miss:None })
    }

    #[test]
    fn only_identical_current_pixels_and_the_same_epoch_can_reuse_a_page() {
        let (mut capture, reading) = fixture();let area=reading.shop.as_ref().unwrap().area;
        let mut cache=PageCache::default();cache.store(&capture,Some((1,2)),None,&reading,&[]);
        capture.frame.at_ms=20;
        assert_eq!(cache.get(&capture,Some((1,2)),Some(area)).unwrap().0.at_ms,20);
        let at=((30*capture.frame.width+30)*4) as usize;capture.frame.rgba[at]+=1;
        assert!(cache.get(&capture,Some((1,2)),Some(area)).is_none());
        capture.frame.rgba[at]-=1;
        assert!(cache.get(&capture,Some((1,3)),Some(area)).is_none());
        assert!(cache.get(&capture,Some((1,2)),Some(area)).is_none());
    }

    #[test]
    fn missing_hint_clipped_names_and_changed_rims_do_not_reuse_a_page() {
        let (mut capture, mut reading)=fixture();let area=reading.shop.as_ref().unwrap().area;
        let mut cache=PageCache::default();cache.store(&capture,Some((1,2)),None,&reading,&[]);
        assert!(cache.get(&capture,Some((1,2)),None).is_none());
        capture.frame.rgba[((18*260+18)*4) as usize]+=1;
        assert!(cache.get(&capture,Some((1,2)),Some(area)).is_none());
        reading.shop.as_mut().unwrap().rows[0].name=Some("Example s...".into());
        cache.store(&capture,Some((1,2)),None,&reading,&[]);
        assert!(cache.get(&capture,Some((1,2)),Some(area)).is_none());
    }
}
