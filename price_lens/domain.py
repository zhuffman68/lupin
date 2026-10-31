"""Conservative item identity and price comparisons; no platform dependencies."""
from dataclasses import dataclass
import math
import re
import time

WORLD = "Classic World"
DEFAULT_TTL = 15 * 60
MAX_MARKET_AGE = 24 * 60 * 60
MAX_SNAPSHOT_AGE = 60 * 60


def number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0:
        return float(value)
    return None


def key(name):
    name = str(name).casefold().replace("’", "'").translate(str.maketrans({'“':'"','”':'"'}))
    # Balanced quotation marks are formatting boundaries. The small shop font
    # can lose the space after a closing quote (Black "Hit Me"Shirt). Keep the
    # marks and their contents; removing punctuation would conflate other names.
    name = re.sub(r'"([^"\n]+)"', lambda match:' "'+match[1].strip()+'" ', name)
    name = " ".join(name.split())
    return re.sub(r"\s*:\s*", ":", name)


def glyph_key(name):
    # The bundled recognizer reads the small Classic font's y as v (also seen
    # in the upstream Horny Mushroom Cap tooltip fixture). No edit-distance guess.
    # Whole-word aliases avoid an edit-distance guess across stats, tiers,
    # prices or percentages. Exact catalog spelling always wins first.
    aliases={'soroll':'scroll','seroll':'scroll','scroil':'scroll','scroii':'scroll','scr0ll':'scroll',
             'arrnor':'armor','mushroorn':'mushroom','helrnet':'helmet','whlte':'white',
             'sllver':'silver','lron':'iron','0range':'orange','b1ue':'blue'}
    text = re.sub(r'\b[\w]+\b',lambda m:aliases.get(m[0],m[0]),key(name))
    # These confusions occur in the small game font (I/l and g/q, including
    # "Kitty Chat Rinq"). Exact spelling wins first; a collision stays ambiguous.
    text = re.sub(r'(?<=[a-z])1(?=[a-z])', 'i', text)
    return text.translate(str.maketrans({'v':'y','l':'i','q':'g'}))


def item_words(name):
    """Visible-name formatting only; provider proofs still use exact key()."""
    return " ".join(re.sub(r"[-‐‑–—]", " ", key(name)).replace("nametag", "name tag").split())


def unclipped_name(name):
    return re.sub(r"(?:[.\u2026]\s*)+(?:[,\u00b7]\s*)?$", "", key(name)).rstrip()


def clipped_name(name):
    return bool(re.search(r"[.\u2026](?:[.\u2026\s,\u00b7])*$", key(name)))


@dataclass(frozen=True)
class Item:
    game_id: int
    name: str
    equipment: bool = False
    per_set: bool = False
    tier: str | None = None
    cash: bool = False
    gender: str | None = None
    sub_category: str | None = None


def item_name_matches(item, name):
    """Exact-ID source spelling, allowing only typography and proven gender."""
    canonical, observed = key(item.name), key(name)
    if canonical == observed:return True
    suffix = re.fullmatch(r'(.+?)\s+\(([mf])\)', observed)
    if not suffix or not item.equipment:return False
    return (suffix[1] == canonical
            and item.gender == ('male' if suffix[2] == 'm' else 'female'))


class Catalog:
    def __init__(self, document, cash_document=None):
        by_id = {}
        self.warning = None
        for row in document.get("items", []) + document.get("scrolls", []):
            if not isinstance(row, dict) or not isinstance(row.get("id"), int) or not row.get("name"):
                continue
            item_id = row["id"]
            by_id[item_id] = Item(item_id, row["name"], row.get("category") == "Equipment",
                                  item_id // 10000 in (207, 233), row.get("tier"), gender=row.get('gender'),
                                  sub_category=row.get('sub_category'))
        for category in (cash_document or {}).get("categories", []):
            for row in category.get("items", []):
                if not isinstance(row, dict) or not isinstance(row.get("id"), int) or not row.get("name"):
                    continue
                by_id[row["id"]] = Item(row["id"], row["name"], row.get("category") == "Equipment",
                                        cash=True,gender=row.get('gender'),
                                        sub_category=row.get('sub_category'))
        self._index_items(list(by_id.values()))

    @classmethod
    def from_items(cls,items):
        catalog=cls({'items':[]});catalog._index_items(items);return catalog

    def _index_items(self,items):
        self.items = list(items)
        self.by_id = {item.game_id:item for item in self.items}
        self.names = {}
        self.read_names = {}
        self.glyph_names = {}
        for item in self.items:
            self.names.setdefault(key(item.name), []).append(item)
            self.read_names.setdefault(item_words(item.name), []).append(item)
            self.glyph_names.setdefault(glyph_key(item_words(item.name)), []).append(item)
        self.resolved = {}

    def candidates(self, visible_name, tier=None):
        name = key(visible_name or "")
        if name in self.names:
            return self.names[name]
        gender = re.fullmatch(r'(.+?)\s+\(([mf])\)', name)
        if gender:
            base, suffix = gender.groups()
            candidates = (self.names.get(base) or self.read_names.get(item_words(base))
                          or self.glyph_names.get(glyph_key(item_words(base)), []))
            expected = 'male' if suffix == 'm' else 'female'
            return [i for i in candidates if i.equipment and i.gender == expected]
        if not clipped_name(name):
            words=item_words(name)
            return (self.read_names.get(words) or self.glyph_names.get(glyph_key(words), [])) if len(words)>=6 else []
        prefix = item_words(unclipped_name(name))
        if len(prefix) < 6:
            return []
        candidates = [i for name_key, items in self.read_names.items() if name_key.startswith(prefix) for i in items]
        if not candidates:
            candidates=[i for name_key,items in self.read_names.items() if glyph_key(name_key).startswith(glyph_key(prefix)) for i in items]
        # Native icon colour is a hypothetical scroll tier, even on equipment.
        # It can narrow a proven scroll family, never a mixed prefix or a ring.
        if tier and candidates and all(item.tier for item in candidates):
            return [item for item in candidates if key(item.tier) == key(tier)]
        return candidates

    def resolve(self, visible_name, tier=None):
        """Unique canonical/formatted name or UI ellipsis prefix; no fuzzy guesses."""
        if not visible_name:
            return None
        name = key(visible_name)
        identity = (name, tier)
        if identity in self.resolved:
            return self.resolved[identity]
        candidates = self.candidates(visible_name,tier)
        result = candidates[0] if len(candidates) == 1 else None
        if len(self.resolved) >= 512:
            self.resolved.clear()
        self.resolved[identity] = result
        return result


@dataclass(frozen=True)
class Quote:
    game_id: int
    price: float | None
    fetched_at: float
    observed_at: float | None
    sample_count: int
    source: str
    url: str
    period: str
    basis: str = "reported prices (asks + sold)"
    lowest_ask: float | None = None
    low: float | None = None
    high: float | None = None
    per_set: bool = False
    world: str = WORLD
    condition: str = "clean"
    uncertain: bool = False
    published_at: float | None = None

    def expires_at(self, ttl=DEFAULT_TTL):
        if self.published_at is not None:
            return min(self.fetched_at + ttl, self.published_at + MAX_SNAPSHOT_AGE)
        return self.fetched_at + ttl

    def cache_valid(self, now=None, ttl=DEFAULT_TTL):
        now = time.time() if now is None else now
        return 0 <= now - self.fetched_at and now < self.expires_at(ttl)

    def fresh(self, now=None, ttl=DEFAULT_TTL):
        now = time.time() if now is None else now
        return (self.world == WORLD and self.cache_valid(now, ttl)
                and self.observed_at is not None and -300 <= now - self.observed_at <= MAX_MARKET_AGE)


@dataclass(frozen=True)
class Verdict:
    label: str
    tone: str
    detail: str
    unit_price: float | None = None
    delta: float | None = None
    net_margin: float | None = None


def compare(item, quantity, mesos, quote, now=None, ttl=DEFAULT_TTL):
    if item is None:
        return Verdict("Unresolved", "muted", "Full item name or scroll tier needed")
    if not number(quantity) or not number(mesos) or quantity != int(quantity) or mesos != int(mesos):
        return Verdict("Unreadable", "muted", "Waiting for a clean price reading")
    unit = float(mesos) if item.per_set else mesos / quantity
    if quote is None or quote.price is None:
        return Verdict("No reference", "muted", quote.basis if quote else "No market reference available", unit)
    if quote.world != WORLD or quote.game_id != item.game_id or quote.per_set != item.per_set or quote.condition != "clean":
        return Verdict("Reference mismatch", "muted", "Item, unit or condition differs", unit)
    if not quote.fresh(now, ttl):
        return Verdict("Expired", "muted", "Refresh needed before comparison", unit)
    if quote.sample_count < 5 or quote.uncertain:
        return Verdict("Thin data", "muted", f"{quote.sample_count} samples; reference only", unit)
    delta = (unit / quote.price - 1) * 100
    net = quote.price * 0.97 - unit  # 3% sale fee shown by the live Classic World shop.
    # User preference: assume equipment is unscrolled, matching the clean reference.
    if unit <= quote.price * 0.8:
        return Verdict("Below reference", "green", f"{abs(delta):.0f}% below • check liquidity", unit, delta, net)
    if unit > quote.price * 1.2:
        return Verdict("Above reference", "red", f"{delta:.0f}% above reference", unit, delta, net)
    return Verdict("Near reference", "blue", f"{delta:+.0f}% versus reference", unit, delta, net)


def age_text(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h {seconds % 3600 // 60}m"
    return f"{seconds // 86400}d {seconds % 86400 // 3600}h"
