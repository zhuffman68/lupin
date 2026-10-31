"""Shared cards distinguish idle missing data, identity failures and real work."""
from dataclasses import replace
import os
import unittest

from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication

from price_lens.domain import Item,Quote
from price_lens.price_widgets import PriceCard
from price_lens.market_lookup import market_lookup_reason


class PriceWidgetStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.app.setProperty('reduceMotion',True)
        self.item=Item(1041078,'Blue Moon',equipment=True,gender='female')
        self.quote=Quote(self.item.game_id,None,2000000000,None,0,'MesoWatch','','no data',uncertain=True)
        self.data=dict(item=self.item,row={'name':'Blue Moon'},quote=self.quote,now=2000000000,ttl=900,hovered=True)
        self.card=PriceCard(**self.data)

    def tearDown(self):
        self.card.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.app.processEvents();self.app.setProperty('reduceMotion',False)

    def status(self,**changes):
        self.card.update_data(**{**self.data,**changes})
        return self.card.fields['status'].text()

    def test_idle_results_have_distinct_reasons_without_fake_pending_text(self):
        messages={'no-sales':'No observed sales','variant-mismatch':'Item variant unverified',
                  'unit-mismatch':'Price units unverified','missing':'No market reference','':'No market reference'}
        for reason,message in messages.items():
            with self.subTest(reason=reason):
                self.assertEqual(self.status(lookup_reason=reason),message)
                self.assertEqual(self.status(quote=None,lookup_reason=reason),message)

    def test_unknown_name_reason_alone_invalidates_the_display_signature(self):
        ambiguous={'name':'Blue Moon','_identity_reason':'ambiguous'}
        self.assertEqual(self.status(item=None,row=ambiguous,quote=None),'Item name ambiguous')
        self.assertIn('Several item IDs',self.card.fields['explanation'].text())
        self.assertEqual(self.status(item=None,row={'name':'Blue Moon','_identity_reason':'unidentified'},quote=None),'Item unidentified')
        self.assertNotIn('Several item IDs',self.card.fields['explanation'].text())

    def test_real_refresh_and_error_priorities_keep_mismatch_explanation(self):
        for state,message in (('refreshing','Updating market prices…'),('queued','Market refresh queued…'),
                              ('retry','Market update unavailable')):
            self.assertEqual(self.status(lookup_reason='variant-mismatch',lookup_state=state),message)
            self.assertIn('different or combined item variant',self.card.fields['explanation'].text())
        self.assertEqual(self.status(lookup_reason='no-sales',lookup_error=True),'Market update unavailable')
        self.assertEqual(self.status(lookup_reason='variant-mismatch',lookup_error=True,lookup_state='refreshing'),'Updating market prices…')

    def test_unit_and_identity_mismatches_cannot_masquerade_as_missing_sales(self):
        wrong_units=replace(self.quote,price=28888,per_set=True)
        self.assertEqual(self.status(quote=wrong_units,lookup_reason='no-sales'),'Price units unverified')
        self.assertNotIn('28,888',self.card.fields['market'].text())
        wrong_item=replace(wrong_units,game_id=1032011,per_set=False)
        self.assertEqual(self.status(quote=wrong_item,lookup_reason='missing'),'Market reference unverified')
        self.assertNotIn('28,888',self.card.fields['market'].text())

    def test_reason_only_change_withholds_an_old_price_without_replacing_fields(self):
        fresh=replace(self.quote,price=28888,observed_at=1999999940,sample_count=8,uncertain=False,period='24h')
        self.status(quote=fresh,lookup_reason='priced')
        self.assertIn('28,888',self.card.fields['market'].text())
        fields=dict(self.card.fields)
        self.assertEqual(self.status(quote=fresh,lookup_reason='variant-mismatch'),'Item variant unverified')
        self.assertNotIn('28,888',self.card.fields['market'].text())
        self.assertEqual(self.status(quote=fresh,lookup_reason='no-sales'),'No observed sales')
        self.assertNotIn('28,888',self.card.fields['market'].text())
        self.assertEqual(self.card.fields['recent'].text(),'')
        self.assertTrue(all(self.card.fields[key] is value for key,value in fields.items()))

    def test_optional_service_reason_preserves_simple_test_doubles(self):
        self.assertEqual(market_lookup_reason(None,self.item),'missing')
        self.assertEqual(market_lookup_reason(object(),self.item),'missing')
        class Market:
            def lookup_reason(self,item):return 'no-sales'
        self.assertEqual(market_lookup_reason(Market(),self.item),'no-sales')


if __name__=='__main__':unittest.main()
