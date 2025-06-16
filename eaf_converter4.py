# Complete EAF File Converter Script (All fixes integrated + Leipzig.sty support)
# - 4-tier gloss support (text0, morph, gloss, translation)
# - GB4E format using \glll
# - Leipzig.sty automatic small caps conversion
# - text1 layer boundary symbols (=, -) reflected in morph/gloss layers
# - Desktop output issues fixed
# - Audio splitting functionality included

import xml.etree.ElementTree as ET
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Dict, List, Optional
import time
import platform

# Audio processing library imports
AUDIO_LIBRARY = None
try:
    import librosa
    import soundfile as sf
    AUDIO_LIBRARY = 'librosa'
    print("✅ Using librosa + soundfile")
except ImportError:
    try:
        from pydub import AudioSegment
        AUDIO_LIBRARY = 'pydub'
        print("✅ Using pydub")
    except ImportError:
        try:
            import wave
            import numpy as np
            AUDIO_LIBRARY = 'wave'
            print("✅ Using standard library wave (WAV files only)")
        except ImportError:
            AUDIO_LIBRARY = None
            print("⚠️ No audio processing library (text conversion only)")

def get_desktop_path():
    """Get desktop path (improved version with fallback support)"""
    system = platform.system()
    
    desktop_candidates = []
    
    if system == "Windows":
        desktop_candidates = [
            os.path.join(os.path.expanduser("~"), "Desktop"),
            os.path.join(os.path.expanduser("~"), "デスクトップ"),
            os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop"),
            os.path.join(os.path.expanduser("~"), "OneDrive", "デスクトップ"),
            os.path.join(os.environ.get("USERPROFILE", ""), "Desktop"),
            os.path.join(os.environ.get("USERPROFILE", ""), "デスクトップ")
        ]
    elif system == "Darwin":  # macOS
        desktop_candidates = [
            os.path.join(os.path.expanduser("~"), "Desktop"),
            os.path.join(os.path.expanduser("~"), "デスクトップ")
        ]
    else:  # Linux
        desktop_candidates = [
            os.path.join(os.path.expanduser("~"), "Desktop"),
            os.path.join(os.path.expanduser("~"), "デスクトップ"),
            os.path.join(os.path.expanduser("~"), "Documents")
        ]
    
    # Find writable desktop path
    for candidate in desktop_candidates:
        if os.path.exists(candidate) and os.access(candidate, os.W_OK):
            print(f"✅ Desktop path confirmed: {candidate}")
            return candidate
    
    # Fallback: home directory
    home_dir = os.path.expanduser("~")
    print(f"⚠️ Desktop not found, using home directory: {home_dir}")
    return home_dir

def ensure_directory_writable(path):
    """Check and create directory with write permissions"""
    path = Path(path)
    try:
        path.mkdir(parents=True, exist_ok=True)
        # Test write
        test_file = path / ".write_test"
        with open(test_file, 'w') as f:
            f.write("test")
        test_file.unlink()
        return True
    except Exception as e:
        print(f"❌ Directory creation/write error: {e}")
        return False

def save_file_safely(file_path, content, encoding='utf-8'):
    """Save file safely"""
    try:
        file_path = Path(file_path)
        # Ensure directory
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w', encoding=encoding, newline='\n') as f:
            f.write(content)
        
        print(f"✅ File saved successfully: {file_path}")
        return True
    except Exception as e:
        print(f"❌ File save failed {file_path}: {e}")
        return False

class EAFConverter:
    def __init__(self, eaf_file_path: str, wav_file_path: str = None):
        self.eaf_file_path = eaf_file_path
        self.wav_file_path = wav_file_path
        self.tree = None
        self.root = None
        self.time_slots = {}
        self.tiers = {}
        
        # Audio processing attributes
        self.audio_data = None
        self.sample_rate = None
        self.audio_available = False
        
    def load_audio(self):
        """Load audio file"""
        if not self.wav_file_path:
            print("No audio file specified. Text conversion only.")
            return False
            
        if not os.path.exists(self.wav_file_path):
            print(f"Audio file not found: {self.wav_file_path}")
            return False
            
        if AUDIO_LIBRARY is None:
            print("Audio library not available. Audio splitting not possible.")
            return False
            
        try:
            if AUDIO_LIBRARY == 'librosa':
                self.audio_data, self.sample_rate = librosa.load(self.wav_file_path, sr=None)
                print(f"Audio file loaded: {self.wav_file_path}")
                print(f"Sample rate: {self.sample_rate}Hz, Length: {len(self.audio_data)/self.sample_rate:.2f}s")
                
            elif AUDIO_LIBRARY == 'pydub':
                if self.wav_file_path.lower().endswith('.wav'):
                    self.audio_data = AudioSegment.from_wav(self.wav_file_path)
                elif self.wav_file_path.lower().endswith('.mp3'):
                    self.audio_data = AudioSegment.from_mp3(self.wav_file_path)
                else:
                    self.audio_data = AudioSegment.from_file(self.wav_file_path)
                self.sample_rate = self.audio_data.frame_rate
                print(f"Audio file loaded: {self.wav_file_path}")
                print(f"Sample rate: {self.sample_rate}Hz, Length: {len(self.audio_data)/1000:.2f}s")
                
            elif AUDIO_LIBRARY == 'wave':
                with wave.open(self.wav_file_path, 'rb') as wav_file:
                    self.sample_rate = wav_file.getframerate()
                    frames = wav_file.readframes(wav_file.getnframes())
                    self.audio_data = np.frombuffer(frames, dtype=np.int16)
                print(f"Audio file loaded: {self.wav_file_path}")
                print(f"Sample rate: {self.sample_rate}Hz, Length: {len(self.audio_data)/self.sample_rate:.2f}s")
                
            self.audio_available = True
            return True
            
        except Exception as e:
            print(f"Audio file loading error: {e}")
            return False
        
    def parse_eaf(self):
        """Parse EAF file"""
        try:
            self.tree = ET.parse(self.eaf_file_path)
            self.root = self.tree.getroot()
            print(f"EAF file loaded successfully: {self.eaf_file_path}")
        except ET.ParseError as e:
            print(f"XML parse error: {e}")
            return False
        except FileNotFoundError:
            print(f"File not found: {self.eaf_file_path}")
            return False
            
        # Get time slots
        time_order = self.root.find('TIME_ORDER')
        if time_order is not None:
            for time_slot in time_order.findall('TIME_SLOT'):
                slot_id = time_slot.get('TIME_SLOT_ID')
                time_value = time_slot.get('TIME_VALUE')
                self.time_slots[slot_id] = int(time_value) if time_value else 0
        
        print(f"Time slots: {len(self.time_slots)}")
        
        # Display tier information
        print("\nAvailable tiers:")
        for tier in self.root.findall('TIER'):
            tier_id = tier.get('TIER_ID')
            print(f"  - {tier_id}")
            
        # Get tiers (check both ALIGNABLE_ANNOTATION and REF_ANNOTATION)
        for tier in self.root.findall('TIER'):
            tier_id = tier.get('TIER_ID')
            self.tiers[tier_id] = []
            
            # Check ALIGNABLE_ANNOTATION
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
            
            # Also check REF_ANNOTATION
            for annotation in tier.findall('.//REF_ANNOTATION'):
                ref_id = annotation.get('ANNOTATION_REF')
                value_elem = annotation.find('ANNOTATION_VALUE')
                value = value_elem.text if value_elem is not None else ""
                
                # Get time from referenced annotation
                ref_start, ref_end = self._get_ref_time(ref_id)
                
                self.tiers[tier_id].append({
                    'start_time': ref_start,
                    'end_time': ref_end,
                    'value': value.strip() if value else "",
                    'type': 'REF',
                    'ref_id': ref_id
                })
            
            # Sort by start time
            self.tiers[tier_id].sort(key=lambda x: x['start_time'])
            print(f"  {tier_id}: {len(self.tiers[tier_id])} annotations")
        
        return True
    
    def _get_ref_time(self, ref_id: str) -> tuple:
        """Get time from REF_ANNOTATION reference"""
        # Search all tiers for referenced annotation
        for tier in self.root.findall('TIER'):
            for annotation in tier.findall('.//ALIGNABLE_ANNOTATION'):
                if annotation.get('ANNOTATION_ID') == ref_id:
                    start_id = annotation.get('TIME_SLOT_REF1')
                    end_id = annotation.get('TIME_SLOT_REF2')
                    return (self.time_slots.get(start_id, 0), self.time_slots.get(end_id, 0))
            
            # Handle REF_ANNOTATION referencing other REF_ANNOTATION
            for annotation in tier.findall('.//REF_ANNOTATION'):
                if annotation.get('ANNOTATION_ID') == ref_id:
                    nested_ref_id = annotation.get('ANNOTATION_REF')
                    if nested_ref_id:
                        return self._get_ref_time(nested_ref_id)
        
        return (0, 0)
    
    def _convert_leipzig_glosses(self, gloss_text: str) -> str:
        """Convert uppercase grammatical morpheme symbols according to Leipzig.sty rules"""
        if not gloss_text:
            return gloss_text
        
        # Double backslashes to avoid tab character issues
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
            'DEF': '\\\\textsc{def}', 'INDEF': '\\\\textsc{indef}', 'COM': '\\\\textsc{com}',
            'INF': '\\\\textsc{inf}', 'SEQ': '\\\\textsc{seq}', 'FIL': '\\\\textsc{fil}'
        }
        
        result = gloss_text
        
        # More careful conversion: strict word boundary check
        for original, replacement in leipzig_mapping.items():
            pattern = r'(?<![A-Za-z])' + re.escape(original) + r'(?![A-Za-z])'
            result = re.sub(pattern, replacement, result)
        
        # Auto-convert remaining consecutive uppercase letters
        def convert_unknown_caps(match):
            caps_text = match.group(0)
            return f'\\\\textsc{{{caps_text.lower()}}}'
        
        result = re.sub(r'(?<![A-Za-z])[A-Z]{2,}(?![A-Za-z])', convert_unknown_caps, result)
        
        return result
    
    def _convert_leipzig_back_to_plain(self, text: str) -> str:
        """Convert Leipzig.sty smallcaps commands back to original small caps"""
        if not text:
            return text
        
        def convert_textsc_to_smallcaps(match):
            content = match.group(1)
            # Convert to small caps (using actual Unicode small caps characters)
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
                'def': 'ᴅᴇꜰ', 'indef': 'ɪɴᴅᴇꜰ', 'com': 'ᴄᴏᴍ',
                'inf': 'ɪɴꜰ', 'seq': 'sᴇQ', 'fil': 'ꜰɪʟ'
            }
            
            return smallcap_mapping.get(content.lower(), content.upper())
        
        # Convert \\textsc{...} to small caps
        result = re.sub(r'\\textsc\{([^}]+)\}', convert_textsc_to_smallcaps, text)
        
        # Also convert regular uppercase (2+ characters) to small caps
        def convert_caps_to_smallcaps(match):
            caps_text = match.group(0)
            result_chars = []
            for char in caps_text:
                # Individual character mapping
                char_mapping = {
                    'A': 'ᴀ', 'B': 'ʙ', 'C': 'ᴄ', 'D': 'ᴅ', 'E': 'ᴇ', 'F': 'ꜰ',
                    'G': 'ɢ', 'H': 'ʜ', 'I': 'ɪ', 'J': 'ᴊ', 'K': 'ᴋ', 'L': 'ʟ',
                    'M': 'ᴍ', 'N': 'ɴ', 'O': 'ᴏ', 'P': 'ᴘ', 'Q': 'Q', 'R': 'ʀ',
                    'S': 's', 'T': 'ᴛ', 'U': 'ᴜ', 'V': 'ᴠ', 'W': 'ᴡ', 'X': 'x',
                    'Y': 'ʏ', 'Z': 'ᴢ'
                }
                result_chars.append(char_mapping.get(char, char))
            return ''.join(result_chars)
        
        # Convert consecutive uppercase letters (2+ characters) to small caps
        result = re.sub(r'(?<![A-Za-z])[A-Z]{2,}(?![A-Za-z])', convert_caps_to_smallcaps, result)
        
        return result
    
    def _align_morphs_with_text1(self, text1: str, morph_or_gloss: str) -> str:
        """Adjust morph or gloss layers based on text1 layer morpheme boundary symbols (=, -)"""
        if not text1 or not morph_or_gloss:
            return morph_or_gloss
        
        # Split morph/gloss layer by spaces
        morph_list = morph_or_gloss.split()
        if not morph_list:
            return morph_or_gloss
        
        # Split text1 layer into words
        text1_words = text1.split()
        result_parts = []
        morph_idx = 0
        
        for word in text1_words:
            # Find morpheme boundaries within word (=, -)
            # Split while preserving delimiters
            segments = re.split(r'([=-])', word)
            word_morphs = []
            
            for segment in segments:
                if segment in ['=', '-']:
                    # Keep delimiter (process later)
                    continue
                elif segment.strip():  # Non-empty segment
                    if morph_idx < len(morph_list):
                        word_morphs.append(morph_list[morph_idx])
                        morph_idx += 1
            
            # Combine morphemes within word with delimiters
            if word_morphs:
                # Restore original word's delimiter pattern
                morphs_with_delims = []
                morph_pos = 0
                
                for segment in segments:
                    if segment in ['=', '-']:
                        # Add delimiter to morpheme
                        if morphs_with_delims and morph_pos > 0:
                            # Add delimiter to previous morpheme
                            morphs_with_delims[-1] += segment
                    elif segment.strip() and morph_pos < len(word_morphs):
                        morphs_with_delims.append(word_morphs[morph_pos])
                        morph_pos += 1
                
                # Concatenate morphemes with delimiters without spaces
                combined_morphs = []
                temp_morph = ""
                
                for morph in morphs_with_delims:
                    if morph.endswith('=') or morph.endswith('-'):
                        # Ends with delimiter, concatenate with next
                        temp_morph += morph
                    else:
                        # Doesn't end with delimiter
                        if temp_morph:
                            # Previous concatenation pending
                            combined_morphs.append(temp_morph + morph)
                            temp_morph = ""
                        else:
                            # Independent morpheme
                            combined_morphs.append(morph)
                
                # Handle remaining concatenation pending
                if temp_morph:
                    combined_morphs.append(temp_morph)
                
                result_parts.extend(combined_morphs)
        
        return ' '.join(result_parts)
    
    def _split_sentences_by_punctuation_multilayer(self, text0: str, text1: str, morph: str, gloss: str, translation: str, start_time: int = 0, end_time: int = 0) -> List[Dict]:
        """Multi-layer sentence splitting (based on text0)"""
        # Pattern to detect sentence-ending punctuation
        sentence_pattern = r'([.?!]+)'
        
        # Split text0 layer by sentence-ending punctuation
        text0_parts = re.split(sentence_pattern, text0)
        
        sentences = []
        current_text0 = ""
        
        # Split each layer by spaces
        text1_words = text1.split() if text1 else []
        morph_words = morph.split() if morph else []
        gloss_words = gloss.split() if gloss else []
        
        text1_idx = 0
        morph_idx = 0
        gloss_idx = 0
        
        # For time calculation
        total_chars = len(text0.replace('.', '').replace('?', '').replace('!', ''))
        current_chars = 0
        
        for part in text0_parts:
            # Check if it's punctuation
            is_punctuation = bool(re.match(r'^[.?!]+$', part))
            
            if is_punctuation:
                # Sentence-ending punctuation
                current_text0 += part
                
                # Complete current sentence
                if current_text0.strip():
                    # Calculate corresponding word count
                    clean_text0 = current_text0.replace('.', '').replace('?', '').replace('!', '')
                    text0_words_count = len(clean_text0.split())
                    
                    # Get corresponding text1, morph, gloss
                    sent_text1 = text1_words[text1_idx:text1_idx + text0_words_count] if text1_idx < len(text1_words) else []
                    sent_morphs = morph_words[morph_idx:morph_idx + text0_words_count] if morph_idx < len(morph_words) else []
                    sent_glosses = gloss_words[gloss_idx:gloss_idx + text0_words_count] if gloss_idx < len(gloss_words) else []
                    
                    # Estimate time
                    sentence_chars = len(clean_text0)
                    if total_chars > 0 and start_time != end_time:
                        char_ratio = sentence_chars / total_chars
                        duration = end_time - start_time
                        sentence_start = start_time + int((current_chars / total_chars) * duration)
                        sentence_end = sentence_start + int(char_ratio * duration)
                    else:
                        sentence_start = start_time
                        sentence_end = end_time
                    
                    sentences.append({
                        'text0': current_text0.strip(),
                        'text1': ' '.join(sent_text1),
                        'morph': ' '.join(sent_morphs),
                        'gloss': ' '.join(sent_glosses),
                        'translation': translation,  # Translation shared for all
                        'start_time': sentence_start,
                        'end_time': sentence_end
                    })
                    
                    # Update indices
                    text1_idx += text0_words_count
                    morph_idx += text0_words_count
                    gloss_idx += text0_words_count
                    current_chars += sentence_chars
                    current_text0 = ""
            
            elif part.strip():
                # Regular text
                current_text0 += part
        
        # Handle remaining text
        if current_text0.strip():
            # Use remaining layers
            remaining_text1 = text1_words[text1_idx:] if text1_idx < len(text1_words) else []
            remaining_morphs = morph_words[morph_idx:] if morph_idx < len(morph_words) else []
            remaining_glosses = gloss_words[gloss_idx:] if gloss_idx < len(gloss_words) else []
            
            # Calculate remaining time
            sentence_chars = len(current_text0.replace('.', '').replace('?', '').replace('!', ''))
            if total_chars > 0 and start_time != end_time:
                char_ratio = sentence_chars / total_chars
                duration = end_time - start_time
                sentence_start = start_time + int((current_chars / total_chars) * duration)
                sentence_end = sentence_start + int(char_ratio * duration)
            else:
                sentence_start = start_time
                sentence_end = end_time
            
            sentences.append({
                'text0': current_text0.strip(),
                'text1': ' '.join(remaining_text1),
                'morph': ' '.join(remaining_morphs),
                'gloss': ' '.join(remaining_glosses),
                'translation': translation,
                'start_time': sentence_start,
                'end_time': sentence_end
            })
        
        return sentences if sentences else [{
            'text0': text0, 
            'text1': text1,
            'morph': morph, 
            'gloss': gloss, 
            'translation': translation,
            'start_time': start_time,
            'end_time': end_time
        }]
    
    def extract_sentences(self, tier_names: Dict[str, str] = None) -> List[Dict]:
        """Extract text0, text1, morph, gloss, translation, and time info per sentence"""
        # Default tier names (adjust to actual tier names)
        if tier_names is None:
            tier_names = {
                'text0': 'text0',
                'text1': 'text1',
                'morph': 'morph', 
                'gloss': 'gloss',
                'translation': 'trans'
            }
        
        sentences = []
        
        # Find corresponding segments from each tier
        text0_tier = self.tiers.get(tier_names['text0'], [])
        text1_tier = self.tiers.get(tier_names['text1'], [])
        morph_tier = self.tiers.get(tier_names['morph'], [])
        gloss_tier = self.tiers.get(tier_names['gloss'], [])
        translation_tier = self.tiers.get(tier_names['translation'], [])
        
        print(f"\nExtraction targets:")
        print(f"  text0: {len(text0_tier)} items")
        print(f"  text1: {len(text1_tier)} items")
        print(f"  morph: {len(morph_tier)} items")
        print(f"  gloss: {len(gloss_tier)} items")
        print(f"  translation: {len(translation_tier)} items")
        
        # Synchronize other layers based on text0
        for i, text0_annotation in enumerate(text0_tier):
            if not text0_annotation['value']:
                continue
                
            start_time = text0_annotation['start_time']
            end_time = text0_annotation['end_time']
            
            # Find corresponding text1, morph, gloss, translation
            text1 = self._find_overlapping_annotation(text1_tier, start_time, end_time)
            morph = self._find_overlapping_annotation(morph_tier, start_time, end_time)
            gloss = self._find_overlapping_annotation(gloss_tier, start_time, end_time)
            translation = self._find_overlapping_annotation(translation_tier, start_time, end_time)
            
            # Adjust morph and gloss based on text1 morpheme boundaries
            aligned_morph = self._align_morphs_with_text1(text1, morph)
            aligned_gloss = self._align_morphs_with_text1(text1, gloss)
            
            # Split by sentence-ending punctuation (with time info)
            split_sentences = self._split_sentences_by_punctuation_multilayer(
                text0_annotation['value'], text1, aligned_morph, aligned_gloss, translation, start_time, end_time
            )
            
            sentences.extend(split_sentences)
        
        print(f"\nExtracted sentences: {len(sentences)}")
        return sentences
    
    def _find_overlapping_annotation(self, tier_data: List[Dict], start_time: int, end_time: int) -> str:
        """Find and combine annotations that overlap with specified time range"""
        matching_annotations = []
        
        for annotation in tier_data:
            # Check if time ranges overlap
            overlap_start = max(annotation['start_time'], start_time)
            overlap_end = min(annotation['end_time'], end_time)
            
            if overlap_start < overlap_end or (annotation['start_time'] == start_time and annotation['end_time'] == end_time):
                # Has overlap or exact match
                matching_annotations.append(annotation)
        
        # Sort overlapping annotations by time and combine
        matching_annotations.sort(key=lambda x: x['start_time'])
        return ' '.join([ann['value'] for ann in matching_annotations if ann['value']])
    
    def save_audio_segment(self, start_ms: int, end_ms: int, output_path: str, padding_ms: int = 100):
        """Save audio segment for specified time range"""
        if not self.audio_available:
            return False
            
        try:
            # Add padding (small buffer before and after)
            padded_start = max(0, start_ms - padding_ms)
            
            if AUDIO_LIBRARY == 'librosa':
                # Convert milliseconds to sample numbers
                start_sample = int((padded_start / 1000.0) * self.sample_rate)
                end_sample = int((end_ms / 1000.0) * self.sample_rate)
                padded_end_sample = min(len(self.audio_data), end_sample + int((padding_ms / 1000.0) * self.sample_rate))
                
                # Extract audio segment
                audio_segment = self.audio_data[start_sample:padded_end_sample]
                
                # Save to file
                sf.write(output_path, audio_segment, self.sample_rate)
                
            elif AUDIO_LIBRARY == 'pydub':
                padded_end = end_ms + padding_ms
                
                # Extract audio segment
                audio_segment = self.audio_data[padded_start:padded_end]
                
                # Save to file
                audio_segment.export(output_path, format="wav")
                
            elif AUDIO_LIBRARY == 'wave':
                # Convert milliseconds to sample numbers
                start_sample = int((padded_start / 1000.0) * self.sample_rate)
                end_sample = int((end_ms / 1000.0) * self.sample_rate)
                padded_end_sample = min(len(self.audio_data), end_sample + int((padding_ms / 1000.0) * self.sample_rate))
                
                # Extract audio segment
                audio_segment = self.audio_data[start_sample:padded_end_sample]
                
                # Save as WAV file
                with wave.open(output_path, 'wb') as wav_out:
                    wav_out.setnchannels(1)  # Mono
                    wav_out.setsampwidth(2)  # 16bit
                    wav_out.setframerate(self.sample_rate)
                    wav_out.writeframes(audio_segment.tobytes())
            
            return True
            
        except Exception as e:
            print(f"Audio save error: {e}")
            return False
    
    def _convert_ipa_to_tipa(self, text: str) -> str:
        """Convert IPA characters to tipa package format"""
        if not text:
            return text
            
        # IPA to tipa command mapping (added {} for clear separation)
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
        """Convert tipa commands back to original IPA characters"""
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
    
    def _align_four_layers_for_doc(self, text0_line: str, morph_line: str, gloss_line: str) -> tuple:
        """Align word start positions for 4 layers (text0, morph, gloss) in doc format"""
        if not text0_line:
            return text0_line, morph_line, gloss_line
        
        text0_words = text0_line.split()
        morph_words = morph_line.split() if morph_line else []
        gloss_words = gloss_line.split() if gloss_line else []
        
        # More accurate character width calculation
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
        
        # Get maximum word count
        max_len = max(len(text0_words), len(morph_words), len(gloss_words))
        
        aligned_text0_parts = []
        aligned_morph_parts = []
        aligned_gloss_parts = []
        
        for i in range(max_len):
            text0_word = text0_words[i] if i < len(text0_words) else ""
            morph_word = morph_words[i] if i < len(morph_words) else ""
            gloss_word = gloss_words[i] if i < len(gloss_words) else ""
            
            # Calculate width for each layer
            text0_width = char_width(text0_word)
            morph_width = char_width(morph_word)
            gloss_width = char_width(gloss_word)
            
            # Calculate maximum width for 3 layers (minimum 2 character spacing)
            max_width = max(text0_width, morph_width, gloss_width) + 2
            
            # Calculate padding for each layer
            text0_padding = max_width - text0_width
            morph_padding = max_width - morph_width
            gloss_padding = max_width - gloss_width
            
            if i < max_len - 1:  # Not the last word
                aligned_text0_parts.append(text0_word + ' ' * text0_padding if text0_word else ' ' * max_width)
                aligned_morph_parts.append(morph_word + ' ' * morph_padding if morph_word else ' ' * max_width)
                aligned_gloss_parts.append(gloss_word + ' ' * gloss_padding if gloss_word else ' ' * max_width)
            else:  # Last word
                aligned_text0_parts.append(text0_word)
                aligned_morph_parts.append(morph_word)
                aligned_gloss_parts.append(gloss_word)
        
        return ''.join(aligned_text0_parts), ''.join(aligned_morph_parts), ''.join(aligned_gloss_parts)
    
    def to_gb4e_format(self, sentences: List[Dict]) -> str:
        """Convert to gb4e format (4-tier gloss: text0, morph, gloss, translation) - using \\glll + Leipzig.sty support"""
        output = []
        
        # Add LaTeX header
        output.append("% UTF-8 encoding settings")
        output.append("% \\usepackage[utf8]{inputenc}")
        output.append("% \\usepackage{CJKutf8}")
        output.append("% \\usepackage{gb4e}")
        output.append("% \\usepackage{tipa}")
        output.append("% \\usepackage{leipzig}  % Leipzig.sty package")
        output.append("")
        output.append("% With Leipzig.sty, uppercase grammatical symbols are automatically converted to lowercase smallcaps")
        output.append("% IPA characters are automatically converted to tipa commands")
        output.append("")
        
        for i, sentence in enumerate(sentences, 1):
            if not sentence.get('text0'):
                continue
                
            output.append("\\begin{exe}")
            output.append("\\ex")
            
            # 🔥 Important: Use \\glll for 4-tier gloss (3 l's)
            text0_tipa = self._convert_ipa_to_tipa(sentence['text0'])
            output.append(f"\\glll {text0_tipa}\\\\")
            
            # 2nd tier: morph (adjusted based on text1 boundaries)
            if sentence.get('morph'):
                # Apply Leipzig.sty conversion
                leipzig_morph = self._convert_leipzig_glosses(sentence['morph'])
                # Fix double backslashes to single
                leipzig_morph = leipzig_morph.replace('\\\\', '\\')
                output.append(f"      {leipzig_morph}\\\\")
            else:
                output.append("      \\\\")
            
            # 3rd tier: gloss (adjusted based on text1 boundaries + Leipzig.sty conversion)
            if sentence.get('gloss'):
                # Apply Leipzig.sty conversion
                leipzig_gloss = self._convert_leipzig_glosses(sentence['gloss'])
                # Fix double backslashes to single
                leipzig_gloss = leipzig_gloss.replace('\\\\', '\\')
                output.append(f"      {leipzig_gloss}\\\\")
            else:
                output.append("      \\\\")
            
            # 4th tier: translation
            if sentence.get('translation'):
                output.append(f"\\glt  {sentence['translation']}")
            else:
                output.append("\\glt")
            
            output.append("\\end{exe}")
            output.append("")
        
        return "\n".join(output)
    
    def to_doc_format(self, sentences: List[Dict], debug: bool = False) -> str:
        """Doc format (4-tier display: text0, morph, gloss, translation) + small caps conversion"""
        output = []
        
        for i, sentence in enumerate(sentences, 1):
            if not sentence.get('text0'):
                continue
                
            # Example number
            output.append(f"({i})")
            
            # 1st tier: text0 (convert IPA to tipa then back to original)
            text0_tipa = self._convert_ipa_to_tipa(sentence['text0'])
            text0_original = self._convert_tipa_back_to_ipa(text0_tipa)
            
            # 2nd tier: morph (adjusted based on text1 + Leipzig.sty conversion then back to small caps)
            morph_content = sentence.get('morph', '')
            if morph_content:
                leipzig_morph = self._convert_leipzig_glosses(morph_content)
                leipzig_morph = leipzig_morph.replace('\\\\', '\\')  # Fix double backslashes
                morph_content = self._convert_leipzig_back_to_plain(leipzig_morph)
            
            # 3rd tier: gloss (adjusted based on text1 + Leipzig.sty conversion then back to small caps)
            gloss_content = sentence.get('gloss', '')
            if gloss_content:
                leipzig_gloss = self._convert_leipzig_glosses(gloss_content)
                leipzig_gloss = leipzig_gloss.replace('\\\\', '\\')  # Fix double backslashes
                gloss_content = self._convert_leipzig_back_to_plain(leipzig_gloss)
            
            if debug:
                print(f"\n--- Example {i} debug info ---")
                print(f"text0: '{sentence.get('text0', '')}'")
                print(f"text1: '{sentence.get('text1', '')}'")
                print(f"morph: '{morph_content}'")
                print(f"gloss: '{gloss_content}'")
            
            # Align word start positions for 4 layers
            if morph_content and gloss_content:
                # 4-layer simultaneous adjustment (text0, morph, gloss)
                aligned_text0, aligned_morph, aligned_gloss = self._align_four_layers_for_doc(
                    text0_original, morph_content, gloss_content
                )
                
                output.append(aligned_text0)
                output.append(aligned_morph)
                output.append(aligned_gloss)
            elif morph_content:
                # text0 and morph only
                aligned_text0, aligned_morph = self._align_words_for_doc(text0_original, morph_content)
                output.append(aligned_text0)
                output.append(aligned_morph)
                output.append("")
            else:
                # text0 only
                output.append(text0_original)
                output.append("")
                output.append("")
            
            # 4th tier: translation
            if sentence.get('translation'):
                output.append(sentence['translation'])
            else:
                output.append("")
            
            output.append("")
        
        return "\n".join(output)
    
    def _align_words_for_doc(self, text_line: str, gloss_line: str) -> tuple:
        """Align word start positions for doc format (2-layer version)"""
        if not text_line or not gloss_line:
            return text_line, gloss_line
        
        text_words = text_line.split()
        gloss_words = gloss_line.split()
        
        # More accurate character width calculation
        def char_width(s):
            import unicodedata
            width = 0
            for char in s:
                # Use Unicode character categories for more accurate determination
                if unicodedata.east_asian_width(char) in ('F', 'W'):
                    # Full width, Wide characters
                    width += 2
                elif unicodedata.east_asian_width(char) in ('H', 'Na', 'N'):
                    # Half width, Narrow, Neutral characters
                    width += 1
                else:
                    # Others (A=Ambiguous) are environment-dependent, treat as 1
                    width += 1
            return width
        
        # If word counts differ, use the shorter one
        min_len = min(len(text_words), len(gloss_words))
        if len(text_words) != len(gloss_words):
            print(f"Warning: Word count mismatch (text: {len(text_words)}, gloss: {len(gloss_words)})")
        
        aligned_text_parts = []
        aligned_gloss_parts = []
        
        for i in range(min_len):
            text_word = text_words[i]
            gloss_word = gloss_words[i]
            
            text_width = char_width(text_word)
            gloss_width = char_width(gloss_word)
            
            # Calculate maximum width for both words (minimum 2 character spacing)
            max_width = max(text_width, gloss_width) + 2
            
            # Add padding
            text_padding = max_width - text_width
            gloss_padding = max_width - gloss_width
            
            if i < min_len - 1:  # Not the last word
                aligned_text_parts.append(text_word + ' ' * text_padding)
                aligned_gloss_parts.append(gloss_word + ' ' * gloss_padding)
            else:  # Last word
                aligned_text_parts.append(text_word)
                aligned_gloss_parts.append(gloss_word)
        
        # Handle remaining words
        if len(text_words) > min_len:
            remaining_text = ' '.join(text_words[min_len:])
            aligned_text_parts.append(' ' + remaining_text)
        
        if len(gloss_words) > min_len:
            remaining_gloss = ' '.join(gloss_words[min_len:])
            aligned_gloss_parts.append(' ' + remaining_gloss)
        
        return ''.join(aligned_text_parts), ''.join(aligned_gloss_parts)
    
    def split_audio_to_desktop(self, sentences: List[Dict], folder_name: str = None, 
                              padding_ms: int = 100, create_zip: bool = False, output_directory: str = None):
        """Split sentence audio and save to desktop (including text files)"""
        if not self.audio_available:
            print("Audio data not available. Audio splitting will be skipped.")
            return None
        
        # Determine output directory
        if output_directory is None:
            output_directory = get_desktop_path()
        
        print(f"📁 Audio output directory: {output_directory}")
        
        # Determine output folder name
        if not folder_name:
            base_name = Path(self.eaf_file_path).stem
            folder_name = f"{base_name}_sentences"
        
        # Create output directory on desktop
        output_path = Path(output_directory) / folder_name
        if output_path.exists():
            # Backup existing folder
            timestamp = int(time.time())
            backup_path = Path(output_directory) / f"{folder_name}_backup_{timestamp}"
            try:
                shutil.move(str(output_path), str(backup_path))
                print(f"📦 Existing folder backed up: {backup_path}")
            except:
                pass
        
        if not ensure_directory_writable(output_path):
            print(f"❌ Failed to create output directory: {output_path}")
            return None
        
        if not sentences:
            print("No sentences found to split")
            return None
        
        saved_files = []
        
        # Extract audio for each sentence
        for i, sentence in enumerate(sentences, 1):
            if not sentence.get('start_time') or not sentence.get('end_time'):
                print(f"⚠️ Sentence {i} has no time information. Skipping.")
                continue
                
            # Generate filename (numbered)
            safe_text = re.sub(r'[^\w\s-]', '', sentence.get('text0', '')[:30])  # Safe filename
            safe_text = re.sub(r'\s+', '_', safe_text.strip())
            filename = f"{i:03d}_{safe_text}.wav"
            output_file = output_path / filename
            
            # Save audio
            success = self.save_audio_segment(
                sentence['start_time'], 
                sentence['end_time'], 
                str(output_file),
                padding_ms
            )
            
            if success:
                saved_files.append({
                    'number': i,
                    'text': sentence.get('text0', ''),
                    'start_time': sentence['start_time'],
                    'end_time': sentence['end_time'],
                    'duration': sentence['end_time'] - sentence['start_time'],
                    'file_path': str(output_file)
                })
                print(f"✅ Saved: {filename} ({sentence['start_time']}ms - {sentence['end_time']}ms)")
            else:
                print(f"❌ Save failed: {filename}")
        
        # Create GB4E format TeX file (Leipzig.sty compatible)
        print("📝 Creating GB4E format (Leipzig.sty compatible) TeX file...")
        gb4e_content = self.to_gb4e_format(sentences)
        gb4e_file = output_path / 'sentences_gb4e_leipzig.tex'
        save_file_safely(gb4e_file, gb4e_content)
        
        # Create DOC format TXT file (small caps compatible)
        print("📄 Creating DOC format (small caps compatible) TXT file...")
        doc_content = self.to_doc_format(sentences)
        doc_file = output_path / 'sentences_doc.txt'
        save_file_safely(doc_file, doc_content)
        
        # Create summary text file
        summary_content = self._create_summary_content(saved_files, output_path, gb4e_file, doc_file)
        summary_file = output_path / 'audio_summary.txt'
        save_file_safely(summary_file, summary_content)
        
        # Create README file
        readme_content = self._create_readme_content(saved_files, gb4e_file, doc_file, summary_file)
        readme_file = output_path / 'README.txt'
        save_file_safely(readme_file, readme_content)
        
        # Create ZIP file if requested
        zip_file_path = None
        if create_zip and saved_files:
            zip_file_path = Path(output_directory) / f"{folder_name}.zip"
            try:
                with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in output_path.rglob('*'):
                        if file_path.is_file():
                            arcname = file_path.relative_to(output_path)
                            zipf.write(file_path, arcname)
                
                print(f"📦 ZIP file created: {zip_file_path}")
            except Exception as e:
                print(f"❌ ZIP creation error: {e}")
                zip_file_path = None
        
        if saved_files:
            print(f"\n🎉 Audio splitting complete!")
            print(f"🎵 Number of saved audio files: {len(saved_files)}")
            print(f"📝 GB4E format file (Leipzig.sty compatible): {gb4e_file.name}")
            print(f"📄 DOC format file (small caps compatible): {doc_file.name}")
            print(f"📁 Save location: {output_path}")
            print(f"📋 Detailed info: {summary_file.name}")
            print(f"💡 Usage guide: {readme_file.name}")
            if zip_file_path:
                print(f"📦 ZIP file: {zip_file_path}")
        
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
    
    def _create_summary_content(self, saved_files, output_path, gb4e_file, doc_file):
        """Create summary file content"""
        content = []
        content.append("Audio File Splitting Results (Leipzig.sty Compatible Version)\n")
        content.append("="*50 + "\n\n")
        content.append(f"Source file: {self.eaf_file_path}\n")
        content.append(f"Audio file: {self.wav_file_path}\n")
        content.append(f"Total sentences: {len(saved_files)}\n")
        content.append(f"Save location: {output_path}\n\n")
        content.append("📁 Generated files:\n")
        content.append(f"  - GB4E format (Leipzig.sty compatible): {gb4e_file.name}\n")
        content.append(f"  - DOC format (small caps compatible): {doc_file.name}\n")
        content.append(f"  - Audio files: {len(saved_files)} files\n\n")
        content.append("🔧 Leipzig.sty features:\n")
        content.append("  - Auto-convert uppercase grammatical symbols (FOC → \\textsc{foc})\n")
        content.append("  - DOC format converts to Unicode small caps (FOC → ꜰᴏᴄ)\n")
        content.append("  - Auto-convert IPA characters to tipa commands\n\n")
        
        for file_info in saved_files:
            content.append(f"{file_info['number']:03d}. {file_info['text']}\n")
            content.append(f"     Time: {file_info['start_time']}ms - {file_info['end_time']}ms "
                          f"(Length: {file_info['duration']}ms)\n")
            content.append(f"     File: {Path(file_info['file_path']).name}\n\n")
        
        return "".join(content)
    
    def _create_readme_content(self, saved_files, gb4e_file, doc_file, summary_file):
        """Create README file content"""
        content = []
        content.append("EAF File Audio Splitting Results (Leipzig.sty Compatible Version)\n")
        content.append("="*40 + "\n\n")
        content.append("📁 This folder contains the following files:\n\n")
        content.append("🎵 Audio files:\n")
        content.append(f"  - {len(saved_files)} split audio files (001_*.wav ~ {len(saved_files):03d}_*.wav)\n")
        content.append("  - Each file is split by sentence\n\n")
        content.append("📝 Text files:\n")
        content.append(f"  - {gb4e_file.name}: LaTeX gb4e format examples (4-tier gloss: \\glll usage, Leipzig.sty compatible)\n")
        content.append(f"  - {doc_file.name}: Plain text format examples (4-tier display, Unicode small caps compatible)\n")
        content.append(f"  - {summary_file.name}: Detailed splitting information\n")
        content.append(f"  - README.txt: This description file\n\n")
        content.append("💡 Usage:\n")
        content.append("  - Audio files: Play individual sentence audio\n")
        content.append("  - GB4E file: Compile with LaTeX to create linguistic paper examples\n")
        content.append("    Don't forget to add \\usepackage{leipzig}\n")
        content.append("  - DOC file: Can be pasted directly into documents (Unicode small caps display)\n\n")
        content.append("🔧 Technical specifications:\n")
        content.append("  - GB4E format: 4-tier gloss (text0, morph, gloss, translation)\n")
        content.append("  - Morpheme boundaries: text1 layer boundary symbols (=, -) reflected in morph/gloss layers\n")
        content.append("  - IPA characters: Auto-converted to tipa package commands\n")
        content.append("  - Leipzig.sty: Auto-convert uppercase grammatical symbols to \\textsc{lowercase}\n")
        content.append("  - Small caps: Unicode small caps used in DOC format\n")
        content.append("  - Sentence splitting: Auto-split by sentence-ending punctuation (., ?, !)\n\n")
        content.append("📚 Leipzig.sty conversion examples:\n")
        content.append("  - LaTeX: FOC → \\textsc{foc}, PST → \\textsc{pst}\n")
        content.append("  - DOC: FOC → ꜰᴏᴄ, PST → ᴘsᴛ\n")
        content.append("  - Regular uppercase: INF → ɪɴꜰ, SEQ → sᴇQ\n\n")
        content.append(f"📅 Created: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        content.append(f"🔧 Source file: {Path(self.eaf_file_path).name}\n")
        
        return "".join(content)


# Diagnostic functions
def diagnose_eaf_file(eaf_filename, wav_filename=None):
    """Examine EAF file structure in detail"""
    converter = EAFConverter(eaf_filename, wav_filename)
    if not converter.parse_eaf():
        return
    
    if wav_filename:
        print("\nChecking audio file...")
        converter.load_audio()
    
    print("\n=== Detailed tier information ===")
    for tier_name, annotations in converter.tiers.items():
        print(f"\nTier: {tier_name}")
        print(f"  Annotation count: {len(annotations)}")
        
        # Display first 3 annotations
        for i, ann in enumerate(annotations[:3]):
            ann_type = ann.get('type', 'UNKNOWN')
            print(f"  [{i+1}] ({ann_type}) Time: {ann['start_time']}-{ann['end_time']}")
            content = ann['value'][:100] + '...' if len(ann['value']) > 100 else ann['value']
            print(f"      Content: '{content}'")
        
        if len(annotations) > 3:
            print(f"  ... (plus {len(annotations)-3} more)")


# Leipzig.sty conversion test function
def test_leipzig_conversion():
    """Test Leipzig.sty conversion functionality (4-tier gloss version)"""
    converter = EAFConverter("dummy.eaf")
    
    test_glosses = [
        "FOC",
        "GEN PST", 
        "COM INF SEQ",
        "書く.INF-替える.SEQ",
        "置く-SEQ 去る-PST=HS",
        "UNKNOWN CUSTOM"
    ]
    
    print("=== Leipzig.sty Conversion Test (4-tier gloss version) ===")
    print("Input → LaTeX format → DOC format (Unicode small caps)")
    print("-" * 70)
    
    for gloss in test_glosses:
        latex_converted = converter._convert_leipzig_glosses(gloss)
        latex_converted = latex_converted.replace('\\\\', '\\')  # Fix double backslashes
        doc_converted = converter._convert_leipzig_back_to_plain(latex_converted)
        
        print(f"'{gloss}'")
        print(f"  → LaTeX: '{latex_converted}'")
        print(f"  → DOC:   '{doc_converted}'")
        print()
        
        # Check backslashes
        if '\\textsc' in latex_converted:
            print("    ✅ LaTeX: \\textsc correctly included")
        elif 'extsc' in latex_converted:
            print("    ❌ LaTeX: \\t is missing!")
        
        # Check small caps
        if any(ord(c) > 127 for c in doc_converted):
            print("    ✅ DOC: Unicode small caps included")
    
    print("\n" + "="*70)
    print("Conversion rules:")
    print("- LaTeX: Uppercase grammatical symbols converted to \\textsc{lowercase}")
    print("- DOC: \\textsc{...} and regular uppercase converted to Unicode small caps")
    print("- Example: FOC → \\textsc{foc} → ꜰᴏᴄ")
    print("- Example: INF.SEQ → ɪɴꜰ.sᴇQ")


# Main conversion function
def convert_eaf_file(eaf_filename, wav_filename=None, tier_names=None, output_format='both', 
                    debug=False, save_audio=True, audio_folder_name=None, 
                    audio_padding_ms=100, create_zip=False, output_directory=None):
    """
    Complete EAF file conversion function (all fixes integrated + Leipzig.sty support)
    
    Args:
        eaf_filename: EAF file name
        wav_filename: WAV file name (for audio extraction, optional)
        tier_names: Tier name dictionary {'text0': 'actual_tier_name', ...}
        output_format: 'gb4e', 'doc', 'both'
        debug: Show debug information
        save_audio: Execute audio splitting
        audio_folder_name: Audio save folder name
        audio_padding_ms: Audio file padding before/after (milliseconds)
        create_zip: Create ZIP of audio files
        output_directory: Output directory (defaults to desktop if not specified)
    
    Returns:
        Conversion result dictionary
    """
    
    print("=== EAF File Conversion Start (Leipzig.sty Compatible Version) ===")
    
    # Check file existence
    if not os.path.exists(eaf_filename):
        print(f"❌ File not found: {eaf_filename}")
        print("\nFiles in current directory:")
        for file in os.listdir('.'):
            if file.endswith('.eaf'):
                print(f"  {file}")
        return None
    
    if wav_filename and not os.path.exists(wav_filename):
        print(f"⚠️ Audio file not found: {wav_filename}")
        print("Text conversion only will be executed.")
        wav_filename = None
    
    # Determine output directory
    if output_directory is None:
        output_directory = get_desktop_path()
    
    print(f"📁 Output directory: {output_directory}")
    
    # Execute conversion
    converter = EAFConverter(eaf_filename, wav_filename)
    
    if not converter.parse_eaf():
        return None
    
    # Load audio file if available
    if wav_filename:
        print("🎵 Loading audio file...")
        converter.load_audio()
    
    sentences = converter.extract_sentences(tier_names)
    
    if not sentences:
        print("❌ No convertible sentences found.")
        return None
    
    result = {
        'sentences': sentences,
        'eaf_file': eaf_filename,
        'wav_file': wav_filename,
        'gb4e_file': None,
        'doc_file': None,
        'audio_result': None,
        'output_directory': output_directory
    }
    
    # Display and save text conversion results
    print("\n" + "="*70)
    
    base_name = Path(eaf_filename).stem
    
    if output_format in ['gb4e', 'both']:
        print("📝 GB4E format (4-tier gloss: \\glll usage, Leipzig.sty compatible):")
        print("-" * 40)
        gb4e_content = converter.to_gb4e_format(sentences)
        print(gb4e_content[:500] + "..." if len(gb4e_content) > 500 else gb4e_content)
        
        # Save to file
        gb4e_filename = Path(output_directory) / f"{base_name}_gb4e_leipzig.tex"
        if save_file_safely(gb4e_filename, gb4e_content):
            result['gb4e_file'] = str(gb4e_filename)
    
    if output_format in ['both']:
        print("\n" + "="*70)
    
    if output_format in ['doc', 'both']:
        print("📄 DOC format (4-tier display: Unicode small caps compatible):")
        print("-" * 40)
        doc_content = converter.to_doc_format(sentences, debug=debug)
        print(doc_content[:500] + "..." if len(doc_content) > 500 else doc_content)
        
        # Save to file
        doc_filename = Path(output_directory) / f"{base_name}_doc.txt"
        if save_file_safely(doc_filename, doc_content):
            result['doc_file'] = str(doc_filename)
    
    # Execute audio splitting
    if save_audio and wav_filename and converter.audio_available:
        print("\n" + "="*70)
        print("🎵 Executing audio splitting...")
        
        audio_result = converter.split_audio_to_desktop(
            sentences, audio_folder_name or f"{base_name}_sentences", 
            audio_padding_ms, create_zip, output_directory
        )
        result['audio_result'] = audio_result
    elif save_audio and wav_filename:
        print("\n⚠️ Audio splitting: Skipped due to unavailable audio library")
    elif save_audio:
        print("\n⚠️ Audio splitting: Skipped due to no WAV file specified")
    
    print(f"\n🎉 Conversion complete!")
    print(f"📊 Extracted sentences: {len(sentences)}")
    if result['gb4e_file']:
        print(f"📝 GB4E format (4-tier gloss・\\glll・Leipzig.sty compatible): {result['gb4e_file']}")
    if result['doc_file']:
        print(f"📄 DOC format (4-tier display・Unicode small caps compatible): {result['doc_file']}")
    if result['audio_result']:
        print(f"🎵 Audio files: {result['audio_result']['total_files']} files")
        print(f"📁 Audio save location: {result['audio_result']['output_path']}")
    
    # File verification
    print(f"\n=== Output file verification ===")
    for key, filepath in result.items():
        if filepath and isinstance(filepath, str) and os.path.exists(filepath):
            size = os.path.getsize(filepath)
            print(f"✅ {key}: {filepath} ({size} bytes)")
        elif filepath and key.endswith('_file'):
            print(f"❌ {key}: {filepath} (file does not exist)")
    
    return result


# Simple conversion function
def quick_convert(eaf_filename, wav_filename=None, output_directory=None):
    """Simple conversion function (all features enabled・Leipzig.sty compatible)"""
    return convert_eaf_file(
        eaf_filename=eaf_filename,
        wav_filename=wav_filename,
        output_format='both',
        save_audio=True if wav_filename else False,
        create_zip=True if wav_filename else False,
        output_directory=output_directory
    )


# Debug conversion function
def debug_convert(eaf_filename, wav_filename=None):
    """Debug mode conversion (Leipzig.sty compatible)"""
    return convert_eaf_file(
        eaf_filename=eaf_filename,
        wav_filename=wav_filename,
        output_format='both',
        debug=True,
        save_audio=True if wav_filename else False
    )


# Test function
def test_gb4e_output():
    """Test GB4E format (\\glll verification・Leipzig.sty compatible)"""
    test_sentence = {
        'text0': 'nkjaandu annatu ujatu',
        'morph': 'nkjaan=du anna=tu uja=tu',
        'gloss': '昔=FOC 母親=COM 父親=COM',
        'translation': '昔々、母親と父親と'
    }
    
    converter = EAFConverter('dummy.eaf')
    gb4e_output = converter.to_gb4e_format([test_sentence])
    
    print("=== GB4E Format Test (Leipzig.sty compatible) ===")
    print(gb4e_output)
    
    if "\\glll" in gb4e_output:
        print("\n✅ Correctly using \\glll (4-tier gloss)")
    else:
        print("\n❌ \\glll not found")
    
    if "\\textsc{foc}" in gb4e_output:
        print("✅ Leipzig.sty conversion working correctly")
    else:
        print("❌ Leipzig.sty conversion has issues")
    
    return gb4e_output


# Usage instructions
print("=== Complete EAF File Conversion Script (Leipzig.sty Compatible) ===")
print("🎯 All fixes integrated + Leipzig.sty functionality - Ready to use!")
print()
print("🔧 Integrated fixes + new features:")
print("✅ GB4E format using \\glll (4-tier gloss)")
print("✅ Leipzig.sty compatible: Auto-convert uppercase grammatical symbols to \\textsc{lowercase}")
print("✅ Unicode small caps compatible: Display ꜰᴏᴄ, ᴘsᴛ etc. in DOC format")
print("✅ Reflect text1 layer boundary symbols (=, -) in morph/gloss layers")
print("✅ Desktop output issues resolved (OneDrive compatible)")
print("✅ Safe file saving functionality")
print("✅ IPA→tipa command auto-conversion")
print("✅ Audio splitting functionality (sentence-by-sentence)")
print("✅ 4-tier display DOC format")
print()
print("📝 Usage:")
print()
print("# 1. Basic conversion (recommended・Leipzig.sty compatible)")
print("result = quick_convert('your_file.eaf', 'your_file.wav')")
print()
print("# 2. Text-only conversion")
print("result = quick_convert('your_file.eaf')")
print()
print("# 3. Custom output destination")
print("result = quick_convert('your_file.eaf', 'your_file.wav', '/path/to/output')")
print()
print("# 4. Detailed settings")
print("result = convert_eaf_file(")
print("    eaf_filename='your_file.eaf',")
print("    wav_filename='your_file.wav',")
print("    output_format='both',")
print("    save_audio=True,")
print("    create_zip=True,")
print("    tier_names={")
print("        'text0': 'your_text0_tier_name',")
print("        'text1': 'your_text1_tier_name',")
print("        'morph': 'your_morph_tier_name',")
print("        'gloss': 'your_gloss_tier_name',")
print("        'translation': 'your_translation_tier_name'")
print("    }")
print(")")
print()
print("# 5. Debug mode")
print("result = debug_convert('your_file.eaf', 'your_file.wav')")
print()
print("# 6. File structure diagnosis")
print("diagnose_eaf_file('your_file.eaf', 'your_file.wav')")
print()
print("# 7. GB4E format test (Leipzig.sty compatible)")
print("test_gb4e_output()")
print()
print("# 8. Leipzig.sty conversion test")
print("test_leipzig_conversion()")
print()
print("🎉 This script is the complete version (Leipzig.sty compatible). Ready to start using!")
print("💡 If you encounter problems, please diagnose with diagnose_eaf_file().")
print()
print("📚 Leipzig.sty functionality:")
print("- LaTeX: FOC → \\textsc{foc}, PST → \\textsc{pst}")
print("- DOC: FOC → ꜰᴏᴄ, PST → ᴘsᴛ")
print("- Regular uppercase: INF → ɪɴꜰ, SEQ → sᴇQ")

if AUDIO_LIBRARY:
    print(f"\n🎵 Audio processing: {AUDIO_LIBRARY} available")
else:
    print(f"\n⚠️ Audio processing: No library (text conversion only)")
    print("To use audio splitting, install:")
    print("  pip install librosa soundfile  # Recommended")
    print("  pip install pydub              # Lightweight version")
