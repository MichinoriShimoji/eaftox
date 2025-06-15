# eaftox: EAF → Glossing Converter with Audio Segmenting

`eaftox` は、ELANの `.eaf` ファイルから、 文単位でInterlinear Glossed Text (IGT)に自動変換し、音声も切り出すPythonスクリプトです。

- txt形式（標準3段グロス、インデント調整済み、doc形式などにすぐに貼り付け可能）
- LaTeX `gb4e` 形式（eaf形式で使用したIPA → tipa変換付き）
- 音声ファイルから対応する文ごとの切り出し（`.wav`）

## 🚀 機能

- `.eaf` ファイルの text/morph/gloss/translation 層を抽出
- 文末記号（. ? !）に基づいた文分割
- 4層構造eaf（text, morph, gloss, trans）、5層構造eaf（text0 (形態素境界なし), text1（基底構造で形態素境界あり）、morph, gloss, trans）に対応
- 自分が使用するtier名を指定することができる
- text -> morphへの自動分割を使用している前提(ELANのmorph層で-, =の形態素記号が消失 -> 上記txt形式、LaTeX形式でこれらが自動で復活)
- tipa 対応のためのIPA変換
- 音声 `.wav` ファイルから、文単位の切り出しとZIP保存（オプション）

## 🛠️ 使用方法

```python
#4層構造eaf（text, morph, gloss, trans）から3層構造IGTへ
from eaf_converter3 import convert_eaf_file %

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
        'text': 'x',
        'morph': 'x',
        'gloss': 'x',
        'translation': 'x'
    }
)

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

