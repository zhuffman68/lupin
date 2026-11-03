"""Native page-cache and progressive replies over public shop pixels only."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage, QPainter

from price_lens.platform_paths import reader_binary

ROOT=Path(__file__).resolve().parents[1]
BINARY=reader_binary(ROOT)


@unittest.skipUnless(BINARY.is_file(),'Build the local screen reader first')
class ShopReaderDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=QImage(str(ROOT/'vendor/minerva/samples/player-shop/ideal-ratio-weapons-and-a-robe.png'))
        cls.image=QImage(source.width()+40,source.height()+40,QImage.Format.Format_RGBA8888)
        cls.image.fill(QColor('#344658'));p=QPainter(cls.image);p.drawImage(20,20,source);p.end()
        instance=cls();cls.clean=instance.read([{'image':cls.image}])[0][-1]
        cls.table=cls.clean['shop']['area']

    def read(self,requests):
        with tempfile.TemporaryDirectory() as folder:
            lines=[]
            for index,request in enumerate(requests,1):
                fields=dict(request);image=fields.pop('image')
                path=Path(folder)/f'{index}.png';self.assertTrue(image.save(str(path)))
                lines.append(json.dumps({'path':str(path),'at_ms':index,**fields}))
            proc=subprocess.run([str(BINARY)],input='\n'.join(lines)+'\n',capture_output=True,
                text=True,check=True,timeout=45,env={**os.environ,'RTEN_NUM_THREADS':'1','RAYON_NUM_THREADS':'2'})
        groups=[[] for _ in requests]
        for line in proc.stdout.splitlines():
            reply=json.loads(line);self.assertNotIn('error',reply)
            groups[reply['atMs']-1].append(reply)
        for group in groups:
            self.assertTrue(group);self.assertIsNot(group[-1].get('shopPartial'),True)
        return groups

    def test_exact_page_reuses_across_crop_origins_but_rejects_scroll_and_source_changes(self):
        area=QRect(*(self.table[key] for key in ('x','y','width','height')))
        crop=area.adjusted(-12,-12,12,12).intersected(self.image.rect())
        cropped=self.image.copy(crop)
        common={'image':self.image,'shop_area':self.table,'capture_generation':1,'shop_epoch':1}
        groups=self.read([common,common,{**common,'image':cropped,'origin':{'x':crop.x(),'y':crop.y()}},
            {**common,'capture_generation':2},{**common,'capture_generation':2,'shop_epoch':2}])
        self.assertEqual([group[-1]['shopCached'] for group in groups],[False,True,True,False,False])
        expected=[(row['name'],row.get('price')) for row in groups[0][-1]['shop']['rows']]
        for group in groups:
            self.assertEqual([(row['name'],row.get('price')) for row in group[-1]['shop']['rows']],expected)
            self.assertEqual(len(group),1)

    def test_changed_price_pixels_are_not_reused_and_unscoped_requests_never_hit(self):
        changed=self.image.copy();row=self.clean['shop']['rows'][0]['area']
        changed.setPixelColor(row['x']+35,row['y']+25,QColor('magenta'))
        common={'image':self.image,'shop_area':self.table,'capture_generation':1,'shop_epoch':1}
        groups=self.read([common,{**common,'image':changed},
                          {'image':self.image,'shop_area':self.table},{'image':self.image,'shop_area':self.table}])
        self.assertTrue(all(not group[-1]['shopCached'] for group in groups))

    def test_incomplete_shop_can_publish_current_complete_rows_before_the_final_reply(self):
        changed=self.image.copy();row=self.clean['shop']['rows'][0]['area']
        p=QPainter(changed);p.fillRect(QRect(row['x']-36,row['y'],row['width']+36,row['height']),QColor('#464b78'));p.end()
        common={'image':self.image,'shop_area':self.table,'capture_generation':1,'shop_epoch':1,'progressive_shop':True}
        groups=self.read([common,{**common,'image':changed},common])
        self.assertEqual(len(groups[0]),1)
        self.assertEqual(len(groups[1]),2)
        self.assertTrue(groups[1][0]['shopPartial'])
        self.assertTrue(any(row.get('name') and row.get('price') for row in groups[1][0]['shop']['rows']))
        self.assertEqual(len(groups[2]),1)
