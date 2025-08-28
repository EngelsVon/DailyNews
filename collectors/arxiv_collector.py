import feedparser
import requests
from urllib.parse import urlencode
from .base import Collector, CollectorResult, CollectorItem
from datetime import datetime
import xml.etree.ElementTree as ET

BASE = "http://export.arxiv.org/api/query?"

class ArxivCollector(Collector):
    def fetch(self, section_name: str, config: dict) -> CollectorResult:
        query = config.get('query', 'cat:cs.CL')  # 默认计算语言学
        max_results = int(config.get('max_results', 20))
        order = config.get('order', 'lastUpdatedDate')
        timeout = config.get('timeout', 30)
        
        params = {
            'search_query': query,
            'start': 0,
            'max_results': max_results,
            'sortBy': order
        }
        url = BASE + urlencode(params)
        print(f"[ArxivCollector] 正在访问: {url}")
        
        try:
            # 使用 requests 先获取内容，带自定义 User-Agent 和超时
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            
            print(f"[ArxivCollector] HTTP 状态: {response.status_code}, 内容长度: {len(response.content)}")
            
            # 使用 feedparser 解析
            d = feedparser.parse(response.content)
            
            print(f"[ArxivCollector] feedparser 状态: {getattr(d, 'status', 'unknown')}")
            print(f"[ArxivCollector] 解析到条目数: {len(getattr(d, 'entries', []))}")
            
            if hasattr(d, 'bozo') and d.bozo:
                print(f"[ArxivCollector] 警告: feedparser 报告解析异常: {getattr(d, 'bozo_exception', 'unknown')}")
            
            items = []
            for i, entry in enumerate(d.entries):
                try:
                    # 处理发布时间
                    published = None
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        try:
                            published = datetime(*entry.published_parsed[:6])
                        except (ValueError, TypeError) as e:
                            print(f"[ArxivCollector] 条目 {i} 时间解析失败: {e}")
                    
                    # 获取摘要
                    summary = ''
                    if hasattr(entry, 'summary'):
                        summary = entry.summary
                    elif hasattr(entry, 'description'):
                        summary = entry.description
                    
                    # 获取标题和链接
                    title = getattr(entry, 'title', '').strip()
                    url = getattr(entry, 'link', '').strip()
                    
                    if not title:
                        print(f"[ArxivCollector] 条目 {i} 无标题，跳过")
                        continue
                    
                    items.append(CollectorItem(
                        title=title,
                        url=url,
                        summary=summary,
                        published_at=published
                    ))
                    
                    print(f"[ArxivCollector] 成功解析条目 {i}: {title[:50]}...")
                    
                except Exception as e:
                    print(f"[ArxivCollector] 条目 {i} 解析失败: {e}")
                    continue
            
            print(f"[ArxivCollector] 最终获取 {len(items)} 条有效数据")
            return CollectorResult(items=items)
            
        except requests.RequestException as e:
            print(f"[ArxivCollector] 网络请求失败: {e}")
            return CollectorResult(items=[], error=f"网络请求失败: {e}")
        except Exception as e:
            print(f"[ArxivCollector] 未知错误: {e}")
            return CollectorResult(items=[], error=f"解析失败: {e}")