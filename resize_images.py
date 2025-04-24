#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
画像リサイズ・圧縮スクリプト 改良版

指定されたディレクトリから画像ファイル(.jpg, .png)を検索し、
指定された幅にリサイズして、圧縮率を指定してJPEG形式で保存します。
処理の進捗表示、サイズ情報、中断・再開機能を備えています。
"""

import os
import sys
import json
import argparse
import time
import signal
from pathlib import Path
from datetime import datetime
from tqdm import tqdm

# コア機能をインポート
import resize_core as core
from resize_core import logger

# シグナルハンドラー変数
interrupt_requested = False

# Ctrl+Cハンドラー
def signal_handler(sig, frame):
    """シグナルハンドラー関数"""
    global interrupt_requested
    logger.warning("\n中断シグナルを受信しました。安全に処理を停止します...")
    interrupt_requested = True

# シグナルハンドラーを登録
signal.signal(signal.SIGINT, signal_handler)

def calculate_reduction_percentage(source_size, dest_size):
    """ファイルサイズの削減率を計算する関数"""
    if source_size == 0:
        return 0
    
    return (source_size - dest_size) / source_size * 100

def parse_args():
    """コマンドライン引数を解析する関数"""
    parser = argparse.ArgumentParser(
        description="画像ファイルを指定された幅にリサイズし、JPEG形式で圧縮して保存します。"
    )
    parser.add_argument(
        "-s", "--source", required=True,
        help="入力元のディレクトリパス"
    )
    parser.add_argument(
        "-d", "--dest", required=True,
        help="出力先のディレクトリパス"
    )
    parser.add_argument(
        "-w", "--width", type=int, default=1280,
        help="リサイズ後の最大幅 (デフォルト: 1280)"
    )
    parser.add_argument(
        "-q", "--quality", type=int, default=85,
        help="JPEGの品質 (0-100、デフォルト: 85)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="ドライランモード（実際にファイルを保存せずシミュレートする）"
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="既存の出力ファイルがあればスキップする"
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="ログレベルを設定する (デフォルト: INFO)"
    )
    parser.add_argument(
        "--check-disk", action="store_true",
        help="処理前にディスク容量を確認する"
    )
    
    return parser.parse_args()

# ログ設定
logger.remove()  # デフォルト設定を削除
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO"
)
logger.add(
    "process_{time}.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {function}: {message}",
    rotation="1 day",
    level="DEBUG"
)


def get_directory_size(path):
    """ディレクトリの合計サイズを取得"""
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
    """削減率を計算（%）"""
    source_size = get_directory_size(source_dir)
    dest_size = get_directory_size(dest_dir)
    
    if source_size == 0:
        return 0
    
    return (source_size - dest_size) / source_size * 100

            new_dir = alt_dir / rel_path
            new_dir.mkdir(exist_ok=True)
            
            logger.info(f"代替ディレクトリを作成しました: {new_dir}")
            return True
        except Exception as alt_err:
            logger.error(f"代替ディレクトリ作成にも失敗しました: {alt_err}")
            return False
    except FileExistsError:
        # ファイルとして同名のものが存在する場合（正常な状態ではフォルダのはず）
        logger.error(f"同名のファイルが存在します。フォルダではありません: {directory_path}")
        
        # 代替名を試みる
        try:
            alt_dir_name = f"{directory_path}_folder"
            Path(alt_dir_name).mkdir(parents=True, exist_ok=True)
            logger.warning(f"代替名でディレクトリを作成しました: {alt_dir_name}")
            return True
        except Exception as rename_err:
            logger.error(f"代替名のディレクトリ作成にも失敗しました: {rename_err}")
            return False
    except Exception as e:
        logger.error(f"ディレクトリ作成中に不明なエラーが発生しました: {e}")
        return False

def save_progress(processed_files, remaining_files, output_file="progress.json"):
    """処理の進捗状況を保存"""
    data = {
        "timestamp": datetime.now().isoformat(),
        "processed": [str(f) for f in processed_files],
        "remaining": [str(f) for f in remaining_files]
    }
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"進捗を保存しました: {output_file}")

def load_progress(input_file="progress.json"):
    """保存された進捗を読み込み"""
    if not os.path.exists(input_file):
        return [], []
    
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"前回の進捗を読み込みました: {input_file}")
        
        # 文字列をPathオブジェクトに変換
        processed = [Path(p) for p in data.get("processed", [])]
        remaining = [Path(p) for p in data.get("remaining", [])]
        
        return processed, remaining
    except Exception as e:
        logger.error(f"進捗ファイル読み込みエラー: {e}")
        return [], []

def format_file_size(size_in_bytes):
    """ファイルサイズを読みやすい形式に変換"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_in_bytes < 1024.0 or unit == 'GB':
            break
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.2f} {unit}"

def generate_html_report(results, source_dir, dest_dir, output_file="report.html"):
    """処理結果のHTMLレポートを生成"""
    # 簡略化したHTMLテンプレート
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>画像処理レポート</title>
        <style>
            body {{ font-family: 'Meiryo', 'Hiragino Kaku Gothic Pro', sans-serif; margin: 20px; }}
            .summary {{ background-color: #f0f8ff; padding: 15px; border-radius: 5px; }}
            .success {{ color: green; }}
            .error {{ color: red; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
            th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }}
            th {{ background-color: #f2f2f2; }}
            .size-reduction {{ font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>画像処理レポート</h1>
        <div class="summary">
            <h2>処理概要</h2>
            <p>処理日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>処理ファイル数: {len(results)}</p>
            <p>成功: <span class="success">{sum(1 for r in results if r.get('status') == 'success')}</span></p>
            <p>エラー: <span class="error">{sum(1 for r in results if r.get('status') == 'error')}</span></p>
            <p>処理前の総サイズ: {format_file_size(get_directory_size(source_dir))}</p>
            <p>処理後の総サイズ: {format_file_size(get_directory_size(dest_dir))}</p>
            <p class="size-reduction">削減率: {calculate_reduction_rate(source_dir, dest_dir):.1f}%</p>
        </div>
        
        <h2>処理詳細</h2>
        <table>
            <tr>
                <th>No.</th>
                <th>ファイル名</th>
                <th>元サイズ</th>
                <th>処理後サイズ</th>
                <th>削減率</th>
                <th>状態</th>
            </tr>
    """
    
    # ファイル毎の行を生成
    for idx, item in enumerate(results, 1):
        status_class = "success" if item.get('status') == "success" else "error"
        status_text = "成功" if item.get('status') == "success" else "エラー"
        
        html_content += f"""
            <tr>
                <td>{idx}</td>
                <td>{item.get('name', '')}</td>
                <td>{item.get('original_size', '')}</td>
                <td>{item.get('new_size', '')}</td>
                <td>{item.get('reduction', '0')}%</td>
                <td class="{status_class}">{status_text}</td>
            </tr>
        """
    
    # HTMLを閉じる
    html_content += """
        </table>
    </body>
    </html>
    """
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    logger.info(f"レポートを生成しました: {output_file}")
    return output_file

def parse_arguments():
    """コマンドライン引数を解析する"""
    parser = argparse.ArgumentParser(description='画像ファイルをリサイズして圧縮します。')
    
    # 基本オプション
    parser.add_argument('--source', '-s', default=os.path.join(os.getcwd(), 'input'),
                        help='入力ディレクトリのパス (デフォルト: カレントディレクトリ/input)')
    parser.add_argument('--destination', '-d', default=os.path.join(os.getcwd(), 'output'),
                        help='出力先ディレクトリのパス (デフォルト: カレントディレクトリ/output)')
    parser.add_argument('--width', '-w', type=int, default=800,
                        help='リサイズする幅 (デフォルト: 800px)')
    parser.add_argument('--quality', '-q', type=int, default=87,
                        help='JPEG品質 (デフォルト: 87%)')
    
    # 実行モード
    parser.add_argument('--dry-run', action='store_true',
                        help='ドライラン実行 (実際にファイルを変更しない)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='詳細出力モード')
    
    # 新機能
    parser.add_argument('--resume', action='store_true',
                        help='前回の処理を再開する')
    parser.add_argument('--report', action='store_true',
                        help='処理結果のHTMLレポートを生成する')
    parser.add_argument('--check-disk', action='store_true',
                        help='ディスク容量を確認する')
    
    return parser.parse_args()


def find_image_files(source_dir):
    """指定されたディレクトリから全ての.jpgと.pngファイルを検索する"""
    logger.info(f"ディレクトリを検索: {source_dir}")
    
    source_path = Path(source_dir)
    image_files = []
    
    if not source_path.exists():
        logger.error(f"ディレクトリが存在しません: {source_dir}")
        return image_files
    
    try:
        # 再帰的に画像ファイルを検索
        for file_path in source_path.glob('**/*'):
            if file_path.is_file() and file_path.suffix.lower() in ('.jpg', '.jpeg', '.png'):
                image_files.append(file_path)
                logger.debug(f"画像ファイル検出: {file_path}")
    except Exception as e:
        logger.error(f"ディレクトリ '{source_dir}' の検索中にエラーが発生しました: {e}")
    
    logger.info(f"{len(image_files)}個の画像ファイルが見つかりました。")
    return image_files


def sanitize_filename(filename):
    """ファイル名をWindows互換に変換"""
    # Windows禁止文字を置換
    for char in '<>:"/\\|?*':
        filename = filename.replace(char, '_')
    
    # 空のファイル名の場合
    if not filename:
        return "untitled"
    
    return filename

def get_system_encoding():
    """システムに適したエンコーディングを返す"""
    if os.name == 'nt':  # Windows
        return 'cp932'
    return 'utf-8'

def get_destination_path(source_path, source_dir, dest_dir):
    """元のパスから新しい出力先パスを生成する（Windows対応強化版）"""
    # 長いパス対応のため、入力パスを正規化
    source_path = Path(normalize_long_path(source_path))
    source_dir = Path(normalize_long_path(source_dir))
    dest_dir = Path(normalize_long_path(dest_dir))
    
    # 相対パスを取得
    try:
        rel_path = source_path.relative_to(source_dir)
    except ValueError:
        # 相対パスを取得できない場合はファイル名のみを使用
        rel_path = Path(source_path.name)
    
    # 新しい出力先パスを生成
    dest_path = dest_dir / rel_path
    
    # ファイル名部分を安全化（Windows互換に）
    parent_dir = dest_path.parent
    safe_name = sanitize_filename(dest_path.name)
    
    # 拡張子を.jpgに変更（すでにjpgの場合も含めて統一）
    name_without_ext = Path(safe_name).stem
    dest_path = parent_dir / f"{name_without_ext}.jpg"
    
    # 長いパス対応のうえでパスを返す
    return Path(normalize_long_path(dest_path))


def resize_and_compress_image(source_path, dest_path, target_width, quality, dry_run=False):
    """画像をリサイズして圧縮する（メモリ効率改善版）、元ファイルより小さくなることを保証"""
    # 長いパス対応を含め、ファイルパスを適切に正規化
    source_path = Path(normalize_long_path(source_path))
    dest_path = Path(normalize_long_path(dest_path))
    
    # ファイルパスを文字列として扱い、日本語対応を強化
    source_path_str = str(source_path)
    dest_path_str = str(dest_path)
    
    try:
        # 元ファイルのサイズを取得
        original_file_size = source_path.stat().st_size
        is_png = source_path.suffix.lower() == '.png'
        
        # 画像を開く
        with Image.open(source_path) as img:
            # 元のサイズを取得
            original_width, original_height = img.size
            
            # ドライランの場合もサイズ予測を行う
            if dry_run:
                # 高さを計算
                if original_width != target_width:
                    target_height = int(original_height * (target_width / original_width))
                    resized_img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                else:
                    # リサイズ不要
                    resized_img = img
                    target_height = original_height
                
                # メモリ上で一時ファイルを作成してサイズを計算
                import io
                start_quality = quality - 10 if is_png else quality
                
                # ファイルサイズ予測用のバッファ
                buffer = io.BytesIO()
                rgb_img = resized_img.convert('RGB')
                
                # 最終サイズは適切な品質での予測値
                rgb_img.save(buffer, format='JPEG', quality=start_quality, optimize=True)
                estimated_size = len(buffer.getvalue())
                
                # 元の使用中メモリを解放
                buffer.close()
                if resized_img is not img:
                    del resized_img
                del rgb_img
                
                return (original_width, original_height), (target_width, target_height), estimated_size
            
            # 実際の処理（ドライランでない場合）
            # 出力先ディレクトリが存在しない場合は作成（権限対策強化版）
            if not create_directory_with_permissions(dest_path.parent):
                logger.error(f"出力先ディレクトリの作成に失敗しました: {dest_path.parent}")
                return None, None
            
            # PNGの場合はデフォルトより低い品質で開始
            start_quality = quality - 10 if is_png else quality
            
            # アスペクト比を維持しながらリサイズするかどうか判断
            if original_width != target_width:
                # 高さを計算
                target_height = int(original_height * (target_width / original_width))
                resized_img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
            else:
                # リサイズ不要
                logger.debug(f"リサイズ不要: すでに目標幅 {target_width}px")
                resized_img = img
            
            # メモリを効率的に使うための情報
            if original_width * original_height > 4000 * 3000:  # 1200万ピクセル以上
                logger.debug(f"大きな画像: {original_width}x{original_height} - メモリ効率モードで処理")
            
            # 複数の品質設定で試行し、元より小さくなるものを探す
            success = False
            temp_file = dest_path.with_suffix('.tmp')
            
            # キャンバスをRGBに変換（バインドエラー防止）
            rgb_img = resized_img.convert('RGB')
            
            # 4段階の品質設定で試行
            test_qualities = [start_quality, start_quality - 10, start_quality - 20, start_quality - 30]
            for test_quality in test_qualities:
                if test_quality < 30:  # 最低品質の制限
                    test_quality = 30
                
                try:
                    # 一時ファイルに保存
                    # 一時ファイル名を文字列として扱い、日本語ファイル名対応を確保
                    rgb_img.save(str(temp_file), 'JPEG', quality=test_quality, optimize=True, progressive=True)
                    
                    # サイズ比較
                    new_size = temp_file.stat().st_size
                    if new_size < original_file_size:
                        # 小さくなったのでリネームして成功
                        temp_file.replace(dest_path)
                        logger.debug(f"成功: 品質{test_quality}%でサイズ削減、{format_file_size(original_file_size)} → {format_file_size(new_size)}")
                        success = True
                        break
                    else:
                        logger.debug(f"試行: 品質{test_quality}%でもまだ大きい、{format_file_size(original_file_size)} < {format_file_size(new_size)}")
                except Exception as e:
                    logger.error(f"品質設定{test_quality}%での保存中にエラー: {e}")
            
            # すべての品質設定で小さくならなかった場合
            if not success:
                logger.warning(f"どの品質設定でも元より小さくならなかったため、元ファイルを使用: {source_path}")
                # 元のファイルをコピー
                import shutil
                try:
                    shutil.copy2(source_path_str, dest_path_str)
                except Exception as copy_err:
                    logger.error(f"ファイルコピー中にエラーが発生しました: {copy_err}")
                    return None, None
            
            # 一時ファイルが残っていれば削除
            if temp_file.exists():
                temp_file.unlink()
            
            # メモリ解放
            del rgb_img
            if 'resized_img' in locals() and resized_img is not img:
                del resized_img
            
            # 元のサイズと新しいサイズを返す
            if original_width != target_width:
                new_size = (target_width, target_height)
            else:
                new_size = (original_width, original_height)
                
            return (original_width, original_height), new_size
    
    except UnidentifiedImageError:
        logger.error(f"有効な画像ファイルではありません: {source_path}")
        return None, None
    except OSError as e:
        # analyze_os_error関数を使用して詳細なエラー情報を取得
        error_info = analyze_os_error(e)
        logger.error(f"ファイルアクセスエラー: '{source_path}' 処理中: {error_info}")
        
        # エラー種別による追加情報
        if os.name == 'nt' and hasattr(e, 'winerror'):
            if e.winerror == 32:  # ファイル使用中
                logger.info("このファイルは他のプログラムで開かれています。他のアプリケーションを閉じて再試行してください。")
            elif e.winerror == 5:  # アクセス拒否
                logger.info("管理者権限で実行するか、ファイルの読み取り専用属性を確認してください。")
            elif e.winerror == 206:  # パスが長すぎる
                logger.info("ファイルをルートに近いフォルダに移動するか、ファイル名を短くしてください。")
        return None, None
    except MemoryError:
        logger.error(f"メモリ不足エラー: '{source_path}' の処理中にメモリが不足しました")
        return None, None
    except Exception as e:
        logger.error(f"画像 '{source_path}' の処理中にエラーが発生しました: {e}")
        return None, None


def format_file_size(size_in_bytes):
    """ファイルサイズを読みやすい形式に変換"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_in_bytes < 1024.0 or unit == 'GB':
            break
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.2f} {unit}"


def main():
    """メイン関数"""
    # シグナルハンドラー登録
    signal.signal(signal.SIGINT, signal_handler)
    
    args = parse_arguments()
    
    # 詳細表示モード
    if args.verbose:
        logger.configure(handlers=[{"sink": sys.stderr, "level": "DEBUG"}])
    
    start_time = time.time()
    
    # ソースディレクトリのチェック
    if not os.path.isdir(args.source):
        logger.error(f"ソースディレクトリが見つかりません: {args.source}")
        return 1
    
    # ディスク容量チェック
    if args.check_disk and not args.dry_run:
        if not check_disk_space(args.destination):
            logger.error("出力先ディスクの空き容量が不足しています。処理を中止します。")
            return 1
    
    # 前回の処理を再開する場合
    processed_files = []
    if args.resume and not args.dry_run:
        processed_files, remaining_files = load_progress()
        if remaining_files:
            image_files = remaining_files
            logger.info(f"処理を再開します。既に{len(processed_files)}ファイル処理済み、残り{len(image_files)}ファイル")
        else:
            logger.warning("再開可能な進捗情報がありません。最初から処理します。")
            image_files = find_image_files(args.source)
    else:
        # 画像ファイルを検索
        image_files = find_image_files(args.source)
    
    if not image_files:
        logger.warning(f"ディレクトリ '{args.source}' には画像ファイルが見つかりませんでした。")
        return 0
    
    # ディレクトリサイズ情報を取得
    source_size = get_directory_size(args.source)
    
    logger.info(f"{'【ドライラン】' if args.dry_run else ''}処理を開始します。")
    logger.info(f"処理対象画像ファイル数: {len(image_files)}")
    logger.info(f"ソースディレクトリ: {args.source}")
    logger.info(f"出力先ディレクトリ: {args.destination}")
    logger.info(f"リサイズ幅: {args.width}px")
    logger.info(f"JPEG品質: {args.quality}%")
    print(f"処理前の総合サイズ: {format_file_size(source_size)}")
    print("-" * 80)
    
    processed_count = 0
    skipped_count = 0
    error_count = 0
    total_size_before = 0
    total_size_after = 0
    results = []
    
    # tqdmで進捗バーを表示
    with tqdm(total=len(image_files), desc="画像処理中", unit="files") as progress:
        for idx, source_path in enumerate(image_files, 1):
            # 中断リクエストがあれば処理を停止
            if interrupt_requested:
                logger.info("ユーザーによる中断リクエストにより処理を停止します")
                # 処理途中の場合は進捗を保存
                if not args.dry_run:
                    remaining = image_files[idx:]
                    save_progress(processed_files + image_files[:idx-1], remaining)
                break
                
            # 元のファイルサイズを取得
            try:
                file_size_before = source_path.stat().st_size
                total_size_before += file_size_before
            except Exception:
                file_size_before = 0
            
            # 出力先パスを取得
            dest_path = get_destination_path(source_path, args.source, args.destination)
            
            # 処理状況を表示
            person_name = source_path.parent.name
            qualification_name = source_path.stem
            
            # 詳細情報表示（進捗バーの下に表示）
            tqdm.write(f"[{idx}/{len(image_files)}] 処理中: {source_path}")
            tqdm.write(f"  - 人物名: {person_name}")
            tqdm.write(f"  - 資格名: {qualification_name}")
            tqdm.write(f"  - 元サイズ: {format_file_size(file_size_before)}")
            tqdm.write(f"  → 出力先: {dest_path}")
            
            # 画像をリサイズして圧縮
            resize_result = resize_and_compress_image(
                source_path, dest_path, args.width, args.quality, args.dry_run
            )
            
            # ドライランの場合は3つの値が返される（サイズ予測あり）
            if args.dry_run and len(resize_result) == 3:
                original_size, new_size, estimated_size = resize_result
                has_size_estimate = True
            else:
                original_size, new_size = resize_result
                has_size_estimate = False
            
            result_item = {
                "path": str(source_path),
                "name": f"{person_name}/{qualification_name}",
                "original_size": format_file_size(file_size_before)
            }
            
            if original_size and new_size:
                tqdm.write(f"  ✓ サイズ変更: {original_size[0]}x{original_size[1]} → {new_size[0]}x{new_size[1]}")
                processed_count += 1
                processed_files.append(source_path)
                result_item["status"] = "success"
                
                # ファイルサイズ情報の表示
                if args.dry_run and has_size_estimate:
                    # ドライランで予測サイズがある場合
                    estimated_size_str = format_file_size(estimated_size)
                    size_diff = file_size_before - estimated_size
                    reduction_percent = (size_diff / file_size_before * 100) if file_size_before > 0 else 0
                    tqdm.write(f"  ✓ 予測ファイルサイズ: {format_file_size(file_size_before)} → {estimated_size_str} ({reduction_percent:.1f}% 削減予定)")
                    total_size_after += estimated_size
                    
                    result_item["new_size"] = estimated_size_str
                    result_item["reduction"] = f"{reduction_percent:.1f}"
                
                # 実際の処理結果のファイルサイズを取得（ドライランでない場合）
                elif not args.dry_run and dest_path.exists():
                    try:
                        file_size_after = dest_path.stat().st_size
                        total_size_after += file_size_after
                        size_diff = file_size_before - file_size_after
                        reduction_percent = (size_diff / file_size_before * 100) if file_size_before > 0 else 0
                        tqdm.write(f"  ✓ ファイルサイズ: {format_file_size(file_size_before)} → {format_file_size(file_size_after)} ({reduction_percent:.1f}% 削減)")
                        
                        result_item["new_size"] = format_file_size(file_size_after)
                        result_item["reduction"] = f"{reduction_percent:.1f}"
                    except Exception:
                        result_item["new_size"] = "不明"
                        result_item["reduction"] = "0"
            elif original_size is None:
                tqdm.write(f"  ✗ エラー: 画像処理に失敗しました")
                error_count += 1
                result_item["status"] = "error"
            else:
                tqdm.write(f"  ✗ スキップしました")
                skipped_count += 1
                result_item["status"] = "skipped"
            
            results.append(result_item)
            tqdm.write("")  # 空行
            
            # 進捗バーを更新
            progress.update(1)
    
    elapsed_time = time.time() - start_time
    
    print("-" * 80)
    print(f"{'【ドライラン結果】' if args.dry_run else '【処理結果】'}")
    print(f"成功: {processed_count}ファイル")
    print(f"エラー: {error_count}ファイル")
    print(f"スキップ: {skipped_count}ファイル")
    
    if total_size_before > 0 and total_size_after > 0:
        size_diff = total_size_before - total_size_after
        reduction_percent = (size_diff / total_size_before * 100)
        print(f"合計サイズ削減: {format_file_size(total_size_before)} → {format_file_size(total_size_after)} ({reduction_percent:.1f}% 削減)")
    
    if not args.dry_run:
        # ディレクトリサイズ情報
        dest_size = get_directory_size(args.destination)
        print(f"処理後の総合サイズ: {format_file_size(dest_size)}")
        overall_reduction = calculate_reduction_rate(args.source, args.destination)
        print(f"全体の削減率: {overall_reduction:.1f}%")
    
    print(f"処理時間: {elapsed_time:.2f}秒")
    
    # HTMLレポート生成
    if args.report and not args.dry_run and processed_count > 0:
        report_file = generate_html_report(results, args.source, args.destination)
        print(f"レポートを生成しました: {report_file}")
    
    if args.dry_run:
        print("\n実際に処理を実行するには、--dry-runオプションを外して再実行してください。")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
