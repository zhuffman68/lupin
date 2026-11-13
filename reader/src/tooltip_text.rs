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

/// Recognition cache only; every reply still needs fresh source/title proofs.
/// Exact captured crop bytes include every colour and antialiasing fringe.
#[derive(Default)]
pub struct AlternativeTitles {
    cache: VecDeque<(Vec<u8>,Vec<String>)>,
}

/// Reuse a complete, already recognized marker title only. The selector still
/// proves the current source/pane; this cache supplies neither source authority
/// nor a name for changed ink. Cold reads retain the ordinary one-pass reader.
#[derive(Default)]
pub struct MarkerTitles {
    cache: VecDeque<(Vec<u8>,ScreenRect,String)>,
}

fn title_local(capture:&ItemCapture,area:ScreenRect)->Option<(u32,u32)> {
    let x=i64::from(area.x)-i64::from(capture.origin.x);
    let y=i64::from(area.y)-i64::from(capture.origin.y);
    if x<0 || y<0 || !(40..=1440).contains(&area.width) || !(8..=64).contains(&area.height)
        || u64::from(area.width)*u64::from(area.height)>65_536
        || x+i64::from(area.width)>i64::from(capture.frame.width)
        || y+i64::from(area.height)>i64::from(capture.frame.height) {return None}
    Some((x as u32,y as u32))
}

fn title_ink(capture:&ItemCapture,area:ScreenRect)->Option<GrayImage> {
    let (x,y)=title_local(capture,area)?;
    Some(GrayImage::from_fn(area.width,area.height,|col,row| {
        let light=crate::tooltip_surface::title_light(crate::tooltip_surface::rgb(&capture.frame,x+col,y+row));
        Luma([light.map_or(255,|v|255-((i32::from(v)-130)*255/90).clamp(0,255)) as u8])
    }))
}

fn marker_key(capture:&ItemCapture,area:ScreenRect)->Option<Vec<u8>> {
    // Match the current-title proof's 150-light ink policy: only dark native
    // background can vary. All included glyph colours/positions remain exact.
    let (x,y)=title_local(capture,area)?;
    let mut key=Vec::with_capacity((area.width*area.height*4+8) as usize);let mut strokes=0;
    key.extend_from_slice(&area.width.to_le_bytes());key.extend_from_slice(&area.height.to_le_bytes());
    for row in y..y+area.height {for col in x..x+area.width {
        let at=((row*capture.frame.width+col)*4) as usize;
        if crate::tooltip_surface::title_light(crate::tooltip_surface::rgb(&capture.frame,col,row)).is_some_and(|v|v>=150) {
            strokes+=1;key.extend_from_slice(&capture.frame.rgba[at..at+4]);
        } else {key.extend_from_slice(&[0;4]);}
    }}
    (strokes>=16).then_some(key)
}

impl MarkerTitles {
    pub fn get(&self,capture:&ItemCapture,area:ScreenRect)->Option<ItemTooltip> {
        let key=marker_key(capture,area)?;
        let (_,relative,name)=self.cache.iter().find(|(old,_,_)|*old==key)?;
        let rect=ScreenRect{x:area.x+relative.x,y:area.y+relative.y,width:relative.width,height:relative.height};
        if rect.x<capture.origin.x || rect.y<capture.origin.y
            || i64::from(rect.x)+i64::from(rect.width)>i64::from(capture.origin.x)+i64::from(capture.frame.width)
            || i64::from(rect.y)+i64::from(rect.height)>i64::from(capture.origin.y)+i64::from(capture.frame.height) {return None}
        Some(ItemTooltip::Found{area:rect,name:Some(name.clone())})
    }

    pub fn remember(&mut self,capture:&ItemCapture,area:ScreenRect,value:&Value) {
        let Ok(ItemTooltip::Found{area:found,name:Some(name)})=serde_json::from_value(value.clone()) else {return};
        // The measured glyph lane must contain the complete name and its ending.
        // Only its decorative bullet may extend left of that lane.
        if name.len()>1024 || found.x<area.x-16 || found.y<area.y || found.width<40 || found.height<8
            || i64::from(found.x)+i64::from(found.width)>i64::from(area.x)+i64::from(area.width)
            || i64::from(found.y)+i64::from(found.height)>i64::from(area.y)+i64::from(area.height) {return}
        let Some(key)=marker_key(capture,area) else {return};
        let relative=ScreenRect{x:found.x-area.x,y:found.y-area.y,width:found.width,height:found.height};
        if self.cache.len()>=16 {self.cache.pop_front();}
        self.cache.push_back((key,relative,name));
    }
}

impl AlternativeTitles {
    pub fn read(&mut self,frame:&Frame,origin:ScreenPoint,found:&Value,marker_title:bool)->Vec<String> {
        let Some(key)=alternative_key(frame,origin,found,marker_title) else {return Vec::new()};
        if let Some((_,value))=self.cache.iter().find(|(old,_)|*old==key) {return value.clone()}
        let value=alternatives(frame,origin,found,marker_title);
        if self.cache.len()>=32 {self.cache.pop_front();}
        self.cache.push_back((key,value.clone()));value
    }
}

fn alternative_key(frame:&Frame,origin:ScreenPoint,found:&Value,marker_title:bool)->Option<Vec<u8>> {
    let area=found.get("area")?;
    let x=area["x"].as_i64()?.checked_sub(i64::from(origin.x))?;
    let y=area["y"].as_i64()?.checked_sub(i64::from(origin.y))?;
    let w=u32::try_from(area["width"].as_u64()?).ok()?;
    let h=u32::try_from(area["height"].as_u64()?).ok()?;
    if x<0 || y<0 || !(40..=720).contains(&w) || !(8..=32).contains(&h)
        || x+w as i64>i64::from(frame.width) || y+h as i64>i64::from(frame.height) {return None}
    let mut key=Vec::with_capacity((w*h*4+9) as usize);
    key.extend_from_slice(&w.to_le_bytes());key.extend_from_slice(&h.to_le_bytes());
    key.push(u8::from(marker_title));
    for row in y as u32..y as u32+h {
        let start=((row*frame.width+x as u32)*4) as usize;
        key.extend_from_slice(frame.rgba.get(start..start+(w*4) as usize)?);
    }
    Some(key)
}

impl PrimaryTitles {
    pub fn read(&mut self,capture:&ItemCapture,area:ScreenRect)->Option<ItemTooltip> {
        let ink=title_ink(capture,area)?;
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

#[cfg(test)]
mod tests {
    use super::*;

    fn marker_fixture()->(ItemCapture,ScreenRect,Value) {
        let mut frame=Frame{width:240,height:120,rgba:[30,30,70,255].repeat(240*120),at_ms:1};
        for y in 18..28 {for x in [30,42,56,70,88] {
            for dx in 0..3 {let at=((y*240+x+dx)*4) as usize;frame.rgba[at..at+3].copy_from_slice(&[240;3]);}
        }}
        let capture=ItemCapture{frame,origin:ScreenPoint{x:100,y:50},pointer:ScreenPoint{x:10,y:10}};
        let area=ScreenRect{x:120,y:64,width:160,height:20};
        let value=serde_json::to_value(ItemTooltip::Found{
            area:ScreenRect{x:113,y:66,width:84,height:12},name:Some("Fixture item".into())}).unwrap();
        (capture,area,value)
    }

    #[test]
    fn marker_cache_rebases_the_original_complete_name_and_rejects_changed_ink() {
        let (capture,area,value)=marker_fixture();let mut cache=MarkerTitles::default();
        assert!(cache.get(&capture,area).is_none());cache.remember(&capture,area,&value);
        assert_eq!(serde_json::to_value(cache.get(&capture,area).unwrap()).unwrap(),value);
        let mut moved=capture.clone();moved.origin=ScreenPoint{x:500,y:-20};
        let moved_area=ScreenRect{x:520,y:-6,..area};
        let Some(ItemTooltip::Found{area:found,name})=cache.get(&moved,moved_area) else {panic!("unchanged complete title lost")};
        assert_eq!((found.x,found.y,found.width,found.height),(513,-4,84,12));assert_eq!(name.as_deref(),Some("Fixture item"));
        let mut background=capture.clone();let at=(20*240+175)*4;
        background.frame.rgba[at..at+3].copy_from_slice(&[50,40,90]);
        assert!(cache.get(&background,area).is_some());
        for (x,colour) in [(30,[30,30,70]),(170,[240;3])] {
            let mut changed=capture.clone();let at=(20*240+x)*4;
            changed.frame.rgba[at..at+3].copy_from_slice(&colour);
            assert!(cache.get(&changed,area).is_none());
        }
        assert!(cache.get(&capture,ScreenRect{width:161,..area}).is_none());
        let mut hidden=capture.clone();hidden.frame.rgba.fill(0);
        assert!(cache.get(&hidden,area).is_none());
    }

    #[test]
    fn marker_cache_is_bounded_and_cannot_remember_a_clipped_or_unknown_title() {
        let (capture,area,value)=marker_fixture();let mut cache=MarkerTitles::default();
        for value in [serde_json::json!("none"),serde_json::json!({"found":{"name":null,"area":{"x":113,"y":66,"width":84,"height":12}}}),
            serde_json::json!({"found":{"name":"Cut item","area":{"x":113,"y":66,"width":240,"height":12}}})] {
            cache.remember(&capture,area,&value);assert!(cache.cache.is_empty());
        }
        for offset in 0..20 {
            let mut changed=capture.clone();let at=(30*240+120+offset)*4;
            changed.frame.rgba[at..at+3].copy_from_slice(&[240;3]);
            cache.remember(&changed,area,&value);
        }
        assert_eq!(cache.cache.len(),16);
        assert!(cache.get(&capture,area).is_none());
    }

    #[test]
    fn retry_cache_binds_every_current_title_pixel_size_and_marker_policy() {
        let mut frame=Frame{width:100,height:50,rgba:vec![255;100*50*4],at_ms:1};
        let origin=ScreenPoint{x:20,y:30};
        let found=serde_json::json!({"area":{"x":30,"y":40,"width":60,"height":17}});
        let key=alternative_key(&frame,origin,&found,true).unwrap();
        frame.at_ms=2;
        assert_eq!(alternative_key(&frame,origin,&found,true).unwrap(),key);
        frame.rgba[(49*100+99)*4]=0;
        assert_eq!(alternative_key(&frame,origin,&found,true).unwrap(),key);
        frame.rgba[(15*100+20)*4]=0;
        assert_ne!(alternative_key(&frame,origin,&found,true).unwrap(),key);
        assert_ne!(alternative_key(&frame,origin,&found,false).unwrap(),key);
        let invalid=serde_json::json!({"area":{"x":30,"y":40,"width":u64::MAX,"height":17}});
        assert!(alternative_key(&frame,origin,&invalid,true).is_none());
    }
}
