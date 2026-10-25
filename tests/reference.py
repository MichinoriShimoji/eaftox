"""Generate golden results using only the original converter class (no Gradio)."""
import ast
import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
tree = ast.parse((ROOT / "app.py").read_text())
converter_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "EAFConverter")
namespace = {"ET": ET, "os": os, "re": re, "Dict": Dict, "List": List, "Optional": Optional}
exec(compile(ast.Module(body=[converter_class], type_ignores=[]), "app.py", "exec"), namespace)
Converter = namespace["EAFConverter"]

records = []
def annotation(identifier, value, start=None, end=None, ref=None):
    return {"annotation_id": identifier, "value": value, "start_time": start, "end_time": end, **({"ref_id": ref} if ref else {})}
def tier(identifier, annotations, parent="", participant=""):
    records.append({"id": identifier, "annotations": annotations, "parent": parent, "participant": participant})

tier("text0@A", [annotation("a1", "ɕi=ga hon=o yom-da.", 200, 1900)], participant="A")
tier("text@A", [annotation("a2", "ɕi=ga hon=o yom-da.", ref="a1")], "text0@A")
morphs = ["ɕi", "ga", "hon", "o", "yom", "da", "."]
glosses = ["3SG", "NOM", "book", "ACC", "read", "PST", "EOS"]
tier("morph@A", [annotation(f"m{i}", value, ref="a2") for i, value in enumerate(morphs)], "text@A")
tier("gloss@A", [annotation(f"g{i}", value, ref=f"m{i}") for i, value in enumerate(glosses)], "morph@A")
tier("pos@A", [annotation(f"p{i}", value, ref=f"m{i}") for i, value in enumerate(["PRO", "PART", "N", "PART", "V", "SUF", "PUNCT"])], "morph@A")
tier("translation@A", [annotation("f1", "彼が本を読んだ。", ref="a1")], "text0@A")
tier("text@B", [annotation("b1", "ame=ga hur-u.", 2400, 3900)], participant="B")
tier("gloss@B", [annotation("bg1", "rain NOM fall NPST", ref="b1")], "text@B")
tier("translation@B", [annotation("bf1", "雨が降る。", ref="b1")], "text@B")

root = ET.Element("ANNOTATION_DOCUMENT")
ET.SubElement(root, "HEADER")
slots = ET.SubElement(root, "TIME_ORDER")
for time in [200, 1900, 2400, 3900]:
    ET.SubElement(slots, "TIME_SLOT", TIME_SLOT_ID=f"t{time}", TIME_VALUE=str(time))
for record in records:
    attrs = {"TIER_ID": record["id"]}
    if record["parent"]: attrs["PARENT_REF"] = record["parent"]
    if record["participant"]: attrs["PARTICIPANT"] = record["participant"]
    node = ET.SubElement(root, "TIER", **attrs)
    for ann in record["annotations"]:
        wrapper = ET.SubElement(node, "ANNOTATION")
        attrs = {"ANNOTATION_ID": ann["annotation_id"]}
        if ann.get("ref_id"):
            attrs["ANNOTATION_REF"] = ann["ref_id"]
            value_node = ET.SubElement(wrapper, "REF_ANNOTATION", **attrs)
        else:
            attrs.update(TIME_SLOT_REF1=f't{ann["start_time"]}', TIME_SLOT_REF2=f't{ann["end_time"]}')
            value_node = ET.SubElement(wrapper, "ALIGNABLE_ANNOTATION", **attrs)
        ET.SubElement(value_node, "ANNOTATION_VALUE").text = ann["value"]
fixture = ROOT / "tests/sample.eaf"
fixture.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
speakers = [
    {"name": "A", "mode": "4層", "tiers": {"text0": "text0@A", "text": "text@A", "morph": "morph@A", "gloss": "gloss@A", "pos": "pos@A", "trans": "translation@A"}},
    {"name": "B", "mode": "シンプル3層", "tiers": {"text": "text@B", "gloss": "gloss@B", "trans": "translation@B"}},
]
converter = Converter(str(fixture))
assert converter.parse_eaf()
cases = []
for config in [speakers, [speakers[1]], [{**speakers[0], "mode": "3層", "tiers": {key: value for key, value in speakers[0]["tiers"].items() if key != "text0"}}]]:
    sentences = []
    for speaker in config:
        sentences.extend(converter.extract_sentences_for_speaker(speaker["mode"], speaker["tiers"], speaker["name"]))
    sentences.sort(key=lambda item: item["start_time"])
    cases.append({"speakers": config, "sentences": sentences, "text": converter.to_doc_format(sentences), "gb4e": {style: converter.to_gb4e_format(sentences, style) for style in ["標準版", "行間調整版", "最小限版"]}})
result = {"records": records, "cases": cases}
(ROOT / "tests/reference.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
repository_samples = []
for path in sorted(ROOT.glob("sample*.eaf")):
    document = ET.parse(path).getroot()
    time_slots = {slot.get("TIME_SLOT_ID"): int(slot.get("TIME_VALUE")) for slot in document.findall("./TIME_ORDER/TIME_SLOT") if slot.get("TIME_VALUE") is not None}
    sample_records = []
    for node in document.findall("TIER"):
        sample_annotations = []
        for ann in node.findall("./ANNOTATION/*"):
            value = ann.find("ANNOTATION_VALUE")
            item = {"annotation_id": ann.get("ANNOTATION_ID"), "value": (value.text or "").strip() if value is not None else ""}
            if ann.get("ANNOTATION_REF"):
                item["ref_id"] = ann.get("ANNOTATION_REF")
            else:
                item.update(start_time=time_slots.get(ann.get("TIME_SLOT_REF1")), end_time=time_slots.get(ann.get("TIME_SLOT_REF2")))
            sample_annotations.append(item)
        sample_records.append({"id": node.get("TIER_ID"), "parent": node.get("PARENT_REF", ""), "participant": node.get("PARTICIPANT", ""), "type": node.get("LINGUISTIC_TYPE_REF", ""), "annotations": sample_annotations})
    repository_samples.append({"file": path.name, "records": sample_records})
(ROOT / "tests/repository-samples.json").write_text(json.dumps(repository_samples, ensure_ascii=False))
print("Generated original-Python parity fixtures (3 structures × 3 GB4E styles)")
