"""Lazy, bounded map alignment; retain only coordinates and verification results."""
from concurrent.futures import CancelledError,ThreadPoolExecutor
import hashlib,json,re,time
from PySide6.QtCore import QObject,Signal,Qt,QBuffer,QByteArray,QIODevice
from PySide6.QtGui import QImage,QImageReader,QImageIOHandler
from .http_json import RequestToken,request_scope,get_bytes,get_json
from .reference_data import DAY

PORTALS='https://osmsdataexplorer.com/data/current/portals.json'
RENDERS='https://osmsdataexplorer.com/data/current/map_manifest.json'
PREVIEW_EDGE=512
PREVIEW_BYTES=1024*1024
PREVIEW_NATIVE_PIXELS=16*1024*1024


def geometry_key(row):
    return hashlib.sha256(json.dumps(['projection-v3-portals',row.get('render_url'),row.get('minimap_url'),row.get('portals'),row.get('mobs')],sort_keys=True).encode()).hexdigest()


def verified_portals(row,portals):
    """Use the viewer's native-image coordinates, bound to exact exported exits.

    The caller also verifies that the current map manifest names the same
    content-addressed render. Scripted destinations and spawn-only points do
    not establish a direct connection.
    """
    result=[];seen=set()
    for source in row.get('portals',[]):
        destination=source.get('dest_map_id');kind=source.get('type');name=source.get('name')
        if type(kind) is not int or kind not in (1,2,3) or type(destination) is not int or not 0<=destination<999999999 or not isinstance(name,str) or not name:continue
        matches=[p for p in portals if p.get('name')==name and type(p.get('type')) is int and p.get('type')==kind
                 and str(p.get('dest_map'))==str(destination) and p.get('dest_portal','')==source.get('dest_portal','')]
        if len(matches)!=1:continue
        point=matches[0]
        if any(type(point.get(axis)) is not int or not 0<=point[axis]<=30000 for axis in ('x','y')):continue
        key=(name,kind,destination,point['x'],point['y'])
        if key in seen:continue
        seen.add(key);result.append(dict(name=name,type=kind,dest_map_id=destination,dest_portal=source.get('dest_portal',''),x=point['x'],y=point['y']))
    return result


def preview_png(data):
    """A bounded thumbnail in the verified render's own coordinate system."""
    buffer=QBuffer();buffer.setData(QByteArray(data));buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader=QImageReader(buffer,b'webp');size=reader.size()
    if size.isEmpty() or max(size.width(),size.height())>30000:return None
    if not reader.supportsOption(QImageIOHandler.ImageOption.ScaledSize) and size.width()*size.height()>PREVIEW_NATIVE_PIXELS:return None
    if max(size.width(),size.height())>PREVIEW_EDGE:reader.setScaledSize(size.scaled(PREVIEW_EDGE,PREVIEW_EDGE,Qt.AspectRatioMode.KeepAspectRatio))
    image=reader.read()
    if image.isNull():return None
    if max(image.width(),image.height())>PREVIEW_EDGE:image=image.scaled(PREVIEW_EDGE,PREVIEW_EDGE,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
    output=QBuffer();output.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(output,'PNG'):return None
    raw=bytes(output.data())
    return raw if len(raw)<=PREVIEW_BYTES else None


def alignment(row,portals):
    """The provider's viewer uses these portal positions in native image pixels."""
    matched=[]
    for source in row.get('portals',[]):
        if source.get('type') not in (1,2) or type(source.get('dest_map_id')) is not int:continue
        options=[p for p in portals if p.get('name')==source.get('name') and str(p.get('dest_map'))==str(source['dest_map_id']) and p.get('type')==source['type']]
        if len(options)!=1:continue
        target=options[0]
        if any(type(p.get(axis)) is not int for p in (source,target) for axis in ('x','y')):continue
        matched.append((target['x']-source['x'],target['y']-source['y'],source['x'],source['y']))
    if len({(p[2],p[3]) for p in matched})<2 or len({p[:2] for p in matched})!=1:return None
    return dict(dx=matched[0][0],dy=matched[0][1],anchors=len(matched))


def native_size(data,url):
    match=re.fullmatch(r'https://osmsdataexplorer.com/data/maps/([a-f0-9]{32})\.webp',url or '')
    if not match or not 24<=len(data)<=4*1024*1024 or hashlib.md5(data,usedforsecurity=False).hexdigest()!=match[1]:return None
    buffer=QBuffer();buffer.setData(QByteArray(data));buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    size=QImageReader(buffer,b'webp').size()
    return (size.width(),size.height()) if 0<size.width()<=30000 and 0<size.height()<=30000 else None


def matching_projection(native,minimap):
    """Confirm the minimap is the same full-canvas projection, not a different crop.

    Both palette and terrain-edge evidence must agree. Where the image plugin
    cannot decode at thumbnail resolution, cap the one-time native decode at
    eight million pixels. Uncertain/cropped maps get no markers.
    """
    small_buffer=QBuffer();small_buffer.setData(QByteArray(minimap));small_buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    small_reader=QImageReader(small_buffer);size=small_reader.size()
    if not (8<=size.width()<=512 and 8<=size.height()<=512):return False
    small=small_reader.read()
    if small.isNull():return False
    buffer=QBuffer();buffer.setData(QByteArray(native));buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader=QImageReader(buffer,b'webp');full=reader.size()
    if full.isEmpty() or abs((size.width()/size.height())/(full.width()/full.height())-1)>.025:return False
    if not reader.supportsOption(QImageIOHandler.ImageOption.ScaledSize) and full.width()*full.height()>8*1024*1024:return False
    reader.setScaledSize(size);image=reader.read()
    if image.isNull() or image.size()!=size:return False
    compared=colours=edges=edge_matches=0
    rgb=lambda p:((p>>16)&255,(p>>8)&255,p&255)
    for y in range(1,size.height()-1,2):
        for x in range(1,size.width()-1,2):
            p=small.pixel(x,y);a=rgb(p)
            if (p>>24)<128 or max(a)<45:continue
            b=rgb(image.pixel(x,y));compared+=1
            if max(abs(v-w) for v,w in zip(a,b))<=48:colours+=1
            for dx,dy in ((1,0),(0,1)):
                da=sum(abs(v-w) for v,w in zip(a,rgb(small.pixel(x+dx,y+dy))))
                if da<90:continue
                edges+=1;db=sum(abs(v-w) for v,w in zip(b,rgb(image.pixel(x+dx,y+dy))))
                if db>=60:edge_matches+=1
    return compared>=32 and edges>=12 and colours/compared>=.8 and edge_matches/edges>=.75


class MapGeometry(QObject):
    updated=Signal(int)
    _finished=Signal(object)

    def __init__(self,store,parent=None,*,fetch_bytes=None,fetch_json=None):
        super().__init__(parent);self.store=store;self.fetch_bytes=fetch_bytes or get_bytes;self.fetch_json=fetch_json or get_json
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='lupin-map-geometry');self.pending=None;self.closed=False
        self.preview_folder=store.path.parent/'reference-map-previews-v1';self._preview_key=None;self._preview_image=QImage()
        self._finished.connect(self.finish,Qt.ConnectionType.QueuedConnection)

    def cached(self,row):
        value=self.store.value('map_geometry',{}).get(str(row['id']))
        return value.get('proof') if value and value.get('key')==geometry_key(row) else None

    def preview(self,row):
        key=geometry_key(row)
        if key==self._preview_key:return self._preview_image
        self._preview_key=key;self._preview_image=QImage()
        path=self.preview_folder/(key+'.png')
        try:
            if path.stat().st_size>PREVIEW_BYTES:return self._preview_image
            reader=QImageReader(str(path),b'png');size=reader.size()
            if 0<size.width()<=PREVIEW_EDGE and 0<size.height()<=PREVIEW_EDGE:self._preview_image=reader.read()
        except OSError:pass
        return self._preview_image

    def save_preview(self,row,data,token):
        raw=preview_png(data)
        if raw is None:return False
        token.check();self.preview_folder.mkdir(parents=True,exist_ok=True)
        path=self.preview_folder/(geometry_key(row)+'.png');temporary=path.with_suffix('.tmp')
        try:
            temporary.write_bytes(raw);token.check();temporary.replace(path)
        finally:temporary.unlink(missing_ok=True)
        # Keep at most 64 small thumbnails and 16 MiB; no native renders remain.
        total=0
        for index,saved in enumerate(sorted(self.preview_folder.glob('*.png'),key=lambda p:p.stat().st_mtime,reverse=True)):
            total+=saved.stat().st_size
            if index>=64 or total>16*1024*1024:saved.unlink(missing_ok=True)
        return True

    def select(self,row):
        key=(row['id'],geometry_key(row)) if row else None
        if self.pending and self.pending[0]==key:return
        if self.pending:self.pending[1].cancel()
        self.pending=None
        if self.closed or row is None:return
        render=row.get('render_url')
        if not isinstance(render,str) or not re.fullmatch(r'https://osmsdataexplorer.com/data/maps/[a-f0-9]{32}\.webp',render):return
        previous=self.store.value('map_geometry',{}).get(str(row['id']))
        if previous and previous.get('key')==key[1] and 0<=time.time()-previous.get('saved',0)<(DAY if previous.get('proof') else 1800):
            if not (previous.get('proof') or {}).get('preview') or (self.preview_folder/(key[1]+'.png')).is_file():return
        token=RequestToken();self.pending=(key,token)
        future=self.pool.submit(self.load,row,token);future.add_done_callback(lambda result:self._finished.emit((key,token,result)) if not self.closed else None)

    def load(self,row,token):
        proof=None;previous=self.store.value('map_geometry',{}).get(str(row['id']))
        try:
            with request_scope(token):
                state=self.store.value('map_portals',{})
                if not 0<=time.time()-state.get('saved',0)<DAY or 'renders' not in state:
                    rows=self.fetch_json(PORTALS);token.check()
                    if not isinstance(rows,dict) or len(rows)>2000 or any(not isinstance(v,list) or len(v)>1000 for v in rows.values()):raise ValueError('Invalid map alignment index')
                    renders=self.fetch_json(RENDERS);token.check()
                    if not isinstance(renders,dict) or len(renders)>2000 or any(not isinstance(k,str) or not isinstance(v,str) or not re.fullmatch(r'[a-f0-9]{32}',v) for k,v in renders.items()):raise ValueError('Invalid map render index')
                    state={'saved':time.time(),'rows':rows,'renders':renders}
                    with self.store.connect() as db:self.store.put_meta(db,'map_portals',state);token.check()
                identity=f"{row['id']:09d}";portals=state.get('rows',{}).get(identity,[])
                offsets=alignment(row,portals);points=verified_portals(row,portals)
                expected='https://osmsdataexplorer.com/data/maps/'+state.get('renders',{}).get(identity,'')+'.webp'
                if (offsets or points) and row.get('render_url')==expected:
                    data=self.fetch_bytes(row.get('render_url',''));token.check();size=native_size(data,row.get('render_url'))
                    if size:
                        verified=False
                        minimap=row.get('minimap_url','')
                        if re.fullmatch(r'https://osmsdataexplorer.com/data/current/images/maps/\d+\.png',minimap):
                            small=self.fetch_bytes(minimap);token.check()
                            if len(small)<=1024*1024:verified=matching_projection(data,small)
                        points=[point for point in points if point['x']<size[0] and point['y']<size[1]]
                        proof=dict(**(offsets or dict(dx=0,dy=0,anchors=0)),width=size[0],height=size[1],projection_verified=verified,
                                   portals=points,spawns_verified=bool(offsets))
                        if not verified and points:proof['preview']=self.save_preview(row,data,token)
        except CancelledError:raise
        except Exception:
            if previous and previous.get('key')==geometry_key(row):proof=previous.get('proof')
        token.check()
        with self.store.connect() as db:
            saved=dict(self.store.value('map_geometry',{}));saved[str(row['id'])]={'key':geometry_key(row),'saved':time.time(),'proof':proof}
            self.store.put_meta(db,'map_geometry',saved);token.check()
        return proof

    def finish(self,result):
        if self.closed:return
        key,token,future=result
        if self.pending!=(key,token):return
        self.pending=None
        try:future.result()
        except CancelledError:return
        except Exception:return
        if self._preview_key==key[1]:self._preview_key=None;self._preview_image=QImage()
        self.updated.emit(key[0])

    def close(self):
        self.closed=True
        if self.pending:self.pending[1].cancel()
        self.pool.shutdown(wait=False,cancel_futures=True)
