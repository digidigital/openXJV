#!/usr/bin/env python3
# coding: utf-8
"""
UI-Hilfsklassen für openXJV.

Dieses Modul enthält Hilfsklassen, die in der gesamten UI verwendet werden:
- CustomWebEnginePage: Behandelt externe Links in der Web-Engine
- StandardItem: Benutzerdefinierte Baumansicht-Elemente mit ID-Verfolgung
- TextObject: Helfer zum Erstellen von formatiertem HTML-Text
- SearchWorker: Hintergrund-Worker für Textextraktion
"""

import os
import sqlite3
from typing import Optional, Tuple, Dict, Any

from PySide6.QtCore import QObject, Signal, QUrl
from PySide6.QtGui import QStandardItem, QColor
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtGui import QDesktopServices

if os.name == 'nt':
    from subprocess import CREATE_NO_WINDOW

from openxjv.utils import extract_texts_from_directory


class CustomWebEnginePage(QWebEnginePage):
    """
    Benutzerdefinierte Web-Engine-Seite, die externe Links im Standard-Browser des Systems öffnet.

    Diese Klasse fängt Navigationsanfragen ab und leitet Nicht-Datei-URLs zum
    Standard-Browser des Systems weiter, anstatt sie in der eingebetteten Web-Ansicht zu laden.

    Signale:
        customPrintRequested: Wird ausgesendet, wenn die Seite Drucken anfordert
    """

    customPrintRequested = Signal()

    def __init__(self, parent: Optional[Any] = None) -> None:
        """
        Initialisiert die benutzerdefinierte Web-Engine-Seite.

        Args:
            parent: Eltern-Widget (optional)
        """
        super().__init__(parent)
        super().printRequested.connect(self.forward_print_requested)

    def acceptNavigationRequest(self, url: QUrl, nav_type: Any, is_main_frame: bool) -> bool:
        """
        Behandelt Navigationsanfragen und öffnet externe Links im Standard-Browser.

        Args:
            url: Die URL, zu der navigiert wird
            nav_type: Typ der Navigation (Link-Klick, Formular-Absenden usw.)
            is_main_frame: Ob dies der Haupt-Frame ist

        Returns:
            True, falls Navigation in der Web-Ansicht fortfahren soll, sonst False
        """
        # Erlaubt file://-URLs normal zu laden
        if url.scheme() == "file":
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)

        # Öffnet externe URLs im Standard-Browser
        QDesktopServices.openUrl(QUrl(url))
        return False

    def forward_print_requested(self) -> None:
        """
        Leitet Druck-Anfrage-Signal weiter.

        Workaround: Das externe printRequested-Signal geht "verloren", wenn
        QWebEnginePage überschrieben wird, daher leiten wir es als benutzerdefiniertes Signal weiter.
        """
        self.customPrintRequested.emit()


class StandardItem(QStandardItem):
    """
    Benutzerdefiniertes QStandardItem für Baumansicht-Elemente mit ID-Verfolgung.

    Diese Klasse erweitert QStandardItem um ein ID-Feld zur Verfolgung von
    Baumelementen in der Inhaltshierarchie (Dokumente, Dateigruppen usw.).

    Attribute:
        id: Eindeutiger Bezeichner für dieses Element
    """

    def __init__(
        self,
        txt: str = '',
        id: str = 'root',
        font_size: int = 15,
        set_bold: bool = False,
        color: QColor = QColor(0, 0, 0)
    ) -> None:
        """
        Initialisiert ein Standard-Element mit ID-Verfolgung.

        Args:
            txt: Anzeigetext für das Element
            id: Eindeutiger Bezeichner (Standard: 'root')
            font_size: Schriftgröße (derzeit ungenutzt)
            set_bold: Ob Text fett gemacht werden soll (derzeit ungenutzt)
            color: Textfarbe (derzeit ungenutzt)
        """
        super().__init__()
        self.id = id
        self.setEditable(False)
        self.setText(txt)


class TextObject:
    """
    Hilfsklasse zum Erstellen von formatiertem HTML-Text mit einheitlichen Trennzeichen.

    Diese Klasse vereinfacht die Erstellung von formatierten Textblöcken mit Schlüssel-Wert-Paaren,
    Überschriften und rohem HTML. Sie wird in der gesamten UI für Metadatenanzeige verwendet.

    Attribute:
        text: Der angesammelte Textinhalt
        delimiter: Trennzeichen zwischen Schlüssel und Wert (Standard: ': ')
        newline: HTML-Zeilenumbruch-Tag (Standard: '<br>')
        headline: Optionaler Überschriftentext
        ignore_empty_text: Ob Überschrift angezeigt werden soll, auch wenn Text leer ist
    """

    def __init__(self, delimiter: str = ': ', newline: str = '<br>') -> None:
        """
        Initialisiert ein Text-Objekt mit Formatierungsoptionen.

        Args:
            delimiter: Trennzeichen zwischen Schlüssel-Wert-Paaren
            newline: HTML-Tag für Zeilenumbrüche
        """
        self.text = ''
        self.delimiter = delimiter
        self.newline = newline
        self.headline = ''
        self.ignore_empty_text = False

    def add_line(
        self,
        value1: Optional[str] = None,
        value2: Optional[str] = None,
        prepend: bool = False
    ) -> None:
        """
        Fügt eine formatierte Schlüssel-Wert-Zeile hinzu, falls beide Werte nicht None sind.

        Args:
            value1: Der Schlüssel (linke Seite)
            value2: Der Wert (rechte Seite)
            prepend: Ob vorangestellt statt angehängt werden soll (derzeit ungenutzt)
        """
        if value1 and value2:
            self.text += f"{value1}{self.delimiter}{value2}{self.newline}"

    def add_raw(self, text: str = '', prepend: bool = False) -> None:
        """
        Fügt rohen Text ohne Formatierung hinzu.

        Args:
            text: Der hinzuzufügende Text
            prepend: Falls True, am Anfang hinzufügen; falls False, anhängen
        """
        if prepend:
            self.text = f"{text}{self.text}"
        else:
            self.text += f"{text}"

    def add_heading(self, headline: str, ignore_empty_text: bool = False) -> None:
        """
        Fügt eine Überschrift zum Text hinzu.

        Args:
            headline: Der Überschriftentext
            ignore_empty_text: Falls True, Überschrift anzeigen, auch wenn Textkörper leer ist
        """
        self.headline = f"<br><b><i>{headline}</b></i>{self.newline}"
        self.ignore_empty_text = bool(ignore_empty_text)

    def get_text(self) -> str:
        """
        Ruft den vollständigen formatierten Text ab.

        Returns:
            Der vollständige Text mit optionaler Überschrift. Gibt leeren String zurück, falls
            Text leer ist und ignore_empty_text False ist.
        """
        if self.ignore_empty_text:
            return f"{self.headline}{self.text}"
        elif self.text:
            return f"{self.headline}{self.text}"
        else:
            return ""


class SearchWorker(QObject):
    """
    Hintergrund-Worker zum Extrahieren von Text aus Dateien für Volltextsuche.

    Dieser Worker läuft in einem separaten Thread, um Text aus allen Dateien
    in einem Verzeichnis zu extrahieren und in der SQLite-Datenbank für die Suche zu speichern.

    Signale:
        finished: Wird ausgesendet, wenn Extraktion abgeschlossen ist
        result: Sendet Tupel aus (empty_files_count, empty_pdfs_count, search_store, exception_text)
    """

    finished = Signal()
    result = Signal(list)

    def run(
        self,
        directory_to_scan: str,
        script_root: str,
        database: str,
        message_id: Optional[str] = None
    ) -> None:
        """
        Extrahiert Text aus allen Dateien und speichert in Datenbank.

        Args:
            directory_to_scan: Verzeichnis mit zu verarbeitenden Dateien
            script_root: Anwendungs-Wurzelverzeichnis (derzeit ungenutzt)
            database: Pfad zur SQLite-Datenbank
            message_id: UUID der aktuellen Nachricht
        """
        empty_files = 0
        empty_pdfs = 0
        search_store: Dict[str, str] = {}
        exception_text: Optional[str] = None

        try:
            # Standard-Argumente für Subprozess
            kwargs = {'capture_output': True}
            if os.name == 'nt':
                kwargs['creationflags'] = CREATE_NO_WINDOW

            # Extrahiert Text aus allen Dateien im Verzeichnis
            search_store = extract_texts_from_directory(directory_to_scan)

            # Speichert in Datenbank
            with sqlite3.connect(database) as db_connection:
                db_cursor = db_connection.cursor()

                # Löscht alte Einträge für diese Nachricht
                db_query = 'DELETE FROM plaintext WHERE uuid = ? AND basedir = ?;'
                db_cursor.execute(db_query, (message_id, directory_to_scan))

                # Fügt neue Einträge ein
                for filename, text in search_store.items():
                    if text == '':
                        empty_files += 1
                        if filename.lower().endswith('.pdf'):
                            empty_pdfs += 1

                    db_query = 'INSERT OR REPLACE INTO plaintext (uuid, filename, text, basedir) VALUES (?, ?, ?, ?);'
                    db_cursor.execute(db_query, (message_id, filename, text, directory_to_scan))

        except Exception as e:
            exception_text = str(e)

        # Sendet Ergebnisse
        result = (empty_files, empty_pdfs, search_store, exception_text)
        self.result.emit(result)
        self.finished.emit()
