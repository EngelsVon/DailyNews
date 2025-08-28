import os
import subprocess
import json
import re
import tempfile
import glob
from .base import Collector, CollectorResult, CollectorItem
from datetime import datetime
from config import DevConfig

class GeminiCollector(Collector):
    def _resolve_cmd(self, config: dict) -> str:
        # 优先顺序：config.cmd -> 环境变量 -> 配置 -> 常见可执行名候选
        candidate = config.get('cmd') or os.environ.get('GEMINI_CLI_CMD') or DevConfig.GEMINI_CLI_CMD
        # 在 Windows 上也尝试 gemini.cmd
        candidates = [c for c in [candidate, 'gemini', 'gemini-cli', 'gemini.cmd'] if c]
        from shutil import which
        for c in candidates:
            path = which(c)
            if path:
                return path  # 返回绝对路径，避免子进程 PATH 差异
        # 返回第一个候选（允许后续报错并记录stderr）
        return candidates[0] if candidates else 'gemini'

    def _force_json(self, text: str):
        # 优先尝试直接解析
        s = (text or '').strip()
        try:
            return json.loads(s)
        except Exception:
            pass
        # 尝试从 Markdown 代码块中提取
        try:
            m = re.search(r"```(?:json)?\s*([\s\S]*?)```", s, flags=re.IGNORECASE)
            if m:
                inner = m.group(1).strip()
                try:
                    return json.loads(inner)
                except Exception:
                    s = inner  # 继续下面的数组提取
        except Exception:
            pass
        # 通用：从首个 '[' 开始做配对括号扫描，提取完整 JSON 数组
        l = s.find('[')
        if l != -1:
            depth = 0
            for i in range(l, len(s)):
                ch = s[i]
                if ch == '[':
                    depth += 1
                elif ch == ']':
                    depth -= 1
                    if depth == 0:
                        candidate = s[l:i+1]
                        try:
                            return json.loads(candidate)
                        except Exception:
                            break
        # 退而求其次：对象提取（若模型返回了 { items: [...] }）
        l = s.find('{')
        if l != -1:
            depth = 0
            in_str = False
            esc = False
            for i in range(l, len(s)):
                ch = s[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == '\\':
                        esc = True
                    elif ch == '"':
                        in_str = False
                else:
                    if ch == '"':
                        in_str = True
                    elif ch == '{':
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0:
                            candidate = s[l:i+1]
                            try:
                                obj = json.loads(candidate)
                                if isinstance(obj, dict) and 'items' in obj:
                                    return obj['items']
                                return obj
                            except Exception:
                                break
        # 最终失败：抛出原始开头错误，便于定位
        raise ValueError('无法从输出中提取有效JSON，输出头: ' + s[:120])

    def _clean_output(self, out: str) -> str:
        if not out:
            return ''
        cleaned = []
        for ln in out.splitlines():
            s = ln.strip()
            # 过滤已知的非数据提示/遥测信息
            if not s:
                continue
            low = s.lower()
            if low.startswith('data collection is disabled'):
                continue
            if 'credentials' in low and ('loading' in low or 'loaded' in low):
                continue
            if s.startswith('ℹ') or s.startswith('i '):
                continue
            cleaned.append(ln)
        return '\n'.join(cleaned).strip()

    def _find_latest_error_report(self) -> str | None:
        candidates = []
        for d in [os.getcwd(), tempfile.gettempdir()]:
            try:
                for p in glob.glob(os.path.join(d, 'gemini-client-error-*.json')):
                    candidates.append(p)
            except Exception:
                pass
        if not candidates:
            return None
        try:
            candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            # 仅返回最近的一个
            return candidates[0]
        except Exception:
            return None

    def _print_error_report(self, path: str):
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                txt = f.read()
            data = None
            try:
                data = json.loads(txt)
            except Exception:
                pass
            print(f"[GeminiCollector] found error report: {path}")
            if isinstance(data, dict):
                # 尝试提取常见结构
                msg = data.get('message') or data.get('error') or ''
                status = data.get('status') or data.get('code') or ''
                cause = ''
                if isinstance(data.get('response'), dict):
                    resp = data['response']
                    msg = msg or resp.get('message') or ''
                    status = status or resp.get('status') or resp.get('code') or ''
                if isinstance(data.get('cause'), dict):
                    cause = data['cause'].get('message') or ''
                brief = f"status={status} message={msg or cause}"
                print(f"[GeminiCollector] API error detail: {brief[:300]}")
            else:
                print(f"[GeminiCollector] error report content head: {txt[:300]}")
        except Exception as e:
            print(f"[GeminiCollector] failed to read error report {path}: {e}")

    # 新增：从参数中提取模型名（用于 Python SDK 回退）
    def _extract_model(self, args) -> str:
        model = 'gemini-1.5-flash'
        try:
            if isinstance(args, list):
                for i, a in enumerate(args):
                    if a in ('-m', '--model') and i + 1 < len(args):
                        return str(args[i + 1])
        except Exception:
            pass
        return model

    # 新增：使用 google-generativeai 的 Python SDK 作为回退方案
    def _sdk_generate(self, prompt: str, model: str, timeout: int, env: dict) -> str | None:
        try:
            import google.generativeai as genai
        except Exception:
            print("[GeminiCollector] Python SDK fallback unavailable: 请安装 google-generativeai 包")
            return None
        api_key = (env or {}).get('GEMINI_API_KEY') or (env or {}).get('GOOGLE_API_KEY') or DevConfig.GEMINI_API_KEY
        if not api_key:
            print("[GeminiCollector] 无法使用 Python SDK 回退：缺少 GEMINI_API_KEY/GOOGLE_API_KEY")
            return None
        try:
            genai.configure(api_key=api_key)
            model_name = model or 'gemini-1.5-flash'
            gm = genai.GenerativeModel(model_name)
            # 尽可能请求 JSON 输出
            resp = gm.generate_content(
                prompt,
                generation_config={
                    'response_mime_type': 'application/json'
                }
            )
            txt = getattr(resp, 'text', None)
            if not txt:
                try:
                    # 兼容不同版本 SDK 的返回结构
                    if getattr(resp, 'candidates', None):
                        parts = resp.candidates[0].content.parts
                        if parts and hasattr(parts[0], 'text'):
                            txt = parts[0].text
                except Exception:
                    pass
            return (txt or '').strip()
        except Exception as e:
            print(f"[GeminiCollector] Python SDK fallback error: {e}")
            return None

    def _run_gemini(self, prompt: str, cmd_args: list, timeout: int = 120, env: dict | None = None) -> str:
        """运行 Gemini CLI，先尝试 --prompt，失败则回退到 stdin"""
        try:
            # 尝试使用 --prompt 参数
            full_args = cmd_args + ['--prompt', prompt]
            result = subprocess.run(
                full_args,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=timeout,
                check=True,
                env=env
            )
            if result.stderr:
                print(f"[GeminiCollector] CLI stderr(head): {(result.stderr or '')[:400]}")
            return result.stdout
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            if isinstance(e, FileNotFoundError):
                print(f"[GeminiCollector] 命令未找到: {' '.join(cmd_args)}")
                print("[GeminiCollector] 请确保：")
                print("  1. 已安装 Gemini CLI: npm install -g @google/generative-ai")
                print("  2. 命令在 PATH 中可用，或在 config_json 中指定完整路径")
                print("  3. 已设置 GEMINI_API_KEY 环境变量")
                print(f"  4. 可在板块配置中覆盖: {{\"cmd\": \"C:\\path\\to\\gemini.exe\"}}")
                raise Exception(f"Gemini CLI 未找到: {' '.join(cmd_args)}")
            # --prompt 参数可能不支持或执行过慢，回退到 stdin
            print(f"[GeminiCollector] --prompt 失败或超时，回退到 stdin: {e}")
            try:
                result = subprocess.run(
                    cmd_args,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=timeout,
                    check=True,
                    env=env
                )
                if result.stderr:
                    print(f"[GeminiCollector] CLI stderr(head): {(result.stderr or '')[:400]}")
                return result.stdout
            except FileNotFoundError:
                print(f"[GeminiCollector] 命令未找到: {' '.join(cmd_args)}")
                print("[GeminiCollector] 请确保：")
                print("  1. 已安装 Gemini CLI: npm install -g @google/generative-ai")
                print("  2. 命令在 PATH 中可用，或在 config_json 中指定完整路径")
                print("  3. 已设置 GEMINI_API_KEY 环境变量")
                print(f"  4. 可在板块配置中覆盖: {{\"cmd\": \"C:\\path\\to\\gemini.exe\"}}")
                raise Exception(f"Gemini CLI 未找到: {' '.join(cmd_args)}")
            except subprocess.CalledProcessError as e2:
                detail = ''
                try:
                    detail = (e2.stderr or e2.stdout or '')
                except Exception:
                    detail = ''
                print(f"[GeminiCollector] CLI stderr/stdout: {detail[:400]}")
                raise Exception(f"Gemini CLI 执行失败: {e2}")
            except subprocess.TimeoutExpired as e3:
                print("[GeminiCollector] CLI 执行超时：请考虑：")
                print("  - 在板块配置中增加 args（如: ['generate','-m','gemini-1.5-flash']）")
                print("  - 确保已设置 GEMINI_API_KEY，且网络可访问 Google 服务")
                print("  - 在板块配置中提升 timeout（单位秒），如: {\"timeout\": 180}")
                raise Exception(f"Gemini CLI 执行超时: {e3}")

    # 解析输出为JSON的辅助函数保持不变
    def fetch(self, section_name: str, config: dict) -> CollectorResult:
        cmd = self._resolve_cmd(config or {})
        print(f"[GeminiCollector] using cmd: {cmd}")
        # 默认参数：10条新闻，聚焦最近3天
        max_items = config.get('max_items', 10)
        days_back = config.get('days_back', 3)
        # 强化提示词，严格要求输出纯JSON数组
        base_prompt = (
            f"你是新闻聚合助手。请整理与{section_name}相关的最新动态，"
            f"聚焦最近{days_back}天内的重要新闻，返回{max_items}条最有价值的内容。"
            "内容应涵盖创新技术、产品发布、行业动态、开源项目等热门话题。"
            "按条目给出标题、相关链接（若有）和一句话摘要，以及发布时间。"
            "必须只输出严格的JSON数组，不要输出任何解释、前后缀或Markdown围栏。"
            "每个元素为对象，字段固定为: title, url, summary, published_at(ISO8601格式)。"
            "示例格式: [{\"title\":\"标题\",\"url\":\"https://...\",\"summary\":\"摘要\",\"published_at\":\"2024-01-15T10:30:00Z\"}]"
        )
        prompt = config.get('prompt', base_prompt)
        args = config.get('args', [])
        # 兼容不同版本的 Gemini CLI：有的不支持 "generate" 子命令
        if isinstance(args, list) and args:
            if isinstance(args[0], str) and args[0].lower() == 'generate':
                args = args[1:]
        env = os.environ.copy()
        if DevConfig.GEMINI_API_KEY and 'GEMINI_API_KEY' not in env:
            env['GEMINI_API_KEY'] = DevConfig.GEMINI_API_KEY
        # 同时兼容部分 CLI 读取 GOOGLE_API_KEY 的环境变量名
        if 'GOOGLE_API_KEY' not in env and env.get('GEMINI_API_KEY'):
            env['GOOGLE_API_KEY'] = env['GEMINI_API_KEY']
        # 解析代理：板块配置 > 环境变量
        proxy = None
        try:
            proxy = (config.get('proxy') or os.environ.get('GEMINI_PROXY') or os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY') or os.environ.get('ALL_PROXY') or '').strip()
            if proxy:
                # 若缺少scheme，默认http
                if not re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', proxy):
                    proxy = 'http://' + proxy
                # 若args尚未包含 --proxy，则追加
                if isinstance(args, list) and '--proxy' not in args:
                    args = list(args) + ['--proxy', proxy]
                    print(f"[GeminiCollector] using proxy: {proxy}")
        except Exception:
            pass
        # 强制默认使用本地提供商（API Key），避免命中GCP缓存登录
        try:
            if isinstance(args, list):
                has_provider = any(a in ('-p', '--provider') for a in args)
                if not has_provider:
                    args = list(args) + ['-p', 'local']
                    print("[GeminiCollector] enforce provider: local")
        except Exception:
            pass
        try:
            # 组装命令与参数
            cmd_args = [cmd] + (args or [])
            out = self._run_gemini(prompt, cmd_args, timeout=config.get('timeout', 120), env=env)
            out = (out or '').strip()
            if not out:
                print("[GeminiCollector] empty stdout from CLI")
                # 诊断：尝试发现错误报告
                p = self._find_latest_error_report()
                if p:
                    self._print_error_report(p)
                # 回退：尝试 Python SDK 直接调用
                try:
                    model_name = self._extract_model(args)
                except Exception:
                    model_name = 'gemini-1.5-flash'
                sdk_out = self._sdk_generate(prompt, model_name, config.get('timeout', 120), env)
                if sdk_out:
                    try:
                        data = self._force_json(self._clean_output(sdk_out) or sdk_out)
                    except Exception as e3:
                        print(f"[GeminiCollector] SDK JSON parse failed: {e3}")
                        return CollectorResult(items=[])
                    else:
                        # 正确构建返回 items
                        items = []
                        if isinstance(data, dict) and 'items' in data:
                            data = data['items']
                        if not isinstance(data, list):
                            print(f"[GeminiCollector] SDK parsed JSON is not a list: type={type(data)}")
                            return CollectorResult(items=[])
                        for it in data:
                            if not isinstance(it, dict):
                                continue
                            published = None
                            ts = it.get('published_at')
                            if ts:
                                try:
                                    published = datetime.fromisoformat(ts.replace('Z','+00:00'))
                                except Exception:
                                    published = None
                            items.append(CollectorItem(
                                title=it.get('title',''),
                                url=it.get('url',''),
                                summary=it.get('summary',''),
                                published_at=published
                            ))
                        try:
                            mi = int(max_items)
                            if mi > 0:
                                items = items[:mi]
                        except Exception:
                            pass
                        return CollectorResult(items=items)
            # 针对非空 CLI 输出，进行清洗与 JSON 解析
            cleaned = self._clean_output(out)
            if cleaned != out:
                print("[GeminiCollector] cleaned CLI output for JSON parsing")
            # 若清洗后为空，认为只包含遥测/提示，直接回退到 SDK
            if not cleaned:
                print("[GeminiCollector] CLI output contains only telemetry/info; skip JSON parse and fallback to SDK")
                p = self._find_latest_error_report()
                if p:
                    self._print_error_report(p)
                try:
                    model_name = self._extract_model(args)
                except Exception:
                    model_name = 'gemini-1.5-flash'
                sdk_out = self._sdk_generate(prompt, model_name, config.get('timeout', 120), env)
                if sdk_out:
                    try:
                        data = self._force_json(self._clean_output(sdk_out) or sdk_out)
                    except Exception as e3:
                        print(f"[GeminiCollector] SDK JSON parse failed: {e3}")
                        return CollectorResult(items=[])
                else:
                    return CollectorResult(items=[])
            try:
                data = self._force_json(cleaned or out)
            except Exception as e:
                print(f"[GeminiCollector] JSON parse failed: {e}; raw head: {(cleaned or out)[:120]}")
                # 诊断增强：自动查找并打印错误报告摘要
                p = self._find_latest_error_report()
                if p:
                    self._print_error_report(p)
                else:
                    print("[GeminiCollector] no gemini-client-error report found; 请检查 GEMINI_API_KEY/账号配额/地区访问策略")
                # 回退：尝试 Python SDK 直接调用
                try:
                    model_name = self._extract_model(args)
                except Exception:
                    model_name = 'gemini-1.5-flash'
                sdk_out = self._sdk_generate(prompt, model_name, config.get('timeout', 120), env)
                if sdk_out:
                    try:
                        data = self._force_json(self._clean_output(sdk_out) or sdk_out)
                    except Exception as e3:
                        print(f"[GeminiCollector] SDK JSON parse failed: {e3}")
                        return CollectorResult(items=[])
                else:
                    return CollectorResult(items=[])
            items = []
            if isinstance(data, dict) and 'items' in data:
                data = data['items']
            if not isinstance(data, list):
                print(f"[GeminiCollector] parsed JSON is not a list: type={type(data)}")
                return CollectorResult(items=[])
            for it in data:
                if not isinstance(it, dict):
                    continue
                published = None
                ts = it.get('published_at')
                if ts:
                    try:
                        published = datetime.fromisoformat(ts.replace('Z','+00:00'))
                    except Exception:
                        published = None
                items.append(CollectorItem(
                    title=it.get('title',''),
                    url=it.get('url',''),
                    summary=it.get('summary',''),
                    published_at=published
                ))
            # 按配置裁剪返回数量
            try:
                mi = int(max_items)
                if mi > 0:
                    items = items[:mi]
            except Exception:
                pass
            return CollectorResult(items=items)
        except Exception as e:
            # 常见情况：命令不存在
            print(f"[GeminiCollector] exception: {e}")
            return CollectorResult(items=[])