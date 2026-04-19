"""
Textkompression und Duplikatbereinigung für LLM-Eingaben.

Öffentliche API:
    deduplicate_paragraphs(text) → str
    compress(text)               → str
"""
from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Duplikatbereinigung
# ---------------------------------------------------------------------------

def _normalize_paragraph(p: str) -> str:
    return re.sub(r"\s+", " ", p.lower()).strip()


def deduplicate_short_lines(text: str, max_words: int = 15) -> str:
    """
    Entfernt exakt doppelte Kurzabsätze (< max_words Wörter).

    Deduplicate_paragraphs überspringt kurze Absätze bewusst, um False
    Positives zu vermeiden.  Bei OCR-Text erscheinen jedoch Seitenköpfe
    (Gericht, Aktenzeichen, Seitennummer) auf jeder Seite als kurze
    Zeilen — diese werden hier auf das erste Vorkommen reduziert.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    seen_short: set[str] = set()
    result: list[str] = []
    for para in paragraphs:
        normalized = re.sub(r"\s+", " ", para.lower()).strip()
        if len(normalized.split()) < max_words:
            if normalized in seen_short:
                continue
            seen_short.add(normalized)
        result.append(para)
    return "\n\n".join(result)


def deduplicate_paragraphs(text: str, similarity_threshold: float = 0.85) -> str:
    """
    Entfernt nahezu identische Absätze (Jaccard-Ähnlichkeit >= threshold).

    Gerichte wiederholen in Berufungsurteilen häufig den Tatbestand der
    Vorinstanz. Schwellenwert 0.85 vermeidet False Positives bei inhaltlich
    ähnlichen, aber rechtlich unterschiedlichen Absätzen.
    Sehr kurze Absätze (< 15 Wörter) werden immer behalten.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    seen: list[set] = []
    result: list[str] = []

    for para in paragraphs:
        normalized = _normalize_paragraph(para)
        if len(normalized.split()) < 15:
            result.append(para)
            continue

        words = set(normalized.split())
        duplicate = False
        for prev_words in seen:
            intersection = len(words & prev_words)
            union = len(words | prev_words)
            if union > 0 and intersection / union >= similarity_threshold:
                duplicate = True
                break

        if not duplicate:
            result.append(para)
            seen.append(words)

    return "\n\n".join(result)


# ---------------------------------------------------------------------------
# Kompression — Regex-Muster
# ---------------------------------------------------------------------------

# 2. ECLI-Kennzeichen und Aktenzeichen (ehemals 3.)
_ECLI_RE = re.compile(
    r"ECLI\s*:\s*\S+|"
    r"\b\d{1,2}\s+[A-Z]{2,5}\s+\d{1,3}/\d{2,4}\b",
)

# 4. Finanz- und Steuernummern
_IBAN_RE = re.compile(
    r"\bDE\d{2}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{2}\b"
    r"|[A-Z]{2}\d{2}(?:[\s\-]?[A-Z0-9]{4}){3,7}",
    re.IGNORECASE,
)
_BIC_RE = re.compile(r"\b[A-Z]{4}DE[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b")
_TAXID_RE = re.compile(
    r"\b(?:Steuer(?:nummer|nr\.?|identifikationsnummer|ID)\s*:?\s*)[\d/\s\-]{8,20}"
    r"|\bUSt\.?-?Id\.?-?Nr\.?\s*:?\s*DE\s*\d{9}\b"
    r"|\bDE\s*\d{9}\b",
    re.IGNORECASE,
)
_HREG_RE = re.compile(r"\b(?:HRB|HRA|PR|VR|GnR)\s*\d+\b", re.IGNORECASE)

# 5. Kontaktdaten — nur alleinstehende Zeilen (Briefkopf), kein Fließtext
_PHONE_RE = re.compile(
    r"(?im)^[ \t]*(?:Tel(?:efon)?\.?|Fax|Mobil|Funk)\s*:?\s*"
    r"[\+\(]?[\d\s\(\)\-\/]{7,20}[ \t]*$",
)
# E-Mail nur in alleinstehenden Zeilen (Briefkopf/Fußzeile)
_EMAIL_RE = re.compile(
    r"(?im)^[ \t]*(?:E-?Mail|Mail)\s*:?\s*[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}[ \t]*$"
)
# URLs nur in Kopf-/Fußzeilen (alleinstehende Zeile oder nach Label) — Fließtext bleibt
_URL_HEADER_RE = re.compile(
    r"(?im)^[\s\-]*(?:www\.|http)[^\s]{4,60}\s*$"
    r"|(?:Web(?:site)?|Internet|Homepage|URL)\s*:?\s*(?:https?://|www\.)\S+",
)

# 6. Briefkopf / Adressblöcke
_ADDRESS_LINE_RE = re.compile(
    r"(?im)^[\w\s\-\.]{3,40}\s+\d{1,4}[a-z]?\s*,\s*\d{5}\s+[\w\s\-]{3,40}$"
)
_POSTBOX_RE = re.compile(r"(?i)\bPostfach\s+\d{3,6}\b(?:\s*,\s*\d{5}\s+\w+)?")

# 7. Anrede- und Grußformeln
_GREETING_RE = re.compile(
    r"(?im)^Sehr geehrte[rs]?\s+(?:Damen und Herren|Herr|Frau|Dr\.|Prof\.)[^\n]{0,60}[,!]?\s*$"
    r"|^(?:Liebe[rs]?)\s+(?:Herr|Frau|Dr\.|Prof\.)[^\n]{0,50}[,!]?\s*$",
)
_CLOSING_RE = re.compile(
    r"(?im)^(?:Mit\s+(?:freundlichen?|kollegialen?|vorzüglicher)\s+Grü(?:ß|ss)en?"
    r"|Hochachtungsvoll|Mit\s+freundlichem\s+Gruß"
    r"|Mit\s+besten?\s+Grü(?:ß|ss)en?"
    r"|Freundliche\s+Grü(?:ß|ss)e"
    r"|i\.A\.|i\.V\.|ppa?\.|gez\."
    r"|Für\s+Rückfragen\s+stehe\s+ich\b[^\n]{0,80}"
    r"|Bitte\s+(?:wenden\s+Sie\s+sich|zögern\s+Sie\s+nicht)[^\n]{0,80}"
    r")\s*[,.]?\s*$",
    re.MULTILINE,
)

# Label-Reste nach Kennzeichenentfernung (z.B. "Bankverbindung: , ")
_LABEL_RESIDUE_RE = re.compile(
    r"(?im)^(?:Bankverbindung|Kontonummer|Konto|BIC|IBAN"
    r"|Telefon|Tel\.?|Fax|Mobil|E-Mail|Mail"
    r"|Steuer(?:nummer|nr\.?|ID)|USt\.?-?Id(?:Nr\.?)?"
    r"|Handelsregister|HRB|HRA"
    r"|Postfach"
    r")\s*:?\s*[,;:\s]*$"
    r"|(?:Bankverbindung|IBAN|BIC|Konto(?:nr\.?|nummer)?)\s*:?\s*,\s*(?:BIC|IBAN)?\s*[,;\s]*"
)

# 9. Referenz-/Metazeilen im Briefkopf
_REF_LINE_RE = re.compile(
    r"(?im)^(?:Ihr(?:e)?\s+(?:Zeichen|Schreiben\s+vom|Nachricht\s+vom)"
    r"|Unser(?:e)?\s+Zeichen"
    r"|Betreff\s*:|Az\.?\s*:|Aktenzeichen\s*:"
    r"|Datum\s*:|Ort\s*,\s*Datum"
    r"|Seite\s+\d+\s+von\s+\d+"
    r")\s*:?[^\n]{0,80}$",
)

# 10. Fußnotenreferenzen im Fließtext
_FOOTNOTE_REF_RE = re.compile(r"[¹²³⁴⁵⁶⁷⁸⁹⁰]+|\[\d{1,3}\](?!\s*\w{10})")


def compress(text: str) -> str:
    """
    Wendet alle lexikalischen Kompressionsschritte an (ohne Duplikatbereinigung).
    Reihenfolge: Zeilenweise Entfernung → Inline-Kennzeichen.
    """
    t = text

    # --- Zeilenweise Entfernung ---
    t = _GREETING_RE.sub("", t)
    t = _CLOSING_RE.sub("", t)
    t = _REF_LINE_RE.sub("", t)
    t = _ADDRESS_LINE_RE.sub("", t)
    t = _POSTBOX_RE.sub("", t)
    t = _URL_HEADER_RE.sub("", t)

    # --- Inline-Kennzeichen ---
    t = _ECLI_RE.sub("", t)
    t = _IBAN_RE.sub("", t)
    t = _BIC_RE.sub("", t)
    t = _TAXID_RE.sub("", t)
    t = _HREG_RE.sub("", t)
    t = _PHONE_RE.sub("", t)
    t = _EMAIL_RE.sub("", t)
    t = _FOOTNOTE_REF_RE.sub("", t)

    # --- Leerraum bereinigen ---
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = _LABEL_RESIDUE_RE.sub("", t)
    t = re.sub(
        r"(?im)\b(?:Bankverbindung|Kontonummer|IBAN|BIC|Konto(?:nr\.?|nummer)?"
        r"|Tel\.?|Fax|Mobil|E-Mail)\s*:?\s*$",
        "", t,
    )
    t = re.sub(r"(?m)^[ \t]*\n", "", t)
    return t.strip()
