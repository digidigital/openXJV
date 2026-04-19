#!/usr/bin/env python3
# coding: utf-8
"""
Einstellungsverwaltung für openXJV.

Dieses Modul stellt einen Wrapper um QSettings bereit zur Verwaltung von Anwendungseinstellungen
mit typsicheren Standards und vereinfachten Zugriffsmustern.
"""

from typing import Any, Dict, Optional
from PySide6.QtCore import QSettings


class SettingsManager:
    """
    Verwaltet Anwendungseinstellungen mit typsicheren Standards.

    Diese Klasse umschließt QSettings und stellt praktische Methoden zum Lesen
    und Schreiben von Anwendungseinstellungen mit korrekter Typbehandlung bereit.

    Attribute:
        settings: Das zugrunde liegende QSettings-Objekt
        defaults: Dictionary mit Standardwerten für alle Einstellungen
    """

    def __init__(self, organization: str = 'digidigital', application: str = 'openXJV') -> None:
        """
        Initialisiert den Einstellungs-Manager.

        Args:
            organization: Organisationsname für QSettings
            application: Anwendungsname für QSettings
        """
        self.settings = QSettings(organization, application)

        # TODO: Migration entfernen, sobald keine Installationen mit altem Registry-Pfad
        # (HKCU\Software\openXJV\digidigital) mehr im Umlauf sind.
        # Hintergrund: Organization und Application wurden vertauscht, damit Settings unter
        # HKCU\Software\digidigital\openXJV liegen — außerhalb des vom Uninstaller
        # gelöschten HKCU\Software\openXJV-Pfads.
        try:
            self._migrate_legacy_settings()
        except Exception:
            pass

        # Standardeinstellungen
        self.defaults: Dict[str, Any] = {
            # Ansichtssichtbarkeit
            'nachrichtenkopf': True,
            'favoriten': True,
            'metadaten': False,
            'notizen': False,
            'leereSpalten': True,  # Leere Spalten ausblenden

            # Exportoptionen
            'deckblatt': True,  # Deckblatt beim Export
            'dateidatumExportieren': True,  # Dateidaten exportieren
            'favoritenExportieren': True,  # Favoriten exportieren
            'nurFavoritenExportieren': False,  # Nur Favoriten exportieren
            'PDFnachExportOeffnen': True,  # PDF nach Export öffnen
            'NotizenaufDeckblatt': True,  # Notizen auf Deckblatt

            # Anzeigeoptionen
            'grosseSchrift': False,  # Große Schrift
            'anwendungshinweise': True,  # Anwendungshinweise
            'sucheAnzeigen': True,  # Suche anzeigen
            'dateiansichtLinksbuendig': False,  # Linksbündige Dateitabelle

            # PDF-Viewer
            'pdfViewer': 'PDFjs',  # PDFjs, chromium, or nativ

            # Updates
            'checkUpdates': True,  # Online nach Updates suchen

            # Maintenance Token
            'maintenance_email': '',
            'maintenance_token': '',
        }

    def get_bool(self, key: str, default: Optional[bool] = None) -> bool:
        """
        Ruft einen booleschen Einstellungswert ab.

        Args:
            key: Einstellungs-Schlüssel
            default: Standardwert (verwendet self.defaults, falls None)

        Returns:
            Der boolesche Einstellungswert
        """
        if default is None:
            default = self.defaults.get(key, False)

        value = str(self.settings.value(key, default)).lower()
        return value == 'true'

    def get_string(self, key: str, default: Optional[str] = None) -> str:
        """
        Ruft einen String-Einstellungswert ab.

        Args:
            key: Einstellungs-Schlüssel
            default: Standardwert (verwendet self.defaults, falls None)

        Returns:
            Der String-Einstellungswert
        """
        if default is None:
            default = self.defaults.get(key, '')

        return str(self.settings.value(key, default))

    def get_int(self, key: str, default: Optional[int] = None) -> int:
        """
        Ruft einen Integer-Einstellungswert ab.

        Args:
            key: Einstellungs-Schlüssel
            default: Standardwert (verwendet self.defaults, falls None)

        Returns:
            Der Integer-Einstellungswert
        """
        if default is None:
            default = self.defaults.get(key, 0)

        try:
            return int(self.settings.value(key, default))
        except (ValueError, TypeError):
            return default

    def set_value(self, key: str, value: Any) -> None:
        """
        Setzt einen Einstellungswert.

        Args:
            key: Einstellungs-Schlüssel
            value: Zu setzender Wert
        """
        self.settings.setValue(key, value)

    def reset_all(self) -> None:
        """
        Setzt alle Einstellungen auf Standardwerte zurück.

        This clears all stored settings and restores default values.
        """
        self.settings.clear()

    def sync(self) -> None:
        """
        Synchronize settings to persistent storage.

        This ensures all pending changes are written to disk.
        """
        self.settings.sync()

    def get_column_visibility(self, column_key: str, default: bool = True) -> bool:
        """
        Get visibility setting for a table column.

        Args:
            column_key: Column identifier
            default: Default visibility

        Returns:
            True if column should be visible
        """
        return self.get_bool(column_key, default)

    def set_column_visibility(self, column_key: str, visible: bool) -> None:
        """
        Set visibility setting for a table column.

        Args:
            column_key: Column identifier
            visible: Whether column should be visible
        """
        self.set_value(column_key, visible)

    def get_pdf_viewer(self) -> str:
        """
        Get the configured PDF-Viewer.

        Returns:
            Viewer name: 'PDFjs', 'chromium', or 'nativ'
        """
        return self.get_string('pdfViewer', 'PDFjs')

    def set_pdf_viewer(self, viewer: str) -> None:
        """
        Set the PDF-Viewer.

        Args:
            viewer: Viewer name ('PDFjs', 'chromium', or 'nativ')
        """
        if viewer in ('PDFjs', 'chromium', 'nativ'):
            self.set_value('pdfViewer', viewer)

    def _migrate_legacy_settings(self) -> None:
        """Migriert Einstellungen vom alten Registry-Pfad (HKCU\\Software\\openXJV\\digidigital)
        in den neuen Pfad (HKCU\\Software\\digidigital\\openXJV).

        Wird nur ausgeführt, wenn der neue Pfad noch leer ist und der alte Pfad Einträge enthält.

        TODO: Entfernen, sobald keine Installationen mit altem Registry-Pfad mehr im Umlauf sind.
        """
        if self.settings.allKeys():
            return  # Neuer Pfad enthält bereits Einstellungen — keine Migration nötig

        legacy = QSettings('openXJV', 'digidigital')
        keys = legacy.allKeys()
        if not keys:
            return  # Kein alter Pfad vorhanden — Neuinstallation

        for key in keys:
            value = legacy.value(key)
            if value is not None:
                self.settings.setValue(key, value)
        self.settings.sync()
