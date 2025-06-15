# Jupyter Lab用 EAFファイル変換コード（完全版：IPA→tipa変換、morph整列、文分割対応、音声切り出し機能付き）
import xml.etree.ElementTree as ET
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

# オーディオ処理ライブラリのインポート
AUDIO_LIBRARY = None
try:
    import librosa
    import soundfile as sf
    AUDIO_LIBRARY = 'librosa'
    print("✅ librosa + soundfile を使用します")
except ImportError:
    try:
        from pydub import AudioSegment
        AUDIO_LIBRARY = 'pydub'
        print("✅ pydub を使用します")
    except ImportError:
        try:
            import wave
            import numpy as np
            AUDIO_LIBRARY = 'wave'
            print("✅ 標準ライブラリ wave を使用します（WAVファイルのみ対応）")
        except ImportError:
            AUDIO_LIBRARY = None
            print("⚠️ 音声処理ライブラリなし（テキスト変換のみ利用可能）")

def get_desktop_path():
    """デスクトップのパスを取得（OS別対応）"""
    import platform
    
    system = platform.system()
    
    if system == "Windows":
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.exists(desktop):
            desktop = os.path.join(os.path.expanduser("~"), "デスクトップ")
    elif system == "Darwin":
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    else:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.exists(desktop):
            desktop = os.path.expanduser("~")
    
    return desktop

class EAFConverter:
    def __init__(self, eaf_file_path: str, wav_file_path: str = None):
        self.eaf_file_path = eaf_file_path
        self.wav_file_path = wav_file_path
        self.tree = None
        self.root = None
        self.time_slots = {}
        self.tiers = {}
        
        # 音声処理用の属性
        self.audio_data = None
        self.sample_rate = None
        self.audio_available = False
        
    def load_audio(self):
        """音声ファイルを読み込む"""
        if not self.wav_file_path:
            print("音声ファイルが指定されていません。テキスト変換のみ実行します。")
            return False
            
        if not os.path.exists(self.wav_file_path):
            print(f"音声ファイルが見つかりません: {self.wav_file_path}")
            return False
            
        if AUDIO_LIBRARY is None:
            print("オーディオライブラリが利用できません。音声分割機能は使用できません。")
            return False
            
        try:
            if AUDIO_LIBRARY == 'librosa':
                self.audio_data, self.sample_rate = librosa.load(self.wav_file_path, sr=None)
                print(f"音声ファイルを読み込みました: {self.wav_file_path}")
                print(f"サンプリング周波数: {self.sample_rate}Hz, 長さ: {len(self.audio_data)/self.sample_rate:.2f}秒")
                
            elif AUDIO_LIBRARY == 'pydub':
                if self.wav_file_path.lower().endswith('.wav'):
                    self.audio_data = AudioSegment.from_wav(self.wav_file_path)
                elif self.wav_file_path.lower().endswith('.mp3'):
                    self.audio_data = AudioSegment.from_mp3(self.wav_file_path)
                else:
                    self.audio_data = AudioSegment.from_file(self.wav_file_path)
                self.sample_rate = self.audio_data.frame_rate
                print(f"音声ファイルを読み込みました: {self.wav_file_path}")
                print(f"サンプリング周波数: {self.sample_rate}Hz, 長さ: {len(self.audio_data)/1000:.2f}秒")
                
            elif AUDIO_LIBRARY == 'wave':
                with wave.open(self.wav_file_path, 'rb') as wav_file:
                    self.sample_rate = wav_file.getframerate()
                    frames = wav_file.readframes(wav_file.getnframes())
                    self.audio_data = np.frombuffer(frames, dtype=np.int16)
                print(f"音声ファイルを読み込みました: {self.wav_file_path}")
                print(f"サンプリング周波数: {self.sample_rate}Hz, 長さ: {len(self.audio_data)/self.sample_rate:.2f}秒")
                
            self.audio_available = True
            return True
            
        except Exception as e:
            print(f"音声ファイルの読み込みエラー: {e}")
            return False
        
    def parse_eaf(self):
        """EAFファイルを解析する"""
        try:
            self.tree = ET.parse(self.eaf_file_path)
            self.root = self.tree.getroot()
            print(f"EAFファイルを正常に読み込みました: {self.eaf_file_path}")
        except ET.ParseError as e:
            print(f"XMLパースエラー: {e}")
            return False
        except FileNotFoundError:
            print(f"ファイルが見つかりません: {self.eaf_file_path}")
            return False
            
        # タイムスロットを取得
        time_order = self.root.find('TIME_ORDER')
        if time_order is not None:
            for time_slot in time_order.findall('TIME_SLOT'):
                slot_id = time_slot.get('TIME_SLOT_ID')
                time_value = time_slot.get('TIME_VALUE')
                self.time_slots[slot_id] = int(time_value) if time_value else 0
        
        print(f"タイムスロット数: {len(self.time_slots)}")
        
        # ティア情報を表示
        print("\n利用可能なティア:")
        for tier in self.root.findall('TIER'):
            tier_id = tier.get('TIER_ID')
            print(f"  - {tier_id}")
            
        # ティアを取得（ALIGNABLE_ANNOTATIONとREF_ANNOTATION両方をチェック）
        for tier in self.root.findall('TIER'):
            tier_id = tier.get('TIER_ID')
            self.tiers[tier_id] = []
            
            # ALIGNABLE_ANNOTATIONをチェック
            for annotation in tier.findall('.//ALIGNABLE_ANNOTATION'):
                start_id = annotation.get('TIME_SLOT_REF1')
                end_id = annotation.get('TIME_SLOT_REF2')
                value_elem = annotation.find('ANNOTATION_VALUE')
                value = value_elem.text if value_elem is not None else ""
                
                self.tiers[tier_id].append({
                    'start_time': self.time_slots.get(start_id, 0),
                    'end_time': self.time_slots.get(end_id, 0),
                    'value': value.strip() if value else "",
                    'type': 'ALIGNABLE'
                })
            
            # REF_ANNOTATIONもチェック
            for annotation in tier.findall('.//REF_ANNOTATION'):
                ref_id = annotation.get('ANNOTATION_REF')
                value_elem = annotation.find('ANNOTATION_VALUE')
                value = value_elem.text if value_elem is not None else ""
                
                # 参照先のアノテーションの時間を取得
                ref_start, ref_end = self._get_ref_time(ref_id)
                
                self.tiers[tier_id].append({
                    'start_time': ref_start,
                    'end_time': ref_end,
                    'value': value.strip() if value else "",
                    'type': 'REF',
                    'ref_id': ref_id
                })
            
            # 開始時間でソート
            self.tiers[tier_id].sort(key=lambda x: x['start_time'])
            print(f"  {tier_id}: {len(self.tiers[tier_id])} アノテーション")
        
        return True
    
    def _get_ref_time(self, ref_id: str) -> tuple:
        """REF_ANNOTATIONの参照先の時間を取得"""
        # すべてのティアを検索して参照先のアノテーションを見つける
        for tier in self.root.findall('TIER'):
            for annotation in tier.findall('.//ALIGNABLE_ANNOTATION'):
                if annotation.get('ANNOTATION_ID') == ref_id:
                    start_id = annotation.get('TIME_SLOT_REF1')
                    end_id = annotation.get('TIME_SLOT_REF2')
                    return (self.time_slots.get(start_id, 0), self.time_slots.get(end_id, 0))
            
            # REF_ANNOTATIONが他のREF_ANNOTATIONを参照している場合
            for annotation in tier.findall('.//REF_ANNOTATION'):
                if annotation.get('ANNOTATION_ID') == ref_id:
                    nested_ref_id = annotation.get('ANNOTATION_REF')
                    if nested_ref_id:
                        return self._get_ref_time(nested_ref_id)
        
        return (0, 0)
    
    def _split_sentences_by_punctuation(self, text: str, morph: str, gloss: str, translation: str, start_time: int = 0, end_time: int = 0) -> List[Dict]:
        """文末記号（.、?、!）で文を分割し、時間情報も保持"""
        # 文末記号を検出するパターン
        sentence_pattern = r'([.?!]+)'
        
        # text層を文末記号で分割
        text_parts = re.split(sentence_pattern, text)
        
        sentences = []
        current_text = ""
        
        # morph層とgloss層をスペースで分割
        morph_words = morph.split() if morph else []
        gloss_words = gloss.split() if gloss else []
        
        morph_idx = 0
        gloss_idx = 0
        
        # 時間計算用
        total_chars = len(text.replace('.', '').replace('?', '').replace('!', ''))
        current_chars = 0
        
        for part in text_parts:
            # 文末記号かどうかチェック
            is_punctuation = bool(re.match(r'^[.?!]+$', part))
            
            if is_punctuation:
                # 文末記号の場合
                current_text += part
                
                # 現在の文を完成させる
                if current_text.strip():
                    # この文に対応するmorph数を計算
                    clean_text = current_text.replace('.', '').replace('?', '').replace('!', '')
                    text_words = clean_text.split()
                    num_morphs = 0
                    for word in text_words:
                        # =や-で分割された形態素数を数える
                        morphs_in_word = len(re.split(r'[=-]', word))
                        num_morphs += morphs_in_word
                    
                    # 対応するmorphとglossを取得
                    sent_morphs = morph_words[morph_idx:morph_idx + num_morphs] if morph_idx < len(morph_words) else []
                    sent_glosses = gloss_words[gloss_idx:gloss_idx + num_morphs] if gloss_idx < len(gloss_words) else []
                    
                    # 時間の推定計算
                    sentence_chars = len(clean_text)
                    if total_chars > 0 and start_time != end_time:
                        char_ratio = sentence_chars / total_chars
                        duration = end_time - start_time
                        sentence_start = start_time + int((current_chars / total_chars) * duration)
                        sentence_end = sentence_start + int(char_ratio * duration)
                    else:
                        sentence_start = start_time
                        sentence_end = end_time
                    
                    sentences.append({
                        'text': current_text.strip(),
                        'morph': ' '.join(sent_morphs),
                        'gloss': ' '.join(sent_glosses),
                        'translation': translation,  # 翻訳は全体で共有
                        'start_time': sentence_start,
                        'end_time': sentence_end
                    })
                    
                    # インデックスを更新
                    morph_idx += num_morphs
                    gloss_idx += num_morphs
                    current_chars += sentence_chars
                    current_text = ""
            
            elif part.strip():
                # 通常のテキストの場合
                current_text += part
        
        # 残りのテキストがある場合
        if current_text.strip():
            # 残りのmorphとglossを使用
            remaining_morphs = morph_words[morph_idx:] if morph_idx < len(morph_words) else []
            remaining_glosses = gloss_words[gloss_idx:] if gloss_idx < len(gloss_words) else []
            
            # 残りの時間計算
            sentence_chars = len(current_text.replace('.', '').replace('?', '').replace('!', ''))
            if total_chars > 0 and start_time != end_time:
                char_ratio = sentence_chars / total_chars
                duration = end_time - start_time
                sentence_start = start_time + int((current_chars / total_chars) * duration)
                sentence_end = sentence_start + int(char_ratio * duration)
            else:
                sentence_start = start_time
                sentence_end = end_time
            
            sentences.append({
                'text': current_text.strip(),
                'morph': ' '.join(remaining_morphs),
                'gloss': ' '.join(remaining_glosses),
                'translation': translation,
                'start_time': sentence_start,
                'end_time': sentence_end
            })
        
        return sentences if sentences else [{
            'text': text, 
            'morph': morph, 
            'gloss': gloss, 
            'translation': translation,
            'start_time': start_time,
            'end_time': end_time
        }]
    
    def extract_sentences(self, tier_names: Dict[str, str] = None) -> List[Dict]:
        """文ごとにtext, morph, gloss, translation, 時間情報を抽出"""
        # デフォルトのティア名（実際のティア名に合わせて修正）
        if tier_names is None:
            tier_names = {
                'text': 'text@KS',
                'morph': 'morph@KS', 
                'gloss': 'gloss@KS',
                'translation': 'translation@KS'  # @TSに修正
            }
        
        sentences = []
        
        # 各ティアから対応する区間を見つける
        text_tier = self.tiers.get(tier_names['text'], [])
        morph_tier = self.tiers.get(tier_names['morph'], [])
        gloss_tier = self.tiers.get(tier_names['gloss'], [])
        translation_tier = self.tiers.get(tier_names['translation'], [])
        
        print(f"\n抽出対象:")
        print(f"  text: {len(text_tier)} 項目")
        print(f"  morph: {len(morph_tier)} 項目")
        print(f"  gloss: {len(gloss_tier)} 項目")
        print(f"  translation: {len(translation_tier)} 項目")
        
        for i, text_annotation in enumerate(text_tier):
            if not text_annotation['value']:
                continue
                
            start_time = text_annotation['start_time']
            end_time = text_annotation['end_time']
            
            # 対応するmorph, gloss, translationを見つける
            morph = self._find_overlapping_annotation(morph_tier, start_time, end_time)
            gloss = self._find_overlapping_annotation(gloss_tier, start_time, end_time)
            translation = self._find_overlapping_annotation(translation_tier, start_time, end_time)
            
            # 文末記号で分割（時間情報付き）
            split_sentences = self._split_sentences_by_punctuation(
                text_annotation['value'], morph, gloss, translation, start_time, end_time
            )
            
            sentences.extend(split_sentences)
        
        print(f"\n抽出された文数: {len(sentences)}")
        return sentences
    
    def _find_overlapping_annotation(self, tier_data: List[Dict], start_time: int, end_time: int) -> str:
        """指定された時間範囲と重複するアノテーションを見つけて結合"""
        matching_annotations = []
        
        for annotation in tier_data:
            # 時間範囲が重複するかチェック
            overlap_start = max(annotation['start_time'], start_time)
            overlap_end = min(annotation['end_time'], end_time)
            
            if overlap_start < overlap_end or (annotation['start_time'] == start_time and annotation['end_time'] == end_time):
                # 重複がある、または完全一致の場合
                matching_annotations.append(annotation)
        
        # 重複するアノテーションを時間順にソートして結合
        matching_annotations.sort(key=lambda x: x['start_time'])
        return ' '.join([ann['value'] for ann in matching_annotations if ann['value']])
    
    def save_audio_segment(self, start_ms: int, end_ms: int, output_path: str, padding_ms: int = 100):
        """指定された時間範囲の音声を保存"""
        if not self.audio_available:
            return False
            
        try:
            # パディングを追加（前後に少し余裕を持たせる）
            padded_start = max(0, start_ms - padding_ms)
            
            if AUDIO_LIBRARY == 'librosa':
                # ミリ秒をサンプル数に変換
                start_sample = int((padded_start / 1000.0) * self.sample_rate)
                end_sample = int((end_ms / 1000.0) * self.sample_rate)
                padded_end_sample = min(len(self.audio_data), end_sample + int((padding_ms / 1000.0) * self.sample_rate))
                
                # 音声セグメントを切り出し
                audio_segment = self.audio_data[start_sample:padded_end_sample]
                
                # ファイルに保存
                sf.write(output_path, audio_segment, self.sample_rate)
                
            elif AUDIO_LIBRARY == 'pydub':
                padded_end = end_ms + padding_ms
                
                # 音声セグメントを切り出し
                audio_segment = self.audio_data[padded_start:padded_end]
                
                # ファイルに保存
                audio_segment.export(output_path, format="wav")
                
            elif AUDIO_LIBRARY == 'wave':
                # ミリ秒をサンプル数に変換
                start_sample = int((padded_start / 1000.0) * self.sample_rate)
                end_sample = int((end_ms / 1000.0) * self.sample_rate)
                padded_end_sample = min(len(self.audio_data), end_sample + int((padding_ms / 1000.0) * self.sample_rate))
                
                # 音声セグメントを切り出し
                audio_segment = self.audio_data[start_sample:padded_end_sample]
                
                # WAVファイルとして保存
                with wave.open(output_path, 'wb') as wav_out:
                    wav_out.setnchannels(1)  # モノラル
                    wav_out.setsampwidth(2)  # 16bit
                    wav_out.setframerate(self.sample_rate)
                    wav_out.writeframes(audio_segment.tobytes())
            
            return True
            
        except Exception as e:
            print(f"音声保存エラー: {e}")
            return False
    
    def split_audio_to_desktop(self, sentences: List[Dict], folder_name: str = None, 
                              padding_ms: int = 100, create_zip: bool = False):
        """分割された文の音声をデスクトップに保存（テキストファイルも含む）"""
        if not self.audio_available:
            print("音声データが利用できません。音声分割はスキップされます。")
            return None
            
        # デスクトップパスを取得
        desktop_path = get_desktop_path()
        print(f"📁 デスクトップパス: {desktop_path}")
        
        # 出力フォルダ名を決定
        if not folder_name:
            base_name = Path(self.eaf_file_path).stem
            folder_name = f"{base_name}_sentences"
        
        # デスクトップに出力ディレクトリを作成
        output_path = Path(desktop_path) / folder_name
        if output_path.exists():
            # 既存フォルダがある場合はバックアップ
            import time
            timestamp = int(time.time())
            backup_path = Path(desktop_path) / f"{folder_name}_backup_{timestamp}"
            shutil.move(str(output_path), str(backup_path))
            print(f"📦 既存フォルダをバックアップ: {backup_path}")
        
        output_path.mkdir(parents=True, exist_ok=True)
        
        if not sentences:
            print("分割する文が見つかりませんでした")
            return None
        
        saved_files = []
        
        # 各文に対して音声を切り出し
        for i, sentence in enumerate(sentences, 1):
            if not sentence.get('start_time') or not sentence.get('end_time'):
                print(f"⚠️ 文 {i} に時間情報がありません。スキップします。")
                continue
                
            # ファイル名を生成（番号付き）
            safe_text = re.sub(r'[^\w\s-]', '', sentence['text'][:30])  # 安全なファイル名
            safe_text = re.sub(r'\s+', '_', safe_text.strip())
            filename = f"{i:03d}_{safe_text}.wav"
            output_file = output_path / filename
            
            # 音声を保存
            success = self.save_audio_segment(
                sentence['start_time'], 
                sentence['end_time'], 
                str(output_file),
                padding_ms
            )
            
            if success:
                saved_files.append({
                    'number': i,
                    'text': sentence['text'],
                    'start_time': sentence['start_time'],
                    'end_time': sentence['end_time'],
                    'duration': sentence['end_time'] - sentence['start_time'],
                    'file_path': str(output_file)
                })
                print(f"✅ 保存完了: {filename} ({sentence['start_time']}ms - {sentence['end_time']}ms)")
            else:
                print(f"❌ 保存失敗: {filename}")
        
        # GB4E形式のTeXファイルを作成
        print("📝 GB4E形式のTeXファイルを作成中...")
        gb4e_content = self.to_gb4e_format(sentences)
        gb4e_file = output_path / 'sentences_gb4e.tex'
        with open(gb4e_file, 'w', encoding='utf-8', newline='\n') as f:
            f.write(gb4e_content)
        print(f"✅ GB4E形式保存: {gb4e_file.name}")
        
        # DOC形式のTXTファイルを作成
        print("📄 DOC形式のTXTファイルを作成中...")
        doc_content = self.to_doc_format(sentences)
        doc_file = output_path / 'sentences_doc.txt'
        with open(doc_file, 'w', encoding='utf-8') as f:
            f.write(doc_content)
        print(f"✅ DOC形式保存: {doc_file.name}")
        
        # 結果をまとめたテキストファイルを作成
        summary_file = output_path / 'audio_summary.txt'
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("音声ファイル分割結果\n")
            f.write("="*50 + "\n\n")
            f.write(f"元ファイル: {self.eaf_file_path}\n")
            f.write(f"音声ファイル: {self.wav_file_path}\n")
            f.write(f"総文数: {len(saved_files)}\n")
            f.write(f"保存場所: {output_path}\n\n")
            f.write("📁 生成ファイル:\n")
            f.write(f"  - GB4E形式: {gb4e_file.name}\n")
            f.write(f"  - DOC形式: {doc_file.name}\n")
            f.write(f"  - 音声ファイル: {len(saved_files)}個\n\n")
            
            for file_info in saved_files:
                f.write(f"{file_info['number']:03d}. {file_info['text']}\n")
                f.write(f"     時間: {file_info['start_time']}ms - {file_info['end_time']}ms "
                       f"(長さ: {file_info['duration']}ms)\n")
                f.write(f"     ファイル: {Path(file_info['file_path']).name}\n\n")
        
        # READMEファイルを作成
        readme_file = output_path / 'README.txt'
        with open(readme_file, 'w', encoding='utf-8') as f:
            f.write("EAFファイル音声分割結果\n")
            f.write("="*30 + "\n\n")
            f.write("📁 このフォルダには以下のファイルが含まれています:\n\n")
            f.write("🎵 音声ファイル:\n")
            f.write(f"  - {len(saved_files)}個の分割された音声ファイル (001_*.wav ～ {len(saved_files):03d}_*.wav)\n")
            f.write("  - 各ファイルは文単位で分割されています\n\n")
            f.write("📝 テキストファイル:\n")
            f.write(f"  - {gb4e_file.name}: LaTeX用gb4e形式の例文集\n")
            f.write(f"  - {doc_file.name}: プレーンテキスト形式の例文集\n")
            f.write(f"  - {summary_file.name}: 詳細な分割情報\n")
            f.write(f"  - {readme_file.name}: この説明ファイル\n\n")
            f.write("💡 使用方法:\n")
            f.write("  - 音声ファイル: 各文の音声を個別に再生可能\n")
            f.write("  - GB4Eファイル: LaTeXでコンパイルして言語学論文用の例文集を作成\n")
            f.write("  - DOCファイル: そのまま文書に貼り付け可能\n\n")
            f.write(f"📅 作成日時: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"🔧 元ファイル: {Path(self.eaf_file_path).name}\n")
        
        # ZIPファイルを作成する場合
        zip_file_path = None
        if create_zip and saved_files:
            zip_file_path = Path(desktop_path) / f"{folder_name}.zip"
            try:
                with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in output_path.rglob('*'):
                        if file_path.is_file():
                            arcname = file_path.relative_to(output_path)
                            zipf.write(file_path, arcname)
                
                print(f"📦 ZIPファイル作成完了: {zip_file_path}")
            except Exception as e:
                print(f"❌ ZIP作成エラー: {e}")
                zip_file_path = None
        
        if saved_files:
            print(f"\n🎉 音声分割完了!")
            print(f"🎵 保存された音声ファイル数: {len(saved_files)}")
            print(f"📝 GB4E形式ファイル: {gb4e_file.name}")
            print(f"📄 DOC形式ファイル: {doc_file.name}")
            print(f"📁 保存場所: {output_path}")
            print(f"📋 詳細情報: {summary_file.name}")
            print(f"💡 使い方: {readme_file.name}")
            if zip_file_path:
                print(f"📦 ZIPファイル: {zip_file_path}")
        
        return {
            'saved_files': saved_files,
            'output_path': str(output_path),
            'gb4e_file': str(gb4e_file),
            'doc_file': str(doc_file),
            'summary_file': str(summary_file),
            'readme_file': str(readme_file),
            'zip_file': str(zip_file_path) if zip_file_path else None,
            'total_files': len(saved_files)
        }
    
    def _convert_ipa_to_tipa(self, text: str) -> str:
        """IPA文字をtipaパッケージの形式に変換"""
        if not text:
            return text
            
        # IPA文字とtipaコマンドの対応表（{}を追加して区切りを明確化）
        ipa_to_tipa = {
            'ɨ': '\\textbari{}',
            'ɯ': '\\textturnm{}',
            'ɛ': '\\textepsilon{}',
            'ɔ': '\\textopeno{}',
            'æ': '\\textae{}',
            'ɑ': '\\textscripta{}',
            'ɒ': '\\textturnscripta{}',
            'ə': '\\textschwa{}',
            'ɪ': '\\textsci{}',
            'ʊ': '\\textupsilon{}',
            'ʃ': '\\textesh{}',
            'ʒ': '\\textyogh{}',
            'θ': '\\texttheta{}',
            'ð': '\\texteth{}',
            'ŋ': '\\texteng{}',
            'ɲ': '\\textltailn{}',
            'ɳ': '\\textrtailn{}',
            'ɱ': '\\textltailm{}',
            'ɾ': '\\textfishhookr{}',
            'ɽ': '\\textrtailr{}',
            'ɻ': '\\textturnr{}',
            'ɭ': '\\textrtaill{}',
            'ʎ': '\\textturny{}',
            'ʈ': '\\textrtailt{}',
            'ɖ': '\\textrtaild{}',
            'ʂ': '\\textrtails{}',
            'ʐ': '\\textrtailz{}',
            'ɕ': '\\textctc{}',
            'ʑ': '\\textctj{}',
            'ç': '\\textccedilla{}',
            'ʝ': '\\textctj{}',
            'ɣ': '\\textgamma{}',
            'χ': '\\textchi{}',
            'ʁ': '\\textinvscr{}',
            'ħ': '\\textcrh{}',
            'ʕ': '\\textrevglotstop{}',
            'ʔ': '\\textglotstop{}',
            'ɸ': '\\textphi{}',
            'β': '\\textbeta{}',
            'ʋ': '\\textscriptv{}',
            'ɹ': '\\textturnr{}',
            'ɰ': '\\textturnmrleg{}',
            'ɺ': '\\textlhti{}',
            'ɢ': '\\textscg{}',
            'ʛ': '\\texthtg{}',
            'ʄ': '\\texthtbardotlessjdotlessj{}',
            'ɠ': '\\texthtg{}',
            'ɡ': '\\textscg{}',
            'ː': '\\textlengthmark{}',
            'ˈ': '\\textprimstress{}',
            'ˌ': '\\textsecstress{}',
            'ʲ': '\\textpal{}',
            'ʷ': '\\textlab{}',
            'ʰ': '\\textsuperscript{h}',
            'ⁿ': '\\textsuperscript{n}',
            'ʼ': '\\textglotstop{}',
        }
        
        result = text
        for ipa_char, tipa_command in ipa_to_tipa.items():
            result = result.replace(ipa_char, tipa_command)
        
        return result
    
    def _align_morphs_with_text(self, text: str, morph: str) -> str:
        """text層の区切り文字（=や-）に基づいてmorph層を再配置"""
        if not text or not morph:
            return morph
        
        # morph層をスペースで分割
        morph_list = morph.split()
        if not morph_list:
            return morph
        
        # text層を単語に分割
        text_words = text.split()
        result_parts = []
        morph_idx = 0
        
        for word in text_words:
            # 単語内の形態素境界を見つける（=, -）
            # 形態素境界で分割（区切り文字も保持）
            segments = re.split(r'([=-])', word)
            word_morphs = []
            
            for segment in segments:
                if segment in ['=', '-']:
                    # 区切り文字はそのまま保持
                    continue
                elif segment.strip():  # 空でないセグメント
                    if morph_idx < len(morph_list):
                        word_morphs.append(morph_list[morph_idx])
                        morph_idx += 1
            
            # 単語内の形態素を区切り文字で結合
            if word_morphs:
                # 元の単語の区切り文字パターンを復元
                morphs_with_delims = []
                morph_pos = 0
                
                for segment in segments:
                    if segment in ['=', '-']:
                        morphs_with_delims.append(segment)
                    elif segment.strip() and morph_pos < len(word_morphs):
                        morphs_with_delims.append(word_morphs[morph_pos])
                        morph_pos += 1
                
                result_parts.append(''.join(morphs_with_delims))
        
        return ' '.join(result_parts)
    
    def _align_words_for_doc(self, text_line: str, gloss_line: str) -> tuple:
        """doc形式用に単語の開始位置を揃える"""
        if not text_line or not gloss_line:
            return text_line, gloss_line
        
        text_words = text_line.split()
        gloss_words = gloss_line.split()
        
        # より正確な文字幅計算
        def char_width(s):
            import unicodedata
            width = 0
            for char in s:
                # Unicode文字カテゴリーを使用してより正確に判定
                if unicodedata.east_asian_width(char) in ('F', 'W'):
                    # 全角文字（Full width, Wide）
                    width += 2
                elif unicodedata.east_asian_width(char) in ('H', 'Na', 'N'):
                    # 半角文字（Half width, Narrow, Neutral）
                    width += 1
                else:
                    # その他（A=Ambiguous）は環境依存だが、ここでは1として扱う
                    width += 1
            return width
        
        # 単語数が異なる場合は短い方に合わせる
        min_len = min(len(text_words), len(gloss_words))
        if len(text_words) != len(gloss_words):
            print(f"警告: 単語数が一致しません (text: {len(text_words)}, gloss: {len(gloss_words)})")
        
        aligned_text_parts = []
        aligned_gloss_parts = []
        
        for i in range(min_len):
            text_word = text_words[i]
            gloss_word = gloss_words[i]
            
            text_width = char_width(text_word)
            gloss_width = char_width(gloss_word)
            
            # 両方の単語の最大幅を計算（最低2文字のスペースを確保）
            max_width = max(text_width, gloss_width) + 2
            
            # パディングを追加
            text_padding = max_width - text_width
            gloss_padding = max_width - gloss_width
            
            if i < min_len - 1:  # 最後の単語でない場合
                aligned_text_parts.append(text_word + ' ' * text_padding)
                aligned_gloss_parts.append(gloss_word + ' ' * gloss_padding)
            else:  # 最後の単語
                aligned_text_parts.append(text_word)
                aligned_gloss_parts.append(gloss_word)
        
        # 余った単語がある場合の処理
        if len(text_words) > min_len:
            remaining_text = ' '.join(text_words[min_len:])
            aligned_text_parts.append(' ' + remaining_text)
        
        if len(gloss_words) > min_len:
            remaining_gloss = ' '.join(gloss_words[min_len:])
            aligned_gloss_parts.append(' ' + remaining_gloss)
        
        return ''.join(aligned_text_parts), ''.join(aligned_gloss_parts)
    
    def to_gb4e_format(self, sentences: List[Dict]) -> str:
        """gb4e形式に変換（3段グロス：text, gloss, translation）"""
        output = []
        
        # LaTeX用のヘッダーを追加
        output.append("% UTF-8エンコーディング用設定")
        output.append("% \\usepackage[utf8]{inputenc}")
        output.append("% \\usepackage{CJKutf8}")
        output.append("% \\usepackage{gb4e}")
        output.append("% \\usepackage{tipa}")
        output.append("")
        
        for i, sentence in enumerate(sentences, 1):
            if not sentence['text']:
                continue
                
            output.append("\\begin{exe}")
            output.append("\\ex")
            
            # 1段目: text（IPAをtipaに変換）
            text_tipa = self._convert_ipa_to_tipa(sentence['text'])
            output.append(f"\\gll {text_tipa}\\\\")
            
            # 2段目: gloss（区切り文字に基づく整列）
            if sentence['gloss']:
                # gloss層をtext層の区切り文字に基づいて再配置
                aligned_gloss = self._align_morphs_with_text(sentence['text'], sentence['gloss'])
                output.append(f"     {aligned_gloss}\\\\")
            else:
                output.append("     \\\\")
            
            # 3段目: translation
            if sentence['translation']:
                output.append(f"\\glt {sentence['translation']}")
            else:
                output.append("\\glt")
            
            output.append("\\end{exe}")
            output.append("")
        
        return "\n".join(output)
    
    def _convert_tipa_back_to_ipa(self, text: str) -> str:
        """tipaコマンドを元のIPA文字に戻す"""
        if not text:
            return text
            
        result = text
        result = result.replace('\\textbari{}', 'ɨ')
        result = result.replace('\\textturnm{}', 'ɯ')
        result = result.replace('\\textepsilon{}', 'ɛ')
        result = result.replace('\\textopeno{}', 'ɔ')
        result = result.replace('\\textae{}', 'æ')
        result = result.replace('\\textscripta{}', 'ɑ')
        result = result.replace('\\textturnscripta{}', 'ɒ')
        result = result.replace('\\textschwa{}', 'ə')
        result = result.replace('\\textsci{}', 'ɪ')
        result = result.replace('\\textupsilon{}', 'ʊ')
        result = result.replace('\\textesh{}', 'ʃ')
        result = result.replace('\\textyogh{}', 'ʒ')
        result = result.replace('\\texttheta{}', 'θ')
        result = result.replace('\\texteth{}', 'ð')
        result = result.replace('\\texteng{}', 'ŋ')
        result = result.replace('\\textltailn{}', 'ɲ')
        result = result.replace('\\textrtailn{}', 'ɳ')
        result = result.replace('\\textltailm{}', 'ɱ')
        result = result.replace('\\textfishhookr{}', 'ɾ')
        result = result.replace('\\textrtailr{}', 'ɽ')
        result = result.replace('\\textturnr{}', 'ɻ')
        result = result.replace('\\textrtaill{}', 'ɭ')
        result = result.replace('\\textturny{}', 'ʎ')
        result = result.replace('\\textrtailt{}', 'ʈ')
        result = result.replace('\\textrtaild{}', 'ɖ')
        result = result.replace('\\textrtails{}', 'ʂ')
        result = result.replace('\\textrtailz{}', 'ʐ')
        result = result.replace('\\textctc{}', 'ɕ')
        result = result.replace('\\textctj{}', 'ʑ')
        result = result.replace('\\textccedilla{}', 'ç')
        result = result.replace('\\textgamma{}', 'ɣ')
        result = result.replace('\\textchi{}', 'χ')
        result = result.replace('\\textinvscr{}', 'ʁ')
        result = result.replace('\\textcrh{}', 'ħ')
        result = result.replace('\\textrevglotstop{}', 'ʕ')
        result = result.replace('\\textglotstop{}', 'ʔ')
        result = result.replace('\\textphi{}', 'ɸ')
        result = result.replace('\\textbeta{}', 'β')
        result = result.replace('\\textscriptv{}', 'ʋ')
        result = result.replace('\\textturnmrleg{}', 'ɰ')
        result = result.replace('\\textlhti{}', 'ɺ')
        result = result.replace('\\textscg{}', 'ɢ')
        result = result.replace('\\texthtg{}', 'ʛ')
        result = result.replace('\\texthtbardotlessjdotlessj{}', 'ʄ')
        result = result.replace('\\textbardotlessj{}', 'ɟ')
        result = result.replace('\\textlengthmark{}', 'ː')
        result = result.replace('\\textprimstress{}', 'ˈ')
        result = result.replace('\\textsecstress{}', 'ˌ')
        result = result.replace('\\textpal{}', 'ʲ')
        result = result.replace('\\textlab{}', 'ʷ')
        result = result.replace('\\textsuperscript{h}', 'ʰ')
        result = result.replace('\\textsuperscript{n}', 'ⁿ')
        
        return result
    
    def to_doc_format(self, sentences: List[Dict], debug: bool = False) -> str:
        """doc形式（gb4e形式をベースにコマンド類を除去、IPA文字を復元、インデント調整）"""
        output = []
        
        for i, sentence in enumerate(sentences, 1):
            if not sentence['text']:
                continue
                
            # 例文番号
            output.append(f"({i})")
            
            # 1段目: text（IPAをtipaに変換してから元に戻す）
            text_tipa = self._convert_ipa_to_tipa(sentence['text'])
            text_original = self._convert_tipa_back_to_ipa(text_tipa)
            
            # 2段目: gloss（区切り文字に基づく整列）
            if sentence['gloss']:
                # gloss層をtext層の区切り文字に基づいて再配置
                aligned_gloss = self._align_morphs_with_text(sentence['text'], sentence['gloss'])
                
                if debug:
                    print(f"\n--- 例文 {i} のデバッグ情報 ---")
                    print(f"元のtext: '{sentence['text']}'")
                    print(f"元のgloss: '{sentence['gloss']}'")
                    print(f"整列後gloss: '{aligned_gloss}'")
                    print(f"最終text: '{text_original}'")
                
                # 単語の開始位置を揃える
                aligned_text, aligned_gloss_final = self._align_words_for_doc(text_original, aligned_gloss)
                
                if debug:
                    print(f"位置調整後text: '{aligned_text}'")
                    print(f"位置調整後gloss: '{aligned_gloss_final}'")
                    print(f"text単語数: {len(text_original.split())}")
                    print(f"gloss単語数: {len(aligned_gloss.split())}")
                
                output.append(aligned_text)
                output.append(aligned_gloss_final)
            else:
                output.append(text_original)
                output.append("")
            
            # 3段目: translation（シングルクォートも除去）
            if sentence['translation']:
                output.append(sentence['translation'])
            else:
                output.append("")
            
            output.append("")
        
        return "\n".join(output)

# 診断関数
def diagnose_eaf_file(eaf_filename, wav_filename=None):
    """EAFファイルの構造を詳しく調べる"""
    converter = EAFConverter(eaf_filename, wav_filename)
    if not converter.parse_eaf():
        return
    
    if wav_filename:
        print("\n音声ファイルのチェック...")
        converter.load_audio()
    
    print("\n=== 詳細なティア情報 ===")
    for tier_name, annotations in converter.tiers.items():
        print(f"\nティア: {tier_name}")
        print(f"  アノテーション数: {len(annotations)}")
        
        # 最初の3つのアノテーションを表示
        for i, ann in enumerate(annotations[:3]):
            ann_type = ann.get('type', 'UNKNOWN')
            print(f"  [{i+1}] ({ann_type}) 時間: {ann['start_time']}-{ann['end_time']}")
            content = ann['value'][:100] + '...' if len(ann['value']) > 100 else ann['value']
            print(f"      内容: '{content}'")
        
        if len(annotations) > 3:
            print(f"  ... (他 {len(annotations)-3} 個)")

# 使用例
def convert_eaf_file(eaf_filename, wav_filename=None, tier_names=None, output_format='both', 
                    debug=False, save_audio=True, audio_folder_name=None, 
                    audio_padding_ms=100, create_zip=False):
    """
    EAFファイルを変換する関数（音声切り出し機能付き）
    
    Args:
        eaf_filename: EAFファイル名
        wav_filename: WAVファイル名（音声切り出し用、任意）
        tier_names: ティア名の辞書 {'text': '実際のティア名', ...}
        output_format: 'gb4e', 'doc', 'both'
        debug: デバッグ情報を表示するかどうか
        save_audio: 音声分割を実行するかどうか
        audio_folder_name: 音声保存用フォルダ名
        audio_padding_ms: 音声ファイルの前後パディング（ミリ秒）
        create_zip: 音声ファイルのZIPを作成するかどうか
    
    Returns:
        変換結果の辞書
    """
    
    # ファイルの存在確認
    if not os.path.exists(eaf_filename):
        print(f"ファイルが見つかりません: {eaf_filename}")
        print("\n現在のディレクトリのファイル:")
        for file in os.listdir('.'):
            if file.endswith('.eaf'):
                print(f"  {file}")
        return None
    
    if wav_filename and not os.path.exists(wav_filename):
        print(f"音声ファイルが見つかりません: {wav_filename}")
        print("テキスト変換のみ実行します。")
        wav_filename = None
    
    # 変換実行
    converter = EAFConverter(eaf_filename, wav_filename)
    
    if not converter.parse_eaf():
        return None
    
    # 音声ファイルがある場合は読み込み
    if wav_filename:
        print("音声ファイルを読み込み中...")
        converter.load_audio()
    
    sentences = converter.extract_sentences(tier_names)
    
    if not sentences:
        print("変換可能な文が見つかりませんでした。")
        return None
    
    result = {
        'sentences': sentences,
        'eaf_file': eaf_filename,
        'wav_file': wav_filename,
        'gb4e_file': None,
        'doc_file': None,
        'audio_result': None
    }
    
    # テキスト変換結果を表示・保存
    print("\n" + "="*70)
    
    if output_format in ['gb4e', 'both']:
        print("GB4E形式:")
        print("-" * 40)
        gb4e_content = converter.to_gb4e_format(sentences)
        print(gb4e_content)
        
        # ファイルに保存（UTF-8 BOMなし）
        gb4e_filename = f"{eaf_filename}_gb4e.tex"
        with open(gb4e_filename, 'w', encoding='utf-8', newline='\n') as f:
            f.write(gb4e_content)
        print(f"\n✅ GB4E形式を保存しました: {gb4e_filename}")
        result['gb4e_file'] = gb4e_filename
    
    if output_format in ['both']:
        print("\n" + "="*70)
    
    if output_format in ['doc', 'both']:
        print("DOC形式:")
        print("-" * 40)
        doc_content = converter.to_doc_format(sentences, debug=debug)
        print(doc_content)
        
        # ファイルに保存
        doc_filename = f"{eaf_filename}_doc.txt"
        with open(doc_filename, 'w', encoding='utf-8') as f:
            f.write(doc_content)
        print(f"\n✅ DOC形式を保存しました: {doc_filename}")
        result['doc_file'] = doc_filename
    
    # 音声分割を実行
    if save_audio and wav_filename and converter.audio_available:
        print("\n" + "="*70)
        print("🎵 音声分割を実行中...")
        audio_result = converter.split_audio_to_desktop(
            sentences, audio_folder_name, audio_padding_ms, create_zip
        )
        result['audio_result'] = audio_result
    elif save_audio and wav_filename:
        print("\n音声分割: オーディオライブラリが利用できないため、スキップされました")
    elif save_audio:
        print("\n音声分割: WAVファイルが指定されていないため、スキップされました")
    
    print(f"\n🎉 変換完了!")
    print(f"📊 抽出された文数: {len(sentences)}")
    if result['gb4e_file']:
        print(f"📝 GB4E形式: {result['gb4e_file']}")
    if result['doc_file']:
        print(f"📄 DOC形式: {result['doc_file']}")
    if result['audio_result']:
        print(f"🎵 音声ファイル: {result['audio_result']['total_files']}個")
        print(f"📁 音声保存場所: {result['audio_result']['output_path']}")
    
    return result

# 実行方法の説明
print("=== EAFファイル変換ツール（修正版・音声切り出し機能付き） ===")
print("機能:")
print("- IPA文字を自動的にtipaコマンドに変換")
print("- gloss層をtext層の区切り文字（=, -）に基づいて整列")
print("- 文末記号（., ?, !）での自動文分割")
print("- gb4e形式：LaTeX用の完全なフォーマット")
print("- doc形式：gb4e形式をベースにコマンド類を除去したプレーンテキスト（インデント調整付き）")
print("- 音声分割：文単位で音声ファイルを分割してデスクトップに保存")
print("- ZIPファイル作成：音声ファイルをまとめてZIP圧縮")
print()

if AUDIO_LIBRARY:
    print("使用方法:")
    print("1. テキスト変換のみ:")
    print("   result = convert_eaf_file('your_file.eaf')")
    print()
    print("2. テキスト変換＋音声分割:")
    print("   result = convert_eaf_file('your_file.eaf', 'your_file.wav')")
    print()
    print("3. 完全カスタム:")
    print("   result = convert_eaf_file('your_file.eaf', 'your_file.wav',")
    print("                            output_format='both',")
    print("                            save_audio=True,")
    print("                            audio_folder_name='My_Audio_Project',")
    print("                            create_zip=True)")
    print()
    print("4. デバッグモード:")
    print("   result = convert_eaf_file('your_file.eaf', debug=True)")
    print()
    print("5. 診断実行:")
    print("   diagnose_eaf_file('your_file.eaf', 'your_file.wav')")
else:
    print("音声処理ライブラリが見つかりません。テキスト変換のみ利用可能です。")
    print("音声分割機能を使用するには以下をインストールしてください:")
    print("  pip install librosa soundfile  # 推奨")
    print("  pip install pydub              # 軽量版")
    print()
    print("使用方法（テキスト変換のみ）:")
    print("1. 基本的な変換:")
    print("   result = convert_eaf_file('your_file.eaf')")
    print()
    print("2. デバッグモード:")
    print("   result = convert_eaf_file('your_file.eaf', debug=True)")
    print()
    print("3. 診断実行:")
    print("   diagnose_eaf_file('your_file.eaf')")