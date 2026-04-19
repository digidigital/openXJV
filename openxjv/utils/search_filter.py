#!/usr/bin/env python3
# coding: utf-8
"""
Such- und Filter-Verwaltungsmodul

Dieses Modul stellt Funktionalität zum Suchen und Filtern von Dokumententabellen bereit,
einschließlich Volltextsuchfähigkeiten und Tabellenzeilen-Filterung basierend auf
Einschluss-/Ausschluss-Mustern.

Klassen:
    SearchWorker: Hintergrund-Thread zum Extrahieren von Text aus Dateien für Volltextsuche.
    SearchFilterManager: Verwaltet Such- und Filteroperationen für Dokumententabellen.
"""

import os
import json
import time
import sqlite3
import traceback
from typing import Dict, Set, Optional, Tuple, Any

from PySide6.QtCore import (
    QEventLoop,
    Qt,
    QThread,
    QCoreApplication,
    Signal,
)
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QTableWidget

from .search_indexing import extract_texts_from_directory

if os.name == 'nt':
    from subprocess import CREATE_NO_WINDOW


class SearchWorker(QThread):
    """
    Hintergrund-Thread zum Extrahieren von Text aus Dateien für Volltextsuche.

    Dies ist ein QThread-Subclass statt QObject + moveToThread().
    Das moveToThread()-Pattern hatte auf Windows folgende Probleme:
    1. Lambda-Slots liefen im Hauptthread statt im Worker-Thread
    2. Signal-Zustellung über Thread-Grenzen war unzuverlässig für
       Python-Lambdas (Qt kann keinen Empfänger-Thread bestimmen)
    3. Race-Conditions zwischen finished->quit() und result-Signal

    Als QThread-Subclass:
    - run() wird automatisch im neuen Thread ausgeführt
    - Das QThread-OBJEKT lebt im Hauptthread (nur run() läuft im neuen Thread)
    - Daher werden Signale (result) per AutoConnection korrekt als
      QueuedConnection zum Hauptthread zugestellt
    - finished ist ein eingebautes QThread-Signal, das nach run() feuert
    - Kein moveToThread(), keine Event-Loop, keine Signal-Routing-Probleme

    Signale:
        result: Sendet Tupel aus (empty_files_count, empty_pdfs_count, search_store, exception_text)
        finished: (geerbt von QThread) Wird nach run() automatisch ausgesendet
    """

    result = Signal(tuple)

    def __init__(self, directory_to_scan: str, script_root: str,
                 database: str, message_id: str, parent=None):
        super().__init__(parent)
        self._directory_to_scan = directory_to_scan
        self._script_root = script_root
        self._database = database
        self._message_id = message_id

    def run(self) -> None:
        """
        Extrahiert Text aus allen Dateien und speichert in Datenbank.
        Wird automatisch im neuen Thread ausgeführt wenn start() aufgerufen wird.
        """
        empty_files = 0
        empty_pdfs = 0
        search_store: Dict[str, str] = {}
        exception_text: Optional[str] = None

        try:
            # Extrahiert Text aus allen Dateien im Verzeichnis
            search_store = extract_texts_from_directory(self._directory_to_scan)

            # Speichert in Datenbank
            with sqlite3.connect(self._database) as db_connection:
                db_cursor = db_connection.cursor()

                # Löscht alte Einträge für diese Nachricht
                db_query = 'DELETE FROM plaintext WHERE uuid = ? AND basedir = ?;'
                db_cursor.execute(db_query, (self._message_id, self._directory_to_scan))

                # Fügt neue Einträge ein
                for filename, text in search_store.items():
                    if text == '':
                        empty_files += 1
                        if filename.lower().endswith('.pdf'):
                            empty_pdfs += 1

                    db_query = 'INSERT OR REPLACE INTO plaintext (uuid, filename, text, basedir) VALUES (?, ?, ?, ?);'
                    db_cursor.execute(db_query, (self._message_id, filename, text, self._directory_to_scan))

        except Exception as e:
            exception_text = str(e)

        # Sendet Ergebnisse. Da das QThread-Objekt im Hauptthread lebt,
        # wird AutoConnection dies als QueuedConnection zum Hauptthread
        # zustellen. finished (QThread-intern) feuert danach automatisch.
        result_data = (empty_files, empty_pdfs, search_store, exception_text)
        self.result.emit(result_data)


class SearchFilterManager:
    """
    Verwaltet Such- und Filteroperationen für Dokumententabellen.

    Diese Klasse behandelt Volltextsuche über Dokumente, Tabellenzeilen-Filterung
    basierend auf Einschluss-/Ausschluss-Mustern und Suchindex-Vorbereitung aus
    verschiedenen Quellen (JSON-Cache, Datenbank oder Dateiverarbeitung).

    Attribute:
        search_store (Dict[str, str]): Cache, der Dateinamen ihrem Textinhalt zuordnet.
        search_lock (bool): Flag, das anzeigt, ob Suche derzeit nicht verfügbar ist.
        empty_files (int): Anzahl der Dateien ohne extrahierbaren Text.
        empty_pdf (int): Anzahl der PDF-Dateien ohne extrahierbaren Text.
    """

    def __init__(self):
        """Initialisiert den SearchFilterManager mit leerem Such-Speicher."""
        self.search_store: Dict[str, str] = {}
        self.search_lock: bool = False
        self.empty_files: int = 0
        self.empty_pdf: int = 0
        self.search_prep_thread: Optional[QThread] = None
        self.search_worker: Optional[SearchWorker] = None

    def prepare_search_store(
        self,
        app: QCoreApplication,
        basedir: str,
        db_path: str,
        uuid: str,
        script_root: str,
        status_callback: Optional[callable] = None,
        ready_callback: Optional[callable] = None,
        reset_search_store: bool = True,
        search_visible: bool = True,
        table_has_header: bool = True
    ) -> bool:
        """
        Bereitet den Such-Speicher vor durch Laden von Textdaten aus Cache, Datenbank oder Dateien.

        Diese Methode versucht, durchsuchbaren Textinhalt in folgender Reihenfolge zu laden:
        1. Aus einer JSON-Cache-Datei (search_store.json)
        2. Aus der SQLite-Datenbank
        3. Durch Verarbeitung von Dateien in einem Hintergrund-Thread

        Args:
            app: Die QApplication-Instanz für Ereignisverarbeitung und Cursor-Steuerung.
            basedir: Basisverzeichnis mit den zu durchsuchenden Dokumenten.
            db_path: Pfad zur SQLite-Datenbankdatei.
            uuid: Eindeutiger Bezeichner für den aktuellen Dokumentensatz.
            script_root: Wurzelverzeichnis der Anwendungsskripte.
            status_callback: Optionaler Callback für Statusaktualisierungen. Wird mit String-Nachricht aufgerufen.
            ready_callback: Optionaler Callback, wenn Such-Speicher bereit ist. Wird aufgerufen mit
                          (empty_files, empty_pdf, search_store, error_msg)-Tupel.
            reset_search_store: Ob der existierende Such-Speicher vor dem Laden zurückgesetzt werden soll.
            search_visible: Ob die Suchfunktion derzeit sichtbar/aktiviert ist.
            table_has_header: Ob die Dokumententabelle eine Kopfzeile hat.

        Returns:
            True, falls Such-Speicher-Vorbereitung initiiert oder erfolgreich geladen wurde,
            False, falls Suche nicht sichtbar oder bereits befüllt ist.

        Hinweis:
            Diese Methode blockiert die Ereignisschleife während der Prüfung, ob eine vorherige Such-
            Thread noch läuft, mit 0,3 Sekunden Pause zwischen Prüfungen.
        """
        try:
            thread_ref = self.search_prep_thread
        except RuntimeError:
            self.search_prep_thread = None
            self.search_worker = None
            thread_ref = None

        # Blockiert Ereignisschleife, falls eine Suche bereits läuft
        while True:
            try:
                if thread_ref and thread_ref.isRunning():
                    # Begrenze Overhead mit Pause
                    time.sleep(0.3)
                else:
                    break
            except Exception:
                break
            app.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

        if reset_search_store:
            self.search_store = {}

        # Lade Textdaten nur in den Speicher, wenn Suche sichtbar und Such-Speicher leer ist
        if not search_visible or len(self.search_store) != 0:
            return False

        self.search_lock = True

        # Prüfe, ob eine Kopfzeile vorhanden ist (fehlt bei leerer Dokumentenstruktur)
        if not table_has_header:
            return False

        app.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        if status_callback:
            status_callback('Daten für Suchfunktion werden geladen')

        # Versuche existierenden Such-Speicher aus search_store.json zu lesen
        search_store_json_path = os.path.join(basedir, 'search_store.json')
        if len(self.search_store) == 0 and os.path.isfile(search_store_json_path):
            with open(search_store_json_path, 'rb') as f:
                self.search_store = json.loads(f.read())
                empty_files = 0
                empty_pdf = 0
                for key in self.search_store:
                    text = self.search_store[key]
                    if len(text) == 0:
                        empty_files += 1
                        if key.lower().endswith('.pdf'):
                            empty_pdf += 1

            if len(self.search_store) > 0:
                self._search_store_ready(
                    (empty_files, empty_pdf, self.search_store, False),
                    app,
                    status_callback,
                    ready_callback
                )
                return True

        # Versuche existierenden Such-Speicher aus Datenbank zu lesen
        if len(self.search_store) == 0:
            with sqlite3.connect(db_path) as db_connection:
                db_cursor = db_connection.cursor()
                db_query = '''
                    SELECT filename, text FROM plaintext WHERE uuid = ? AND basedir = ?;
                '''
                db_cursor.execute(db_query, (uuid, basedir))
                rows = db_cursor.fetchall()
                empty_files = 0
                empty_pdf = 0
                for row in rows:
                    self.search_store[row[0]] = row[1]
                    if len(row[1]) == 0:
                        empty_files += 1
                        if row[0].lower().endswith('.pdf'):
                            empty_pdf += 1

            if len(self.search_store) > 0:
                self._search_store_ready(
                    (empty_files, empty_pdf, self.search_store, False),
                    app,
                    status_callback,
                    ready_callback
                )
                return True

        # Erstelle neuen Such-Speicher durch Konvertierung von Dateien in "Klartext"
        if len(self.search_store) == 0:
            self.search_worker = SearchWorker(
                basedir, script_root, db_path, uuid
            )
            # search_prep_thread wird nicht mehr separat gebraucht — der
            # Worker IST der Thread. Referenz behalten für isRunning()-Check.
            self.search_prep_thread = self.search_worker

            # result-Signal: AutoConnection. Da das QThread-Objekt im
            # Hauptthread lebt, erkennt Qt automatisch, dass dies eine
            # Cross-Thread-Verbindung ist → QueuedConnection → Callback
            # wird im Hauptthread ausgeführt.
            self.search_worker.result.connect(
                lambda result: self._search_store_ready(
                    result, app, status_callback, ready_callback
                )
            )

            # finished: Aufräumen nach Thread-Ende.
            self.search_worker.finished.connect(self.search_worker.deleteLater)

            self.search_worker.start()
        else:
            self._search_store_ready(
                (0, 0, {}, 'Textaufbereitung fehlgeschlagen.'),
                app,
                status_callback,
                ready_callback
            )

        return True

    def _search_store_ready(
        self,
        result: Tuple[int, int, Dict[str, str], Any],
        app: QCoreApplication,
        status_callback: Optional[callable] = None,
        ready_callback: Optional[callable] = None
    ) -> None:
        """
        Behandelt das Such-Speicher-bereit-Ereignis.

        Interne Methode, die aufgerufen wird, wenn der Such-Speicher geladen oder vorbereitet wurde.
        Aktualisiert den internen Zustand und ruft Callbacks auf.

        Args:
            result: Tupel mit (empty_files, empty_pdf, search_store, error_msg).
            app: Die QApplication-Instanz für Cursor-Steuerung.
            status_callback: Optionaler Callback für Statusaktualisierungen.
            ready_callback: Optionaler Callback zur Benachrichtigung, wenn bereit.
        """
        self.empty_files = result[0]
        self.empty_pdf = result[1]
        self.search_store = result[2]
        self.search_lock = False

        message = (f'Suchfunktion ist bereit. {self.empty_files} Dateien '
                  f'({self.empty_pdf} PDF-Dateien) enthalten keinen Text bzw. es konnte kein Text ausgelesen werden.')

        if result[3]:
            error_msg = result[3]
            message = f'Während der Aufbereitung der Inhalte für die Suche ist ein Fehler aufgetreten: {error_msg}'

        if status_callback:
            status_callback(message)

        if ready_callback:
            ready_callback(result)

        app.restoreOverrideCursor()

        # Aufräumen: search_worker und search_prep_thread zeigen auf dasselbe
        # Objekt (SearchWorker ist ein QThread-Subclass). deleteLater wird
        # bereits per finished-Signal ausgelöst. Hier nur Referenzen löschen.
        self.search_worker = None
        self.search_prep_thread = None

    def perform_search(
        self,
        table: QTableWidget,
        search_terms_text: str,
        app: QCoreApplication,
        filename_column_name: str = "Dateiname",
        status_callback: Optional[callable] = None,
        clear_callback: Optional[callable] = None,
        filters_callback: Optional[callable] = None,
        message_callback: Optional[callable] = None
    ) -> None:
        """
        Führt Volltextsuche über Dokumente durch und filtert Tabellenzeilen.

        Sucht nach allen Begriffen in der Suchzeichenkette innerhalb des Dokumententextinhalts.
        Zeilen werden ausgeblendet, wenn sie nicht alle Suchbegriffe enthalten (UND-Logik).
        Durchsucht nur derzeit sichtbare Zeilen.

        Args:
            table: Das zu filternde QTableWidget.
            search_terms_text: Leerzeichen-getrennte Suchbegriffe zum Finden.
            app: Die QApplication-Instanz für Cursor-Steuerung.
            filename_column_name: Name der Spalte mit Dateinamen.
            status_callback: Optionaler Callback für Statusmeldungen. Wird mit String aufgerufen.
            clear_callback: Optionaler Callback zum Leeren des Sucheingabefeldes.
            filters_callback: Optionaler Callback zum erneuten Anwenden von Filtern. Sollte
                            keepSearchTerms=True Parameter akzeptieren.
            message_callback: Optionaler Callback zur Anzeige von Nachrichten an den Benutzer.

        Hinweis:
            - Suche ist Groß-/Kleinschreibung-unabhängig
            - Alle Suchbegriffe müssen in einem Dokument vorhanden sein, damit es übereinstimmt (UND-Logik)
            - Durchsucht nur Dokumente in derzeit sichtbaren Zeilen
            - Blendet Zeilen aus, die nicht den Suchkriterien entsprechen
        """
        # Setze Ansicht zurück, falls bereits durch vorherige Suche gefiltert
        if filters_callback:
            filters_callback(keepSearchTerms=True)

        if search_terms_text == '':
            return
        elif self.search_lock:
            if clear_callback:
                clear_callback()
            if message_callback:
                message_callback(
                    "Der Suchindex ist momentan nicht verfügbar. "
                    "Bitte später erneut versuchen."
                )
            return

        filename_column = None

        try:
            # Finde die Dateinamen-Spalte
            for header_item in range(table.columnCount()):
                if table.horizontalHeaderItem(header_item).text() == filename_column_name:
                    filename_column = header_item
                    break
        except AttributeError:
            return

        search_terms = search_terms_text.split()

        if filename_column is not None and len(search_terms) != 0:
            app.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
            # TODO: Volltextsuche in Datenbank
            for row in range(table.rowCount()):
                # Durchsuche nur sichtbare Dateien
                if not table.isRowHidden(row):
                    filename = table.item(row, filename_column).text()
                    if filename:
                        hits = 0

                        # Versuche zuerst mit .pdf-Erweiterung, dann ohne
                        if self.search_store.get(filename + '.pdf'):
                            text = self.search_store.get(filename + '.pdf')
                        elif self.search_store.get(filename):
                            text = self.search_store.get(filename)
                        else:
                            text = ''

                        # Zähle, wie viele Suchbegriffe gefunden wurden
                        for term in search_terms:
                            if term.lower() in text:
                                hits += 1

                        # Verberge Zeile, wenn nicht alle Suchbegriffe gefunden wurden
                        if not hits == len(search_terms):
                            table.hideRow(row)

        status_message = 'Suche abgeschlossen.'
        if self.empty_pdf != 0:
            status_message += (f' Bitte beachten: {self.empty_pdf} PDF-Dateien in der Nachricht '
                             f'enthalten keinen durchsuchbaren Text.')

        if status_callback:
            status_callback(status_message)

        app.restoreOverrideCursor()

    @staticmethod
    def apply_filters(
        table: QTableWidget,
        plus_filter_text: str,
        minus_filter_text: str,
        settings: Optional[Any] = None,
        clear_search_callback: Optional[callable] = None,
        keep_search_terms: bool = False
    ) -> None:
        """
        Wendet Einschluss- und Ausschluss-Filter auf Tabellenzeilen an.

        Filtert Zeilen basierend auf Plus-Filter (Einschluss) und Minus-Filter (Ausschluss) Mustern.
        Plus-Filter zeigen nur übereinstimmende Zeilen; Minus-Filter verbergen übereinstimmende Zeilen.

        Args:
            table: Das zu filternde QTableWidget.
            plus_filter_text: Leerzeichen-getrennte Begriffe zum Einschließen (nur übereinstimmende Zeilen zeigen).
                            Leerer String bedeutet alle Zeilen einschließen.
            minus_filter_text: Leerzeichen-getrennte Begriffe zum Ausschließen (übereinstimmende Zeilen verbergen).
            settings: Optionales QSettings-Objekt zum Speichern von Filterwerten.
            clear_search_callback: Optionaler Callback zum Leeren der Suchbegriffe.
            keep_search_terms: Falls False, werden Suchbegriffe über Callback geleert.

        Hinweis:
            - Filter sind standardmäßig Groß-/Kleinschreibung-unabhängig (abhängig von Qt.MatchFlag.MatchContains)
            - Plus-Filter verwendet ODER-Logik (Zeile stimmt mit beliebigem Begriff überein)
            - Minus-Filter verwendet ODER-Logik (Zeile wird verborgen, wenn sie mit beliebigem Begriff übereinstimmt)
            - Minus-Filter wird nach Plus-Filter angewendet
        """
        if not keep_search_terms and clear_search_callback:
            clear_search_callback()

        filtered_rows = set(SearchFilterManager.filter_table_rows(
            table,
            plus_filter_text,
            minus_filter_text
        ))

        # Blockiere Aktualisierungen für bessere Performance
        table.setUpdatesEnabled(False)

        row_count = table.rowCount()
        for row in range(row_count):
            should_show = row in filtered_rows
            # Nur ändern, wenn notwendig
            if table.isRowHidden(row) == should_show:
                table.setRowHidden(row, not should_show)

        table.setUpdatesEnabled(True)

        # Speichere Filterwerte
        if settings:
            settings.setValue("minusFilter", minus_filter_text)
            settings.setValue("plusFilter", plus_filter_text)

    @staticmethod
    def filter_table_rows(
        table: QTableWidget,
        plus_filter_str: str,
        minus_filter_str: str
    ) -> Set[int]:
        """
        Berechnet, welche Tabellenzeilen basierend auf Filtern sichtbar sein sollten.

        Args:
            table: Das zu filternde QTableWidget.
            plus_filter_str: Leerzeichen-getrennte Einschluss-Filterbegriffe.
            minus_filter_str: Leerzeichen-getrennte Ausschluss-Filterbegriffe.

        Returns:
            Menge von Zeilenindizes, die nach dem Filtern sichtbar sein sollten.

        Hinweis:
            - Falls plus_filter_str leer ist (oder nur Leerzeichen), werden zunächst alle Zeilen eingeschlossen
            - Plus-Filter verwendet ODER-Logik: Zeile wird eingeschlossen, wenn sie mit beliebigem Begriff übereinstimmt
            - Minus-Filter verwendet ODER-Logik: Zeile wird ausgeschlossen, wenn sie mit beliebigem Begriff übereinstimmt
            - Suche wird mit Qt.MatchFlag.MatchContains durchgeführt (Teilstring-Suche)
        """
        rows = set()

        # Wende Plus-Filter an (Einschluss)
        if plus_filter_str.replace(" ", ""):
            for filter_term in plus_filter_str.split():
                for hit in table.findItems(filter_term, Qt.MatchFlag.MatchContains):
                    rows.add(hit.row())
        else:
            # Falls kein Plus-Filter, schließe alle Zeilen ein
            for row in range(table.rowCount()):
                rows.add(row)

        # Wende Minus-Filter an (Ausschluss)
        for filter_term in minus_filter_str.split():
            for hit in table.findItems(filter_term, Qt.MatchFlag.MatchContains):
                if hit.row() in rows:
                    rows.remove(hit.row())

        return rows

    @staticmethod
    def apply_magic_filters(
        minus_filter_text: str,
        update_minus_filter_callback: callable,
        filters_callback: callable
    ) -> None:
        """
        Fügt gängige technische Dokumenten-Dateierweiterungen zum Ausschluss-Filter hinzu.

        Fügt bekannte technische Dateierweiterungen (.pks, .p7s, .xml, .pkcs7) zum
        Minus-Filter hinzu, falls diese noch nicht vorhanden sind, und wendet dann die Filter an.

        Args:
            minus_filter_text: Aktueller Minus-Filter-Text.
            update_minus_filter_callback: Callback zum Aktualisieren des Minus-Filter-Textes.
                                         Wird mit dem neuen Filter-String aufgerufen.
            filters_callback: Callback zum Auslösen der Filter-Anwendung.

        Hinweis:
            Diese "magischen" Filter helfen dabei, technische/Signatur-Dateien zu verbergen, die
            typischerweise nicht relevant für die Dokumentenansicht sind.
        """
        filter_items = minus_filter_text.split()
        extensions_to_add = [".pks", ".p7s", ".xml", ".pkcs7"]

        new_filter = minus_filter_text
        for file_extension in extensions_to_add:
            if file_extension not in filter_items:
                new_filter += ' ' + file_extension

        update_minus_filter_callback(new_filter)
        filters_callback()

    @staticmethod
    def reset_filters(
        clear_search_callback: callable,
        clear_plus_filter_callback: callable,
        clear_minus_filter_callback: callable,
        filters_callback: callable
    ) -> None:
        """
        Löscht alle Suchbegriffe und Filterfelder.

        Setzt die Sucheingabe und sowohl Plus- als auch Minus-Filter auf leer zurück
        und wendet dann Filter erneut an (was alle Zeilen anzeigen wird).

        Args:
            clear_search_callback: Callback zum Leeren des Suchbegriffe-Feldes.
            clear_plus_filter_callback: Callback zum Leeren des Plus-Filter-Feldes.
            clear_minus_filter_callback: Callback zum Leeren des Minus-Filter-Feldes.
            filters_callback: Callback zum Auslösen der Filter-Anwendung.
        """
        clear_search_callback()
        clear_plus_filter_callback()
        clear_minus_filter_callback()
        filters_callback()
