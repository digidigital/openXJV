#!/usr/bin/env python3
"""
Search indexing utilities for full-text search.

Migrated from helperScripts/search_tool.py to openxjv.utils module.
Provides batch text extraction with cleaning and multiprocessing support.
"""
import os
import sys
import unicodedata
import orjson as json
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count, freeze_support
from .text_extraction import get_document_text

VERSION = '0.3'


def clean_text(text: str) -> str:
    """
    Bereinigt extrahierten Text für Volltextsuche.
    Entfernt Steuerzeichen, Umbrüche, Tabs, Trennzeichen und typische Artefakte.

    Args:
        text: Raw extracted text

    Returns:
        str: Cleaned text ready for indexing
    """
    # Unicode-Normalisierung (z.B. für zusammengesetzte Zeichen)
    text = unicodedata.normalize("NFKC", text)

    # Entferne Soft-Hyphen (Unicode \u00AD) und andere Trennzeichen
    text = text.replace("\u00AD", "")  # Soft hyphen
    text = text.replace("-", "")       # Worttrennung

    # Entferne alle unsichtbaren Unicode-Steuerzeichen
    text = "".join(c for c in text if unicodedata.category(c)[0] != "C")

    return text.strip()

def parse_text(filename: str, filepath: str) -> tuple[str, str]:
    """
    Extrahiert und bereinigt Text aus einer Datei.

    Args:
        filename: Name of the file
        filepath: Full path to the file

    Returns:
        tuple: (filename, cleaned_text)
    """
    try:
        raw_text = get_document_text(filepath, lower_case=True)
        return filename, clean_text(raw_text)
    except Exception:
        return filename, ''

def extract_texts_from_directory(search_path: str) -> dict[str, str]:
    """
    Verarbeitet alle Dateien im Verzeichnis und extrahiert bereinigten Text.

    Args:
        search_path: Path to directory containing files to index

    Returns:
        dict: Mapping of filename to extracted text
    """
    if not os.path.isdir(search_path):
        return {}

    jobs = [
        (filename, os.path.join(search_path, filename))
        for filename in os.listdir(search_path)
        if os.path.isfile(os.path.join(search_path, filename))
    ]

    # ProcessPoolExecutor, da nicht alle von get_document_text
    # genutzten Module threadsafe sind!
    try:
        with ProcessPoolExecutor(max_workers=cpu_count()) as executor:
            futures = {executor.submit(parse_text, fn, fp): fn for fn, fp in jobs}
            result = {}
            for future in as_completed(futures):
                try:
                    filename, text = future.result()
                    result[filename] = text
                except Exception:
                    pass
        return result
    except Exception:
        return {}

if __name__ == "__main__":
    freeze_support()
    if len(sys.argv) > 1:
        search_path = sys.argv[1]
        result = extract_texts_from_directory(search_path)
        if result:
            sys.stdout.buffer.write(json.dumps(result))
        else:
            sys.exit(1)
    else:
        print(f'Version {VERSION}', end='')
        sys.exit(1)
