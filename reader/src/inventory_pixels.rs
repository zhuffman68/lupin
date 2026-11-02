//! Inventory identity excludes only verified native new-item decoration.

pub(crate) fn same_header(before: &[u8],after: &[u8],width: u32,tab: u32) -> bool {
    if before.len()!=after.len() || !(130..=435).contains(&width) || tab>=6
        || before.len()%(width as usize*3)!=0 {return false}
    let height=before.len()/(width as usize*3);let scale=width as f32/207.0;
    let x0=(((6+33*tab) as f32*scale).floor() as usize).saturating_sub(1);
    let x1=((35+33*tab) as f32*scale).ceil() as usize+1;
    let y0=((22.0*scale).floor() as usize).saturating_sub(1);let y1=(41.0*scale).ceil() as usize+1;
    if x1>width as usize || y1>height {return false}
    let corner=((2.0*scale).ceil() as usize+1).clamp(2,6);
    let mut old_selected=0;let mut new_selected=0;
    let selected=|p: &[u8]| {let (r,g,b)=(i32::from(p[0]),i32::from(p[1]),i32::from(p[2]));
        r>=180&&r-g>=8&&b-g>=4&&g>=45&&b>=60};
    for y in 0..height {for x in 0..width as usize {
        if y<corner&&(x<corner||x>=width as usize-corner) {continue}
        let offset=(y*width as usize+x)*3;let a=&before[offset..offset+3];let b=&after[offset..offset+3];
        if !(x0..x1).contains(&x)||!(y0..y1).contains(&y) {
            if a!=b {return false}continue
        }
        old_selected+=usize::from(selected(a));new_selected+=usize::from(selected(b));
        let va=[255-i32::from(a[0]),255-i32::from(a[1]),255-i32::from(a[2])];
        let vb=[255-i32::from(b[0]),255-i32::from(b[1]),255-i32::from(b[2])];
        let ma=*va.iter().max().unwrap();let mb=*vb.iter().max().unwrap();
        let (lo,hi)=(ma.min(mb),ma.max(mb));
        if (lo==0&&hi>2)||(lo>0&&hi>4*lo)
            || (0..3).any(|i|(va[i]*mb-vb[i]*ma).abs()>3*(ma+mb)) {return false}
    }}
    let minimum=((64.0*scale*scale).round() as usize).max(24);
    old_selected>=minimum&&new_selected>=minimum
}

#[cfg(test)]
mod tests {
    use super::*;
    fn header() -> Vec<u8> {
        let mut pixels=vec![245;207*45*3];
        for y in 22..41 {for x in 6..35 {pixels[(y*207+x)*3..(y*207+x)*3+3].copy_from_slice(&[234,101,129])}}
        for y in 25..31 {pixels[(y*207+12)*3..(y*207+12)*3+3].copy_from_slice(&[255;3])}
        pixels
    }
    #[test]
    fn selected_tab_whitening_preserves_ink_and_all_other_header_pixels() {
        let before=header();let mut after=before.clone();
        for y in 22..41 {for x in 6..35 {for c in 0..3 {
            let at=(y*207+x)*3+c;after[at]=(255.0-(255.0-f32::from(before[at]))*0.4).round() as u8;
        }}}
        assert!(same_header(&before,&after,207,0));assert!(same_header(&after,&before,207,0));
        for (x,y) in [(12,7),(188,7),(45,28),(12,26)] {
            let mut bad=after.clone();bad[(y*207+x)*3..(y*207+x)*3+3].copy_from_slice(&[10,240,20]);
            assert!(!same_header(&before,&bad,207,0));
        }
        assert!(!same_header(&before,&vec![255;before.len()],207,0));
    }
}
