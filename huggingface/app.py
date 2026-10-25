"""Migration notice for the retired Hugging Face version of eaftox."""

import gradio as gr

APP_URL = "https://michinorishimoji.github.io/eaftox/"
SOURCE_URL = "https://github.com/MichinoriShimoji/eaftox"

with gr.Blocks(title="eaftox — 移転しました", analytics_enabled=False) as demo:
    gr.Markdown(
        "# eaftox は新しいサイトへ移転しました\n\n"
        "Hugging Face版の提供は終了しました。今後は下のリンクからご利用ください。\n\n"
        f"## [新しい eaftox を開く ↗]({APP_URL})\n\n"
        "インストールやアカウント登録は不要です。"
        "EAFの変換・音声の分割は、お使いのPCのブラウザ内で行います。"
        "EAFやWAVをサーバーへアップロードする必要はありません。\n\n"
        "「オフライン用に保存」からHTMLを保存すると、"
        "インターネットに接続せずに利用できます。\n\n"
        "ブックマークの変更をお願いします。\n\n"
        "---\n\n"
        f"[GitHub：ソースコード・使い方]({SOURCE_URL})\n\n"
        "eaftox · Michinori Shimoji"
    )

if __name__ == "__main__":
    demo.launch()
