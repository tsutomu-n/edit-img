#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
画像リサイズ・圧縮ツール GUI版

TkEasyGUIを使ったグラフィカルインターフェースで
画像のリサイズと圧縮を行います。
"""

import os
import sys
import time
import signal
import threading
import traceback
import queue
from datetime import datetime
from pathlib import Path

# TkEasyGUI
import tkeasygui as eg
from tkeasygui import widgets
from tkeasygui import dialogs

# カスタム画像処理モジュール
import resize_core as core
from resize_core import logger

# デバッグモード設定
DEBUG_MODE = True  # Trueにすると詳細なエラー情報を表示

# グローバル変数
cancel_process = False  # 処理キャンセルフラグ
update_queue = queue.Queue()  # スレッド間通信用キュー

def process_images_thread(values, window):
    """
    別スレッドで実行する画像処理関数
    """
    global cancel_process, update_queue
    cancel_process = False
    
    try:
        # パスの正規化処理
        source_dir = Path(core.normalize_long_path(values['source'], add_prefix=False, remove_prefix=True))
        dest_dir = Path(core.normalize_long_path(values['dest'], add_prefix=False, remove_prefix=True))
        width = int(values['width'])
        quality = int(values['quality'])
        
        # 新しいパラメータの取得
        # 出力形式の取得
        if values.get('format_jpeg', True):
            format_type = 'jpeg'
        elif values.get('format_png', False):
            format_type = 'png'
        elif values.get('format_webp', False):
            format_type = 'webp'
        else:
            format_type = 'jpeg'  # デフォルト
        
        # 圧縮バランスの取得
        balance = int(values.get('balance', 5))
        
        # EXIFメタデータオプション
        keep_exif = values.get('keep_exif', True)
    except Exception as e:
        # 直接更新する代わりにキューにメッセージを送る
        update_queue.put(('status', f"エラー: パスの正規化に失敗しました - {str(e)}"))
        update_queue.put(('btn_start', {'disabled': False}))
        update_queue.put(('btn_cancel', {'disabled': True}))
        return
    
    # 画像ファイルを検索
    try:
        update_queue.put(('status', "画像ファイルを検索中..."))
        image_files = core.find_image_files(source_dir)
        
        if not image_files:
            update_queue.put(('status', "画像ファイルが見つかりませんでした"))
            update_queue.put(('btn_start', {'disabled': False}))
            update_queue.put(('btn_cancel', {'disabled': True}))
            return
        
        # 進行状況の設定
        # 直接更新せずにキューに送る
        update_queue.put(('progress', {'value': 0}))
        update_queue.put(('progress_text', '0%'))
        # 詳細な処理説明を表示
        format_name = {'jpeg': 'JPEG', 'png': 'PNG', 'webp': 'WebP'}[format_type]
        exif_status = '保持する' if keep_exif else '削除する'
        balance_desc = '圧縮優先' if balance < 4 else '標準' if balance < 7 else '品質優先'
        
        status_msg = f"処理開始: 合計 {len(image_files)} ファイル\n" \
                   f"出力形式: {format_name}, 幅: {width}px, 品質: {quality}%, " \
                   f"バランス: {balance} ({balance_desc}), EXIF: {exif_status}"
        
        update_queue.put(('status', status_msg))
        
        # 処理結果の統計
        processed = 0
        errors = 0
        skipped = 0
        total_size_before = 0
        total_size_after = 0
        
        # 各画像を処理
        for idx, img_path in enumerate(image_files):
            if cancel_process:
                update_queue.put(('status', "処理がキャンセルされました"))
                break
                
            try:
                # 出力先パスを取得
                dest_path = core.get_destination_path(img_path, source_dir, dest_dir)
                
                # 処理状況を表示
                file_name = img_path.name
                update_queue.put(('current_file', f"{idx+1}/{len(image_files)}: {file_name}"))
                
                # ファイルサイズを取得
                file_size_before = img_path.stat().st_size
                total_size_before += file_size_before
                
                # 画像処理実行
                result = core.resize_and_compress_image(
                    img_path, dest_path, width, quality,
                    format=format_type,
                    keep_exif=keep_exif,
                    balance=balance,
                    dry_run=False
                )
                
                if result[0]:  # 処理成功
                    processed += 1
                    # 処理後のファイルサイズを取得
                    if dest_path.exists():
                        file_size_after = dest_path.stat().st_size
                        total_size_after += file_size_after
                        reduction = ((file_size_before - file_size_after) / file_size_before * 100)
                        status_msg = (f"処理: {core.format_file_size(file_size_before)} → "
                                     f"{core.format_file_size(file_size_after)} ({reduction:.1f}% 削減)")
                        update_queue.put(('status', status_msg))
                else:
                    errors += 1
                    update_queue.put(('status', f"エラー: 画像処理に失敗しました"))
                    
            except Exception as e:
                # 詳細なエラーメッセージを生成
                error_detail = str(e)
                suggestions = ""
                
                # エラータイプに基づいたメッセージ生成
                if "not in the subpath" in error_detail:
                    # 長いパスの問題
                    suggestions = "パスの形式が異なる場合に発生します。入力/出力先を再選択してみてください。"
                elif "invalid character" in error_detail.lower() or "illegal character" in error_detail.lower():
                    # 無効な文字の問題
                    suggestions = "ファイル名に無効な文字が含まれています。絵文字や特殊文字を含むファイル名を避けてください。"
                elif "access denied" in error_detail.lower() or "permission" in error_detail.lower():
                    # アクセス権限の問題
                    suggestions = "ファイルまたはフォルダへのアクセス権限がありません。管理者権限で実行してみてください。"
                elif os.name == 'nt' and ("path too long" in error_detail.lower() or "(206)" in error_detail):
                    # 長いパスの問題（Windows固有）
                    suggestions = "パスが長すぎます。Windowsの長いパス設定を有効にするか、より短いパスを使用してください。"
                
                # エラー情報の記録
                error_trace = traceback.format_exc()
                logger.error(f"予期せぬエラー: {error_detail}")
                logger.error(f"トレースバック情報:\n{error_trace}")
                
                # エラーメッセージを結合
                if suggestions:
                    error_detail = f"{error_detail}\n\n推奨対策: {suggestions}"
                
                # 直接GUI操作しないようキューにエラーを送る
                update_queue.put(('error_popup', error_detail))
                update_queue.put(('status', f"エラー: {error_detail[:50]}..."))
                
                skipped += 1
            
            # 進行状況の更新
            progress_value = idx + 1
            progress_percent = int((progress_value / len(image_files)) * 100)
            
            # 進捗状況をキューに送る
            update_queue.put(('progress', {'value': progress_value}))
            update_queue.put(('progress_text', f'{progress_percent}%'))
            
            # カンセルをチェック
            # 直接window.read()は呼び出さず、メインスレッドでチェックする
            # より効率的なイベント処理のために、キャンセル状態をキューで確認
            update_queue.put(('check_cancel', None))
            # 短い待機でCPU負荷を下げる（time.sleepより効率的）
            threading.Event().wait(0.001)
            
        # 処理完了
        if not cancel_process:
            reduction_rate = 0
            if total_size_before > 0:
                reduction_rate = ((total_size_before - total_size_after) / total_size_before * 100)
                
            summary = f"{len(image_files)}個の画像中{processed}個を処理しました。 "
            if errors > 0:
                summary += f"({errors}個のエラー) "
                # エラーの場合の追加情報
                if os.name == 'nt' and errors > 0:
                    # ログ出力から判断しない
                    summary += "\n注意: Windowsでは長いパスや特殊文字を含むファイル名で問題が発生することがあります。"
                    summary += "\n別のフォルダを使用するか、単純なファイル名の画像を処理してみてください。"
            
            if processed > 0:
                summary += f"\n総容量: {core.format_file_size(total_size_before)} → {core.format_file_size(total_size_after)}"
                summary += f" ({reduction_rate:.1f}% 削減)"
                
            # 直接更新せず、キューに送る
            update_queue.put(('status', summary))
            
            # 結果ダイアログ表示の内容もキューに送る
            popup_message = f"処理完了!\n\n" \
                           f"処理ファイル数: {processed}\n" \
                           f"エラー数: {errors}\n"
                           
            if processed > 0:
                popup_message += f"\n総容量: {core.format_file_size(total_size_before)} → {core.format_file_size(total_size_after)}"
                popup_message += f" ({reduction_rate:.1f}% 削減)"
                
            if errors > 0 and os.name == 'nt':
                popup_message += f"\n\n注意: {errors}個のファイルでエラーが発生しました。" \
                                f"ログを確認してください。"
            
            # パップアップの表示リクエストをキューに送る
            update_queue.put(('popup', {'message': popup_message, 'title': "処理結果"}))
            # 処理完了フラグも送信
            update_queue.put(('process_complete', True))
    except Exception as e:
        # エラー内容の詳細なログ記録
        error_msg = str(e)
        error_trace = traceback.format_exc()
        logger.error(f"予期せぬエラー: {error_msg}")
        logger.error(f"トレースバック情報:\n{error_trace}")
        
        # キューを使ってエラー情報を送信
        status_msg = f"予期せぬエラー: {error_msg}"
        update_queue.put(('status', status_msg))
        
        # デバッグモードの場合は詳細情報も送信
        if DEBUG_MODE:
            error_detail = f"{error_msg}\n\n{error_trace if error_trace else ''}" 
            update_queue.put(('error_popup', error_detail))
            
        # 処理完了フラグも送信
        update_queue.put(('process_complete', True))
        
        # ボタンの状態を元に戻すようキューに送る
        update_queue.put(('btn_start', {'disabled': False}))
        update_queue.put(('btn_cancel', {'disabled': True}))
        
    finally:
        # UI状態を元に戻すようキューに送る
        update_queue.put(('btn_start', {'disabled': False}))
        update_queue.put(('btn_cancel', {'disabled': True}))


def setup_logger():
    """
    ロガーの設定を行う関数
    """
    # デフォルトのロガー設定を削除
    logger.remove()
    
    # デバッグモードの場合は詳細情報を出力
    log_level = "DEBUG" if DEBUG_MODE else "INFO"
    
    # 画面出力用のロガー設定
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=log_level
    )
    
    # ログディレクトリの作成
    import os
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log")
    os.makedirs(log_dir, exist_ok=True)
    
    # ファイル出力用のロガー設定（ローテーション付き）
    from datetime import datetime
    log_filename = os.path.join(log_dir, "process_{time}.log")
    
    # ログローテーション設定を実装
    logger.add(
        log_filename,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="DEBUG",  # ファイルには常に詳細情報を記録
        rotation="500 KB",  # ファイルサイズが500KBを超えたらローテーション
        retention="10 days",  # ログは10日間保持
        compression="zip",  # 古いログをzip形式で圧縮
        encoding="utf-8"  # 日本語パスに対応
    )
    
    # 実際のファイル名を取得（現在のタイムスタンプが入る）
    current_log_file = os.path.join(log_dir, f"process_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log")
    
    return current_log_file

def main():
    """
    メイン関数 - GUIアプリケーションを実行します
    """
    global cancel_process, update_queue
    try:
        # ロガー設定
        log_filename = setup_logger()
        logger.info(f"GUIモードで起動しました。ログファイル: {log_filename}")
        logger.info(f"Pythonバージョン: {sys.version}")
        logger.info(f"OS情報: {os.name} - {sys.platform}")
        
        # デフォルト設定
        settings = {
            'source': './input',
            'dest': './output',
            'width': 1200,
            'quality': 87,
            'format': 'jpeg',
            'balance': 5,
            'keep_exif': True
        }
        
        # レイアウト定義
        layout = [
            [eg.Text('画像リサイズ・圧縮ツール', font=('', 16))],
            [eg.Text('入力フォルダ', size=(12, 1)), 
             eg.Input(settings['source'], key='source', width=40), 
             eg.FolderBrowse('参照')],
            [eg.Text('出力フォルダ', size=(12, 1)), 
             eg.Input(settings['dest'], key='dest', width=40), 
             eg.FolderBrowse('参照')],
            [eg.Text('リサイズ幅', size=(12, 1)), 
             eg.Slider(range=(300, 3000), default_value=settings['width'], resolution=100, 
                       orientation='h', width=40, key='width')],
            [eg.Text('JPEG品質', size=(12, 1)), 
             eg.Slider(range=(30, 100), default_value=settings['quality'], 
                      orientation='h', width=40, key='quality')],
            
            # 出力形式選択
            [eg.Text('出力形式:', size=(12, 1)),
             eg.Radio('JPEG', 'format', key='format_jpeg', default=settings['format']=='jpeg'),
             eg.Radio('PNG', 'format', key='format_png', default=settings['format']=='png'),
             eg.Radio('WebP', 'format', key='format_webp', default=settings['format']=='webp')],
             
            # 圧縮と品質のバランス調整
            [eg.Text('圧縮バランス:', size=(12, 1)), 
             eg.Slider(range=(1, 10), default_value=settings['balance'], orientation='h', width=40, 
                      key='balance', tooltip='1=最高圧縮率、ファイルサイズ優先 / 10=最高品質、画質優先')],
            
            # メタデータオプション
            [eg.Text('', size=(12, 1)), eg.Checkbox('EXIFメタデータを保持', default=settings['keep_exif'], key='keep_exif')],
            [eg.Text('処理ファイル:', size=(12, 1)), eg.Text('', key='current_file', size=(40, 1))],
            [eg.Text('進行状況:'), eg.Slider(range=(0, 100), default_value=0, resolution=1, 
                      orientation='h', width=45, key='progress', disabled=True),
             eg.Text('0%', key='progress_text', size=(5, 1))],
            [eg.Text('準備完了', key='status')],
            [eg.Button('実行', key='btn_start'), 
             eg.Button('キャンセル', key='btn_cancel', disabled=True), 
             eg.Button('終了')]
        ]
        
        # ウィンドウ作成
        window = eg.Window('画像リサイズ・圧縮ツール', layout, resizable=True)
        processing_thread = None
        
        # イベントループ
        while True:
            # キューからのメッセージを処理（ノンブロッキング）
            try:
                while True:  # 全ての待機中メッセージを処理
                    msg = update_queue.get_nowait()
                    if msg:
                        key, value = msg
                        if key == 'error_popup':
                            # エラーポップアップの処理
                            messagebox.showerror("エラー", value)
            # 処理前の合計サイズ計算
            total_size_before = 0
            
            # メモリ使用量の最適化のため、大量の画像を処理する場合はバッチ処理
            batch_size = 10  # 一度に処理するファイル数
            for i in range(0, len(image_files), batch_size):
                batch = image_files[i:i+batch_size]
                for img_path in batch:
                    try:
                        # リトライ機構を利用
                        def get_size(path):
                            return os.path.getsize(path)
                            
                        size = core.retry_on_file_error(get_size, img_path, max_retries=2, retry_delay=0.1)
                        total_size_before += size
                    except Exception as e:
                        logger.error(f"ファイルサイズ取得エラー: {e} - {img_path}")
                
                # 定期的にガベージコレクションを実行
                import gc
                gc.collect()
                        elif key == 'popup':
                            # 通常のポップアップを表示
                            try:
                                # valueは追加パラメータを持つ辞書
                                message = value.get('message', '')
{{ ... }}
                                eg.popup(message, title=title)
                            except Exception as e:
                                logger.error(f"GUIポップアップ表示に失敗: {e}")
                        elif key == 'check_cancel':
                            # キャンセル状態をスレッドに伝えるためのダミーメッセージ処理
                            # 実際のキャンセル状態はグローバル変数で管理されている
                            pass
                        elif key == 'process_complete':
                            # 処理完了の場合、スレッドをクリア
                            if processing_thread and processing_thread.is_alive():
                                processing_thread.join(0.1)  # スレッド終了を確認
                            processing_thread = None
                        elif isinstance(value, dict):
                            # 追加パラメータ付きの更新
                            window[key].update(**value)
                        else:
                            # 単純な更新
                            window[key].update(value)
                    update_queue.task_done()
            except queue.Empty:
                pass  # キューが空の場合は無視
            
            # GUIイベントを読み取る
            event, values = window.read(timeout=100)  # タイムアウトでGUIを応答的に
            
            if event in (eg.WINDOW_CLOSED, '終了'):
                break
                
            elif event == 'btn_start':
                # 入力値の検証
                source_dir = values['source']
                dest_dir = values['dest']
                
                if not os.path.exists(source_dir):
                    eg.popup_error(f'入力フォルダが見つかりません: {source_dir}')
                    continue
                    
                # 出力フォルダ作成確認
                if not os.path.exists(dest_dir):
                    if eg.popup_yes_no(f'出力フォルダ {dest_dir} が存在しません。作成しますか？') == 'Yes':
                        try:
                            os.makedirs(dest_dir, exist_ok=True)
                        except Exception as e:
                            error_trace = traceback.format_exc()
                            logger.error(f"出力フォルダの作成に失敗: {e}\n{error_trace}")
                            eg.popup_error(f'フォルダを作成できませんでした: {e}')
                            continue
                    else:
                        continue
                        
                # UI状態更新
                window['btn_start'].update(disabled=True)
                window['btn_cancel'].update(disabled=False)
                window['status'].update(f"処理準備中... 幅: {int(values['width'])}px, 品質: {int(values['quality'])}%")
                
                # 別スレッドで処理実行
                processing_thread = threading.Thread(
                    target=process_images_thread,
                    args=(values, window),
                    daemon=True
                )
                processing_thread.start()
                
            elif event == 'btn_cancel':
                cancel_process = True
                window['status'].update("キャンセル中...")
        
        # ウィンドウを閉じる
        window.close()
    except Exception as e:
        # 未処理の例外をログに記録
        error_trace = traceback.format_exc()
        logger.critical(f"メイン関数で予期せぬエラーが発生しました: {e}")
        logger.critical(f"トレースバック情報:\n{error_trace}")
        
        # デバッグモードの場合は推奨対策も表示
        error_msg = f"予期せぬエラーが発生しました: {e}"
        if DEBUG_MODE:
            error_msg += f"\n\nトレースバック情報:\n{error_trace}"
            error_msg += "\n\n推奨対策:\n1. ログファイルを確認してください\n2. Python環境が正しく設定されているか確認してください"
        
        # エラーダイアログ表示
        try:
            eg.popup_error(error_msg, title="エラー")
        except:
            # GUIが使えない場合は標準出力
            print(f"\nエラー: {error_msg}")
        
        sys.exit(1)  # エラー終了

if __name__ == '__main__':
    main()
