from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

@dataclass
class CollectorItem:
    title: str
    url: str = ''
    summary: str = ''
    published_at: Optional[datetime] = None

@dataclass
class CollectorResult:
    items: List[CollectorItem]
    error: Optional[str] = None

class Collector:
    def fetch(self, section_name: str, config: dict) -> CollectorResult:
        raise NotImplementedError