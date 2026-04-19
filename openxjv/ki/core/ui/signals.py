"""Qt-Signal-Bridge für Worker-Thread → UI-Thread-Kommunikation."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class Signals(QObject):
    progress         = Signal(str)       # Fortschrittsmeldung → Log
    token            = Signal(str)       # einzelnes Token → Ausgabefenster
    error            = Signal(str)       # Fehlermeldung
    started          = Signal()          # Worker gestartet
    finished         = Signal()          # Worker beendet
    download_progress = Signal(int, int) # (bytes_done, bytes_total)
