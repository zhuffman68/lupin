"""One detailed item card for search, observed descriptions and selected offers."""
from .domain import item_name_matches
from .listing_widgets import add_fallback_panel
from .price_widgets import PriceCard
from .reference_details import EntryDetails


def item_caption(item):
    return item.sub_category or ('Cash item' if item.cash else 'Equipment' if item.equipment else 'Item')


def item_record(panel,item):
    store=getattr(panel,'store',None)
    record=store.entry('items',item.game_id) if store and item else None
    return record if record and item_name_matches(item,record[0].name) else None


def matches_item_card(card,item,record):
    if record:return isinstance(card,EntryDetails) and card.entry.id==item.game_id and card.row==record[1]
    return isinstance(card,PriceCard) and getattr(card,'listing_item',None)==item


def make_item_card(panel,identity,record,*,automatic=False,**data):
    item=identity
    if record:
        card=EntryDetails(panel,*record)
        card.sources_activated=not automatic
        card.media_changed.connect(panel.reference_changed.emit)
    else:
        data['selected']=True
        data['context_name']=item_caption(item)
        card=PriceCard(watchlist=getattr(panel,'watchlist',None),**data)
        add_fallback_panel(card,item,getattr(panel,'market',None),panel.source_requested.emit,
                           active=lambda:getattr(panel,'listing_active',True))
    card.update_data(**data)
    return card
