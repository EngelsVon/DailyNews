import asyncio
from mcp.server.fastmcp import FastMCP
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from config import DevConfig
from flask import Flask
import os

# 复用与Flask一致的数据库配置
app = Flask(__name__)
app.config.from_object(DevConfig)
db = SQLAlchemy(app)

# 与app.py一致的模型定义（为避免循环依赖，重复定义）
class Section(db.Model):
    __tablename__ = 'sections'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(255), default='')
    enabled = db.Column(db.Boolean, default=True)
    fetch_method = db.Column(db.String(50), default='crawler')
    update_interval_minutes = db.Column(db.Integer, default=60)
    last_run_at = db.Column(db.DateTime, nullable=True)
    config_json = db.Column(db.Text, default='{}')

class NewsItem(db.Model):
    __tablename__ = 'news_items'
    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey('sections.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    summary = db.Column(db.Text, default='')
    url = db.Column(db.String(512), default='')
    published_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    section = db.relationship('Section', backref=db.backref('news_items', lazy=True, cascade="all, delete-orphan"))

mcp = FastMCP(
    name="dailynews_mcp",
    version="0.1.0",
    description="MCP server for Daily News Station"
)

@mcp.tool()
async def ping() -> str:
    """健康检查工具"""
    return "pong"

@mcp.tool()
async def get_sections() -> list:
    """获取所有板块名称列表"""
    with app.app_context():
        rows = Section.query.order_by(Section.name).all()
        return [r.name for r in rows]

@mcp.tool()
async def get_latest(section: str, limit: int = 10) -> list:
    """获取某板块最新消息，返回[{title, url, summary, published_at}]"""
    with app.app_context():
        sec = Section.query.filter_by(name=section).first()
        if not sec:
            return []
        items = NewsItem.query.filter_by(section_id=sec.id).order_by(NewsItem.published_at.desc()).limit(limit).all()
        def to_dict(n: NewsItem):
            return {
                'title': n.title,
                'url': n.url,
                'summary': n.summary,
                'published_at': n.published_at.isoformat() if n.published_at else None,
                'section': sec.name,
            }
        return [to_dict(n) for n in items]

@mcp.tool()
async def search_news(keyword: str, limit: int = 20) -> list:
    """根据关键词搜索新闻，返回匹配的消息列表"""
    with app.app_context():
        query = NewsItem.query.filter(
            (NewsItem.title.contains(keyword)) | 
            (NewsItem.summary.contains(keyword))
        ).order_by(NewsItem.published_at.desc()).limit(limit)
        items = query.all()
        results = []
        for n in items:
            section_name = n.section.name if n.section else 'Unknown'
            results.append({
                'title': n.title,
                'url': n.url,
                'summary': n.summary,
                'published_at': n.published_at.isoformat() if n.published_at else None,
                'section': section_name,
            })
        return results

@mcp.tool()
async def trigger_fetch(section: str) -> dict:
    """手动触发某板块的内容采集"""
    from app import run_section_fetch
    with app.app_context():
        sec = Section.query.filter_by(name=section).first()
        if not sec:
            return {'success': False, 'message': f'板块 "{section}" 不存在'}
        try:
            run_section_fetch(sec.id)
            return {'success': True, 'message': f'板块 "{section}" 采集完成'}
        except Exception as e:
            return {'success': False, 'message': f'采集失败: {str(e)}'}

@mcp.tool()
async def get_section_stats() -> list:
    """获取所有板块的统计信息：名称、状态、消息数量、最后更新时间"""
    with app.app_context():
        sections = Section.query.order_by(Section.name).all()
        stats = []
        for s in sections:
            item_count = NewsItem.query.filter_by(section_id=s.id).count()
            stats.append({
                'name': s.name,
                'description': s.description,
                'enabled': s.enabled,
                'fetch_method': s.fetch_method,
                'update_interval_minutes': s.update_interval_minutes,
                'item_count': item_count,
                'last_run_at': s.last_run_at.isoformat() if s.last_run_at else None,
            })
        return stats

if __name__ == "__main__":
    # 确保数据库可用
    with app.app_context():
        db.create_all()
    # 选择传输方式（默认stdio），可通过环境变量切换到sse
    transport = os.environ.get('FASTMCP_TRANSPORT', 'stdio').lower()
    if transport not in ('stdio', 'sse'):
        transport = 'stdio'
    # FastMCP 的 host/port 会从环境变量 FASTMCP_HOST/FASTMCP_PORT 读取
    # 当 transport=sse 时会启动HTTP SSE服务并监听对应端口
    mcp.run('sse' if transport == 'sse' else 'stdio')