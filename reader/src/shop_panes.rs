//! Keep a player-shop sales ledger out of the pinned listing detector.
//!
//! The separate Sold Items window reuses the listing palette and width. Its
//! totals header can therefore win Minerva's candidate order before the real
//! shop. A header name alone is not a rejection: require its native three-line
//! summary cell and the following long grid cell, then retry without that pane.
use crate::shop_prices::PriceRecovery;
use minerva_core::{Frame, PlayerShopReader, ScreenRect, ShopCapture, ShopReading};

fn pixel(frame: &Frame, x: u32, y: u32) -> [u8; 3] {
    let at = ((y * frame.width + x) * 4) as usize;
    [frame.rgba[at], frame.rgba[at + 1], frame.rgba[at + 2]]
}

fn blue(p: [u8; 3]) -> bool {
    let base = [202.0, 213.0, 223.0];
    let k = (0..3).map(|i| p[i] as f32 * base[i]).sum::<f32>()
        / base.iter().map(|v| v * v).sum::<f32>();
    (0.5..=1.15).contains(&k) && (0..3).all(|i| (p[i] as f32 - base[i] * k).abs() <= 7.0)
}

fn ledger_area(capture: &ShopCapture, reading: &ShopReading) -> Option<ScreenRect> {
    let shop = reading.shop.as_ref()?;
    let row = shop.rows.first()?;
    let name: String = row
        .name
        .as_ref()?
        .chars()
        .filter(|c| c.is_ascii_alphanumeric())
        .map(|c| c.to_ascii_lowercase())
        .collect();
    if name != "totalsalestotalreceived"
        || row.covered
        || row.price.is_some()
        || !(140..=480).contains(&row.area.width)
    {
        return None;
    }
    let scale = row.area.width as f32 / 162.0;
    let px = |n: f32| (n * scale).round() as u32;
    if row.area.y.abs_diff(shop.area.y) > px(4.0) || shop.area.height < px(110.0) {
        return None;
    }
    let x = i64::from(row.area.x) - i64::from(capture.origin.x);
    let y = i64::from(row.area.y) - i64::from(capture.origin.y);
    let frame = &capture.frame;
    if x < 0
        || y < 0
        || x + i64::from(row.area.width) > i64::from(frame.width)
        || y + i64::from(px(76.0)) > i64::from(frame.height)
    {
        return None;
    }
    let (x, y) = (x as u32, y as u32);
    let slack = px(4.0);
    // OCR's price-line ascent can move the inferred listing top a few pixels.
    // Find the native rules within that tolerance rather than trusting ascent.
    (y.saturating_sub(slack)..=(y + slack).min(frame.height - px(76.0)))
        .any(|top| ledger_grid(frame, x, top, row.area.width, scale))
        .then_some(shop.area)
}

fn ledger_grid(frame: &Frame, x: u32, y: u32, band_width: u32, scale: f32) -> bool {
    let px = |n: f32| (n * scale).round() as u32;
    let left = x + px(3.0);
    let right = x + band_width - px(3.0);
    let width = (right - left) as usize;
    // Ordinary shop listings have two lines, followed by a thick slot divider
    // at y=36. This pane has a second thin white rule there and a third line.
    for dy in [18.0, 36.0] {
        let white = (left..right)
            .filter(|&xx| {
                let p = pixel(frame, xx, y + px(dy));
                p.iter().all(|&v| v >= 235) && p[0].abs_diff(p[2]) <= 12
            })
            .count();
        if white * 5 < width * 4 {
            return false;
        }
        let after = (left..right)
            .filter(|&xx| blue(pixel(frame, xx, y + px(dy + 2.0))))
            .count();
        if after * 5 < width * 4 {
            return false;
        }
    }
    for (top, bottom) in [(1.0, 17.0), (19.0, 35.0), (37.0, 53.0), (59.0, 75.0)] {
        let (top, bottom) = (y + px(top), y + px(bottom));
        let total = width * (bottom - top) as usize;
        let mut count = 0;
        for yy in top..bottom {
            count += (left..right)
                .filter(|&xx| blue(pixel(frame, xx, yy)))
                .count();
        }
        if count * 5 < total * 3 {
            return false;
        }
    }
    let mut ink = 0;
    for yy in y + px(39.0)..y + px(51.0) {
        ink += (left..right)
            .filter(|&xx| pixel(frame, xx, yy).iter().all(|&v| v < 110))
            .count();
    }
    ink >= (12.0 * scale * scale).round() as usize
}

fn mask_pane(capture: &mut ShopCapture, area: ScreenRect) {
    let frame = &mut capture.frame;
    let left = (i64::from(area.x) - i64::from(capture.origin.x) - 3)
        .clamp(0, i64::from(frame.width)) as u32;
    let top = (i64::from(area.y) - i64::from(capture.origin.y) - 3)
        .clamp(0, i64::from(frame.height)) as u32;
    let right =
        (area.right() - i64::from(capture.origin.x) + 3).clamp(0, i64::from(frame.width)) as u32;
    let bottom =
        (area.bottom() - i64::from(capture.origin.y) + 3).clamp(0, i64::from(frame.height)) as u32;
    for yy in top..bottom {
        for xx in left..right {
            let at = ((yy * frame.width + xx) * 4) as usize;
            frame.rgba[at..at + 4].copy_from_slice(&[0, 0, 0, 255]);
        }
    }
}

pub fn read(
    capture: &ShopCapture,
    reader: &mut PlayerShopReader,
    prices: &mut PriceRecovery,
) -> ShopReading {
    let mut reading = reader.read(capture);
    let mut filtered = None;
    // There is normally one ledger; bound retry work for arbitrary captures.
    for _ in 0..2 {
        let source = filtered.as_ref().unwrap_or(capture);
        let Some(area) = ledger_area(source, &reading) else {
            prices.apply(source, &mut reading, reader);
            return reading;
        };
        let source = filtered.get_or_insert_with(|| capture.clone());
        mask_pane(source, area);
        reading = reader.read(source);
    }
    let source = filtered.as_ref().unwrap_or(capture);
    if ledger_area(source, &reading).is_some() {
        reading.shop = None;
        reading.hover = None;
    } else {
        prices.apply(source, &mut reading, reader);
    }
    reading
}

#[cfg(test)]
mod tests {
    use super::*;
    use minerva_core::{ScreenPoint, ShopList, ShopRow};

    fn example(scale: u32) -> (ShopCapture, ShopReading) {
        let (width, height) = (260 * scale, 290 * scale);
        let mut frame = Frame {
            width,
            height,
            rgba: vec![0; (width * height * 4) as usize],
            at_ms: 0,
        };
        for yy in 10 * scale..240 * scale {
            for xx in 50 * scale..212 * scale {
                let relative = yy / scale - 10;
                let colour = if [18, 36].contains(&(relative % 58)) {
                    [255, 255, 255, 255]
                } else {
                    [205, 217, 227, 255]
                };
                let at = ((yy * width + xx) * 4) as usize;
                frame.rgba[at..at + 4].copy_from_slice(&colour);
            }
        }
        for yy in 52 * scale..58 * scale {
            for xx in 55 * scale..80 * scale {
                let at = ((yy * width + xx) * 4) as usize;
                frame.rgba[at..at + 4].copy_from_slice(&[0, 0, 0, 255]);
            }
        }
        let origin = ScreenPoint { x: 400, y: 80 };
        let area = ScreenRect {
            x: 400 + 13 * scale as i32,
            y: 80 + 10 * scale as i32,
            width: 199 * scale,
            height: 228 * scale,
        };
        let row = ShopRow {
            area: ScreenRect {
                x: 400 + 50 * scale as i32,
                y: area.y,
                width: 162 * scale,
                height: 35 * scale,
            },
            name: Some("Total Sales / Total Received".into()),
            price: None,
            covered: false,
            tier: None,
        };
        (
            ShopCapture {
                frame,
                origin,
                pointer: None,
            },
            ShopReading {
                shop: Some(ShopList {
                    area,
                    rows: vec![row],
                }),
                hover: None,
                at_ms: 0,
                near_miss: None,
            },
        )
    }

    #[test]
    fn rejects_only_a_proven_three_line_summary_pane_at_each_scale() {
        for scale in [1, 2] {
            let (capture, reading) = example(scale);
            assert_eq!(
                ledger_area(&capture, &reading),
                Some(reading.shop.as_ref().unwrap().area)
            );
        }
    }

    #[test]
    fn a_name_without_ledger_geometry_is_not_a_blacklist() {
        let (mut capture, reading) = example(1);
        for yy in 46..50 {
            for xx in 50..212 {
                let at = ((yy * capture.frame.width + xx) * 4) as usize;
                capture.frame.rgba[at..at + 4].copy_from_slice(&[147, 167, 189, 255]);
            }
        }
        assert!(ledger_area(&capture, &reading).is_none());
    }

    #[test]
    fn unrelated_names_prices_and_covered_rows_cannot_exclude_a_pane() {
        let (capture, reading) = example(1);
        let mut changed = reading.clone();
        changed.shop.as_mut().unwrap().rows[0].name = Some("Example Hat".into());
        assert!(ledger_area(&capture, &changed).is_none());
        changed = reading.clone();
        changed.shop.as_mut().unwrap().rows[0].covered = true;
        assert!(ledger_area(&capture, &changed).is_none());
        changed = reading.clone();
        changed.shop.as_mut().unwrap().rows[0].price = Some(minerva_core::ListedPrice {
            quantity: 1,
            mesos: 10,
        });
        assert!(ledger_area(&capture, &changed).is_none());
    }

    #[test]
    fn exclusion_preserves_other_panes_and_original_tooltip_pixels() {
        let (capture, reading) = example(1);
        let before = capture.frame.rgba.clone();
        let mut filtered = capture.clone();
        mask_pane(&mut filtered, ledger_area(&capture, &reading).unwrap());
        assert_eq!(capture.frame.rgba, before);
        assert_eq!(pixel(&filtered.frame, 60, 20), [0, 0, 0]);
        assert_eq!(
            pixel(&filtered.frame, 220, 20),
            pixel(&capture.frame, 220, 20)
        );
    }
}
