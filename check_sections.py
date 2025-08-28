#!/usr/bin/env python3
import os, json, sys, subprocess
sys.path.insert(0, '.')
from app import app, db, Section
from collectors.gemini_collector import GeminiCollector

with app.app_context():
    print('板块列表:')
    for s in Section.query.all():
        print(f'{s.id}\t{s.name}\t{s.fetch_method}\t{s.enabled}\t{s.update_interval_minutes}min')
        print(f'  config_json: {s.config_json}')
        if s.name == 'EPIC免费游戏' and s.fetch_method == 'gemini':
            try:
                print(f'\n测试 "{s.name}" 板块的 Gemini 收集器...')
                cfg = json.loads(s.config_json or '{}')
                collector = GeminiCollector()
                result = collector.fetch(s.name, cfg)
                print(f'收集结果: {len(result.items)} 条')
                for i, item in enumerate(result.items[:3]):
                    print(f'  {i+1}. {item.title} - {item.url}')
            except Exception as e:
                print(f'收集器测试失败: {e}')