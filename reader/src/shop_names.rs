//! Recover independently exposed native shop lines on a verified table hint.
//! The hint supplies geometry only. Every name and asking amount is read from
//! this capture, twice; no popup title, hidden icon tier or old row is reused.
use image::{GrayImage, Luma, imageops::FilterType};
use minerva_core::{ListedPrice, ScreenRect, ShopCapture, ShopList, ShopReading, ShopRow};
use std::collections::HashMap;

const MAX_ROWS: usize = 24;
const MAX_LINE_PIXELS: u32 = 32768;
const MAX_CACHE_LINES: usize = 96;

#[derive(Default)]
pub struct NameRecovery {
    cache: HashMap<Vec<u8>, Option<String>>,
}

pub struct RecoveredComponents {
    pub row: ScreenRect,
    pub name: ScreenRect,
    pub price: Option<ScreenRect>,
    pub price_value: Option<ScreenRect>,
    pub price_text: Option<String>,
}

struct Prepared {
    area: ScreenRect,
    ink: GrayImage,
    ink_width: u32,
}

struct NativeLine {
    area: ScreenRect,
    ink: GrayImage,
    bad_columns: Vec<usize>,
    available: u32,
    inset: u32,
}

struct NumericAsking {
    area: ScreenRect,
    price: ListedPrice,
}

fn pointer_covers(capture: &ShopCapture, x: i64, y: i64, scale: f32) -> bool {
    capture.pointer.is_some_and(|pointer| {
        x >= i64::from(pointer.x) - (6.0 * scale).round() as i64
            && x < i64::from(pointer.x) + (26.0 * scale).round() as i64
            && y >= i64::from(pointer.y) - (6.0 * scale).round() as i64
            && y < i64::from(pointer.y) + (30.0 * scale).round() as i64
    })
}

fn pixel(capture: &ShopCapture, x: i32, y: i32) -> Option<[u8; 3]> {
    let x = i64::from(x) - i64::from(capture.origin.x);
    let y = i64::from(y) - i64::from(capture.origin.y);
    if x < 0 || y < 0 || x >= i64::from(capture.frame.width) || y >= i64::from(capture.frame.height)
    {
        return None;
    }
    let at = ((y as u32 * capture.frame.width + x as u32) * 4) as usize;
    Some(capture.frame.rgba.get(at..at + 3)?.try_into().ok()?)
}

fn gain(p: [u8; 3], base: [f32; 3]) -> Option<f32> {
    gain_with_tolerance(p, base, 8.0)
}

fn gain_with_tolerance(p: [u8; 3], base: [f32; 3], tolerance: f32) -> Option<f32> {
    let k = (0..3).map(|i| f32::from(p[i]) * base[i]).sum::<f32>()
        / base.iter().map(|v| v * v).sum::<f32>();
    ((0.0..=1.16).contains(&k)
        && (0..3).all(|i| (f32::from(p[i]) - base[i] * k).abs() <= tolerance))
    .then_some(k)
}

fn selected_edge_colour(p: [u8; 3], base: [f32; 3]) -> bool {
    let orange = [251.0, 167.0, 46.0];
    let brightness = (0..3).map(|i| base[i] * orange[i]).sum::<f32>()
        / orange.iter().map(|v| v * v).sum::<f32>();
    let blue = [202.0, 213.0, 223.0].map(|v| v * brightness);
    let rule = [255.0, 195.0, 96.0].map(|v| v * brightness);
    if gain(p, base).is_some_and(|k| k >= 0.7)
        || gain(p, blue).is_some_and(|k| k >= 0.7)
        || gain_with_tolerance(p, rule, 16.0).is_some_and(|k| k >= 0.7)
    {
        return true;
    }
    let low = *p.iter().min().unwrap();
    let high = *p.iter().max().unwrap();
    if high - low <= 12 && f32::from(low) >= 180.0 * brightness {
        return true;
    }
    // The selected bevel blends back into the blue native band. This is a
    // background candidate only; a broad uninterrupted edge must prove it.
    let t = (f32::from(p[2]) - base[2]) / (blue[2] - base[2]);
    (0.0..=1.0).contains(&t)
        && (0..3).all(|i| (f32::from(p[i]) - (base[i] * (1.0 - t) + blue[i] * t)).abs() <= 8.0)
}

fn selected_edge_row(
    pixels: &[[u8; 3]],
    bad: &mut [bool],
    ink: &mut GrayImage,
    y: u32,
    base: [f32; 3],
    scale: f32,
) {
    let mut counts = HashMap::new();
    for &p in pixels {
        if selected_edge_colour(p, base) {
            *counts.entry(p).or_insert(0usize) += 1;
        }
    }
    let Some((colour, count)) = counts.into_iter().max_by_key(|&(p, n)| (n, p)) else {
        return;
    };
    let minimum = (12.0 * scale).ceil() as usize;
    if count < minimum {
        return;
    }
    let matches = |p: [u8; 3]| (0..3).all(|i| p[i].abs_diff(colour[i]) <= 2);
    let prefix = pixels
        .iter()
        .zip(bad.iter())
        .take_while(|(p, b)| !**b || matches(**p))
        .count();
    if prefix < minimum
        || pixels[..prefix].iter().filter(|&&p| matches(p)).count() * 100 < prefix * 85
    {
        return;
    }
    for x in 0..prefix {
        if matches(pixels[x]) {
            bad[x] = false;
            ink.put_pixel(x as u32, y, Luma([255]));
        }
    }
}

fn native_anchor(capture: &ShopCapture, table: ScreenRect, x: i32, scale: f32) -> Option<i32> {
    let native = |y: i32| -> bool {
        [(1.0, 3.0), (3.0, 5.0)].into_iter().any(|(from, to)| {
            let left = (from * scale).round().max(1.0) as i32;
            let right = (to * scale).round().max(left as f32 + 1.0) as i32;
            (left..right).all(|dx| {
                x.checked_add(dx)
                    .and_then(|xx| pixel(capture, xx, y))
                    .is_some_and(|p| {
                        [[202.0, 213.0, 223.0], [251.0, 167.0, 46.0]]
                            .into_iter()
                            .any(|base| gain(p, base).is_some_and(|k| k >= 0.45))
                    })
            })
        })
    };
    let margin = (4.0 * scale).ceil() as i32;
    let reach = (20.0 * scale).ceil() as i32;
    let run = (8.0 * scale).ceil() as i32;
    let separator = (2.0 * scale).round().max(2.0) as i32;
    (table.y.checked_sub(margin)?..=table.y.checked_add(reach)?).find(|&top| {
        (0..run).all(|dy| top.checked_add(dy).is_some_and(&native))
            && (1..=separator).all(|dy| top.checked_sub(dy).is_some_and(|y| !native(y)))
    })
}

fn same_table(table: ScreenRect, candidate: ScreenRect) -> bool {
    let scale = table.width as f32 / 199.0;
    let slack = (4.0 * scale).ceil() as i64;
    candidate.x.abs_diff(table.x) <= (5.0 * scale).ceil() as u32
        && candidate.right() <= table.right() + slack
        && i64::from(candidate.y) < table.bottom() + slack
        && candidate.bottom() > i64::from(table.y) - slack
}

fn native_grid(capture: &ShopCapture, table: ScreenRect) -> bool {
    let scale = table.width as f32 / 199.0;
    let Some(x) = table.x.checked_add((37.0 * scale).round() as i32) else {
        return false;
    };
    // A lone blue text field is not enough to displace another detected
    // window. Require independently repeated native slot geometry. Sold-out
    // slots may precede the first readable listing, so search the whole hint.
    let mut first = None;
    (0..MAX_ROWS)
        .map(|i| {
            table
                .y
                .saturating_add((i as f32 * 40.1 * scale).round() as i32)
        })
        .take_while(|&y| {
            i64::from(y) + (35.0 * scale).round() as i64
                <= table.bottom() + (4.0 * scale).ceil() as i64
        })
        .any(|y| {
            let Some(found) = native_anchor(capture, ScreenRect { y, ..table }, x, scale) else {
                return false;
            };
            let Some(anchor) = first else {
                first = Some(found);
                return false;
            };
            let slot = ((i64::from(found) - i64::from(anchor)) as f32 / (40.1 * scale)).round();
            slot >= 1.0
                && (i64::from(found) - i64::from(anchor) - (slot * 40.1 * scale).round() as i64)
                    .abs()
                    <= (3.0 * scale).ceil() as i64
        })
}

fn later_anchor(capture: &ShopCapture, table: ScreenRect, x: i32, scale: f32) -> Option<i32> {
    let pitch = 40.1 * scale;
    let mut phases = Vec::new();
    for index in 0..MAX_ROWS {
        let top = table.y.checked_add((index as f32 * pitch).round() as i32)?;
        if i64::from(top) + (35.0 * scale).round() as i64
            > table.bottom() + (4.0 * scale).ceil() as i64
        {
            break;
        }
        if let Some(found) = native_anchor(capture, ScreenRect { y: top, ..table }, x, scale) {
            let phase = ((i64::from(found) - i64::from(table.y)) as f32).rem_euclid(pitch);
            phases.push(if phase > pitch * 0.5 {
                phase - pitch
            } else {
                phase
            });
        }
    }
    let phase = phases.iter().copied().max_by_key(|candidate| {
        phases
            .iter()
            .filter(|other| {
                let delta = (*candidate - **other).abs();
                delta.min((pitch - delta).abs()) <= 2.0 * scale
            })
            .count()
    })?;
    table.y.checked_add(phase.round() as i32)
}

fn rows(capture: &ShopCapture, table: ScreenRect, reading: &ShopReading) -> Vec<ScreenRect> {
    if !(100..=597).contains(&table.width) || !(30..=1400).contains(&table.height) {
        return Vec::new();
    }
    let scale = table.width as f32 / 199.0;
    let pitch = 40.1 * scale;
    let Some(x) = table.x.checked_add((37.0 * scale).round() as i32) else {
        return Vec::new();
    };
    let width = (162.0 * scale).round() as u32;
    let height = (35.0 * scale).round() as u32;
    let slack = (4.0 * scale).ceil() as u32;
    // Another palette-compatible window (notably Sold Items) may outrank a
    // shop whose unused band tails are covered. Its geometry supplies neither
    // the hinted shop's grid nor a reason to discard its fresh native pixels.
    let offset = reading
        .shop
        .as_ref()
        .filter(|shop| same_table(table, shop.area))
        .and_then(|s| {
            s.rows
                .iter()
                .filter(|r| r.area.x.abs_diff(x) <= slack && r.area.width.abs_diff(width) <= slack)
                .map(|r| r.area.y)
                .min()
        })
        .or_else(|| later_anchor(capture, table, x, scale))
        .map(|y| {
            let value = ((i64::from(y) - i64::from(table.y)) as f32).rem_euclid(pitch);
            if value > pitch * 0.5 {
                value - pitch
            } else {
                value
            }
        })
        .unwrap_or(0.0);
    let anchor = i64::from(table.y) + i64::from(offset.round() as i32);
    (0..MAX_ROWS)
        .map(|index| ScreenRect {
            x,
            y: (anchor + (index as f32 * pitch).round() as i64)
                .clamp(i64::from(i32::MIN), i64::from(i32::MAX)) as i32,
            width,
            height,
        })
        .take_while(|row| row.bottom() <= table.bottom() + i64::from(slack))
        .collect()
}

fn prepare(capture: &ShopCapture, row: ScreenRect, asking: bool) -> Option<Prepared> {
    prepare_line(capture, row, asking, false)
}

fn prepare_line(
    capture: &ShopCapture,
    row: ScreenRect,
    asking: bool,
    ellipsis: bool,
) -> Option<Prepared> {
    let NativeLine {
        area,
        ink,
        bad_columns,
        available,
        inset,
    } = native_line(capture, row, asking)?;
    prepare_ending(
        capture,
        row,
        ellipsis,
        area,
        ink,
        bad_columns,
        available,
        inset,
    )
}

fn native_line(capture: &ShopCapture, row: ScreenRect, asking: bool) -> Option<NativeLine> {
    let scale = row.width as f32 / 162.0;
    let y = row.y.checked_add(if asking {
        (18.0 * scale).round() as i32
    } else {
        0
    })?;
    let height = (17.0 * scale).round() as u32;
    let width = row.width;
    if width < 20 || width.checked_mul(height)? > MAX_LINE_PIXELS {
        return None;
    }
    // Require a broad native blue/orange background, never a purple description
    // or a grey sold-out band. Its modal colour gives this frame's brightness.
    let mut best = None;
    for (selected, base) in [(false, [202.0, 213.0, 223.0]), (true, [251.0, 167.0, 46.0])] {
        let mut counts = HashMap::new();
        for yy in 0..height {
            for xx in 0..width {
                let p = pixel(
                    capture,
                    row.x.checked_add(xx as i32)?,
                    y.checked_add(yy as i32)?,
                )?;
                if gain(p, base).is_some_and(|k| k >= 0.45) {
                    *counts.entry(p).or_insert(0usize) += 1;
                }
            }
        }
        if let Some((colour, count)) = counts.into_iter().max_by_key(|&(p, n)| (n, p)) {
            if count >= (12.0 * scale).ceil() as usize * height as usize
                && best.as_ref().is_none_or(|(_, _, n)| count > *n)
            {
                best = Some((selected, colour, count));
            }
        }
    }
    let (selected, colour, _) = best?;
    // A selected row has an ordinary blue strip before its orange text band.
    // This is the pinned reader's selected inset, converted to captured pixels.
    let inset = if selected {
        (8.0 * row.width as f32 / 253.0).round() as u32
    } else {
        0
    };
    let mut inset = inset;
    let mut x = row.x.checked_add(inset as i32)?;
    let mut width = width.checked_sub(inset)?;
    let base = colour.map(f32::from);
    let mut ink = GrayImage::from_pixel(width, height, Luma([255]));
    let mut bad_columns = vec![0usize; width as usize];
    let edge_rows = (4.0 * scale).ceil() as u32;
    let brightness = base
        .iter()
        .zip([251.0, 167.0, 46.0])
        .map(|(a, b)| a * b)
        .sum::<f32>()
        / (251.0_f32.powi(2) + 167.0_f32.powi(2) + 46.0_f32.powi(2));
    let rule = [255.0, 195.0, 96.0].map(|v| v * brightness);
    for yy in 0..height {
        let edge = selected && (yy < edge_rows || yy + edge_rows >= height);
        let mut pixels = if edge {
            Vec::with_capacity(width as usize)
        } else {
            Vec::new()
        };
        let mut bad = if edge {
            vec![false; width as usize]
        } else {
            Vec::new()
        };
        for xx in 0..width {
            let p = pixel(
                capture,
                x.checked_add(xx as i32)?,
                y.checked_add(yy as i32)?,
            )?;
            if edge {
                pixels.push(p);
            }
            let native = if selected {
                gain_with_tolerance(p, base, 28.0)
            } else {
                gain(p, base)
            };
            if let Some(k) =
                native.or_else(|| edge.then(|| gain_with_tolerance(p, rule, 16.0)).flatten())
            {
                ink.put_pixel(xx, yy, Luma([(k * 255.0).round().clamp(0.0, 255.0) as u8]));
            } else if !((yy < 3 || yy + 3 >= height) && p.iter().all(|v| *v >= 235)) {
                if edge {
                    bad[xx as usize] = true;
                } else {
                    bad_columns[xx as usize] += 1;
                }
            }
        }
        if edge {
            selected_edge_row(&pixels, &mut bad, &mut ink, yy, base, scale);
            for (column, bad) in bad_columns.iter_mut().zip(bad) {
                *column += usize::from(bad);
            }
        }
    }
    let edge = bad_columns
        .iter()
        .take_while(|n| **n * 4 > height as usize)
        .count() as u32;
    if edge > 0 && edge <= (3.0 * scale).ceil() as u32 {
        // The native frame/scaled band edge may occupy the first columns of
        // an otherwise exact hinted band. Item/quantity ink begins farther in.
        inset += edge;
        x = x.checked_add(edge as i32)?;
        width -= edge;
        ink = image::imageops::crop_imm(&ink, edge, 0, width, height).to_image();
        bad_columns.drain(..edge as usize);
    }
    // Keep only the uninterrupted native component from the left text edge.
    // An occasional native rule/rounding pixel is not a foreign pane column.
    let available = bad_columns
        .iter()
        .position(|n| *n * 4 > height as usize)
        .map_or(width, |right| right as u32);
    if available < (20.0 * scale).round() as u32 {
        return None;
    }
    Some(NativeLine {
        area: ScreenRect {
            x,
            y,
            width,
            height,
        },
        ink,
        bad_columns,
        available,
        inset,
    })
}

fn prepare_ending(
    capture: &ShopCapture,
    row: ScreenRect,
    ellipsis: bool,
    area: ScreenRect,
    ink: GrayImage,
    bad_columns: Vec<usize>,
    available: u32,
    inset: u32,
) -> Option<Prepared> {
    let scale = row.width as f32 / 162.0;
    let (x, y, height) = (area.x, area.y, area.height);
    // Stop at the first complete native blank ending. A remote pointer's
    // black outline in the unused tail is not part of this line's glyphs.
    let ending = ((if ellipsis { 4.0 } else { 10.0 }) * scale).ceil() as u32;
    let mut blank = 0;
    let mut seen_ink = false;
    let mut complete_width = None;
    for xx in 0..available {
        if (0..height).any(|yy| ink.get_pixel(xx, yy).0[0] < 160) {
            seen_ink = true;
            blank = 0;
        } else if seen_ink && bad_columns[xx as usize] == 0 {
            blank += 1;
            if blank >= ending && !ellipsis {
                complete_width = Some(xx + 1);
                break;
            }
        } else {
            blank = 0;
        }
    }
    if ellipsis {
        // A complete UI ellipsis sits close to the native band's right edge.
        // Read its whole component; the caller must independently recognize
        // the literal full marker in both OCR passes before this can count.
        let last = (0..available)
            .rev()
            .find(|&xx| (0..height).any(|yy| ink.get_pixel(xx, yy).0[0] < 160))?;
        let end = last.checked_add(1 + ending)?;
        if end <= available
            && bad_columns[(last + 1) as usize..end as usize]
                .iter()
                .all(|n| *n == 0)
        {
            complete_width = Some(end);
        }
    }
    let complete_width = complete_width?;
    let mut bounds = (complete_width, height, 0, 0);
    let mut count = 0;
    for yy in 0..height {
        for xx in 0..complete_width {
            if ink.get_pixel(xx, yy).0[0] < 160 {
                bounds.0 = bounds.0.min(xx);
                bounds.1 = bounds.1.min(yy);
                bounds.2 = bounds.2.max(xx);
                bounds.3 = bounds.3.max(yy);
                count += 1;
            }
        }
    }
    if count < 8
        || bounds.0 > bounds.2
        || inset + bounds.0 > (12.0 * scale).ceil() as u32
        || bounds.3 - bounds.1 + 1 > (14.0 * scale).ceil() as u32
    {
        return None;
    }
    // Never read a name/number prefix cut at an occluder or the band edge. A
    // complete line must finish naturally, followed by native blank pixels.
    // Pointer coordinates are conservative geometry. Veto glyphs inside its
    // footprint, while actual native blank pixels can still prove an ending.
    if (0..height).any(|yy| {
        (0..complete_width).any(|xx| {
            ink.get_pixel(xx, yy).0[0] < 160
                && pointer_covers(
                    capture,
                    i64::from(x) + i64::from(xx),
                    i64::from(y) + i64::from(yy),
                    scale,
                )
        })
    }) {
        return None;
    }
    let ink = image::imageops::crop_imm(&ink, 0, 0, complete_width, height).to_image();
    Some(Prepared {
        area: ScreenRect {
            x,
            y,
            width: complete_width,
            height,
        },
        ink,
        ink_width: bounds.2 - bounds.0 + 1,
    })
}

fn normalized(value: &str) -> String {
    value
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase()
}

fn asking_number(
    capture: &ShopCapture,
    row: ScreenRect,
    raw: NativeLine,
    text: &str,
) -> Option<NumericAsking> {
    let price = parse_numeric(text)?;
    let words = text.split_whitespace().collect::<Vec<_>>();
    let amount = words[2];
    let scale = row.width as f32 / 162.0;
    let inked = |x| (0..raw.ink.height()).any(|y| raw.ink.get_pixel(x, y).0[0] < 160);
    let mut glyphs = Vec::new();
    let mut x = 0;
    while x < raw.available {
        if !inked(x) {
            x += 1;
            continue;
        }
        let start = x;
        while x < raw.available && inked(x) {
            x += 1;
        }
        glyphs.push((start, x));
    }
    let first = glyphs.first()?.0;
    let expected = 28.0
        + 11.0 * text.chars().filter(char::is_ascii_digit).count() as f32
        + 4.7 * text.chars().filter(|c| *c == ',').count() as f32;
    // Adjacent zeroes can be one continuous ink run. Select the numeric end by
    // the measured complete core width, never by one-run-per-character count.
    let last = glyphs
        .into_iter()
        .filter(|&(left, right)| {
            let mut top = raw.ink.height();
            let mut bottom = 0;
            for y in 0..raw.ink.height() {
                for x in left..right {
                    if raw.ink.get_pixel(x, y).0[0] < 160 {
                        top = top.min(y);
                        bottom = bottom.max(y);
                    }
                }
            }
            top <= bottom
                && bottom - top + 1 >= (5.0 * scale).ceil() as u32
                && fits_price(text, right - first, row.width, 28.0)
        })
        .min_by_key(|&(_, right)| {
            (((right - first) as f32 * 253.0 / row.width as f32 - expected).abs() * 1000.0).round()
                as u32
        })?;
    let advance = (11.0 * row.width as f32 / 253.0).round().max(1.0) as u32;
    let cells = ((last.1 - last.0) as f32 / advance as f32).round().max(1.0) as u32;
    let last_cell = last.0.checked_add((cells - 1).checked_mul(advance)?)?;
    let final_group = amount.rsplit(',').next()?;
    // Three canonical final digits can extend only through a comma. Prove its
    // entire next advance/stroke slot blank, including its low descender rows.
    // Short numbers need a whole next digit slot; no currency is consulted.
    let end = if final_group.len() == 3 {
        last_cell
            .checked_add(advance)?
            .checked_add((2.0 * scale).ceil() as u32)?
    } else {
        last_cell.checked_add(advance.checked_mul(2)?)?
    };
    if raw.inset + first > (12.0 * scale).ceil() as u32
        || end > raw.available
        || end <= last.1
        || raw.bad_columns[..end as usize].iter().any(|n| *n != 0)
        || (last.1..end).any(inked)
        || !fits_price(text, last.1 - first, row.width, 28.0)
    {
        return None;
    }
    let mut top = raw.ink.height();
    let mut bottom = 0;
    let mut ink_count = 0;
    for y in 0..raw.ink.height() {
        for x in first..last.1 {
            if raw.ink.get_pixel(x, y).0[0] < 160 {
                top = top.min(y);
                bottom = bottom.max(y);
                ink_count += 1;
                if pointer_covers(
                    capture,
                    i64::from(raw.area.x) + i64::from(x),
                    i64::from(raw.area.y) + i64::from(y),
                    scale,
                ) {
                    return None;
                }
            }
        }
    }
    if ink_count < 8 || top > bottom || bottom - top + 1 > (14.0 * scale).ceil() as u32 {
        return None;
    }
    let area = ScreenRect {
        width: end,
        ..raw.area
    };
    Some(NumericAsking { area, price })
}

fn complete_ellipsis(line: &Prepared, scale: f32) -> bool {
    let inked = |x| (0..line.ink.height()).any(|y| line.ink.get_pixel(x, y).0[0] < 160);
    let mut right = line.ink.width();
    let mut dots = Vec::new();
    while right > 0 && dots.len() < 3 {
        while right > 0 && !inked(right - 1) {
            right -= 1;
        }
        if right == 0 {
            return false;
        }
        let end = right;
        while right > 0 && inked(right - 1) {
            right -= 1;
        }
        let mut top = line.ink.height();
        let mut bottom = 0;
        for y in 0..line.ink.height() {
            for x in right..end {
                if line.ink.get_pixel(x, y).0[0] < 160 {
                    top = top.min(y);
                    bottom = bottom.max(y);
                }
            }
        }
        if end - right > (3.0 * scale).ceil() as u32
            || bottom - top + 1 > (3.0 * scale).ceil() as u32
        {
            return false;
        }
        dots.push((right, end, top, bottom));
    }
    dots.len() == 3
        && dots[0].1 - dots[2].0 <= (18.0 * scale).ceil() as u32
        && dots.iter().all(|dot| {
            dot.2.abs_diff(dots[0].2) <= scale.ceil() as u32
                && dot.3.abs_diff(dots[0].3) <= scale.ceil() as u32
        })
}

// Keep the pinned font's quantity/"for"/number measurement and canonical
// quantity/comma grammar. Currency words supply no amount authority.
fn fits_price(value: &str, ink_width: u32, band_width: u32, fixed_width: f32) -> bool {
    let digits = value.chars().filter(char::is_ascii_digit).count() as f32;
    let commas = value.chars().filter(|c| *c == ',').count() as f32;
    let native_width = ink_width as f32 * 253.0 / band_width as f32;
    (fixed_width + 11.0 * digits + 4.7 * commas - native_width).abs() <= 11.0 / 2.0
}

fn parse_numeric(value: &str) -> Option<ListedPrice> {
    let words = value.split_whitespace().collect::<Vec<_>>();
    let [quantity, "for", amount] = words[..] else {
        return None;
    };
    let digits = |text: &str| -> Option<u64> {
        (!text.is_empty() && !text.starts_with('0') && text.bytes().all(|c| c.is_ascii_digit()))
            .then(|| text.parse().ok())?
    };
    let quantity = digits(quantity)?;
    let mut groups = amount.split(',');
    let first = groups.next()?;
    if first.is_empty() || first.len() > 3 {
        return None;
    }
    let rest = groups.collect::<Vec<_>>();
    if rest
        .iter()
        .any(|group| group.len() != 3 || !group.bytes().all(|c| c.is_ascii_digit()))
    {
        return None;
    }
    let mesos = digits(&std::iter::once(first).chain(rest).collect::<String>())?;
    Some(ListedPrice { quantity, mesos })
}

fn numeric_prefix(value: &str) -> Option<String> {
    let mut words = value.split_whitespace();
    let quantity = words.next()?;
    if words.next()? != "for" {
        return None;
    }
    let amount = words
        .next()?
        .chars()
        .take_while(|c| c.is_ascii_digit() || *c == ',')
        .collect::<String>();
    let text = format!("{quantity} for {amount}");
    parse_numeric(&text)?;
    Some(text)
}

impl NameRecovery {
    fn read_numeric(&mut self, raw: &NativeLine) -> Option<String> {
        let ink =
            image::imageops::crop_imm(&raw.ink, 0, 0, raw.available, raw.ink.height()).to_image();
        let mut key = b"numeric-only\0".to_vec();
        key.extend_from_slice(&ink.width().to_le_bytes());
        key.extend_from_slice(&ink.height().to_le_bytes());
        key.extend_from_slice(ink.as_raw());
        if let Some(value) = self.cache.get(&key) {
            return value.clone();
        }
        let first = crate::text::read_scaled(&ink, 2, FilterType::Triangle)
            .and_then(|text| numeric_prefix(&text));
        let second = crate::text::read_scaled(&ink, 3, FilterType::Triangle)
            .and_then(|text| numeric_prefix(&text));
        let value = first.filter(|text| second.as_ref() == Some(text));
        if self.cache.len() >= MAX_CACHE_LINES {
            self.cache.clear();
        }
        self.cache.insert(key, value.clone());
        value
    }
    fn read(&mut self, prepared: &Prepared) -> Option<String> {
        let mut key = Vec::with_capacity(prepared.ink.as_raw().len() + 8);
        key.extend_from_slice(&prepared.ink.width().to_le_bytes());
        key.extend_from_slice(&prepared.ink.height().to_le_bytes());
        key.extend_from_slice(prepared.ink.as_raw());
        if let Some(value) = self.cache.get(&key) {
            return value.clone();
        }
        let first = crate::text::read_scaled(&prepared.ink, 2, FilterType::Triangle);
        let second = crate::text::read_scaled(&prepared.ink, 3, FilterType::Triangle);
        let value = first.filter(|a| {
            second
                .as_ref()
                .is_some_and(|b| normalized(a) == normalized(b))
        });
        if self.cache.len() >= MAX_CACHE_LINES {
            self.cache.clear();
        }
        self.cache.insert(key, value.clone());
        value
    }

    pub fn apply(
        &mut self,
        capture: &ShopCapture,
        reading: &mut ShopReading,
        hint: Option<ScreenRect>,
    ) -> Vec<RecoveredComponents> {
        let Some(table) = hint else {
            return Vec::new();
        };
        let candidates = rows(capture, table, reading);
        let unrelated = reading
            .shop
            .as_ref()
            .is_some_and(|shop| !same_table(table, shop.area));
        let mut fresh = Vec::new();
        for candidate in candidates {
            let previous = reading.shop.as_ref().and_then(|shop| {
                if !same_table(table, shop.area) {
                    return None;
                }
                shop.rows.iter().find(|r| {
                    r.area.x.abs_diff(candidate.x) <= 3 && r.area.y.abs_diff(candidate.y) <= 3
                })
            });
            let area = previous.map_or(candidate, |row| row.area);
            let Some((name, requires_ellipsis)) = prepare(capture, area, false)
                .map(|name| (name, false))
                .or_else(|| prepare_line(capture, area, false, true).map(|name| (name, true)))
            else {
                continue;
            };
            // A clean native row already read this name in this same capture.
            // Keep that identity while independently proving its numeric line.
            let current_name = previous
                .filter(|row| !row.covered)
                .and_then(|row| row.name.clone());
            let Some(text) = current_name.or_else(|| self.read(&name)) else {
                continue;
            };
            let ellipsis = text.ends_with("...") || text.ends_with('…');
            if requires_ellipsis && !ellipsis
                || text.ends_with('.') && !ellipsis
                || ellipsis && !complete_ellipsis(&name, area.width as f32 / 162.0)
                || text.chars().count() > 100
                || !text.chars().any(char::is_alphabetic)
            {
                continue;
            }
            let mut price = None;
            let mut price_area = None;
            let mut price_value = None;
            let mut price_text = None;
            if let Some(raw) = native_line(capture, area, true) {
                if let Some(text) = self.read_numeric(&raw) {
                    if let Some(number) = asking_number(capture, area, raw, &text) {
                        price = Some(number.price);
                        price_area = Some(number.area);
                        price_value = Some(number.area);
                        price_text = Some(text);
                    }
                }
            }
            if previous.is_some_and(|row| {
                !row.covered
                    && row.name.is_some()
                    && row.price.is_some()
                    && (row.name.as_ref() != Some(&text) || row.price != price)
            }) {
                // This is a current, strict native read from the same capture,
                // not an old page/cache offer. An optional proof cannot erase it.
                continue;
            }
            let tier = previous
                .filter(|row| !row.covered && row.name.as_ref() == Some(&text))
                .and_then(|row| row.tier);
            let row = ShopRow {
                area,
                name: Some(text),
                price,
                covered: false,
                tier,
            };
            fresh.push((
                row,
                RecoveredComponents {
                    row: area,
                    name: name.area,
                    price: price_area,
                    price_value,
                    price_text,
                },
            ));
        }
        if unrelated {
            if fresh.is_empty()
                || !fresh.iter().any(|(row, _)| row.price.is_some()) && !native_grid(capture, table)
            {
                return Vec::new();
            }
            // Commit only after fresh native listing/grid evidence. A single
            // unrelated name at arbitrary hinted geometry cannot replace the
            // detected window. Its hover title never becomes shop authority.
            reading.shop = None;
            reading.hover = None;
            reading.near_miss = None;
        }
        let mut recovered = Vec::new();
        for (row, metadata) in fresh {
            let shop = reading.shop.get_or_insert_with(|| ShopList {
                area: table,
                rows: Vec::new(),
            });
            if i64::from(row.area.y) < i64::from(shop.area.y) - 4
                || row.area.bottom() > shop.area.bottom() + 4
            {
                shop.area = table;
            }
            if let Some(previous) = shop
                .rows
                .iter_mut()
                .find(|r| r.area.y.abs_diff(row.area.y) <= 3)
            {
                *previous = row;
            } else {
                shop.rows.push(row);
            }
            recovered.push(metadata);
        }
        if let Some(shop) = reading.shop.as_mut() {
            shop.rows.sort_by_key(|r| r.area.y);
        }
        recovered
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use minerva_core::{Frame, ScreenPoint};

    fn sample(pointer: Option<ScreenPoint>) -> (ShopCapture, ScreenRect, ShopReading) {
        let mut frame = Frame {
            width: 300,
            height: 180,
            rgba: [202, 213, 223, 255].repeat(300 * 180),
            at_ms: 1,
        };
        for y in 45..54 {
            for x in 82..125 {
                let i = (y * 300 + x) * 4;
                frame.rgba[i..i + 3].copy_from_slice(&[0, 0, 0]);
            }
        }
        (
            ShopCapture {
                frame,
                origin: ScreenPoint { x: 0, y: 0 },
                pointer,
            },
            ScreenRect {
                x: 40,
                y: 40,
                width: 199,
                height: 100,
            },
            ShopReading {
                shop: None,
                hover: None,
                at_ms: 1,
                near_miss: None,
            },
        )
    }

    fn row(table: ScreenRect) -> ScreenRect {
        let (capture, _, reading) = sample(None);
        rows(&capture, table, &reading)[0]
    }

    #[test]
    fn independently_prepares_all_slots_without_requiring_a_hovered_row() {
        let (capture, table, reading) = sample(None);
        let bands = rows(&capture, table, &reading);
        assert_eq!(bands.len(), 2);
        assert_eq!(bands[0].x, 77);
        assert_eq!(bands[1].y, 80);
        let name = prepare(&capture, bands[0], false).unwrap();
        assert_eq!(name.area.height, 17);
        assert_eq!(name.area.width, 58);
    }

    #[test]
    fn pointer_inside_name_glyphs_cannot_price_its_prefix() {
        let (capture, table, _) = sample(Some(ScreenPoint { x: 110, y: 48 }));
        assert!(prepare(&capture, row(table), false).is_none());
    }

    #[test]
    fn pointer_on_asking_or_native_blank_tail_preserves_a_complete_name() {
        for pointer in [ScreenPoint { x: 160, y: 68 }, ScreenPoint { x: 133, y: 48 }] {
            let (capture, table, _) = sample(Some(pointer));
            assert!(prepare(&capture, row(table), false).is_some());
        }
    }

    #[test]
    fn remote_pointer_ink_after_a_native_ending_is_not_part_of_the_line() {
        let (mut capture, table, _) = sample(Some(ScreenPoint { x: 160, y: 48 }));
        for y in 45..52 {
            for x in 158..164 {
                let i = (y * 300 + x) * 4;
                capture.frame.rgba[i..i + 3].copy_from_slice(&[0, 0, 0]);
            }
        }
        assert_eq!(prepare(&capture, row(table), false).unwrap().area.width, 58);
    }

    #[test]
    fn native_left_band_edges_supply_the_grid_when_no_reader_row_survives() {
        let (mut capture, table, reading) = sample(None);
        for y in 36..45 {
            for x in 77..82 {
                let i = (y * 300 + x) * 4;
                capture.frame.rgba[i..i + 3].copy_from_slice(&[255, 255, 255]);
            }
        }
        assert_eq!(rows(&capture, table, &reading)[0].y, 45);
    }

    #[test]
    fn component_geometry_handles_scale_capture_origin_and_out_of_bounds() {
        let (capture, table, _) = sample(None);
        let original = row(table);
        let rgba = image::RgbaImage::from_raw(300, 180, capture.frame.rgba).unwrap();
        let scaled = image::imageops::resize(&rgba, 600, 360, FilterType::Nearest);
        let capture = ShopCapture {
            frame: Frame {
                width: 600,
                height: 360,
                rgba: scaled.into_raw(),
                at_ms: 1,
            },
            origin: ScreenPoint { x: 100, y: -50 },
            pointer: None,
        };
        let band = ScreenRect {
            x: original.x * 2 + 100,
            y: original.y * 2 - 50,
            width: original.width * 2,
            height: original.height * 2,
        };
        let name = prepare(&capture, band, false).unwrap();
        assert_eq!(
            name.area,
            ScreenRect {
                width: 116,
                height: 34,
                ..band
            }
        );
        assert!(prepare(&capture, ScreenRect { x: 650, ..band }, false).is_none());
    }

    #[test]
    fn rejects_purple_or_grey_and_empty_bands() {
        let (mut capture, table, _) = sample(None);
        for colour in [
            [70, 65, 105, 255],
            [200, 200, 200, 255],
            [202, 213, 223, 255],
        ] {
            capture.frame.rgba = colour.repeat(300 * 180);
            assert!(prepare(&capture, row(table), false).is_none());
        }
    }

    #[test]
    fn rejects_occluded_prefix_but_accepts_a_complete_native_ending() {
        for (left, accepted) in [(120, false), (134, false), (135, true), (180, true)] {
            let (mut capture, table, _) = sample(None);
            for y in 40..57 {
                for x in left..239 {
                    let i = (y * 300 + x) * 4;
                    capture.frame.rgba[i..i + 3].copy_from_slice(&[70, 65, 105]);
                }
            }
            assert_eq!(
                prepare(&capture, row(table), false).is_some(),
                accepted,
                "pane at {left}"
            );
        }
    }

    #[test]
    fn orange_native_name_uses_its_inset_and_never_the_blue_strip() {
        let (mut capture, table, _) = sample(None);
        for y in 40..57 {
            for x in 82..239 {
                let i = (y * 300 + x) * 4;
                if capture.frame.rgba[i..i + 3] != [0, 0, 0] {
                    capture.frame.rgba[i..i + 3].copy_from_slice(&[251, 167, 46]);
                }
            }
        }
        let name = prepare(&capture, row(table), false).unwrap();
        assert_eq!(name.area.x, 82);
        assert_eq!(name.ink_width, 43);
    }

    #[test]
    fn short_ending_requires_all_three_small_baseline_dot_components() {
        let mut ink = GrayImage::from_pixel(80, 17, Luma([255]));
        for y in 4..13 {
            for x in 5..35 {
                ink.put_pixel(x, y, Luma([0]));
            }
        }
        for left in [50, 55, 60] {
            for y in 11..13 {
                for x in left..left + 2 {
                    ink.put_pixel(x, y, Luma([0]));
                }
            }
        }
        let mut line = Prepared {
            area: ScreenRect {
                x: 0,
                y: 0,
                width: 80,
                height: 17,
            },
            ink,
            ink_width: 57,
        };
        assert!(complete_ellipsis(&line, 1.0));
        for y in 11..13 {
            for x in 60..62 {
                line.ink.put_pixel(x, y, Luma([255]));
            }
        }
        assert!(!complete_ellipsis(&line, 1.0));
    }

    #[test]
    fn unrelated_name_only_override_needs_more_than_a_single_native_band_edge() {
        let (mut capture, table, _) = sample(None);
        for y in 36..45 {
            for x in 77..82 {
                let i = (y * 300 + x) * 4;
                capture.frame.rgba[i..i + 3].copy_from_slice(&[255, 255, 255]);
            }
        }
        assert!(!native_grid(&capture, table));
        for y in 76..85 {
            for x in 77..82 {
                let i = (y * 300 + x) * 4;
                capture.frame.rgba[i..i + 3].copy_from_slice(&[255, 255, 255]);
            }
        }
        assert!(native_grid(&capture, table));
    }

    #[test]
    fn table_hints_are_bounded_and_unrelated_candidates_cannot_move_the_grid() {
        let (capture, table, mut reading) = sample(None);
        for invalid in [
            ScreenRect { width: 99, ..table },
            ScreenRect {
                height: 1401,
                ..table
            },
            ScreenRect {
                x: i32::MAX,
                ..table
            },
        ] {
            assert!(rows(&capture, invalid, &reading).is_empty());
        }
        assert!(
            rows(
                &capture,
                ScreenRect {
                    height: 1400,
                    ..table
                },
                &reading
            )
            .len()
                <= MAX_ROWS
        );
        reading.shop = Some(ShopList {
            area: ScreenRect { x: 80, ..table },
            rows: vec![ShopRow {
                area: ScreenRect {
                    x: 77,
                    y: 50,
                    width: 162,
                    height: 35,
                },
                name: Some("Unrelated ledger row".into()),
                price: None,
                covered: false,
                tier: None,
            }],
        });
        assert_eq!(rows(&capture, table, &reading)[0].y, table.y);
        reading.shop = Some(ShopList {
            area: ScreenRect {
                width: 160,
                ..table
            },
            rows: Vec::new(),
        });
        assert!(!rows(&capture, table, &reading).is_empty());
        reading.shop.as_mut().unwrap().area.width = 240;
        assert_eq!(rows(&capture, table, &reading)[0].y, table.y);
    }

    #[test]
    fn numeric_parser_keeps_canonical_quantity_groups_and_font_width() {
        assert_eq!(
            parse_numeric("1 for 13,999"),
            Some(ListedPrice {
                quantity: 1,
                mesos: 13999
            })
        );
        assert!(fits_price("1 for 13,999", 63, 162, 28.0));
        assert!(fits_price("1 for 13,999", 126, 324, 28.0));
        assert!(!fits_price("1 for 3,999", 63, 162, 28.0));
        for value in [
            "1 for 13999",
            "0 for 13,999",
            "01 for 13,999",
            "1 for 13,99",
            "1 for 013,999",
            "1 for 13,999 me",
            "1 for 13,999 mesos",
            "1 For 13,999",
            "for 13,999",
        ] {
            assert_eq!(parse_numeric(value), None, "{value}");
        }
    }

    #[test]
    fn numeric_ocr_prefix_ignores_all_trailing_nonnumeric_text() {
        for value in [
            "1 for 12,999",
            "1 for 12,999 me",
            "1 for 12,999whatever",
            "1 for 12,999 ?",
        ] {
            assert_eq!(numeric_prefix(value), Some("1 for 12,999".into()));
        }
        for value in [
            "1 for 12,99",
            "1 for 12,999,9",
            "1 for 12999",
            "1 for 12,9999",
            "1 for 12,999,",
            "0 for 12,999",
        ] {
            assert_eq!(numeric_prefix(value), None, "{value}");
        }
    }
}
