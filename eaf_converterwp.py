import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
import time
import shutil

# オーディオライブラリの検出
AUDIO_LIBRARY = None
try:
    import librosa
    import soundfile as sf
    AUDIO_LIBRARY = 'librosa'
    print("使用オーディオライブラリ: librosa + soundfile")
except ImportError:
    try:
        from pydub import AudioSegment
        AUDIO_LIBRARY = 'pydub'
        print("使用オーディオライブラリ: pydub")
    except ImportError:
        try:
            import wave
            import numpy as np
            AUDIO_LIBRARY = 'wave'
            print("使用オーディオライブラリ: wave + numpy")
        except ImportError:
            print("オーディオライブラリが見つかりません。音声機能は無効です。")

def get_desktop_path():
    home = Path.home()
    desktop_candidates = [home / "Desktop", home / "デスクトップ", home / "desktop"]
    for path in desktop_candidates:
        if path.exists():
            return str(path)
    return str(home)

class SimpleEAFConverter:
    def __init__(self, eaf_file_path, wav_file_path=None):
        self.eaf_file_path = eaf_file_path
        self.wav_file_path = wav_file_path
        self.time_slots = {}
        self.annotations = {}
        self.audio_available = False
        self.audio_data = None
        self.sample_rate = None
    
    def parse_eaf(self):
        try:
            tree = ET.parse(self.eaf_file_path)
            root = tree.getroot()
            
            # タイムスロット解析
            for time_slot in root.findall('.//TIME_SLOT'):
                slot_id = time_slot.get('TIME_SLOT_ID')
                time_value = time_slot.get('TIME_VALUE')
                if time_value:
                    self.time_slots[slot_id] = int(time_value)
            
            print(f"EAFファイル読み込み: {self.eaf_file_path}")
            print(f"タイムスロット数: {len(self.time_slots)}")
            
            # アノテーション解析
            all_annotations = {}
            
            for tier in root.findall('.//TIER'):
                tier_id = tier.get('TIER_ID')
                annotations = []
                
                # ALIGNABLE_ANNOTATION
                for annotation in tier.findall('.//ALIGNABLE_ANNOTATION'):
                    annotation_id = annotation.get('ANNOTATION_ID')
                    start_slot = annotation.get('TIME_SLOT_REF1')
                    end_slot = annotation.get('TIME_SLOT_REF2')
                    
                    if start_slot in self.time_slots and end_slot in self.time_slots:
                        value_elem = annotation.find('ANNOTATION_VALUE')
                        value = value_elem.text if value_elem is not None and value_elem.text else ""
                        
                        ann_data = {
                            'start_time': self.time_slots[start_slot],
                            'end_time': self.time_slots[end_slot],
                            'value': value.strip(),
                            'annotation_id': annotation_id
                        }
                        annotations.append(ann_data)
                        all_annotations[annotation_id] = ann_data
                
                # REF_ANNOTATION
                for annotation in tier.findall('.//REF_ANNOTATION'):
                    annotation_id = annotation.get('ANNOTATION_ID')
                    ref_id = annotation.get('ANNOTATION_REF')
                    
                    if ref_id in all_annotations:
                        ref_ann = all_annotations[ref_id]
                        value_elem = annotation.find('ANNOTATION_VALUE')
                        value = value_elem.text if value_elem is not None and value_elem.text else ""
                        
                        ann_data = {
                            'start_time': ref_ann['start_time'],
                            'end_time': ref_ann['end_time'],
                            'value': value.strip(),
                            'annotation_id': annotation_id,
                            'ref_annotation': ref_id
                        }
                        annotations.append(ann_data)
                        all_annotations[annotation_id] = ann_data
                
                self.annotations[tier_id] = annotations
            
            print("利用可能なティア:")
            for tier_id, annotations in self.annotations.items():
                print(f"  - {tier_id}: {len(annotations)} アノテーション")
            
            return True
            
        except Exception as e:
            print(f"EAF解析エラー: {e}")
            return False
    
    def extract_sentences(self, tier_names=None):
        if tier_names is None:
            tier_names = {'word': 'word', 'gloss': 'gloss', 'trans': 'trans', 'text': 'text'}
        
        sentences = []
        
        word_tier = tier_names.get('word', 'word')
        gloss_tier = tier_names.get('gloss', 'gloss')
        trans_tier = tier_names.get('trans', 'trans')
        text_tier = tier_names.get('text', 'text')
        
        word_annotations = self.annotations.get(word_tier, [])
        gloss_annotations = self.annotations.get(gloss_tier, [])
        trans_annotations = self.annotations.get(trans_tier, [])
        text_annotations = self.annotations.get(text_tier, [])
        
        print(f"抽出対象: word:{len(word_annotations)} gloss:{len(gloss_annotations)} trans:{len(trans_annotations)} text:{len(text_annotations)}")
        
        if not text_annotations:
            print(f"text層が見つかりません")
            return sentences
        
        for text_ann in text_annotations:
            text_start = text_ann['start_time']
            text_end = text_ann['end_time']
            text_content = text_ann['value']
            
            print(f"処理中: {text_content} ({text_start}ms - {text_end}ms)")
            
            words_in_sentence = []
            glosses_in_sentence = []
            
            for word_ann in word_annotations:
                if (word_ann['start_time'] >= text_start and word_ann['end_time'] <= text_end):
                    words_in_sentence.append(word_ann)
            
            for gloss_ann in gloss_annotations:
                if (gloss_ann['start_time'] >= text_start and gloss_ann['end_time'] <= text_end):
                    glosses_in_sentence.append(gloss_ann)
            
            trans_content = ""
            for trans_ann in trans_annotations:
                if (trans_ann['start_time'] <= text_start and trans_ann['end_time'] >= text_end):
                    trans_content = trans_ann['value']
                    break
            
            words_in_sentence.sort(key=lambda x: x['start_time'])
            glosses_in_sentence.sort(key=lambda x: x['start_time'])
            
            word_text = " ".join([ann['value'] for ann in words_in_sentence])
            gloss_text = " ".join([ann['value'] for ann in glosses_in_sentence])
            
            if word_text.strip():
                sentence = {
                    'word': word_text.strip(),
                    'gloss': gloss_text.strip(),
                    'trans': trans_content.strip(),
                    'text': text_content.strip(),
                    'start_time': text_start,
                    'end_time': text_end
                }
                sentences.append(sentence)
        
        print(f"抽出文数: {len(sentences)}")
        return sentences
    
    def ipa_to_tipa(self, text):
        # IPA→TIPA変換マップ（スペース保護版）
        conversions = {}
        conversions['ɨ'] = '\\textbari{}'
        conversions['ɯ'] = '\\textturnm{}'
        conversions['ɪ'] = '\\textsci{}'
        conversions['ʊ'] = '\\textupsilon{}'
        conversions['ə'] = '\\textschwa{}'
        conversions['ɛ'] = '\\textepsilon{}'
        conversions['ɔ'] = '\\textopeno{}'
        conversions['æ'] = '\\textae{}'
        conversions['ɑ'] = '\\textscripta{}'
        conversions['ɸ'] = '\\textphi{}'
        conversions['β'] = '\\textbeta{}'
        conversions['θ'] = '\\texttheta{}'
        conversions['ð'] = '\\textdh{}'
        conversions['ʃ'] = '\\textesh{}'
        conversions['ʒ'] = '\\textyogh{}'
        conversions['ç'] = '\\textcçc{}'
        conversions['ɣ'] = '\\textgamma{}'
        conversions['χ'] = '\\textchi{}'
        conversions['ʁ'] = '\\textinvscr{}'
        conversions['ɱ'] = '\\textmrleg{}'
        conversions['ɳ'] = '\\textrtailn{}'
        conversions['ɲ'] = '\\textltailn{}'
        conversions['ŋ'] = '\\texteng{}'
        conversions['ɾ'] = '\\textfishhookr{}'
        conversions['ɹ'] = '\\textturnr{}'
        conversions['ʔ'] = '\\textglotstop{}'
        conversions['ː'] = ':'
        
        result = text
        for ipa_char, tipa_code in conversions.items():
            result = result.replace(ipa_char, tipa_code)
        
        return result
    
    def load_audio(self):
        """音声ファイルを読み込む"""
        if not self.wav_file_path:
            print("音声ファイルが指定されていません。")
            return False
            
        if not os.path.exists(self.wav_file_path):
            print(f"音声ファイルが見つかりません: {self.wav_file_path}")
            return False
            
        if AUDIO_LIBRARY is None:
            print("オーディオライブラリが利用できません。")
            return False
            
        try:
            if AUDIO_LIBRARY == 'librosa':
                self.audio_data, self.sample_rate = librosa.load(self.wav_file_path, sr=None)
                print(f"音声ファイル読み込み: {self.wav_file_path}")
                print(f"サンプリング周波数: {self.sample_rate}Hz, 長さ: {len(self.audio_data)/self.sample_rate:.2f}秒")
                
            elif AUDIO_LIBRARY == 'pydub':
                if self.wav_file_path.lower().endswith('.wav'):
                    self.audio_data = AudioSegment.from_wav(self.wav_file_path)
                elif self.wav_file_path.lower().endswith('.mp3'):
                    self.audio_data = AudioSegment.from_mp3(self.wav_file_path)
                else:
                    self.audio_data = AudioSegment.from_file(self.wav_file_path)
                self.sample_rate = self.audio_data.frame_rate
                print(f"音声ファイル読み込み: {self.wav_file_path}")
                print(f"サンプリング周波数: {self.sample_rate}Hz")
                
            elif AUDIO_LIBRARY == 'wave':
                with wave.open(self.wav_file_path, 'rb') as wav_file:
                    self.sample_rate = wav_file.getframerate()
                    frames = wav_file.readframes(wav_file.getnframes())
                    self.audio_data = np.frombuffer(frames, dtype=np.int16)
                print(f"音声ファイル読み込み: {self.wav_file_path}")
                print(f"サンプリング周波数: {self.sample_rate}Hz")
                
            self.audio_available = True
            return True
            
        except Exception as e:
            print(f"音声読み込みエラー: {e}")
            return False
    
    def save_audio_segment(self, start_ms, end_ms, output_path, padding_ms=100):
        """指定時間範囲の音声を保存"""
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
    
    def create_gb4e(self, sentences):
        lines = []
        lines.append("% GB4E形式の例文")
        lines.append("% プリアンブルに \\usepackage{tipa} を追加")
        lines.append("")
        
        for i, sentence in enumerate(sentences, 1):
            if not sentence['word']:
                continue
            
            word_text = sentence['word']
            gloss_text = sentence['gloss']
            trans_text = sentence['trans']
            
            # カンマをスペースに変換
            clean_gloss = ""
            for char in gloss_text:
                if char == ",":
                    clean_gloss = clean_gloss + " "
                else:
                    clean_gloss = clean_gloss + char
            
            # IPA→TIPA変換
            tipa_word = self.ipa_to_tipa(word_text)
            
            # GB4E標準形式：改行を%で終了して継続
            lines.append("\\begin{exe}")
            lines.append("\\ex")
            lines.append("\\gll " + tipa_word + " \\\\%")
            lines.append("     " + clean_gloss + " \\\\%")
            lines.append("\\glt " + trans_text)
            lines.append("\\end{exe}")
        
    def create_gb4e_with_spacing_fix(self, sentences):
        """GB4E行間問題の根本解決版"""
        lines = []
        lines.append("% GB4E形式の例文（行間問題根本解決版）")
        lines.append("% プリアンブルに以下を必ず追加:")
        lines.append("% \\usepackage{tipa}")
        lines.append("% \\usepackage{gb4e}")
        lines.append("% % GB4E行間調整（重要）")
        lines.append("% \\let\\eachwordone=\\it")
        lines.append("% \\let\\eachwordtwo=\\rm") 
        lines.append("% \\def\\glossglue{\\hfil}")
        lines.append("% \\setlength{\\glossglue}{0pt}")
        lines.append("")
        
        for i, sentence in enumerate(sentences, 1):
            if not sentence['word']:
                continue
            
            word_text = sentence['word']
            gloss_text = sentence['gloss']
            trans_text = sentence['trans']
            
            clean_gloss = gloss_text.replace(',', ' ')
            tipa_word = self.ipa_to_tipa(word_text)
            
            # 厳密なGB4E形式（行間制御）
            lines.append("\\begin{exe}")
            lines.append("\\ex")
            lines.append("\\gll " + tipa_word + "\\\\")
            lines.append("     " + clean_gloss + "\\\\")
            lines.append("\\glt `" + trans_text + "'%")
            lines.append("\\end{exe}")
            lines.append("")
        
        return "\n".join(lines)

    def create_gb4e_minimal(self, sentences):
        """最小限GB4E形式（行間問題回避）"""
        lines = []
        lines.append("% GB4E形式の例文（最小限版）")
        lines.append("")
        
        for i, sentence in enumerate(sentences, 1):
            if not sentence['word']:
                continue
            
            word_text = sentence['word']
            gloss_text = sentence['gloss']
            trans_text = sentence['trans']
            
            clean_gloss = gloss_text.replace(',', ' ')
            tipa_word = self.ipa_to_tipa(word_text)
            
            # 最小限の書式（スペース最小化）
            lines.append("\\begin{exe}\\ex")
            lines.append("\\gll " + tipa_word + "\\\\")
            lines.append(clean_gloss + "\\\\")
            lines.append("\\glt `" + trans_text + "'\\end{exe}")
            lines.append("")
        
        return "\n".join(lines)

    def create_gb4e(self, sentences):
        # 問題解決版を優先使用
        return self.create_gb4e_with_spacing_fix(sentences)
    
    def create_txt(self, sentences):
        lines = []
        lines.append("EAF例文集")
        lines.append("=" * 50)
        lines.append("")
        
        for i, sentence in enumerate(sentences, 1):
            if not sentence['word']:
                continue
            
            lines.append(f"({i})")
            lines.append(sentence['word'])
            lines.append(sentence['gloss'])
            lines.append(sentence['trans'])
            lines.append("")
        
        return "\n".join(lines)
    
    def save_to_desktop(self, sentences):
        desktop_path = get_desktop_path()
        base_name = Path(self.eaf_file_path).stem
        folder_name = f"{base_name}_output"
        
        output_path = Path(desktop_path) / folder_name
        if output_path.exists():
            timestamp = int(time.time())
            backup_path = Path(desktop_path) / f"{folder_name}_backup_{timestamp}"
            shutil.move(str(output_path), str(backup_path))
            print(f"バックアップ: {backup_path}")
        
        output_path.mkdir(parents=True, exist_ok=True)
        
        # GB4E形式保存
        gb4e_content = self.create_gb4e(sentences)
        gb4e_file = output_path / 'sentences_gb4e.tex'
        with open(gb4e_file, 'w', encoding='utf-8') as f:
            f.write(gb4e_content)
        print(f"GB4E保存: {gb4e_file}")
        
        # TXT形式保存
        txt_content = self.create_txt(sentences)
        txt_file = output_path / 'sentences.txt'
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write(txt_content)
        print(f"TXT保存: {txt_file}")
        
        # 音声ファイル保存
        saved_audio_files = []
        if self.audio_available:
            print("音声ファイル分割中...")
            for i, sentence in enumerate(sentences, 1):
                if not sentence.get('start_time') or not sentence.get('end_time'):
                    print(f"⚠️ 文 {i} に時間情報がありません")
                    continue
                
                # 安全なファイル名生成
                safe_word = re.sub(r'[^\w\s-]', '', sentence['word'][:30])
                safe_word = re.sub(r'\s+', '_', safe_word.strip())
                if not safe_word:
                    safe_word = f"sentence_{i}"
                
                filename = f"{i:03d}_{safe_word}.wav"
                audio_file = output_path / filename
                
                success = self.save_audio_segment(
                    sentence['start_time'],
                    sentence['end_time'],
                    str(audio_file)
                )
                
                if success:
                    saved_audio_files.append(str(audio_file))
                    print(f"✅ 音声保存: {filename}")
                else:
                    print(f"❌ 音声保存失敗: {filename}")
            
            print(f"音声ファイル保存完了: {len(saved_audio_files)}個")
        else:
            print("音声データなし - テキストファイルのみ作成")
        
        return {
            'gb4e_file': str(gb4e_file), 
            'txt_file': str(txt_file), 
            'output_path': str(output_path),
            'audio_files': saved_audio_files,
            'total_files': len(saved_audio_files)
        }

def convert_eaf_simple(eaf_filename, wav_filename=None, tier_names=None):
    if not os.path.exists(eaf_filename):
        print(f"ファイルが見つかりません: {eaf_filename}")
        return None
    
    if wav_filename and not os.path.exists(wav_filename):
        print(f"音声ファイルが見つかりません: {wav_filename}")
        print("テキスト変換のみ実行します")
        wav_filename = None
    
    converter = SimpleEAFConverter(eaf_filename, wav_filename)
    
    if not converter.parse_eaf():
        return None
    
    # 音声ファイルがある場合は読み込み
    if wav_filename:
        converter.load_audio()
    
    sentences = converter.extract_sentences(tier_names)
    
    if not sentences:
        print("変換可能な文が見つかりませんでした")
        return None
    
    result = converter.save_to_desktop(sentences)
    
    print(f"\n🎉 変換完了!")
    print(f"📊 抽出文数: {len(sentences)}")
    print(f"📁 保存場所: {result['output_path']}")
    print(f"📝 GB4E形式: {result['gb4e_file']}")
    print(f"📄 TXT形式: {result['txt_file']}")
    if result['total_files'] > 0:
        print(f"🎵 音声ファイル: {result['total_files']}個")
    
    return result

# 使用例
if __name__ == "__main__":
    tier_names = {
        'word': 'word',
        'gloss': 'gloss', 
        'trans': 'trans',
        'text': 'text'
    }
    
    # 音声ファイルも指定
    result = convert_eaf_simple('sample3Ka.eaf', 'sample.wav', tier_names=tier_names)