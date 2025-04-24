#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
画像リサイズ・圧縮ツール GUI版

TkEasyGUIを使ったグラフィカルインターフェースで
画像のリサイズと圧縮を行います。
"""

import os
import sys
import threading
import time
import traceback
from pathlib import Path

import TkEasyGUI as eg

# コア機能をインポート
import resize_core as core
from resize_core import logger

# デバッグモード設定
DEBUG_MODE = True  # Trueにすると詳細なエラー情報を表示

# グローバル変数
cancel_process = False  # 処理キャンセルフラグ

def process_images_thread(values, window):
    """
    別スレッドで実行する画像処理関数
    """
    global cancel_process
    cancel_process = False
    
    try:
        # パスの正規化処理
        source_dir = Path(core.normalize_long_path(values['source'], add_prefix=False, remove_prefix=True))
        dest_dir = Path(core.normalize_long_path(values['dest'], add_prefix=False, remove_prefix=True))
        width = int(values['width'])
        quality = int(values['quality'])
    except Exception as e:
        window['status'].update(f"エラー: パスの正規化に失敗しました - {str(e)}")
        window['btn_start'].update(disabled=False)
        window['btn_cancel'].update(disabled=True)
        return
    
    # 画像ファイルを検索
    try:
        window['status'].update("画像ファイルを検索中...")
        image_files = core.find_image_files(source_dir)
        
        if not image_files:
            window['status'].update("画像ファイルが見つかりませんでした")
            window['btn_start'].update(disabled=False)
            window['btn_cancel'].update(disabled=True)
            return
            
        # 進行状況の設定
        # Sliderコンポーネント用の更新
        # TkEasyGUI 0.2.80の仕様に合わせて更新方法を修正
        try:
            # 特定のバージョンではrangeがサポートされていない可能性がある
            window['progress'].update(value=0)
        except Exception as e:
            logger.warning(f"Sliderの更新メソッドに問題があります: {e}")
            logger.info("代替の更新方法を試行します")
            try:
                # 別の更新方法を試行
                window['progress'].update(0)
            except:
                logger.error("進行表示の更新に失敗しましたが処理は続行します")
                
        # 進行状況テキストの更新
        window['progress_text'].update('0%')
        window['status'].update(f"処理開始: 合計 {len(image_files)} ファイル")
        
        # 処理結果の統計
        processed = 0
        errors = 0
        skipped = 0
        total_size_before = 0
        total_size_after = 0
        
        # 各画像を処理
        for idx, img_path in enumerate(image_files):
            if cancel_process:
                window['status'].update("処理がキャンセルされました")
                break
                
            try:
                # 出力先パスを取得
                dest_path = core.get_destination_path(img_path, source_dir, dest_dir)
                
                # 処理状況を表示
                file_name = img_path.name
                window['current_file'].update(f"{idx+1}/{len(image_files)}: {file_name}")
                
                # ファイルサイズを取得
                file_size_before = img_path.stat().st_size
                total_size_before += file_size_before
                
                # 画像処理実行
                result = core.resize_and_compress_image(
                    img_path, dest_path, width, quality, False
                )
                
                if result[0]:  # 処理成功
                    processed += 1
                    # 処理後のファイルサイズを取得
                    if dest_path.exists():
                        file_size_after = dest_path.stat().st_size
                        total_size_after += file_size_after
                        reduction = ((file_size_before - file_size_after) / file_size_before * 100)
                        window['status'].update(
                            f"処理: {core.format_file_size(file_size_before)} → "
                            f"{core.format_file_size(file_size_after)} ({reduction:.1f}% 削減)"
                        )
                else:
                    errors += 1
                    window['status'].update(f"エラー: 画像処理に失敗しました")
                    
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
                    suggestions = "ファイルへのアクセス権限が不足しています。管理者権限で実行するか、別のフォルダを選択してください。"
                elif os.name == 'nt' and ("path too long" in error_detail.lower() or "(206)" in error_detail):
                    # 長いパスの問題（Windows固有）
                    suggestions = "パスが長すぎます。Windowsの長いパス設定を有効にするか、より短いパスを使用してください。"
                
                # 詳細なエラーメッセージを表示
                error_msg = f"エラー: {error_detail}"
                if suggestions:
                    error_msg += f"\n提案: {suggestions}"
                    
                window['status'].update(error_msg)
                errors += 1
                
            # 進捗更新
            progress_value = idx + 1
            progress_percent = int((progress_value / len(image_files)) * 100)
            
            # TkEasyGUI 0.2.80との互換性を確保するためのエラーハンドリング
            try:
                # 新しいバージョンの更新方法
                window['progress'].update(value=progress_value)
                logger.debug(f"進捗更新成功: update(value=progress_value) 方式")
            except Exception as update_error:
                logger.debug(f"Slider更新例外 #1: {update_error}")
                try:
                    # 代替の更新方法を試行
                    window['progress'].update(progress_value)
                    logger.debug(f"進捗更新成功: update(progress_value) 方式")
                except Exception as alt_error:
                    logger.debug(f"Slider更新例外 #2: {alt_error}")
                    try:
                        # 別の更新方法を試行
                        window['progress'].update(progress_percent)
                        logger.debug(f"進捗更新成功: update(progress_percent) 方式")
                    except Exception as percent_error:
                        logger.debug(f"Slider更新例外 #3: {percent_error}")
                        try:
                            # 最後の手段として直接keyを指定しない方法
                            window.Element('progress').update(progress_value)
                            logger.debug(f"進捗更新成功: Element('progress').update() 方式")
                        except Exception as last_error:
                            logger.debug(f"Slider更新例外 #4: {last_error}")
                            logger.warning("すべての進捗更新方法が失敗しましたが、処理は続行します")
            
            # 進行状況テキストの更新
            window['progress_text'].update(f'{progress_percent}%')
            
            # GUI応答性維持のためのイベントチェック
            event, values = window.read(timeout=10)
            if event == 'btn_cancel':
                if self._cancel_requested and not self._cancellation_confirmed:
                    self._cancellation_confirmed = True
            # タイムアウトイベントで対応するのでここでの待機は不要
            # time.sleep(0.01)
            
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
                    if any("not in the subpath" in str(e) for e in core.logger.handlers[0].buffer if hasattr(core.logger.handlers[0], 'buffer')):
                        summary += "\n注意: Windowsの長いパスや絵文字を含むファイル名で問題が発生しています。"
                        summary += "\n別のフォルダを使用するか、単純なファイル名の画像を処理してみてください。"
            
            if processed > 0:
                summary += f"\n総容量: {core.format_file_size(total_size_before)} → {core.format_file_size(total_size_after)}"
                summary += f" ({reduction_rate:.1f}% 削減)"
                
            window['status'].update(summary)
            
            # 結果ダイアログ表示
            popup_message = f"処理完了!\n\n" \
                           f"処理ファイル数: {processed}\n" \
                           f"エラー数: {errors}\n"
                           
            if processed > 0:
                popup_message += f"元のサイズ: {core.format_file_size(total_size_before)}\n" \
                                f"処理後サイズ: {core.format_file_size(total_size_after)}\n" \
                                f"削減率: {reduction_rate:.1f}%"
                                
            if errors > 0 and os.name == 'nt':
                popup_message += f"\n\n注意: {errors}個のファイルでエラーが発生しました。" \
                                f"ログを確認してください。"
            
            eg.popup(popup_message, title="処理結果")
    except Exception as e:
        # エラー内容の詳細なログ記録
        error_msg = str(e)
        error_trace = traceback.format_exc()
        logger.error(f"予期せぬエラー: {error_msg}")
        logger.error(f"トレースバック情報: \n{error_trace}")
        
        # デバッグモードの場合は詳細情報を表示
        if DEBUG_MODE:
            error_detail = f"{error_msg}\n\n{error_trace if error_trace else ''}" 
            window['status'].update(f"予期せぬエラー\n(詳細はログファイルを確認): {error_detail}")
            # エラーダイアログ表示
            eg.popup_error(f"予期せぬエラーが発生しました\n\n{error_detail}", title="エラー")
        else:
            window['status'].update(f"予期せぬエラー: {error_msg}\n(詳細はログファイルを確認)")
            # シンプルなエラーダイアログ
            eg.popup_error(f"予期せぬエラーが発生しました: {error_msg}", title="エラー")
        
        # ボタンの状態を元に戻す
        window['btn_start'].update(disabled=False)
        window['btn_cancel'].update(disabled=True)
        
    finally:
        # UI状態を元に戻す
        window['btn_start'].update(disabled=False)
        window['btn_cancel'].update(disabled=True)


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
    
    # ファイル出力用のロガー設定
    from datetime import datetime
    log_filename = f"process_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S_%f')}.log"
    logger.add(
        log_filename,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="DEBUG"  # ファイルには常に詳細情報を記録
    )
    
    return log_filename

def main():
    """
    メイン関数 - GUIアプリケーションを実行します
    """
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
            'quality': 87
        }
    
    # レイアウト定義
    layout = [
        [eg.Text('画像リサイズ・圧縮ツール', font=('', 16))],
        [eg.Text('入力フォルダ', size=(12, 1)), 
         eg.Input(settings['source'], key='source', size=(40, 1)), 
         eg.FolderBrowse('参照')],
        [eg.Text('出力フォルダ', size=(12, 1)), 
         eg.Input(settings['dest'], key='dest', size=(40, 1)), 
         eg.FolderBrowse('参照')],
        [eg.Text('リサイズ幅', size=(12, 1)), 
         eg.Slider(range=(300, 3000), default_value=settings['width'], resolution=100, 
                  orientation='h', size=(40, 15), key='width')],
        [eg.Text('JPEG品質', size=(12, 1)), 
         eg.Slider(range=(30, 100), default_value=settings['quality'], 
                  orientation='h', size=(40, 15), key='quality')],
        [eg.Text('処理ファイル:', size=(12, 1)), eg.Text('', key='current_file', size=(40, 1))],
        [eg.Text('進行状況:'), eg.Slider(range=(0, 100), default_value=0, resolution=1, 
                  orientation='h', size=(45, 15), key='progress', disabled=True),
         eg.Text('0%', key='progress_text', size=(5, 1))],
        [eg.Text('準備完了', key='status')],
        [eg.Button('実行', key='btn_start'), 
         eg.Button('キャンセル', key='btn_cancel', disabled=True), 
         eg.Button('終了')]
    ]
    
    # ウィンドウ作成
    window = eg.Window('画像リサイズ・圧縮ツール', layout, resizable=True)
    
    # イベントループ
    while True:
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
            threading.Thread(
                target=process_images_thread,
                args=(values, window),
                daemon=True
            ).start()
            
        elif event == 'btn_cancel':
            global cancel_process
            cancel_process = True
            window['status'].update("キャンセル中...")
    
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
