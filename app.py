from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, UTC
import os
import json
import subprocess
import sys
import time
import requests
import threading
from threading import Lock

from config import DevConfig

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config.from_object(DevConfig)

db = SQLAlchemy(app)
scheduler = BackgroundScheduler(timezone="UTC")

# 后台翻译锁，防止同时运行多个翻译任务
translation_lock = Lock()

# Models
class Section(db.Model):
    __tablename__ = 'sections'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(255), default='')
    enabled = db.Column(db.Boolean, default=True)
    fetch_method = db.Column(db.String(50), default='crawler')  # crawler | gemini | manual | arxiv | rss
    update_interval_minutes = db.Column(db.Integer, default=60)
    last_run_at = db.Column(db.DateTime, nullable=True)
    config_json = db.Column(db.Text, default='{}')  # 保存该板块自定义配置

class NewsItem(db.Model):
    __tablename__ = 'news_items'
    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey('sections.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    summary = db.Column(db.Text, default='')
    url = db.Column(db.String(512), default='')
    published_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # 新增：译文字段
    title_translated = db.Column(db.Text, default='')
    summary_translated = db.Column(db.Text, default='')
    translated_at = db.Column(db.DateTime, nullable=True)  # 翻译时间戳

    section = db.relationship('Section', backref=db.backref('news_items', lazy=True, cascade="all, delete-orphan"))

# 后台翻译工具函数
def get_translation_settings():
    """从环境变量或配置中获取翻译设置"""
    return {
        'method': os.environ.get('AUTO_TRANSLATE_METHOD', 'free'),  # free | gemini | none
        'target_lang': os.environ.get('AUTO_TRANSLATE_TARGET', 'zh-CN'),
        'source_lang': os.environ.get('AUTO_TRANSLATE_SOURCE', 'en'),
        'mymemory_email': DevConfig.MYMEMORY_EMAIL,
        'gemini_cmd': DevConfig.GEMINI_CLI_CMD,
        'batch_size': int(os.environ.get('AUTO_TRANSLATE_BATCH_SIZE', '10')),  # 每批处理数量
        'delay_seconds': float(os.environ.get('AUTO_TRANSLATE_DELAY', '2.0'))  # 每条间隔
    }


def ensure_db():
    with app.app_context():
        db.create_all()

# Schedulers

def run_section_fetch(section_id: int):
    with app.app_context():
        section = Section.query.get(section_id)
        if not section:
            print(f"[Fetch] skip: section not found, id={section_id}")
            return
        if not section.enabled:
            print(f"[Fetch] skip: section disabled, id={section.id}, name={section.name}")
            return
        # 解析配置
        try:
            cfg = json.loads(section.config_json or '{}')
        except Exception:
            cfg = {}
        print(f"[Fetch] start: id={section.id}, name={section.name}, method={section.fetch_method}")
        result = None
        if section.fetch_method == 'arxiv':
            from collectors.arxiv_collector import ArxivCollector
            result = ArxivCollector().fetch(section.name, cfg)
        elif section.fetch_method == 'gemini':
            from collectors.gemini_collector import GeminiCollector
            result = GeminiCollector().fetch(section.name, cfg)
        elif section.fetch_method == 'rss':
            from collectors.rss_collector import RSSCollector
            result = RSSCollector().fetch(section.name, cfg)
        else:
            # 默认：不做任何事（可扩展crawler）
            result = None

        if result and result.items:
            # 简单去重：基于title+url
            existing = {(n.title or '') + '|' + (n.url or '') for n in NewsItem.query.filter_by(section_id=section.id).all()}
            added = 0
            for it in result.items:
                key = f"{it.title}|{it.url}"
                if key in existing:
                    continue
                db.session.add(NewsItem(
                    section_id=section.id,
                    title=it.title[:255] if it.title else '',
                    url=it.url[:512] if it.url else '',
                    summary=it.summary or '',
                    published_at=it.published_at or datetime.now(UTC),
                ))
                added += 1
            db.session.commit()
            print(f"[Fetch] fetched={len(result.items)}, added={added}")
        else:
            if result and getattr(result, 'error', None):
                print(f"[Fetch] error: {result.error}")
            print("[Fetch] no items returned")
        section.last_run_at = datetime.now(UTC)
        db.session.commit()


def schedule_section(section: Section):
    job_id = f"section_{section.id}"
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass
    if section.enabled and section.update_interval_minutes > 0:
        scheduler.add_job(
            func=run_section_fetch,
            trigger=IntervalTrigger(minutes=section.update_interval_minutes),
            id=job_id,
            kwargs={'section_id': section.id},
            replace_existing=True,
        )

# Routes
@app.route('/')
def index():
    sections = Section.query.order_by(Section.name).all()
    latest = {}
    for s in sections:
        items = (NewsItem.query
                 .filter_by(section_id=s.id)
                 .order_by(NewsItem.created_at.desc(), NewsItem.published_at.desc())
                 .limit(100)
                 .all())
        # 为每个条目添加翻译状态
        for item in items:
            item.has_translation = bool(item.title_translated or item.summary_translated)
            try:
                now = datetime.utcnow()
                if item.created_at:
                    item.is_new = (now - item.created_at).total_seconds() <= 12*3600
                else:
                    item.is_new = False
            except Exception:
                item.is_new = False
        latest[s.id] = items
    return render_template('index.html', sections=sections, latest=latest)

@app.route('/sections')
def manage_sections():
    sections = Section.query.order_by(Section.id.desc()).all()
    return render_template('sections.html', sections=sections)

@app.route('/sections', methods=['POST'])
def create_section():
    name = request.form.get('name', '').strip()
    desc = request.form.get('description', '').strip()
    fetch_method = request.form.get('fetch_method', 'crawler')
    interval = int(request.form.get('update_interval_minutes', '60') or 60)
    if not name:
        flash('名称不能为空', 'error')
        return redirect(url_for('manage_sections'))
    
    # 检查是否已存在相同名称的板块
    existing = Section.query.filter_by(name=name).first()
    if existing:
        flash(f'板块名称 "{name}" 已存在，请使用其他名称', 'error')
        return redirect(url_for('manage_sections'))
    
    try:
        s = Section(name=name, description=desc, fetch_method=fetch_method, update_interval_minutes=interval)
        db.session.add(s)
        db.session.commit()
        schedule_section(s)
        flash('创建成功', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"创建板块失败: {e}")
        flash(f'创建失败: {str(e)}', 'error')
    
    return redirect(url_for('manage_sections'))

@app.route('/sections/<int:section_id>/toggle', methods=['POST'])
def toggle_section(section_id):
    s = Section.query.get_or_404(section_id)
    s.enabled = not s.enabled
    db.session.commit()
    schedule_section(s)
    return jsonify({'ok': True, 'enabled': s.enabled})

@app.route('/sections/<int:section_id>/delete', methods=['POST'])
def delete_section(section_id):
    s = Section.query.get_or_404(section_id)
    NewsItem.query.filter_by(section_id=section_id).delete()
    db.session.delete(s)
    db.session.commit()
    try:
        scheduler.remove_job(f"section_{section_id}")
    except Exception:
        pass
    flash('删除成功', 'success')
    return redirect(url_for('manage_sections'))

@app.route('/sections/<int:section_id>/run', methods=['POST'])
def run_once(section_id):
    run_section_fetch(section_id)
    return jsonify({'ok': True})

@app.route('/sections/<int:section_id>/config', methods=['POST'])
def update_section_config(section_id):
    s = Section.query.get_or_404(section_id)
    data = request.get_json(silent=True) or {}
    cfg_payload = data.get('config_json', '')
    # 允许传入对象或字符串
    if isinstance(cfg_payload, dict):
        cfg_str = json.dumps(cfg_payload, ensure_ascii=False)
    else:
        cfg_str = str(cfg_payload or '').strip()
    if not cfg_str:
        cfg_str = '{}'
    # 校验JSON格式
    try:
        json.loads(cfg_str)
    except Exception:
        return jsonify({'ok': False, 'error': 'Invalid JSON'}), 400
    s.config_json = cfg_str
    db.session.commit()
    return jsonify({'ok': True})

# Settings routes
@app.route('/settings')
def settings():
    # 将配置对象传入模板，便于显示默认值
    return render_template('settings.html', config=DevConfig)

# 测试翻译API
@app.route('/api/translate/test', methods=['POST'])
def test_translate():
    data = request.get_json()
    method = data.get('method', 'none')
    cmd_override = data.get('cmd')
    # 新增：可选源语言，默认 en，避免 MyMemory 对 AUTO 的报错
    source_lang = (data.get('source_lang') or 'en').strip()
    if source_lang.lower() == 'auto':
        source_lang = 'en'
    # 可选：MyMemory 邮箱
    mymem_de = (data.get('de') or '').strip() or DevConfig.MYMEMORY_EMAIL
    
    if method == 'none':
        return jsonify({'success': True, 'message': '翻译已禁用'})
    elif method == 'browser':
        return jsonify({'success': True, 'message': '浏览器翻译可用（前端处理）'})
    elif method == 'free':
        # 使用 MyMemory 免费API 进行连通性测试
        try:
            extra = {}
            if mymem_de:
                extra['de'] = mymem_de
            r = requests.get(
                'https://api.mymemory.translated.net/get',
                params={ 'q': 'hello', 'langpair': f"{source_lang}|zh-CN", **extra },
                timeout=8
            )
            if r.status_code == 200:
                data = r.json()
                txt = (data.get('responseData') or {}).get('translatedText')
                if txt:
                    return jsonify({'success': True, 'message': '免费翻译服务可用'})
                return jsonify({'success': False, 'message': '免费翻译返回异常数据'})
            if r.status_code == 429:
                return jsonify({'success': False, 'message': '免费翻译触发限流(429)，请稍后重试或在设置中填写 MyMemory 邮箱以提高配额'})
            return jsonify({'success': False, 'message': f'免费翻译HTTP错误: {r.status_code}'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'免费翻译测试失败: {str(e)}'})
    elif method == 'gemini':
        # 使用现有的Gemini CLI配置，允许前端覆盖
        cmd = cmd_override or DevConfig.GEMINI_CLI_CMD or os.environ.get('GEMINI_CLI_CMD') or 'gemini'
        if not cmd:
            return jsonify({'success': False, 'message': 'Gemini CLI命令未配置，请在设置中配置GEMINI_CLI_CMD'})
        try:
            env = os.environ.copy()
            if DevConfig.GEMINI_API_KEY and 'GEMINI_API_KEY' not in env:
                env['GEMINI_API_KEY'] = DevConfig.GEMINI_API_KEY
            result = subprocess.run(
                [cmd, '--help'],
                shell=False,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=10,
                env=env
            )
            if result.returncode == 0:
                return jsonify({'success': True, 'message': 'Gemini CLI连接正常'})
            else:
                return jsonify({'success': False, 'message': f'Gemini CLI错误: {result.stderr or result.stdout}'})
        except subprocess.TimeoutExpired:
            return jsonify({'success': False, 'message': 'Gemini CLI超时'})
        except FileNotFoundError:
            return jsonify({'success': False, 'message': f'未找到命令: {cmd}，请确认路径或在设置中填写完整路径'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Gemini CLI测试失败: {str(e)}'})
    else:
        return jsonify({'success': False, 'message': f'未知翻译方式: {method}'})

# 翻译API
@app.route('/api/translate', methods=['POST'])
def translate_text():
    data = request.get_json()
    texts = data.get('texts', [])  # 支持批量翻译
    target_lang = data.get('target_lang', 'zh-CN')
    method = data.get('method', 'none')
    cmd_override = data.get('cmd')
    # 新增：可选源语言，默认 en，避免 MyMemory 对 AUTO 的报错
    source_lang = (data.get('source_lang') or 'en').strip()
    if source_lang.lower() == 'auto':
        source_lang = 'en'
    # 可选：MyMemory 邮箱
    mymem_de = (data.get('de') or '').strip() or DevConfig.MYMEMORY_EMAIL
    
    if method == 'none' or method == 'browser':
        return jsonify({'success': True, 'results': texts})  # 原文返回
    elif method == 'free':
        # 使用 MyMemory 免费API 逐条翻译
        try:
            results = [];
            extra = {}
            if mymem_de:
                extra['de'] = mymem_de
            for text in texts:
                try:
                    # 安全截断到500字符，避免 MyMemory 的长度限制报错
                    safe_q = (text or '')[:500]

                    # 加入 429 指数回退重试（最多 3 次: 0.5s, 1.0s, 2.0s）
                    attempts = 0
                    wait = 0.5
                    translated = None
                    while attempts < 3 and translated is None:
                        r = requests.get(
                            'https://api.mymemory.translated.net/get',
                            params={ 'q': safe_q, 'langpair': f"{source_lang}|{target_lang}", **extra },
                            timeout=12
                        )
                        if r.status_code == 200:
                            j = r.json()
                            translated = ((j.get('responseData') or {}).get('translatedText') or '').strip() or text
                            break
                        elif r.status_code == 429:
                            attempts += 1
                            if attempts >= 3:
                                break
                            time.sleep(wait)
                            wait *= 2
                        else:
                            # 其他错误直接退出重试
                            break

                    if translated is None:
                        translated = text
                    results.append(translated)
                except Exception:
                    results.append(text)
            return jsonify({'success': True, 'results': results})
        except Exception as e:
            return jsonify({'success': False, 'message': f'免费翻译失败: {str(e)}'}), 500
    elif method == 'gemini':
        try:
            results = []
            cmd = cmd_override or DevConfig.GEMINI_CLI_CMD or os.environ.get('GEMINI_CLI_CMD') or 'gemini'
            env = os.environ.copy()
            if DevConfig.GEMINI_API_KEY and 'GEMINI_API_KEY' not in env:
                env['GEMINI_API_KEY'] = DevConfig.GEMINI_API_KEY
            for text in texts:
                prompt = f"请将以下文本翻译成{target_lang}，只返回翻译结果，不要解释：\n\n{text}"
                try:
                    result = subprocess.run(
                        [cmd, '--prompt', prompt],
                        shell=False,
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        errors='replace',
                        timeout=45,
                        env=env
                    )
                except FileNotFoundError:
                    return jsonify({'success': False, 'message': f'未找到命令: {cmd}，请在设置中填写完整路径或配置环境变量'}), 400
                if result.returncode == 0:
                    translated = (result.stdout or '').strip()
                    if not translated:
                        translated = text
                    results.append(translated)
                else:
                    # 失败则兜底原文
                    results.append(text)
            return jsonify({'success': True, 'results': results})
        except Exception as e:
            return jsonify({'success': False, 'message': f'翻译失败: {str(e)}'}), 500
    else:
        return jsonify({'success': False, 'message': f'未知翻译方式: {method}'})

# MCP服务状态
mcp_process = None

@app.route('/api/mcp/status')
def mcp_status():
    global mcp_process
    if mcp_process and mcp_process.poll() is None:
        return jsonify({'ok': True, 'running': True, 'pid': mcp_process.pid})
    else:
        return jsonify({'ok': True, 'running': False})

@app.route('/api/mcp/start', methods=['POST'])
def start_mcp():
    global mcp_process
    if mcp_process and mcp_process.poll() is None:
        return jsonify({'ok': False, 'error': 'MCP服务已在运行中'})
    
    try:
        data = request.get_json(silent=True) or {}
        port = int(data.get('port') or 0)
        env = os.environ.copy()
        # 允许通过环境变量控制FastMCP
        env.setdefault('FASTMCP_TRANSPORT', 'sse')
        if port:
            env['FASTMCP_PORT'] = str(port)
            env.setdefault('FASTMCP_HOST', '0.0.0.0')
        # 启动MCP服务器（使用sse时监听HTTP端口）
        mcp_process = subprocess.Popen(
            [sys.executable, '-m', 'mcp_server.server'],
            cwd=os.path.dirname(__file__),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # 合并stderr到stdout便于调试
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        time.sleep(1)  # 等待启动
        
        if mcp_process.poll() is None:
            return jsonify({'ok': True, 'message': f'MCP服务已启动，PID: {mcp_process.pid}', 'port': port or env.get('FASTMCP_PORT')})
        else:
            stderr = mcp_process.stderr.read().decode(errors='ignore') if mcp_process.stderr else ''
            return jsonify({'ok': False, 'error': f'MCP服务启动失败: {stderr}'})
    except Exception as e:
        return jsonify({'ok': False, 'error': f'启动MCP服务失败: {str(e)}'})

@app.route('/api/mcp/stop', methods=['POST'])
def stop_mcp():
    global mcp_process
    if not mcp_process or mcp_process.poll() is not None:
        return jsonify({'ok': False, 'error': 'MCP服务未在运行'})
    
    try:
        mcp_process.terminate()
        mcp_process.wait(timeout=5)
        return jsonify({'ok': True, 'message': 'MCP服务已停止'})
    except subprocess.TimeoutExpired:
        mcp_process.kill()
        return jsonify({'ok': True, 'message': 'MCP服务已强制停止'})
    except Exception as e:
        return jsonify({'ok': False, 'error': f'停止MCP服务失败: {str(e)}'})



def translate_text_background(text, settings):
    """后台翻译单条文本"""
    if not text or not text.strip():
        return text
    
    method = settings['method']
    if method == 'none':
        return text
    
    try:
        if method == 'free':
            # MyMemory 免费翻译
            extra = {}
            if settings['mymemory_email']:
                extra['de'] = settings['mymemory_email']
            
            # 对超长文本分段处理
            chunks = []
            text_chunks = [text[i:i+500] for i in range(0, len(text), 500)]
            
            for chunk in text_chunks:
                attempts = 0
                wait = 0.5
                translated_chunk = None
                
                while attempts < 3 and translated_chunk is None:
                    # 构建请求URL
                    params = {
                        'q': chunk,
                        'langpair': f"{settings['source_lang']}|{settings['target_lang']}"
                    }
                    params.update(extra)
                    
                    try:
                        import requests
                        response = requests.get('https://api.mymemory.translated.net/get', params=params, timeout=10)
                        if response.status_code == 200:
                            data = response.json()
                            if data.get('responseStatus') == 200:
                                translated_chunk = data['responseData']['translatedText']
                            else:
                                print(f"[BackgroundTranslation] MyMemory API错误: {data.get('responseDetails', 'Unknown error')}")
                                translated_chunk = chunk  # 失败时保持原文
                                break
                        else:
                            print(f"[BackgroundTranslation] HTTP错误 {response.status_code}")
                    except Exception as e:
                        print(f"[BackgroundTranslation] 请求异常: {e}")
                    
                    attempts += 1
                    if translated_chunk is None and attempts < 3:
                        time.sleep(wait)
                        wait *= 2  # 指数退避
                
                chunks.append(translated_chunk or chunk)
                
                # 请求间延时
                time.sleep(settings['delay_seconds'])
            
            return ''.join(chunks)
            
        elif method == 'gemini':
            # Gemini CLI 翻译
            import subprocess
            cmd = settings['gemini_cmd']
            if not cmd:
                return text
            
            prompt = f"请将以下文本翻译为{settings['target_lang']}，只返回翻译结果，不要任何解释：\n\n{text}"
            
            try:
                result = subprocess.run(
                    cmd.split() + [prompt],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    encoding='utf-8'
                )
                
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
                else:
                    print(f"[BackgroundTranslation] Gemini CLI失败: {result.stderr}")
                    return text
            except subprocess.TimeoutExpired:
                print("[BackgroundTranslation] Gemini CLI超时")
                return text
            except Exception as e:
                print(f"[BackgroundTranslation] Gemini CLI异常: {e}")
                return text
        else:
            return text
            
    except Exception as e:
        print(f"[BackgroundTranslation] 翻译失败: {e}")
        return text

# 后台翻译任务锁
translation_lock = threading.Lock()

def run_background_translation():
    """后台翻译任务：定期翻译未翻译的内容"""
    if not translation_lock.acquire(blocking=False):
        print("[BackgroundTranslation] 翻译任务已在运行中，跳过本次执行")
        return
    
    try:
        with app.app_context():
            settings = get_translation_settings()
            if settings['method'] == 'none':
                print("[BackgroundTranslation] 翻译已禁用")
                return
            
            # 查找未翻译的条目（优先处理最新的）
            untranslated = NewsItem.query.filter(
                (NewsItem.title_translated == '') | 
                (NewsItem.summary_translated == '') |
                (NewsItem.title_translated.is_(None)) |
                (NewsItem.summary_translated.is_(None))
            ).order_by(NewsItem.created_at.desc()).limit(settings['batch_size']).all()
            
            if not untranslated:
                print("[BackgroundTranslation] 没有待翻译的内容")
                return
            
            print(f"[BackgroundTranslation] 开始翻译 {len(untranslated)} 条内容")
            
            translated_count = 0
            for item in untranslated:
                try:
                    # 翻译标题
                    if not item.title_translated:
                        translated_title = translate_text_background(item.title, settings)
                        if translated_title != item.title:  # 只有翻译成功才保存
                            item.title_translated = translated_title
                            translated_count += 1
                    
                    # 翻译摘要
                    if not item.summary_translated and item.summary:
                        translated_summary = translate_text_background(item.summary, settings)
                        if translated_summary != item.summary:  # 只有翻译成功才保存
                            item.summary_translated = translated_summary
                            translated_count += 1
                    
                    # 更新翻译时间戳
                    if item.title_translated or item.summary_translated:
                        item.translated_at = datetime.now(UTC)
                    
                    # 保存到数据库
                    db.session.commit()
                    
                    # 延时避免过快请求
                    time.sleep(settings['delay_seconds'])
                    
                except Exception as e:
                    print(f"[BackgroundTranslation] 翻译条目 {item.id} 失败: {e}")
                    db.session.rollback()
                    continue
            
            print(f"[BackgroundTranslation] 完成，翻译了 {translated_count} 个字段")
            
    except Exception as e:
        print(f"[BackgroundTranslation] 后台翻译任务出错: {e}")
    finally:
        translation_lock.release()

# 获取缓存译文API
@app.route('/api/cached_translations')
def get_cached_translations():
    """获取指定板块的缓存译文"""
    section_id = request.args.get('section_id', type=int)
    if not section_id:
        return jsonify({'ok': False, 'error': 'section_id is required'}), 400
    
    # 查询该板块下有译文的条目
    items = NewsItem.query.filter_by(section_id=section_id).filter(
        (NewsItem.title_translated != '') | (NewsItem.summary_translated != '')
    ).all()
    
    translations = []
    for item in items:
        translation = {
            'item_id': item.id,
            'title_translated': item.title_translated if item.title_translated else None,
            'summary_translated': item.summary_translated if item.summary_translated else None,
            'translated_at': item.translated_at.isoformat() if item.translated_at else None
        }
        translations.append(translation)
    
    return jsonify({
        'ok': True,
        'translations': translations
    })

# 后台翻译控制API
@app.route('/api/translate/background/start', methods=['POST'])
def start_background_translation():
    """启动后台翻译"""
    try:
        # 检查翻译设置
        with app.app_context():
            settings = get_translation_settings()
            if settings['method'] == 'none':
                return jsonify({'ok': False, 'error': '翻译功能已禁用，请在设置中启用'}), 400
        
        # 手动触发一次后台翻译任务
        scheduler.add_job(
            func=run_background_translation,
            trigger='date',  # 立即执行一次
            id='manual_background_translation',
            replace_existing=True
        )
        
        return jsonify({'ok': True, 'message': '后台翻译任务已启动'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/translate/background/status', methods=['GET'])
def get_background_translation_status():
    """获取后台翻译状态"""
    try:
        with app.app_context():
            # 统计待翻译和已翻译的数量
            total_items = NewsItem.query.count()
            translated_items = NewsItem.query.filter(
                (NewsItem.title_translated != '') & 
                (NewsItem.summary_translated != '')
            ).count()
            
            # 检查是否有翻译任务正在运行
            is_running = not translation_lock.acquire(blocking=False)
            if not is_running:
                translation_lock.release()
            
            # 获取调度器状态
            scheduler_running = scheduler.running
            translation_job = scheduler.get_job('background_translation')
            job_active = translation_job is not None
            
            return jsonify({
                'ok': True,
                'status': {
                    'total_items': total_items,
                    'translated_items': translated_items,
                    'pending_items': total_items - translated_items,
                    'is_running': is_running,
                    'scheduler_active': scheduler_running,
                    'job_scheduled': job_active,
                    'next_run': translation_job.next_run_time.isoformat() if translation_job and translation_job.next_run_time else None
                }
            })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# Bootstrap
if __name__ == '__main__':
    ensure_db()
    # schedule all existing sections
    with app.app_context():
        for s in Section.query.all():
            schedule_section(s)
    
    # 添加后台翻译调度器（每10分钟运行一次）
    translation_interval = int(os.environ.get('AUTO_TRANSLATE_INTERVAL_MINUTES', '10'))
    if translation_interval > 0:
        scheduler.add_job(
            func=run_background_translation,
            trigger=IntervalTrigger(minutes=translation_interval),
            id='background_translation',
            replace_existing=True,
        )
    
    scheduler.start()
    app.run(host='0.0.0.0', port=5000, debug=True)