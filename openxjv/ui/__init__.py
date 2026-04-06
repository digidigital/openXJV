"""User interface components for openXJV.

Migration Status:
    ✅ CustomWebEnginePage - Imported from openxjv.ui (duplicate removed from openXJV.py)
    ✅ StandardItem - Imported from openxjv.ui (duplicate removed from openXJV.py)
    ✅ TextObject - Imported from openxjv.ui (duplicate removed from openXJV.py)
    ✅ SearchWorker - Imported from openxjv.ui (duplicate removed from openXJV.py)
    ✅ XJustizDisplayRenderer - Integrated in Phase 6 (template delegation complete)
"""
from .openXJV_UI import Ui_MainWindow 
from .helpers import (
    CustomWebEnginePage,
    StandardItem,
    TextObject,
    SearchWorker,
)
from .xjustiz_display import XJustizDisplayRenderer

__all__ = [
    'CustomWebEnginePage',
    'StandardItem',
    'TextObject',
    'SearchWorker',
    'XJustizDisplayRenderer',
]
