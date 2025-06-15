# eaftox: EAF → Glossing Converter with Audio Segmenting

`eaftox` is a Python script that automatically converts ELAN `.eaf` files into Interlinear Glossed Texts (IGTs) on a sentence-by-sentence basis and extracts the corresponding audio segments.

- Outputs in `.txt` format (standard 3-line glossing, properly indented and ready to paste into document formats)
- Outputs in LaTeX `gb4e` format (with IPA-to-tipa conversion for use with LaTeX)
- Extracts sentence-aligned segments from audio files (`.wav`)

## 🚀 Features

- Extracts `text`, `morph`, `gloss`, and `translation` tiers from `.eaf` files  
- Sentence segmentation based on punctuation marks (e.g., `.`, `?`, `!`)  
- Supports both 4-tier EAFs (`text`, `morph`, `gloss`, `trans`) and 5-tier EAFs (`text0` (without morpheme boundaries), `text1` (with base-structure morpheme boundaries), `morph`, `gloss`, `trans`)  
- Allows specification of custom tier names  
- Assumes automatic segmentation from `text` to `morph` (where `-` and `=` morpheme delimiters may be lost in ELAN’s `morph` tier — these are automatically restored in both `.txt` and LaTeX output formats)  
- IPA-to-tipa conversion for LaTeX compatibility  
- Optional: extracts sentence-level audio segments from `.wav` files and saves them in a ZIP archive

## Requirements
```bush
pip install librosa soundfile pydub numpy
```

## 🛠️ Usage

### From 4-tier EAF (text, morph, gloss, trans) to 3-line IGT

```python
from eaf_converter3 import convert_eaf_file

# Execute after loading: specify the eaf filename and tier names (replace 'x' accordingly)
convert_eaf_file(
    eaf_filename='x.eaf',
    wav_filename='x.wav',
    output_format='both',
    save_audio=True,
    create_zip=True,
    tier_names={
        'text': 'x',
        'morph': 'x',
        'gloss': 'x',
        'translation': 'x'
    }
)

from eaf_converter4 import convert_eaf_file

# Execute after loading: specify the eaf filename and tier names (replace 'x' accordingly)
convert_eaf_file(
    eaf_filename='x.eaf',
    wav_filename='x.wav',
    output_format='both',
    save_audio=True,
    create_zip=True,
    tier_names={
        'text0': 'x',
        'text1': 'x',
        'morph': 'x',
        'gloss': 'x',
        'translation': 'x'
    }
)
