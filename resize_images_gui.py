#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
画像リサイズ・圧縮ツール GUI版

TkEasyGUIを使ったグラフィカルインターフェースで
画像のリサイズと圧縮を行います。
モダンなデザインとユーザビリティを備えています。
"""

import os
import sys
import time
import signal
import threading
import traceback
import queue
import json
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageTk

# TkEasyGUI
import tkinter as tk
import TkEasyGUI as eg
from TkEasyGUI import widgets
from TkEasyGUI import dialogs
from tkinter import messagebox, ttk

# カスタム画像処理モジュール
import resize_core as core
from resize_core import logger

# デバッグモード設定
DEBUG_MODE = True  # Trueにすると詳細なエラー情報を表示

# グローバル変数
cancel_process = False  # 処理キャンセルフラグ
update_queue = queue.Queue()  # スレッド間通信用キュー

# 設定ファイルパス
SETTINGS_FILE = Path(__file__).parent / 'gui_settings.json'

def process_images_thread(values, window, dry_run=False):
    """
    別スレッドで実行する画像処理関数
    
    Args:
        values: GUIからの入力値
        window: ウィンドウオブジェクト
        dry_run: プレビューモード（True）か実行モード（False）か
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
        update_queue.put(('btn_preview', {'disabled': False}))
        update_queue.put(('btn_execute', {'disabled': False}))
        update_queue.put(('btn_cancel', {'disabled': True}))
        return
    
    # 画像ファイルを検索
    try:
        update_queue.put(('status', "画像ファイルを検索中..."))
        image_files = core.find_image_files(source_dir)
        
        if not image_files:
            update_queue.put(('status', "画像ファイルが見つかりませんでした"))
            update_queue.put(('btn_preview', {'disabled': False}))
            update_queue.put(('btn_execute', {'disabled': False}))
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
            # キャンセルフラグの確認
            # キャンセル状態を確認するダミーメッセージをキューに送る
            update_queue.put(('check_cancel', None))
            
            if cancel_process:
                update_queue.put(('status', "処理がキャンセルされました"))
                break
            
            try:
                # 出力先パスを取得
                dest_path = core.get_destination_path(img_path, source_dir, dest_dir)
                
                # 処理状況を表示
                file_name = img_path.name
                update_queue.put(('current_file', f"{idx+1}/{len(image_files)}: {file_name}"))
                
                # 進行状況を更新
                progress_percent = int((idx / len(image_files)) * 100)
                update_queue.put(('progress', {'value': progress_percent}))
                update_queue.put(('progress_text', f'{progress_percent}%'))
                
                # ファイルサイズを取得
                file_size_before = img_path.stat().st_size
                total_size_before += file_size_before
                
                # 画像処理実行
                try:
                    success, original_size, estimated_size = core.resize_and_compress_image(
                        img_path, dest_path, width, quality,
                        format=format_type,
                        keep_exif=keep_exif,
                        balance=balance,
                        dry_run=dry_run
                    )
                except Exception as e:
                    logger.error(f"画像処理中に例外が発生しました: {e}")
                    errors += 1
                    continue
                
                if success:  # 処理成功
                    processed += 1
                    # ファイルサイズ情報が取得できた場合、結果を更新
                    if file_size_before > 0:
                        # プレビューモードとそうでない場合で分岐
                        if dry_run and estimated_size is not None:
                            # 予測サイズを使用
                            file_size_after = estimated_size
                            status_prefix = "【プレビュー】予測: "
                        elif not dry_run:
                            # 実際のファイルサイズを取得
                            file_size_after = dest_path.stat().st_size
                            status_prefix = ""
                        else:
                            # 予測できなかった場合
                            update_queue.put(('status', "サイズ予測ができませんでした"))
                            continue
                        
                        reduction = ((file_size_before - file_size_after) / file_size_before * 100)
                        status_msg = (f"{status_prefix}{core.format_file_size(file_size_before)} → "
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
                mode_prefix = "【プレビュー】" if dry_run else ""
                summary = (f"{mode_prefix}処理完了: {processed}ファイル処理, {errors}エラー, {skipped}スキップ")
                if total_size_before > 0 and total_size_after > 0:
                    total_reduction = (total_size_before - total_size_after) / total_size_before * 100
                    action_msg = "推定削減量" if dry_run else "削減量"
                    summary += (f"\n合計{action_msg}: {core.format_file_size(total_size_before)} → "
                                f"{core.format_file_size(total_size_after)} "
                                f"({total_reduction:.1f}% 削減)")
            
            # 直接更新せず、キューに送る
            update_queue.put(('status', summary))
            
            # 結果ダイアログ表示の内容もキューに送る
            popup_message = f"処理完了!\n\n" \
                           f"処理ファイル数: {processed}\n" \
                           f"エラー数: {errors}\n"
                           
            if processed > 0:
                # action_msg変数をここでも定義
                action_msg = "推定削減量" if dry_run else "削減量"
                popup_message += f"\n合計{action_msg}: {core.format_file_size(total_size_before)} → {core.format_file_size(total_size_after)}"
                popup_message += f" ({total_reduction:.1f}% 削減)"
                
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
        update_queue.put(('btn_preview', {'disabled': False}))
        update_queue.put(('btn_execute', {'disabled': False}))
        update_queue.put(('btn_cancel', {'disabled': True}))
        
    finally:
        # UI状態を元に戻すようキューに送る
        update_queue.put(('btn_preview', {'disabled': False}))
        update_queue.put(('btn_execute', {'disabled': False}))
        update_queue.put(('btn_cancel', {'disabled': True}))
        
        # 処理完了時のUIリセット
        update_queue.put(('btn_preview', {'disabled': False}))
        update_queue.put(('btn_execute', {'disabled': values.get('preview_mode', True)}))
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

def load_settings():
    """
    保存された設定を読み込む
    """
    default_settings = {
        'source': './input',
        'dest': './output',
        'width': 1200,
        'quality': 87,
        'format_jpeg': True,
        'format_png': False,
        'format_webp': False,
        'balance': 5,
        'keep_exif': True,
        'preview_mode': True,  # デフォルトはプレビューモード
    }
    
    if not SETTINGS_FILE.exists():
        return default_settings
        
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            saved_settings = json.load(f)
        # デフォルト設定をロードした設定で上書き
        settings = default_settings.copy()
        settings.update(saved_settings)
        return settings
    except Exception as e:
        logger.error(f"設定ファイル読み込みエラー: {e}")
        return default_settings

def save_settings(settings):
    """
    設定をJSONファイルに保存
    """
    try:
        # GUIコントロール関連の値を除外
        save_keys = ['source', 'dest', 'width', 'quality', 'format_jpeg', 
                    'format_png', 'format_webp', 'balance', 'keep_exif',
                    'preview_mode']
        save_data = {k: settings[k] for k in save_keys if k in settings}
        
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"設定ファイル保存エラー: {e}")
        return False

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
        
        # 設定を読み込む
        settings = load_settings()
        
        # テーマ設定
        # eg.theme("SystemDefaultForReal") # Windowsで利用できない場合がある
        eg.theme("vista") # Windows標準に近いテーマに変更

        # レイアウト定義
        layout = [
            # ヘッダーセクション
            [eg.Column([
                [eg.Text('画像リサイズ・圧縮ツール', font=('Noto Sans CJK JP', 12, 'bold'))]
            ])],
            
            # 入出力設定カード
            [eg.Frame('フォルダ設定', [
                [eg.Text('入力フォルダ', size=(12, 1)), 
                 eg.Input(settings['source'], key='source', size=(40, 1)), 
                 eg.FolderBrowse('参照', button_color=('white', '#007ACC'))],
                [eg.Text('出力フォルダ', size=(12, 1)), 
                 eg.Input(settings['dest'], key='dest', size=(40, 1)), 
                 eg.FolderBrowse('参照', button_color=('white', '#007ACC'))]
            ])],
            
            # 画像設定カード
            [eg.Frame('画像設定', [
                # リサイズ設定
                [eg.Text('リサイズ幅', size=(12, 1)), 
                 eg.Slider(range=(300, 3000), default_value=settings['width'], resolution=100, 
                           orientation='h', size=(40, 15), key='width',
                           trough_color='#3C3C3C', slider_depth=16)],
                [eg.Text(f"{settings['width']}px", key='width_value', size=(8, 1), font=('Noto Sans CJK JP', 10))],
                
                # JPEG品質設定
                [eg.Text('JPEG品質', size=(12, 1)), 
                 eg.Slider(range=(30, 100), default_value=settings['quality'], 
                          orientation='h', size=(40, 15), key='quality',
                          trough_color='#3C3C3C', slider_depth=16)],
                [eg.Text(f"{settings['quality']}%", key='quality_value', size=(8, 1), font=('Noto Sans CJK JP', 10))],
                
                # 出力形式選択
                [eg.Text('出力形式:', size=(12, 1)),
                 eg.Radio('JPEG', 'format', key='format_jpeg', default=settings.get('format_jpeg', True)),
                 eg.Radio('PNG', 'format', key='format_png', default=settings.get('format_png', False)),
                 eg.Radio('WebP', 'format', key='format_webp', default=settings.get('format_webp', False))],
                 
                # 圧縮と品質のバランス調整
                [eg.Text('圧縮バランス:', size=(12, 1)), 
                 eg.Slider(range=(1, 10), default_value=settings.get('balance', 5), orientation='h', size=(40, 15), 
                          key='balance', trough_color='#3C3C3C', slider_depth=16)],
                [eg.Text(f"バランス: {settings.get('balance', 5)}", key='balance_value', size=(12, 1), font=('Noto Sans CJK JP', 10))],
                [eg.Text('1=最高圧縮率(ファイルサイズ優先) / 10=最高品質(画質優先)', size=(50, 1), font=('Noto Sans CJK JP', 10))],
            ])],
            
            # オプション設定カード
            [eg.Frame('オプション', [
                # メタデータオプション
                [eg.Checkbox('EXIFメタデータを保持', default=settings.get('keep_exif', True), key='keep_exif')],
                [eg.Checkbox("プレビューモード（ファイルを実際に保存しません）", default=settings.get('preview_mode', True), 
                             key="preview_mode")],
            ])],
            
            # 進行状況表示カード
            [eg.Frame('処理状況', [
                [eg.Text('処理ファイル:', size=(12, 1)), 
                 eg.Text('', key='current_file', size=(40, 1), font=('Noto Sans CJK JP', 10))],
                [eg.Text('進行状況:', size=(12, 1)), 
                 eg.ProgressBar(max_value=100, orientation='h', size=(40, 20), key='progress', bar_color=('#007ACC', '#2E2E2E')),
                 eg.Text('0%', key='progress_text', size=(5, 1), font=('Noto Sans CJK JP', 10))],
                [eg.Text('準備完了', key='status', size=(50, 2), font=('Noto Sans CJK JP', 10))],
            ])],
            
            # アクションボタン
            [eg.Button("プレビュー", key="btn_preview", button_color=('white', '#007ACC'), font=('Noto Sans CJK JP', 10, 'bold'), border_width=0, size=(10, 1)), 
             eg.Button("実行", key="btn_execute", button_color=('white', '#007ACC'), font=('Noto Sans CJK JP', 10, 'bold'), border_width=0, size=(10, 1), disabled=settings.get('preview_mode', True)),
             eg.Button("キャンセル", key="btn_cancel", button_color=('white', '#FF0000'), font=('Noto Sans CJK JP', 10, 'bold'), border_width=0, size=(10, 1), disabled=True),
             eg.Button("終了", key="exit", button_color=('white', '#AAAAAA'), font=('Noto Sans CJK JP', 10, 'bold'), border_width=0, size=(10, 1))]
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
                            eg.popup_error(value, title="エラー")
                        elif key == 'popup':
                            # 通常のポップアップを表示
                            try:
                                # valueは追加パラメータを持つ辞書
                                message = value.get('message', '')
                                title = value.get('title', '情報')
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
                # キューが空の場合、処理を続行
                pass
                
            # GUIイベントを読み取る
            event, values = window.read(timeout=100)  # タイムアウトでGUIを応答的に
            
            # スライダー値の表示を更新
            if 'width' in values:
                window['width_value'].update(f"{int(values['width'])}px")
            if 'quality' in values:
                window['quality_value'].update(f"{int(values['quality'])}%")
            if 'balance' in values:
                balance_text = "ファイルサイズ優先" if values['balance'] < 4 else "バランス" if values['balance'] < 7 else "画質優先"
                window['balance_value'].update(f"バランス: {int(values['balance'])} ({balance_text})")
            
            if event in (eg.WINDOW_CLOSED, '終了'):
                # 設定を保存
                save_settings(values)
                break
                
            elif event == 'プレビューモード':
                # プレビューモードの切り替え時の処理
                window['実行'].update(disabled=values['プレビューモード'])
                
                # 適切なボタンを強調表示
                if values['プレビューモード']:
                    window['プレビュー'].update(button_color=('white', '#007ACC'))  # 緑色強調
                    window['実行'].update(button_color=('white', '#AAAAAA'))  # グレー化
                else:
                    window['プレビュー'].update(button_color=('white', '#AAAAAA'))  # グレー化
                    window['実行'].update(button_color=('white', '#007ACC'))  # 青色強調
                
            elif event == 'プレビュー' or event == '実行':
                # プレビューか実行かの判定
                is_preview = event == 'プレビュー'
                # 入力値の検証
                source_dir = values['入力フォルダ']
                dest_dir = values['出力フォルダ']
                
                # プレビューモードの場合はチェックボックスを強制的にオン
                if is_preview:
                    values['プレビューモード'] = True
                    window['プレビューモード'].update(True)
                
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
                window['プレビュー'].update(disabled=True)
                window['実行'].update(disabled=True)
                window['キャンセル'].update(disabled=False)
                
                # モードに応じたステータス表示
                mode_prefix = "【プレビュー】" if is_preview else ""
                window['ステータス'].update(f"{mode_prefix}処理準備中... 幅: {int(values['幅'])}px, 品質: {int(values['品質'])}%")
                
                # 別スレッドで処理実行
                processing_thread = threading.Thread(
                    target=process_images_thread,
                    args=(values, window, is_preview),  # プレビューフラグを渡す
                    daemon=True
                )
                processing_thread.start()
                
            elif event == 'キャンセル':
                cancel_process = True
                window['ステータス'].update("キャンセル中...")
        
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
