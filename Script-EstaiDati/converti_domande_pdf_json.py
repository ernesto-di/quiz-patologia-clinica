#!/usr/bin/env python3
"""
Estrae domande, opzioni e risposta corretta da un PDF di quiz a due colonne.

Uso:
    python extract_quiz_json_fixed.py Pat_Clin_BC_Esercitazioni_Quiz.pdf domande.json

Dipendenza principale:
    pip install pymupdf

Opzionale, usata solo come fallback se PyMuPDF non estrae testo da una pagina:
    pip install pdfplumber
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
from pathlib import Path
from typing import Any

QUESTION_RE = re.compile(r"^(\d{1,5})\s+(.+)$")
OPTION_RE = re.compile(r"^(X\s+)?([A-E])\s+(.+)$")
HEADER_RE = re.compile(r"^(BIOCHIMICA CLINICA|PAG\.?\s*\d*|\d+)$", re.IGNORECASE)


def normalize(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_noise(line: str) -> bool:
    line = normalize(line)
    if not line:
        return True
    if HEADER_RE.match(line):
        return True
    return "BIOCHIMICA CLINICA" in line.upper()


def group_words(words: list[tuple[float, float, str]], y_tolerance: float = 3.0) -> list[str]:
    """words: lista di (x0, y0/top, testo)."""
    words.sort(key=lambda w: (round(w[1], 1), w[0]))
    rows: list[list[tuple[float, float, str]]] = []

    for word in words:
        if not rows:
            rows.append([word])
            continue
        avg_y = sum(w[1] for w in rows[-1]) / len(rows[-1])
        if abs(word[1] - avg_y) <= y_tolerance:
            rows[-1].append(word)
        else:
            rows.append([word])

    lines: list[str] = []
    for row in rows:
        row.sort(key=lambda w: w[0])
        line = normalize(" ".join(w[2] for w in row))
        if not is_noise(line):
            lines.append(line)
    return lines


def lines_from_fitz(pdf_path: Path) -> list[tuple[int, str, list[str]]]:
    import fitz

    blocks: list[tuple[int, str, list[str]]] = []

    # PyMuPDF può stampare warning tipo "zlib error" su alcuni PDF.
    # Non sono necessariamente bloccanti, quindi li silenziamo e controlliamo le righe estratte.
    stderr_buffer = io.StringIO()
    with contextlib.redirect_stderr(stderr_buffer):
        doc = fitz.open(str(pdf_path))
        for page_number, page in enumerate(doc, start=1):
            page_width = page.rect.width
            split_x = page_width * 0.47
            raw_words = page.get_text("words") or []

            left: list[tuple[float, float, str]] = []
            right: list[tuple[float, float, str]] = []
            for w in raw_words:
                x0, y0, _x1, _y1, text = float(w[0]), float(w[1]), float(w[2]), float(w[3]), str(w[4])
                target = left if x0 < split_x else right
                target.append((x0, y0, text))

            blocks.append((page_number, "left", group_words(left)))
            blocks.append((page_number, "right", group_words(right)))
        doc.close()

    return blocks


def lines_from_pdfplumber(pdf_path: Path) -> list[tuple[int, str, list[str]]]:
    import pdfplumber

    blocks: list[tuple[int, str, list[str]]] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            split_x = page.width * 0.47
            raw_words = page.extract_words(x_tolerance=1, y_tolerance=3, keep_blank_chars=False, use_text_flow=False) or []
            left = [(float(w["x0"]), float(w["top"]), str(w["text"])) for w in raw_words if float(w["x0"]) < split_x]
            right = [(float(w["x0"]), float(w["top"]), str(w["text"])) for w in raw_words if float(w["x0"]) >= split_x]
            blocks.append((page_number, "left", group_words(left)))
            blocks.append((page_number, "right", group_words(right)))
    return blocks


def parse_column(lines: list[str], page_number: int, column: str) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_option: str | None = None

    def close_current() -> None:
        nonlocal current, current_option
        if current is not None:
            for letter, answer in list(current["opzioni"].items()):
                current["opzioni"][letter] = normalize(re.sub(r"\s+X$", "", answer))
            letter = current.get("risposta_corretta")
            current["risposta"] = current["opzioni"].get(letter) if letter else None
            questions.append(current)
        current = None
        current_option = None

    for line in lines:
        line = normalize(line)
        q_match = QUESTION_RE.match(line)
        opt_match = OPTION_RE.match(line)

        if q_match and not opt_match:
            close_current()
            current = {
                "numero": int(q_match.group(1)),
                "domanda": normalize(q_match.group(2)),
                "opzioni": {},
                "risposta_corretta": None,
                "risposta": None,
                "pagina": page_number,
                "colonna": column,
            }
            current_option = None
            continue

        if opt_match and current is not None:
            is_correct = bool(opt_match.group(1))
            letter = opt_match.group(2)
            text = normalize(opt_match.group(3))
            current["opzioni"][letter] = text
            if is_correct:
                current["risposta_corretta"] = letter
            current_option = letter
            continue

        if current is not None:
            if current_option is None:
                current["domanda"] = normalize(current["domanda"] + " " + line)
            else:
                current["opzioni"][current_option] = normalize(current["opzioni"].get(current_option, "") + " " + line)

    close_current()
    return questions


def extract_questions(pdf_path: Path, keep_incomplete: bool = False, engine: str = "auto") -> list[dict[str, Any]]:
    if engine == "fitz":
        blocks = lines_from_fitz(pdf_path)
    elif engine == "pdfplumber":
        blocks = lines_from_pdfplumber(pdf_path)
    else:
        blocks = lines_from_fitz(pdf_path)
        # fallback se non viene estratta quasi nessuna riga utile
        useful_lines = sum(len(lines) for _p, _c, lines in blocks)
        if useful_lines < 20:
            blocks = lines_from_pdfplumber(pdf_path)

    extracted: list[dict[str, Any]] = []
    for page_number, column, lines in blocks:
        extracted.extend(parse_column(lines, page_number, column))

    extracted.sort(key=lambda q: (q["pagina"], 0 if q["colonna"] == "left" else 1, q["numero"]))

    if not keep_incomplete:
        extracted = [
            q for q in extracted
            if q.get("risposta_corretta") in q.get("opzioni", {}) and len(q.get("opzioni", {})) >= 5
        ]

    for idx, q in enumerate(extracted, start=1):
        q["id"] = idx
        letter = q.get("risposta_corretta")
        q["risposta"] = q["opzioni"].get(letter) if letter else None

    return extracted


def main() -> None:
    parser = argparse.ArgumentParser(description="Estrae domande, opzioni e risposte da un PDF in JSON.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("json", type=Path)
    parser.add_argument("--keep-incomplete", action="store_true")
    parser.add_argument("--engine", choices=["auto", "fitz", "pdfplumber"], default="auto")
    args = parser.parse_args()

    questions = extract_questions(args.pdf, keep_incomplete=args.keep_incomplete, engine=args.engine)
    args.json.write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")

    complete = sum(1 for q in questions if q.get("risposta_corretta") in q.get("opzioni", {}))
    print(f"Estratte {len(questions)} domande in: {args.json}")
    print(f"Complete con risposta riconosciuta: {complete}")

    if not questions:
        print("Nessuna domanda trovata. Prova: --engine pdfplumber --keep-incomplete")


if __name__ == "__main__":
    main()
