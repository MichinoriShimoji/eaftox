import gradio as gr
import xml.etree.ElementTree as ET
import os
import re
import zipfile
from typing import Dict, List, Optional
import tempfile
import io

__version__ = "2026-03-10-r6"  # LaTeX特殊文字エスケープ修正版

# オーディオ処理ライブラリのインポート
AUDIO_LIBRARY = None
try:
    import librosa
    import soundfile as sf
    AUDIO_LIBRARY = 'librosa'
except ImportError:
    try:
        from pydub import AudioSegment
        AUDIO_LIBRARY = 'pydub'
    except ImportError:
        try:
            import wave
            import numpy as np
            AUDIO_LIBRARY = 'wave'
        except ImportError:
            AUDIO_LIBRARY = None

# 最大話者数
MAX_SPEAKERS = 8


class EAFConverter:
    """EAFコンバーター"""
    
    def __init__(self, eaf_file_path: str, wav_file_path: str = None):
        self.eaf_file_path = eaf_file_path
        self.wav_file_path = wav_file_path
        self.tree = None
        self.root = None
        self.time_slots = {}
        self.tiers = {}
        self.tier_info = {}
        
        # 音声処理用
        self.audio_data = None
        self.sample_rate = None
        self.audio_available = False
    
    def parse_eaf(self) -> bool:
        """EAFファイルを解析"""
        try:
            self.tree = ET.parse(self.eaf_file_path)
            self.root = self.tree.getroot()
        except Exception as e:
            print(f"EAF parse error: {e}")
            return False
        
        # タイムスロット解析
        time_order = self.root.find('TIME_ORDER')
        if time_order is not None:
            for ts in time_order.findall('TIME_SLOT'):
                slot_id = ts.get('TIME_SLOT_ID')
                time_value = ts.get('TIME_VALUE')
                if time_value:
                    self.time_slots[slot_id] = int(time_value)
        
        # 全アノテーションを一時保存（REF解決用）
        all_annotations = {}
        
        # ティア解析
        for tier in self.root.findall('TIER'):
            tier_id = tier.get('TIER_ID')
            parent_ref = tier.get('PARENT_REF', '')
            linguistic_type = tier.get('LINGUISTIC_TYPE_REF', '')
            
            annotations = []
            
            # ALIGNABLE_ANNOTATION
            for ann in tier.findall('.//ALIGNABLE_ANNOTATION'):
                ann_id = ann.get('ANNOTATION_ID')
                start_slot = ann.get('TIME_SLOT_REF1')
                end_slot = ann.get('TIME_SLOT_REF2')
                value_elem = ann.find('ANNOTATION_VALUE')
                value = value_elem.text.strip() if value_elem is not None and value_elem.text else ""
                
                if start_slot in self.time_slots and end_slot in self.time_slots:
                    ann_data = {
                        'annotation_id': ann_id,
                        'start_time': self.time_slots[start_slot],
                        'end_time': self.time_slots[end_slot],
                        'value': value
                    }
                    annotations.append(ann_data)
                    all_annotations[ann_id] = ann_data
            
            # REF_ANNOTATION
            for ann in tier.findall('.//REF_ANNOTATION'):
                ann_id = ann.get('ANNOTATION_ID')
                ref_id = ann.get('ANNOTATION_REF')
                value_elem = ann.find('ANNOTATION_VALUE')
                value = value_elem.text.strip() if value_elem is not None and value_elem.text else ""
                
                ref_time = self._resolve_ref_time(ref_id, all_annotations)
                if ref_time:
                    ann_data = {
                        'annotation_id': ann_id,
                        'start_time': ref_time[0],
                        'end_time': ref_time[1],
                        'value': value,
                        'ref_id': ref_id
                    }
                    annotations.append(ann_data)
                    all_annotations[ann_id] = ann_data
            
            annotations.sort(key=lambda x: x['start_time'])
            
            self.tiers[tier_id] = annotations
            self.tier_info[tier_id] = {
                'parent': parent_ref,
                'type': linguistic_type,
                'annotation_count': len(annotations),
                'sample': annotations[0]['value'][:50] if annotations else ''
            }
        
        return True
    
    def _resolve_ref_time(self, ref_id: str, all_annotations: dict, depth: int = 0) -> Optional[tuple]:
        """REF_ANNOTATIONの参照先の時間を再帰的に解決"""
        if depth > 10:
            return None
        
        if ref_id in all_annotations:
            ann = all_annotations[ref_id]
            return (ann['start_time'], ann['end_time'])
        
        for tier in self.root.findall('TIER'):
            for ann in tier.findall('.//ALIGNABLE_ANNOTATION'):
                if ann.get('ANNOTATION_ID') == ref_id:
                    start_slot = ann.get('TIME_SLOT_REF1')
                    end_slot = ann.get('TIME_SLOT_REF2')
                    if start_slot in self.time_slots and end_slot in self.time_slots:
                        return (self.time_slots[start_slot], self.time_slots[end_slot])
            
            for ann in tier.findall('.//REF_ANNOTATION'):
                if ann.get('ANNOTATION_ID') == ref_id:
                    nested_ref = ann.get('ANNOTATION_REF')
                    if nested_ref:
                        return self._resolve_ref_time(nested_ref, all_annotations, depth + 1)
        
        return None
    
    def get_tier_list(self) -> List[str]:
        """利用可能なティア名のリストを返す"""
        return list(self.tiers.keys())
    
    def get_tier_info_text(self) -> str:
        """ティア情報をテキストで返す"""
        lines = ["## 検出されたティア\n"]
        for tier_id, info in self.tier_info.items():
            lines.append(f"### {tier_id}")
            lines.append(f"- アノテーション数: {info['annotation_count']}")
            if info['parent']:
                lines.append(f"- 親ティア: {info['parent']}")
            if info['sample']:
                lines.append(f"- サンプル: {info['sample']}...")
            lines.append("")
        return "\n".join(lines)
    
    def load_audio(self) -> bool:
        """音声ファイルを読み込む"""
        if not self.wav_file_path or not os.path.exists(self.wav_file_path):
            return False
        
        if AUDIO_LIBRARY is None:
            return False
        
        try:
            if AUDIO_LIBRARY == 'librosa':
                self.audio_data, self.sample_rate = librosa.load(self.wav_file_path, sr=None)
            elif AUDIO_LIBRARY == 'pydub':
                ext = self.wav_file_path.lower()
                if ext.endswith('.wav'):
                    self.audio_data = AudioSegment.from_wav(self.wav_file_path)
                elif ext.endswith('.mp3'):
                    self.audio_data = AudioSegment.from_mp3(self.wav_file_path)
                else:
                    self.audio_data = AudioSegment.from_file(self.wav_file_path)
                self.sample_rate = self.audio_data.frame_rate
            elif AUDIO_LIBRARY == 'wave':
                import numpy as np
                with wave.open(self.wav_file_path, 'rb') as wav_file:
                    self.sample_rate = wav_file.getframerate()
                    frames = wav_file.readframes(wav_file.getnframes())
                    self.audio_data = np.frombuffer(frames, dtype=np.int16)
            
            self.audio_available = True
            return True
        except Exception as e:
            print(f"Audio load error: {e}")
            return False
    
    def save_audio_segment(self, start_ms: int, end_ms: int, output_path: str, padding_ms: int = 100) -> bool:
        """指定時間範囲の音声を保存"""
        if not self.audio_available:
            return False
        
        try:
            padded_start = max(0, start_ms - padding_ms)
            padded_end = end_ms + padding_ms
            
            if AUDIO_LIBRARY == 'librosa':
                start_sample = int((padded_start / 1000.0) * self.sample_rate)
                end_sample = int((padded_end / 1000.0) * self.sample_rate)
                end_sample = min(len(self.audio_data), end_sample)
                audio_segment = self.audio_data[start_sample:end_sample]
                sf.write(output_path, audio_segment, self.sample_rate)
            elif AUDIO_LIBRARY == 'pydub':
                audio_segment = self.audio_data[padded_start:padded_end]
                audio_segment.export(output_path, format="wav")
            elif AUDIO_LIBRARY == 'wave':
                import numpy as np
                start_sample = int((padded_start / 1000.0) * self.sample_rate)
                end_sample = int((padded_end / 1000.0) * self.sample_rate)
                end_sample = min(len(self.audio_data), end_sample)
                audio_segment = self.audio_data[start_sample:end_sample]
                with wave.open(output_path, 'wb') as wav_out:
                    wav_out.setnchannels(1)
                    wav_out.setsampwidth(2)
                    wav_out.setframerate(self.sample_rate)
                    wav_out.writeframes(audio_segment.tobytes())
            
            return True
        except Exception as e:
            print(f"Audio segment save error: {e}")
            return False
    
    def _find_overlapping_value(self, tier_data: List[Dict], start_time: int, end_time: int,
                                exclude_ann_ids: set = None, exclude_ref_ids: set = None) -> str:
        """指定時間範囲と重複するアノテーションを結合して返す。
        
        exclude_ann_ids: 除外するアノテーションID（annotation_id で照合、morph層用）
        exclude_ref_ids: 除外する参照先ID（ref_id で照合、gloss/pos層用）
        """
        matching = []
        
        for ann in tier_data:
            # 境界マーカー除外チェック
            if exclude_ann_ids and ann.get('annotation_id') in exclude_ann_ids:
                continue
            if exclude_ref_ids and ann.get('ref_id') in exclude_ref_ids:
                continue
            
            overlap_start = max(ann['start_time'], start_time)
            overlap_end = min(ann['end_time'], end_time)
            
            if overlap_start < overlap_end or (ann['start_time'] == start_time and ann['end_time'] == end_time):
                matching.append(ann)
        
        matching.sort(key=lambda x: x['start_time'])
        return ' '.join([a['value'] for a in matching if a['value']])
    
    # EOS/EOA等の境界マーカーとして認識するグロスラベルのパターン
    # （EO + 大文字1文字以上：EOS, EOA, EOC, EOP, EOT, EOPAT など）
    _BOUNDARY_GLOSS_PATTERN = re.compile(r'^EO[A-Z]+$', re.IGNORECASE)
    
    # 形態素値が句読点のみ（グロス層なしの場合のフォールバック検出）
    _PUNCTUATION_ONLY_PATTERN = re.compile(r'^[^\w\s]+$')
    
    def _get_boundary_marker_ann_ids(self, start_time: int, end_time: int,
                                      morph_tier_name: str, gloss_tier_name: str) -> set:
        """EOS/EOA等の区切り文字形態素に対応するmorph annotation IDのセットを返す。
        
        検出方法（両方を適用し和集合を返す）：
        1. gloss層でEO*パターンのラベルを持つアノテーションのref_id（= morph ann id）
        2. morph層で値が句読点のみのアノテーションのannotation_id（グロスなし時のフォールバック）
        """
        exclude_ids = set()
        
        # 検出方法1: gloss層のEO*ラベルからmorph annotation IDを収集
        if gloss_tier_name and gloss_tier_name in self.tiers:
            for ann in self.tiers[gloss_tier_name]:
                # 時間範囲内のアノテーションのみ対象
                if not (ann['start_time'] >= start_time and ann['end_time'] <= end_time):
                    # 部分重複も考慮（完全包含でない場合）
                    if not (ann['start_time'] < end_time and ann['end_time'] > start_time):
                        continue
                if self._BOUNDARY_GLOSS_PATTERN.match(ann['value'].strip()):
                    ref = ann.get('ref_id')
                    if ref:
                        exclude_ids.add(ref)
        
        # 検出方法2: morph層の句読点形態素（gloss未設定のファイル向けフォールバック）
        if morph_tier_name and morph_tier_name in self.tiers:
            for ann in self.tiers[morph_tier_name]:
                if not (ann['start_time'] < end_time and ann['end_time'] > start_time):
                    continue
                val = ann['value'].strip()
                if val and self._PUNCTUATION_ONLY_PATTERN.match(val):
                    exclude_ids.add(ann['annotation_id'])
        
        return exclude_ids
    
    def _align_morphs_with_text(self, text_with_boundaries: str, morph_or_gloss: str) -> str:
        """text層の区切り文字（=、-、+、.）に基づいてmorph/gloss層を再配置"""
        if not text_with_boundaries or not morph_or_gloss:
            return morph_or_gloss
        
        # EOS/EOA等に対応する句読点をboundary_baseから除去する前処理：
        #   1. 単独句読点のみのトークンを除去（例: "hai ." → "hai"）
        #   2. 語末の句読点をstrip（例: "s-i-mas-u." → "s-i-mas-u"）
        cleaned_words = []
        for w in text_with_boundaries.split():
            if self._PUNCTUATION_ONLY_PATTERN.match(w):
                continue  # 単独句読点トークンはスキップ
            w = re.sub(r'[.,!?;:。、！？；：]+$', '', w)  # 語末句読点を除去
            if w:
                cleaned_words.append(w)
        text_with_boundaries = ' '.join(cleaned_words)
        
        if not text_with_boundaries:
            return morph_or_gloss
        
        # gloss層をスペースで分割
        gloss_list = morph_or_gloss.split()
        if not gloss_list:
            return morph_or_gloss
        
        text_words = text_with_boundaries.split()
        result_parts = []
        gloss_idx = 0
        
        for word in text_words:
            # text単語を境界記号で分割（_ も境界記号として扱う）
            text_segments = re.split(r'([=\-+._])', word)
            text_morphs = [s for s in text_segments if s not in ['=', '-', '+', '.', '_'] and s.strip()]
            text_morph_count = len(text_morphs)
            
            if text_morph_count == 0:
                # 境界記号のみの単語（句読点など）はスキップ
                result_parts.append(word)
                continue
            
            if gloss_idx >= len(gloss_list):
                break
            
            # 先頭/末尾の境界記号を検出（. はグロス側に出力しない）
            leading_boundary = ''
            trailing_boundary = ''
            if text_segments and text_segments[0] == '':
                # 先頭が空 = 境界記号から始まる
                if len(text_segments) > 1 and text_segments[1] in ['=', '-', '+', '_']:
                    leading_boundary = text_segments[1]
            if text_segments and text_segments[-1] == '':
                # 末尾が空 = 境界記号で終わる
                if len(text_segments) > 1 and text_segments[-2] in ['=', '-', '+', '_']:
                    trailing_boundary = text_segments[-2]
            
            # 対応するgloss要素を取得
            current_gloss = gloss_list[gloss_idx]
            
            # gloss要素内に境界記号があるかチェック（_ も境界記号として扱う）
            # ※グロス側では . をライプツィヒ複合グロス区切り（PST.CSL等）として扱うため分割しない
            gloss_segments = re.split(r'([=\-+_])', current_gloss)
            gloss_morphs = [s for s in gloss_segments if s not in ['=', '-', '+', '_'] and s.strip()
                            and not self._PUNCTUATION_ONLY_PATTERN.match(s)]
            gloss_morph_count = len(gloss_morphs)
            
            if gloss_morph_count == text_morph_count:
                # glossの境界パターンがtextと一致 → そのまま使用（先頭/末尾の境界を追加）
                result = leading_boundary + current_gloss + trailing_boundary
                result_parts.append(result)
                gloss_idx += 1
            elif gloss_morph_count == 1 and text_morph_count > 1:
                # glossに境界がないがtextにはある → 複数のgloss要素を結合
                word_glosses = []
                morphs_needed = text_morph_count
                
                while morphs_needed > 0 and gloss_idx < len(gloss_list):
                    g = gloss_list[gloss_idx]
                    g_segments = re.split(r'([=\-+_])', g)
                    g_morphs = [s for s in g_segments if s not in ['=', '-', '+', '_'] and s.strip()
                                and not self._PUNCTUATION_ONLY_PATTERN.match(s)]
                    
                    if len(g_morphs) <= morphs_needed:
                        word_glosses.append(g)
                        morphs_needed -= len(g_morphs)
                        gloss_idx += 1
                    else:
                        break
                
                # textの境界パターンに合わせて再構築
                if word_glosses:
                    combined_glosses = []
                    for g in word_glosses:
                        g_parts = re.split(r'([=\-+_])', g)
                        for p in g_parts:
                            if p.strip():
                                combined_glosses.append(p)
                    
                    # textの境界パターンを適用（. はグロス側には出力しない）
                    result_morph = []
                    combined_idx = 0
                    for seg in text_segments:
                        if seg in ['=', '-', '+', '_']:
                            result_morph.append(seg)
                        elif seg == '.':
                            pass  # 文末句読点はグロス側に出力しない
                        elif seg.strip() and combined_idx < len(combined_glosses):
                            result_morph.append(combined_glosses[combined_idx])
                            combined_idx += 1
                    result_parts.append(''.join(result_morph))
            else:
                # その他のケース → gloss1つに先頭/末尾の境界を追加
                result = leading_boundary + current_gloss + trailing_boundary
                result_parts.append(result)
                gloss_idx += 1
        
        # EOS除去によって宙ぶらりになった末尾の境界記号（= - +）を除去
        # 例: PST-HS= の末尾 = は =ca. の ca が EOS除去されたことで生じる
        assembled = ' '.join(result_parts)
        assembled = re.sub(r'[=\-+_]+$', '', assembled).rstrip()
        return assembled
    
    def _convert_ipa_to_tipa(self, text: str) -> str:
        """IPA→TIPA変換"""
        if not text:
            return text
        
        # LaTeX特殊文字のエスケープ（安全網）
        # ※ \ はIPA変換コマンドに使うため最初に処理済みなのでここでは対象外
        # ※ { } はtextscコマンド等に使うため対象外
        text = text.replace('_', '\\_')   # 下付き
        text = text.replace('^', r'\^{}') # 上付き → ^^XXで日本語が化ける原因
        text = text.replace('%', '\\%')   # コメント
        text = text.replace('&', '\\&')   # 表のセル区切り
        text = text.replace('#', '\\#')   # パラメータ
        text = text.replace('~', '\\~{}') # ノーブレークスペース
        text = text.replace('$', '\\$')   # 数式モード
        
        ipa_to_tipa = {
            'ɨ': '\\textbari{}', 'ɯ': '\\textturnm{}', 'ɛ': '\\textepsilon{}',
            'ɔ': '\\textopeno{}', 'æ': '\\textae{}', 'ɑ': '\\textscripta{}',
            'ɒ': '\\textturnscripta{}', 'ə': '\\textschwa{}', 'ɪ': '\\textsci{}',
            'ʊ': '\\textupsilon{}', 'ʃ': '\\textesh{}', 'ʒ': '\\textyogh{}',
            'θ': '\\texttheta{}', 'ð': '\\textdh{}', 'ŋ': '\\texteng{}',
            'ɲ': '\\textltailn{}', 'ɳ': '\\textrtailn{}', 'ɱ': '\\textmrleg{}',
            'ɾ': '\\textfishhookr{}', 'ɽ': '\\textrtailr{}', 'ɻ': '\\textturnr{}',
            'ɭ': '\\textrtaill{}', 'ʎ': '\\textturny{}', 'ʈ': '\\textrtailt{}',
            'ɖ': '\\textrtaild{}', 'ʂ': '\\textrtails{}', 'ʐ': '\\textrtailz{}',
            'ɕ': '\\textctc{}', 'ʑ': '\\textctj{}', 'ç': '\\textc{c}',
            'ʝ': '\\textctj{}', 'ɣ': '\\textgamma{}', 'χ': '\\textchi{}',
            'ʁ': '\\textinvscr{}', 'ħ': '\\textcrh{}', 'ʕ': '\\textrevglotstop{}',
            'ʔ': '\\textglotstop{}', 'ɸ': '\\textphi{}', 'β': '\\textbeta{}',
            'ʋ': '\\textscriptv{}', 'ɹ': '\\textturnr{}', 'ɰ': '\\textturnmrleg{}',
            'ɺ': '\\textlhti{}', 'ɢ': '\\textscg{}', 'ʛ': '\\texthtg{}',
            'ɠ': '\\texthtg{}', 'ɡ': '\\textscg{}', 'ː': ':',
            'ˈ': '\\textprimstress{}', 'ˌ': '\\textsecstress{}',
            'ʲ': '\\textpal{}', 'ʷ': '\\textlab{}',
            'ʰ': '\\textsuperscript{h}', 'ⁿ': '\\textsuperscript{n}',
            'ʼ': '\\textglotstop{}',
            # ゼロ形態素記号
            'Ø': '\\O{}', 'ø': '\\o{}',
            # その他の特殊文字
            '∅': '$\\emptyset$',
            # ハーチェク付き文字
            'ž': 'Z', 'Ž': 'Z',
            'š': 'S', 'Š': 'S',
            'č': 'C', 'Č': 'C',
        }
        
        result = text
        for ipa_char, tipa_cmd in ipa_to_tipa.items():
            result = result.replace(ipa_char, tipa_cmd)
        return result
    
    def _convert_leipzig_glosses(self, gloss_text: str) -> str:
        """大文字グロス→\\textsc{}変換（数字付きグロスも対応）"""
        if not gloss_text:
            return gloss_text
        
        def convert_caps(match):
            return f'\\textsc{{{match.group(0).lower()}}}'
        
        # [A-Z]{2,}[0-9]* で NOM2, GEN2 なども一括変換
        result = re.sub(r'(?<![A-Za-z0-9])[A-Z]{2,}[0-9]*(?![A-Za-z])', convert_caps, gloss_text)
        return result
    
    def extract_sentences_for_speaker(self, mode: str, tier_names: Dict[str, str], speaker_name: str) -> List[Dict]:
        """指定話者の文を抽出"""
        sentences = []
        
        # 基準ティアを決定
        if mode == "4層" and tier_names.get('text0') and tier_names['text0'] in self.tiers:
            base_tier_name = tier_names['text0']
            base_role = 'text0'
        elif tier_names.get('text') and tier_names['text'] in self.tiers:
            base_tier_name = tier_names['text']
            base_role = 'text'
        else:
            return sentences
        
        base_tier = self.tiers[base_tier_name]
        
        for base_ann in base_tier:
            if not base_ann['value']:
                continue
            
            start_time = base_ann['start_time']
            end_time = base_ann['end_time']
            
            sentence = {
                'start_time': start_time,
                'end_time': end_time,
                'speaker': speaker_name,
                'mode': mode,
                'text0': None,
                'text': None,
                'morph': None,
                'gloss': None,
                'pos': None,
                'trans': None
            }
            
            sentence[base_role] = base_ann['value']
            
            # 他のティアから取得（境界マーカーを除外）のあと、
            # text層（2層目以降）の末尾句読点を除去する準備フラグ
            # （text0はsurface formなのでそのまま、textはunderlying formなので末尾句読点を除去）
            
            # EOS/EOA等の境界マーカー形態素のIDを収集
            # morph層のannotation_idセット（morph層除外用）= gloss/pos層のref_idセット（子層除外用）
            boundary_ids = self._get_boundary_marker_ann_ids(
                start_time, end_time,
                tier_names.get('morph'),
                tier_names.get('gloss')
            )
            
            # 他のティアから取得（境界マーカーを除外）
            for role, tier_name in tier_names.items():
                if role == base_role or not tier_name or tier_name not in self.tiers:
                    continue
                if boundary_ids:
                    if role == 'morph':
                        # morph層自身: annotation_id で除外
                        value = self._find_overlapping_value(
                            self.tiers[tier_name], start_time, end_time,
                            exclude_ann_ids=boundary_ids
                        )
                    else:
                        # gloss/pos/trans等の子層: ref_id（= 親morphのannotation_id）で除外
                        value = self._find_overlapping_value(
                            self.tiers[tier_name], start_time, end_time,
                            exclude_ref_ids=boundary_ids
                        )
                else:
                    value = self._find_overlapping_value(self.tiers[tier_name], start_time, end_time)
                sentence[role] = value
            
            # text層（underlying form）の末尾句読点を除去するのは、
            # text0（surface form）も存在する4層モードのときだけ。
            # text が唯一の表層形（3層/シンプル3層）のときは手を触れない。
            if sentence.get('text') and sentence.get('text0'):
                # 末尾の句読点を除去するが、.. や ... など複数ドットの言い淀みは残す
                # (?<!\.)\.(?!\.) = 前後にドットがない単独の . のみ対象
                sentence['text'] = re.sub(r'\s*([,!?;:。、！？；：]+|(?<!\.)\.(?!\.))\s*$', '', sentence['text']).rstrip()
            
            sentences.append(sentence)
        
        return sentences
    
    def _normalize_boundaries(self, text: str) -> str:
        """形態素境界記号を正規化（== → =、-- → -、++ → +、.. → .）"""
        if not text:
            return text
        # ==を=に、--を-に、++を+に、..を.に変換
        result = text.replace('==', '=').replace('--', '-').replace('++', '+').replace('..', '.')
        return result
    
    def to_doc_format(self, sentences: List[Dict]) -> str:
        """DOC形式に変換（複数話者対応）"""
        output = []
        
        # 話者が複数いる場合のみラベルを表示
        unique_speakers = {s.get('speaker', '') for s in sentences if s.get('speaker')}
        show_speaker = len(unique_speakers) > 1
        
        for i, sent in enumerate(sentences, 1):
            if not sent.get('text0') and not sent.get('text'):
                continue
            
            mode = sent.get('mode', '3層')
            speaker = sent.get('speaker', '')
            
            # 話者ラベル付き番号（複数話者のときのみ）
            if show_speaker and speaker:
                output.append(f"({i}) [{speaker}]")
            else:
                output.append(f"({i})")
            
            if mode == "4層":
                # 4層: text0, text, gloss, (pos), trans
                if sent.get('text0'):
                    output.append(self._normalize_boundaries(sent['text0']))
                if sent.get('text'):
                    output.append(self._normalize_boundaries(sent['text']))
                boundary_base = sent.get('text') or sent.get('text0')
            else:
                # 3層、シンプル3層: text, gloss, (pos), trans
                if sent.get('text'):
                    output.append(self._normalize_boundaries(sent['text']))
                boundary_base = sent.get('text')
            
            # gloss（形態素境界を復活）
            if sent.get('gloss') and boundary_base:
                aligned_gloss = self._align_morphs_with_text(boundary_base, sent['gloss'])
                output.append(self._normalize_boundaries(aligned_gloss))
            
            # pos（オプション、形態素境界を復活）
            if sent.get('pos') and boundary_base:
                aligned_pos = self._align_morphs_with_text(boundary_base, sent['pos'])
                output.append(self._normalize_boundaries(aligned_pos))
            
            # trans
            if sent.get('trans'):
                output.append(sent['trans'])
            
            output.append("")
        
        return "\n".join(output)
    
    def to_gb4e_format(self, sentences: List[Dict], style: str = "標準版") -> str:
        """GB4E形式に変換（複数話者対応）"""
        if style == "行間調整版":
            return self._create_gb4e_spacing_fix(sentences)
        elif style == "最小限版":
            return self._create_gb4e_minimal(sentences)
        else:
            return self._create_gb4e_standard(sentences)
    
    def _create_gb4e_standard(self, sentences: List[Dict]) -> str:
        """標準GB4E形式（複数話者対応）"""
        output = []
        # Preamble
        output.append("\\documentclass{jarticle}")
        output.append("\\usepackage{gb4e}")
        output.append("\\usepackage{tipa}")
        output.append("% \\usepackage{leipzig}")
        output.append("")
        output.append("\\begin{document}")
        output.append("")
        
        # 話者が複数いる場合のみラベルを表示
        unique_speakers = {s.get('speaker', '') for s in sentences if s.get('speaker')}
        show_speaker = len(unique_speakers) > 1
        
        for sent in sentences:
            if not sent.get('text0') and not sent.get('text'):
                continue
            
            mode = sent.get('mode', '3層')
            speaker = sent.get('speaker', '')
            
            output.append("\\begin{exe}")
            output.append("\\ex")
            
            # 話者ラベル付き（複数話者のときのみ）
            if show_speaker and speaker:
                output.append(f"\\textbf{{[{speaker}]}}")
            
            if mode == "4層":
                # 4層: text0, text, gloss
                boundary_base = sent.get('text') or sent.get('text0')
                text0_normalized = self._normalize_boundaries(sent.get('text0', ''))
                text_normalized = self._normalize_boundaries(sent.get('text', ''))
                text0_tipa = self._convert_ipa_to_tipa(text0_normalized)
                text_tipa = self._convert_ipa_to_tipa(text_normalized)
                
                output.append(f"\\glll {text0_tipa}\\\\")
                output.append(f"      {text_tipa}\\\\")
                
                if sent.get('gloss') and boundary_base:
                    aligned_gloss = self._align_morphs_with_text(boundary_base, sent['gloss'])
                    aligned_gloss = self._normalize_boundaries(aligned_gloss)
                    gloss_leipzig = self._convert_leipzig_glosses(aligned_gloss)
                    gloss_tipa = self._convert_ipa_to_tipa(gloss_leipzig)
                    output.append(f"      {gloss_tipa}\\\\")
                else:
                    output.append("      \\\\")
            else:
                # 3層、シンプル3層: text, gloss
                boundary_base = sent.get('text')
                text_normalized = self._normalize_boundaries(sent.get('text', ''))
                text_tipa = self._convert_ipa_to_tipa(text_normalized)
                output.append(f"\\gll {text_tipa}\\\\")
                
                if sent.get('gloss') and boundary_base:
                    aligned_gloss = self._align_morphs_with_text(boundary_base, sent['gloss'])
                    aligned_gloss = self._normalize_boundaries(aligned_gloss)
                    gloss_leipzig = self._convert_leipzig_glosses(aligned_gloss)
                    gloss_tipa = self._convert_ipa_to_tipa(gloss_leipzig)
                    output.append(f"     {gloss_tipa}\\\\")
                else:
                    output.append("     \\\\")
            
            if sent.get('trans'):
                output.append(f"\\glt {sent['trans']}")
            else:
                output.append("\\glt")
            
            output.append("\\end{exe}")
            output.append("")
        
        output.append("\\end{document}")
        return "\n".join(output)
    
    def _create_gb4e_spacing_fix(self, sentences: List[Dict]) -> str:
        """行間調整版GB4E（複数話者対応）"""
        output = []
        # Preamble
        output.append("\\documentclass{jarticle}")
        output.append("\\usepackage{gb4e}")
        output.append("\\usepackage{tipa}")
        output.append("% \\usepackage{leipzig}")
        output.append("\\let\\eachwordone=\\it")
        output.append("\\let\\eachwordtwo=\\rm")
        output.append("\\def\\glossglue{\\hfil}")
        output.append("")
        output.append("\\begin{document}")
        output.append("")
        
        # 話者が複数いる場合のみラベルを表示
        unique_speakers = {s.get('speaker', '') for s in sentences if s.get('speaker')}
        show_speaker = len(unique_speakers) > 1
        
        for sent in sentences:
            if not sent.get('text0') and not sent.get('text'):
                continue
            
            mode = sent.get('mode', '3層')
            speaker = sent.get('speaker', '')
            
            output.append("\\begin{exe}")
            output.append("\\ex")
            
            if show_speaker and speaker:
                output.append(f"\\textbf{{[{speaker}]}}")
            
            if mode == "4層":
                boundary_base = sent.get('text') or sent.get('text0')
                text0_normalized = self._normalize_boundaries(sent.get('text0', ''))
                text_normalized = self._normalize_boundaries(sent.get('text', ''))
                text0_tipa = self._convert_ipa_to_tipa(text0_normalized)
                text_tipa = self._convert_ipa_to_tipa(text_normalized)
                
                output.append(f"\\glll {text0_tipa}\\\\")
                output.append(f"      {text_tipa}\\\\")
                
                if sent.get('gloss') and boundary_base:
                    aligned_gloss = self._align_morphs_with_text(boundary_base, sent['gloss'])
                    aligned_gloss = self._normalize_boundaries(aligned_gloss)
                    gloss_leipzig = self._convert_leipzig_glosses(aligned_gloss)
                    gloss_tipa = self._convert_ipa_to_tipa(gloss_leipzig)
                    output.append(f"      {gloss_tipa}\\\\")
                else:
                    output.append("      \\\\")
            else:
                boundary_base = sent.get('text')
                text_normalized = self._normalize_boundaries(sent.get('text', ''))
                text_tipa = self._convert_ipa_to_tipa(text_normalized)
                output.append(f"\\gll {text_tipa}\\\\")
                
                if sent.get('gloss') and boundary_base:
                    aligned_gloss = self._align_morphs_with_text(boundary_base, sent['gloss'])
                    aligned_gloss = self._normalize_boundaries(aligned_gloss)
                    gloss_leipzig = self._convert_leipzig_glosses(aligned_gloss)
                    gloss_tipa = self._convert_ipa_to_tipa(gloss_leipzig)
                    output.append(f"     {gloss_tipa}\\\\")
                else:
                    output.append("     \\\\")
            
            if sent.get('trans'):
                output.append(f"\\glt `{sent['trans']}'%")
            else:
                output.append("\\glt")
            
            output.append("\\end{exe}")
            output.append("")
        
        output.append("\\end{document}")
        return "\n".join(output)
    
    def _create_gb4e_minimal(self, sentences: List[Dict]) -> str:
        """最小限GB4E形式（複数話者対応）"""
        output = []
        # Preamble
        output.append("\\documentclass{jarticle}")
        output.append("\\usepackage{gb4e}")
        output.append("\\usepackage{tipa}")
        output.append("")
        output.append("\\begin{document}")
        output.append("")
        
        # 話者が複数いる場合のみラベルを表示
        unique_speakers = {s.get('speaker', '') for s in sentences if s.get('speaker')}
        show_speaker = len(unique_speakers) > 1
        
        for sent in sentences:
            if not sent.get('text0') and not sent.get('text'):
                continue
            
            mode = sent.get('mode', '3層')
            speaker = sent.get('speaker', '')
            
            if show_speaker and speaker:
                output.append(f"\\begin{{exe}}\\ex \\textbf{{[{speaker}]}}")
            else:
                output.append("\\begin{exe}\\ex")
            
            if mode == "4層":
                boundary_base = sent.get('text') or sent.get('text0')
                text0_normalized = self._normalize_boundaries(sent.get('text0', ''))
                text_normalized = self._normalize_boundaries(sent.get('text', ''))
                text0_tipa = self._convert_ipa_to_tipa(text0_normalized)
                text_tipa = self._convert_ipa_to_tipa(text_normalized)
                
                output.append(f"\\glll {text0_tipa}\\\\")
                output.append(f"{text_tipa}\\\\")
                
                if sent.get('gloss') and boundary_base:
                    aligned_gloss = self._align_morphs_with_text(boundary_base, sent['gloss'])
                    aligned_gloss = self._normalize_boundaries(aligned_gloss)
                    gloss_leipzig = self._convert_leipzig_glosses(aligned_gloss)
                    gloss_tipa = self._convert_ipa_to_tipa(gloss_leipzig)
                    output.append(f"{gloss_tipa}\\\\")
                else:
                    output.append("\\\\")
            else:
                boundary_base = sent.get('text')
                text_normalized = self._normalize_boundaries(sent.get('text', ''))
                text_tipa = self._convert_ipa_to_tipa(text_normalized)
                output.append(f"\\gll {text_tipa}\\\\")
                
                if sent.get('gloss') and boundary_base:
                    aligned_gloss = self._align_morphs_with_text(boundary_base, sent['gloss'])
                    aligned_gloss = self._normalize_boundaries(aligned_gloss)
                    gloss_leipzig = self._convert_leipzig_glosses(aligned_gloss)
                    gloss_tipa = self._convert_ipa_to_tipa(gloss_leipzig)
                    output.append(f"{gloss_tipa}\\\\")
                else:
                    output.append("\\\\")
            
            if sent.get('trans'):
                output.append(f"\\glt `{sent['trans']}'\\end{{exe}}")
            else:
                output.append("\\glt\\end{exe}")
            
            output.append("")
        
        output.append("\\end{document}")
        return "\n".join(output)


# グローバル変数
current_converter = None
current_tier_list = []


def analyze_eaf(eaf_file):
    """EAFファイルを解析してティア情報を返す"""
    global current_converter, current_tier_list
    
    if eaf_file is None:
        return "EAFファイルをアップロードしてください。", []
    
    try:
        if hasattr(eaf_file, 'name'):
            eaf_path = eaf_file.name
        else:
            eaf_path = eaf_file
        
        current_converter = EAFConverter(eaf_path)
        if not current_converter.parse_eaf():
            return "EAFファイルの解析に失敗しました。", []
        
        current_tier_list = current_converter.get_tier_list()
        tier_info = current_converter.get_tier_info_text()
        
        return tier_info, current_tier_list
    
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        return f"エラー: {str(e)}\n\n{error_detail}", []


def update_tier_dropdowns(tier_list):
    """ティアリストに基づいてドロップダウンを更新"""
    choices_with_none = ["（なし）"] + tier_list
    updates = []
    
    for _ in range(MAX_SPEAKERS):
        # 各話者のティアドロップダウン更新（text0, text, morph, gloss, pos, trans × MAX_SPEAKERS）
        for _ in range(6):
            updates.append(gr.update(choices=choices_with_none, value="（なし）"))
    
    return updates


def update_speaker_visibility(num_speakers):
    """話者数に応じてUIの表示/非表示を更新"""
    updates = []
    for i in range(MAX_SPEAKERS):
        updates.append(gr.update(visible=(i < num_speakers)))
    return updates


def update_mode_visibility(mode):
    """モードに応じてtext0とmorphの表示を切り替え"""
    if mode == "4層":
        return gr.update(visible=True), gr.update(visible=True)
    elif mode == "3層":
        return gr.update(visible=False), gr.update(visible=True)
    else:  # シンプル3層
        return gr.update(visible=False), gr.update(visible=False)


def convert_eaf(eaf_file, audio_file, include_audio, padding_ms, gb4e_style,
                num_speakers, *speaker_args, progress=gr.Progress()):
    """EAFファイルを変換（複数話者対応）"""
    
    if eaf_file is None:
        return None, None, None, "EAFファイルをアップロードしてください。"
    
    try:
        progress(0.1, desc="ファイルを準備中...")
        
        if hasattr(eaf_file, 'name'):
            eaf_path = eaf_file.name
        else:
            eaf_path = eaf_file
        
        audio_path = None
        if audio_file and include_audio:
            if hasattr(audio_file, 'name'):
                audio_path = audio_file.name
            else:
                audio_path = audio_file
        
        progress(0.2, desc="EAFファイルを解析中...")
        
        converter = EAFConverter(eaf_path, audio_path)
        if not converter.parse_eaf():
            return None, None, None, "EAFファイルの解析に失敗しました。"
        
        if audio_path:
            converter.load_audio()
        
        progress(0.3, desc="文を抽出中...")
        
        # 話者設定を解析
        # speaker_args: [name1, mode1, text0_1, text1, morph1, gloss1, pos1, trans1, name2, mode2, ...]
        args_per_speaker = 8  # name, mode, text0, text, morph, gloss, pos, trans
        
        all_sentences = []
        speaker_info_list = []
        
        for i in range(num_speakers):
            base_idx = i * args_per_speaker
            speaker_name = speaker_args[base_idx] or f"話者{i+1}"
            mode = speaker_args[base_idx + 1] or "3層"
            text0_tier = speaker_args[base_idx + 2]
            text_tier = speaker_args[base_idx + 3]
            morph_tier = speaker_args[base_idx + 4]
            gloss_tier = speaker_args[base_idx + 5]
            pos_tier = speaker_args[base_idx + 6]
            trans_tier = speaker_args[base_idx + 7]
            
            def get_tier_value(val):
                return val if val and val != "（なし）" else None
            
            tier_names = {
                'text': get_tier_value(text_tier),
                'gloss': get_tier_value(gloss_tier),
                'pos': get_tier_value(pos_tier),
                'trans': get_tier_value(trans_tier)
            }
            
            if mode == "4層":
                tier_names['text0'] = get_tier_value(text0_tier)
                tier_names['morph'] = get_tier_value(morph_tier)
            elif mode == "3層":
                tier_names['morph'] = get_tier_value(morph_tier)
            
            # 検証
            if mode == "4層":
                if not tier_names.get('text0') and not tier_names.get('text'):
                    continue  # この話者はスキップ
            else:
                if not tier_names.get('text'):
                    continue
            
            sentences = converter.extract_sentences_for_speaker(mode, tier_names, speaker_name)
            all_sentences.extend(sentences)
            
            if sentences:
                speaker_info_list.append({
                    'name': speaker_name,
                    'mode': mode,
                    'count': len(sentences)
                })
        
        if not all_sentences:
            return None, None, None, "変換可能な文が見つかりませんでした。ティアの選択を確認してください。"
        
        # 時間順にソート
        all_sentences.sort(key=lambda x: x['start_time'])
        
        progress(0.5, desc="テキスト形式を生成中...")
        
        gb4e_content = converter.to_gb4e_format(all_sentences, style=gb4e_style)
        doc_content = converter.to_doc_format(all_sentences)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='_gb4e.tex', delete=False, encoding='utf-8') as f:
            f.write(gb4e_content)
            gb4e_path = f.name
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='_doc.txt', delete=False, encoding='utf-8') as f:
            f.write(doc_content)
            doc_path = f.name
        
        progress(0.7, desc="ZIPファイルを作成中...")
        
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(gb4e_path, 'sentences_gb4e.tex')
            zipf.write(doc_path, 'sentences_doc.txt')
            
            if include_audio and audio_path and converter.audio_available:
                progress(0.8, desc="音声ファイルを分割中...")
                
                for i, sent in enumerate(all_sentences, 1):
                    if sent.get('start_time') is not None and sent.get('end_time') is not None:
                        speaker = sent.get('speaker', '')
                        text_for_name = sent.get('text0') or sent.get('text') or ''
                        safe_text = re.sub(r'[^\w\s-]', '', text_for_name[:30])
                        safe_text = re.sub(r'\s+', '_', safe_text.strip())
                        safe_speaker = re.sub(r'[^\w\s-]', '', speaker)
                        filename = f"audio_segments/{i:03d}_{safe_speaker}_{safe_text}.wav"
                        
                        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_wav:
                            success = converter.save_audio_segment(
                                sent['start_time'],
                                sent['end_time'],
                                tmp_wav.name,
                                padding_ms
                            )
                            if success:
                                zipf.write(tmp_wav.name, filename)
                            os.unlink(tmp_wav.name)
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.zip', delete=False) as f:
            f.write(zip_buffer.getvalue())
            zip_path = f.name
        
        progress(1.0, desc="完了！")
        
        status_msg = f"✅ 変換完了！\n"
        status_msg += f"📊 抽出された文数: {len(all_sentences)}\n"
        status_msg += f"📝 GB4Eスタイル: {gb4e_style}\n"
        status_msg += f"\n👥 話者情報:\n"
        for info in speaker_info_list:
            status_msg += f"  - {info['name']}: {info['count']}文 ({info['mode']})\n"
        if include_audio and audio_path and converter.audio_available:
            status_msg += f"\n🎵 音声ファイル: {len(all_sentences)}個"
        
        return gb4e_path, doc_path, zip_path, status_msg
    
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        return None, None, None, f"エラー: {str(e)}\n\n{error_detail}"


# Gradio UI
custom_css = """
/* ========== 基本設定 ========== */
:root { color-scheme: light !important; }
.gradio-container, .gradio-container * { color-scheme: light !important; }

/* コンテナ全体 */
.gradio-container { background: #ffffff !important; }

/* セクションボックス */
.section-box { 
    background: #ffffff !important; 
    padding: 16px 20px; 
    border-radius: 6px; 
    margin-bottom: 8px; 
    border: 1px solid #e0e0e0;
}
.section-accent { 
    background: #f8f8f8 !important; 
    padding: 16px 20px; 
    border-radius: 6px; 
    margin-bottom: 8px; 
    border: 1px solid #e0e0e0;
}
.section-title { margin-bottom: 10px !important; font-weight: 600; color: #333333 !important; }

/* 話者セクション */
.speaker-section {
    background: #fafafa !important;
    padding: 12px 16px;
    border-radius: 6px;
    margin-bottom: 8px;
    border: 1px solid #e8e8e8;
}
.speaker-header {
    font-weight: 600;
    color: #555555 !important;
    margin-bottom: 8px;
}

/* すべてのテキスト要素 */
h1, h2, h3, h4, h5, h6, p, label, span, div { color: #333333 !important; }

/* 入力コンポーネント */
input, select, textarea {
    background: #ffffff !important;
    color: #333333 !important;
    border: 1px solid #cccccc !important;
}
input::placeholder, textarea::placeholder {
    color: #999999 !important;
}

/* ========== ドロップダウン（Gradio 5.x対応） ========== */
/* ドロップダウンのinputと表示部分 */
[data-testid="dropdown"] input,
[data-testid="dropdown"] > div,
[data-testid="dropdown"] button,
.wrap > .wrap > input,
.dropdown-container,
.dropdown-container input {
    background: #ffffff !important;
    background-color: #ffffff !important;
    color: #000000 !important;
    border: 1px solid #aaaaaa !important;
}

/* ドロップダウンリスト全体 */
[data-testid="dropdown"] ul,
ul[role="listbox"],
.dropdown-content,
div[role="listbox"] {
    background: #ffffff !important;
    background-color: #ffffff !important;
    border: 1px solid #aaaaaa !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15) !important;
}

/* ドロップダウンの各項目 */
[data-testid="dropdown"] li,
li[role="option"],
.dropdown-item {
    background: #ffffff !important;
    background-color: #ffffff !important;
    color: #000000 !important;
    padding: 8px 12px !important;
}

/* ホバー時 */
[data-testid="dropdown"] li:hover,
li[role="option"]:hover {
    background: #f0f0f0 !important;
    background-color: #f0f0f0 !important;
}

/* 選択済み項目 */
[data-testid="dropdown"] li[aria-selected="true"],
li[role="option"][aria-selected="true"] {
    background: #ff8c00 !important;
    background-color: #ff8c00 !important;
    color: #ffffff !important;
}

/* ========== ラジオボタン（Gradio 5.x対応） ========== */
/* ラジオボタンの各項目 - 通常状態 */
[data-testid="radio"] label,
[role="radiogroup"] label,
.radio-group label,
.gr-radio label,
label[data-testid="radio-label"] {
    background: #ffffff !important;
    background-color: #ffffff !important;
    color: #333333 !important;
    border: 2px solid #aaaaaa !important;
    padding: 10px 20px !important;
    border-radius: 8px !important;
    margin: 4px !important;
    cursor: pointer !important;
    font-weight: normal !important;
    transition: all 0.2s !important;
}

/* ラジオボタン - 選択状態 */
[data-testid="radio"] label[data-checked="true"],
[data-testid="radio"] label.selected,
[role="radiogroup"] label[data-checked="true"],
label[data-testid="radio-label"][data-checked="true"],
label:has(input[type="radio"]:checked),
input[type="radio"]:checked + label,
input[type="radio"]:checked ~ label,
.radio-group label.selected {
    background: #ff8c00 !important;
    background-color: #ff8c00 !important;
    color: #ffffff !important;
    border: 2px solid #ff8c00 !important;
    font-weight: 700 !important;
}

/* ラジオボタンのホバー */
[data-testid="radio"] label:hover,
[role="radiogroup"] label:hover {
    border-color: #ff8c00 !important;
}

/* ラジオボタンの丸いインジケータを隠す（オプション） */
[data-testid="radio"] input[type="radio"],
[role="radiogroup"] input[type="radio"] {
    accent-color: #ff8c00 !important;
}

/* ========== チェックボックス（Gradio 5.x対応） ========== */
/* チェックボックス - 通常状態 */
[data-testid="checkbox"] label,
.gr-checkbox label,
label:has(input[type="checkbox"]) {
    background: #ffffff !important;
    background-color: #ffffff !important;
    color: #333333 !important;
    border: 2px solid #aaaaaa !important;
    padding: 10px 20px !important;
    border-radius: 8px !important;
    cursor: pointer !important;
}

/* チェックボックス - 選択状態 */
[data-testid="checkbox"] label[data-checked="true"],
[data-testid="checkbox"] label.selected,
label:has(input[type="checkbox"]:checked),
input[type="checkbox"]:checked + label,
input[type="checkbox"]:checked ~ label {
    background: #ff8c00 !important;
    background-color: #ff8c00 !important;
    color: #ffffff !important;
    border: 2px solid #ff8c00 !important;
    font-weight: 700 !important;
}

/* チェックボックスのアイコン色 */
input[type="checkbox"] {
    accent-color: #ff8c00 !important;
}

/* ファイルアップロード */
.gr-file, [data-testid="file"] {
    background: #fafafa !important;
    color: #333333 !important;
    border: 1px dashed #cccccc !important;
}

/* テキストエリア */
.gr-textbox, .gr-textbox textarea {
    background: #ffffff !important;
    color: #333333 !important;
    border: 1px solid #cccccc !important;
}

/* Markdownエリア */
.markdown, .gr-markdown {
    background: transparent !important;
    color: #333333 !important;
}

/* 通常のボタン */
.gr-button, button {
    background: #f0f0f0 !important;
    color: #333333 !important;
    border: 1px solid #cccccc !important;
}
.gr-button:hover, button:hover {
    background: #e0e0e0 !important;
}

/* 変換実行ボタン（オレンジ） */
.gr-button-primary, button.primary, button[variant="primary"] {
    background: #ff8c00 !important;
    color: #ffffff !important;
    border: none !important;
    font-weight: 600 !important;
}
.gr-button-primary:hover, button.primary:hover {
    background: #e07b00 !important;
}

/* ファイルアップロードセクション */
.file-upload-section label { font-size: 1.1rem !important; font-weight: 500 !important; color: #333333 !important; }
.file-upload-section [data-testid="block-label"] { font-size: 1.1rem !important; }

/* ダウンロードセクション */
.download-section { background: #f0fff4 !important; border: 2px solid #68d391 !important; }
.download-section label { font-size: 1.1rem !important; font-weight: 600 !important; color: #333333 !important; }
.download-section a { 
    background: #48bb78 !important; 
    color: #ffffff !important; 
    padding: 10px 16px !important; 
    border-radius: 6px !important;
    font-size: 1rem !important;
    font-weight: 500 !important;
}
.download-section a:hover { background: #38a169 !important; }

/* タイトル */
.sub-info { color: #666666 !important; font-size: 1rem !important; }
.sub-info a { color: #ff8c00 !important; text-decoration: underline !important; }
.sub-info a:hover { color: #e07b00 !important; }

/* footer */
footer { background: #ffffff !important; color: #666666 !important; }

/* 話者数スライダー */
.speaker-count-slider { max-width: 200px; }
input[type="range"] { accent-color: #ff8c00 !important; }

/* スライダーの数値表示 */
.gr-slider input[type="number"] {
    background: #ffffff !important;
    color: #333333 !important;
}
"""

light_theme = gr.themes.Base(
    primary_hue="orange",
    neutral_hue="gray"
).set(
    body_background_fill="#ffffff",
    body_background_fill_dark="#ffffff",
    body_text_color="#333333",
    body_text_color_dark="#333333",
    block_background_fill="#f8f8f8",
    block_background_fill_dark="#f8f8f8",
    block_label_background_fill="#f8f8f8",
    block_label_background_fill_dark="#f8f8f8",
    block_title_background_fill="#f8f8f8",
    block_title_background_fill_dark="#f8f8f8",
    input_background_fill="#ffffff",
    input_background_fill_dark="#ffffff",
    input_border_color="#cccccc",
    input_border_color_dark="#cccccc",
    button_primary_background_fill="#ff8c00",
    button_primary_background_fill_dark="#ff8c00",
    button_primary_text_color="#ffffff",
    button_primary_text_color_dark="#ffffff",
    button_secondary_background_fill="#f0f0f0",
    button_secondary_background_fill_dark="#f0f0f0",
    button_secondary_text_color="#333333",
    button_secondary_text_color_dark="#333333",
    panel_background_fill="#f8f8f8",
    panel_background_fill_dark="#f8f8f8",
    border_color_primary="#e0e0e0",
    border_color_primary_dark="#e0e0e0",
)

with gr.Blocks(title="eaftox - EAF変換ツール（複数話者対応）", css=custom_css, theme=light_theme) as app:
    gr.HTML("""
        <div style='display: flex; align-items: baseline; gap: 20px; flex-wrap: wrap;'>
            <div style='font-size: 7rem; font-weight: 800; color: #333333; letter-spacing: -0.02em; line-height: 1.1;'>eaftox</div>
            <div style='font-size: 0.9rem; color: #888888;'>created by Michinori Shimoji (<a href="https://mshimoji.com" target="_blank" style="color: #ff8c00;">mshimoji.com</a>) &nbsp;|&nbsp; v2026-03-10-r6</div>
        </div>
    """)
    gr.Markdown("EAFファイルを例文形式（GB4E / テキスト）に変換　｜　複数話者対応　｜　[解説記事はこちら](https://note.com/lingfieldwork/n/nb2eb90735124?sub_rt=share_sb)", elem_classes="sub-info")
    
    # 状態管理
    tier_list_state = gr.State([])
    
    # セクション1: ファイル
    with gr.Group(elem_classes="section-accent file-upload-section"):
        gr.Markdown("**ファイル**", elem_classes="section-title")
        with gr.Row():
            eaf_input = gr.File(label="EAFファイル", file_types=[".eaf"], scale=1)
            audio_input = gr.File(label="音声ファイル（任意）", file_types=[".wav", ".mp3"], scale=1)
    
    # ティア情報表示
    tier_info_output = gr.Markdown(visible=False)
    
    # セクション2: 話者設定
    with gr.Group(elem_classes="section-box"):
        gr.Markdown("**話者設定**", elem_classes="section-title")
        
        with gr.Row():
            num_speakers = gr.Slider(
                minimum=1, maximum=MAX_SPEAKERS, value=1, step=1,
                label="話者数", elem_classes="speaker-count-slider"
            )
            with gr.Column(scale=3):
                gr.Markdown("""
| モード | 出力 | 必要なティア |
|--------|------|-------------|
| シンプル3層 | text → gloss → (pos) → trans | text, gloss, trans |
| 3層 | text → gloss → (pos) → trans | text, morph, gloss, trans |
| 4層 | text0 → text → gloss → (pos) → trans | text0, text, morph, gloss, trans |
                """)
        
        # 話者セクション（動的表示）
        speaker_sections = []
        speaker_names = []
        speaker_modes = []
        speaker_text0s = []
        speaker_texts = []
        speaker_morphs = []
        speaker_glosses = []
        speaker_poses = []
        speaker_transes = []
        
        for i in range(MAX_SPEAKERS):
            with gr.Group(visible=(i == 0), elem_classes="speaker-section") as speaker_group:
                gr.Markdown(f"**話者 {i+1}**", elem_classes="speaker-header")
                
                with gr.Row():
                    speaker_name = gr.Textbox(
                        label="話者名", value=f"話者{i+1}", scale=1
                    )
                    speaker_mode = gr.Radio(
                        ["シンプル3層", "3層", "4層"],
                        label="モード", value="3層", scale=2
                    )
                
                with gr.Row():
                    text0_dropdown = gr.Dropdown(label="text0", choices=["（なし）"], value="（なし）", visible=False)
                    text_dropdown = gr.Dropdown(label="text", choices=["（なし）"], value="（なし）")
                    morph_dropdown = gr.Dropdown(label="morph", choices=["（なし）"], value="（なし）", visible=False)
                    gloss_dropdown = gr.Dropdown(label="gloss", choices=["（なし）"], value="（なし）")
                    pos_dropdown = gr.Dropdown(label="pos（任意）", choices=["（なし）"], value="（なし）")
                    trans_dropdown = gr.Dropdown(label="trans", choices=["（なし）"], value="（なし）")
                
                speaker_sections.append(speaker_group)
                speaker_names.append(speaker_name)
                speaker_modes.append(speaker_mode)
                speaker_text0s.append(text0_dropdown)
                speaker_texts.append(text_dropdown)
                speaker_morphs.append(morph_dropdown)
                speaker_glosses.append(gloss_dropdown)
                speaker_poses.append(pos_dropdown)
                speaker_transes.append(trans_dropdown)
                
                # モード変更時のUI更新（各話者ごと）
                speaker_mode.change(
                    fn=update_mode_visibility,
                    inputs=[speaker_mode],
                    outputs=[text0_dropdown, morph_dropdown]
                )
    
    # セクション3: 出力オプション
    with gr.Group(elem_classes="section-accent"):
        gr.Markdown("**出力オプション**", elem_classes="section-title")
        with gr.Row():
            gb4e_style = gr.Radio(
                ["標準版", "行間調整版", "最小限版"],
                label="GB4Eスタイル",
                value="標準版",
                scale=2
            )
            include_audio = gr.Checkbox(label="音声分割", value=True, scale=1)
            padding_slider = gr.Slider(0, 500, value=100, step=50, label="前後余白（ms）", scale=1)
    
    # 変換ボタン
    convert_btn = gr.Button("変換実行", variant="primary")
    
    # セクション4: 出力
    with gr.Group(elem_classes="section-accent download-section"):
        gr.Markdown("**📥 出力ファイル**", elem_classes="section-title")
        with gr.Row():
            status_output = gr.Textbox(label="処理状況", lines=6, scale=2)
            gb4e_output = gr.File(label="📄 GB4E (.tex)", scale=1)
            doc_output = gr.File(label="📄 テキスト (.txt)", scale=1)
            zip_output = gr.File(label="📦 ZIP", scale=1)
    
    # 話者数変更時のUI更新
    num_speakers.change(
        fn=update_speaker_visibility,
        inputs=[num_speakers],
        outputs=speaker_sections
    )
    
    # EAFファイル読み込み時
    def on_eaf_upload(eaf_file):
        tier_info, tier_list = analyze_eaf(eaf_file)
        
        if not tier_list:
            return [tier_info, []] + [gr.update(choices=["（なし）"], value="（なし）")] * (6 * MAX_SPEAKERS)
        
        choices_with_none = ["（なし）"] + tier_list
        
        # デフォルト値推測
        def guess_default(keywords, exclude=None):
            for tier in tier_list:
                tier_lower = tier.lower()
                if exclude:
                    if any(ex in tier_lower for ex in exclude):
                        continue
                for kw in keywords:
                    if kw in tier_lower:
                        return tier
            return "（なし）"
        
        updates = [tier_info, tier_list]
        
        for i in range(MAX_SPEAKERS):
            # 話者番号のサフィックスを考慮した推測
            suffix = str(i + 1) if i > 0 else ""
            suffix_patterns = [f"_{i+1}", f"-{i+1}", f"{i+1}", f"_{chr(65+i)}", f"-{chr(65+i)}", chr(65+i)]
            
            def guess_with_suffix(keywords, exclude=None):
                # まずサフィックス付きで検索
                for tier in tier_list:
                    tier_lower = tier.lower()
                    if exclude:
                        if any(ex in tier_lower for ex in exclude):
                            continue
                    for kw in keywords:
                        for suf in suffix_patterns:
                            if kw + suf.lower() in tier_lower or suf.lower() + kw in tier_lower:
                                return tier
                # サフィックスなしで検索（最初の話者のみ）
                if i == 0:
                    return guess_default(keywords, exclude)
                return "（なし）"
            
            updates.append(gr.update(choices=choices_with_none, value=guess_with_suffix(['text0'])))
            updates.append(gr.update(choices=choices_with_none, value=guess_with_suffix(['text'], exclude=['text0'])))
            updates.append(gr.update(choices=choices_with_none, value=guess_with_suffix(['morph'])))
            updates.append(gr.update(choices=choices_with_none, value=guess_with_suffix(['gloss'])))
            updates.append(gr.update(choices=choices_with_none, value=guess_with_suffix(['pos'])))
            updates.append(gr.update(choices=choices_with_none, value=guess_with_suffix(['trans', 'translation'])))
        
        return updates
    
    # EAFアップロード時のドロップダウン更新
    all_tier_dropdowns = []
    for i in range(MAX_SPEAKERS):
        all_tier_dropdowns.extend([
            speaker_text0s[i], speaker_texts[i], speaker_morphs[i],
            speaker_glosses[i], speaker_poses[i], speaker_transes[i]
        ])
    
    eaf_input.change(
        fn=on_eaf_upload,
        inputs=[eaf_input],
        outputs=[tier_info_output, tier_list_state] + all_tier_dropdowns
    )
    
    # 変換実行
    all_speaker_inputs = []
    for i in range(MAX_SPEAKERS):
        all_speaker_inputs.extend([
            speaker_names[i], speaker_modes[i],
            speaker_text0s[i], speaker_texts[i], speaker_morphs[i],
            speaker_glosses[i], speaker_poses[i], speaker_transes[i]
        ])
    
    convert_btn.click(
        fn=convert_eaf,
        inputs=[eaf_input, audio_input, include_audio, padding_slider, gb4e_style, num_speakers] + all_speaker_inputs,
        outputs=[gb4e_output, doc_output, zip_output, status_output]
    )


if __name__ == "__main__":
    app.launch(share=True)
