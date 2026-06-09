#!/usr/bin/env python3
"""
Converte PDF di quiz MIUR/Biochimica clinica in JSON.
Formato supportato:
  1. Testo domanda
  A opzione
  B* opzione corretta
  C opzione
  ...

Uso:
  python converti_domande4_pdf_json.py Domande-4.pdf domande4.json

Dipendenze:
  pip install pymupdf
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    import fitz  # PyMuPDF
except ImportError:
    print("Errore: manca pymupdf. Installa con: pip install pymupdf", file=sys.stderr)
    raise

QUESTION_RE = re.compile(r"^\s*(\d+)\s*[\.)]\s*(.*)$")
OPTION_RE = re.compile(r"^\s*([A-E])(?:\*\s*|\s+|$)(.*)$")
OPTION_STAR_AFTER_RE = re.compile(r"^\s*([A-E])\*\s*(.*)$")

HEADER_PATTERNS = [
    re.compile(r"^\s*Ministero\s+dell", re.I),
    re.compile(r"^\s*Anno\s+Accademico", re.I),
    re.compile(r"^\s*Scuola\s+di\s+Specializzazione", re.I),
    re.compile(r"^\s*Biochimica\s+clinica\s+Pag\.", re.I),
    re.compile(r"^\s*Pag\.\s*\d+\s*/\s*\d+\s*$", re.I),
    re.compile(r"^\s*Biochimica\s+clinica\s*$", re.I),
    re.compile(r"^\s*[,]+\s*$"),
]


def clean_text(s: str) -> str:
    """Normalizza spazi e piccoli artefatti di estrazione PDF."""
    s = s.replace("\u00a0", " ")
    s = s.replace("￾", "-")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+([,;:?.])", r"\1", s)
    return s.strip()


def is_header_or_footer(line: str) -> bool:
    line = line.strip()
    if not line:
        return True
    return any(p.search(line) for p in HEADER_PATTERNS)


def extract_lines(pdf_path: Path) -> List[tuple[int, str]]:
    doc = fitz.open(pdf_path)
    rows: List[tuple[int, str]] = []
    for page_index, page in enumerate(doc, start=1):
        text = page.get_text("text")
        for raw in text.splitlines():
            line = raw.strip()
            if is_header_or_footer(line):
                continue
            rows.append((page_index, line))
    return rows


def finalize_question(q: Optional[Dict[str, Any]], keep_incomplete: bool = False) -> Optional[Dict[str, Any]]:
    if not q:
        return None

    q["domanda"] = clean_text(" ".join(q.get("_question_lines", [])))

    opzioni: Dict[str, str] = {}
    for letter in ["A", "B", "C", "D", "E"]:
        txt = clean_text(" ".join(q.get("_option_lines", {}).get(letter, [])))
        if txt:
            opzioni[letter] = txt

    q["opzioni"] = opzioni
    correct = q.get("risposta_corretta")
    q["risposta"] = opzioni.get(correct, "") if correct else ""

    for k in ["_question_lines", "_option_lines", "_current_option"]:
        q.pop(k, None)

    complete = bool(q["domanda"]) and len(opzioni) >= 2 and bool(correct)
    if complete or keep_incomplete:
        return q
    return None


def parse_quiz(rows: List[tuple[int, str]], keep_incomplete: bool = False) -> List[Dict[str, Any]]:
    questions: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for page, line in rows:
        line = line.strip()
        if not line:
            continue

        qm = QUESTION_RE.match(line)
        if qm:
            finished = finalize_question(current, keep_incomplete=keep_incomplete)
            if finished:
                questions.append(finished)

            num = int(qm.group(1))
            rest = qm.group(2).strip()
            current = {
                "numero": num,
                "domanda": "",
                "opzioni": {},
                "risposta_corretta": None,
                "risposta": "",
                "pagina": page,
                "id": num,
                "_question_lines": [rest] if rest else [],
                "_option_lines": {},
                "_current_option": None,
            }
            continue

        if current is None:
            continue

        om = OPTION_STAR_AFTER_RE.match(line) or OPTION_RE.match(line)
        if om:
            letter = om.group(1).upper()
            text = om.group(2).strip()
            starred = bool(OPTION_STAR_AFTER_RE.match(line)) or ("*" in line[:4])

            current["_option_lines"].setdefault(letter, [])
            if text:
                current["_option_lines"][letter].append(text)
            current["_current_option"] = letter
            if starred:
                current["risposta_corretta"] = letter
            continue

        # Continuazione: se sono già iniziate le opzioni, aggiungi all'ultima opzione.
        # Altrimenti aggiungi al testo della domanda.
        if current.get("_current_option"):
            current["_option_lines"].setdefault(current["_current_option"], []).append(line)
        else:
            current["_question_lines"].append(line)

    finished = finalize_question(current, keep_incomplete=keep_incomplete)
    if finished:
        questions.append(finished)

    return questions


def main() -> None:
    parser = argparse.ArgumentParser(description="Estrae domande da PDF e le salva in JSON.")
    parser.add_argument("pdf", type=Path, help="File PDF di input")
    parser.add_argument("output", type=Path, help="File JSON di output")
    parser.add_argument("--keep-incomplete", action="store_true", help="Mantiene anche domande incomplete")
    parser.add_argument("--pretty", action="store_true", help="JSON indentato, default attivo")
    args = parser.parse_args()

    if not args.pdf.exists():
        raise SystemExit(f"PDF non trovato: {args.pdf}")

    rows = extract_lines(args.pdf)
    questions = parse_quiz(rows, keep_incomplete=args.keep_incomplete)

    with args.output.open("w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

    complete = sum(1 for q in questions if q.get("risposta_corretta") and q.get("risposta"))
    print(f"Estratte {len(questions)} domande in: {args.output}")
    print(f"Complete con risposta riconosciuta: {complete}")


if __name__ == "__main__":
    main()
