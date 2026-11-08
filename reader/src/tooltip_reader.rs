//! Independent inventory-title work. Shop repair must not delay its first reply.
use minerva_core::{Frame,ItemCapture,ItemTooltipReader,ScreenPoint,ShopCapture};
use serde_json::{json,Value};
use crate::{annotation_rectangles,centered_tooltip,game_area::Rect,mask_regions,
    tooltip_association,tooltip_frame,tooltip_surface,tooltip_text};

#[derive(Default)]
pub struct TooltipReader {
    reader: Option<ItemTooltipReader>,
    centered: centered_tooltip::CenteredTitles,
    primary: tooltip_text::PrimaryTitles,
    selector: tooltip_association::Selector,
    alternatives: tooltip_text::AlternativeTitles,
}

impl TooltipReader {
    pub fn read(&mut self,capture:&ShopCapture,pointer:ScreenPoint,retry:bool,
                annotations:&[Rect],scale_hint:Option<f32>)
        -> Result<Value,Box<dyn std::error::Error>> {
        let mut value=json!({});
        // Own just this immutable request's pixels. The shop stage keeps the
        // original image and runs after independently verified inventory work.
        let mut tooltip_capture=ItemCapture {
            frame:Frame{width:capture.frame.width,height:capture.frame.height,
                rgba:capture.frame.rgba.clone(),at_ms:capture.frame.at_ms},
            origin:capture.origin,pointer,
        };
        let (prepared,markers)=tooltip_surface::prepare(&tooltip_capture.frame);
        let owned=annotation_rectangles(&tooltip_capture.frame,tooltip_capture.origin,annotations);
        let association=self.selector.select_with_exclusions(&tooltip_capture,&markers,scale_hint,&owned);
        let mut raw_frame=prepared.map(|frame|std::mem::replace(&mut tooltip_capture.frame,frame));
        if !owned.is_empty() {
            if raw_frame.is_none() {raw_frame=Some(Frame{width:tooltip_capture.frame.width,
                height:tooltip_capture.frame.height,at_ms:tooltip_capture.frame.at_ms,
                rgba:tooltip_capture.frame.rgba.clone()})}
            mask_regions(&mut tooltip_capture.frame,tooltip_capture.origin,annotations,64);
        }
        let primary_header=association.primary_header.map(|header|minerva_core::ScreenRect{
            x:tooltip_capture.origin.x+header.x as i32,y:tooltip_capture.origin.y+header.y as i32,
            width:header.w,height:header.h});
        value["tooltipAssociation"]=association.metadata;
        if association.rejected {
            value["tooltip"]=json!("none");
            return Ok(value);
        }
        if let Some(rect)=association.panel {
            let mut rgba=Vec::with_capacity((rect.w*rect.h*4) as usize);
            for y in rect.y..rect.y+rect.h {
                let start=((y*tooltip_capture.frame.width+rect.x)*4) as usize;
                rgba.extend_from_slice(&tooltip_capture.frame.rgba[start..start+(rect.w*4) as usize]);
            }
            tooltip_capture.frame=Frame{width:rect.w,height:rect.h,rgba,at_ms:tooltip_capture.frame.at_ms};
            tooltip_capture.origin.x+=rect.x as i32;
            tooltip_capture.origin.y+=rect.y as i32;
            // Internal pixel probe only. Never change the OS cursor.
            tooltip_capture.pointer=ScreenPoint{x:tooltip_capture.origin.x+(rect.w.min(32)/2) as i32,
                y:tooltip_capture.origin.y+(rect.h.min(40)/2) as i32};
        }
        let reader=self.reader.get_or_insert_with(ItemTooltipReader::bundled);
        let mut marker_title=primary_header.is_none();
        if let Some(header)=primary_header {
            value["tooltip"]=match self.primary.read(&tooltip_capture,header) {
                Some(title)=>serde_json::to_value(title)?,None=>json!("none"),
            };
        } else {
            value["tooltip"]=serde_json::to_value(reader.read(&tooltip_capture).tooltip)?;
            if !value["tooltip"]["found"]["name"].is_string() {
                let popup=if let Some(title)=self.centered.read(&tooltip_capture) {
                    marker_title=false;Some(title)
                } else {tooltip_text::popup(reader,&mut tooltip_capture)};
                if let Some(popup)=popup {
                    value["tooltip"]=serde_json::to_value(popup)?;
                    value["tooltip"]["found"]["pinned"]=json!(true);
                }
            }
        }
        if retry {
            let found=&value["tooltip"]["found"];
            if found.is_object() {
                value["tooltip"]["found"]["alternatives"]=json!(self.alternatives.read(
                    &tooltip_capture.frame,tooltip_capture.origin,found,marker_title));
            }
            value["tooltipRetried"]=json!(true);
        }
        if association.panel.is_none() {
            value["tooltipPanel"]=tooltip_frame::export_for_title(
                raw_frame.as_ref().unwrap_or(&tooltip_capture.frame),tooltip_capture.origin,
                &value["tooltip"]["found"]["area"],scale_hint.unwrap_or(1.0)).unwrap_or(Value::Null);
        }
        Ok(value)
    }
}
