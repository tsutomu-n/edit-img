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


def retry_on_file_error(func, *args, max_retries=3, retry_delay=0.5, **kwargs):
    """
    ファイル操作に関連する関数を実行し、エラー時にリトライするラッパー関数
    
    Args:
        func: 実行する関数
        *args: 関数の引数
        max_retries: 最大リトライ回数
        retry_delay: リトライ間の待機時間（秒）
        **kwargs: 関数のキーワード引数
        
    Returns:
        関数の結果
        
    Raises:
        最大リトライ回数後も失敗した場合は最後の例外を再送出
    """
    retries = 0
    last_exception = None
    
    while retries < max_retries:
        try:
            return func(*args, **kwargs)
        except (PermissionError, OSError) as e:
            last_exception = e
            retries += 1
            logger.debug(f"ファイル操作エラー: {e} - リトライ {retries}/{max_retries}")
            
            # Windows環境ではファイルロックが一時的な場合があるため、待機して再試行
            time.sleep(retry_delay)
    
    # 最大リトライ回数到達後も失敗した場合
    if last_exception:
        logger.error(f"最大リトライ回数到達: {last_exception}")
        raise last_exception
    return None


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


def normalize_long_path(path, add_prefix=True, remove_prefix=False, normalize=True):
    """
    Windowsの長いパスを処理するためのパス正規化処理。
    Windowsの260文字制限を回避し、絵文字などのUnicode文字を含むパスも処理します。
    
    Args:
        path: パスオブジェクトまたはパス文字列
        add_prefix: \\?\\u30d7レフィックスを追加するか（Windowsのみ有効）
        remove_prefix: 既存の\\?\\u30d7レフィックスを削除するか（Windowsのみ有効）
        normalize: パスを正規化するか（二重スラッシュなどの正規化）
        
    Returns:
        str: 正規化されたパス（Windowsでは必要に応じて\\?\\u5f62式）
    """
    try:
        # パスを文字列に変換
        path_str = str(path)
        original_path = path_str  # ログ記録用に元のパスを保存
        
        # Windowsでなければそのまま返す
        if os.name != 'nt':
            return path_str
        
        # UNCパス（ネットワークパス）の处理
        is_unc = path_str.startswith('\\\\')
        
        # 既存のプレフィックスを確認
        has_prefix = path_str.startswith('\\\\?\\') 
        has_unc_prefix = path_str.startswith('\\\\?\\UNC\\')
        
        # プレフィックスを削除する必要がある場合
        if remove_prefix:
            if has_unc_prefix:
                # UNCパスのプレフィックスを削除
                path_str = '\\\\' + path_str[8:]  # '\\?\UNC\\'(8文字)を削除して'\\\\'(2文字)を追加
                logger.debug(f"UNCパスのプレフィックスを削除: '{original_path}' -> '{path_str}'")
            elif has_prefix:
                # 通常のプレフィックスを削除
                path_str = path_str[4:]  # '\\?\\'(4文字)を削除
                logger.debug(f"プレフィックスを削除: '{original_path}' -> '{path_str}'")
        
        # パスを正規化する必要がある場合
        if normalize:
            # プレフィックスの有無に応じて正規化
            if has_prefix and not remove_prefix:
                # 一時的にプレフィックスを削除して正規化
                temp_path = path_str[4:] if has_prefix else path_str
                normalized_path = os.path.abspath(temp_path)
                # プレフィックスを復元
                path_str = '\\\\?\\' + normalized_path
                logger.debug(f"プレフィックス付きパスを正規化: '{original_path}' -> '{path_str}'")
            else:
                # 正規化のみ実行
                path_str = os.path.abspath(path_str)
                logger.debug(f"パスを正規化: '{original_path}' -> '{path_str}'")
        
        # プレフィックスを追加する必要がある場合
        if add_prefix and not has_prefix and not path_str.startswith('\\\\?\\'):
            # パスが無効な場合は正規化
            norm_path = path_str if normalize else os.path.abspath(path_str)
            
            if is_unc:
                # UNCパスの場合は特別な処理が必要
                # \\で始まるパスは\\を削除してUNCプレフィックスを追加
                path_str = '\\\\?\\UNC\\' + norm_path[2:]
                logger.debug(f"UNCパスにプレフィックスを追加: '{original_path}' -> '{path_str}'")
            else:
                # 通常のパスにプレフィックスを追加
                path_str = '\\\\?\\' + norm_path
                logger.debug(f"パスにプレフィックスを追加: '{original_path}' -> '{path_str}'")
        
        # パス长のチェック
        if len(path_str) > 260 and not (has_prefix or path_str.startswith('\\\\?\\')):
            logger.warning(f"パスが260文字を超えていますが、\\?\\プレフィックスが付いていません: {path_str}")
            # プレフィックスが付いていない場合は自動的に追加
            if is_unc:
                path_str = '\\\\?\\UNC\\' + path_str[2:]
            else:
                path_str = '\\\\?\\' + path_str
        
        return path_str
        
    except Exception as e:
        # パスの正規化中に問題が発生した場合はログに記録し、元のパスを返す
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"パスの正規化中にエラーが発生しました: {e}")
        logger.debug(f"トレースバック情報: \n{error_trace}")
        logger.warning(f"元のパスを返します: {str(path)}")
        return str(path)  # 元のパスを返す


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
    ファイル名をWindows互換に変換します。絵文字などの特殊文字も処理します。
    
    Args:
        filename: 元のファイル名
        
    Returns:
        str: 安全なファイル名
    """
    try:
        # 文字列に変換
        safe_name = str(filename)
        
        # Windows禁止文字をアンダースコアに置換
        unsafe_chars = '<>:"/\\|?*\0'
        for char in unsafe_chars:
            safe_name = safe_name.replace(char, '_')
        
        # コントロール文字をアンダースコアに置換
        safe_name = ''.join(c if ord(c) >= 32 else '_' for c in safe_name)
        
        # Windowsの予約語をチェック
        reserved_names = ["CON", "PRN", "AUX", "NUL",
                         "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
                         "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"]
        
        # ファイル名と拡張子を分ける
        name_parts = os.path.splitext(safe_name)
        base_name = name_parts[0]
        extension = name_parts[1] if len(name_parts) > 1 else ""
        
        # 予約語対策
        if base_name.upper() in reserved_names:
            base_name = base_name + "_file"
        
        # 先頭や末尾のスペースとピリオドを削除
        base_name = base_name.strip(" .")
        
        # 空の場合はデフォルト名
        if not base_name:
            base_name = "unnamed_file"
        
        # ファイル名が長すぎる場合は切り詰め
        if len(base_name) > 200:  # Windowsの制限より少なく
            base_name = base_name[:197] + "..."
            
        # 拡張子も簡素化
        if len(extension) > 10:  # 正常な拡張子はそれより短い
            extension = extension[:10]
            
        # ファイル名を元に戻す
        safe_name = base_name + extension
        
        logger.debug(f"ファイル名を正規化: '{filename}' -> '{safe_name}'")
        return safe_name
        
    except Exception as e:
        # 例外発生時はログに記録し、デフォルト名を使用
        logger.error(f"ファイル名の正規化中にエラーが発生しました: {e}")
        import uuid
        return f"unnamed_file_{uuid.uuid4().hex[:8]}"


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
        # Windows対応：\\?\ プレフィックスを一時的に削除して処理
        source_path_str = str(source_path)
        source_dir_str = str(source_dir)
        
        is_long_path = False
        if os.name == 'nt' and source_path_str.startswith('\\\\?\\'):
            is_long_path = True
            source_path_str = source_path_str[4:]  # \\?\ を削除
            source_dir_str = source_dir_str[4:] if source_dir_str.startswith('\\\\?\\') else source_dir_str
        
        # 文字列ベースで相対パスを計算（Windows長パス問題を回避）
        if not source_path_str.startswith(source_dir_str):
            # 正規化されていない可能性があるので絶対パスで試行
            abs_source = os.path.abspath(source_path_str)
            abs_source_dir = os.path.abspath(source_dir_str)
            
            if not abs_source.startswith(abs_source_dir):
                raise ValueError(f"'{source_path_str}' is not in the subpath of '{source_dir_str}'")
                
            # 相対パスを手動で計算
            rel_path_str = abs_source[len(abs_source_dir):].lstrip(os.sep)
        else:
            # 直接相対パス計算
            rel_path_str = source_path_str[len(source_dir_str):].lstrip(os.sep)
        
        # 出力先パスを構築
        dest_path = dest_dir
        
        # パスを分割して処理
        path_parts = rel_path_str.split(os.sep)
        
        # ディレクトリ部分を処理
        for part in path_parts[:-1]:  # ファイル名を除く
            safe_part = sanitize_filename(part)
            dest_path = dest_path / safe_part
            
        # ファイル名部分の処理（最後の部分）
        if path_parts:
            filename = sanitize_filename(path_parts[-1])
            dest_path = dest_path / filename
        
        # Windows環境では長いパスの処理
        if os.name == 'nt':
            # 出力先ディレクトリを作成
            parent_dir = dest_path.parent
            success, _ = create_directory_with_permissions(parent_dir)
            if not success:
                logger.error(f"出力先ディレクトリを作成できませんでした: {parent_dir}")
                
            # 長いパスの処理
            if is_long_path:
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
