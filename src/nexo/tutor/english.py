"""Asistente de inglés A2.4/B1 con correcciones educativas locales."""

from __future__ import annotations

import re
from typing import Any

from nexo.core.models import DataClass
from nexo.tools.base import BaseTool

_REPLACEMENTS = (
    (re.compile(r"\bI am agree\b", re.IGNORECASE), "I agree"),
    (re.compile(r"\bI have (\d+) years\b", re.IGNORECASE), r"I am \1 years old"),
    (re.compile(r"\b(he|she|it) don't\b", re.IGNORECASE), r"\1 doesn't"),
    (re.compile(r"\b(he|she|it) have\b", re.IGNORECASE), r"\1 has"),
    (re.compile(r"\b(he|she|it) go\b", re.IGNORECASE), r"\1 goes"),
    (re.compile(r"\bmore better\b", re.IGNORECASE), "better"),
)


def _correct(text: str) -> tuple[str, list[str]]:
    corrected = text
    notes: list[str] = []
    for pattern, replacement in _REPLACEMENTS:
        updated, count = pattern.subn(replacement, corrected)
        if count:
            corrected = updated
            notes.append(f"Revisa esta estructura: {pattern.pattern}")
    return corrected, notes


class EnglishCorrectTextTool(BaseTool):
    name = "english.correct_text"
    data_class = DataClass.LOCAL

    def run(self, params: dict[str, Any]) -> str:
        text = str(params.get("text", "")).strip()
        if not text:
            raise ValueError("text no puede estar vacío")
        corrected, notes = _correct(text)
        feedback = "\n".join(f"- {note}" for note in notes) or (
            "No detecté errores en las estructuras básicas revisadas."
        )
        return f"Original: {text}\nPropuesta: {corrected}\nNivel: A2.4/B1\nNotas:\n{feedback}"


class EnglishExplainGrammarTool(BaseTool):
    name = "english.explain_grammar"
    data_class = DataClass.LOCAL

    def run(self, params: dict[str, Any]) -> str:
        topic = str(params.get("topic", "")).strip().lower()
        explanations = {
            "present simple": (
                "Usa el presente simple para rutinas y hechos. Con he/she/it, agrega -s "
                "al verbo: 'She works'. En preguntas usa does y el verbo base: 'Does she work?'"
            ),
            "past simple": (
                "Usa el pasado simple para acciones terminadas. Los verbos regulares suelen "
                "terminar en -ed; los irregulares tienen formas propias: go -> went."
            ),
            "present perfect": (
                "Forma: have/has + participio. Conecta una experiencia o resultado pasado "
                "con el presente: 'I have finished my homework'."
            ),
            "articles": (
                "Usa a/an para mencionar algo singular no específico, the para algo "
                "identificado y omite el artículo al hablar en general de plurales."
            ),
        }
        if topic not in explanations:
            return (
                f"No tengo una explicación preparada para '{topic}'. Temas disponibles: "
                f"{', '.join(sorted(explanations))}. Comparte una frase para revisarla."
            )
        return f"{topic.title()} (A2.4/B1): {explanations[topic]}"