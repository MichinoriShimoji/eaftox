# Jupyter Lab用 EAFファイル変換コード（完全版：音声切り出し機能付き、デスクトップ保存対応）
import xml.etree.ElementTree as ET
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Dict, List, Optional
import time

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
            
        # ティアを取得
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
        for tier in self.root.findall('TIER'):
            for annotation in tier.findall('.//ALIGNABLE_ANNOTATION'):
                if annotation.get('ANNOTATION_ID') == ref_id:
                    start_id = annotation.get('TIME_SLOT_REF1')
                    end_id = annotation.get('TIME_SLOT_REF2')
                    return (self.time_slots.get(start_id, 0), self.time_slots.get(end_id, 0))
            
            for annotation in tier.findall('.//REF_ANNOTATION'):
                if annotation.get('ANNOTATION_ID') == ref_id:
                    nested_ref_id = annotation.get('ANNOTATION_REF')
                    if nested_ref_id:
                        return self._get_ref_time(nested_ref_id)
        
        return (0, 0)
    
    def _split_sentences_by_punctuation(self, text: str, morph: str, gloss: str, translation: str, start_time: int = 0, end_time: int = 0) -> List[Dict]:
        """文末記号（.、?、!）で文を分割し、時間情報も保持"""
        sentence_pattern = r'([.?!]+)'
        text_parts = re.split(sentence_pattern, text)
        
        sentences = []
        current_text = ""
        
        morph_words = morph.split() if morph else []
        gloss_words = gloss.split() if gloss else []
        
        morph_idx = 0
        gloss_idx = 0
        
        total_chars = len(text.replace('.', '').replace('?', '').replace('!', ''))
        current_chars = 0
        
        for part in text_parts:
            is_punctuation = bool(re.match(r'^[.?!]+$', part))
            
            if is_punctuation:
                current_text += part
                
                if current_text.strip():
                    clean_text = current_text.replace('.', '').replace('?', '').replace('!', '')
                    text_words = clean_text.split()
                    num_morphs = 0
                    for word in text_words:
                        morphs_in_word = len(re.split(r'[=-]', word))
                        num_morphs += morphs_in_word
                    
                    sent_morphs = morph_words[morph_idx:morph_idx + num_morphs] if morph_idx < len(morph_words) else []
                    sent_glosses = gloss_words[gloss_idx:gloss_idx + num_morphs] if gloss_idx < len(gloss_words) else []
                    
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
                        'translation': translation,
                        'start_time': sentence_start,
                        'end_time': sentence_end
                    })
                    
                    morph_idx += num_morphs
                    gloss_idx += num_morphs
                    current_chars += sentence_chars
                    current_text = ""
            
            elif part.strip():
                current_text += part
        
        if current_text.strip():
            remaining_morphs = morph_words[morph_idx:] if morph_idx < len(morph_words) else []
            remaining_glosses = gloss_words[gloss_idx:] if gloss_idx < len(gloss_words) else []
            
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
        if tier_names is None:
            tier_names = {
                'text': 'text@KS',
                'morph': 'morph@KS', 
                'gloss': 'gloss@KS',
                'translation': 'translation@KS'
            }
        
        sentences = []
        
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
            
            morph = self._find_overlapping_annotation(morph_tier, start_time, end_time)
            gloss = self._find_overlapping_annotation(gloss_tier, start_time, end_time)
            translation = self._find_overlapping_annotation(translation_tier, start_time, end_time)
            
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
            overlap_start = max(annotation['start_time'], start_time)
            overlap_end = min(annotation['end_time'], end_time)
            
            if overlap_start < overlap_end or (annotation['start_time'] == start_time and annotation['end_time'] == end_time):
                matching_annotations.append(annotation)
        
        matching_annotations.sort(key=lambda x: x['start_time'])
        return ' '.join([ann['value'] for ann in matching_annotations if ann['value']])
    
    def save_audio_segment(self, start_ms: int, end_ms: int, output_path: str, padding_ms: int = 100):
        """指定された時間範囲の音声を保存"""
        if not self.audio_available:
            return False
            
        try:
            padded_start = max(0, start_ms - padding_ms)
            
            if AUDIO_LIBRARY == 'librosa':
                start_sample = int((padded_start / 1000.0) * self.sample_rate)
                end_sample = int((end_ms / 1000.0) * self.sample_rate)
                padded_end_sample = min(len(self.audio_data), end_sample + int((padding_ms / 1000.0) * self.sample_rate))
                
                audio_segment = self.audio_data[start_sample:padded_end_sample]
                sf.write(output_path, audio_segment, self.sample_rate)
                
            elif AUDIO_LIBRARY == 'pydub':
                padded_end = end_ms + padding_ms
                audio_segment = self.audio_data[padded_start:padded_end]
                audio_segment.export(output_path, format="wav")
                
            elif AUDIO_LIBRARY == 'wave':
                start_sample = int((padded_start / 1000.0) * self.sample_rate)
                end_sample = int((end_ms / 1000.0) * self.sample_rate)
                padded_end_sample = min(len(self.audio_data), end_sample + int((padding_ms / 1000.0) * self.sample_rate))
                
                audio_segment = self.audio_data[start_sample:padded_end_sample]
                
                with wave.open(output_path, 'wb') as wav_out:
                    wav_out.setnchannels(1)
                    wav_out.setsampwidth(2)
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
            
        desktop_path = get_desktop_path()
        print(f"📁 デスクトップパス: {desktop_path}")
        
        if not folder_name:
            base_name = Path(self.eaf_file_path).stem
            folder_name = f"{base_name}_sentences"
        
        output_path = Path(desktop_path) / folder_name
        if output_path.exists():
            timestamp = int(time.time())
            backup_path = Path(desktop_path) / f"{folder_name}_backup_{timestamp}"
            shutil.move(str(output_path), str(backup_path))
            print(f"📦 既存フォルダをバックアップ: {backup_path}")
        
        output_path.mkdir(parents=True, exist_ok=True)
        
        if not sentences:
            print("分割する文が見つかりませんでした")
            return None
        
        saved_files = []
        
        for i, sentence in enumerate(sentences, 1):
            if not sentence.get('start_time') or not sentence.get('end_time'):
                print(f"⚠️ 文 {i} に時間情報がありません。スキップします。")
                continue
                
            safe_text = re.sub(r'[^\w\s-]', '', sentence['text'][:30])
            safe_text = re.sub(r'\s+', '_', safe_text.strip())
            filename = f"{i:03d}_{safe_text}.wav"
            output_file = output_path / filename
            
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
        print("📝 GB4E形式（Leipzig.sty対応）のTeXファイルを作成中...")
        gb4e_content = self.to_gb4e_format(sentences)
        gb4e_file = output_path / 'sentences_gb4e_leipzig.tex'
        with open(gb4e_file, 'w', encoding='utf-8', newline='\n') as f:
            f.write(gb4e_content)
        print(f"✅ GB4E形式（Leipzig.sty対応）保存: {gb4e_file.name}")
        
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
            f.write(f"  - GB4E形式（Leipzig.sty対応）: {gb4e_file.name}\n")
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
            f.write("EAFファイル音声分割結果（Leipzig.sty対応版）\n")
            f.write("="*40 + "\n\n")
            f.write("📁 このフォルダには以下のファイルが含まれています:\n\n")
            f.write("🎵 音声ファイル:\n")
            f.write(f"  - {len(saved_files)}個の分割された音声ファイル (001_*.wav ～ {len(saved_files):03d}_*.wav)\n")
            f.write("  - 各ファイルは文単位で分割されています\n\n")
            f.write("📝 テキストファイル:\n")
            f.write(f"  - {gb4e_file.name}: LaTeX用gb4e形式の例文集（Leipzig.sty対応）\n")
            f.write(f"  - {doc_file.name}: プレーンテキスト形式の例文集\n")
            f.write(f"  - {summary_file.name}: 詳細な分割情報\n")
            f.write(f"  - {readme_file.name}: この説明ファイル\n\n")
            f.write("💡 使用方法:\n")
            f.write("  - 音声ファイル: 各文の音声を個別に再生可能\n")
            f.write("  - GB4Eファイル: LaTeXでコンパイルして言語学論文用の例文集を作成\n")
            f.write("    \\usepackage{leipzig} を忘れずに追加してください\n")
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
            print(f"📝 GB4E形式ファイル（Leipzig.sty対応）: {gb4e_file.name}")
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
    
    def _align_morphs_with_text(self, text: str, morph: str) -> str:
        """text層の区切り文字（=や-）に基づいてmorph層を再配置"""
        if not text or not morph:
            return morph
        
        morph_list = morph.split()
        if not morph_list:
            return morph
        
        text_words = text.split()
        result_parts = []
        morph_idx = 0
        
        for word in text_words:
            segments = re.split(r'([=-])', word)
            word_morphs = []
            
            for segment in segments:
                if segment in ['=', '-']:
                    continue
                elif segment.strip():
                    if morph_idx < len(morph_list):
                        word_morphs.append(morph_list[morph_idx])
                        morph_idx += 1
            
            if word_morphs:
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
        
        def char_width(s):
            import unicodedata
            width = 0
            for char in s:
                if unicodedata.east_asian_width(char) in ('F', 'W'):
                    width += 2
                elif unicodedata.east_asian_width(char) in ('H', 'Na', 'N'):
                    width += 1
                else:
                    width += 1
            return width
        
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
            
            max_width = max(text_width, gloss_width) + 2
            
            text_padding = max_width - text_width
            gloss_padding = max_width - gloss_width
            
            if i < min_len - 1:
                aligned_text_parts.append(text_word + ' ' * text_padding)
                aligned_gloss_parts.append(gloss_word + ' ' * gloss_padding)
            else:
                aligned_text_parts.append(text_word)
                aligned_gloss_parts.append(gloss_word)
        
        if len(text_words) > min_len:
            remaining_text = ' '.join(text_words[min_len:])
            aligned_text_parts.append(' ' + remaining_text)
        
        if len(gloss_words) > min_len:
            remaining_gloss = ' '.join(gloss_words[min_len:])
            aligned_gloss_parts.append(' ' + remaining_gloss)
        
        return ''.join(aligned_text_parts), ''.join(aligned_gloss_parts)

    def _convert_leipzig_glosses(self, gloss_text: str) -> str:
        """Leipzig.styの規則に従って大文字英字の文法形態素記号を変換"""
        if not gloss_text:
            return gloss_text
        
        # バックスラッシュを二重にしてエスケープ
        leipzig_mapping = {
            'NOM': '\\\\textsc{nom}', 'ACC': '\\\\textsc{acc}', 'GEN': '\\\\textsc{gen}',
            'DAT': '\\\\textsc{dat}', 'ABL': '\\\\textsc{abl}', 'LOC': '\\\\textsc{loc}',
            'PST': '\\\\textsc{pst}', 'PRS': '\\\\textsc{prs}', 'FUT': '\\\\textsc{fut}',
            'NPST': '\\\\textsc{npst}', 'PFV': '\\\\textsc{pfv}', 'IPFV': '\\\\textsc{ipfv}',
            'SG': '\\\\textsc{sg}', 'PL': '\\\\textsc{pl}', 'DU': '\\\\textsc{du}',
            'COP': '\\\\textsc{cop}', 'AUX': '\\\\textsc{aux}', 'NEG': '\\\\textsc{neg}',
            'FOC': '\\\\textsc{foc}', 'TOP': '\\\\textsc{top}', 'EMPH': '\\\\textsc{emph}',
            'HS': '\\\\textsc{hs}', 'EVID': '\\\\textsc{evid}', 'QUOT': '\\\\textsc{quot}',
            'SFP': '\\\\textsc{sfp}', 'CAS': '\\\\textsc{cas}', 'PART': '\\\\textsc{part}',
            'CAUS': '\\\\textsc{caus}', 'PASS': '\\\\textsc{pass}', 'REFL': '\\\\textsc{refl}',
            'Q': '\\\\textsc{q}', 'CLF': '\\\\textsc{clf}', 'DET': '\\\\textsc{det}',
            'DEF': '\\\\textsc{def}', 'INDEF': '\\\\textsc{indef}', 'COM': '\\\\textsc{com}'
        }
        
        result = gloss_text
        
        # より慎重に変換：単語境界を厳密にチェック
        for original, replacement in leipzig_mapping.items():
            pattern = r'(?<![A-Za-z])' + re.escape(original) + r'(?![A-Za-z])'
            result = re.sub(pattern, replacement, result)
        
        # 残った連続する大文字を自動変換（前後に英数字がない場合のみ）
        def convert_unknown_caps(match):
            caps_text = match.group(0)
            return f'\\\\textsc{{{caps_text.lower()}}}'
        
        result = re.sub(r'(?<![A-Za-z])[A-Z]{2,}(?![A-Za-z])', convert_unknown_caps, result)
        
        return result
    
    def _convert_leipzig_back_to_plain(self, text: str) -> str:
        """Leipzig.styのsmallcapsコマンドを元の小型大文字に戻す"""
        if not text:
            return text
        
        def convert_textsc_to_smallcaps(match):
            content = match.group(1)
            # 小型大文字に変換（実際にはUnicodeの小型大文字文字を使用）
            smallcap_mapping = {
                'nom': 'ɴᴏᴍ', 'acc': 'ᴀᴄᴄ', 'gen': 'ɢᴇɴ',
                'dat': 'ᴅᴀᴛ', 'abl': 'ᴀʙʟ', 'loc': 'ʟᴏᴄ',
                'pst': 'ᴘsᴛ', 'prs': 'ᴘʀs', 'fut': 'ꜰᴜᴛ',
                'npst': 'ɴᴘsᴛ', 'pfv': 'ᴘꜰᴠ', 'ipfv': 'ɪᴘꜰᴠ',
                'sg': 'sɢ', 'pl': 'ᴘʟ', 'du': 'ᴅᴜ',
                'cop': 'ᴄᴏᴘ', 'aux': 'ᴀᴜx', 'neg': 'ɴᴇɢ',
                'foc': 'ꜰᴏᴄ', 'top': 'ᴛᴏᴘ', 'emph': 'ᴇᴍᴘʜ',
                'hs': 'ʜs', 'evid': 'ᴇᴠɪᴅ', 'quot': 'Qᴜᴏᴛ',
                'sfp': 'sꜰᴘ', 'cas': 'ᴄᴀs', 'part': 'ᴘᴀʀᴛ',
                'caus': 'ᴄᴀᴜs', 'pass': 'ᴘᴀss', 'refl': 'ʀᴇꜰʟ',
                'q': 'Q', 'clf': 'ᴄʟꜰ', 'det': 'ᴅᴇᴛ',
                'def': 'ᴅᴇꜰ', 'indef': 'ɪɴᴅᴇꜰ', 'com': 'ᴄᴏᴍ'
            }
            
            return smallcap_mapping.get(content.lower(), content.upper())
        
        # \\textsc{...} を小型大文字に変換
        result = re.sub(r'\\textsc\{([^}]+)\}', convert_textsc_to_smallcaps, text)
        
        # 通常の大文字（2文字以上）も小型大文字に変換
        def convert_caps_to_smallcaps(match):
            caps_text = match.group(0)
            result_chars = []
            for char in caps_text:
                # 個別文字のマッピング
                char_mapping = {
                    'A': 'ᴀ', 'B': 'ʙ', 'C': 'ᴄ', 'D': 'ᴅ', 'E': 'ᴇ', 'F': 'ꜰ',
                    'G': 'ɢ', 'H': 'ʜ', 'I': 'ɪ', 'J': 'ᴊ', 'K': 'ᴋ', 'L': 'ʟ',
                    'M': 'ᴍ', 'N': 'ɴ', 'O': 'ᴏ', 'P': 'ᴘ', 'Q': 'Q', 'R': 'ʀ',
                    'S': 's', 'T': 'ᴛ', 'U': 'ᴜ', 'V': 'ᴠ', 'W': 'ᴡ', 'X': 'x',
                    'Y': 'ʏ', 'Z': 'ᴢ'
                }
                result_chars.append(char_mapping.get(char, char))
            return ''.join(result_chars)
        
        # 連続する大文字（2文字以上）を小型大文字に変換
        result = re.sub(r'(?<![A-Za-z])[A-Z]{2,}(?![A-Za-z])', convert_caps_to_smallcaps, result)
        
        return result
    
    def to_gb4e_format(self, sentences: List[Dict]) -> str:
        """gb4e形式に変換（Leipzig.sty対応、IPA→tipa変換付き）"""
        output = []
        
        output.append("% UTF-8エンコーディング用設定")
        output.append("% \\usepackage[utf8]{inputenc}")
        output.append("% \\usepackage{CJKutf8}")
        output.append("% \\usepackage{gb4e}")
        output.append("% \\usepackage{tipa}")
        output.append("% \\usepackage{leipzig}  % Leipzig.styパッケージ")
        output.append("")
        output.append("% Leipzig.styの使用により、大文字の文法記号が自動的に小文字のスモールキャップスに変換されます")
        output.append("% IPA文字は自動的にtipaコマンドに変換されます")
        output.append("")
        
        for i, sentence in enumerate(sentences, 1):
            if not sentence['text']:
                continue
                
            output.append("\\begin{exe}")
            output.append("\\ex")
            
            # 1段目: text（IPAをtipaに変換）
            text_tipa = self._convert_ipa_to_tipa(sentence['text'])
            output.append(f"\\gll {text_tipa}\\\\")
            
            # 2段目: gloss（形態素整列 + Leipzig.sty変換）
            if sentence['gloss']:
                # text層の境界記号に基づいてgloss層を整列
                aligned_gloss = self._align_morphs_with_text(sentence['text'], sentence['gloss'])
                leipzig_gloss = self._convert_leipzig_glosses(aligned_gloss)
                # 二重バックスラッシュを単一に修正
                leipzig_gloss = leipzig_gloss.replace('\\\\', '\\')
                output.append(f"     {leipzig_gloss}\\\\")
            else:
                output.append("     \\\\")
            
            # 3段目: translation（デバッグ情報付き）
            if sentence.get('translation') and sentence['translation'].strip():
                output.append(f"\\glt {sentence['translation']}")
            else:
                # 翻訳がない場合の情報表示
                if not sentence.get('translation'):
                    print(f"警告: 文 {i} に翻訳データがありません")
                else:
                    print(f"警告: 文 {i} の翻訳が空です: '{sentence['translation']}'")
                output.append("\\glt")
            
            output.append("\\end{exe}")
            output.append("")
        
        return "\n".join(output)
    
    def to_doc_format(self, sentences: List[Dict], debug: bool = False) -> str:
        """doc形式（プレーンテキスト、IPA文字復元、小型大文字変換、インデント調整付き）"""
        output = []
        
        for i, sentence in enumerate(sentences, 1):
            if not sentence['text']:
                continue
                
            output.append(f"({i})")
            
            # 1段目: text（IPAをtipaに変換してから元に戻す）
            text_tipa = self._convert_ipa_to_tipa(sentence['text'])
            text_original = self._convert_tipa_back_to_ipa(text_tipa)
            
            # 2段目: gloss（区切り文字に基づく整列 + Leipzig.sty変換後に小型大文字に戻す）
            if sentence['gloss']:
                aligned_gloss = self._align_morphs_with_text(sentence['text'], sentence['gloss'])
                leipzig_gloss = self._convert_leipzig_glosses(aligned_gloss)
                # 二重バックスラッシュを単一に修正
                leipzig_gloss = leipzig_gloss.replace('\\\\', '\\')
                plain_gloss = self._convert_leipzig_back_to_plain(leipzig_gloss)
                
                if debug:
                    print(f"\n--- 例文 {i} のデバッグ情報 ---")
                    print(f"元のtext: '{sentence['text']}'")
                    print(f"元のgloss: '{sentence['gloss']}'")
                    print(f"整列後gloss: '{aligned_gloss}'")
                    print(f"Leipzig変換後: '{leipzig_gloss}'")
                    print(f"最終text: '{text_original}'")
                    print(f"最終gloss: '{plain_gloss}'")
                
                # 単語の開始位置を揃える
                aligned_text, aligned_gloss_final = self._align_words_for_doc(text_original, plain_gloss)
                
                if debug:
                    print(f"位置調整後text: '{aligned_text}'")
                    print(f"位置調整後gloss: '{aligned_gloss_final}'")
                    print(f"text単語数: {len(text_original.split())}")
                    print(f"gloss単語数: {len(plain_gloss.split())}")
                
                output.append(aligned_text)
                output.append(aligned_gloss_final)
            else:
                output.append(text_original)
                output.append("")
            
            # 3段目: translation
            if sentence['translation']:
                output.append(sentence['translation'])
            else:
                output.append("")
            
            output.append("")
        
        return "\n".join(output)

# Leipzig.styテスト関数を改良
def test_leipzig_conversion():
    """Leipzig.sty変換機能のテスト"""
    converter = EAFConverter("dummy.eaf")
    
    test_glosses = [
        "FOC",
        "GEN", 
        "COM",
        "PST",
        "HS",
        "昔=FOC 貧しい=GEN",
        "UNKNOWN CUSTOM"
    ]
    
    print("=== Leipzig.sty変換テスト ===")
    print("入力 → 出力")
    print("-" * 50)
    
    for gloss in test_glosses:
        converted = converter._convert_leipzig_glosses(gloss)
        print(f"'{gloss}' → '{converted}'")
        
        # バックスラッシュの確認
        if '\\textsc' in converted:
            print("  ✅ \\textsc が正しく含まれています")
        elif 'extsc' in converted:
            print("  ❌ \\t が欠けています！")
    
    print("\n" + "="*50)
    print("変換規則:")
    print("- 大文字の文法記号は \\textsc{小文字} に変換")
    print("- 数字(1,2,3)はそのまま保持")
    print("- 未定義の大文字記号も自動変換")

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
        
        for i, ann in enumerate(annotations[:3]):
            ann_type = ann.get('type', 'UNKNOWN')
            print(f"  [{i+1}] ({ann_type}) 時間: {ann['start_time']}-{ann['end_time']}")
            content = ann['value'][:200] + '...' if len(ann['value']) > 200 else ann['value']
            print(f"      内容: '{content}'")
            # 境界記号の確認
            if '=' in ann['value'] or '-' in ann['value']:
                print(f"      *** 境界記号を検出: = や - が含まれています ***")
        
        if len(annotations) > 3:
            print(f"  ... (他 {len(annotations)-3} 個)")

# 抽出内容確認用の関数を追加
def debug_sentence_extraction(eaf_filename, tier_names=None):
    """文抽出プロセスを詳しく確認"""
    converter = EAFConverter(eaf_filename)
    if not converter.parse_eaf():
        return
    
    sentences = converter.extract_sentences(tier_names)
    
    print("\n=== 抽出された文の詳細確認 ===")
    for i, sentence in enumerate(sentences[:3], 1):  # 最初の3文のみ
        print(f"\n--- 文 {i} ---")
        print(f"text: '{sentence['text']}'")
        print(f"morph: '{sentence['morph']}'")
        print(f"gloss: '{sentence['gloss']}'")
        print(f"translation: '{sentence['translation']}'")
        print(f"時間: {sentence['start_time']}ms - {sentence['end_time']}ms")
        
        # 境界記号の確認
        if '=' in sentence['text'] or '-' in sentence['text']:
            print("  *** text層に境界記号あり ***")
        if '=' in sentence['gloss'] or '-' in sentence['gloss']:
            print("  *** gloss層に境界記号あり ***")
        if '=' in sentence['morph'] or '-' in sentence['morph']:
            print("  *** morph層に境界記号あり ***")
        
        # 翻訳の詳細確認
        if not sentence.get('translation'):
            print("  ❌ translation キーが存在しません")
        elif not sentence['translation']:
            print("  ❌ translation が空文字列です")
        elif not sentence['translation'].strip():
            print("  ❌ translation が空白のみです")
        else:
            print(f"  ✅ translation OK: '{sentence['translation']}'")
    
    if len(sentences) > 3:
        print(f"\n... (他 {len(sentences)-3} 文)")
    
    # ティア名の確認も追加
    if tier_names:
        print(f"\n=== 使用中のティア名 ===")
        for key, value in tier_names.items():
            print(f"{key}: '{value}'")
    else:
        print(f"\n=== デフォルトティア名使用 ===")
        default_tiers = {
            'text': 'text@KS',
            'morph': 'morph@KS', 
            'gloss': 'gloss@KS',
            'translation': 'translation@KS'
        }
        for key, value in default_tiers.items():
            print(f"{key}: '{value}'")

# morph整列のテスト関数を追加
def test_morph_alignment():
    """morph整列機能のテスト"""
    converter = EAFConverter("dummy.eaf")
    
    test_cases = [
        {
            'text': 'nkjaan=du kiban-kiban=nu',
            'morph': '昔 FOC 貧しい 貧しい GEN'
        },
        {
            'text': 'pZtu=tu ujaki=ti=nu',
            'morph': '人 COM 豊かな QUOT GEN'
        },
        {
            'text': 'a-tar=ca',
            'morph': 'COP PST HS'
        }
    ]
    
    print("=== morph整列テスト ===")
    for i, case in enumerate(test_cases, 1):
        print(f"\n--- テストケース {i} ---")
        print(f"入力text: '{case['text']}'")
        print(f"入力morph: '{case['morph']}'")
        
        result = converter._align_morphs_with_text(case['text'], case['morph'])
        print(f"整列結果: '{result}'")
        
        leipzig_result = converter._convert_leipzig_glosses(result)
        print(f"Leipzig変換: '{leipzig_result}'")

# 変換関数
def convert_eaf_file(eaf_filename, wav_filename=None, tier_names=None, output_format='both',
                    debug=False, save_audio=True, audio_folder_name=None,
                    audio_padding_ms=100, create_zip=False):
    """
    EAFファイルを変換する関数（Leipzig.sty対応＋音声切り出し機能付き）
    
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
    
    converter = EAFConverter(eaf_filename, wav_filename)
    
    if not converter.parse_eaf():
        return None
    
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
    
    print("\n" + "="*70)
    
    if output_format in ['gb4e', 'both']:
        print("GB4E形式 (Leipzig.sty対応):")
        print("-" * 40)
        gb4e_content = converter.to_gb4e_format(sentences)
        print(gb4e_content)
        
        gb4e_filename = f"{eaf_filename}_gb4e_leipzig.tex"
        with open(gb4e_filename, 'w', encoding='utf-8', newline='\n') as f:
            f.write(gb4e_content)
        print(f"\n✅ GB4E形式(Leipzig.sty対応)を保存しました: {gb4e_filename}")
        result['gb4e_file'] = gb4e_filename
    
    if output_format in ['both']:
        print("\n" + "="*70)
    
    if output_format in ['doc', 'both']:
        print("DOC形式:")
        print("-" * 40)
        doc_content = converter.to_doc_format(sentences)
        print(doc_content)
        
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
        print(f"📝 GB4E形式（Leipzig.sty対応）: {result['gb4e_file']}")
    if result['doc_file']:
        print(f"📄 DOC形式: {result['doc_file']}")
    if result['audio_result']:
        print(f"🎵 音声ファイル: {result['audio_result']['total_files']}個")
        print(f"📁 音声保存場所: {result['audio_result']['output_path']}")
    
    return result

# 実行方法の説明
print("=== EAFファイル変換ツール（Leipzig.sty対応＋音声切り出し機能付き） ===")
print("新機能:")
print("✅ Leipzig.styパッケージに対応した文法記号の自動変換") 
print("✅ NOM → \\textsc{nom}, PST → \\textsc{pst} など")
print("✅ 未定義の大文字記号も自動でsmallcapsに変換")
print("✅ IPA文字をtipaコマンドに自動変換（ɛ → \\textepsilon{}, ŋ → \\texteng{} など）")
print("✅ 音声分割：文単位で音声ファイルを分割してデスクトップに保存")
print("✅ ZIPファイル作成：音声ファイルをまとめてZIP圧縮")
print("✅ 文末記号での自動文分割（時間情報付き）")
print("✅ 形態素整列：text層の区切り文字に基づいてmorph/gloss層を再配置")
print()

if AUDIO_LIBRARY:
    print("使用方法:")
    print("1. テキスト変換のみ:")
    print("   result = convert_eaf_file('your_file.eaf')")
    print()
    print("2. テキスト変換＋音声分割:")
    print("   result = convert_eaf_file('your_file.eaf', 'your_file.wav')")
    print()
    print("3. カスタムティア名を指定:")
    print("   tier_names = {")
    print("       'text': 'text@Speaker1',      # 実際のtext層の名前")
    print("       'morph': 'morph@Speaker1',    # 実際のmorph層の名前")
    print("       'gloss': 'gloss@Speaker1',    # 実際のgloss層の名前")
    print("       'translation': 'translation@Speaker1'  # 実際のtranslation層の名前")
    print("   }")
    print("   result = convert_eaf_file('your_file.eaf', 'your_file.wav',")
    print("                            tier_names=tier_names)")
    print()
    print("4. 完全カスタム（ティア名指定＋全オプション）:")
    print("   tier_names = {'text': 'text@MyName', 'gloss': 'gloss@MyName', ...}")
    print("   result = convert_eaf_file('your_file.eaf', 'your_file.wav',")
    print("                            tier_names=tier_names,")
    print("                            output_format='both',")
    print("                            save_audio=True,")
    print("                            audio_folder_name='My_Audio_Project',")
    print("                            create_zip=True)")
    print()
    print("5. Leipzig.sty変換テスト:")
    print("   test_leipzig_conversion()")
    print()
    print("6. morph整列テスト:")
    print("   test_morph_alignment()")
    print()
    print("7. 文抽出デバッグ:")
    print("   debug_sentence_extraction('your_file.eaf')")
    print()
    print("8. 診断実行（ティア名確認に便利）:")
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
    print("2. カスタムティア名を指定:")
    print("   tier_names = {")
    print("       'text': 'text@Speaker1',")
    print("       'morph': 'morph@Speaker1',")
    print("       'gloss': 'gloss@Speaker1',")
    print("       'translation': 'translation@Speaker1'")
    print("   }")
    print("   result = convert_eaf_file('your_file.eaf', tier_names=tier_names)")
    print()
    print("3. Leipzig.sty変換テスト:")
    print("   test_leipzig_conversion()")
    print()
    print("4. morph整列テスト:")
    print("   test_morph_alignment()")
    print()
    print("5. 文抽出デバッグ:")
    print("   debug_sentence_extraction('your_file.eaf')")
    print()
    print("6. 診断実行（ティア名確認に便利）:")
    print("   diagnose_eaf_file('your_file.eaf')")

print()
print("💡 ティア名の確認方法:")
print("EAFファイルのティア名を確認するには:")
print("   diagnose_eaf_file('your_file.eaf')")
print("これで利用可能な全ティア名が表示されます。")
print()
print("📝 よくあるティア名のパターン:")
print("- text@話者名 (例: text@KS, text@Speaker1)")
print("- morph@話者名 (例: morph@KS, morph@Speaker1)")
print("- gloss@話者名 (例: gloss@KS, gloss@Speaker1)")
print("- translation@話者名 (例: translation@KS, translation@Speaker1)")
print()
print("📝 LaTeX文書での使用方法:")
print("\\documentclass{article}")
print("\\usepackage[utf8]{inputenc}")
print("\\usepackage{CJKutf8}")
print("\\usepackage{gb4e}")
print("\\usepackage{tipa}")
print("\\usepackage{leipzig}  % Leipzig.styパッケージ")
print()
print("\\begin{document}")
print("\\input{your_file.eaf_gb4e_leipzig.tex}")
print("\\end{document}")
