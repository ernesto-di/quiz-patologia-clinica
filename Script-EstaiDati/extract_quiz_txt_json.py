#!/usr/bin/env python3
"""
Estrae domande a risposta multipla da un file TXT nel formato:

1.
2.
Domanda...
a. risposta
b. * risposta corretta
...

Supporta anche numeri e testo sulla stessa riga, es.:
100. Dove si trova...

Output JSON:
[
  {
    "numero": 1,
    "domanda": "...",
    "opzioni": {"a": "...", "b": "...", ...},
    "risposta_corretta": "b",
    "risposta": "..."
  }
]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

NUM_ONLY_RE = re.compile(r"^\s*(\d+)\s*[\.)]\s*$")
NUM_WITH_TEXT_RE = re.compile(r"^\s*(\d+)\s*[\.)]\s+(.+)$")
OPT_RE = re.compile(r"^\s*([a-eA-E])\s*[\.)]\s*(.*)$")


def normalize_spaces(text: str) -> str:
    """Normalizza spazi multipli e alcuni caratteri tipografici frequenti."""
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return text.strip()


def read_text(path: Path) -> str:
    """Legge il file provando UTF-8 e poi Latin-1."""
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def clean_option_text(raw: str) -> Tuple[str, bool]:
    """Rimuove l'asterisco dalla risposta corretta e restituisce (testo, is_correct)."""
    raw = raw.strip()
    is_correct = False

    # Caso comune: "* risposta"
    if raw.startswith("*"):
        is_correct = True
        raw = raw[1:].strip()

    # Caso meno comune: "risposta *" o asterisco interno isolato
    if re.search(r"(^|\s)\*(\s|$)", raw):
        is_correct = True
        raw = re.sub(r"(^|\s)\*(\s|$)", " ", raw).strip()

    return normalize_spaces(raw), is_correct


def new_question(number: Optional[int], first_line: str) -> Dict:
    return {
        "numero": number,
        "domanda_parts": [normalize_spaces(first_line)] if first_line.strip() else [],
        "opzioni": {},
        "risposta_corretta": None,
        "_current_option": None,
    }


def finalize(q: Optional[Dict], keep_incomplete: bool = False) -> Optional[Dict]:
    if not q:
        return None

    domanda = normalize_spaces(" ".join(q.get("domanda_parts", [])))
    opzioni = {k: normalize_spaces(v) for k, v in q.get("opzioni", {}).items() if normalize_spaces(v)}
    correct = q.get("risposta_corretta")

    if not domanda:
        return None
    if not keep_incomplete and (len(opzioni) < 2 or correct is None):
        return None

    out = {
        "numero": q.get("numero"),
        "domanda": domanda,
        "opzioni": opzioni,
        "risposta_corretta": correct,
        "risposta": opzioni.get(correct) if correct else None,
    }
    return out


def parse_quiz_text(text: str, keep_incomplete: bool = False) -> List[Dict]:
    lines = [line.strip() for line in text.splitlines()]

    questions: List[Dict] = []
    pending_numbers: List[int] = []
    q: Optional[Dict] = None

    def save_current() -> None:
        nonlocal q
        item = finalize(q, keep_incomplete=keep_incomplete)
        if item:
            questions.append(item)
        q = None

    for raw_line in lines:
        line = normalize_spaces(raw_line)
        if not line:
            continue

        # Ignora intestazioni ricorrenti o righe chiaramente non-domanda.
        if line.lower().startswith("scuola di specializzazione"):
            continue

        # Numero isolato: viene accodato e associato alla prossima domanda.
        m_num_only = NUM_ONLY_RE.match(line)
        if m_num_only:
            pending_numbers.append(int(m_num_only.group(1)))
            continue

        # Numero + testo sulla stessa riga: chiude l'eventuale domanda precedente e apre questa.
        m_num_text = NUM_WITH_TEXT_RE.match(line)
        if m_num_text:
            save_current()
            q = new_question(int(m_num_text.group(1)), m_num_text.group(2))
            continue

        # Opzione a/b/c/d/e.
        m_opt = OPT_RE.match(line)
        if m_opt and q is not None:
            opt_key = m_opt.group(1).lower()
            opt_text, is_correct = clean_option_text(m_opt.group(2))
            q["opzioni"][opt_key] = opt_text
            q["_current_option"] = opt_key
            if is_correct:
                q["risposta_corretta"] = opt_key
            continue

        # Nuova domanda senza numero sulla stessa riga, usando la coda di numeri già letti.
        if q is None:
            number = pending_numbers.pop(0) if pending_numbers else None
            q = new_question(number, line)
            continue

        # Se abbiamo già le 5 opzioni e arriva testo non-opzione, probabilmente è la domanda successiva.
        if len(q.get("opzioni", {})) >= 5 and pending_numbers:
            save_current()
            number = pending_numbers.pop(0)
            q = new_question(number, line)
            continue

        # Continuazione di un'opzione o della domanda.
        current_option = q.get("_current_option")
        if current_option and q.get("opzioni"):
            # Se la riga contiene un asterisco in una continuazione, segna comunque l'opzione come corretta.
            cont_text, is_correct = clean_option_text(line)
            q["opzioni"][current_option] = normalize_spaces(q["opzioni"].get(current_option, "") + " " + cont_text)
            if is_correct:
                q["risposta_corretta"] = current_option
        else:
            q["domanda_parts"].append(line)

    save_current()

    # Aggiunge ID progressivo stabile.
    for i, item in enumerate(questions, 1):
        item["id"] = i

    return questions


def main() -> None:
    parser = argparse.ArgumentParser(description="Estrae quiz a risposta multipla da TXT e salva JSON.")
    parser.add_argument("input", help="File .txt di input")
    parser.add_argument("output", nargs="?", default="domande.json", help="File .json di output")
    parser.add_argument("--keep-incomplete", action="store_true", help="Mantiene anche domande senza risposta corretta/opzioni complete")
    parser.add_argument("--indent", type=int, default=2, help="Indentazione JSON, default 2")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    text = read_text(input_path)
    questions = parse_quiz_text(text, keep_incomplete=args.keep_incomplete)

    output_path.write_text(json.dumps(questions, ensure_ascii=False, indent=args.indent), encoding="utf-8")

    complete = sum(1 for q in questions if q.get("risposta_corretta") and q.get("risposta"))
    print(f"Estratte {len(questions)} domande in: {output_path}")
    print(f"Complete con risposta riconosciuta: {complete}")

    if questions[:1]:
        print("Prima domanda estratta:")
        print(json.dumps(questions[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
