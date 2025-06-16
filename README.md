# eaftox: EAF → Glossing Converter with Audio Segmenting

`eaftox` は、ELANの `.eaf` ファイルから、 文単位でInterlinear Glossed Text (IGT)に自動変換し、音声も切り出すPythonスクリプトです。

- txt形式（標準3段グロス、インデント調整済み、doc形式などにすぐに貼り付け可能）
- LaTeX `gb4e` 形式（eaf形式で使用したIPA → tipa変換付き）
- いずれもグロスのアルファベットは元ファイル(eaf)の大文字から小型大文字（LaTeXでは¥textsc{}）に自動変換
- 音声ファイルから対応する文ごとの切り出し（`.wav`）

## 🚀 機能

- `.eaf` ファイルの text/morph/gloss/translation 層を抽出
- 文末記号（. ? !）に基づいた文分割
- 4層構造eaf（text, morph, gloss, trans）、5層構造eaf（text0 (形態素境界なし), text1（基底構造で形態素境界あり）、morph, gloss, trans）に対応
- さらに、形態素に分けない立場のglossing（文節ごとにスペースを入れたtext層、それを自動分割したword層, word層にグロスをつけるgloss層, trans層）にも対応
- 自分が使用するtier名を指定することができる
- text -> morphへの自動分割を使用している前提(ELANのmorph層で-, =の形態素記号が消失 -> 上記txt形式、LaTeX形式でこれらが自動で復活)
- tipa 対応のためのIPA変換
- 音声 `.wav` ファイルから、文単位の切り出しとZIP保存（オプション）

## 追加インストール（必要に応じて）
```bush
pip install librosa soundfile pydub numpy
```

## 🛠️ 使用方法

```python
#4層構造eaf（text, morph, gloss, trans）から3層構造IGTへ
from eaf_converter3 import convert_eaf_file

#読み込み後、実行：eafファイル名、eafのtier名を指定（以下の'x'を修正）
tier_names = {
       'text': 'x',      # 実際のtext層の名前
       'morph': 'x',    # 実際のmorph層の名前
       'gloss': 'x',    # 実際のgloss層の名前
       'translation': 'x'  # 実際のtranslation層の名前
   }
convert_eaf_file('x.eaf', 'x.wav',
                            tier_names=tier_names)


#5層構造eaf（text0 (形態素境界なし), text1（基底構造で形態素境界あり）, morph, gloss, trans）から4層構造IGTへ
from eaf_converter4 import convert_eaf_file 

#読み込み後、実行：eafファイル名、eafのtier名を指定（以下の'x'を修正）
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

#3層構造eaf（text層（形態素境界なし）、word層（形態素境界なし）、gloss, trans）から3層構造IGTへ
from eaf_converterwp import convert_eaf_simple

#読み込み後、実行：まず、tier名を指定（xを修正）
tier_names = {
        'word': 'x',
        'gloss': 'x', 
        'trans': 'x',
        'text': 'x'
    }
convert_eaf_simple('x.eaf', 'x.wav', tier_names = tier_names)
