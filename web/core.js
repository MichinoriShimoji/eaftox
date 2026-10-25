/* eaftox browser core. No network requests or runtime dependencies. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.Eaftox = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const VERSION = "2026.10-browser.1";
  const MODES = ["シンプル3層", "3層", "4層"];
  const NONE = "";
  const isPunctuation = text => /^[^\p{L}\p{N}_\s]+$/u.test(text);
  const normalize = text => (text || "").replace(/==/g, "=").replace(/--/g, "-").replace(/\+\+/g, "+").replace(/\.\./g, ".");
  const overlaps = (ann, start, end) => Math.max(ann.start_time, start) < Math.min(ann.end_time, end) || (ann.start_time === start && ann.end_time === end);

  function parseEaf(xml, Parser = globalThis.DOMParser) {
    if (!Parser) throw new Error("このブラウザはXMLの読み込みに対応していません。");
    if (/<!DOCTYPE|<!ENTITY/i.test(xml)) throw new Error("DOCTYPE・ENTITYを含むEAFは読み込めません。");
    const doc = new Parser().parseFromString(xml, "application/xml");
    if (doc.getElementsByTagName("parsererror").length || doc.documentElement?.localName !== "ANNOTATION_DOCUMENT") {
      throw new Error("正しいEAFファイルではありません。ELANから保存した .eaf を選択してください。");
    }
    const elements = (node, name) => [...node.getElementsByTagNameNS("*", name)];
    const slots = new Map();
    for (const slot of elements(doc, "TIME_SLOT")) {
      const value = slot.getAttribute("TIME_VALUE");
      if (value === null || value.trim() === "") continue;
      const time = Number(value);
      if (!Number.isSafeInteger(time) || time < 0) throw new Error("EAFの時間値が不正です。");
      slots.set(slot.getAttribute("TIME_SLOT_ID"), time);
    }
    const tiers = elements(doc, "TIER").map(tier => ({
      id: tier.getAttribute("TIER_ID"), parent: tier.getAttribute("PARENT_REF") || "",
      participant: tier.getAttribute("PARTICIPANT") || "", type: tier.getAttribute("LINGUISTIC_TYPE_REF") || "",
      annotations: [...tier.getElementsByTagNameNS("*", "*")]
        .filter(node => ["ALIGNABLE_ANNOTATION", "REF_ANNOTATION"].includes(node.localName))
        .map(ann => ({
          annotation_id: ann.getAttribute("ANNOTATION_ID"),
          value: elements(ann, "ANNOTATION_VALUE")[0]?.textContent.trim() || "",
          ref_id: ann.getAttribute("ANNOTATION_REF") || undefined,
          start_time: slots.get(ann.getAttribute("TIME_SLOT_REF1")),
          end_time: slots.get(ann.getAttribute("TIME_SLOT_REF2"))
        }))
    }));
    return resolveTiers(tiers);
  }

  function resolveTiers(records) {
    const all = new Map();
    for (const tier of records) {
      if (!tier.id) throw new Error("ティア名がないEAFです。");
      for (const ann of tier.annotations) {
        if (all.has(ann.annotation_id)) throw new Error(`アノテーションIDが重複しています: ${ann.annotation_id}`);
        all.set(ann.annotation_id, ann);
      }
    }
    const resolved = new Map();
    function resolve(id, visiting = new Set()) {
      if (resolved.has(id)) return resolved.get(id);
      const ann = all.get(id);
      if (!ann || visiting.has(id)) return null;
      visiting.add(id);
      let time;
      if (ann.ref_id) time = resolve(ann.ref_id, visiting);
      else if (Number.isFinite(ann.start_time) && Number.isFinite(ann.end_time) && ann.end_time >= ann.start_time) {
        time = [ann.start_time, ann.end_time];
      }
      visiting.delete(id);
      resolved.set(id, time || null);
      return time;
    }
    const tiers = new Map();
    const info = [];
    let skipped = 0;
    for (const tier of records) {
      if (tiers.has(tier.id)) throw new Error(`ティア名が重複しています: ${tier.id}`);
      const annotations = [];
      for (const ann of tier.annotations) {
        const time = resolve(ann.annotation_id);
        if (!time) { skipped++; continue; }
        annotations.push({ ...ann, start_time: time[0], end_time: time[1] });
      }
      annotations.sort((a, b) => a.start_time - b.start_time);
      tiers.set(tier.id, annotations);
      info.push({ id: tier.id, parent: tier.parent || "", participant: tier.participant || "", type: tier.type || "", count: annotations.length, sample: annotations[0]?.value || "" });
    }
    return { tiers, info, skipped };
  }

  function guessSpeakers(eaf) {
    const byId = new Map(eaf.info.map(tier => [tier.id, tier]));
    function participant(tier, seen = new Set()) {
      if (!tier || seen.has(tier.id)) return "";
      seen.add(tier.id);
      return tier.participant || participant(byId.get(tier.parent), seen);
    }
    const suffix = name => name.match(/(?:[_@-]([A-H1-8])|@([^@]+))$/i)?.slice(1).find(Boolean) || name.match(/^([A-H1-8])[_@-]/i)?.[1] || "";
    const keys = [...new Set(eaf.info.map(t => participant(t)).filter(Boolean))];
    const hasParticipants = keys.length > 0;
    if (!keys.length) keys.push(...new Set(eaf.info.map(t => suffix(t.id)).filter(Boolean)));
    if (!keys.length) keys.push("");
    const rolePatterns = {
      text0: /(?:text0|surface|orthograph|phonetic|表層|音声表記)/i,
      text: /(?:text(?!0)|transcript|utterance|phrase|sentence|\btx\b|発話|本文|転写)/i,
      morph: /(?:morph|morpheme|\bmb\b|形態素)/i,
      gloss: /(?:gloss|\bgl\b|\bge\b|グロス)/i,
      pos: /(?:\bpos\b|\bps\b|part.of.speech|品詞)/i,
      trans: /(?:translat|trans(?!cript)|free.?trans|\bft\b|訳|翻訳)/i
    };
    return keys.slice(0, 8).map((key, index) => {
      let candidates = eaf.info.filter(tier => hasParticipants ? participant(tier) === key || (!participant(tier) && keys.length === 1) : (suffix(tier.id) === key || (!suffix(tier.id) && index === 0)));
      if (!candidates.length) candidates = eaf.info;
      const tiers = { text0: "", text: "", morph: "", gloss: "", pos: "", trans: "" };
      const used = new Set();
      for (const role of ["text0", "gloss", "pos", "trans", "morph", "text"]) {
        const match = candidates.find(tier => tier.count && !used.has(tier.id) && rolePatterns[role].test(tier.id.replace(/[_@-]/g, " ") + " " + tier.type));
        if (match) { tiers[role] = match.id; used.add(match.id); }
      }
      let uncertain = false;
      if (!tiers.text && !tiers.text0) {
        const base = candidates.find(tier => tier.count && !tier.parent && !used.has(tier.id)) || candidates.find(tier => tier.count && !used.has(tier.id));
        if (base) tiers.text = base.id;
        uncertain = true;
      }
      return { name: key || `話者${index + 1}`, mode: tiers.text0 ? "4層" : tiers.morph ? "3層" : "シンプル3層", tiers, uncertain: uncertain || !tiers.gloss || !tiers.trans };
    });
  }

  // Keep the EAF hierarchy separate from output roles: roles never create edges.
  function buildTierForest(info) {
    const nodes = new Map(info.map(tier => [tier.id, { tier, children: [], warning: "" }]));
    const parents = new Map();
    for (const tier of info) {
      if (tier.parent && nodes.has(tier.parent)) parents.set(tier.id, tier.parent);
      else if (tier.parent) nodes.get(tier.id).warning = `親ティア「${tier.parent}」が見つかりません。`;
    }
    const visited = new Set();
    for (const tier of info) {
      const path = [], positions = new Map();
      let id = tier.id;
      while (id && !visited.has(id)) {
        if (positions.has(id)) {
          for (const cyclic of path.slice(positions.get(id))) nodes.get(cyclic).warning = "親子関係が循環しています。図では循環する接続を1本省略しています。";
          parents.delete(path.at(-1));
          break;
        }
        positions.set(id, path.length); path.push(id); id = parents.get(id);
      }
      for (const seen of path) visited.add(seen);
    }
    const roots = [];
    for (const [id, node] of nodes) {
      const parent = parents.get(id);
      if (parent) nodes.get(parent).children.push(node);
      else roots.push(node);
    }
    return roots;
  }

  function extractSentences(eaf, speakers) {
    const sentences = [];
    for (const [speakerIndex, speaker] of speakers.entries()) {
      const { mode, tiers } = speaker;
      const baseRole = mode === "4層" && eaf.tiers.has(tiers.text0) ? "text0" : "text";
      const base = eaf.tiers.get(tiers[baseRole]);
      if (!base) throw new Error(`話者${speakerIndex + 1}の ${baseRole} ティアを選択してください。`);
      for (const ann of base) {
        if (!ann.value) continue;
        const start = ann.start_time, end = ann.end_time;
        const sent = { start_time: start, end_time: end, speaker: speaker.name || `話者${speakerIndex + 1}`, mode,
          text0: null, text: null, morph: null, gloss: null, pos: null, trans: null };
        sent[baseRole] = ann.value;
        const excluded = new Set();
        for (const gloss of eaf.tiers.get(tiers.gloss) || []) {
          if (((gloss.start_time >= start && gloss.end_time <= end) || overlaps(gloss, start, end)) && /^EO[A-Z]+$/i.test(gloss.value.trim()) && gloss.ref_id) excluded.add(gloss.ref_id);
        }
        if (mode !== "シンプル3層") {
          for (const morph of eaf.tiers.get(tiers.morph) || []) {
            if (morph.start_time < end && morph.end_time > start && isPunctuation(morph.value.trim())) excluded.add(morph.annotation_id);
          }
        }
        for (const [role, tier] of Object.entries(tiers)) {
          if (role === baseRole || !tier || !eaf.tiers.has(tier)) continue;
          if (role === "text0" && mode !== "4層") continue;
          if (role === "morph" && mode === "シンプル3層") continue;
          sent[role] = eaf.tiers.get(tier).filter(a => overlaps(a, start, end) && !excluded.has(role === "morph" ? a.annotation_id : a.ref_id))
            .map(a => a.value).filter(Boolean).join(" ");
        }
        if (sent.text && sent.text0) sent.text = sent.text.replace(/\s*([,!?;:。、！？；：]+|(?<!\.)\.(?!\.))\s*$/u, "").trimEnd();
        sentences.push(sent);
      }
    }
    return sentences.sort((a, b) => a.start_time - b.start_time);
  }

  function alignMorphs(text, gloss) {
    if (!text || !gloss) return gloss || "";
    text = text.split(/\s+/).filter(word => !isPunctuation(word)).map(word => word.replace(/[.,!?;:。、！？；：]+$/u, "")).filter(Boolean).join(" ");
    if (!text) return gloss;
    const glosses = gloss.trim().split(/\s+/);
    const parts = [];
    let idx = 0;
    const boundaries = ["=", "-", "+", ".", "_"];
    const splitGloss = item => item.split(/([=\-+_])/).filter(s => !["=", "-", "+", "_"].includes(s) && s.trim() && !isPunctuation(s));
    for (const word of text.split(/\s+/)) {
      const segments = word.split(/([=\-+._])/);
      const count = segments.filter(s => !boundaries.includes(s) && s.trim()).length;
      if (!count) { parts.push(word); continue; }
      if (idx >= glosses.length) break;
      const leading = segments[0] === "" && ["=", "-", "+", "_"].includes(segments[1]) ? segments[1] : "";
      const trailing = segments.at(-1) === "" && ["=", "-", "+", "_"].includes(segments.at(-2)) ? segments.at(-2) : "";
      const current = glosses[idx];
      const glossCount = splitGloss(current).length;
      if (glossCount === count) {
        parts.push(leading + current + trailing); idx++;
      } else if (glossCount === 1 && count > 1) {
        const wordGlosses = [];
        let needed = count;
        while (needed > 0 && idx < glosses.length) {
          const g = glosses[idx], n = splitGloss(g).length;
          if (n > needed) break;
          wordGlosses.push(g); needed -= n; idx++;
        }
        if (wordGlosses.length) {
          const combined = wordGlosses.flatMap(g => g.split(/([=\-+_])/).filter(p => p.trim()));
          let ci = 0;
          parts.push(segments.map(s => ["=", "-", "+", "_"].includes(s) ? s : s === "." ? "" : s.trim() && ci < combined.length ? combined[ci++] : "").join(""));
        }
      } else { parts.push(leading + current + trailing); idx++; }
    }
    return parts.join(" ").replace(/[=\-+_]+$/, "").trimEnd();
  }

  const IPA_TO_TIPA = {
    "ɨ": "\\textbari{}",
    "ɯ": "\\textturnm{}",
    "ɛ": "\\textepsilon{}",
    "ɔ": "\\textopeno{}",
    "æ": "\\textae{}",
    "ɑ": "\\textscripta{}",
    "ɒ": "\\textturnscripta{}",
    "ə": "\\textschwa{}",
    "ɪ": "\\textsci{}",
    "ʊ": "\\textupsilon{}",
    "ʃ": "\\textesh{}",
    "ʒ": "\\textyogh{}",
    "θ": "\\texttheta{}",
    "ð": "\\textdh{}",
    "ŋ": "\\texteng{}",
    "ɲ": "\\textltailn{}",
    "ɳ": "\\textrtailn{}",
    "ɱ": "\\textmrleg{}",
    "ɾ": "\\textfishhookr{}",
    "ɽ": "\\textrtailr{}",
    "ɻ": "\\textturnr{}",
    "ɭ": "\\textrtaill{}",
    "ʎ": "\\textturny{}",
    "ʈ": "\\textrtailt{}",
    "ɖ": "\\textrtaild{}",
    "ʂ": "\\textrtails{}",
    "ʐ": "\\textrtailz{}",
    "ɕ": "\\textctc{}",
    "ʑ": "\\textctj{}",
    "ç": "\\textc{c}",
    "ʝ": "\\textctj{}",
    "ɣ": "\\textgamma{}",
    "χ": "\\textchi{}",
    "ʁ": "\\textinvscr{}",
    "ħ": "\\textcrh{}",
    "ʕ": "\\textrevglotstop{}",
    "ʔ": "\\textglotstop{}",
    "ɸ": "\\textphi{}",
    "β": "\\textbeta{}",
    "ʋ": "\\textscriptv{}",
    "ɹ": "\\textturnr{}",
    "ɰ": "\\textturnmrleg{}",
    "ɺ": "\\textlhti{}",
    "ɢ": "\\textscg{}",
    "ʛ": "\\texthtg{}",
    "ɠ": "\\texthtg{}",
    "ɡ": "\\textscg{}",
    "ː": ":",
    "ˈ": "\\textprimstress{}",
    "ˌ": "\\textsecstress{}",
    "ʲ": "\\textpal{}",
    "ʷ": "\\textlab{}",
    "ʰ": "\\textsuperscript{h}",
    "ⁿ": "\\textsuperscript{n}",
    "ʼ": "\\textglotstop{}",
    "Ø": "\\O{}",
    "ø": "\\o{}",
    "∅": "$\\emptyset$",
    "ž": "Z",
    "Ž": "Z",
    "š": "S",
    "Š": "S",
    "č": "C",
    "Č": "C"
};
  function ipaToTipa(text) {
    if (!text) return "";
    text = text.replace(/_/g, "\\_").replace(/\^/g, "\\^{}").replace(/%/g, "\\%").replace(/&/g, "\\&").replace(/#/g, "\\#").replace(/~/g, "\\~{}").replace(/\$/g, "\\$");
    for (const [ipa, tipa] of Object.entries(IPA_TO_TIPA)) text = text.split(ipa).join(tipa);
    return text;
  }
  const leipzig = text => text.replace(/(?<![A-Za-z0-9])[A-Z]{2,}[0-9]*(?![A-Za-z])/g, match => `\\textsc{${match.toLowerCase()}}`);
  const latexEscape = text => (text || "").replace(/[\\{}%&#_$^~]/g, ch => ({"\\":"\\textbackslash{}", "^":"\\^{}", "~":"\\~{}"}[ch] || "\\" + ch));

  function toText(sentences) {
    const output = [], showSpeaker = new Set(sentences.map(s => s.speaker).filter(Boolean)).size > 1;
    sentences.forEach((sent, index) => {
      if (!sent.text0 && !sent.text) return;
      output.push(`(${index + 1})${showSpeaker && sent.speaker ? ` [${sent.speaker}]` : ""}`);
      if (sent.mode === "4層" && sent.text0) output.push(normalize(sent.text0));
      if (sent.text) output.push(normalize(sent.text));
      const base = sent.text || sent.text0;
      for (const role of ["gloss", "pos"]) if (sent[role] && base) output.push(normalize(alignMorphs(base, sent[role])));
      if (sent.trans) output.push(sent.trans);
      output.push("");
    });
    return output.join("\n");
  }

  function toGb4e(sentences, style = "標準版") {
    const minimal = style === "最小限版", spacing = style === "行間調整版";
    const output = ["\\documentclass{jarticle}", "\\usepackage{gb4e}", "\\usepackage{tipa}"];
    if (!minimal) output.push("% \\usepackage{leipzig}");
    if (spacing) output.push("\\let\\eachwordone=\\it", "\\let\\eachwordtwo=\\rm", "\\def\\glossglue{\\hfil}");
    output.push("", "\\begin{document}", "");
    const showSpeaker = new Set(sentences.map(s => s.speaker).filter(Boolean)).size > 1;
    for (const sent of sentences) {
      if (!sent.text0 && !sent.text) continue;
      const label = showSpeaker && sent.speaker ? `\\textbf{[${latexEscape(sent.speaker)}]}` : "";
      if (minimal) output.push("\\begin{exe}\\ex" + (label ? " " + label : ""));
      else { output.push("\\begin{exe}", "\\ex"); if (label) output.push(label); }
      const four = sent.mode === "4層", indent = minimal ? "" : four ? "      " : "     ";
      if (four) output.push(`\\glll ${ipaToTipa(normalize(sent.text0))}\\\\`, `${indent}${ipaToTipa(normalize(sent.text))}\\\\`);
      else output.push(`\\gll ${ipaToTipa(normalize(sent.text))}\\\\`);
      const base = sent.text || sent.text0;
      const gloss = sent.gloss && base ? ipaToTipa(leipzig(normalize(alignMorphs(base, sent.gloss)))) : "";
      output.push(indent + gloss + "\\\\");
      const trans = latexEscape(sent.trans);
      if (minimal) output.push((trans ? `\\glt \`${trans}'` : "\\glt") + "\\end{exe}");
      else { output.push(trans ? spacing ? `\\glt \`${trans}'%` : `\\glt ${trans}` : "\\glt"); output.push("\\end{exe}"); }
      output.push("");
    }
    output.push("\\end{document}");
    return output.join("\n");
  }

  const readAscii = (view, offset, length) => String.fromCharCode(...new Uint8Array(view.buffer, view.byteOffset + offset, length));
  const writeAscii = (view, offset, text) => [...text].forEach((ch, i) => view.setUint8(offset + i, ch.charCodeAt(0)));
  async function openWav(file) {
    const first = new DataView(await file.slice(0, 12).arrayBuffer());
    if (first.byteLength < 12 || readAscii(first, 0, 4) !== "RIFF" || readAscii(first, 8, 4) !== "WAVE") throw new Error("対応するRIFF WAVではありません。PCMまたはIEEE FloatのWAVを選択してください。");
    const limit = first.getUint32(4, true) + 8;
    if (limit > file.size || limit < 12) throw new Error("WAVファイルが途中で切れているか、ヘッダーが不正です。");
    let fmt = null, format, channels, sampleRate, blockAlign, bits, data = [];
    for (let offset = 12; offset + 8 <= limit;) {
      const header = new DataView(await file.slice(offset, offset + 8).arrayBuffer());
      const name = readAscii(header, 0, 4), size = header.getUint32(4, true), start = offset + 8;
      if (start + size > limit) throw new Error(`WAVの ${name} チャンクが不正です。`);
      if (name === "fmt " && fmt === null) {
        if (size < 16 || size > 65536) throw new Error("WAVの形式情報が不正です。");
        fmt = await file.slice(start, start + size).arrayBuffer();
        const f = new DataView(fmt);
        format = f.getUint16(0, true); channels = f.getUint16(2, true); sampleRate = f.getUint32(4, true); blockAlign = f.getUint16(12, true); bits = f.getUint16(14, true);
        if (format === 65534) {
          if (size < 40 || f.getUint16(16, true) < 22 || readAscii(f, 28, 12) !== "\u0000\u0000\u0010\u0000\u0080\u0000\u0000\u00aa\u0000\u0038\u009b\u0071") throw new Error("対応していないWAV拡張形式です。");
          format = f.getUint32(24, true);
        }
        if (![1, 3].includes(format) || !channels || !sampleRate || !blockAlign || blockAlign !== channels * bits / 8 || !(format === 1 ? [8, 16, 24, 32] : [32, 64]).includes(bits)) throw new Error("圧縮WAVは未対応です。PCMまたはIEEE FloatのWAVに変換してください。");
      } else if (name === "data") data.push({ offset: start, bytes: size });
      offset = start + size + size % 2;
    }
    if (!fmt || !data.length) throw new Error("WAVの形式情報または音声データがありません。");
    if (data.some(part => part.bytes % blockAlign)) throw new Error("WAVの音声データ長が不正です。");
    let total = 0;
    data = data.map(part => { const result = { ...part, firstFrame: total, frames: part.bytes / blockAlign }; total += result.frames; return result; });
    if (!total) throw new Error("WAVに音声が含まれていません。");
    return { kind: "wav", file, fmt, format, channels, sampleRate, blockAlign, bits, frames: total, duration: total / sampleRate, data };
  }

  function segmentBounds(audio, startMs, endMs, paddingMs = 100) {
    if (![startMs, endMs, paddingMs].every(Number.isFinite) || startMs < 0 || endMs <= startMs || paddingMs < 0) throw new Error(`音声区間が不正です: ${startMs}–${endMs} ms`);
    const start = Math.floor(Math.max(0, startMs - paddingMs) * audio.sampleRate / 1000);
    const end = Math.min(audio.frames, Math.floor((endMs + paddingMs) * audio.sampleRate / 1000));
    if (end <= start) throw new Error(`音声の範囲外です: ${startMs}–${endMs} ms（音声 ${audio.duration.toFixed(2)} 秒）`);
    return { start, end };
  }

  function wavBlob(fmt, format, frames, parts) {
    const bytes = parts.reduce((sum, part) => sum + (part.size ?? part.byteLength), 0), pad = bytes % 2;
    const fmtPad = fmt.byteLength % 2, factSize = format === 3 ? 12 : 0;
    const headerSize = 12 + 8 + fmt.byteLength + fmtPad + factSize + 8;
    if (headerSize + bytes + pad - 8 > 0xffffffff) throw new Error("4GBを超えるWAV区間は保存できません。");
    const header = new ArrayBuffer(headerSize), view = new DataView(header);
    writeAscii(view, 0, "RIFF"); view.setUint32(4, headerSize + bytes + pad - 8, true); writeAscii(view, 8, "WAVE");
    writeAscii(view, 12, "fmt "); view.setUint32(16, fmt.byteLength, true); new Uint8Array(header, 20, fmt.byteLength).set(new Uint8Array(fmt));
    let offset = 20 + fmt.byteLength + fmtPad;
    if (format === 3) { writeAscii(view, offset, "fact"); view.setUint32(offset + 4, 4, true); view.setUint32(offset + 8, frames, true); offset += 12; }
    writeAscii(view, offset, "data"); view.setUint32(offset + 4, bytes, true);
    return new Blob([header, ...parts, ...(pad ? [new Uint8Array(1)] : [])], { type: "audio/wav" });
  }

  function sliceWav(audio, startMs, endMs, paddingMs = 100) {
    const { start, end } = segmentBounds(audio, startMs, endMs, paddingMs);
    const parts = [];
    for (const part of audio.data) {
      const lo = Math.max(start, part.firstFrame), hi = Math.min(end, part.firstFrame + part.frames);
      if (hi > lo) parts.push(audio.file.slice(part.offset + (lo - part.firstFrame) * audio.blockAlign, part.offset + (hi - part.firstFrame) * audio.blockAlign));
    }
    return wavBlob(audio.fmt, audio.format, end - start, parts);
  }

  function sliceDecodedAudio(audio, startMs, endMs, paddingMs = 100) {
    const { start, end } = segmentBounds(audio, startMs, endMs, paddingMs);
    const output = new ArrayBuffer((end - start) * audio.channels * 2), view = new DataView(output);
    const channels = Array.from({ length: audio.channels }, (_, i) => audio.buffer.getChannelData(i));
    let offset = 0;
    for (let frame = start; frame < end; frame++) for (const channel of channels) {
      const sample = Math.max(-1, Math.min(1, channel[frame]));
      view.setInt16(offset, sample < 0 ? Math.round(sample * 32768) : Math.round(sample * 32767), true); offset += 2;
    }
    const fmt = new ArrayBuffer(16), f = new DataView(fmt);
    f.setUint16(0, 1, true); f.setUint16(2, audio.channels, true); f.setUint32(4, audio.sampleRate, true); f.setUint32(8, audio.sampleRate * audio.channels * 2, true); f.setUint16(12, audio.channels * 2, true); f.setUint16(14, 16, true);
    return wavBlob(fmt, 1, end - start, [output]);
  }

  const CRC_TABLE = Uint32Array.from({ length: 256 }, (_, n) => { for (let i = 0; i < 8; i++) n = n & 1 ? 0xedb88320 ^ (n >>> 1) : n >>> 1; return n >>> 0; });
  function crc32(bytes, crc = 0xffffffff) { for (const byte of bytes) crc = CRC_TABLE[(crc ^ byte) & 255] ^ (crc >>> 8); return crc >>> 0; }
  const cancelled = signal => { if (signal?.aborted) throw new Error("処理を中止しました。"); };
  async function makeZip(entries, { signal, onProgress = () => {} } = {}) {
    if (entries.length > 65535) throw new Error("ZIP内のファイル数が多すぎます。");
    const parts = [], central = [], encoder = new TextEncoder();
    let offset = 0;
    for (let index = 0; index < entries.length; index++) {
      cancelled(signal);
      const { name, blob } = entries[index], encoded = encoder.encode(name);
      if (!name || name.split("/").includes("..") || name.startsWith("/") || name.includes("\\") || encoded.length > 65535) throw new Error("ZIPのファイル名が不正です。");
      if (blob.size > 0xffffffff || offset + blob.size + 30 + encoded.length > 0xffffffff) throw new Error("合計4GBを超えるZIPは保存できません。話者や対象範囲を減らしてください。");
      let crc = 0xffffffff;
      for (let pos = 0; pos < blob.size; pos += 1024 * 1024) {
        cancelled(signal);
        crc = crc32(new Uint8Array(await blob.slice(pos, pos + 1024 * 1024).arrayBuffer()), crc);
      }
      crc = (crc ^ 0xffffffff) >>> 0;
      const header = new ArrayBuffer(30), h = new DataView(header);
      h.setUint32(0, 0x04034b50, true); h.setUint16(4, 20, true); h.setUint16(6, 0x800, true); h.setUint16(12, 0x21, true);
      h.setUint32(14, crc, true); h.setUint32(18, blob.size, true); h.setUint32(22, blob.size, true); h.setUint16(26, encoded.length, true);
      const directory = new ArrayBuffer(46), d = new DataView(directory);
      d.setUint32(0, 0x02014b50, true); d.setUint16(4, 20, true); d.setUint16(6, 20, true); d.setUint16(8, 0x800, true); d.setUint16(14, 0x21, true);
      d.setUint32(16, crc, true); d.setUint32(20, blob.size, true); d.setUint32(24, blob.size, true); d.setUint16(28, encoded.length, true); d.setUint32(42, offset, true);
      parts.push(header, encoded, blob); central.push(directory, encoded);
      offset += 30 + encoded.length + blob.size;
      onProgress((index + 1) / entries.length);
      // Yield between entries so the progress indicator and cancel button work.
      await new Promise(resolve => setTimeout(resolve, 0));
    }
    const centralSize = central.reduce((sum, part) => sum + part.byteLength, 0);
    if (offset + centralSize + 22 > 0xffffffff) throw new Error("ZIPのサイズが4GBを超えます。");
    const end = new ArrayBuffer(22), e = new DataView(end);
    e.setUint32(0, 0x06054b50, true); e.setUint16(8, entries.length, true); e.setUint16(10, entries.length, true); e.setUint32(12, centralSize, true); e.setUint32(16, offset, true);
    cancelled(signal);
    return new Blob([...parts, ...central, end], { type: "application/zip" });
  }

  const safeName = value => (value || "").normalize("NFC").replace(/[^\p{L}\p{N}_\s-]/gu, "").trim().replace(/\s+/g, "_").slice(0, 50);
  function audioFilename(sent, index) { return `audio_segments/${String(index + 1).padStart(3, "0")}_${safeName(sent.speaker)}_${safeName((sent.text0 || sent.text || "").slice(0, 30)) || "sentence"}.wav`; }

  return { VERSION, MODES, NONE, parseEaf, resolveTiers, guessSpeakers, buildTierForest, extractSentences, alignMorphs, normalize, ipaToTipa, toText, toGb4e, openWav, sliceWav, sliceDecodedAudio, segmentBounds, makeZip, crc32, audioFilename };
});
