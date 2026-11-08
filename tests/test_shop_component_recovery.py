"""Native shop component OCR over public pixels and generated occluders."""
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from PySide6.QtCore import Qt,QRect
from PySide6.QtGui import QColor, QImage, QPainter

from price_lens.platform_paths import reader_binary
from price_lens.price_observations import PriceObservations
from price_lens.domain import Catalog
from price_lens.shop_browsing import ShopBrowsing


ROOT = Path(__file__).resolve().parents[1]
BINARY = reader_binary(ROOT)
PUBLIC = ROOT / 'vendor/minerva/samples/player-shop'


@unittest.skipUnless(BINARY.is_file(), 'Build the screen reader first')
class ShopComponentRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.image = QImage(str(PUBLIC / 'ideal-ratio-weapons-and-a-robe.png'))
        self.expected = json.loads((PUBLIC / 'ideal-ratio-weapons-and-a-robe.json').read_text())
        self.clean = self.read(self.image)
        self.table = self.clean['shop']['area']
        self.first = self.clean['shop']['rows'][0]['area']

    def read_many(self, images, **fields):
        with tempfile.TemporaryDirectory(prefix='lupin-shop-components-') as directory:
            requests = []
            for index, image in enumerate(images):
                path = Path(directory) / f'{index}.png'
                self.assertTrue(image.save(str(path)))
                requests.append(json.dumps(dict(path=str(path), **fields)))
            result = subprocess.run([str(BINARY)], input='\n'.join(requests) + '\n',
                text=True, capture_output=True, check=True, timeout=45,
                env={**os.environ, 'RAYON_NUM_THREADS': '2'})
        values = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(values), len(images))
        for value in values:
            self.assertNotIn('error', value)
        return values

    def read(self, image, **fields):
        return self.read_many([image], **fields)[0]

    def tail_pane(self, *, every_row=False, left=125):
        image = self.image.copy()
        painter = QPainter(image)
        top = self.first['y'] if every_row else self.first['y'] + 36
        painter.fillRect(self.first['x'] + left, top, image.width(), image.height(), QColor('#464b78'))
        painter.end()
        return image

    def listings(self, result):
        return [dict(name=row['name'], **row['price'])
                for row in result['shop']['rows'] if row.get('name') and row.get('price')]

    def test_all_independently_readable_rows_recover_name_and_asking(self):
        result = self.read(self.tail_pane(), shop_area=self.table, pointer=dict(x=225, y=5))
        self.assertEqual(self.listings(result), self.expected)
        recovered = [row for row in result['shop']['rows'] if row.get('nameArea')]
        self.assertEqual(len(recovered), 5)
        self.assertTrue(all(row.get('priceArea') and not row.get('nameOnly') for row in recovered))

    def test_new_component_page_is_accepted_without_a_followup_read(self):
        result=self.read(self.image,shop_area=self.table)
        self.assertTrue(any(row.get('priceText') for row in result['shop']['rows']))
        catalog=Catalog({'items':[dict(id=index+1,name=row['name'])
            for index,row in enumerate(self.clean['shop']['rows'])]})
        observations=PriceObservations(catalog=catalog)
        observations.browsing=ShopBrowsing(identity=observations.shop_identity)
        first=observations.observe_shop(result['shop'],self.image,self.image)
        self.assertFalse(first.retry,'Complete current components establish their own frame proof')
        self.assertEqual([dict(name=row['name'],**row['price']) for row in observations.rows
            if row.get('name') and row.get('price')],self.expected)
        second=observations.observe_shop(result['shop'],self.image,self.image)
        self.assertFalse(second.retry,'A stationary verified shop must not spin on retries')
        self.assertEqual([dict(name=row['name'],**row['price']) for row in observations.rows
            if row.get('name') and row.get('price')],self.expected)

    def test_complete_lines_recover_when_no_full_width_native_row_remains(self):
        result = self.read(self.tail_pane(every_row=True), shop_area=self.table)
        self.assertEqual(self.listings(result), self.expected)
        self.assertTrue(all(row.get('nameArea') and row.get('priceArea') for row in result['shop']['rows']))

    def test_unrelated_three_lane_ledger_cannot_veto_verified_shop_components(self):
        image = QImage(1100, 800, QImage.Format.Format_RGBA8888)
        image.fill(QColor('#4c4c4c'))
        painter = QPainter(image)
        painter.drawImage(20, 410, self.image)
        x, y = 700, 40
        # Sold Items may have enough purchases that its totals header is below
        # the viewport. Use real public name glyphs in all three text lanes;
        # no line has the native asking-price grammar.
        for index in range(4):
            top = y + index * 58
            painter.fillRect(x - 37, top, 36, 54, QColor('#e1e1d8'))
            painter.fillRect(x, top, 162, 54, QColor('#cdd9e3'))
            for lane, source in enumerate(self.clean['shop']['rows'][:3]):
                area = source['area']
                painter.drawImage(x, top + lane * 18, self.image.copy(
                    area['x'], area['y'], 125, 17))
            for rule in (18, 36):
                painter.fillRect(x, top + rule, 162, 1, QColor('white'))
            painter.fillRect(x - 37, top + 54, 199, 4, QColor('#f5f6f7'))
        painter.fillRect(self.first['x'] + 20 + 125, self.first['y'] + 410 + 36,
            80, 250, QColor('#464b78'))
        painter.end()
        hint = dict(self.table, x=self.table['x'] + 20, y=self.table['y'] + 410)
        result = self.read(image, shop_area=hint)
        self.assertEqual(self.listings(result), self.expected)
        self.assertTrue(all(row['area']['x'] < 300 for row in result['shop']['rows']))
        self.assertEqual(result['shop']['area'], hint)

    def test_single_name_at_arbitrary_hint_cannot_replace_detected_shop(self):
        image = QImage(1100, 800, QImage.Format.Format_RGBA8888)
        image.fill(QColor('#4c4c4c'))
        painter = QPainter(image)
        painter.drawImage(20, 410, self.image)
        painter.fillRect(537, 70, 162, 17, QColor('#cdd9e3'))
        painter.drawImage(537, 70, self.image.copy(self.first['x'], self.first['y'], 125, 17))
        painter.end()
        result = self.read(image, shop_area=dict(x=500, y=70, width=199, height=200))
        self.assertEqual(self.listings(result), self.expected)
        self.assertTrue(all(row['area']['x'] < 300 for row in result['shop']['rows']))

    def test_complete_native_ellipsis_recovers_without_inventing_its_asking(self):
        image = QImage(str(PUBLIC / 'a-scroll-cut-short.png'))
        clean = self.read(image)
        row = next(row for row in clean['shop']['rows'] if row.get('name', '').endswith('...'))
        area = row['area'];scale = area['width'] / 162;row_name = row['name']
        last = max(x for x in range(area['x'], area['x'] + area['width'])
            if any(max(image.pixelColor(x, y).getRgb()[:3]) < 110
                   for y in range(area['y'], area['y'] + round(17 * scale))))
        pane_left = last + 1 + math.ceil(4 * scale)
        painter = QPainter(image)
        painter.fillRect(pane_left, area['y'], area['x'] + area['width'] - pane_left,
            round(17 * scale), QColor('#464b78'))
        painter.fillRect(area['x'], area['y'] + round(18 * scale), area['width'],
            round(17 * scale), QColor('white'))
        painter.end()
        result = self.read(image, shop_area=clean['shop']['area'])
        recovered = next(row for row in result['shop']['rows'] if row.get('name') == row_name)
        self.assertEqual(recovered['name'], row['name'])
        self.assertTrue(recovered.get('nameOnly'))
        self.assertIsNone(recovered['price'])

    def test_pane_cut_last_ellipsis_dot_does_not_supply_a_name_prefix(self):
        image = QImage(str(PUBLIC / 'a-scroll-cut-short.png'))
        clean = self.read(image)
        row = next(row for row in clean['shop']['rows'] if row.get('name', '').endswith('...'))
        area = row['area'];scale = area['width'] / 162
        last = max(x for x in range(area['x'], area['x'] + area['width'])
            if any(max(image.pixelColor(x, y).getRgb()[:3]) < 110
                   for y in range(area['y'], area['y'] + round(17 * scale))))
        painter = QPainter(image)
        painter.fillRect(last - 1, area['y'], area['x'] + area['width'] - last + 1,
            round(17 * scale), QColor('#464b78'))
        painter.fillRect(area['x'], area['y'] + round(18 * scale), area['width'],
            round(17 * scale), QColor('white'))
        painter.end()
        result = self.read(image, shop_area=clean['shop']['area'])
        self.assertFalse(any(row.get('name', '').startswith('One-Handed Sword Attac')
            for row in result['shop']['rows'] if row.get('name')))

    def test_each_exposed_name_is_independent_of_its_blocked_asking(self):
        image = self.image.copy()
        painter = QPainter(image)
        for row in self.clean['shop']['rows']:
            area = row['area']
            painter.fillRect(area['x'], area['y'] + 18, area['width'], 17, QColor('white'))
        painter.end()
        result = self.read(image, shop_area=self.table, pointer=dict(x=225, y=5))
        rows = result['shop']['rows']
        self.assertEqual([row['name'] for row in rows], [row['name'] for row in self.expected])
        self.assertTrue(all(row.get('nameOnly') and row['price'] is None
                            and row.get('nameArea') and not row.get('priceArea') for row in rows))

    def test_occluder_cut_name_prefixes_never_become_complete_names(self):
        result = self.read(self.tail_pane(every_row=True, left=30), shop_area=self.table)
        self.assertFalse(any(row.get('name') for row in ((result.get('shop') or {}).get('rows') or [])))

    def test_cursor_on_name_glyphs_prevents_component_recovery(self):
        image = self.image.copy()
        painter = QPainter(image)
        painter.fillRect(self.first['x'], self.first['y'] + 18, self.first['width'], 17, QColor('white'))
        painter.end()
        result = self.read(image, shop_area=self.table,
            pointer=dict(x=self.first['x'] + 24, y=self.first['y'] + 9))
        self.assertFalse(any(row.get('name') == 'Fish Spear' for row in result['shop']['rows']))

    def test_purple_description_title_pixels_are_not_native_shop_names(self):
        image = self.image.copy()
        for y in range(self.first['y'], self.first['y'] + self.first['height']):
            for x in range(self.first['x'], self.first['x'] + self.first['width']):
                old = image.pixelColor(x, y)
                image.setPixelColor(x, y, QColor('white') if max(old.red(), old.green(), old.blue()) < 110
                                    else QColor('#464b78'))
        result = self.read(image, shop_area=self.table)
        self.assertFalse(any(row.get('name') == 'Fish Spear' for row in result['shop']['rows']))
        self.assertTrue(any(row.get('name') == 'Nakamaki' for row in result['shop']['rows']))

    def test_component_coordinates_and_strict_amounts_survive_double_scale(self):
        image = self.tail_pane().scaled(self.image.width() * 2, self.image.height() * 2,
            Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
        hint = {key: value * 2 for key, value in self.table.items()}
        result = self.read(image, shop_area=hint)
        self.assertEqual(self.listings(result), self.expected)
        recovered = [row for row in result['shop']['rows'] if row.get('nameArea')]
        self.assertEqual(len(recovered), 5)
        for row in recovered:
            name=QRect(*(row['nameArea'][k] for k in ('x','y','width','height')))
            band=QRect(*(row['area'][k] for k in ('x','y','width','height')))
            self.assertTrue(band.adjusted(-2,-2,2,2).contains(name))
            self.assertTrue(20<=name.height()<=34)
            self.assertLess(name.bottom(),row['priceArea']['y'])
            self.assertIsNotNone(PriceObservations.component_proof(row,'name',image,image))

    def test_native_orange_component_keeps_full_name_and_strict_amount(self):
        image = self.image.copy()
        area = self.clean['shop']['rows'][1]['area']
        base = (205, 217, 227)
        norm = sum(value * value for value in base)
        for y in range(area['y'], area['y'] + area['height']):
            for x in range(area['x'] + 5, area['x'] + area['width']):
                p = image.pixelColor(x, y).getRgb()[:3]
                gain = sum(a * b for a, b in zip(p, base)) / norm
                if 0 <= gain <= 1.04 and all(abs(a - b * gain) <= 8 for a, b in zip(p, base)):
                    image.setPixelColor(x, y, QColor(*(round(value * gain) for value in (251, 167, 46))))
        painter = QPainter(image)
        painter.fillRect(area['x'] + 125, area['y'], area['width'], area['height'], QColor('#464b78'))
        painter.end()
        result = self.read(image, shop_area=self.table)
        row = next(row for row in result['shop']['rows'] if row.get('name') == 'Nakamaki')
        self.assertEqual(row['price'], dict(quantity=1, mesos=10999))
        self.assertEqual(row['nameArea']['x'], area['x'] + 5)
        self.assertTrue(row.get('priceArea'))

    def test_real_selected_row_is_read_fresh_beside_a_description(self):
        image=QImage(str(PUBLIC/'potions-and-a-selected-listing.png'))
        clean=self.read(image);table=clean['shop']['area']
        painter=QPainter(image)
        painter.fillRect(250,0,image.width()-250,image.height(),QColor('#464b78'));painter.end()
        result=self.read(image,shop_area=table)
        row=next((row for row in result['shop']['rows'] if row.get('name')=='Magic Potion'),None)
        self.assertIsNotNone(row,'A newly visible selected row must not need an earlier page read')
        self.assertEqual(row.get('price'),dict(quantity=1,mesos=400))
        self.assertIsNotNone(PriceObservations.component_proof(row,'name',image,image))
        self.assertIsNotNone(PriceObservations.component_proof(row,'price',image,image))

    def test_real_selected_row_after_scroll_is_accepted_without_old_page_prices(self):
        image=QImage(str(PUBLIC/'potions-and-a-selected-listing.png'))
        clean=self.read(image);table=clean['shop']['area']
        catalog=Catalog({'items':[dict(id=index+1,name=row['name'])
            for index,row in enumerate(clean['shop']['rows'])]})
        observations=PriceObservations(catalog=catalog)
        observations.browsing=ShopBrowsing(identity=observations.shop_identity)
        observations.observe_shop(clean['shop'],image,image)
        observations.browsing._advance();observations.viewport_changed()
        self.assertFalse(observations.rows);self.assertFalse(observations.shop_rows.rows)
        panel=QRect(250,0,image.width()-250,image.height())
        painter=QPainter(image);painter.fillRect(panel,QColor('#464b78'));painter.end()
        point=(240,208)
        result=self.read(image,shop_area=table,pointer=dict(zip(('x','y'),point)))
        observations.observe_shop(result['shop'],image,image,pointer=point,read_point=point,
            panel=panel,source_exclude=(panel,))
        row=next((r for r in observations.rows if r.get('name')=='Magic Potion'),None)
        self.assertIsNotNone(row)
        self.assertEqual(observations.item_for(row).name,'Magic Potion')
        self.assertEqual(row['price'],dict(quantity=1,mesos=400))
        self.assertFalse(row.get('reference_only'));self.assertFalse(row.get('retained'))

    def test_selected_native_edges_do_not_excuse_cut_or_foreign_text(self):
        image=QImage(str(PUBLIC/'potions-and-a-selected-listing.png'))
        table=self.read(image)['shop']['area']
        painter=QPainter(image)
        painter.fillRect(250,0,image.width()-250,image.height(),QColor('#464b78'));painter.end()
        result=self.read(image,shop_area=table)
        row=next(r for r in result['shop']['rows'] if r.get('name')=='Magic Potion')
        changed=image.copy();changed.setPixelColor(110,205,QColor('white'))
        self.assertIsNone(PriceObservations.component_proof(row,'name',changed,changed))
        self.assertIsNone(PriceObservations.component_proof(row,'name',image,changed))
        cut=image.copy();painter=QPainter(cut)
        painter.fillRect(132,row['priceArea']['y'],100,row['priceArea']['height'],QColor('#464b78'));painter.end()
        self.assertIsNone(PriceObservations.component_proof(row,'price',cut,cut))
        result=self.read(cut,shop_area=table)
        row=next(r for r in result['shop']['rows'] if r.get('name')=='Magic Potion')
        self.assertIsNone(row['price'])

    def test_cached_components_follow_changed_current_name_pixels(self):
        before = self.tail_pane()
        after = before.copy()
        original = self.clean['shop']['rows'][0]['area']
        target = self.clean['shop']['rows'][2]['area']
        painter = QPainter(after)
        painter.drawImage(target['x'], target['y'], self.image.copy(
            original['x'], original['y'], 125, 17))
        painter.fillRect(target['x'], target['y'] + 18, 125, 17, QColor('white'))
        painter.end()
        first, second, changed = self.read_many([before, before, after], shop_area=self.table)
        self.assertEqual(first['shop']['rows'], second['shop']['rows'])
        row = next(row for row in changed['shop']['rows'] if abs(row['area']['y'] - target['y']) <= 3)
        self.assertEqual(row['name'], 'Fish Spear')
        self.assertTrue(row['nameOnly'])
        self.assertIsNone(row['price'])

    def semantic_asking_frame(self, pane_left):
        image = self.image.copy()
        painter = QPainter(image)
        # These are the public first asking line's actual glyph coordinates:
        # complete number ends110, "me" spans116..131, final "s" ends152.
        painter.fillRect(pane_left, 31, 205 - pane_left, 17, QColor('#464b78'))
        painter.end()
        return image

    def test_full_amount_survives_cursor_envelope_on_currency_suffix(self):
        result = self.read(self.semantic_asking_frame(155), shop_area=self.table,
            pointer=dict(x=149, y=35))
        row = next(row for row in result['shop']['rows'] if row.get('name') == 'Fish Spear')
        self.assertEqual(row['price'], dict(quantity=1, mesos=13999))
        self.assertEqual(row['priceText'], '1 for 13,999')
        self.assertEqual(row['priceValueArea']['x'] + row['priceValueArea']['width'], 115)
        self.assertLess(row['priceArea']['x'] + row['priceArea']['width'], 141)

    def test_complete_amount_with_entire_currency_hidden_is_current(self):
        result = self.read(self.semantic_asking_frame(115), shop_area=self.table)
        row = next(row for row in result['shop']['rows'] if row.get('name') == 'Fish Spear')
        self.assertEqual(row['price'], dict(quantity=1, mesos=13999))
        self.assertEqual(row['priceText'], '1 for 13,999')
        self.assertTrue(row.get('priceValueArea'))

    def test_cut_digit_or_hidden_next_comma_slot_never_supplies_an_amount(self):
        for left in (109, 114):
            result = self.read(self.semantic_asking_frame(left), shop_area=self.table)
            row = next(row for row in result['shop']['rows'] if row.get('name') == 'Fish Spear')
            self.assertIsNone(row['price'])
            self.assertTrue(row['nameOnly'])
            self.assertNotIn('priceValueArea', row)

    def test_cursor_envelope_on_number_still_vetoes_semantic_amount(self):
        result = self.read(self.semantic_asking_frame(155), shop_area=self.table,
            pointer=dict(x=108, y=39))
        row = next(row for row in result['shop']['rows'] if row.get('name') == 'Fish Spear')
        self.assertIsNone(row['price'])
        self.assertTrue(row['nameOnly'])

    def test_semantic_amount_value_geometry_survives_double_scale(self):
        image = self.semantic_asking_frame(115).scaled(self.image.width() * 2, self.image.height() * 2,
            Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
        result = self.read(image, shop_area={key: value * 2 for key, value in self.table.items()})
        row = next(row for row in result['shop']['rows'] if row.get('name') == 'Fish Spear')
        self.assertEqual(row['price'], dict(quantity=1, mesos=13999))
        self.assertEqual(row['priceText'], '1 for 13,999')
        self.assertEqual(row['priceValueArea']['x'] + row['priceValueArea']['width'], 230)

    def test_currency_cut_does_not_change_a_proven_numeric_amount(self):
        result = self.read(self.semantic_asking_frame(129), shop_area=self.table)
        row = next(row for row in result['shop']['rows'] if row.get('name') == 'Fish Spear')
        self.assertEqual(row['price'], dict(quantity=1, mesos=13999))
        self.assertEqual(row['priceText'], '1 for 13,999')
        self.assertEqual(row['priceArea'], row['priceValueArea'])

    def test_short_amount_requires_a_whole_next_digit_advance(self):
        for edge, accepted in ((96, True), (91, False)):
            image = self.image.copy()
            painter = QPainter(image)
            painter.fillRect(87, 31, 118, 17, QColor('#cdd9e3'))
            painter.fillRect(edge, 31, 205 - edge, 17, QColor('#464b78'))
            painter.end()
            result = self.read(image, shop_area=self.table)
            row = next(row for row in result['shop']['rows'] if row.get('name') == 'Fish Spear')
            self.assertEqual(row['price'], dict(quantity=1, mesos=13) if accepted else None)

    def test_gray_top_slots_do_not_hide_later_native_grid_phase(self):
        image = self.tail_pane(every_row=True)
        painter = QPainter(image)
        for row in self.clean['shop']['rows'][:2]:
            area = row['area']
            painter.fillRect(area['x'], area['y'], area['width'], area['height'], QColor('#eeeeef'))
        painter.end()
        result = self.read(image, shop_area=self.table)
        self.assertEqual(self.listings(result), self.expected[2:])
        first = next(row for row in result['shop']['rows'] if row.get('name') == 'Scimitar')
        self.assertEqual(first['area']['y'],92)
        self.assertTrue(92<=first['nameArea']['y']<=95)
        self.assertIsNotNone(PriceObservations.component_proof(first,'name',image,image))

    def test_clean_current_hint_rows_emit_numeric_proof_on_first_read(self):
        result = self.read(self.image, shop_area=self.table, pointer=dict(x=225, y=5))
        self.assertEqual(self.listings(result), self.expected)
        for row in result['shop']['rows']:
            self.assertEqual(len(row['priceText'].split()), 3)
            self.assertEqual(row['priceArea'], row['priceValueArea'])

    def test_quantity_800_current_amount_survives_optional_numeric_abstention(self):
        image = QImage(str(PUBLIC / 'ores-and-bundles-of-800.png'))
        clean = self.read(image)
        result = self.read(image, shop_area=clean['shop']['area'])
        expected = [dict(name=row['name'], **row['price']) for row in clean['shop']['rows']]
        self.assertEqual(self.listings(result), expected)
        bundles = [row for row in result['shop']['rows'] if row.get('price', {}).get('quantity') == 800]
        self.assertEqual(len(bundles), 2)
        for row in bundles:
            if row.get('priceText') is not None:
                self.assertTrue(row['priceText'].startswith('800 for '))
                self.assertEqual(row['priceArea'], row['priceValueArea'])


if __name__ == '__main__':
    unittest.main()
