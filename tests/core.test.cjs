const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const E = require('../web/core.js');
const reference = require('./reference.json');

function makeWav({bits = 16, channels = 1, rate = 16000, frames = 80000, float = false, extensible = false, extra = false} = {}) {
  const fmt = Buffer.alloc(extensible ? 40 : 16), block = channels * bits / 8;
  fmt.writeUInt16LE(extensible ? 65534 : float ? 3 : 1, 0); fmt.writeUInt16LE(channels, 2); fmt.writeUInt32LE(rate, 4); fmt.writeUInt32LE(rate * block, 8); fmt.writeUInt16LE(block, 12); fmt.writeUInt16LE(bits, 14);
  if (extensible) { fmt.writeUInt16LE(22, 16); fmt.writeUInt16LE(bits, 18); fmt.writeUInt32LE(float ? 3 : 1, 24); Buffer.from([0,0,16,0,128,0,0,170,0,56,155,113]).copy(fmt,28); }
  const data = Buffer.alloc(frames * block);
  for (let i = 0; i < data.length; i++) data[i] = (i * 37) % 256;
  const chunk = (name, value) => { const header = Buffer.alloc(8); header.write(name); header.writeUInt32LE(value.length, 4); return Buffer.concat([header, value, ...(value.length % 2 ? [Buffer.alloc(1)] : [])]); };
  const body = Buffer.concat([chunk('fmt ', fmt), ...(extra ? [chunk('JUNK', Buffer.from('12345'))] : []), chunk('data', data)]);
  const header = Buffer.alloc(12); header.write('RIFF'); header.writeUInt32LE(body.length + 4, 4); header.write('WAVE',8);
  return {blob:new Blob([header,body]), data, block};
}

test('original Python parity: speaker modes, REF chains, EOS, IPA, all GB4E styles', () => {
  const eaf = E.resolveTiers(reference.records);
  for (const sample of reference.cases) {
    const sentences = E.extractSentences(eaf, sample.speakers);
    assert.deepEqual(sentences, sample.sentences);
    assert.equal(E.toText(sentences), sample.text);
    for (const [style, output] of Object.entries(sample.gb4e)) assert.equal(E.toGb4e(sentences,style), output);
  }
});
test('speaker detection inherits participant through parents and separates A/B', () => {
  const guessed = E.guessSpeakers(E.resolveTiers(reference.records));
  assert.equal(guessed.length, 2);
  assert.equal(guessed[0].name, 'A'); assert.equal(guessed[0].mode,'4層'); assert.equal(guessed[0].tiers.trans,'translation@A');
  assert.equal(guessed[1].name, 'B'); assert.equal(guessed[1].tiers.gloss,'gloss@B');
  assert.equal(E.extractSentences(E.resolveTiers(reference.records),guessed).length,2);
});
test('speaker detection works with suffix names when participant is absent', () => {
  const records = reference.records.map(tier=>({...tier,participant:''}));
  assert.deepEqual(E.guessSpeakers(E.resolveTiers(records)).map(s=>s.name),['A','B']);
});
test('actual repository EAF samples: each structure is mapped and yields four sentences', () => {
  const fixtures = require('./repository-samples.json');
  for (const fixture of fixtures) {
    const eaf = E.resolveTiers(fixture.records), speakers = E.guessSpeakers(eaf);
    assert.equal(speakers.length,1,fixture.file);
    assert.equal(speakers[0].uncertain,false,fixture.file);
    assert.equal(E.extractSentences(eaf,speakers).length,4,fixture.file);
    if(fixture.file==='sample4.eaf') {assert.equal(speakers[0].mode,'4層');assert.equal(speakers[0].tiers.text,'text1');}
  }
});
test('bad reference cycles are reported instead of hanging', () => {
  const eaf = E.resolveTiers([{id:'text',annotations:[{annotation_id:'a',ref_id:'b',value:'x'},{annotation_id:'b',ref_id:'a',value:'y'}]}]);
  assert.equal(eaf.skipped,2); assert.equal(eaf.tiers.get('text').length,0);
});
test('LaTeX escaping covers translations and speaker labels', () => {
  const output = E.toGb4e([{text:'a',trans:'50% & x_y $1',speaker:'A&B'},{text:'b',speaker:'C'}]);
  assert.ok(output.includes('50\\% \\& x\\_y \\$1'));
  assert.ok(output.includes('[A\\&B]'));
});
test('chain selection removes output rows while preserving segmentation and gloss alignment', () => {
  const eaf = E.resolveTiers(reference.records), speaker = {...reference.cases[0].speakers[0], excludedRoles: []};
  const all = E.extractSentences(eaf,[speaker])[0];
  assert.deepEqual(E.outputRows(all).map(row=>row.role),['text0','text','morph','gloss','pos','trans']);
  const selected = E.extractSentences(eaf,[{...speaker,excludedRoles:['text0','morph','pos','trans']}])[0];
  assert.equal(selected.start_time,all.start_time); assert.equal(selected.end_time,all.end_time);
  assert.deepEqual(E.outputRows(selected).map(row=>row.role),['text','gloss']);
  assert.equal(E.outputRows(selected)[1].text,'3SG=NOM book=ACC read-PST');
  assert.equal(E.toText([selected]),'(1)\nɕi=ga hon=o yom-da\n3SG=NOM book=ACC read-PST\n');
  for(const style of ['標準版','行間調整版','最小限版']) {
    const tex = E.toGb4e([selected],style);
    assert.ok(tex.includes('\\gll ')); assert.ok(!tex.includes('\\glll '));
    assert.ok(!tex.includes('\\glt')); assert.ok(!tex.includes('彼が本を読んだ。'));
    assert.ok(!tex.includes('\\begin{tabular}'));
  }
  assert.deepEqual(E.extractSentences(eaf,[speaker])[0],all);
});
test('all rows can be hidden, including source text, independently for each speaker', () => {
  const eaf = E.resolveTiers(reference.records), [a,b] = reference.cases[0].speakers;
  const hidden = ['text0','text','morph','gloss','pos','trans'];
  assert.deepEqual(E.extractSentences(eaf,[{...a,excludedRoles:hidden}]),[]);
  const onlyB = E.extractSentences(eaf,[{...a,excludedRoles:hidden},{...b,excludedRoles:[]}]);
  assert.equal(onlyB.length,1); assert.equal(onlyB[0].speaker,'B');
  const onlyGloss = E.extractSentences(eaf,[{...a,excludedRoles:hidden.filter(role=>role!=='gloss')}]);
  assert.equal(E.toText(onlyGloss),'(1)\n3SG=NOM book=ACC read-PST\n');
  assert.ok(!E.toGb4e(onlyGloss).includes('\\gll'));
  const onlyTrans = E.extractSentences(eaf,[{...a,excludedRoles:hidden.filter(role=>role!=='trans')}]);
  assert.equal(E.toText(onlyTrans),'(1)\n彼が本を読んだ。\n');
  assert.ok(E.toGb4e(onlyTrans).includes('彼が本を読んだ。'));
});
test('selected LaTeX rows use valid two/three-line macros or a table for more rows', () => {
  const speaker = {...reference.cases[0].speakers[0],excludedRoles:[]};
  const eaf = E.resolveTiers(reference.records);
  const all = E.extractSentences(eaf,[speaker]);
  assert.ok(E.toGb4e(all).includes('\\begin{tabular}[t]{@{}llllll@{}}'));
  assert.ok(E.toGb4e(all).includes('\\end{tabular}\n\\par 彼が本を読んだ。'));
  const three = E.extractSentences(eaf,[{...speaker,excludedRoles:['morph','pos']}]);
  assert.ok(E.toGb4e(three).includes('\\glll '));
  assert.ok(E.toGb4e(three).includes('\\glt 彼が本を読んだ。'));
});
for (const config of [{bits:8,channels:1},{bits:16,channels:2},{bits:24,channels:2,extra:true},{bits:32,channels:1},{bits:32,channels:2,float:true},{bits:64,channels:1,float:true},{bits:24,channels:2,extensible:true},{bits:32,channels:2,float:true,extensible:true}]) {
  test(`WAV exact frame slicing preserves ${JSON.stringify(config)}`, async () => {
    const fixture = makeWav(config), audio = await E.openWav(fixture.blob);
    const output = E.sliceWav(audio,1000,2000,100), result = await E.openWav(output);
    assert.equal(result.frames, 19200); assert.equal(result.channels, config.channels); assert.equal(result.bits,config.bits);
    const bytes = Buffer.from(await output.slice(result.data[0].offset,result.data[0].offset+result.data[0].bytes).arrayBuffer());
    assert.deepEqual(bytes,fixture.data.subarray(14400*fixture.block,33600*fixture.block));
    assert.equal(output.size % 2,0);
  });
}
test('WAV bounds clip padding, reject empty/out-of-range segments', async () => {
  const audio = await E.openWav(makeWav().blob);
  assert.equal((await E.openWav(E.sliceWav(audio,0,100,100))).frames,3200);
  assert.equal((await E.openWav(E.sliceWav(audio,4900,5100,100))).frames,3200);
  assert.throws(()=>E.sliceWav(audio,5100,5200,0),/範囲外/);
  assert.throws(()=>E.sliceWav(audio,100,100,0),/不正/);
});
test('40MB WAV reads header only, never loads all samples', async () => {
  const fixture = makeWav({frames:20000000});
  let readBytes = 0;
  const file = {size:fixture.blob.size,slice:(lo,hi)=>{readBytes += Math.min(hi,fixture.blob.size)-lo;return fixture.blob.slice(lo,hi);}};
  const started = performance.now(), audio = await E.openWav(file);
  assert.ok(readBytes < 128, `Read ${readBytes} bytes`); assert.equal(audio.frames,20000000);
  console.log(`40MB WAV metadata: ${(performance.now()-started).toFixed(2)}ms, ${readBytes} bytes read`);
});
test('truncated and compressed WAV are rejected with usable errors', async () => {
  const fixture = makeWav();
  await assert.rejects(E.openWav(fixture.blob.slice(0,100)),/途中/);
  const bytes = Buffer.from(await fixture.blob.arrayBuffer()); bytes.writeUInt16LE(6,20);
  await assert.rejects(E.openWav(new Blob([bytes])),/圧縮/);
});
test('ZIP supports UTF-8 names, correct CRC and all contents', async () => {
  const dir = path.join(__dirname,'../artifacts'); fs.mkdirSync(dir,{recursive:true});
  const entries = [{name:'音声/日本語.txt',blob:new Blob(['こんにちは'])},{name:'empty.txt',blob:new Blob([])},{name:'audio/test.wav',blob:makeWav({frames:4000}).blob}];
  const zip = await E.makeZip(entries);
  fs.writeFileSync(path.join(dir,'test.zip'),Buffer.from(await zip.arrayBuffer()));
  assert.equal(E.crc32(new TextEncoder().encode('123456789')) ^ 0xffffffff, 0xcbf43926 | 0);
});
test('ZIP cancellation and dangerous filenames fail', async () => {
  const controller = new AbortController(); controller.abort();
  await assert.rejects(E.makeZip([{name:'x',blob:new Blob(['x'])}],{signal:controller.signal}),/中止/);
  await assert.rejects(E.makeZip([{name:'../x',blob:new Blob(['x'])}]),/ファイル名/);
});
test('decoded MP3 fallback writes correct interleaved PCM16', async () => {
  const audio = {sampleRate:1000,channels:2,frames:4,duration:.004,buffer:{getChannelData:i=>i===0?new Float32Array([-1,-.5,0,1]):new Float32Array([1,0,.5,-1])}};
  const wav = E.sliceDecodedAudio(audio,0,4,0), parsed = await E.openWav(wav);
  const bytes = Buffer.from(await wav.slice(parsed.data[0].offset).arrayBuffer());
  assert.deepEqual([...new Int16Array(bytes.buffer,bytes.byteOffset,8)],[-32768,32767,-16384,0,0,16384,32767,-32768]);
});
