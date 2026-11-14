/* Shared WebKitGTK/WebView2 sighting query. Item keys are validated before use.
 * Polling starts one same-origin request, never another request per tick.
 * Keep large sale histories out of IPC and persistent application caches. */
#define LISTING_SCRIPT_HEAD "(()=>{const id='"
#define LISTING_SCRIPT_TAIL "';" \
"if(!window.MarketData?.doc)return null;" \
"if(!window.__lupinListings){window.__lupinListings={result:null};" \
"(async()=>{try{" \
"const doc=window.MarketData.doc;" \
"if(doc.market!=='Classic World'||doc.preview!==false||doc.kind!=='list'||doc.version!==2)throw Error();" \
"const matches=Array.isArray(doc.items)?doc.items.filter(x=>x.id===id):[];" \
"if(matches.length!==1)throw Error();const c=matches[0];" \
"const url='/data/markets/Classic%20World/item/'+id.replace(':','_')+'.json';" \
"const r=await fetch(url,{cache:'no-cache',credentials:'omit',redirect:'error'});" \
"if(!r.ok||!r.body)throw Error();" \
"const reader=r.body.getReader(),decoder=new TextDecoder('utf-8',{fatal:true});let body='',size=0;" \
"for(;;){const part=await reader.read();if(part.done)break;size+=part.value.byteLength;" \
"if(size>33554432){await reader.cancel();throw Error();}body+=decoder.decode(part.value,{stream:true});}" \
"body+=decoder.decode();const d=JSON.parse(body);if(!Array.isArray(d.listings))throw Error();" \
"window.__lupinListings.result={version:d.version,kind:d.kind,market:d.market,id:d.id,generated_at:d.generated_at," \
"catalog:{id:c.id,catalogId:c.catalogId,name:c.name,unitBasis:c.unitBasis}," \
"listings:d.listings.slice(0,500),truncated:d.listings.length>500};" \
"}catch(_){window.__lupinListings.result={listingError:'unavailable'};}})();}" \
"return window.__lupinListings.result;})()"

#define LISTING_SELF_TEST "<!doctype html><meta charset=utf-8><script>" \
"const identity='basil:01082000',at=new Date().toISOString();" \
"window.MarketData={doc:{version:2,kind:'list',market:'Classic World',preview:false," \
"items:[{id:identity,catalogId:identity,name:'Work Gloves',unitBasis:'item'}]}};" \
"window.fetch=async()=>new Response(JSON.stringify({version:2,kind:'item',market:'Classic World'," \
"id:identity,generated_at:at,listings:[{seller:'Test seller',location:'Free Market &lt;7&gt;'," \
"channel:3,channelRoom:7,price:15000,qty:1,stock:null,lastSeen:at,up:true}],sales:[{private:'omitted'}]}));" \
"</script>"

static int valid_listing_item(const char *item) {
    const char *digits;
    if (!strncmp(item,"basil:",6)) digits=item+6;
    else if (!strncmp(item,"cash:",5)) digits=item+5;
    else return 0;
    if (strlen(digits)!=8) return 0;
    for (int i=0;i<8;i++) if (digits[i]<'0'||digits[i]>'9') return 0;
    return 1;
}
