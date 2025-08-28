#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库迁移脚本：为 news_items 表添加翻译字段
"""
import sqlite3
import os

def migrate_db():
    db_path = os.path.join(os.path.dirname(__file__), 'data', 'dailynews.db')
    print(f"Connecting to database: {db_path}")
    
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    
    # 添加 title_translated 列
    try:
        cur.execute("ALTER TABLE news_items ADD COLUMN title_translated TEXT DEFAULT '';")
        print("✓ Added title_translated column")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("! title_translated column already exists")
        else:
            raise
    
    # 添加 summary_translated 列
    try:
        cur.execute("ALTER TABLE news_items ADD COLUMN summary_translated TEXT DEFAULT '';")
        print("✓ Added summary_translated column")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("! summary_translated column already exists")
        else:
            raise
    
    # 添加 translated_at 列
    try:
        cur.execute("ALTER TABLE news_items ADD COLUMN translated_at DATETIME;")
        print("✓ Added translated_at column")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("! translated_at column already exists")
        else:
            raise
    
    con.commit()
    con.close()
    print("✓ Database migration completed")

if __name__ == '__main__':
    migrate_db()