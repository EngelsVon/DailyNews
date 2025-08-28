from .base import Collector, CollectorResult
from .rss_collector import RSSCollector
from .arxiv_collector import ArxivCollector
from .gemini_collector import GeminiCollector

__all__ = [
    'Collector', 'CollectorResult',
    'RSSCollector', 'ArxivCollector', 'GeminiCollector'
]