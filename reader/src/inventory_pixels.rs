//! Inventory identity excludes only verified native new-item decoration.

pub(crate) fn selected_pixel([r,g,b]: [u8;3]) -> bool {
    r>=180 && g>=45 && b>=60 && r.saturating_sub(g)>=8 && (4..55).contains(&b.saturating_sub(g))
}

fn distance_from_white(pixel: &[u8]) -> [i32;3] {
    [255-i32::from(pixel[0]),255-i32::from(pixel[1]),255-i32::from(pixel[2])]
}

fn direction(a:[i32;3],b:[i32;3]) -> bool {
    let ma=a.into_iter().map(i32::abs).max().unwrap();let mb=b.into_iter().map(i32::abs).max().unwrap();
    (0..3).all(|i|(a[i]*mb-b[i]*ma).abs()<=3*(ma+mb))
}

fn tab_row_matches(old: &[u8],new: &[u8],active:bool,fringe:usize,outer_row:bool) -> bool {
    if old==new {return true}
    let width=old.len()/3;let edge=fringe/3+1;
    for (x,(old,new)) in old.chunks_exact(3).zip(new.chunks_exact(3)).enumerate() {
        let a=distance_from_white(old);let b=distance_from_white(new);
        let ma=*a.iter().max().unwrap();let mb=*b.iter().max().unwrap();
        let (lo,hi)=(ma.min(mb),ma.max(mb));
        if (lo==0&&hi>2)||(lo>0&&hi>(if active {6} else {4})*lo) {return false}
        if !direction(a,b) {
            let rim=outer_row||x<edge||x>=width-edge;
            let bright=old.iter().all(|value|*value>=218)||new.iter().all(|value|*value>=218);
            // The stationary native paper can contribute to the tab edge
            // during scaling. Limit the target to that white blend.
            if !rim||!bright||![[2,2,2],[4,4,3],[6,5,5],[8,7,6],[10,9,8]].into_iter().any(|t|
                direction(std::array::from_fn(|i|a[i]-t[i]),std::array::from_fn(|i|b[i]-t[i]))) {return false}
        }
    }
    if active {return true}
    // As in the frontend, the gray glyphs need coherent brightness across
    // the tab face. Leave the antialiased side pixels to the colour check.
    let a=&old[fringe..old.len()-fringe];let b=&new[fringe..new.len()-fringe];
    let sum=|pixels: &[u8]| pixels.iter().map(|p|255-i32::from(*p)).sum::<i32>();
    let (sa,sb)=(sum(a),sum(b));
    a.iter().zip(b).all(|(&x,&y)|((255-i32::from(x))*sb-(255-i32::from(y))*sa).abs()<=3*(sa+sb))
}

pub(crate) fn same_header(before: &[u8],after: &[u8],width: u32,tab: u32) -> bool {
    if before.len()!=after.len() || !(130..=435).contains(&width) || tab>=6
        || before.len()%(width as usize*3)!=0 {return false}
    let height=before.len()/(width as usize*3);let scale=width as f32/207.0;
    let width=width as usize;
    let tabs:[(usize,usize);6]=std::array::from_fn(|index| (
        (((6+33*index) as f32*scale).floor() as usize).saturating_sub(1),
        ((35+33*index) as f32*scale).ceil() as usize+1,
    ));
    let y0=((22.0*scale).floor() as usize).saturating_sub(1);let y1=(41.0*scale).ceil() as usize+1;
    if tabs[5].1>width || y1>height {return false}
    let corner=((2.0*scale).ceil() as usize+1).clamp(2,6);
    let fringe=(scale.ceil() as usize+1)*3;
    let mut old_selected=[0;6];let mut new_selected=[0;6];
    let selected=|row: &[u8]| row.chunks_exact(3).filter(|p|selected_pixel([p[0],p[1],p[2]])).count();
    for (y,(old,new)) in before.chunks_exact(width*3).zip(after.chunks_exact(width*3)).enumerate() {
        if !(y0..y1).contains(&y) {
            let margin=if y<corner {corner*3} else {0};
            if old[margin..old.len()-margin]!=new[margin..new.len()-margin] {return false}
            continue
        }
        let mut end=0;
        for (index,(left,right)) in tabs.into_iter().enumerate() {
            let lo=left*3;let hi=right*3;
            if end<lo&&old[end..lo]!=new[end..lo] {return false}
            let (a,b)=(&old[lo..hi],&new[lo..hi]);
            old_selected[index]+=selected(a);new_selected[index]+=selected(b);
            let outer_row=y-y0<fringe/3+1||y1-1-y<fringe/3+1;
            if !tab_row_matches(a,b,index==tab as usize,fringe,outer_row) {return false}
            end=hi;
        }
        if old[end..]!=new[end..] {return false}
    }
    let minimum=((64.0*scale*scale).round() as usize).max(24);
    (0..6).all(|index|(old_selected[index]>=minimum)==(index==tab as usize)
        &&(new_selected[index]>=minimum)==(index==tab as usize))
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
