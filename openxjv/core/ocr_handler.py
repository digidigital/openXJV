#!/usr/bin/env python3
# coding: utf-8
"""
OCR-Handler-Modul für openXJV

Dieses Modul stellt OCR-Funktionalität (Optische Zeichenerkennung) für PDF-Dokumente bereit.
Es verwaltet Einzel-Datei-OCR, Batch-OCR-Operationen und stellt Callbacks für Fortschrittsberichte bereit.

Klassen:
    OCRHandler: Main class for handling OCR operations on PDF files.
"""

import os
import sys
import time
import traceback
import multiprocessing
import concurrent.futures
from pathlib import Path
from shutil import copyfile
from threading import Thread
from typing import Callable, Optional, Dict, List, Any

from PySide6.QtCore import QEventLoop, Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox, QApplication, QStatusBar
from PySide6.QtGui import QCursor
from PySide6.QtCore import QSettings

from .ocr import PDFocr


class OCRHandler:
    """
    Verwaltet OCR-Operationen für PDF-Dokumente.

    Diese Klasse stellt Methoden zur Verfügung, um OCR auf einzelnen PDF-Dateien, Batch-OCR
    Operationen auf mehreren Dateien durchzuführen und OCR-Fortschritt mit Callbacks für UI-Updates zu verwalten.

    Attribute:
        ocr_lock (bool): Thread-Sperre zur Verhinderung gleichzeitiger OCR-Operationen.
        status_bar (Optional[QStatusBar]): Referenz zur Statusleiste für Fortschrittsaktualisierungen.
        app (Optional[QApplication]): Referenz zur Qt-Anwendung für Ereignisverarbeitung.
        home_dir (Path): Pfad zum Home-Verzeichnis des Benutzers.
        settings (Optional[QSettings]): Anwendungseinstellungen für Standard-Pfade.
        display_message_callback (Optional[Callable]): Callback zur Anzeige von Nachrichten an den Benutzer.
        scan_folder_after_ocr (Optional[str]): Ordnerpfad zum Scannen nach OCR-Abschluss.
        last_exception_string (str): Letzte Exception-Nachricht für Fehlerverfolgung.
        ocr_threads (List[Thread]): Liste aktiver OCR-Threads.
    """

    def __init__(
        self,
        status_bar: Optional[QStatusBar] = None,
        app: Optional[QApplication] = None,
        home_dir: Optional[Path] = None,
        settings: Optional[QSettings] = None,
        display_message_callback: Optional[Callable[[str], None]] = None
    ):
        """
        Initialisiert den OCR-Handler.

        Args:
            status_bar: Qt-Statusleisten-Widget zur Anzeige von Fortschrittsnachrichten.
            app: Qt-Anwendungsinstanz für Ereignisverarbeitung.
            home_dir: Pfad zum Home-Verzeichnis des Benutzers. Standard ist Path.home(), falls nicht angegeben.
            settings: Qt-Einstellungsobjekt zum Speichern von Standard-Pfaden.
            display_message_callback: Callback-Funktion zur Anzeige von Nachrichten an den Benutzer.
        """
        self.ocr_lock: bool = False
        self.status_bar: Optional[QStatusBar] = status_bar
        self.app: Optional[QApplication] = app
        self.home_dir: Path = home_dir or Path.home()
        self.settings: Optional[QSettings] = settings
        self.display_message_callback: Optional[Callable[[str], None]] = display_message_callback
        self.scan_folder_after_ocr: Optional[str] = None
        self.last_exception_string: str = ""
        self.ocr_threads: List[Thread] = []

    def perform_ocr(
        self,
        source_path: Optional[str] = None,
        parent_widget: Optional[Any] = None
    ) -> None:
        """
        Führt OCR auf einer einzelnen PDF-Datei durch.

        Diese Methode führt Texterkennung auf einer beliebigen PDF-Datei durch. Falls kein Quellpfad
        angegeben ist, öffnet sie einen Dateidialog zur Dateiauswahl. Die Ausgabedatei
        wird automatisch mit einem 'ocr'-Suffix im selben Verzeichnis erstellt.

        Args:
            source_path: Pfad zur zu verarbeitenden PDF-Datei. Falls None, wird ein Dateidialog geöffnet.
            parent_widget: Eltern-Widget für den Dateidialog.

        Hinweise:
            - Die Methode prüft, ob die Datei für OCR geeignet ist (kein existierender Text, gültige PDF).
            - Erstellt einen eindeutigen Ausgabedateinamen, um Überschreiben existierender Dateien zu vermeiden.
            - Führt OCR in einem separaten Thread aus, um Blockierung der UI zu vermeiden.
            - Aktualisiert die Statusleiste mit Fortschrittsinformationen.
        """
        if self.ocr_lock:
            self._display_message(
                'Es läuft bereits eine Texterkennung. Bitte warten Sie, bis der Vorgang abgeschlossen ist.'
            )
            return

        if not source_path:
            source_path, check = QFileDialog.getOpenFileName(
                parent_widget,
                "PDF-Datei für die Texterkennung auswählen",
                str(self.home_dir),
                "PDF-Dateien (*.pdf *.PDF)"
            )
            if not check:
                return

        if not PDFocr.checkIfSupported(source_path):
            self._display_message(
                'Die ausgewählte Datei kann nicht mit der Texterkennungsfunktion bearbeitet werden.\n\n'
                'Mögliche Gründe:\n'
                '- Die Datei enthält bereits Text\n'
                '- Die Datei enthält mehr als ein Bild pro Seite\n'
                '- Die PDF-Datei ist defekt'
            )
            return

        self.ocr_lock = True

        # Findet eindeutigen Dateinamen, falls Name bereits existiert
        ocr_marker = 'ocr'
        counter = 0
        while True:
            target_path = os.path.join(
                Path(source_path).parent,
                f'{Path(source_path).stem}.{ocr_marker}.pdf'
            )
            if os.path.isfile(target_path):
                counter += 1
                ocr_marker = f'ocr({counter})'
            else:
                break

        # Führt in separatem Thread aus, um Blockierung der Event-Schleife zu vermeiden
        ocr_thread = Thread(target=self.ocr_file_worker, args=(source_path, target_path))
        self.ocr_threads.append(ocr_thread)
        ocr_thread.start()

        if self.status_bar:
            self.status_bar.showMessage(f'Texterkennung für {source_path} gestartet')

    def perform_ocr_on_loaded_pdf(
        self,
        loaded_pdf_path: str,
        loaded_pdf_filename: str,
        parent_widget: Optional[Any] = None
    ) -> None:
        """
        Führt OCR auf dem aktuell geladenen PDF-Dokument in der Vorschau durch.

        Diese Methode ist darauf ausgelegt, mit einer PDF-Datei zu arbeiten, die aktuell angezeigt wird in
        der Anwendungsvorschau. Der Benutzer wählt den Ausgabeort über einen Speicherdialog aus.

        Args:
            loaded_pdf_path: Vollständiger Pfad zur aktuell geladenen PDF-Datei.
            loaded_pdf_filename: Dateiname der aktuell geladenen PDF.
            parent_widget: Eltern-Widget für den Dateidialog.

        Hinweise:
            - Validiert, dass eine PDF geladen und für OCR geeignet ist.
            - Öffnet einen Speicherdialog zur Auswahl des Ausgabeorts.
            - Führt OCR in einem separaten Thread aus.
            - Die Ausgabedatei wird nach Abschluss automatisch geöffnet.
        """
        if not loaded_pdf_filename:
            return

        if self.ocr_lock:
            self._display_message(
                'Es läuft bereits eine Texterkennung. Bitte warten Sie, bis der Vorgang abgeschlossen ist.'
            )
            return

        if (
            loaded_pdf_path
            and os.path.exists(loaded_pdf_path)
            and loaded_pdf_path.lower().endswith('.pdf')
            and PDFocr.checkIfSupported(loaded_pdf_path)
        ):
            default_folder = str(self.home_dir)
            if self.settings:
                default_folder = self.settings.value("defaultFolder", str(self.home_dir))

            export_filename, extension = QFileDialog.getSaveFileName(
                parent_widget,
                "Zieldatei wählen",
                default_folder,
                "PDF-Dateien (*.pdf *.PDF)"
            )

            if export_filename:
                if not export_filename.lower().endswith('.pdf'):
                    export_filename = export_filename + '.pdf'
            else:
                return

            self.ocr_lock = True

            # Verschiebt in separaten Thread, um Blockierung der Event-Schleife zu vermeiden
            try:
                ocr_thread = Thread(
                    target=self.ocr_file_worker,
                    args=(loaded_pdf_path, export_filename, True)
                )
                self.ocr_threads.append(ocr_thread)
                ocr_thread.start()
            except Exception as e:
                self.last_exception_string = str(e)
                if '--debug' in sys.argv:
                    print(f'DEBUG OCRHandler.__texterkennung: {traceback.format_exc()}', file=sys.stderr)
                self.ocr_lock = False
                return

            if self.status_bar:
                self.status_bar.showMessage(
                    f'Texterkennung für {loaded_pdf_path} gestartet. '
                    'Das Dokument öffnet sich nach Abschluss automatisch.'
                )
        else:
            self._display_message(
                'Die in der Vorschau angezeigte Datei kann nicht mit der Texterkennungsfunktion bearbeitet werden.\n\n'
                'Mögliche Gründe:\n'
                '- Die Datei enthält bereits Text\n'
                '- Die Datei enthält mehr als ein Bild pro Seite\n'
                '- In der Vorschau wird keine PDF-Datei angezeigt'
            )

    def perform_batch_ocr(
        self,
        base_dir: str,
        search_store: Dict[str, str],
        parent_widget: Optional[Any] = None,
        action_ocr_all: Optional[Any] = None
    ) -> Optional[str]:
        """
        Führt OCR auf allen nicht durchsuchbaren Dateien in einem Verzeichnis durch.

        Diese Methode erstellt eine Kopie eines Nachrichtenverzeichnisses und führt OCR auf allen
        nicht durchsuchbaren PDF-Dateien durch. Andere Dateien werden einfach unverändert kopiert.

        Args:
            base_dir: Basisverzeichnis mit den Quelldateien.
            search_store: Dictionary, das Dateinamen ihrem extrahierten Textinhalt zuordnet.
                         Dateien mit leeren Strings werden als nicht durchsuchbar betrachtet.
            parent_widget: Eltern-Widget für Dialoge.
            action_ocr_all: Action-Widget, das während der Verarbeitung ausgeblendet werden soll (optional).

        Returns:
            Der Zielordner-Pfad bei Erfolg, None bei Abbruch oder Fehler.

        Hinweise:
            - Zeigt einen Bestätigungsdialog vor dem Start.
            - Fordert Benutzer auf, ein leeres Zielverzeichnis auszuwählen.
            - Kopiert durchsuchbare Dateien direkt, reiht nicht durchsuchbare PDFs für OCR ein.
            - Verwendet Multi-Thread-Batch-Verarbeitung für Effizienz.
            - Updates status bar with progress information.
            - Setzt scan_folder_after_ocr-Attribut für Nachverarbeitung.
        """
        if self.ocr_lock:
            self._display_message(
                'Es läuft bereits eine Texterkennung. Bitte warten Sie, bis der Vorgang abgeschlossen ist.'
            )
            return None

        # Zeigt Bestätigungsdialog
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setWindowTitle("Texterkennung durchführen?")
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        button_yes = msg_box.button(QMessageBox.StandardButton.Yes)
        button_yes.setText('Ja')
        button_no = msg_box.button(QMessageBox.StandardButton.No)
        button_no.setText('Nein')
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)
        msg_box.setText(
            "Soll für die nicht durchsuchbaren Dokumente eine Texterkennung durchgeführt werden "
            "und eine Kopie der Nachricht mit durchsuchbaren PDF-Dateien angelegt werden?\n\n"
            "Dieser Vorgang kann einige Zeit in Anspruch nehmen und ggf. reagiert die Anwendung "
            "während der Bearbeitung nicht. Bitte haben Sie in diesem Fall ein wenig Geduld.\n\n"
            "Hinweis: Schlechte Scans und handschriftliche Inhalte werden weiterhin nicht durchsuchbar "
            "sein oder fehlerhaften Text enthalten. Entsprechende Dateien werden ggf. weiterhin als "
            "nicht druchsuchbare Dateien im Suchhinweis angezeigt."
        )
        msg_box.exec()
        if msg_box.clickedButton() == button_no:
            return None

        # Wählt Zielverzeichnis aus
        default_folder = str(self.home_dir)
        if self.settings:
            default_folder = self.settings.value("defaultFolder", str(self.home_dir))

        folder = QFileDialog.getExistingDirectory(
            parent_widget,
            "Bitte ein leeres Verzeichnis zum Speichern der Nachrichtenkopie auswählen",
            default_folder,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks
        )

        if not folder:
            return None

        if folder == base_dir:
            self._display_message(
                "Eine Kopie der Nachricht kann nicht im Verzeichnis der Originalnachricht erstellt werden!"
            )
            return None

        if os.listdir(folder):
            self._display_message(
                "Zur Erstellung der Nachrichtenkopie bitte ein leeres Verzeichnis angeben."
            )
            return None

        # Dateidialog schließt sich nicht immer ohne Pause
        time.sleep(2)

        if action_ocr_all:
            action_ocr_all.setVisible(False)

        self.ocr_lock = True

        if self.status_bar:
            self.status_bar.showMessage(
                'Dateien werden in das Zielverzeichnis kopiert oder für die Texterkennung ausgewählt.'
            )
            self.status_bar.repaint()

        ocr_queue = []
        for filename in search_store.keys():
            if self.app:
                self.app.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

            # Ignoriert bestimmte Dateien aus Quellnachricht und kopiert sie NICHT
            if filename in ('search_store.json',):
                continue

            source_path = os.path.join(base_dir, filename)
            target_path = os.path.join(folder, filename)

            if not os.path.exists(source_path) or not os.path.isfile(source_path):
                continue

            # Prüft, ob Datei eine nicht durchsuchbare PDF ist
            if filename.lower().endswith('.pdf') and len(search_store[filename]) == 0:
                if PDFocr.checkIfSupported(source_path):
                    ocr_queue.append({'sourcepath': source_path, 'targetpath': target_path})
                else:
                    copyfile(source_path, target_path)
            else:
                copyfile(source_path, target_path)

        self.scan_folder_after_ocr = target_path

        if self.status_bar:
            self.status_bar.showMessage(f'Starte Texterkennung für {str(len(ocr_queue))} Dokumente')
            self.status_bar.repaint()

        ocr_thread = Thread(target=self.ocr_batch_worker, args=(ocr_queue,))
        self.ocr_threads.append(ocr_thread)
        ocr_thread.start()

        return folder

    def ocr_file_worker(
        self,
        source_path: str,
        target_path: str,
        open_when_done: bool = True
    ) -> None:
        """
        Worker-Funktion für einzelne OCR-Aufgaben.

        Diese Methode ist darauf ausgelegt, in einem separaten Thread ausgeführt zu werden, um Blockierung
        des Haupt-UI-Threads während der OCR-Verarbeitung zu vermeiden.

        Args:
            source_path: Pfad zur Quell-PDF-Datei.
            target_path: Pfad, unter dem die OCR-verarbeitete Datei gespeichert werden soll.
            open_when_done: Ob die Datei nach OCR-Abschluss automatisch geöffnet werden soll.

        Hinweise:
            - Misst Verarbeitungszeit und meldet sie über ocr_finished-Callback.
            - Fängt Exceptions ab und meldet sie über display_message-Callback.
            - Gibt automatisch die OCR-Sperre frei, wenn beendet.
        """
        self.ocr_lock = True
        start_time = time.time()

        try:
            PDFocr(source_path, target_path, open_when_done)
        except Exception as e:
            self._display_message(f"Texterkennung fehlgeschlagen\n\n{e}")
            self.ocr_lock = False
            self.last_exception_string = str(e)
            if '--debug' in sys.argv:
                print(f'DEBUG OCRHandler._ocr_thread_function: {traceback.format_exc()}', file=sys.stderr)
            return

        self.ocr_finished(time.time() - start_time)

    def ocr_batch_worker(
        self,
        jobs: List[Dict[str, str]],
        open_when_done: bool = False,
        threads: Optional[int] = None
    ) -> None:
        """
        Worker-Funktion für langandauernde Batch-OCR-Aufgaben.

        Diese Methode verarbeitet mehrere OCR-Jobs parallel mit einem Thread-Pool.
        Sie ist darauf ausgelegt, in einem separaten Thread ausgeführt zu werden.

        Args:
            jobs: Liste von Job-Dictionaries, die jeweils 'sourcepath'- und 'targetpath'-Schlüssel enthalten.
            open_when_done: Ob Dateien nach OCR-Abschluss automatisch geöffnet werden sollen.
            threads: Anzahl der zu verwendenden Worker-Threads. Falls None, wird CPU-Anzahl - 1 verwendet.

        Hinweise:
            - Verwendet ThreadPoolExecutor für parallele Verarbeitung.
            - Setzt Warte-Cursor während der Verarbeitung.
            - Meldet Fortschritt für jede abgeschlossene Datei.
            - Fängt Exceptions einzelner Jobs ab und protokolliert sie.
            - Misst Gesamtverarbeitungszeit und meldet über ocr_finished-Callback.
        """
        self.ocr_lock = True

        if self.app:
            self.app.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))

        if not threads:
            threads = multiprocessing.cpu_count() - 1

        start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(threads) as executor:
            future_ocr = {
                executor.submit(PDFocr, job['sourcepath'], job['targetpath'], open_when_done, threads): job
                for job in jobs
            }

            for future in concurrent.futures.as_completed(future_ocr):
                job = future_ocr[future]
                try:
                    if future.result() is not None:
                        self.report_ocr_progress(f"Texterkennung abgeschlossen für {job['sourcepath']}")
                except Exception as exc:
                    error_message = f"OCR-Thread {job} generated an exception: {str(exc)}"
                    self.last_exception_string = error_message
                    if '--debug' in sys.argv:
                        print(f'DEBUG OCRHandler.perform_batch_ocr: {traceback.format_exc()}', file=sys.stderr)

        if self.app:
            self.app.restoreOverrideCursor()

        self.ocr_finished(time.time() - start_time)

    def report_ocr_progress(self, message: str) -> None:
        """
        Meldet OCR-Fortschritt an die Benutzeroberfläche.

        Diese Callback-Methode aktualisiert die Statusleiste mit Fortschrittsinformationen.

        Args:
            message: Anzuzeigende Fortschrittsnachricht.

        Hinweise:
            - Diese Methode wird typischerweise von Worker-Threads aufgerufen.
            - Aktualisierungen sind thread-sicher, da Qt threadübergreifende Signal-Emission verwaltet.
        """
        if self.status_bar:
            self.status_bar.showMessage(f"{message}")

    def ocr_finished(self, seconds: float) -> None:
        """
        Behandelt OCR-Abschluss.

        Diese Callback-Methode wird aufgerufen, wenn die OCR-Verarbeitung abgeschlossen ist.
        Sie gibt die OCR-Sperre frei und zeigt Abschlussinformationen an.

        Args:
            seconds: Zeit, die für die OCR-Operation benötigt wurde.

        Hinweise:
            - Gibt die OCR-Sperre frei, um neue Operationen zu erlauben.
            - Formatiert die verstrichene Zeit mit 2 Dezimalstellen.
            - Aktualisiert die Statusleiste mit Abschlussnachricht.
        """
        message = f'Texterkennung abgeschlossen. Benötigte Zeit: {"{:.2f}".format(seconds)} Sekunden'
        self.ocr_lock = False

        if self.status_bar:
            self.status_bar.showMessage(message)

    def _display_message(self, message: str) -> None:
        """
        Zeigt eine Nachricht dem Benutzer an.

        Interne Hilfsmethode, die an display_message_callback delegiert, falls verfügbar.

        Args:
            message: Nachricht, die dem Benutzer angezeigt werden soll.
        """
        if self.display_message_callback:
            self.display_message_callback(message)

    def is_ocr_available(self) -> bool:
        """
        Prüft, ob OCR-Funktionalität verfügbar ist.

        Diese Methode prüft, ob Tesseract OCR installiert und richtig konfiguriert ist
        mit deutscher Sprachunterstützung.

        Returns:
            True, falls OCR verfügbar ist, sonst False.
        """
        return PDFocr.tesseractAvailable()

    def is_file_supported(self, filepath: str) -> bool:
        """
        Prüft, ob eine Datei für OCR-Verarbeitung unterstützt wird.

        Eine Datei wird unterstützt, wenn sie eine gültige PDF ohne existierenden Text ist und
        nur ein Bild pro Seite enthält.

        Args:
            filepath: Path to the file to check.

        Returns:
            True, falls die Datei mit OCR verarbeitet werden kann, sonst False.
        """
        return PDFocr.checkIfSupported(filepath)

    def cleanup_threads(self) -> None:
        """
        Bereinigt beendete OCR-Threads.

        Diese Methode verbindet alle beendeten Threads und entfernt sie aus der Thread-Liste.
        Sollte periodisch aufgerufen werden, um Speicherlecks durch angesammelte Thread-Objekte zu verhindern.
        """
        self.ocr_threads = [t for t in self.ocr_threads if t.is_alive()]
