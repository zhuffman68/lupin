"""Generated Sold Items pane plus public shop/description pixels, never live images."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter
from PySide6.QtWidgets import QApplication

from price_lens.domain import Catalog
from price_lens.platform_paths import reader_binary
from price_lens.price_observations import PriceObservations
from price_lens.shop_browsing import ShopBrowsing

ROOT = Path(__file__).resolve().parents[1]
BINARY = reader_binary(ROOT)
PUBLIC = ROOT / 'vendor/minerva/samples'


@unittest.skipUnless(BINARY.is_file(), 'Build the screen reader first')
class SalesLedgerReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        font_id = QFontDatabase.addApplicationFont(str(ROOT / 'price_lens/resources/fonts/InterVariable.ttf'))
        cls.font = QFont(QFontDatabase.applicationFontFamilies(font_id)[0])
        cls.font.setPixelSize(11)

    def frame(self, *, shop=False, description=False):
        image = QImage(1100, 800, QImage.Format.Format_RGBA8888)
        image.fill(QColor('#4c4c4c'))
        painter = QPainter(image)
        painter.setFont(self.font)
        x, y = 450, 40
        # Each ledger cell has three text lanes, rather than a listing's two.
        # The long empty grid intentionally outranks the public shop candidate.
        for dy in range(0, 348, 58):
            painter.fillRect(x - 37, y + dy, 36, 54, QColor('#e1e1d8'))
            painter.fillRect(x, y + dy, 162, 54, QColor('#cdd9e3'))
            for rule in (18, 36):
                painter.fillRect(x, y + dy + rule, 162, 1, QColor('white'))
            painter.fillRect(x - 37, y + dy + 54, 199, 5, QColor('#f5f6f7'))
        painter.setPen(QColor('black'))
        for text, dy in [('Total Sales / Total Received', 0), ('0 mesos', 18), ('0 mesos', 36)]:
            painter.drawText(x + 5, y + dy + 14, text)
        if shop:
            painter.drawImage(20, 410, QImage(str(PUBLIC / 'player-shop/ideal-ratio-weapons-and-a-robe.png')))
        if description:
            painter.drawImage(700, 400, QImage(str(PUBLIC / 'item-tooltip/screw@60,20.png')))
        painter.end()
        return image

    def read(self, image, **fields):
        with tempfile.TemporaryDirectory(prefix='lupin-public-ledger-') as directory:
            path = Path(directory) / 'generated.png'
            self.assertTrue(image.save(str(path)))
            result = subprocess.run([str(BINARY)], input=json.dumps(dict(path=str(path), **fields)) + '\n',
                text=True, capture_output=True, check=True, timeout=30,
                env={**os.environ, 'RAYON_NUM_THREADS': '2'})
        value = json.loads(result.stdout)
        self.assertNotIn('error', value)
        return value

    def test_summary_pane_emits_no_item_even_if_heading_is_in_catalog(self):
        image = self.frame()
        result = self.read(image)
        self.assertIsNone(result['shop'])
        state = PriceObservations(catalog=Catalog({'items': [dict(id=1, name='Total Sales / Total Received')]}))
        state.browsing = ShopBrowsing(identity=state.shop_identity)
        self.addCleanup(state.browsing.timer.stop)
        state.observe_shop(result['shop'], image, image)
        self.assertFalse(state.shop_open)
        self.assertEqual(state.rows, [])
        self.assertEqual(state.identity_candidates, ())
        self.assertEqual(state.shop_rows.rows, {})

    def test_actual_shop_candidate_wins_and_outside_description_still_reads(self):
        result = self.read(self.frame(shop=True, description=True), tooltip=True, pointer=dict(x=790, y=440),
            origin=dict(x=30, y=20))
        expected = json.loads((PUBLIC / 'player-shop/ideal-ratio-weapons-and-a-robe.json').read_text())
        rows = result['shop']['rows']
        self.assertEqual([dict(name=row['name'], **row['price']) for row in rows], expected)
        self.assertTrue(all(row['area']['x'] < 300 for row in rows))
        self.assertEqual(result['tooltip']['found']['name'], 'Screw')


if __name__ == '__main__':
    unittest.main()
