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
    markers: tooltip_text::MarkerTitles,
    selector: tooltip_association::Selector,
    alternatives: tooltip_text::AlternativeTitles,
}

impl TooltipReader {
    pub fn read(&mut self,capture:&ShopCapture,pointer:ScreenPoint,retry:bool,inventory_only:bool,
                annotations:&[Rect],scale_hint:Option<f32>)
        -> Result<Value,Box<dyn std::error::Error>> {
        let mut value=json!({});
        // Geometry borrows the immutable submitted frame; only the selected
        // analysis panel needs owned pixels. The original remains shop evidence.
        let (prepared,markers)=tooltip_surface::prepare(&capture.frame);
        let owned=annotation_rectangles(&capture.frame,capture.origin,annotations);
        let association=self.selector.select_frame(&capture.frame,capture.origin,pointer,&markers,scale_hint,&owned);
        let primary_header=association.primary_header.map(|header|minerva_core::ScreenRect{
            x:capture.origin.x+header.x as i32,y:capture.origin.y+header.y as i32,
            width:header.w,height:header.h});
        let marker_source=association.metadata["titleMarker"].as_bool()==Some(true);
        value["tooltipAssociation"]=association.metadata;
        if inventory_only {
            value["inventoryProbe"]=json!({"absent":value["tooltipAssociation"]["source"].is_null(),
                "area":tooltip_association::inventory_probe_area(&capture.frame,capture.origin,pointer)});
            if value["tooltipAssociation"]["state"]!="inventory-primary" {
                value["tooltip"]=json!("none");
                return Ok(value);
            }
        }
        if association.rejected {
            value["tooltip"]=json!("none");
            return Ok(value);
        }
        let source=prepared.as_ref().unwrap_or(&capture.frame);
        let (frame,origin,pointer)=if let Some(rect)=association.panel {
            let mut rgba=Vec::with_capacity((rect.w*rect.h*4) as usize);
            for y in rect.y..rect.y+rect.h {
                let start=((y*source.width+rect.x)*4) as usize;
                rgba.extend_from_slice(&source.rgba[start..start+(rect.w*4) as usize]);
            }
            let origin=ScreenPoint{x:capture.origin.x+rect.x as i32,y:capture.origin.y+rect.y as i32};
            (Frame{width:rect.w,height:rect.h,rgba,at_ms:source.at_ms},origin,
             ScreenPoint{x:origin.x+(rect.w.min(32)/2) as i32,y:origin.y+(rect.h.min(40)/2) as i32})
        } else {(prepared.unwrap_or_else(||capture.frame.clone()),capture.origin,pointer)};
        let mut tooltip_capture=ItemCapture{frame,origin,pointer};
        if !owned.is_empty(){mask_regions(&mut tooltip_capture.frame,tooltip_capture.origin,annotations,64);}
        let direct=primary_header.and_then(|header|if marker_source {
            self.markers.get(&tooltip_capture,header)
        } else {self.primary.read(&tooltip_capture,header)});
        let cached=marker_source && direct.is_some();
        value["tooltipCacheHit"]=json!(cached);
        let mut marker_title=marker_source || primary_header.is_none();
        if let Some(title)=direct {
            value["tooltip"]=serde_json::to_value(title)?;
        } else if primary_header.is_some() && !marker_source {
            // A hidden marker may not reopen nearest-comparison recognition.
            value["tooltip"]=json!("none");
        } else {
            let reader=self.reader.get_or_insert_with(ItemTooltipReader::bundled);
            value["tooltip"]=serde_json::to_value(reader.read(&tooltip_capture).tooltip)?;
            if !value["tooltip"]["found"]["name"].is_string() {
                let popup=if let Some(header)=primary_header {
                    // A source-bound description already has a measured title
                    // lane. Read that complete lane instead of searching a
                    // generic popup; a wide name must not become stat text or
                    // the equipped comparison merely because its bullet fails.
                    self.primary.read(&tooltip_capture,header)
                } else if let Some(title)=self.centered.read(&tooltip_capture) {
                    marker_title=false;Some(title)
                } else {tooltip_text::popup(reader,&mut tooltip_capture)};
                if let Some(popup)=popup {
                    value["tooltip"]=serde_json::to_value(popup)?;
                    if primary_header.is_none() {value["tooltip"]["found"]["pinned"]=json!(true);}
                }
            }
        }
        if retry && marker_source && let Some(header)=primary_header {
            // Retrying only the first measured fragment cannot recover a wide
            // title cut short at an OCR word gap. Two agreeing bounded reads
            // of the current full header can; no catalog guessing is involved.
            if let Some(complete)=self.primary.read(&tooltip_capture,header) {
                value["tooltip"]=serde_json::to_value(complete)?;
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
        if marker_source && (!cached || retry) && let Some(header)=primary_header {
            self.markers.remember(&tooltip_capture,header,&value["tooltip"]);
        }
        if association.panel.is_none() {
            value["tooltipPanel"]=tooltip_frame::export_for_title(
                &capture.frame,capture.origin,
                &value["tooltip"]["found"]["area"],scale_hint.unwrap_or(1.0)).unwrap_or(Value::Null);
        }
        Ok(value)
    }
}
