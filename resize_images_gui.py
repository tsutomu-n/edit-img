#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
画像リサイズ・圧縮ツール GUI版

TkEasyGUIを使ったグラフィカルインターフェースで
画像のリサイズと圧縮を行います。
"""

import os
import sys
from pathlib import Path

import TkEasyGUI as eg

# コア機能をインポート
import resize_core as core

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
        [eg.Text('', key='status')],
        [eg.Button('実行', key='btn_start'), 
         eg.Button('終了')]
    ]
    
    # ウィンドウ作成
    window = eg.Window('画像リサイズ・圧縮ツール', layout, resizable=True)
    
    # イベントループ
    while True:
        event, values = window.read()
        
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
                    
            # パラメータ表示
            window['status'].update(f"幅: {int(values['width'])}px, 品質: {int(values['quality'])}%")
            eg.popup(f"処理を開始します\n\n入力: {source_dir}\n出力: {dest_dir}\n幅: {int(values['width'])}px\n品質: {int(values['quality'])}%")
    
    window.close()

if __name__ == '__main__':
    main()
