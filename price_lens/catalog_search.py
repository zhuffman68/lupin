"""Pre-normalized local suggestions; preserve duplicate-name ambiguity."""
from .domain import item_words,key


class CatalogSearch:
    def __init__(self):self.catalog=None;self.rows=()

    def find(self,catalog,query):
        if catalog is not self.catalog:
            self.catalog=catalog
            self.rows=tuple((item,item_words(item.name),item.name.casefold()) for item in catalog.items) if catalog else ()
        if not catalog or len(query)<2:return []
        exact=catalog.by_id.get(int(query)) if query.isdecimal() else None
        if exact:return [[exact]]
        terms=query.split()
        found=[row for row in self.rows if all(term in row[1] for term in terms)]
        found.sort(key=lambda row:(row[1]!=query,not row[1].startswith(query),row[2],row[0].game_id))
        groups={}
        for item,_,_ in found:groups.setdefault(key(item.name),[]).append(item)
        return list(groups.values())
