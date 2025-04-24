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
        # emojiパッケージのインポート（必要な場合のみ実行）
        try:
            import emoji
            has_emoji_lib = True
        except ImportError:
            has_emoji_lib = False
            logger.warning("emojiパッケージがインストールされていません。通常の絵文字処理を使用します。")
        
        # 文字列に変換
        safe_name = str(filename)
        original_name = safe_name
        
        # 絵文字を処理する
        if has_emoji_lib:
            # emojiパッケージを使用して絵文字をテキスト表現に変換
            try:
                # 絵文字が含まれているかチェック
                if emoji.emoji_count(safe_name) > 0:
                    # 絵文字をテキスト表現に変換 (:smile: などに変換)
                    demojized = emoji.demojize(safe_name)
                    
                    # コロンをアンダースコアに変換し、ファイル名に適した形式にする
                    import re
                    safe_name = re.sub(r':(\w+):', r'_\1_', demojized)
                    logger.debug(f"絵文字を変換: '{original_name}' -> '{safe_name}'")
            except Exception as emoji_err:
                logger.warning(f"絵文字処理中にエラーが発生しました: {emoji_err}")
        
        # Windows禁止文字をアンダースコアに置換
        unsafe_chars = '<>:"/\\|?*\0'
        for char in unsafe_chars:
            safe_name = safe_name.replace(char, '_')
        
        # コントロール文字をアンダースコアに置換
        safe_name = ''.join(c if ord(c) >= 32 else '_' for c in safe_name)
        
        # 絵文字パッケージが使えない場合のバックアップ処理
        if not has_emoji_lib and emoji.emoji_count(original_name) > 0:
            # unicodedataを使用した代替絵文字処理
            import unicodedata
            import re
            
            # ASCII文字と一部の一般的な非ASCII文字を許可
            # 日本語は正規表現でマッチしないようにし、そのまま残す
            ascii_and_safe = re.compile(r'[a-zA-Z0-9\-_. \[\]()\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+')
            
            def replace_unsafe_char(c):
                # 日本語など一般的な文字はそのまま使用
                if ascii_and_safe.fullmatch(c):
                    return c
                # 絵文字やアクセント記号などは名前に変換
                try:
                    emoji_name = unicodedata.name(c).lower()
                    # 絵文字などは短い説明的な名前に変換
                    if 'emoji' in emoji_name:
                        return f'_{emoji_name.split()[-1][:8]}_'
                    # その他の特殊文字は単純なアンダースコアに
                    return '_'
                except Exception:
                    return '_'
            
            # 安全でないUnicode文字を処理
            safe_name = ''.join(replace_unsafe_char(c) for c in safe_name)
        
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
        
        # ダブルアンダースコアをシングルに置換して可読性を高める
        import re
        base_name = re.sub(r'_+', '_', base_name)
        
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
    # 出力先のパスを保持する変数を初期化
    # どのケースでもデフォルト値を持つようにする
    result_path = None
    
    # dest_dirを安全に取得
    dest_dir_str = ""
    if dest_dir is not None:
        try:
            dest_dir_str = str(dest_dir)
            # 万が一で空文字列ならデフォルト値を使用
            if not dest_dir_str:
                dest_dir_str = "./output"
        except Exception:
            dest_dir_str = "./output"
    else:
        dest_dir_str = "./output"
    
    # source_pathを安全に取得
    source_path_str = ""
    filename = "output_file.jpg"  # デフォルトファイル名
    if source_path is not None:
        try:
            source_path_str = str(source_path)
            filename = os.path.basename(source_path_str)
        except Exception:
            pass
    
    # source_dirを安全に取得
    source_dir_str = ""
    if source_dir is not None:
        try:
            source_dir_str = str(source_dir)
        except Exception:
            pass
    
    # メイン処理ブロック
    try:
        # Windowsの長いパス処理
        is_long_path = False
        if os.name == 'nt' and source_path_str.startswith('\\\\?\\'):
            is_long_path = True
            source_path_str = source_path_str[4:]
            source_dir_str = source_dir_str[4:] if source_dir_str.startswith('\\\\?\\') else source_dir_str
        
        # 相対パスの計算
        rel_path_str = ""
        if source_path_str and source_dir_str:
            if not source_path_str.startswith(source_dir_str):
                # 絶対パスで試行
                try:
                    abs_source = os.path.abspath(source_path_str)
                    abs_source_dir = os.path.abspath(source_dir_str)
                    
                    if abs_source.startswith(abs_source_dir):
                        rel_path_str = abs_source[len(abs_source_dir):].lstrip(os.sep)
                except Exception:
                    # 失敗した場合は相対パスなし
                    rel_path_str = ""
            else:
                # 直接相対パス計算
                rel_path_str = source_path_str[len(source_dir_str):].lstrip(os.sep)
        
        # 相対パスが存在する場合
        if rel_path_str:
            # パス部分の分割
            path_parts = rel_path_str.split(os.sep)
            
            # 出力先パスの構築
            result_path = Path(dest_dir_str)
            
            # ディレクトリ部分の処理
            if len(path_parts) > 1:
                for part in path_parts[:-1]:
                    try:
                        part_safe = sanitize_filename(part)
                        result_path = result_path / part_safe
                    except Exception:
                        # 失敗した場合はスキップして次のディレクトリ部分へ
                        continue
                
                # ディレクトリ作成
                try:
                    create_directory_with_permissions(result_path)
                except Exception as dir_err:
                    logger.debug(f"ディレクトリ作成エラーは無視します: {dir_err}")
            
            # ファイル名部分の処理
            if path_parts:
                try:
                    filename = sanitize_filename(path_parts[-1])
                    result_path = result_path / filename
                except Exception:
                    # ファイル名部分の処理に失敗した場合は元のファイル名を使用
                    result_path = result_path / filename
        else:
            # 相対パスが存在しない場合、ファイル名のみ使用
            try:
                safe_name = sanitize_filename(filename)
                result_path = Path(dest_dir_str) / safe_name
            except Exception:
                # 安全なファイル名の生成に失敗した場合はデフォルト名を使用
                result_path = Path(dest_dir_str) / "output_file.jpg"
        
        # Windowsの長いパス処理
        if os.name == 'nt' and is_long_path and result_path:
            try:
                dest_path_str = normalize_long_path(str(result_path))
                result_path = Path(dest_path_str)
            except Exception:
                # 長いパスの正規化に失敗した場合は元のパスを使用
                pass
    
    except Exception as e:
        # メイン処理でエラーが発生した場合
        logger.error(f"出力先パス生成エラー: {e}")
    
    # 最終的なチェックと結果返却
    if result_path is None:
        # メイン処理に失敗した場合の最終手段
        try:
            # 安全なファイル名を生成
            safe_name = sanitize_filename(filename)
            result_path = Path(dest_dir_str) / safe_name
        except Exception:
            # 本当に最後の手段として、デフォルトから生成
            result_path = Path("./output/output_file.jpg")
    
    # 結果返却
    return result_path


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


def resize_and_compress_image(source_path, dest_path, target_width, quality, format='jpeg', keep_exif=True, balance=5, dry_run=False):
    """
    画像をリサイズして圧縮します
    
    Args:
        source_path: 元の画像ファイルパス (Path)
        dest_path: 出力先ファイルパス (Path)
        target_width: 目標の幅 (ピクセル)
        quality: 圧縮品質 (1-100)
        format: 出力形式 ('jpeg', 'png', 'webp')
        keep_exif: EXIFメタデータを保持するか
        balance: 圧縮と品質のバランス (1-10, 1=最高圧縮率, 10=最高品質)
        dry_run: 実際の処理を行わずサイズ見積もりのみ実施
        
    Returns:
        tuple: (成功したか, 元のサイズを維持したか, 見積もりサイズ)
    """
    # 変数の初期化 - スコープ問題防止のため先に定義
    source_path_str = ""
    file_size_before = 0
    dest_path_str = ""
    keep_original = False
    estimated_size = None
    resized_img = None
    img = None
    save_img = None
    
    try:
        # パスの正規化にリトライ機構を使用
        def normalize_path_with_retry(path):
            return normalize_long_path(path, remove_prefix=True)
            
        source_path_str = retry_on_file_error(normalize_path_with_retry, source_path, max_retries=3, retry_delay=0.2)
        source_path = Path(source_path_str)

        # 実際に存在するか確認し、存在しない場合は再試行
        def check_file_exists(path):
            if not Path(path).exists():
                raise FileNotFoundError(f"ファイルが存在しません: {path}")
            return True
            
        retry_on_file_error(check_file_exists, source_path_str, max_retries=3, retry_delay=0.3)

        # ファイルサイズ取得にリトライ機構を使用
        def get_size(path):
            return os.path.getsize(path)
            
        file_size_before = retry_on_file_error(get_size, source_path_str, max_retries=3, retry_delay=0.2)

        # 出力先ディレクトリの安全な取得 (dest_path引数を使用)
        dest_dir = Path(dest_path).parent
        success, created_dir = create_directory_with_permissions(dest_dir)
        if not success:
            logger.error(f"出力先ディレクトリを作成できませんでした: {dest_dir}")
            return False, False, None

        # 出力先パスを文字列に変換
        dest_path_str = str(dest_path)
        
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
                    import uuid
                    import time
                    
                    # Windows環境での権限問題に対応するため、一意なファイル名を使用
                    temp_dir = tempfile.gettempdir()
                    temp_filename = f"resize_temp_{uuid.uuid4().hex}.jpg"
                    temp_path = os.path.join(temp_dir, temp_filename)
                    
                    # リトライ機構を使って一時ファイル操作
                    def save_temp_image():
                        # RGBモードに変換してから保存
                        img_to_save = resized_img.convert('RGB')
                        img_to_save.save(temp_path, format='JPEG', quality=quality)
                        return os.path.getsize(temp_path)
                    
                    try:
                        # リトライ機構で一時ファイルを保存してサイズを計測
                        estimated_size = retry_on_file_error(save_temp_image, max_retries=3, retry_delay=0.5)
                    except Exception as e:
                        logger.error(f"サイズ見積もりエラー: {e}")
                    finally:
                        # 一時ファイルの削除を試みる
                        try:
                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                        except Exception as e:
                            logger.debug(f"一時ファイルの削除に失敗: {e}")
                
                # ドライランの場合は実際の保存は行わない
                if not dry_run:
                    # ディレクトリが存在するか確認
                    if not os.path.exists(os.path.dirname(dest_path_str)):
                        os.makedirs(os.path.dirname(dest_path_str), exist_ok=True)
                    
                    # バランス値に基づいて最適化パラメータを調整
                    optimized_quality = adjust_quality_by_balance(quality, balance, format)
                    
                    # 出力形式に応じた処理
                    # 保存する画像を選択
                    if not keep_original:
                        save_img = resized_img
                    else:
                        save_img = img
                
                if format.lower() == 'jpeg':
                    # 拡張子を.jpgに更新
                    dest_path_str = update_extension(dest_path_str, '.jpg')
                    
                    # RGBモードに変換してからJPEGとして保存
                    try:
                        # まずRGBモードに変換
                        rgb_img = save_img.convert('RGB')
                        
                        # JPEGとして保存
                        if keep_exif and hasattr(img, 'info') and 'exif' in img.info:
                            rgb_img.save(dest_path_str, format='JPEG', 
                                        quality=optimized_quality,
                                        exif=img.info['exif'])
                        else:
                            rgb_img.save(dest_path_str, format='JPEG', 
                                        quality=optimized_quality)
                    except Exception as e:
                        logger.error(f"JPEG保存エラー: {e}")
                        return False, False, None
                    
                elif format.lower() == 'png':
                    # 拡張子を.pngに更新
                    dest_path_str = update_extension(dest_path_str, '.png')
                    
                    # PNGはqualityではなくcompressionレベルを使用
                    compression = int(9 - (optimized_quality / 10))  # 0-9の範囲に変換（9が最高圧縮）
                    compression = max(0, min(9, compression))  # 範囲を確保
                    
                    # PNGとして保存
                    save_img.save(dest_path_str, format='PNG', compress_level=compression)
                    
                elif format.lower() == 'webp':
                    # 拡張子を.webpに更新
                    dest_path_str = update_extension(dest_path_str, '.webp')
                    
                    # WebPはqualityをそのまま使用できる
                    save_img.save(dest_path_str, format='WEBP', quality=optimized_quality)
                
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


def update_extension(file_path, new_ext):
    """
    ファイルパスの拡張子を更新します
    
    Args:
        file_path: 元のファイルパス
        new_ext: 新しい拡張子 (ドット付き、例: '.jpg')
        
    Returns:
        str: 拡張子を更新したパス
    """
    path_obj = Path(file_path)
    stem = path_obj.stem
    parent = path_obj.parent
    
    # 新しいパスを作成
    new_path = parent / f"{stem}{new_ext}"
    
    return str(new_path)


def adjust_quality_by_balance(quality, balance, format):
    """
    圧縮と品質のバランスに基づいて品質パラメータを調整します
    
    Args:
        quality: 元の品質値 (1-100)
        balance: 圧縮と品質のバランス (1-10, 1=最高圧縮率, 10=最高品質)
        format: 出力形式 ('jpeg', 'png', 'webp')
        
    Returns:
        int: 調整後の品質値
    """
    # バランス値を正規化 (1-10 → 0.0-1.0)
    balance_factor = (balance - 1) / 9.0
    
    # 形式ごとの品質調整
    if format.lower() == 'jpeg':
        # JPEGの場合: バランス値が高いほど高品質
        # balance = 1 (最高圧縮) → quality * 0.7
        # balance = 10 (最高品質) → quality * 1.2 (上限100)
        adjustment = 0.7 + (balance_factor * 0.5)
        new_quality = int(quality * adjustment)
        
    elif format.lower() == 'png':
        # PNGの場合: 圧縮レベルは別関数で処理するのでそのまま返す
        new_quality = quality
        
    elif format.lower() == 'webp':
        # WebPの場合: バランスに基づく調整
        # balance = 1 (最高圧縮) → quality * 0.6
        # balance = 10 (最高品質) → quality * 1.1 (上限100)
        adjustment = 0.6 + (balance_factor * 0.5)
        new_quality = int(quality * adjustment)
    
    else:
        # 未対応の形式はそのまま返す
        new_quality = quality
    
    # 範囲の正規化 (1-100)
    return max(1, min(100, new_quality))


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
