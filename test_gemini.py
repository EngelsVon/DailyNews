#!/usr/bin/env python3
import os
import subprocess
import json
from config import DevConfig

def test_gemini():
    cmd = os.environ.get('GEMINI_CLI_CMD', DevConfig.GEMINI_CLI_CMD)
    print(f"测试 Gemini CLI: {cmd}")
    
    # 基础测试
    try:
        proc = subprocess.run([cmd, "--help"], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
        print(f"Help 命令退出码: {proc.returncode}")
        if proc.returncode != 0:
            print(f"stderr: {proc.stderr[:200]}")
            print("可能Gemini CLI未正确安装或PATH配置错误")
            return False
    except Exception as e:
        print(f"执行失败: {e}")
        return False
    
    # 实际提示测试
    prompt = "请整理与技术新闻相关的最新动态，给出标题、链接（若有）和一句话摘要，输出JSON列表，字段为title,url,summary,published_at(ISO8601)"
    print(f"\n测试提示词: {prompt[:50]}...")
    
    env = os.environ.copy()
    if DevConfig.GEMINI_API_KEY and 'GEMINI_API_KEY' not in env:
        env['GEMINI_API_KEY'] = DevConfig.GEMINI_API_KEY
    
    try:
        proc = subprocess.run([cmd, "--prompt", prompt], capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, timeout=120)
        print(f"提示命令退出码: {proc.returncode}")
        print(f"stdout长度: {len(proc.stdout)}")
        print(f"stderr长度: {len(proc.stderr)}")
        
        if proc.stdout:
            print(f"前100字符: {repr(proc.stdout[:100])}")
        if proc.stderr:
            print(f"错误信息: {proc.stderr[:200]}")
            
        if proc.stdout.strip():
            try:
                data = json.loads(proc.stdout.strip())
                print(f"JSON解析成功，条目数: {len(data) if isinstance(data, list) else 'not list'}")
                if isinstance(data, list) and data:
                    print(f"第一条示例: {data[0]}")
                return True
            except json.JSONDecodeError as e:
                print(f"JSON解析失败: {e}")
                print("可能需要优化提示词要求更严格的输出格式")
                return False
        else:
            print("无输出内容")
            return False
    except subprocess.TimeoutExpired:
        print("命令超时")
        return False
    except Exception as e:
        print(f"执行异常: {e}")
        return False

if __name__ == "__main__":
    success = test_gemini()
    print(f"\n测试结果: {'通过' if success else '失败'}")