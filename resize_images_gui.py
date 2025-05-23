import customtkinter as ctk
from tkinter import filedialog, TclError
from pathlib import Path
import threading
import time

# 日本語フォント設定モジュールをインポート
try:
    from japanese_font_utils import get_normal_font, get_button_font, get_heading_font
except ImportError:
    # フォールバック用の簡易フォント設定
    def get_normal_font():
        return {"family": "", "size": 11}

    def get_button_font():
        return {"family": "", "size": 11, "weight": "bold"}

    def get_heading_font():
        return {"family": "", "size": 13, "weight": "bold"}


try:
    from resize_core import (
        resize_and_compress_image,
        get_destination_path,
        sanitize_filename,
        format_file_size,
    )
except ImportError:

    def resize_and_compress_image(*args, **kwargs):
        print("ダミー: resize_and_compress_image")
        return True, {'original_size': 100000, 'new_size': 50000, 'compression_ratio': 50.0}, "ダミー処理成功"

    def get_destination_path(source_path, source_dir, dest_dir):
        print("ダミー: get_destination_path")
        return Path(dest_dir) / Path(source_path).name

    def sanitize_filename(filename):
        print("ダミー: sanitize_filename")
        return filename
        
    def format_file_size(size_in_bytes):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_in_bytes < 1024.0 or unit == 'GB':
                break
            size_in_bytes /= 1024.0
        return f"{size_in_bytes:.1f} {unit}"


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("画像処理ツール")
        
        # ウィンドウサイズを設定
        self.geometry("1000x800")
        self.minsize(900, 700)  # 最小サイズを設定
        
        # フレームの拡大性を確保するためにgridを設定
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # フォント設定の初期化
        self.normal_font = ctk.CTkFont(**get_normal_font())
        self.button_font = ctk.CTkFont(**get_button_font())
        self.heading_font = ctk.CTkFont(**get_heading_font())

        # 先にログとプログレスバーのフレームを作成
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=0)
        self.main_frame.grid_columnconfigure(0, weight=1)
        
        # ログとプログレスバーを先に初期化
        self.log_progress_frame = ctk.CTkFrame(self.main_frame, corner_radius=6)
        self.log_progress_frame.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        self.log_progress_frame.grid_columnconfigure(0, weight=1)

        self.log_textbox = ctk.CTkTextbox(
            self.log_progress_frame,
            height=120,
            corner_radius=6,
            wrap="word",
            state="disabled",
            font=self.normal_font,
        )
        self.log_textbox.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        self.progress_bar = ctk.CTkProgressBar(self.log_progress_frame, corner_radius=6)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=5, pady=(0, 5))
        self.progress_bar.set(0)

        # タブを作成
        self.tab_view = ctk.CTkTabview(self.main_frame, corner_radius=8)
        self.tab_view.grid(row=0, column=0, sticky="nsew", pady=(0, 10))

        # タブを追加
        self.tab_resize = self.tab_view.add("リサイズ")
        self.tab_compress = self.tab_view.add("圧縮")
        self.tab_batch = self.tab_view.add("一括処理")
        
        # タブのフォント設定を試行
        try:
            # 方法1: segmented_buttonの各タブにフォントを設定
            if hasattr(self.tab_view, "_segmented_button"):
                for tab_name in ["リサイズ", "圧縮", "一括処理"]:
                    self.tab_view._segmented_button.configure_tab(tab_name, font=self.heading_font)
        except (AttributeError, TclError) as e:
            # エラーの場合はデバッグ情報を記録
            print(f"タブフォント設定エラー: {e}")
            
        # 方法2: タブのテキスト表示に影響する可能性のある他の方法を試行
        try:
            # 全体のtkinterフォントを設定
            self.option_add("*Font", self.heading_font)
        except Exception:
            pass

        # 必要な変数を初期化
        self.resize_value_unit_label = None
        self.resize_quality_text_label = None
        self.resize_quality_slider = None
        self.resize_quality_value_label = None
        self.resize_start_button = None
        self.resize_cancel_button = None
        
        # ログ初期化完了後にタブの中身を作成
        self.create_tab_content_frames()
        
        # 初期化完了後に初期状態を設定
        self.add_log_message("アプリケーションを初期化しました")
        
        # リサイズタブの初期値を設定
        if hasattr(self, "resize_mode_var"):
            self.on_resize_mode_change(self.resize_mode_var.get())
        if hasattr(self, "resize_output_format_var"):
            self.on_output_format_change(self.resize_output_format_var.get())
        
        # ウィンドウを中央に配置
        self.center_window()

    def _select_file(
        self,
        entry_widget,
        title="ファイルを選択",
        filetypes=(
            ("画像ファイル", "*.jpg *.jpeg *.png *.gif *.bmp *.tiff"),
            ("すべてのファイル", "*.*"),
        ),
    ):
        filepath = filedialog.askopenfilename(title=title, filetypes=filetypes)
        if filepath:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, filepath)
            self.add_log_message(f"ファイル選択: {filepath}")

    def _select_directory(self, entry_widget, title="フォルダを選択"):
        """ディレクトリ選択ダイアログを表示し、選択されたパスをエントリーに設定する"""
        dirpath = filedialog.askdirectory(title=title)
        if dirpath:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, dirpath)
            self.add_log_message(f"フォルダ選択: {dirpath}")

    def on_output_format_change(self, selected_format):
        # ログメッセージは初期化完了後のみ表示
        if hasattr(self, "log_textbox") and self.log_textbox is not None:
            self.add_log_message(f"出力フォーマット変更: {selected_format}")
        show_quality = selected_format in ["JPEG", "WEBP"]

        if self.resize_quality_text_label:
            if show_quality:
                self.resize_quality_text_label.grid()
            else:
                self.resize_quality_text_label.grid_remove()

        if self.resize_quality_slider:
            if show_quality:
                self.resize_quality_slider.grid()
            else:
                self.resize_quality_slider.grid_remove()

        if self.resize_quality_value_label:
            if show_quality:
                self.resize_quality_value_label.grid()
                self.update_quality_label(self.resize_quality_var.get())
            else:
                self.resize_quality_value_label.grid_remove()

    def update_quality_label(self, value):
        if self.resize_quality_value_label:
            self.resize_quality_value_label.configure(text=f"{int(value)}")

    def on_resize_mode_change(self, selected_mode):
        # ログメッセージは初期化完了後のみ表示
        if hasattr(self, "log_textbox") and self.log_textbox is not None:
            self.add_log_message(f"リサイズモード変更: {selected_mode}")
        if hasattr(self, "resize_value_unit_label") and self.resize_value_unit_label:
            if selected_mode == "パーセント":
                self.resize_value_unit_label.configure(text="%")
            else:
                self.resize_value_unit_label.configure(text="px")

        if hasattr(self, "resize_value_entry"):
            self.resize_value_entry.delete(0, "end")

    def create_tab_content_frames(self):
        self.resize_tab_content = ctk.CTkFrame(
            self.tab_resize, corner_radius=0, fg_color="transparent"
        )
        self.resize_tab_content.pack(fill="both", expand=True)

        self.resize_tab_content.grid_columnconfigure(0, weight=0)
        self.resize_tab_content.grid_columnconfigure(1, weight=1)
        self.resize_tab_content.grid_columnconfigure(2, weight=0)

        current_row = 0

        ctk.CTkLabel(
            self.resize_tab_content, text="入力ファイル:", font=self.normal_font
        ).grid(row=current_row, column=0, padx=(10, 5), pady=10, sticky="w")
        self.resize_input_file_entry = ctk.CTkEntry(
            self.resize_tab_content, font=self.normal_font
        )
        self.resize_input_file_entry.grid(
            row=current_row, column=1, padx=5, pady=10, sticky="ew"
        )
        self.resize_input_file_button = ctk.CTkButton(
            self.resize_tab_content,
            text="選択...",
            width=80,
            font=self.button_font,
            command=lambda: self._select_file(
                self.resize_input_file_entry, title="入力ファイルを選択"
            ),
        )
        self.resize_input_file_button.grid(
            row=current_row, column=2, padx=(5, 10), pady=10, sticky="e"
        )
        current_row += 1

        ctk.CTkLabel(
            self.resize_tab_content, text="出力先フォルダ:", font=self.normal_font
        ).grid(row=current_row, column=0, padx=(10, 5), pady=10, sticky="w")
        self.resize_output_dir_entry = ctk.CTkEntry(
            self.resize_tab_content, font=self.normal_font
        )
        self.resize_output_dir_entry.grid(
            row=current_row, column=1, padx=5, pady=10, sticky="ew"
        )
        self.resize_output_dir_button = ctk.CTkButton(
            self.resize_tab_content,
            text="選択...",
            width=80,
            font=self.button_font,
            command=lambda: self._select_directory(
                self.resize_output_dir_entry, title="出力先フォルダを選択"
            ),
        )
        self.resize_output_dir_button.grid(
            row=current_row, column=2, padx=(5, 10), pady=10, sticky="e"
        )
        current_row += 1

        resize_settings_frame = ctk.CTkFrame(self.resize_tab_content)
        resize_settings_frame.grid(
            row=current_row, column=0, columnspan=3, padx=10, pady=(10, 0), sticky="ew"
        )
        resize_settings_frame.grid_columnconfigure(1, weight=1)

        rs_current_row = 0
        ctk.CTkLabel(
            resize_settings_frame, text="リサイズモード:", font=self.normal_font
        ).grid(row=rs_current_row, column=0, padx=5, pady=5, sticky="w")
        self.resize_mode_options = ["パーセント", "幅指定", "高さ指定"]
        self.resize_mode_var = ctk.StringVar(value=self.resize_mode_options[0])
        self.resize_mode_menu = ctk.CTkOptionMenu(
            resize_settings_frame,
            values=self.resize_mode_options,
            variable=self.resize_mode_var,
            command=self.on_resize_mode_change,
            font=self.normal_font,
            dropdown_font=self.normal_font,
        )
        self.resize_mode_menu.grid(
            row=rs_current_row, column=1, columnspan=2, padx=5, pady=5, sticky="ew"
        )
        rs_current_row += 1

        ctk.CTkLabel(resize_settings_frame, text="値:", font=self.normal_font).grid(
            row=rs_current_row, column=0, padx=5, pady=5, sticky="w"
        )
        self.resize_value_entry = ctk.CTkEntry(
            resize_settings_frame, font=self.normal_font
        )
        self.resize_value_entry.grid(
            row=rs_current_row, column=1, padx=5, pady=5, sticky="ew"
        )
        self.resize_value_unit_label = ctk.CTkLabel(
            resize_settings_frame, text="%", font=self.normal_font
        )
        self.resize_value_unit_label.grid(
            row=rs_current_row, column=2, padx=(0, 5), pady=5, sticky="w"
        )
        rs_current_row += 1

        self.resize_aspect_ratio_var = ctk.BooleanVar(value=True)
        self.resize_aspect_ratio_checkbox = ctk.CTkCheckBox(
            resize_settings_frame,
            text="アスペクト比を維持",
            variable=self.resize_aspect_ratio_var,
            font=self.normal_font,
        )
        self.resize_aspect_ratio_checkbox.grid(
            row=rs_current_row, column=0, columnspan=3, padx=5, pady=(5, 10), sticky="w"
        )
        rs_current_row += 1

        ctk.CTkLabel(
            resize_settings_frame, text="出力フォーマット:", font=self.normal_font
        ).grid(row=rs_current_row, column=0, padx=5, pady=5, sticky="w")
        self.resize_output_format_options = [
            "元のフォーマットを維持",
            "PNG",
            "JPEG",
            "WEBP",
        ]
        self.resize_output_format_var = ctk.StringVar(
            value=self.resize_output_format_options[0]
        )
        self.resize_output_format_menu = ctk.CTkOptionMenu(
            resize_settings_frame,
            values=self.resize_output_format_options,
            variable=self.resize_output_format_var,
            command=self.on_output_format_change,
            font=self.normal_font,
            dropdown_font=self.normal_font,
        )
        self.resize_output_format_menu.grid(
            row=rs_current_row, column=1, columnspan=2, padx=5, pady=5, sticky="ew"
        )
        rs_current_row += 1

        self.resize_quality_text_label = ctk.CTkLabel(
            resize_settings_frame, text="品質 (JPEG/WEBP):", font=self.normal_font
        )
        self.resize_quality_text_label.grid(
            row=rs_current_row, column=0, padx=5, pady=5, sticky="w"
        )
        self.resize_quality_var = ctk.IntVar(value=85)
        self.resize_quality_slider = ctk.CTkSlider(
            resize_settings_frame,
            from_=1,
            to=100,
            number_of_steps=99,
            variable=self.resize_quality_var,
            command=self.update_quality_label,
        )
        self.resize_quality_slider.grid(
            row=rs_current_row, column=1, padx=5, pady=5, sticky="ew"
        )
        self.resize_quality_value_label = ctk.CTkLabel(
            resize_settings_frame,
            text=str(self.resize_quality_var.get()),
            font=self.normal_font,
        )
        self.resize_quality_value_label.grid(
            row=rs_current_row, column=2, padx=(5, 10), pady=5, sticky="w"
        )
        rs_current_row += 1

        current_row += 1  # resize_settings_frame の分

        action_buttons_frame = ctk.CTkFrame(
            self.resize_tab_content, fg_color="transparent"
        )
        action_buttons_frame.grid(
            row=current_row, column=0, columnspan=3, padx=10, pady=(10, 0), sticky="ew"
        )
        action_buttons_frame.grid_columnconfigure(0, weight=1)
        action_buttons_frame.grid_columnconfigure(1, weight=0)  # Start button column
        action_buttons_frame.grid_columnconfigure(2, weight=0)  # Cancel button column
        action_buttons_frame.grid_columnconfigure(3, weight=1)

        self.resize_start_button = ctk.CTkButton(
            action_buttons_frame,
            text="処理開始",
            command=self.start_resize_process,
            width=120,
            font=self.button_font,
        )
        self.resize_start_button.grid(row=0, column=1, padx=5, pady=5)

        self.resize_cancel_button = ctk.CTkButton(
            action_buttons_frame,
            text="中断",
            command=self.cancel_resize_process,
            state="disabled",
            width=120,
            font=self.button_font,
        )
        self.resize_cancel_button.grid(row=0, column=2, padx=5, pady=5)
        current_row += 1

        # 全ての初期化が完了した後に初期値を設定する

        self.compress_tab_content = ctk.CTkFrame(
            self.tab_compress, corner_radius=0, fg_color="transparent"
        )
        self.compress_tab_content.pack(fill="both", expand=True, padx=5, pady=5)
        ctk.CTkLabel(
            self.compress_tab_content,
            text="圧縮設定はここに配置",
            font=self.normal_font,
        ).pack(pady=20)

        self.batch_tab_content = ctk.CTkFrame(
            self.tab_batch, corner_radius=0, fg_color="transparent"
        )
        self.batch_tab_content.pack(fill="both", expand=True, padx=5, pady=5)
        ctk.CTkLabel(
            self.batch_tab_content,
            text="一括処理設定はここに配置",
            font=self.normal_font,
        ).pack(pady=20)

    def add_log_message(self, message):
        # log_textboxがまだ初期化されていない場合は何もしない
        if not hasattr(self, "log_textbox") or self.log_textbox is None:
            print(f"ログメッセージ（表示不可）: {message}")
            return
            
        try:
            self.log_textbox.configure(state="normal")
            self.log_textbox.insert("end", f"{message}\n")
            self.log_textbox.configure(state="disabled")
            self.log_textbox.see("end")
        except Exception as e:
            print(f"ログ表示エラー: {e} - メッセージ: {message}")

    def update_progress(self, value, pulse=False):
        """
        進捗バーを更新する
        
        Args:
            value: 0.0-1.0の間の進捗値
            pulse: Trueの場合、パルスモードを使用（処理中アニメーション）
        """
        if pulse:
            # パルスモードの場合、少し値を変動させて動きを演出
            current = self.progress_bar.get()
            # 0.45-0.55の間で値を変動させる
            if current < 0.45 or current > 0.55:
                self.progress_bar.set(0.5)
            else:
                # 少しずつ値を変更して動きを作る
                delta = 0.01
                new_value = current + delta if current < 0.55 else current - delta
                self.progress_bar.set(new_value)
        else:
            # 通常モード
            self.progress_bar.set(value)

    def center_window(self):
        """Windows環境でも正しく動作するよう修正した中央配置メソッド"""
        self.update_idletasks()
        
        # サイズが小さすぎる場合は最小値を適用
        width = max(self.winfo_width(), 1000)
        height = max(self.winfo_height(), 800)
        
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        
        # 位置とサイズを設定
        self.geometry(f"{width}x{height}+{x}+{y}")
        
        # 再度サイズを確定させる
        self.update_idletasks()

    def start_resize_process(self):
        self.add_log_message("リサイズ処理を開始します...")
        if self.resize_start_button:
            self.resize_start_button.configure(state="disabled")
        if self.resize_cancel_button:
            self.resize_cancel_button.configure(state="normal")
        self.update_progress(0.1)

        input_file_str = self.resize_input_file_entry.get()
        output_dir_str = self.resize_output_dir_entry.get()
        resize_mode_gui = self.resize_mode_var.get()
        resize_value_str = self.resize_value_entry.get()
        keep_aspect_ratio = self.resize_aspect_ratio_var.get()
        output_format_gui = self.resize_output_format_var.get()
        quality = self.resize_quality_var.get()

        if not input_file_str:
            self.add_log_message(
                "エラー: 入力ファイルが選択されていません。ファイルを選択してください。"
            )
            self.finish_resize_process(success=False)

        core_output_format = {
            "JPEG": "jpeg",
            "PNG": "png",
            "WebP": "webp",
            "入力と同じ": "same",
        }.get(output_format, "same")

        # 出力ファイルパスの生成
        base_name = source_path.stem
        ext = source_path.suffix

        sanitized_stem = sanitize_filename(base_name)
        output_filename = sanitized_stem + ext
        dest_path = dest_dir / output_filename

        self.add_log_message(
            f"フォーマット: {core_output_format}, 品質: {quality if core_output_format in ['jpeg', 'webp'] else 'N/A'}"
        )

        self.update_progress(0.3)
        self.processing_thread = None
        self.cancel_requested = False

        # 処理をスレッドで実行
        try:
            self.add_log_message("画像処理を実行中...")
            self.processing_thread = threading.Thread(
                target=self._process_image_thread,
                args=(
                    source_path,
                    dest_path,
                    core_resize_mode,
                    resize_value,
                    keep_aspect_ratio,
                    core_output_format,
                    quality,
                ),
                daemon=True
            )
            self.processing_thread.start()
            
            # 進捗状況の更新を開始
            self.after(100, self._check_thread_status)
        except Exception as e:
            self.add_log_message(f"画像処理の開始中に予期せぬエラーが発生しました: {e}")
            self.finish_resize_process(success=False, message=str(e))

    def cancel_resize_process(self):
        self.add_log_message("リサイズ処理を中断しています...")
        self.cancel_requested = True
        
        # スレッドは自然に終了するのを待つ
        # 本格的な実装では、もっと洗練された中断機構が必要

    def finish_resize_process(self, success=True, message="処理完了"):
        if success:
            self.add_log_message(f"完了: {message}")
            self.update_progress(1)
        else:
            self.add_log_message(f"エラー/中断: {message}")
            self.update_progress(0)

        if self.resize_start_button:
            self.resize_start_button.configure(state="normal")
        if self.resize_cancel_button:
            self.resize_cancel_button.configure(state="disabled")
            
        # 処理関連の状態をリセット
        self.processing_thread = None
        self.cancel_requested = False
        
    def _process_image_thread(self, source_path, dest_path, resize_mode, resize_value, keep_aspect_ratio, output_format, quality):
        """スレッドで実行される画像処理関数"""
        try:
            # キャンセル要求のチェック
            if self.cancel_requested:
                return
                
            # 実際の画像処理を実行
            success, stats, message = resize_and_compress_image(
                source_path=str(source_path),
                destination_path=str(dest_path),
                resize_mode=resize_mode,
                resize_value=resize_value,
                maintain_aspect_ratio=keep_aspect_ratio,
                output_format=output_format,
                quality=quality
            )
            
            # キャンセル要求のチェック
            if self.cancel_requested:
                return
                
            # 処理結果をメインスレッドに通知
            if success and stats:
                original_size = stats.get('original_size', 0)
                new_size = stats.get('new_size', 0)
                compression_ratio = stats.get('compression_ratio', 0)
                result_message = f"処理完了 - 元サイズ: {format_file_size(original_size)}, 新サイズ: {format_file_size(new_size)}, 圧縮率: {compression_ratio:.1f}%"
            else:
                result_message = message or "処理が完了しましたが、詳細情報はありません"
                
            # UIスレッドでの処理完了通知
            self.after(0, lambda: self.finish_resize_process(success=success, message=result_message))
            
        except Exception as e:
            # エラー発生時の処理
            error_message = f"画像処理中にエラーが発生しました: {e}"
            self.after(0, lambda: self.finish_resize_process(success=False, message=error_message))
            
    def _check_thread_status(self):
        """処理スレッドの状態をチェックし、進捗バーを更新する"""
        if self.processing_thread and self.processing_thread.is_alive():
            # スレッドがまだ実行中の場合、進捗を更新して再度チェックをスケジュール
            if self.cancel_requested:
                self.update_progress(0.5, pulse=True)  # パルスモードで進捗表示
            else:
                # ここでは簡易的な進捗表示。実際には処理の進行状況に応じて値を設定すべき
                current_progress = min(0.9, self.progress_var.get() + 0.1)
                self.update_progress(current_progress)
                
            # 100ms後に再度チェック
            self.after(100, self._check_thread_status)
        elif self.cancel_requested:
            # キャンセルが要求され、スレッドが終了している場合
            self.after(0, lambda: self.finish_resize_process(success=False, message="ユーザーにより中断されました"))


def main():
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
