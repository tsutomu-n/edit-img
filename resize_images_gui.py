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
from pathlib import Path

import TkEasyGUI as eg

# コア機能をインポート
import resize_core as core

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
            
        # プログレスバーの設定
        # Sliderコンポーネント用の更新
        window['progress'].update(range=(0, len(image_files)))
        window['progress'].update(value=0)
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
            window['progress'].update(value=progress_value)
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
        window['status'].update(f"予期せぬエラー: {str(e)}")
        
    finally:
        # UI状態を元に戻す
        window['btn_start'].update(disabled=False)
        window['btn_cancel'].update(disabled=True)


def main():
    """
    メイン関数 - GUIアプリケーションを実行します
    """
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

if __name__ == '__main__':
    main()
