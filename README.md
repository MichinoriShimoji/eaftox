# eaftox: EAF → Glossing Converter with Audio Segmenting

## ブラウザ版（インストール不要）

**[eaftoxを開く](https://MichinoriShimoji.github.io/eaftox/)**

EAF解析・例文変換・音声分割・ZIP作成を、各自のPCのブラウザ内で行います。EAFや音声はサーバーに送信しません。アカウントやPythonのインストールも不要です。

1. EAFファイルと、必要ならWAVまたはMP3を選択します。
2. 「構造を確認」で、親子ティアを線でつないだ図と、自動判定された役割を確認します。各カードにティア名・内容の例・役割が表示され、カード内で役割を変更できます。複数話者はタブで切り替えます。
3. 「ファイルを作成」を押し、GB4E・テキスト・文ごとの音声をZIPでダウンロードします。

図の左が親、右が子で、線はEAFの `PARENT_REF` に基づきます。狭い画面では親の下に子を並べます。独立したティアは別の根として表示します。「すべてのティアを表示」で他の話者や未使用のティアも確認でき、「役割ごとの対応を詳しく調整」では従来のドロップダウン形式で設定できます。役割の変更は出力プレビューに反映されます。

「オフライン用に保存」から単一のHTMLを保存できます。保存したHTMLはChrome・Edge・Safariなどのブラウザで直接開いて使えます。JavaScriptやフォントを外部CDNから取得しないため、インターネット接続は不要です。読み込んだユーザーファイルや変換結果は、保存用HTMLに含めません。

### ブラウザ版の対応範囲

- 最大8話者。`PARTICIPANT`、親子関係、ティア名、言語タイプから対応候補を判定します。独自の名前は手動修正が必要なことがあります。
- 3層・4層・形態素を使わない構造、参照アノテーション、境界マーカーの除去、IPA→TIPA、3種類のGB4Eスタイルに対応します。
- WAVは必要な区間だけ読み、サンプリング周波数・チャンネル数・ビット深度を保持します。PCM 8/16/24/32bit、IEEE Float 32/64bit、対応するWAVE_FORMAT_EXTENSIBLEを扱えます。圧縮WAV・RF64は未対応です。
- MP3はブラウザのデコーダーを使い、16bit PCM WAVへ変換します。ブラウザの再生周波数に変換される場合があります。MP3全体をメモリーに展開するため、長い録音にはWAVを推奨します。
- 前後余白は0〜500ms。音声の範囲外・不正な区間は、該当文を表示して停止します。
- 品詞はテキスト形式に出力します。ZIPは速度を優先した無圧縮形式で、合計4GBまでに対応します。使用可能なメモリーはブラウザ・PCによって異なります。
- ファイル読み込み後の通信はCSPでも禁止しています。外部リンクを自分で開く場合を除き、処理にネットワークを使いません。

### 開発・公開

GitHub Pagesでは `main` ブランチのルートを公開します。配信用ファイルは `index.html` と `.nojekyll` です。旧Pythonスクリプトとサンプルはそのまま残しています。

変更するときは `web/` のHTMLテンプレート・CSS・JavaScriptを編集し、次を実行します。生成済みの `index.html` はビルドせずそのまま利用できます。

```sh
python3 scripts/build.py
python3 tests/reference.py
node --test tests/core.test.cjs
```

テストは元のPython版との出力比較、リポジトリ内の3種類のサンプルEAF、各種WAVのフレーム単位の切り出し、40MB WAVのヘッダー限定読み込み、ZIPのCRC・Unicodeファイル名・中止処理を確認します。`app.py` はHugging Face版の比較用ソースです。

## 従来のPython版

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

```
## サンプルファイル
サンプルファイルは、作成者（下地理則）が用意した3つのeafファイルと1つのwavファイルからなる。

- 音声ファイル：sample.wav：伊良部島方言の昔話の冒頭4文
- sample3.eaf: sample.wavを4弾構成（text, morph, gloss, trans）で書き起こしたeafファイル。eaf_converter3.pyで処理できるデモファイル
- sample4.eaf: sample.wavを5弾構成（text0, text1, morph, gloss, trans）で書き起こしたeafファイル。eaf_converter4.pyで処理できるデモファイル
- samplewp.eaf: sample.wavを3弾構成（text, word, gloss, trans）で書き起こしたeafファイル。eaf_converterwp.pyで処理できるデモファイル
