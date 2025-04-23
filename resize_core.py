#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
画像リサイズ・圧縮ツールのコア機能モジュール

コマンドラインインターフェース(CLI)とグラフィカルユーザーインターフェース(GUI)の
両方から利用可能な共通機能を提供します。
"""

import os
import sys
import json
import shutil
import time
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from loguru import logger

# Windows固有のエラーコードと対応する日本語メッセージ
WINDOWS_ERROR_MESSAGES = {
    2: "指定されたファイルが見つかりません",
    3: "指定されたパスが見つかりません",
    5: "アクセスが拒否されました。管理者権限で実行するか、ファイルの権限を確認してください",
    32: "ファイルが他のプロセスで使用中です。開いているアプリケーションを閉じてください",
    80: "ファイル名が正しくありません。使用できない文字が含まれています",
    123: "ファイル名、ディレクトリ名、またはボリュームラベルの構文が正しくありません",
    145: "ディレクトリが空ではありません",
    183: "この名前のファイルまたはディレクトリが既に存在しています",
    206: "ファイルパスが長すぎます。260文字以内に収まるパスを使用してください",
    1920: "メディアが書き込み保護されています",
}

# ログ設定
def setup_logging(console_level="INFO", file_level="DEBUG", log_file="process_{time}.log"):
    """ロギングの設定を行います"""
    logger.remove()  # デフォルト設定を削除
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{function}</cyan>: <white>{message}</white>",
        colorize=True,
        level=console_level
    )
    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {function}: {message}",
        rotation="1 day",
        level=file_level
    )


def get_directory_size(path):
    """ディレクトリの合計サイズを取得します"""
    total_size = 0
    dir_path = Path(path)
    
    if not dir_path.exists():
        return 0
    
    for file_path in dir_path.glob('**/*'):
        if file_path.is_file():
            try:
                total_size += file_path.stat().st_size
            except OSError:
                # ファイルアクセスエラーの場合はスキップ
                pass
    
    return total_size


def calculate_reduction_rate(source_dir, dest_dir):
    """削減率を計算します（%）"""
    source_size = get_directory_size(source_dir)
    dest_size = get_directory_size(dest_dir)
    
    if source_size == 0:
        return 0
    
    return (source_size - dest_size) / source_size * 100


def check_disk_space(path, required_space_mb=500):
    """ディスクの空き容量を確認します"""
    try:
        total, used, free = shutil.disk_usage(path)
        free_mb = free / (1024 * 1024)  # MB単位
        
        if free_mb < required_space_mb:
            logger.warning(f"ディスク空き容量が少なくなっています: {free_mb:.2f}MB")
            return False
        return True
    except Exception as e:
        logger.error(f"ディスク容量確認エラー: {e}")
        return False


def get_windows_error_message(error_code):
    """
    Windowsエラーコードから日本語メッセージを取得します
    
    Args:
        error_code: Windowsエラーコード
        
    Returns:
        str: 日本語エラーメッセージ
    """
    return WINDOWS_ERROR_MESSAGES.get(error_code, "不明なエラー")


def is_long_path_enabled():
    """
    Windows環境で長いパスサポートが有効か確認します
    
    Returns:
        bool: 長いパスサポートが有効かどうか
    """
    if os.name != 'nt':
        return True  # Windows以外では常にTrueとする
    
    try:
        # 長いパスが有効かテスト
        test_long_path = 'a' * 260
        Path(test_long_path)
        return True
    except OSError:
        # ファイル名の制限に達した場合
        return False
    except Exception:
        # その他のエラー
        return False


def normalize_long_path(path):
    """
    長いパスをWindows対応形式に正規化します
    
    Args:
        path: 正規化するファイルパス（文字列またはPathオブジェクト）
        
    Returns:
        str: 正規化されたパス（Windowsでは必要に応じて\\\\?\\形式）
    """
    # パスを文字列に変換
    path_str = str(path)
    
    # Windowsでなければそのまま返す
    if os.name != 'nt':
        return path_str
    
    # 既にLong Path形式なら処理不要
    if path_str.startswith('\\\\?\\'):
        return path_str
    
    # 絶対パスに変換してLong Path形式に
    return '\\\\?\\' + os.path.abspath(path_str)


def analyze_os_error(e):
    """
    OSエラーを詳細に分析し、具体的な情報を返します
    
    Args:
        e: OSError例外オブジェクト
        
    Returns:
        str: 詳細なエラー情報
    """
    error_msg = str(e)
    
    # WindowsのOSエラーで、winerrnoがある場合
    if os.name == 'nt' and hasattr(e, 'winerror'):
        win_code = e.winerror
        win_msg = get_windows_error_message(win_code)
        
        if win_code == 206:  # Path too long
            return f"{error_msg}。パスが長すぎます。長いパス有効化の設定を確認するか、短いパスを使用してください。"
        elif win_code == 80:  # Invalid filename
            return f"{error_msg}。ファイル名に使用できない文字が含まれています。"
        elif win_code == 5:   # Access denied
            return f"{error_msg}。アクセスが拒否されました。管理者権限で実行するか、ファイルの権限を確認してください。"
        else:
            return f"{error_msg}。{win_msg}"
    
    # 一般的なファイル/ディレクトリエラー
    if "No such file or directory" in error_msg:
        return f"{error_msg}。指定されたパスが存在しません。"
    elif "Permission denied" in error_msg:
        return f"{error_msg}。ファイルへのアクセス権限がありません。"
    elif "File exists" in error_msg:
        return f"{error_msg}。ファイルが既に存在します。"
    else:
        return error_msg


def create_directory_with_permissions(directory_path):
    """
    ディレクトリを安全に作成し、権限エラーの場合は回避策を試みます
    
    Args:
        directory_path: 作成するディレクトリパス（Path オブジェクトまたは文字列）
    
    Returns:
        tuple: (成功したかどうか, 作成されたディレクトリパス)
    """
    try:
        # Pathオブジェクトに変換
        directory = Path(directory_path)
        
        # 既に存在する場合は成功とみなす
        if directory.exists():
            return True, directory
        
        # Windows環境で長いパス対応
        if os.name == 'nt':
            directory_str = normalize_long_path(directory)
            os.makedirs(directory_str, exist_ok=True)
        else:
            # 通常の処理
            directory.mkdir(parents=True, exist_ok=True)
            
        logger.debug(f"ディレクトリを作成しました: {directory}")
        return True, directory
        
    except PermissionError:
        # 権限エラーの場合、ユーザーホームディレクトリに作成を試みる
        logger.warning(f"権限エラー: {directory_path} を作成できません")
        try:
            home_dir = Path.home() / "resize_images_output"
            home_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"代替ディレクトリを作成しました: {home_dir}")
            return True, home_dir
        except Exception as e:
            logger.error(f"代替ディレクトリの作成にも失敗しました: {e}")
            return False, None
            
    except OSError as e:
        # その他のOSエラー
        error_msg = analyze_os_error(e)
        logger.error(f"ディレクトリ作成エラー: {error_msg}")
        return False, None
        
    except Exception as e:
        # その他の予期せぬエラー
        logger.error(f"ディレクトリ作成中の予期せぬエラー: {e}")
        return False, None


def sanitize_filename(filename):
    """
    ファイル名をWindows互換に変換します
    
    Args:
        filename: 元のファイル名
        
    Returns:
        str: 安全なファイル名
    """
    # Windows禁止文字をアンダースコアに置換
    unsafe_chars = '<>:"/\\|?*'
    safe_name = str(filename)
    
    for char in unsafe_chars:
        safe_name = safe_name.replace(char, '_')
    
    # 予約語対策（先頭や末尾のスペースとピリオドを削除）
    safe_name = safe_name.strip(" .")
    
    # 空の場合はデフォルト名
    if not safe_name:
        safe_name = "unnamed_file"
        
    return safe_name


def get_system_encoding():
    """システムに適したエンコーディングを返します"""
    return 'cp932' if os.name == 'nt' else 'utf-8'


def get_destination_path(source_path, source_dir, dest_dir):
    """
    元のパスから新しい出力先パスを生成します（Windows対応強化版）
    
    Args:
        source_path: 元のファイルパス (Path)
        source_dir: 入力ディレクトリ (Path)
        dest_dir: 出力ディレクトリ (Path)
        
    Returns:
        Path: 出力先のパス
    """
    try:
        # 相対パスを計算
        rel_path = source_path.relative_to(source_dir)
        
        # 出力先パスを構築
        dest_path = dest_dir
        
        # Windows対応のためにパスの各部分を個別に処理
        for part in rel_path.parts[:-1]:  # ディレクトリ部分
            safe_part = sanitize_filename(part)
            dest_path = dest_path / safe_part
            
        # ファイル名部分の処理
        filename = sanitize_filename(rel_path.name)
        dest_path = dest_path / filename
        
        # Windows環境では長いパスの処理
        if os.name == 'nt':
            # 出力先ディレクトリを作成
            parent_dir = dest_path.parent
            success, _ = create_directory_with_permissions(parent_dir)
            if not success:
                logger.error(f"出力先ディレクトリを作成できませんでした: {parent_dir}")
                
            # 長いパスの処理
            dest_path_str = normalize_long_path(dest_path)
            return Path(dest_path_str)
        
        # 出力先ディレクトリを作成
        parent_dir = dest_path.parent
        success, _ = create_directory_with_permissions(parent_dir)
        if not success:
            logger.error(f"出力先ディレクトリを作成できませんでした: {parent_dir}")
        
        return dest_path
        
    except Exception as e:
        logger.error(f"出力先パス生成エラー: {e}")
        # エラー時は出力ディレクトリにファイル名だけを付ける
        safe_name = sanitize_filename(source_path.name)
        return dest_dir / safe_name


def find_image_files(source_dir):
    """
    指定されたディレクトリから全ての.jpgと.pngファイルを検索します
    
    Args:
        source_dir: 検索対象のディレクトリパス
        
    Returns:
        list: 画像ファイルパスのリスト（Path）
    """
    image_files = []
    source_path = Path(source_dir)
    
    if not source_path.exists():
        logger.error(f"指定されたディレクトリが存在しません: {source_dir}")
        return []
    
    try:
        # .jpg, .jpeg, .pngファイルを検索
        for pattern in ["**/*.jpg", "**/*.jpeg", "**/*.png"]:
            # normalize_long_pathを使ってWindowsの長いパス対応
            norm_path = normalize_long_path(source_path) if os.name == 'nt' else source_path
            image_files.extend(list(Path(norm_path).glob(pattern)))
        
        logger.info(f"{len(image_files)}個の画像ファイルが見つかりました")
        return sorted(image_files)
    except Exception as e:
        logger.error(f"画像ファイル検索エラー: {e}")
        return []


def resize_and_compress_image(source_path, dest_path, target_width, quality, dry_run=False):
    """
    画像をリサイズして圧縮します
    
    Args:
        source_path: 元の画像ファイルパス (Path)
        dest_path: 出力先ファイルパス (Path)
        target_width: 目標の幅 (ピクセル)
        quality: JPEG圧縮品質 (1-100)
        dry_run: 実際の処理を行わずサイズ見積もりのみ実施
        
    Returns:
        tuple: (成功したか, 元のサイズを維持したか, 見積もりサイズ)
    """
    try:
        # ファイルパスを文字列に変換
        source_path_str = str(source_path)
        dest_path_str = str(dest_path)
        
        # Windows環境では長いパス対応
        if os.name == 'nt':
            source_path_str = normalize_long_path(source_path)
            dest_path_str = normalize_long_path(dest_path)
            
        # 出力先ディレクトリを作成
        dest_dir = Path(dest_path).parent
        success, created_dir = create_directory_with_permissions(dest_dir)
        if not success:
            return False, False, None

        # 画像を開いて処理
        try:
            with Image.open(source_path_str) as img:
                # 元の画像サイズ
                original_width, original_height = img.size
                
                # 既に十分小さい場合はリサイズ不要
                keep_original = original_width <= target_width
                
                # 縦横比を維持したリサイズ計算
                if not keep_original:
                    ratio = original_height / original_width
                    new_height = int(target_width * ratio)
                    new_size = (target_width, new_height)
                    resized_img = img.resize(new_size, Image.LANCZOS)
                else:
                    resized_img = img
                
                # 見積もりサイズ計算（テンポラリファイルに保存して測定）
                estimated_size = None
                
                # ドライランまたはサイズ計算が必要な場合
                if dry_run or not keep_original:
                    # テンポラリパスを用意
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=True) as tmp:
                        # 一時ファイルに保存してサイズを計測
                        try:
                            resized_img.save(tmp.name, format='JPEG', quality=quality)
                            estimated_size = os.path.getsize(tmp.name)
                        except Exception as e:
                            logger.error(f"サイズ見積もりエラー: {e}")
                
                # ドライランの場合は実際の保存は行わない
                if not dry_run:
                    # ディレクトリが存在するか確認
                    if not os.path.exists(os.path.dirname(dest_path_str)):
                        os.makedirs(os.path.dirname(dest_path_str), exist_ok=True)
                    
                    # JPEG形式で保存
                    if not keep_original:
                        resized_img.save(dest_path_str, format='JPEG', quality=quality)
                    else:
                        # 元のサイズを維持する場合はコピーのみ
                        if source_path.suffix.lower() in ['.jpg', '.jpeg']:
                            img.save(dest_path_str, format='JPEG', quality=quality)
                        else:
                            # PNG等はJPEGに変換
                            img.convert('RGB').save(dest_path_str, format='JPEG', quality=quality)
                
                return True, keep_original, estimated_size
                
        except UnidentifiedImageError:
            logger.error(f"未対応または破損した画像形式: {source_path}")
            return False, False, None
            
        except Exception as e:
            logger.error(f"画像処理エラー: {e}")
            return False, False, None
            
    except OSError as e:
        # ファイルアクセスエラー
        error_msg = analyze_os_error(e)
        logger.error(f"ファイルアクセスエラー: {error_msg}")
        return False, False, None
        
    except Exception as e:
        # その他の予期せぬエラー
        logger.error(f"予期せぬエラー: {e}")
        return False, False, None


def format_file_size(size_in_bytes):
    """
    ファイルサイズを読みやすい形式に変換します
    
    Args:
        size_in_bytes: バイト単位のサイズ
        
    Returns:
        str: 人間が読みやすい形式（例: 1.2 MB）
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_in_bytes < 1024.0 or unit == 'GB':
            break
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.1f} {unit}"


def save_progress(processed_files, remaining_files, output_file="progress.json"):
    """
    処理の進捗状況を保存します
    
    Args:
        processed_files: 処理済みファイルのリスト
        remaining_files: 残りのファイルのリスト
        output_file: 出力ファイル名
    """
    data = {
        "processed": [str(p) for p in processed_files],
        "remaining": [str(r) for r in remaining_files],
        "timestamp": time.time()
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_progress(input_file="progress.json"):
    """
    保存された進捗を読み込みます
    
    Args:
        input_file: 入力ファイル名
        
    Returns:
        tuple: (処理済みファイルリスト, 残りファイルリスト)
    """
    try:
        if not os.path.exists(input_file):
            return [], []
            
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        processed = [Path(p) for p in data.get("processed", [])]
        remaining = [Path(r) for r in data.get("remaining", [])]
        
        return processed, remaining
    except Exception as e:
        logger.error(f"進捗データ読み込みエラー: {e}")
        return [], []

# 初期ロギング設定
setup_logging()
