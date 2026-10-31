"""Shared local lookup adapters preserve reason and avoid duplicate demands."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from price_lens.domain import Item,Quote
from price_lens.market_lookup import LookupResult,market_lookup,market_lookup_reason


class MarketLookupTests(unittest.TestCase):
    def setUp(self):
        self.item=Item(1041078,'Blue Moon',equipment=True,gender='female')
        self.quote=Quote(1041078,19000,2000000000,1999999940,8,'MesoWatch','','24h')

    def test_combined_production_result_is_used_once_without_fallback_reads(self):
        expected=LookupResult(self.quote,'priced')
        market=SimpleNamespace(lookup=Mock(return_value=expected),
            cached=Mock(side_effect=AssertionError('Duplicate cache read')),
            lookup_reason=Mock(side_effect=AssertionError('Duplicate reason read')))
        self.assertIs(market_lookup(market,self.item),expected)
        market.lookup.assert_called_once_with(self.item)

    def test_negative_combined_result_preserves_reason_and_reference(self):
        quote=Quote(1041078,None,2000000000,None,0,'MesoWatch','','no data')
        market=SimpleNamespace(lookup=lambda item:LookupResult(quote,'variant-mismatch'))
        result=market_lookup(market,self.item)
        self.assertIs(result.quote,quote)
        self.assertEqual(result.reason,'variant-mismatch')

    def test_cached_only_doubles_get_neutral_missing_or_priced_status(self):
        self.assertEqual(market_lookup(None,self.item),LookupResult(None,'missing'))
        self.assertEqual(market_lookup(SimpleNamespace(cached=lambda item:self.quote),self.item),
                         LookupResult(self.quote,'priced'))
        self.assertEqual(market_lookup(None,None),LookupResult(None,'unidentified'))

    def test_explicit_fake_reason_is_not_conflated_with_absence(self):
        for reason in ('no-sales','variant-mismatch','unit-mismatch','missing'):
            market=SimpleNamespace(cached=lambda item:None,lookup_reason=lambda item:reason)
            self.assertEqual(market_lookup_reason(market,self.item),reason)


if __name__=='__main__':unittest.main()
