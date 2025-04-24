# 画像リサイズ・圧縮ツール

日本語ファイル名に対応した画像リサイズ・圧縮ツールです。指定されたディレクトリから画像ファイル(.jpg, .png)を検索し、指定された幅にリサイズして、圧縮率を指定してJPEG形式で保存します。コマンドライン版とGUI版の両方を提供しています。

![GUI画面例](.github/screenshots/gui_example.png)

## 機能

- 横幅を指定してリサイズ（アスペクト比維持）
- JPEG圧縮率の調整
- 日本語ファイル名・フォルダ名対応
- ディレクトリ構造の維持
- Windows 11のパス長制限対応
- ドライラン機能（変更前に処理内容を確認）
- 詳細なログ出力
- GUIモードとコマンドラインモードの両方に対応
- 非同期処理と進捗表示

## 前提条件

- Python 3.12以上
- 依存ライブラリ：
  - Pillow: 画像処理
  - loguru: ロギング
  - tqdm: 進捗表示（CLI版）
  - TkEasyGUI: GUIフレームワーク（GUI版）

## インストール

### uvを使用したインストール（推奨）

```bash
# リポジトリのクローン
git clone https://github.com/yourusername/edit-img.git
cd edit-img

# 仮想環境の作成
uv venv

# 仮想環境の有効化
# Windowsの場合
.venv\Scripts\activate
# Linux/macOSの場合
source .venv/bin/activate

# 依存ライブラリのインストール
uv sync
```

### pipを使用したインストール

```bash
# リポジトリのクローン
git clone https://github.com/yourusername/edit-img.git
cd edit-img

# 仮想環境の作成
python -m venv .venv

# 仮想環境の有効化
# Windowsの場合
.venv\Scripts\activate
# Linux/macOSの場合
source .venv/bin/activate

# 依存ライブラリのインストール
pip install -e .
```

## 使用方法

コマンドライン版とGUI版の二つの方法で利用できます。

### 1. ディレクトリ構造

処理したい画像ファイルを `input` ディレクトリ内に配置します。

```
edit-img/
  ├─ input/            # 入力画像を配置するディレクトリ
  │   ├─ 山田太郎/     # 人物名ごとのフォルダ
  │   │   ├─ 足場.jpg   # 資格画像
  │   │   └─ クレーン.jpg
  │   ├─ 鈴木一郎/
  │   │   └─ ...
  │   └─ ...
  │
  ├─ output/           # 処理済み画像の出力先
  ├─ resize_images.py    # CLI版処理スクリプト
  ├─ resize_images_gui.py # GUI版処理スクリプト
  └─ resize_core.py     # コア機能モジュール
```

### 2. GUI版の起動方法

```bash
# 直接実行
python resize_images_gui.py

# またはインストール後
edit-img-gui
```

GUIアプリケーションが起動します。以下のステップで操作します：

1. 入力フォルダと出力フォルダを選択（「参照」ボタンでブラウズ可能）
2. リサイズ幅とJPEG品質をスライダーで調整
3. 「実行」ボタンをクリックして処理開始
4. 進捗バーで処理状況を確認
5. 必要に応じて「キャンセル」ボタンで処理を中断

### 3. コマンドライン版の使い方

```bash
# 基本的な使い方
python resize_images.py

# またはインストール後
edit-img-cli
```

### 4. ドライランモード（CLI版のみ）

```bash
python resize_images.py --dry-run
```

### 5. カスタム設定（CLI版）

```bash
# 横幅800px、JPEG品質90%で処理
python resize_images.py --width 800 --quality 90

# 詳細出力モード
python resize_images.py --verbose

# 入力・出力ディレクトリを指定
python resize_images.py --source "別のパス" --destination "別の出力先"
```

## オプション一覧（CLI版）

| オプション | 短縮形 | デフォルト値 | 説明 |
|----------|-------|------------|------|
| `--source` | `-s` | `./input` | 入力ディレクトリのパス |
| `--destination` | `-d` | `./output` | 出力先ディレクトリのパス |
| `--width` | `-w` | `1200` | リサイズする幅（ピクセル） |
| `--quality` | `-q` | `87` | JPEG品質（1-100） |
| `--dry-run` | なし | `False` | ドライラン実行（実際に変更しない） |
| `--verbose` | `-v` | `False` | 詳細出力モード |

## 処理結果

処理結果は `output` ディレクトリに保存され、元のディレクトリ構造が維持されます。

例：
- 入力：`input/山田太郎/足場.jpg`
- 出力：`output/山田太郎/足場.jpg`（リサイズ・圧縮済み）

## ログ

処理の詳細なログは `process_日付.log` ファイルに記録されます。エラーが発生した場合は、このログファイルを確認してください。

## 他プラットフォームでの実行

このツールは以下のプラットフォームで動作確認済みです：

- Windows 11（日本語版） - 完全対応
- Linux (Ubuntuなど) - 完全対応
- macOS - 完全対応

### GUI版の起動（X11を使用する環境）

Linuxサーバー環境などでGUIを表示する場合は、X11転送が必要です。

```bash
# SSHでX11転送を有効にして接続
ssh -X username@hostname

# WindowsのWSL2で実行する場合
# 1. VcXsrvなどのX serverをインストール
# 2. 環境変数を設定
export DISPLAY=:0
```

## 注意事項

- 大量の画像を処理する場合は、メモリ使用量に注意してください。
- 元のファイル名に使用できない文字（`\ / : * ? " < > |`）が含まれていた場合、自動的に安全なファイル名に変換されます。
- `.jpg`と`.jpeg`以外の拡張子を持つファイル（PNGなど）は、JPEG形式に変換されます。
- GUI版では、処理中にアプリケーションが応答しなくなった場合でもバックグラウンドで処理が続行されています。キャンセルボタンで中断できます。
- Windows環境で長いパス名（260文字以上）のファイルを処理する場合、自動的に長いパス対応モードで処理されます。

## コントリビューション

本プロジェクトへの貢献を歓迎します。バグ報告や機能要望は、GitHubのIssueでご報告ください。
