//! A bounded second look at an already located name line, never a scene text search.
use image::{GrayImage,Luma,imageops::FilterType};
use minerva_core::{Frame,ScreenPoint,ScreenRect,ItemCapture,ItemTooltip,ItemTooltipReader};
use serde_json::Value;
use std::collections::VecDeque;

/// Only the association selector's independently framed primary header enters
/// this path. It never searches for another panel or reuses an old item name.
#[derive(Default)]
pub struct PrimaryTitles {
    cache: VecDeque<(Vec<u8>,Option<String>)>,
}

impl PrimaryTitles {
    pub fn read(&mut self,capture:&ItemCapture,area:ScreenRect)->Option<ItemTooltip> {
        let x=i64::from(area.x)-i64::from(capture.origin.x);
        let y=i64::from(area.y)-i64::from(capture.origin.y);
        if x<0 || y<0 || !(40..=1440).contains(&area.width) || !(8..=64).contains(&area.height)
            || u64::from(area.width)*u64::from(area.height)>65_536
            || x+ i64::from(area.width)>i64::from(capture.frame.width)
            || y+ i64::from(area.height)>i64::from(capture.frame.height) {return None}
        let x=x as u32;let y=y as u32;
        let ink=GrayImage::from_fn(area.width,area.height,|col,row| {
            let light=crate::tooltip_surface::title_light(crate::tooltip_surface::rgb(&capture.frame,x+col,y+row));
            Luma([light.map_or(255,|v|255-((i32::from(v)-130)*255/90).clamp(0,255)) as u8])
        });
        let points:Vec<_>=ink.enumerate_pixels().filter(|(_,_,p)|p.0[0]<150).map(|(x,y,_)|(x,y)).collect();
        if points.len()<16 {return None}
        let left=points.iter().map(|p|p.0).min()?;let right=points.iter().map(|p|p.0).max()?+1;
        let top=points.iter().map(|p|p.1).min()?;let bottom=points.iter().map(|p|p.1).max()?+1;
        let scale=area.height as f32/17.0;
        // A cut prefix/suffix or a stat/icon lane is not a complete title.
        if left>(12.0*scale).ceil() as u32 || right-left<20 || bottom-top<8
            || area.width-right<(4.0*scale).ceil().max(3.0) as u32 {return None}
        let ink=image::imageops::crop_imm(&ink,left,top,right-left,bottom-top).to_image();
        let mut key=Vec::with_capacity(ink.as_raw().len()+8);
        key.extend_from_slice(&ink.width().to_le_bytes());key.extend_from_slice(&ink.height().to_le_bytes());
        key.extend_from_slice(ink.as_raw());
        let name=if let Some((_,name))=self.cache.iter().find(|(old,_)|*old==key) {name.clone()} else {
            let first=crate::text::read_scaled(&ink,2,FilterType::Triangle);
            let second=crate::text::read_scaled(&ink,3,FilterType::Triangle);
            let normalized=|text:&str|text.split_whitespace().collect::<Vec<_>>().join(" ").to_lowercase();
            let name=first.filter(|a|second.as_ref().is_some_and(|b|normalized(a)==normalized(b)));
            if self.cache.len()>=16 {self.cache.pop_front();}
            self.cache.push_back((key,name.clone()));name
        }?;
        Some(ItemTooltip::Found{area:ScreenRect{x:area.x+left as i32,y:area.y+top as i32,
            width:right-left,height:bottom-top},name:Some(name)})
    }
}

/// A clicked item link can open its description far from the pointer. Probe
/// captured pixels only; the UI also validates its name and description panel.
pub fn popup(reader:&ItemTooltipReader,capture:&mut ItemCapture)->Option<ItemTooltip> {
    let original=capture.pointer;
    let centers=|length:u32|->Vec<i32> {
        if length<=1280 {return vec![(length/2) as i32]}
        let mut points:Vec<i32>=(640..length).step_by(1280).map(|x|x as i32).collect();
        let end=length.saturating_sub(640) as i32;
        if points.last().copied()!=Some(end) {points.push(end)}
        points
    };
    let mut result=None;
    'search:for y in centers(capture.frame.height).into_iter().take(3) {
        for x in centers(capture.frame.width).into_iter().take(3) {
            capture.pointer=ScreenPoint{x:x+capture.origin.x,y:y+capture.origin.y};
            let candidate=reader.read(capture).tooltip;
            if matches!(&candidate,ItemTooltip::Found{name:Some(_),..}) {result=Some(candidate);break 'search}
        }
    }
    capture.pointer=original;result
}

pub fn alternatives(frame:&Frame,origin:ScreenPoint,found:&Value,marker_title:bool)->Vec<String> {
    let read = || -> Option<Vec<String>> {
        let area=found.get("area")?;
        let x=area["x"].as_i64()?.checked_sub(i64::from(origin.x))?;
        let y=area["y"].as_i64()?.checked_sub(i64::from(origin.y))?;
        let w=area["width"].as_u64()? as u32;
        let h=area["height"].as_u64()? as u32;
        if x<0 || y<0 || !(40..=720).contains(&w) || !(8..=32).contains(&h)
            || x as u32+w>frame.width || y as u32+h>frame.height {return None}
        // Preserve `found.area` for panel geometry and pixel proofs. Only this
        // independent OCR crop excludes a structurally verified leading marker.
        let glyph_x=crate::tooltip_surface::name_glyph_start(frame,x as u32,y as u32,w,h,marker_title);
        let glyph_w=w-(glyph_x-x as u32);
        let mut results=Vec::new();
        for (threshold,scale,filter) in [(None,3,FilterType::Triangle),(Some(150),2,FilterType::Triangle)] {
            let ink=GrayImage::from_fn(glyph_w,h,|col,row| {
                let at=(((y as u32+row)*frame.width+glyph_x+col)*4) as usize;
                let p=&frame.rgba[at..at+3];let light=crate::tooltip_surface::title_light([p[0],p[1],p[2]]);
                let neutral=light.is_some();let luma=i32::from(light.unwrap_or(0));
                let value=match threshold {
                    Some(t)=> if neutral && luma>=t {0} else {255},
                    None=> if neutral {255-((luma-100)*255/120).clamp(0,255)} else {255}
                };
                Luma([value as u8])
            });
            if let Some(text)=crate::text::read_scaled(&ink,scale,filter) {
                if !results.contains(&text) {results.push(text)}
            }
        }
        Some(results)
    };
    read().unwrap_or_default()
}
