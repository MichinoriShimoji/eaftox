(function () {
  "use strict";
  const E = window.Eaftox;
  // Capture the empty application before any user file or example enters the UI.
  const pristineHtml = "<!doctype html>\n" + document.documentElement.outerHTML;
  const $ = id => document.getElementById(id);
  const state = { eaf: null, speakers: [], sentences: [], audioFile: null, audio: null, audioStatus: "empty", urls: [], eafGeneration: 0, audioGeneration: 0, busy: false, abort: null };
  const roles = { text0: ["表層形", "text0"], text: ["本文・形態素境界", "text"], morph: ["形態素", "morph"], gloss: ["グロス", "gloss"], pos: ["品詞", "pos・任意"], trans: ["自由訳", "trans"] };
  const modeLabels = { "シンプル3層": "本文 → グロス → 訳", "3層": "本文＋形態素 → グロス → 訳", "4層": "表層形 → 本文 → グロス → 訳" };
  function element(tag, className, text) { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; }
  const sizeText = bytes => bytes < 1000000 ? `${(bytes / 1000).toFixed(0)} KB` : `${(bytes / 1000000).toFixed(1)} MB`;
  const timeText = seconds => { const min = Math.floor(seconds / 60); return `${min}:${(seconds % 60).toFixed(2).padStart(5, "0")}`; };
  function showError(message) { $("alert").textContent = message; $("alert").hidden = !message; }
  function resetResults() {
    for (const url of state.urls) URL.revokeObjectURL(url);
    state.urls = [];
    $("results").hidden = true;
    for (const id of ["download-zip", "download-tex", "download-txt"]) $(id).removeAttribute("href");
  }
  function updatePreview() {
    resetResults();
    const preview = $("preview"); preview.replaceChildren();
    state.sentences = [];
    let error = "";
    if (state.eaf) {
      try { state.sentences = E.extractSentences(state.eaf, state.speakers); }
      catch (e) { error = e.message; }
    }
    for (const [index, sent] of state.sentences.slice(0, 3).entries()) {
      const item = element("div", "example"), top = element("div", "example-top");
      top.append(element("span", "", `(${index + 1})`), element("span", "example-speaker", sent.speaker), element("span", "example-time", `${timeText(sent.start_time / 1000)} — ${timeText(sent.end_time / 1000)}`));
      item.append(top);
      if (sent.mode === "4層" && sent.text0) item.append(element("div", "example-text", E.normalize(sent.text0)));
      if (sent.text) item.append(element("div", "example-text", E.normalize(sent.text)));
      const base = sent.text || sent.text0;
      if (sent.gloss) item.append(element("div", "example-gloss", E.normalize(E.alignMorphs(base, sent.gloss))));
      if (sent.pos) item.append(element("div", "example-gloss", E.normalize(E.alignMorphs(base, sent.pos))));
      if (sent.trans) item.append(element("div", "example-trans", sent.trans));
      preview.append(item);
    }
    if (!state.sentences.length) preview.append(element("p", "preview-empty", error || (state.eaf ? "対応する本文ティアを選択してください。" : "ティアを選ぶと、出力する例文を確認できます。")));
    const count = state.sentences.length;
    $("sentence-count").textContent = count ? `${count.toLocaleString()} 文を検出` : "";
    const audioBlocked = $("include-audio").checked && ["loading", "error"].includes(state.audioStatus);
    $("convert").disabled = state.busy || !count || audioBlocked;
    $("export-hint").textContent = error || (audioBlocked ? state.audioStatus === "loading" ? "音声情報を確認しています…" : "音声を選び直すか、音声を解除してください。" : count ? `${count.toLocaleString()}文 ${$("include-audio").checked && state.audioFile ? "＋ 分割音声" : "・ テキストのみ"}を書き出します。` : "まずEAFファイルを選択してください。");
  }

  function renderMapping() {
    $("mapping-empty").hidden = !!state.eaf;
    $("mapping-content").hidden = !state.eaf;
    $("mapping-count").hidden = !state.eaf;
    $("mapping-count").textContent = `${state.speakers.length} 話者`;
    $("add-speaker").disabled = !state.eaf || state.speakers.length >= 8 || state.busy;
    $("speakers").replaceChildren();
    if (!state.eaf) { updatePreview(); return; }
    const uncertain = state.speakers.some(s => s.uncertain);
    const notice = $("mapping-notice");
    notice.classList.toggle("warning", uncertain || state.eaf.skipped > 0);
    notice.textContent = uncertain ? "ティア名から役割を判断しきれない箇所があります。本文・グロス・自由訳の対応を確認してください。" : "話者情報・ティア名・親子関係から対応候補を設定しました。下のプレビューを確認し、必要な箇所だけ変更してください。";
    if (state.eaf.skipped) notice.textContent += ` 時間を解決できなかった ${state.eaf.skipped} 件は除外しています。`;
    state.speakers.forEach((speaker, index) => {
      const card = element("div", "speaker-card"), top = element("div", "speaker-top");
      const name = element("input", "speaker-name"); name.type = "text"; name.value = speaker.name; name.setAttribute("aria-label", `話者${index + 1}の名前`);
      name.addEventListener("input", () => { speaker.name = name.value; updatePreview(); });
      const mode = element("select", "mode-select"); mode.setAttribute("aria-label", `話者${index + 1}の構造`);
      for (const value of E.MODES) mode.add(new Option(modeLabels[value], value, false, value === speaker.mode));
      mode.addEventListener("change", () => { speaker.mode = mode.value; renderMapping(); });
      const remove = element("button", "remove-speaker", "×"); remove.setAttribute("aria-label", `話者${index + 1}を削除`); remove.disabled = state.speakers.length === 1;
      remove.addEventListener("click", () => { state.speakers.splice(index, 1); renderMapping(); });
      top.append(element("span", "speaker-index", String(index + 1)), name, mode, remove); card.append(top);
      const grid = element("div", "mapping-grid");
      for (const [role, labels] of Object.entries(roles)) {
        if (role === "text0" && speaker.mode !== "4層") continue;
        if (role === "morph" && speaker.mode === "シンプル3層") continue;
        const field = element("label", "field"), title = element("span", "", labels[0]); title.append(element("small", "", labels[1]));
        const select = element("select"); select.setAttribute("aria-label", `話者${index + 1} ${labels[0]}`);
        select.add(new Option("選択しない", ""));
        for (const tier of state.eaf.info) select.add(new Option(`${tier.id}  (${tier.count})`, tier.id));
        select.value = speaker.tiers[role] || "";
        select.addEventListener("change", () => { speaker.tiers[role] = select.value; speaker.uncertain = false; updatePreview(); });
        field.append(title, select); grid.append(field);
      }
      card.append(grid); $("speakers").append(card);
    });
    $("tier-count").textContent = `${state.eaf.info.length} ティア`;
    $("tier-table").replaceChildren();
    for (const tier of state.eaf.info) {
      const tr = element("tr");
      for (const value of [tier.id, tier.parent || "—", tier.participant || "—", String(tier.count), tier.sample.slice(0, 70)]) tr.append(element("td", "", value));
      $("tier-table").append(tr);
    }
    updatePreview();
  }

  async function loadEaf(file) {
    if (!file || state.busy) return;
    const generation = ++state.eafGeneration;
    showError(""); resetResults(); state.eaf = null; state.speakers = []; renderMapping();
    $("eaf-name").textContent = file.name; $("eaf-meta").textContent = "読み込み中…"; $("eaf-zone").classList.remove("ready"); $("file-step-check").textContent = "";
    try {
      if (file.size > 50 * 1000000) throw new Error("EAFが50MBを超えています。EAFを小さく分けてから読み込んでください。");
      const started = performance.now();
      const bytes = await file.arrayBuffer();
      let text;
      if (bytes.byteLength >= 2 && new Uint8Array(bytes, 0, 2)[0] === 255 && new Uint8Array(bytes, 0, 2)[1] === 254) text = new TextDecoder("utf-16le").decode(bytes);
      else if (bytes.byteLength >= 2 && new Uint8Array(bytes, 0, 2)[0] === 254 && new Uint8Array(bytes, 0, 2)[1] === 255) text = new TextDecoder("utf-16be").decode(bytes);
      else text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
      const eaf = E.parseEaf(text);
      if (generation !== state.eafGeneration) return;
      if (!eaf.info.length) throw new Error("EAF内にティアが見つかりませんでした。");
      state.eaf = eaf; state.speakers = E.guessSpeakers(eaf);
      $("eaf-meta").textContent = `${sizeText(file.size)} · ${eaf.info.length} ティア · ${Math.round(performance.now() - started)} msで読み込み`;
      $("eaf-zone").classList.add("ready"); $("eaf-action").textContent = "別のファイルに変更 ＋"; $("file-step-check").textContent = "✓";
      renderMapping();
    } catch (error) {
      if (generation !== state.eafGeneration) return;
      state.eaf = null; state.speakers = []; $("eaf-meta").textContent = "読み込めませんでした"; renderMapping(); showError(error.message);
    }
  }

  function clearAudio() {
    state.audioGeneration++; state.audioFile = null; state.audio = null; state.audioStatus = "empty"; $("audio-file").value = "";
    $("audio-zone").classList.remove("ready"); $("audio-name").textContent = ".wav / .mp3 を選択、またはドロップ";
    $("audio-meta").textContent = "音声を分割する場合に選択してください"; $("audio-action").textContent = "ファイルを選択 ＋"; $("remove-audio").hidden = true;
    updatePreview();
  }
  async function loadAudio(file) {
    if (!file || state.busy) return;
    const generation = ++state.audioGeneration;
    state.audioFile = null; state.audio = null; state.audioStatus = "loading"; showError(""); updatePreview();
    $("audio-name").textContent = file.name; $("audio-meta").textContent = "音声情報を確認中…"; $("audio-zone").classList.remove("ready"); $("remove-audio").hidden = false;
    try {
      const started = performance.now();
      if (/\.wav$/i.test(file.name)) {
        const audio = await E.openWav(file);
        if (generation !== state.audioGeneration) return;
        state.audio = audio;
        $("audio-meta").textContent = `${sizeText(file.size)} · ${timeText(audio.duration)} · ${audio.sampleRate.toLocaleString()} Hz / ${audio.bits}bit / ${audio.channels}ch · ${Math.round(performance.now() - started)} ms`;
      } else if (/\.mp3$/i.test(file.name)) {
        $("audio-meta").textContent = `${sizeText(file.size)} · 書き出し時にブラウザで読み込み、16bit WAVに変換`;
      } else throw new Error("WAVまたはMP3ファイルを選択してください。");
      if (generation !== state.audioGeneration) return;
      state.audioFile = file; state.audioStatus = "ready"; $("audio-zone").classList.add("ready"); $("audio-action").textContent = "別のファイルに変更 ＋";
      updatePreview();
    } catch (error) {
      if (generation !== state.audioGeneration) return;
      state.audioFile = null; state.audio = null; state.audioStatus = "error"; $("audio-meta").textContent = "読み込めませんでした"; showError(error.message); updatePreview();
    }
  }

  const paint = () => new Promise(resolve => setTimeout(resolve, 0));
  function progress(value, text) { $("progress").value = value; $("progress-text").textContent = text; $("progress-percent").textContent = `${Math.round(value * 100)}%`; }
  async function decodeMp3(file) {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) throw new Error("このブラウザはMP3の読み込みに対応していません。WAVをご利用ください。");
    const ctx = new AudioCtx();
    try {
      const buffer = await ctx.decodeAudioData(await file.arrayBuffer());
      return { kind: "decoded", buffer, sampleRate: buffer.sampleRate, channels: buffer.numberOfChannels, frames: buffer.length, duration: buffer.duration, bits: 16 };
    } catch (_) { throw new Error("MP3を読み込めませんでした。WAVへの変換、または別のブラウザでお試しください。"); }
    finally { await ctx.close(); }
  }
  let disabledSnapshot = [];
  function setBusy(busy) {
    state.busy = busy; document.body.classList.toggle("busy", busy);
    if (busy) {
      disabledSnapshot = [...document.querySelectorAll("button,input,select")].filter(node => node.id !== "cancel").map(node => [node, node.disabled]);
      for (const [node] of disabledSnapshot) node.disabled = true;
    } else for (const [node, wasDisabled] of disabledSnapshot) node.disabled = wasDisabled;
    $("cancel").hidden = !busy; $("convert").hidden = busy;
    $("progress-region").hidden = !busy;
  }
  async function convert() {
    if (state.busy || !state.eaf) return;
    showError(""); resetResults(); state.abort = new AbortController();
    const started = performance.now(); setBusy(true); progress(0.01, "例文を準備中…"); await paint();
    try {
      const signal = state.abort.signal;
      const check = () => { if (signal.aborted) throw new Error("処理を中止しました。"); };
      const sentences = E.extractSentences(state.eaf, state.speakers);
      if (!sentences.length) throw new Error("出力できる文がありません。本文のティアを確認してください。");
      const tex = new Blob([E.toGb4e(sentences, $("gb4e-style").value)], { type: "text/plain;charset=utf-8" });
      const txt = new Blob([E.toText(sentences)], { type: "text/plain;charset=utf-8" });
      const entries = [{ name: "sentences_gb4e.tex", blob: tex }, { name: "sentences_doc.txt", blob: txt }];
      const include = $("include-audio").checked && state.audioFile;
      let audioCount = 0;
      if (include) {
        progress(0.04, state.audio ? "音声区間を確認中…" : "MP3を読み込み中…"); await paint(); check();
        const audio = state.audio || await decodeMp3(state.audioFile);
        check();
        // Cache one MP3 decode while this file remains selected.
        state.audio = audio;
        const padding = Number($("padding").value);
        for (const [index, sent] of sentences.entries()) {
          check();
          let blob;
          try { blob = audio.kind === "wav" ? E.sliceWav(audio, sent.start_time, sent.end_time, padding) : E.sliceDecodedAudio(audio, sent.start_time, sent.end_time, padding); }
          catch (e) { throw new Error(`${index + 1}文目（${sent.speaker}）: ${e.message}`); }
          entries.push({ name: E.audioFilename(sent, index), blob }); audioCount++;
          if (index % 20 === 0) { progress(0.08 + 0.22 * (index + 1) / sentences.length, `音声を分割中… ${index + 1} / ${sentences.length}`); await paint(); }
        }
      }
      check();
      progress(0.3, "ZIPを作成中…"); await paint();
      const zip = await E.makeZip(entries, { signal, onProgress: fraction => progress(0.3 + 0.69 * fraction, "ZIPを作成中…") });
      check();
      for (const [id, blob, filename] of [["download-zip", zip, "eaftox_examples.zip"], ["download-tex", tex, "sentences_gb4e.tex"], ["download-txt", txt, "sentences_doc.txt"]]) {
        const url = URL.createObjectURL(blob); state.urls.push(url); $(id).href = url; $(id).download = filename;
      }
      $("result-summary").textContent = `${sentences.length.toLocaleString()}文${audioCount ? ` ・ 音声 ${audioCount.toLocaleString()}個` : ""} ・ ZIP ${sizeText(zip.size)} ・ ${((performance.now() - started) / 1000).toFixed(2)} 秒`;
      $("results").hidden = false; progress(1, "完了");
      $("results").scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (error) { if (state.abort.signal.aborted) $("export-hint").textContent = "処理を中止しました。設定を確認して再実行できます。"; else showError(error.message); }
    finally { setBusy(false); state.abort = null; }
  }

  function bindDrop(zoneId, inputId, load) {
    const zone = $(zoneId), input = $(inputId);
    input.addEventListener("change", () => load(input.files[0]));
    zone.addEventListener("dragover", event => { event.preventDefault(); if (!state.busy) zone.classList.add("dragging"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("dragging"));
    zone.addEventListener("drop", event => {
      event.preventDefault(); zone.classList.remove("dragging");
      if (event.dataTransfer.files.length !== 1) { showError("ファイルは1つずつ選択してください。"); return; }
      load(event.dataTransfer.files[0]);
    });
  }
  bindDrop("eaf-zone", "eaf-file", loadEaf); bindDrop("audio-zone", "audio-file", loadAudio);
  $("remove-audio").addEventListener("click", clearAudio);
  $("add-speaker").addEventListener("click", () => { if (state.speakers.length >= 8) return; state.speakers.push({ name: `話者${state.speakers.length + 1}`, mode: "シンプル3層", tiers: { text0: "", text: "", morph: "", gloss: "", pos: "", trans: "" }, uncertain: true }); renderMapping(); });
  $("include-audio").addEventListener("change", updatePreview);
  $("gb4e-style").addEventListener("change", resetResults);
  $("padding").addEventListener("input", () => { $("padding-value").textContent = `${$("padding").value} ms`; resetResults(); });
  $("convert").addEventListener("click", convert); $("cancel").addEventListener("click", () => state.abort?.abort());
  $("save-app").addEventListener("click", () => {
    const url = URL.createObjectURL(new Blob([pristineHtml], { type: "text/html;charset=utf-8" })), link = element("a");
    link.href = url; link.download = "eaftox.html"; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 10000);
  });
  const sampleEaf = `<?xml version="1.0" encoding="UTF-8"?><ANNOTATION_DOCUMENT><HEADER/><TIME_ORDER><TIME_SLOT TIME_SLOT_ID="t1" TIME_VALUE="200"/><TIME_SLOT TIME_SLOT_ID="t2" TIME_VALUE="1500"/><TIME_SLOT TIME_SLOT_ID="t3" TIME_VALUE="1900"/><TIME_SLOT TIME_SLOT_ID="t4" TIME_VALUE="3400"/><TIME_SLOT TIME_SLOT_ID="t5" TIME_VALUE="3800"/><TIME_SLOT TIME_SLOT_ID="t6" TIME_VALUE="4900"/></TIME_ORDER><TIER TIER_ID="text" PARTICIPANT="話者A"><ANNOTATION><ALIGNABLE_ANNOTATION ANNOTATION_ID="a1" TIME_SLOT_REF1="t1" TIME_SLOT_REF2="t2"><ANNOTATION_VALUE>taroo=ga hon=o yom-da.</ANNOTATION_VALUE></ALIGNABLE_ANNOTATION></ANNOTATION><ANNOTATION><ALIGNABLE_ANNOTATION ANNOTATION_ID="a2" TIME_SLOT_REF1="t3" TIME_SLOT_REF2="t4"><ANNOTATION_VALUE>hana=ga sak-u.</ANNOTATION_VALUE></ALIGNABLE_ANNOTATION></ANNOTATION><ANNOTATION><ALIGNABLE_ANNOTATION ANNOTATION_ID="a3" TIME_SLOT_REF1="t5" TIME_SLOT_REF2="t6"><ANNOTATION_VALUE>ame=ga hur-u.</ANNOTATION_VALUE></ALIGNABLE_ANNOTATION></ANNOTATION></TIER><TIER TIER_ID="gloss" PARENT_REF="text"><ANNOTATION><REF_ANNOTATION ANNOTATION_ID="g1" ANNOTATION_REF="a1"><ANNOTATION_VALUE>Taro NOM book ACC read PST</ANNOTATION_VALUE></REF_ANNOTATION></ANNOTATION><ANNOTATION><REF_ANNOTATION ANNOTATION_ID="g2" ANNOTATION_REF="a2"><ANNOTATION_VALUE>flower NOM bloom NPST</ANNOTATION_VALUE></REF_ANNOTATION></ANNOTATION><ANNOTATION><REF_ANNOTATION ANNOTATION_ID="g3" ANNOTATION_REF="a3"><ANNOTATION_VALUE>rain NOM fall NPST</ANNOTATION_VALUE></REF_ANNOTATION></ANNOTATION></TIER><TIER TIER_ID="translation" PARENT_REF="text"><ANNOTATION><REF_ANNOTATION ANNOTATION_ID="f1" ANNOTATION_REF="a1"><ANNOTATION_VALUE>太郎が本を読んだ。</ANNOTATION_VALUE></REF_ANNOTATION></ANNOTATION><ANNOTATION><REF_ANNOTATION ANNOTATION_ID="f2" ANNOTATION_REF="a2"><ANNOTATION_VALUE>花が咲く。</ANNOTATION_VALUE></REF_ANNOTATION></ANNOTATION><ANNOTATION><REF_ANNOTATION ANNOTATION_ID="f3" ANNOTATION_REF="a3"><ANNOTATION_VALUE>雨が降る。</ANNOTATION_VALUE></REF_ANNOTATION></ANNOTATION></TIER></ANNOTATION_DOCUMENT>`;
  $("load-demo").addEventListener("click", async () => {
    if (state.busy) return;
    const pcm = new Int16Array(16000 * 5.2);
    for (let i = 0; i < pcm.length; i++) pcm[i] = Math.round(Math.sin(i * Math.PI * 2 * 220 / 16000) * 1800 * (0.5 - 0.5 * Math.cos(i / 3200)));
    const header = new ArrayBuffer(44), h = new DataView(header), ascii = (offset, value) => [...value].forEach((ch, i) => h.setUint8(offset + i, ch.charCodeAt(0)));
    ascii(0, "RIFF"); h.setUint32(4, 36 + pcm.byteLength, true); ascii(8, "WAVEfmt "); h.setUint32(16, 16, true); h.setUint16(20, 1, true); h.setUint16(22, 1, true); h.setUint32(24, 16000, true); h.setUint32(28, 32000, true); h.setUint16(32, 2, true); h.setUint16(34, 16, true); ascii(36, "data"); h.setUint32(40, pcm.byteLength, true);
    await Promise.all([loadEaf(new File([sampleEaf], "sample.eaf", { type: "application/xml" })), loadAudio(new File([header, pcm], "sample.wav", { type: "audio/wav" }))]);
  });
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) if (entry.isIntersecting) {
      for (const step of document.querySelectorAll(".step")) step.classList.toggle("active", step.getAttribute("href") === "#" + entry.target.id);
    }
  }, { rootMargin: "-12% 0px -65% 0px" });
  for (const id of ["files", "mapping", "export"]) observer.observe($(id));
  window.addEventListener("beforeunload", () => { for (const url of state.urls) URL.revokeObjectURL(url); });
  renderMapping();
})();
