import feedparser
from .base import Collector, CollectorResult, CollectorItem
from datetime import datetime
from typing import List

class RSSCollector(Collector):
    def fetch(self, section_name: str, config: dict) -> CollectorResult:
        urls = config.get('rss_urls', [])
        max_items = int(config.get('max_items', 20))
        items: List[CollectorItem] = []
        for url in urls:
            d = feedparser.parse(url)
            for entry in d.entries[:max_items]:
                published = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                items.append(CollectorItem(
                    title=getattr(entry, 'title', ''),
                    url=getattr(entry, 'link', ''),
                    summary=getattr(entry, 'summary', ''),
                    published_at=published
                ))
        return CollectorResult(items=items)