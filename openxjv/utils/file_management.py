#!/usr/bin/env python3
# coding: utf-8
"""
Datei-Verwaltungshilfsprogramme für openXJV.

Dieses Modul stellt eine FileManager-Klasse bereit, die alle Dateioperationen verwaltet
einschließlich Laden, Exportieren und Öffnen von Dateien.

Klassen:
    FileManager: Hauptklasse für Dateiverwaltungsoperationen.

2022 - 2025 Björn Seipel
"""

import os
import re
import sys
import subprocess
from pathlib import Path
from shutil import copyfile
from typing import Optional, List, Any
from uuid import uuid4
from zipfile import ZipFile

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QFileDialog, QMessageBox, QApplication


class FileManager:
    """
    Verwaltet Dateioperationen für XJustiz-Dokumente.

    Diese Klasse stellt Methoden zum Laden, Exportieren und Öffnen von Dateien bereit,
    sowie zur Handhabung von ZIP-Archiven und verschiedenen Dateidialogen.

    Attribute:
        app (QApplication): Die Anwendungsinstanz für Cursor-Verwaltung.
        settings (QSettings): Anwendungseinstellungen zum Speichern von Präferenzen.
        homedir (str): Pfad zum Home-Verzeichnis des Benutzers.
        basedir (str): Basisverzeichnis für aktuelle Dateioperationen.
        temp_dir: Temporäres Verzeichnis für Dateioperationen.
    """

    def __init__(
        self,
        app: QApplication,
        settings: QSettings,
        homedir: str,
        basedir: str = "",
        temp_dir: Any = None
    ):
        """
        Initialisiert den FileManager.

        Args:
            app: Die QApplication-Instanz.
            settings: QSettings-Instanz zum Speichern von Präferenzen.
            homedir: Pfad zum Home-Verzeichnis des Benutzers.
            basedir: Basisverzeichnis für Dateioperationen. Standard ist leerer String.
            temp_dir: Temporäres Verzeichnisobjekt. Standard ist None.
        """
        self.app = app
        self.settings = settings
        self.homedir = homedir
        self.basedir = basedir
        self.temp_dir = temp_dir

    def detect_xjustiz_version(self, file_path: str) -> Optional[str]:
        """
        Erkennt die XJustiz-Version aus einer XML-Datei.

        Liest die Datei Zeile für Zeile, um das xjustizVersion-Attribut zu finden
        und extrahiert die Versionsnummer.

        Args:
            file_path: Pfad zur XJustiz-XML-Datei.

        Returns:
            Versionsstring (z.B. "3.6.2") oder None, falls nicht gefunden.

        Example:
            >>> fm = FileManager(app, settings, homedir)
            >>> version = fm.detect_xjustiz_version("/path/to/file.xml")
            >>> print(version)  # "3.6.2"
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as fp:
                while True:
                    line = fp.readline()
                    if not line:
                        break

                    # Entfernt Leerzeichen für einfacheres Musterabgleichen
                    line = line.replace(" ", "")

                    # Sucht nach xjustizVersion-Attribut
                    search_for_version = re.search(
                        r'xjustizVersion\W*=\W*[^\d](\d+\.\d+\.\d+)[^\d]',
                        line
                    )

                    if search_for_version:
                        return search_for_version.group(1)

            return None

        except Exception:
            return None

    def load_file(
        self,
        file_path: str,
        parser_map: dict,
        on_success: Optional[callable] = None,
        on_error: Optional[callable] = None
    ) -> Optional[Any]:
        """
        Lädt eine XJustiz-Datei und parst sie basierend auf erkannter Version.

        Diese Methode erkennt die XJustiz-Version aus der Datei und verwendet
        den geeigneten Parser zum Laden der Daten. Sie verwaltet Cursor-Zustände
        und behandelt Fehler elegant.

        Args:
            file_path: Pfad zur zu ladenden XJustiz-XML-Datei.
            parser_map: Dictionary, das Versionsstrings Parser-Funktionen zuordnet.
                Example: {"2.4.0": parser240, "3.6.2": parser362}
            on_success: Optionale Callback-Funktion, die bei erfolgreichem Laden aufgerufen wird.
                Erhält (akte_object, file_path, version) als Argumente.
            on_error: Optionale Callback-Funktion, die bei Fehler aufgerufen wird.
                Erhält (file_path, exception) als Argumente.

        Returns:
            Geparste Akte-Objekt bei Erfolg, None bei Fehler.

        Example:
            >>> parser_map = {
            ...     "2.4.0": parser240,
            ...     "3.6.2": parser362
            ... }
            >>> akte = fm.load_file("/path/to/file.xml", parser_map)
        """
        self.app.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))

        try:
            # Erkennt Version
            version = self.detect_xjustiz_version(file_path)

            # Wählt geeigneten Parser aus
            if version in parser_map:
                parser = parser_map[version]
            else:
                # Use the most recent parser as default
                parser = parser_map.get("default", list(parser_map.values())[-1])

            # Parse the file
            akte = parser(file_path)

            self.app.restoreOverrideCursor()

            # Ruft Erfolgs-Callback auf if provided
            if on_success and callable(on_success):
                on_success(akte, file_path, version)

            return akte

        except Exception as e:
            self.app.restoreOverrideCursor()

            # Ruft Fehler-Callback auf if provided
            if on_error and callable(on_error):
                on_error(file_path, e)

            return None

    def select_zip_files(self) -> Optional[List[str]]:
        """
        Open a file dialog to select one or more ZIP files.

        Returns:
            List of selected file paths, or None if dialog was cancelled.

        Example:
            >>> files = fm.select_zip_files()
            >>> if files:
            ...     print(f"Selected {len(files)} files")
        """
        files, check = QFileDialog.getOpenFileNames(
            None,
            "XJustiz-ZIP-Archive öffnen",
            str(self.settings.value("defaultFolder", str(self.homedir))),
            "XJustiz-Archive (*.zip *.ZIP)"
        )

        if check:
            return files
        return None

    def extract_zip_files(
        self,
        zip_files: List[str],
        on_error: Optional[callable] = None
    ) -> Optional[str]:
        """
        Extract ZIP files to a temporary directory.

        Args:
            zip_files: List of paths to ZIP files to extract.
            on_error: Optionale Callback-Funktion, die bei Fehler aufgerufen wird.
                Erhält (file_path, exception) als Argumente.

        Returns:
            Path to the temporary extraction directory on success, None on failure.

        Example:
            >>> files = ["/path/to/archive1.zip", "/path/to/archive2.zip"]
            >>> temp_path = fm.extract_zip_files(files)
            >>> if temp_path:
            ...     print(f"Extracted to: {temp_path}")
        """
        if not zip_files or not self.temp_dir:
            return None

        self.app.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))

        # Create unique temporary directory
        temp_path = os.path.join(self.temp_dir.name, str(uuid4()))
        Path(temp_path).mkdir(parents=True, exist_ok=True)

        try:
            for file in zip_files:
                with ZipFile(file, 'r') as zipfile:
                    zipfile.extractall(temp_path)

            self.app.restoreOverrideCursor()
            return temp_path

        except Exception as e:
            self.app.restoreOverrideCursor()

            if on_error and callable(on_error):
                on_error(file, e)

            return None

    def export_to_zip(
        self,
        zip_path: str,
        file_list: List[str],
        include_xml: bool = True,
        xml_file: Optional[str] = None
    ) -> bool:
        """
        Export files to a ZIP archive.

        Args:
            zip_path: Path where the ZIP file should be created.
            file_list: List of file paths to include in the ZIP.
            include_xml: Whether to include the XJustiz XML file. Defaults to True.
            xml_file: Path to the XJustiz XML file to include. Required if include_xml is True.

        Returns:
            True on success, False on failure.

        Example:
            >>> files = ["doc1.pdf", "doc2.pdf"]
            >>> success = fm.export_to_zip("/path/to/archive.zip", files, xml_file="data.xml")
        """
        try:
            # Ensure zip extension
            if not zip_path.lower().endswith('.zip'):
                zip_path = zip_path + '.zip'

            # Prepare file list
            files_to_zip = file_list.copy()

            # Add XML file if requested
            if include_xml and xml_file:
                files_to_zip.append(xml_file)

            # Create ZIP archive
            self._create_zip(zip_path, files_to_zip)
            return True

        except Exception:
            return False

    def _create_zip(self, zipname: str, filelist: List[str]) -> None:
        """
        Create a ZIP archive from a list of files.

        This is a private helper method used by export_to_zip.

        Args:
            zipname: Path for the output ZIP file.
            filelist: List of file paths to include.

        Raises:
            Exception: If ZIP creation fails.
        """
        with ZipFile(zipname, 'w') as outzip:
            for file in filelist:
                outzip.write(file, os.path.basename(file))

    def export_to_folder(
        self,
        folder_path: str,
        file_list: List[str],
        include_xml: bool = True,
        xml_file: Optional[str] = None
    ) -> bool:
        """
        Export files to a folder by copying them.

        Args:
            folder_path: Destination folder path.
            file_list: List of file paths (relative to basedir) to copy.
            include_xml: Whether to include the XJustiz XML file. Defaults to True.
            xml_file: Path to the XJustiz XML file to include. Required if include_xml is True.

        Returns:
            True on success, False on failure.

        Example:
            >>> files = ["doc1.pdf", "doc2.pdf"]
            >>> success = fm.export_to_folder("/path/to/folder", files, xml_file="data.xml")
        """
        try:
            for filename in file_list:
                filepath = os.path.join(self.basedir, filename)
                targetpath = os.path.join(folder_path, filename)
                copyfile(filepath, targetpath)

            # Copy XML file if requested
            if include_xml and xml_file:
                xml_basename = os.path.basename(xml_file)
                copyfile(xml_file, os.path.join(folder_path, xml_basename))

            return True

        except Exception:
            return False

    def open_file_external(
        self,
        filename: str,
        ignore_warnings: bool = False,
        absolute_path: bool = False,
        on_warning: Optional[callable] = None
    ) -> bool:
        """
        Open a file with the system's default application.

        This method performs security checks on the filename and opens it
        with the appropriate system command based on the platform.

        Args:
            filename: Name or path of the file to open.
            ignore_warnings: Whether to skip security warnings. Defaults to False.
            absolute_path: Whether filename is an absolute path. Defaults to False.
            on_warning: Optional callback for handling warnings.
                Receives (warning_type, filename) and returns bool to continue.

        Returns:
            True if file was opened successfully, False otherwise.

        Example:
            >>> fm.open_file_external("document.pdf")
            >>> fm.open_file_external("/absolute/path/to/file.pdf", absolute_path=True)
        """
        # Security check: illegal characters
        illegal_chars = re.findall(r"[^-A-ZÄÖÜa-zäöüß_0-9\.]", filename)
        if illegal_chars and not ignore_warnings:
            if on_warning:
                if not on_warning("illegal_chars", filename):
                    return False
            else:
                # Default behavior: ask user
                msg_box = self._create_warning_dialog(
                    "Der Dateiname enthält unzulässige Zeichen.\n\n"
                    "Dies kann ein Sicherheitsrisiko bedeuten, falls ausführbare "
                    "Befehle im Dateinamen versteckt wurden! Es kann sich jedoch "
                    "auch schlicht um Nachlässigkeit des Absenders handeln.\n\n"
                    "Trotzdem öffnen?"
                )
                if msg_box.exec() == QMessageBox.StandardButton.Yes:
                    return self.open_file_external(
                        filename,
                        ignore_warnings=True,
                        absolute_path=absolute_path,
                        on_warning=on_warning
                    )
                return False

        # Security check: filename length
        if len(filename) > 90 and not ignore_warnings:
            if on_warning:
                if not on_warning("long_filename", filename):
                    return False
            else:
                # Default behavior: ask user
                msg_box = self._create_warning_dialog(
                    "Der Dateiname ist länger als 90 Zeichen.\n"
                    "Dies entspricht nicht den Vorgaben des XJustiz-Standards.\n\n"
                    "Trotzdem öffnen?"
                )
                if msg_box.exec() == QMessageBox.StandardButton.Yes:
                    return self.open_file_external(
                        filename,
                        ignore_warnings=True,
                        absolute_path=absolute_path,
                        on_warning=on_warning
                    )
                return False

        # Determine full path
        if absolute_path:
            full_path = filename
        else:
            full_path = os.path.join(self.basedir, filename)

        # Check if file exists
        if not os.path.exists(full_path):
            return False

        # Open file based on platform
        try:
            if sys.platform.startswith('linux'):
                # Copy current environment
                env = os.environ.copy()

                # Remove LD_LIBRARY_PATH for this call (pyinstaller workaround)
                env.pop("LD_LIBRARY_PATH", None)

                # Start xdg-open with cleaned environment
                subprocess.Popen(
                    ["xdg-open", full_path],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

            elif sys.platform.lower().startswith('win'):
                os.startfile(full_path)

            else:  # macOS
                os.popen("open '%s'" % full_path)

            return True

        except Exception:
            return False

    def _create_warning_dialog(self, message: str) -> QMessageBox:
        """
        Create a warning dialog with Yes/No buttons.

        Args:
            message: Warning message to display.

        Returns:
            Configured QMessageBox instance.
        """
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle("Sicherheitshinweis!")
        msg_box.setText(message)
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        # Localize buttons
        button_yes = msg_box.button(QMessageBox.StandardButton.Yes)
        button_yes.setText('Ja')
        button_no = msg_box.button(QMessageBox.StandardButton.No)
        button_no.setText('Nein')
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)

        return msg_box

    def select_file_dialog(
        self,
        folder: Optional[str] = None,
        file_filter: str = "XJustiz-Dateien (*.xml *.XML)"
    ) -> Optional[str]:
        """
        Show a file selection dialog.

        Args:
            folder: Initial folder to show. Defaults to settings default folder.
            file_filter: File filter string for the dialog.
                Defaults to "XJustiz-Dateien (*.xml *.XML)".

        Returns:
            Selected file path, or None if cancelled.

        Example:
            >>> file = fm.select_file_dialog()
            >>> if file:
            ...     print(f"Selected: {file}")
        """
        if folder is None:
            folder = str(self.settings.value("defaultFolder", self.homedir))

        file, check = QFileDialog.getOpenFileName(
            None,
            "XJustiz-Datei öffnen",
            folder,
            file_filter
        )

        if check:
            return file
        return None

    def select_folder_dialog(
        self,
        title: str = "Standardverzeichnis wählen",
        initial_folder: Optional[str] = None
    ) -> Optional[str]:
        """
        Show a folder selection dialog.

        Args:
            title: Dialog window title. Defaults to "Standardverzeichnis wählen".
            initial_folder: Initial folder to show. Defaults to settings default folder.

        Returns:
            Selected folder path, or None if cancelled.

        Example:
            >>> folder = fm.select_folder_dialog("Select export folder")
            >>> if folder:
            ...     print(f"Selected: {folder}")
        """
        if initial_folder is None:
            initial_folder = str(self.settings.value("defaultFolder", str(self.homedir)))

        folder = QFileDialog.getExistingDirectory(
            None,
            title,
            initial_folder,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks
        )

        if folder:
            return folder
        return None

    def save_file_dialog(
        self,
        title: str = "Datei speichern",
        file_filter: str = "Alle Dateien (*.*)",
        default_extension: str = ""
    ) -> Optional[str]:
        """
        Show a save file dialog.

        Args:
            title: Dialog window title. Defaults to "Datei speichern".
            file_filter: File filter string. Defaults to "Alle Dateien (*.*)".
            default_extension: Extension to add if not present. Defaults to empty string.

        Returns:
            Selected file path with extension, or None if cancelled.

        Example:
            >>> path = fm.save_file_dialog("Save as ZIP", "ZIP-Dateien (*.zip)", ".zip")
            >>> if path:
            ...     print(f"Will save to: {path}")
        """
        filepath, _ = QFileDialog.getSaveFileName(
            None,
            title,
            self.settings.value("defaultFolder", str(self.homedir)),
            file_filter
        )

        if filepath:
            # Add extension if not present
            if default_extension and not filepath.lower().endswith(default_extension.lower()):
                filepath = filepath + default_extension
            return filepath

        return None

    def set_basedir(self, basedir: str) -> None:
        """
        Set the base directory for file operations.

        Args:
            basedir: Path to the base directory.
        """
        self.basedir = basedir

    def get_basedir(self) -> str:
        """
        Get the current base directory.

        Returns:
            Path to the current base directory.
        """
        return self.basedir
