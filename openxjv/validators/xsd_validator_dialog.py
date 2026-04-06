#!/usr/bin/env python3
# coding: utf-8
"""QDialog fuer die XSD-Validierung von XJustiz-XML-Dateien.

Stellt die Klasse XSDValidatorDialog bereit, die als nicht-modaler
Dialog aus dem Hauptfenster gestartet wird. Die Validierung laeuft
beim Oeffnen automatisch und kann ueber einen Button wiederholt werden.
"""

import os
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QMessageBox,
    QApplication,
)

from .xsd_validator import XSDValidator


class XSDValidatorDialog(QDialog):
    """Dialog zur XSD-Validierung der geladenen XJustiz-XML-Datei.

    Der Dialog zeigt den Dateinamen an, fuehrt die Validierung
    automatisch beim Oeffnen durch und bietet Buttons zum
    erneuten Validieren und Kopieren der Ausgabe.

    Args:
        xml_path: Vollstaendiger Pfad zur geladenen XML-Datei.
        app_base_path: Basisverzeichnis der Anwendung (fuer Schema-Suche).
        detect_version_callback: Callable das einen Dateipfad entgegennimmt
            und die XJustiz-Version als String zurueckgibt (oder None).
        parent: Eltern-Widget (das Hauptfenster).
    """

    def __init__(
        self,
        xml_path: str,
        app_base_path: str,
        detect_version_callback: Callable[[str], Optional[str]],
        parent=None
    ):
        super().__init__(parent)

        self._xml_path = xml_path
        self._app_base_path = app_base_path
        self._detect_version = detect_version_callback
        self._validator = XSDValidator()

        self.setWindowTitle("XML-Validierung mittels XSD (Entwicklerwerkzeug)")
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumSize(800, 500)
        self.resize(900, 600)

        self._setup_ui()

        # Validierung beim Oeffnen automatisch starten
        self._run_validation()

    def _setup_ui(self):
        """Erstellt das Dialog-Layout."""
        layout = QVBoxLayout(self)

        # XML-Dateiname (nur Anzeige)
        file_layout = QHBoxLayout()
        file_label = QLabel("XML-Datei:")
        file_label.setStyleSheet("font-weight: bold;")
        self._file_name_label = QLabel(os.path.basename(self._xml_path))
        self._file_name_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        file_layout.addWidget(file_label)
        file_layout.addWidget(self._file_name_label, 1)
        layout.addLayout(file_layout)

        # Ausgabebereich (nur lesbar, kein Zeilenumbruch)
        self._output_text = QTextEdit()
        self._output_text.setReadOnly(True)
        self._output_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self._output_text, 1)

        # Buttons
        button_layout = QHBoxLayout()
        self._validate_button = QPushButton("Erneut validieren")
        self._validate_button.clicked.connect(self._run_validation)
        self._copy_button = QPushButton("In Zwischenablage kopieren")
        self._copy_button.clicked.connect(self._copy_to_clipboard)
        button_layout.addStretch()
        button_layout.addWidget(self._validate_button)
        button_layout.addWidget(self._copy_button)
        layout.addLayout(button_layout)

    def _run_validation(self):
        """Fuehrt die XSD-Validierung durch und zeigt das Ergebnis an.

        Erkennt die Version, sucht das Schema, validiert und
        zeigt alle Fehler im Ausgabebereich an. Bei Problemen
        wird eine Warnmeldung angezeigt.
        """
        self._output_text.clear()
        self._output_text.setPlainText("Validierung laeuft...")
        QApplication.processEvents()

        try:
            # 1. Version erkennen
            version = self._detect_version(self._xml_path)
            if not version:
                self._show_warning(
                    "Die XJustiz-Version konnte nicht aus der "
                    "XML-Datei ermittelt werden."
                )
                self._output_text.setPlainText(
                    "Fehler: XJustiz-Version nicht erkennbar."
                )
                return
  
            # 2. Schema-Ordner finden
            schema_folder = XSDValidator.find_schema_folder(
                self._app_base_path, version
            )
            if not schema_folder:
                schemata_dir = os.path.join(self._app_base_path, 'schemata')
                self._show_warning(
                    f"Kein passender Schema-Ordner fuer Version "
                    f"{version} gefunden.\n\n"
                    f"Suchverzeichnis: {schemata_dir}"
                )
                self._output_text.setPlainText(
                    f"Fehler: Schema-Ordner fuer Version {version} "
                    f"nicht gefunden."
                )
                return

            # 3. Nachrichten-XSD finden
            xsd_path = XSDValidator.find_nachrichten_xsd(schema_folder)
            if not xsd_path:
                self._show_warning(
                    f"Die Datei xjustiz_0005_nachrichten_*.xsd wurde "
                    f"im Ordner\n{schema_folder}\nnicht gefunden."
                )
                self._output_text.setPlainText(
                    "Fehler: Nachrichten-XSD nicht gefunden."
                )
                return

            # 4. Validierung durchfuehren
            result = self._validator.validate(self._xml_path, xsd_path)

            # 5. Ergebnis anzeigen
            self._output_text.setPlainText(result.summary_text)

            # Zum Anfang scrollen
            cursor = self._output_text.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            self._output_text.setTextCursor(cursor)

        except Exception as e:
            error_msg = f"Unerwarteter Fehler: {type(e).__name__}: {e}"
            self._show_warning(error_msg)
            self._output_text.setPlainText(error_msg)

    def _copy_to_clipboard(self):
        """Kopiert den gesamten Ausgabetext in die Zwischenablage."""
        text = self._output_text.toPlainText()
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)

    def _show_warning(self, message: str):
        """Zeigt eine Warnmeldung als QMessageBox an."""
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle("Validierungsfehler")
        msg_box.setText(message)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()
