"""Utility modules for openXJV.

Migration Status:
    ✅ SearchFilterManager - ACTIVELY USED in openXJV_modular.py (Phase 2 complete)
    ✅ FileManager - ACTIVELY USED in openXJV_modular.py (Phase 4 complete)
    ✅ TextExtraction - Migrated from helperScripts/Search.py
    ✅ SearchIndexing - Migrated from helperScripts/search_tool.py
    ⏳ SettingsManager - Available but not yet integrated (future phase)
"""

from .file_management import FileManager
from .search_filter import SearchFilterManager
from .settings import SettingsManager
from .text_extraction import (
    phrase_search,
    get_document_text,
    PDF,
    DOCX,
    TXT,
    XML,
    XLSX,
    ODT,
    ODS,
    Baseclass
)
from .search_indexing import (
    clean_text,
    parse_text,
    extract_texts_from_directory
)

__all__ = [
    'FileManager',
    'SearchFilterManager',
    'SettingsManager',
    'phrase_search',
    'get_document_text',
    'PDF',
    'DOCX',
    'TXT',
    'XML',
    'XLSX',
    'ODT',
    'ODS',
    'Baseclass',
    'clean_text',
    'parse_text',
    'extract_texts_from_directory',
]
