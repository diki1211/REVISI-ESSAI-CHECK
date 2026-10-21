"""Deterministic Indonesian sentence splitting with stable ids <answer_id>_s<n>."""
import re
import unicodedata

# Abbreviations whose final dot never ends a sentence.
ABBREVIATIONS = {"dll.", "dsb.", "dst.", "dkk.", "mis.", "misal.", "spt.", "tsb.", "yg.", "dg.", "dgn.",
                 "no.", "hlm.", "dr.", "prof.", "ir.", "drs.", "sdr.", "bpk.", "kg.", "cm.", "km."}
BOUNDARY = re.compile(r"[.?!]+(?=\s|$)")


def split(answer_id, text):
    """[(sentence_id, sentence_text)]; a decimal like 0.5 or 1,5 never splits (no space after the dot)."""
    text = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text or "")).strip()
    sentences, start = [], 0
    for m in BOUNDARY.finditer(text):
        last_word = text[start:m.end()].rsplit(" ", 1)[-1].lower()
        if m.group() == "." and last_word in ABBREVIATIONS:
            continue
        sentences.append(text[start:m.end()].strip())
        start = m.end()
    if text[start:].strip():
        sentences.append(text[start:].strip())
    return [(f"{answer_id}_s{i}", s) for i, s in enumerate(sentences, 1)]
