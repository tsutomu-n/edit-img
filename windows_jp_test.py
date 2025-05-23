#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Windows11日本語環境でのファイル名処理テスト
"""

from pathlib import Path
import os
import sys

# リポジトリのルートディレクトリをパスに追加（直接インポートできるようにする）
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from resize_core import sanitize_filename, get_system_encoding
    import logging
    from loguru import logger
except ImportError as e:
    print(f"インポートエラー: {e}")
    sys.exit(1)

# テスト用の日本語ファイル名のリスト
test_filenames = [
    "テスト画像.jpg",
    "テスト_画像 (1).jpg",
    "テスト画像　空白あり.png",
    "🍣寿司🍣.png",
    "長いファイル名" + "あ" * 300 + ".jpg",
    "CON.png",  # Windowsの予約語
    "<>:\"/\\|?*テスト.jpg",  # 禁止文字入り
    "新しいフォルダー.jpg",  # 一般的なWindowsフォルダ名
    "IMG_20250523_123456.jpg",  # カメラで撮影した画像のような名前
    "スクリーンショット 2025-05-23 15.45.30.png",  # スクリーンショットのような名前
]

def run_test():
    """ファイル名変換テストを実行"""
    print("\n" + "=" * 50)
    print("Windows11日本語環境ファイル名変換テスト")
    print("=" * 50)
    
    print(f"\nシステムエンコーディング: {get_system_encoding()}")
    print(f"現在のOS: {os.name} ({sys.platform})\n")
    
    print("-" * 50)
    for name in test_filenames:
        try:
            safe_name = sanitize_filename(name)
            print(f"元の名前: {name}")
            print(f"変換後　: {safe_name}")
            print("-" * 50)
        except Exception as e:
            print(f"エラー ({name}): {e}")
            print("-" * 50)

if __name__ == "__main__":
    run_test()
