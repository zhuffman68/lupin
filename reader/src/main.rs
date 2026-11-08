//! Pixel-only bridge: accepts captured RGBA or PNG paths; no game resources.
#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]
use minerva_core::{
    Frame, PlayerShopReader, ScreenPoint, ShopCapture,
};
use serde::Deserialize;
use std::io::{self, BufRead, Write};
use std::time::Instant;
mod experience;
mod game_area;
mod text;
mod pickups;
mod tooltip_text;
mod tooltip_reader;
mod tooltip_surface;
mod tooltip_association;
mod inventory_pixels;
mod tooltip_frame;
mod centered_tooltip;
mod shop_prices;
mod shop_selection;
mod shop_panes;
mod shop_names;
mod shop_cache;
use game_area::{Locator, Rect};

#[derive(Deserialize)]
struct Request {
    path: String,
    #[serde(default)]
    at_ms: u64,
    pointer: Option<ScreenPoint>,
    width: Option<u32>,
    height: Option<u32>,
    #[serde(default)]
    tooltip: bool,
    #[serde(default)]
    tooltip_retry: bool,
    origin: Option<ScreenPoint>,
    #[serde(default)]
    auto_game: bool,
    #[serde(default)]
    locate_only: bool,
    roi: Option<Rect>,
    #[serde(default)]
    experience_only: bool,
    #[serde(default)]
    read_map: bool,
    #[serde(default)]
    pickups_only: bool,
    #[serde(default)]
    exclude: Vec<Rect>,
    #[serde(default)]
    annotations: Vec<Rect>,
    shop_area: Option<minerva_core::ScreenRect>,
    shop_epoch: Option<u64>,
    capture_generation: Option<u64>,
    shop_recovery: Option<bool>,
    #[serde(default)]
    progressive_shop: bool,
    #[serde(default)]
    progressive_tooltip: bool,
}

fn main() {
    let mut reader = None;
    let mut tooltip_reader = tooltip_reader::TooltipReader::default();
    let mut locator = Locator::new();
    let mut experience = None;
    let mut pickups = pickups::PickupLogReader::default();
    let mut price_recovery = shop_prices::PriceRecovery::default();
    let mut name_recovery = shop_names::NameRecovery::default();
    let mut page_cache = shop_cache::PageCache::default();
    let stdin = io::stdin();
    let mut stdout = io::BufWriter::new(io::stdout());
    for line in stdin.lock().lines() {
        let result = (|| -> Result<serde_json::Value, Box<dyn std::error::Error>> {
            let request: Request = serde_json::from_str(&line?)?;
            let started = Instant::now();
            let frame = if let (Some(width), Some(height)) = (request.width, request.height) {
                if width == 0
                    || height == 0
                    || width > 16384
                    || height > 16384
                    || u64::from(width) * u64::from(height) > 16_777_216
                {
                    return Err("capture dimensions exceed limit".into());
                }
                let rgba = std::fs::read(&request.path)?;
                if rgba.len() != width as usize * height as usize * 4 {
                    return Err("captured RGBA length does not match dimensions".into());
                }
                Frame {
                    width,
                    height,
                    rgba,
                    at_ms: request.at_ms,
                }
            } else if request.width.is_some() || request.height.is_some() {
                return Err("raw captures require both width and height".into());
            } else {
                let img = image::open(&request.path)?.into_rgba8();
                if img.width() > 16384 || img.height() > 16384 {
                    return Err("capture dimensions exceed limit".into());
                }
                Frame {
                    width: img.width(),
                    height: img.height(),
                    rgba: img.into_raw(),
                    at_ms: request.at_ms,
                }
            };
            let mut origin = request.origin.unwrap_or(ScreenPoint { x: 0, y: 0 });
            let mut location = None;
            let frame = if request.auto_game || request.locate_only {
                let image = image::RgbaImage::from_raw(frame.width, frame.height, frame.rgba)
                    .ok_or("invalid pixels")?;
                location = locator.find(&image);
                if location.is_none() || request.locate_only {
                    return Ok(
                        serde_json::json!({"atMs":request.at_ms,"shop":null,"hover":null,"tooltip":null,
                        "gameArea":location.as_ref().map(|l|l.area),"gameGuards":location.as_ref().map(|l|&l.guards),
                        "gameFooter":location.as_ref().map(|l|l.footer),
                        "ocrMs":started.elapsed().as_secs_f64()*1000.0}),
                    );
                }
                let mut area = location.as_ref().unwrap().area;
                if let Some(roi) = request.roi {
                    let x = area.x.max(roi.x);
                    let y = area.y.max(roi.y);
                    let right = (area.x + area.width).min(roi.x + roi.width);
                    let bottom = (area.y + area.height).min(roi.y + roi.height);
                    if right > x && bottom > y {
                        area = Rect {
                            x,
                            y,
                            width: right - x,
                            height: bottom - y,
                        };
                    }
                }
                origin.x += area.x as i32;
                origin.y += area.y as i32;
                let cropped =
                    image::imageops::crop_imm(&image, area.x, area.y, area.width, area.height)
                        .to_image();
                Frame {
                    width: area.width,
                    height: area.height,
                    rgba: cropped.into_raw(),
                    at_ms: request.at_ms,
                }
            } else {
                frame
            };
            if request.experience_only {
                let result = experience
                    .get_or_insert_with(experience::ExperienceReader::new)
                    .read(frame, origin, request.read_map);
                return Ok(serde_json::json!({"atMs":request.at_ms,"experience":result,
                    "experienceOnly":true,"ocrMs":started.elapsed().as_secs_f64()*1000.0}));
            }
            if request.pickups_only {
                return Ok(serde_json::json!({"atMs":request.at_ms,"pickups":pickups.read(&frame),
                    "pickupsRead":true,"ocrMs":started.elapsed().as_secs_f64()*1000.0}));
            }
            let mut frame=frame;
            mask_owned_surfaces(&mut frame,origin,&request.exclude);
            let capture = ShopCapture {
                frame,
                origin,
                pointer: request.pointer,
            };
            let tooltip_started=Instant::now();
            let scale_hint=location.as_ref().and_then(|l|l.guards.get(1)).map(|r|r.width as f32/36.0);
            let tooltip_value=if request.tooltip {
                if let Some(pointer)=request.pointer {
                    tooltip_reader.read(&capture,pointer,request.tooltip_retry,&request.annotations,scale_hint)?
                } else {serde_json::json!({})}
            } else {serde_json::json!({})};
            let tooltip_ms=tooltip_started.elapsed().as_secs_f64()*1000.0;
            // An independently bound inventory title can finish before shop
            // repair; its frame, epoch and original deadline remain immutable.
            if request.progressive_tooltip && request.tooltip
                && tooltip_value["tooltipAssociation"]["state"]=="inventory-primary"
                && tooltip_value["tooltip"]["found"]["name"].is_string() {
                let mut partial=tooltip_value.clone();
                partial["atMs"]=serde_json::json!(request.at_ms);
                partial["tooltipPartial"]=serde_json::json!(true);
                partial["shopDeferred"]=serde_json::json!(true);
                partial["ocrMs"]=serde_json::json!(started.elapsed().as_secs_f64()*1000.0);
                partial["gameArea"]=serde_json::to_value(location.as_ref().map(|l|l.area))?;
                partial["gameGuards"]=serde_json::to_value(location.as_ref().map(|l|&l.guards))?;
                partial["gameFooter"]=serde_json::to_value(location.as_ref().map(|l|l.footer))?;
                partial["readerStages"]=serde_json::json!({"shopMs":0.0,"componentMs":0.0,"tooltipMs":tooltip_ms});
                writeln!(stdout,"{partial}")?;
                stdout.flush()?;
            }
            let shop_reader=reader.get_or_insert_with(PlayerShopReader::bundled);
            let shop_started=Instant::now();
            let scope=request.capture_generation.zip(request.shop_epoch);
            let cached=page_cache.get(&capture,scope,request.shop_area);
            let cache_hit=cached.is_some();
            let (mut shop_reading,cached_components)=match cached {
                Some((reading,components))=>(reading,Some(components)),
                None=>(shop_panes::read(&capture,shop_reader,&mut price_recovery),None),
            };
            let shop_ms=shop_started.elapsed().as_secs_f64()*1000.0;
            // Return already complete ordinary rows before costly missing-line
            // recovery. Only explicit shop-only requests opt into this protocol;
            // inventory reads and complete/cache-hit pages remain one reply.
            if request.progressive_shop && !request.tooltip && !cache_hit && request.shop_area.is_some()
                && request.shop_recovery.unwrap_or(true)
                && shop_reading.shop.as_ref().is_some_and(|shop|
                    shop.rows.iter().any(|row| !row.covered && row.name.is_some() && row.price.is_some())
                    && shop.rows.iter().any(|row| row.covered || row.name.is_none() || row.price.is_none())) {
                let mut partial=serde_json::to_value(&shop_reading)?;
                partial["shopPartial"]=serde_json::json!(true);
                partial["ocrMs"]=serde_json::json!(started.elapsed().as_secs_f64()*1000.0);
                partial["gameArea"]=serde_json::to_value(location.as_ref().map(|l| l.area))?;
                partial["gameGuards"]=serde_json::to_value(location.as_ref().map(|l| &l.guards))?;
                partial["gameFooter"]=serde_json::to_value(location.as_ref().map(|l| l.footer))?;
                partial["readerStages"]=serde_json::json!({"shopMs":shop_ms,"componentMs":0.0,"tooltipMs":0.0});
                writeln!(stdout,"{partial}")?;
                stdout.flush()?;
            }
            let components_started=Instant::now();
            let recovered=cached_components.unwrap_or_else(||name_recovery.apply(&capture,&mut shop_reading,
                request.shop_area.filter(|_|request.shop_recovery.unwrap_or(true))));
            if !cache_hit {page_cache.store(&capture,scope,request.shop_area,&shop_reading,&recovered);}
            let component_ms=components_started.elapsed().as_secs_f64()*1000.0;
            let mut value = serde_json::to_value(shop_reading)?;
            value["shopCached"]=serde_json::json!(cache_hit);
            if let Some(rows)=value.get_mut("shop").and_then(|s|s.get_mut("rows"))
                .and_then(serde_json::Value::as_array_mut) {
                for recovered in recovered {
                    for row in rows.iter_mut() {
                        if row["area"]["x"].as_i64()==Some(i64::from(recovered.row.x))
                            && row["area"]["y"].as_i64()==Some(i64::from(recovered.row.y)) {
                            if let Some(price)=recovered.price {
                                row["priceArea"]=serde_json::to_value(price)?;
                                if let Some(value)=recovered.price_value {
                                    row["priceValueArea"]=serde_json::to_value(value)?;
                                }
                                if let Some(text)=recovered.price_text.as_ref() {
                                    row["priceText"]=serde_json::to_value(text)?;
                                }
                            } else {
                                row["nameOnly"]=serde_json::json!(true);
                            }
                            row["nameArea"]=serde_json::to_value(recovered.name)?;
                        }
                    }
                }
            }
            if let Some(tooltip)=tooltip_value.as_object() {
                value.as_object_mut().unwrap().extend(tooltip.clone());
            }
            value["readerStages"]=serde_json::json!({"shopMs":shop_ms,"componentMs":component_ms,
                "tooltipMs":tooltip_ms});
            value["ocrMs"] = serde_json::json!(started.elapsed().as_secs_f64() * 1000.0);
            value["gameArea"] = serde_json::to_value(location.as_ref().map(|l| l.area))?;
            value["gameGuards"] = serde_json::to_value(location.as_ref().map(|l| &l.guards))?;
            value["gameFooter"] = serde_json::to_value(location.as_ref().map(|l| l.footer))?;
            Ok(value)
        })();
        let value = result.unwrap_or_else(|err| serde_json::json!({"error":err.to_string()}));
        if writeln!(stdout, "{value}")
            .and_then(|_| stdout.flush())
            .is_err()
        {
            break;
        }
    }
}

fn mask_owned_surfaces(frame: &mut Frame, origin: ScreenPoint, regions: &[Rect]) {
    // Only independent Lupin editor surfaces are supplied. Locator proofs were
    // read from the original capture; the editor must never cover those proofs.
    mask_regions(frame,origin,regions,8);
}

fn annotation_rectangles(frame: &Frame,origin: ScreenPoint,regions: &[Rect]) -> Vec<tooltip_frame::BoxRect> {
    regions.iter().take(64).filter_map(|r| {
        let left=(i64::from(r.x)-i64::from(origin.x)).clamp(0,i64::from(frame.width)) as u32;
        let top=(i64::from(r.y)-i64::from(origin.y)).clamp(0,i64::from(frame.height)) as u32;
        let right=(i64::from(r.x)+i64::from(r.width)-i64::from(origin.x)).clamp(0,i64::from(frame.width)) as u32;
        let bottom=(i64::from(r.y)+i64::from(r.height)-i64::from(origin.y)).clamp(0,i64::from(frame.height)) as u32;
        (right>left&&bottom>top).then_some(tooltip_frame::BoxRect{x:left,y:top,w:right-left,h:bottom-top})
    }).collect()
}

fn mask_regions(frame: &mut Frame, origin: ScreenPoint, regions: &[Rect],limit: usize) {
    for rect in regions.iter().take(limit) {
        let left=(i64::from(rect.x)-i64::from(origin.x)).clamp(0,i64::from(frame.width)) as u32;
        let top=(i64::from(rect.y)-i64::from(origin.y)).clamp(0,i64::from(frame.height)) as u32;
        let right=(i64::from(rect.x)+i64::from(rect.width)-i64::from(origin.x)).clamp(0,i64::from(frame.width)) as u32;
        let bottom=(i64::from(rect.y)+i64::from(rect.height)-i64::from(origin.y)).clamp(0,i64::from(frame.height)) as u32;
        for y in top..bottom {
            for x in left..right {
                let at=((y*frame.width+x)*4) as usize;
                frame.rgba[at..at+4].copy_from_slice(&[0,0,0,255]);
            }
        }
    }
}

#[cfg(test)]
mod writer_mask_tests {
    use super::*;

    #[test]
    fn masks_only_owned_pixels_with_a_nonzero_roi_origin() {
        let mut frame=Frame{width:10,height:8,rgba:vec![200;10*8*4],at_ms:0};
        mask_owned_surfaces(&mut frame,ScreenPoint{x:30,y:40},&[
            Rect{x:33,y:42,width:3,height:2},Rect{x:0,y:0,width:2,height:2},
        ]);
        for y in 0..8 {
            for x in 0..10 {
                let at=(y*10+x)*4;
                assert_eq!(&frame.rgba[at..at+4],if (3..6).contains(&x) && (2..4).contains(&y) {&[0,0,0,255]} else {&[200;4]});
            }
        }
    }

    #[test]
    fn clips_large_rectangles_to_the_capture() {
        let mut frame=Frame{width:3,height:2,rgba:vec![200;3*2*4],at_ms:0};
        mask_owned_surfaces(&mut frame,ScreenPoint{x:50,y:60},&[Rect{x:0,y:0,width:u32::MAX,height:u32::MAX}]);
        assert!(frame.rgba.chunks(4).all(|pixel|pixel==[0,0,0,255]));
    }

    #[test]
    fn annotation_geometry_clips_to_the_analysis_origin_and_is_bounded() {
        let frame=Frame{width:10,height:8,rgba:vec![200;10*8*4],at_ms:0};
        let owned=annotation_rectangles(&frame,ScreenPoint{x:30,y:40},&[
            Rect{x:28,y:42,width:8,height:9},Rect{x:90,y:90,width:2,height:2}]);
        assert_eq!(owned,vec![tooltip_frame::BoxRect{x:0,y:2,w:6,h:6}]);
        let many:Vec<_>=(0..100).map(|_|Rect{x:30,y:40,width:1,height:1}).collect();
        assert_eq!(annotation_rectangles(&frame,ScreenPoint{x:30,y:40},&many).len(),64);
    }
}
