#!/usr/bin/env python3
# coding: utf-8
"""
PDF-Operationen-Modul

Dieses Modul stellt Funktionalität für PDF-Export und Manipulationsoperationen bereit.
Druckfunktionalität wurde zu pdfjs_viewer ausgelagert.
Extrahiert aus openXJV.py und für eigenständige Nutzung umgestaltet.

Author: Björn Seipel
License: GPL v3
"""

import os
import sys
import traceback
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional, List, Tuple, Dict, Any, Callable

from pikepdf import Pdf, OutlineItem
from fpdf import FPDF
import pypdfium2 as pdfium
from PIL import Image
from PIL.ImageQt import ImageQt

from openxjv.core.database import FavoriteEntry

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QTableWidget, QApplication
# QPrinter import removed - printing is handled by pdfjs_viewer


class PDFExportError(Exception):
    """Benutzerdefinierte Exception für PDF-Export-Fehler."""
    pass


# PDFPrintError removed - printing is handled by pdfjs_viewer


class TableFileInfo:
    """Container für Dateiinformationen, die aus dem Tabellen-Widget extrahiert wurden."""

    def __init__(
        self,
        filename: str,
        display_name: Optional[str] = None,
        class_name: Optional[str] = None,
        date: Optional[str] = None,
        scan_date: Optional[str] = None,
        filing_date: Optional[str] = None,
        received_date: Optional[str] = None,
    ):
        """
        Initialisiert Dateiinformationen.

        Args:
            filename: Der tatsächliche Dateiname auf der Festplatte
            display_name: Optionaler Anzeigename für die Datei
            class_name: Optionaler Klassifizierungsname
            date: Optionales allgemeines Datum
            scan_date: Optionales Scan-Datum
            filing_date: Optionales Veraktungsdatum
            received_date: Optionales Eingangsdatum
        """
        self.filename = filename
        self.display_name = display_name
        self.class_name = class_name
        self.date = date
        self.scan_date = scan_date
        self.filing_date = filing_date
        self.received_date = received_date


class PDFExportConfig:
    """Konfiguration für PDF-Export-Operationen."""

    def __init__(
        self,
        include_cover_page: bool = False,
        include_favorites_only: bool = False,
        include_favorites_section: bool = True,
        include_file_dates: bool = True,
        open_after_export: bool = False,
        font_dir: Optional[str] = None,
    ):
        """
        Initialisiert Export-Konfiguration.

        Args:
            include_cover_page: Ob ein Deckblatt eingeschlossen werden soll
            include_favorites_only: Nur favorisierte Dateien exportieren
            include_favorites_section: Separaten Favoriten-Bereich in Gliederung erstellen
            include_file_dates: Datumsangaben in Gliederungsnamen einschließen
            open_after_export: PDF nach erfolgreichem Export öffnen
            font_dir: Verzeichnis mit Schriftarten-Dateien (Ubuntu-Schriftfamilie)
        """
        self.include_cover_page = include_cover_page
        self.include_favorites_only = include_favorites_only
        self.include_favorites_section = include_favorites_section
        self.include_file_dates = include_file_dates
        self.open_after_export = open_after_export
        self.font_dir = font_dir or self._get_default_font_dir()

    @staticmethod
    def _get_default_font_dir() -> str:
        """Ruft Standard-Schriftarten-Verzeichnispfad ab."""
        return os.path.join(os.path.dirname(__file__), '..', '..', 'fonts')


def extract_table_columns(table_widget: QTableWidget) -> Dict[str, Optional[int]]:
    """
    Extrahiert Spaltenindizes aus Tabellen-Widget-Kopfzeilen.

    Args:
        table_widget: Qt-Tabellen-Widget mit Dateiinformationen

    Returns:
        Dictionary, das Spaltennamen ihren Indizes zuordnet

    Raises:
        PDFExportError: Falls erforderliche Spalten nicht gefunden werden
    """
    columns = {
        'filename': None,
        'displayname': None,
        'class': None,
        'date': None,
        'scan': None,
        'filing': None,
        'received': None,
    }

    try:
        column_range = table_widget.columnCount()

        for header_idx in range(column_range):
            header_text = table_widget.horizontalHeaderItem(header_idx).text()

            if header_text == "Dateiname":
                columns['filename'] = header_idx
            elif header_text == "Klasse":
                columns['class'] = header_idx
            elif header_text == "Datum":
                columns['date'] = header_idx
            elif header_text == "Scandatum":
                columns['scan'] = header_idx
            elif header_text == "Veraktung":
                columns['filing'] = header_idx
            elif header_text == "Eingang":
                columns['received'] = header_idx
            elif header_text in ("Anzeige-\nname", "Anzeigename"):
                columns['displayname'] = header_idx

    except Exception as e:
        raise PDFExportError(
            f"Could not determine columns for export: {str(e)}"
        )

    if columns['filename'] is None:
        raise PDFExportError(
            'Required column "Dateiname" not found in table'
        )

    return columns


def extract_files_from_table(
    table_widget: QTableWidget,
    base_dir: str,
    favorites: Optional[List[FavoriteEntry]] = None,
    only_favorites: bool = False,
) -> List[TableFileInfo]:
    """
    Extrahiert Dateiinformationen aus Tabellen-Widget.

    Args:
        table_widget: Qt-Tabellen-Widget mit Dateiinformationen
        base_dir: Base directory where files are located
        favorites: List of favorite filenames
        only_favorites: If True, only extract favorited files

    Returns:
        Liste von TableFileInfo-Objekten

    Raises:
        PDFExportError: Falls Tabellen-Parsing fehlschlägt
    """
    columns = extract_table_columns(table_widget)
    favorites = favorites or []

    # TODO (Version 1.5+): Nach Entfernung der Legacy-Unterstützung (anzeigename='')
    # kann hier direkt ein Set von (anzeigename, filename)-Tupeln für den only_favorites-
    # Filter verwendet werden. Aktuell reicht Dateiname-Abgleich, da jede favorisierte
    # Datei unabhängig vom Anzeigenamen exportiert werden soll.
    favorites_filenames = {e.filename for e in favorites}

    files_info = []

    for row in range(table_widget.rowCount()):
        if table_widget.isRowHidden(row):
            continue

        filename = table_widget.item(row, columns['filename']).text()

        if only_favorites and filename not in favorites_filenames:
            continue

        # Überspringt, falls Datei nicht existiert (außer für Signaturdateien)
        file_path = os.path.join(base_dir, filename)
        if not os.path.exists(file_path):
            if not filename.lower().endswith(('.pkcs7', '.p7s', '.pks')):
                continue
            else:
                continue

        # Extrahiert optionale Informationen
        display_name = None
        if columns['displayname'] is not None:
            display_name = table_widget.item(row, columns['displayname']).text()

        class_name = None
        if columns['class'] is not None:
            class_name = table_widget.item(row, columns['class']).text()

        date_val = None
        if columns['date'] is not None:
            date_val = table_widget.item(row, columns['date']).text()

        scan_date = None
        if columns['scan'] is not None:
            scan_date = table_widget.item(row, columns['scan']).text()

        filing_date = None
        if columns['filing'] is not None:
            filing_date = table_widget.item(row, columns['filing']).text()

        received_date = None
        if columns['received'] is not None:
            received_date = table_widget.item(row, columns['received']).text()

        files_info.append(TableFileInfo(
            filename=filename,
            display_name=display_name,
            class_name=class_name,
            date=date_val,
            scan_date=scan_date,
            filing_date=filing_date,
            received_date=received_date,
        ))

    return files_info


def convert_text_file_to_pdf(
    file_path: str,
    output_path: str,
    font_dir: str,
    orientation: str = 'portrait',
) -> str:
    """
    Konvertiert textbasierte Datei (XML, CSV, TXT) nach PDF.

    Args:
        file_path: Pfad zur Textdatei
        output_path: Pfad für die Ausgabe-PDF
        font_dir: Verzeichnis mit Ubuntu-Schriftarten
        orientation: Seitenausrichtung ('portrait' oder 'landscape')

    Returns:
        Pfad zur erstellten PDF-Datei

    Raises:
        PDFExportError: Falls Konvertierung fehlschlägt
    """
    try:
        # Versucht zuerst UTF-8-Lesen, fällt zurück auf cp1252
        try:
            contents = Path(file_path).read_text(encoding='utf-8')
        except UnicodeDecodeError:
            contents = Path(file_path).read_text(encoding='cp1252')
    except Exception as e:
        raise PDFExportError(f"Could not read file {file_path}: {str(e)}")

    try:
        temp_pdf = FPDF(orientation=orientation)

        # Fügt Ubuntu-Schriftfamilie hinzu
        ubuntu_font_path = os.path.join(font_dir, 'ubuntu-font-family-0.83')
        temp_pdf.add_font("Ubuntu", style="", fname=f"{ubuntu_font_path}/Ubuntu-R.ttf")
        temp_pdf.add_font("Ubuntu", style="b", fname=f"{ubuntu_font_path}/Ubuntu-B.ttf")
        temp_pdf.add_font("Ubuntu", style="i", fname=f"{ubuntu_font_path}/Ubuntu-RI.ttf")
        temp_pdf.add_font("Ubuntu", style="bi", fname=f"{ubuntu_font_path}/Ubuntu-BI.ttf")
        temp_pdf.set_font("Ubuntu")

        temp_pdf.add_page()
        temp_pdf.write(text=contents)
        temp_pdf.output(output_path)

        return output_path
    except Exception as e:
        raise PDFExportError(f"Could not convert text file to PDF: {str(e)}")


def convert_image_to_pdf(
    image_path: str,
    output_path: str,
) -> str:
    """
    Konvertiert Bilddatei (JPG, PNG, TIFF) nach PDF.

    Args:
        image_path: Pfad zur Bilddatei
        output_path: Pfad für die Ausgabe-PDF

    Returns:
        Pfad zur erstellten PDF-Datei

    Raises:
        PDFExportError: Falls Konvertierung fehlschlägt
    """
    try:
        with Image.open(image_path) as im:
            # Bestimmt Ausrichtung
            orientation = "landscape" if im.size[0] > im.size[1] else "portrait"
            temp_pdf = FPDF(orientation=orientation)
    except Exception as e:
        raise PDFExportError(f"Could not open image {image_path}: {str(e)}")

    try:
        temp_pdf.add_page()
        temp_pdf.set_draw_color(r=255, g=255, b=255)

        # Setzt Rechteck-Dimensionen basierend auf Ausrichtung
        if orientation == 'portrait':
            rect = 10, 10, 190, 277
        else:
            rect = 10, 10, 277, 190

        temp_pdf.rect(*rect)
        temp_pdf.image(
            image_path,
            *rect,
            keep_aspect_ratio=True
        )
        temp_pdf.output(output_path)

        return output_path
    except Exception as e:
        raise PDFExportError(f"Could not convert image to PDF: {str(e)}")


def create_outline_name(
    file_info: TableFileInfo,
    include_dates: bool = True,
) -> str:
    """
    Erstellt Gliederungs-(Lesezeichen-)Namen für eine Datei.

    Args:
        file_info: Dateiinformationsobjekt
        include_dates: Ob Datum im Namen eingeschlossen werden soll

    Returns:
        Formatierter Gliederungsname
    """
    # Verwendet Anzeigenamen falls verfügbar, sonst Klassenname, sonst Dateiname
    outline_name = file_info.filename

    if file_info.display_name and len(file_info.display_name.strip()) > 0:
        outline_name = file_info.display_name
    elif file_info.class_name and len(file_info.class_name.strip()) > 0:
        outline_name = file_info.class_name

    # Fügt Datum hinzu, falls angefordert
    if include_dates:
        # Priorität: date, filing_date, scan_date, received_date
        date_columns = [
            file_info.date,
            file_info.filing_date,
            file_info.scan_date,
            file_info.received_date,
        ]

        for date_val in date_columns:
            if date_val:
                outline_name += f" {date_val}"
                break

    return outline_name


def export_pdf(
    table_widget: QTableWidget,
    base_dir: str,
    export_filename: str,
    config: PDFExportConfig,
    favorites: Optional[List[FavoriteEntry]] = None,
    cover_page_creator: Optional[Callable[[str], str]] = None,
    status_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Tuple[bool, List[str]]:
    """
    Exportiert Dateien aus Tabellen-Widget in eine einzelne PDF-Datei.

    Diese Funktion kombiniert mehrere Dateien (PDFs, Bilder, Textdateien) in eine einzelne
    PDF-Datei mit optionalem Deckblatt und Lesezeichen.

    Args:
        table_widget: Qt-Tabellen-Widget mit Dateiinformationen
        base_dir: Basisverzeichnis, in dem sich die Quelldateien befinden
        export_filename: Pfad für die Ausgabe-PDF-Datei
        config: Export-Konfigurationsobjekt
        favorites: Liste favorisierter Dateinamen (für Gliederungsmarkierung)
        cover_page_creator: Optionaler Callback zum Erstellen des Deckblatt-PDFs
        status_callback: Optionaler Callback für Statusnachrichten
        progress_callback: Optionaler Callback für Fortschrittsaktualisierungen (aktuell, gesamt)

    Returns:
        Tupel aus (success: bool, not_supported: List[str])
        - success: True bei erfolgreichem Export
        - not_supported: Liste von Dateinamen, die nicht verarbeitet werden konnten

    Raises:
        PDFExportError: Falls Export kritisch fehlschlägt

    Beispiel:
        >>> config = PDFExportConfig(include_cover_page=True)
        >>> success, failed = export_pdf(
        ...     table_widget=my_table,
        ...     base_dir="/path/to/files",
        ...     export_filename="/path/to/output.pdf",
        ...     config=config,
        ...     favorites=["file1.pdf", "file2.pdf"],
        ... )
    """
    favorites = favorites or []
    not_supported = []

    # TODO (Version 1.5+): favorites_legacy und den Legacy-Zweig in der Schleife
    # entfernen, sobald alle FavoriteEntry-Objekte anzeigename != '' haben.
    # Dann nur noch favorites_by_pair für den Abgleich verwenden.
    favorites_by_pair: set = {(e.anzeigename, e.filename) for e in favorites if e.anzeigename}
    favorites_legacy: set = {e.filename for e in favorites if not e.anzeigename}

    # Verhindert doppelte Bookmark-Einträge, wenn dieselbe Datei mehrfach im
    # Datensatz referenziert wird (z. B. von Signaturdateien).
    favorites_in_outline: set = set()

    # Extract file information from table
    try:
        files_info = extract_files_from_table(
            table_widget,
            base_dir,
            favorites,
            config.include_favorites_only,
        )
    except PDFExportError as e:
        raise PDFExportError(f"Could not extract files from table: {str(e)}")

    if not files_info:
        return False, not_supported

    try:
        pdf = Pdf.new()
        page_count = 0
        file_count = 0

        # System-/tmp-Ordner nicht zugänglich für SNAP LibreOffice
        tmpdir = os.path.expanduser("~") if sys.platform.lower() == 'linux' else None

        with TemporaryDirectory(dir=tmpdir) as local_temp_dir:
            with pdf.open_outline() as outline:
                # Erstellt Favoriten-Bereich in Gliederung
                favorites_outline = OutlineItem('Favoriten')
                outline.root.append(favorites_outline)

                # Fügt Deckblatt hinzu, falls konfiguriert
                if config.include_cover_page and cover_page_creator:
                    cover_path = os.path.join(local_temp_dir, 'Deckblatt.pdf')
                    try:
                        attach_file = cover_page_creator(cover_path)
                        if attach_file and os.path.exists(attach_file):
                            with Pdf.open(attach_file) as src:
                                outline.root.append(OutlineItem('Deckblatt', 0))
                                page_count += len(src.pages)
                                pdf.pages.extend(src.pages)
                        else:
                            error_msg = f"Cover page file not created: {attach_file}"
                            print(f"ERROR: {error_msg}", file=sys.stderr)
                            if status_callback:
                                status_callback(error_msg)
                    except Exception as e:
                        error_msg = f"Cover page creation failed: {str(e)}"
                        print(f"ERROR: {error_msg}", file=sys.stderr)
                        print(traceback.format_exc(), file=sys.stderr)
                        if status_callback:
                            status_callback(error_msg)

                # Verarbeitet jede Datei
                for idx, file_info in enumerate(files_info):
                    if progress_callback:
                        progress_callback(idx + 1, len(files_info))

                    if status_callback:
                        status_callback(f'Processing: {file_info.filename}')

                    file_path = os.path.join(base_dir, file_info.filename)
                    attach_file = None

                    # Konvertiert verschiedene Dateitypen nach PDF
                    if file_info.filename.lower().endswith(('.xml', '.csv', '.txt')):
                        # Textdateien
                        try:
                            orientation = "landscape" if file_info.filename.lower().endswith('.csv') else "portrait"
                            temp_pdf_file = os.path.join(local_temp_dir, file_info.filename + '.pdf')
                            attach_file = convert_text_file_to_pdf(
                                file_path,
                                temp_pdf_file,
                                config.font_dir,
                                orientation,
                            )
                        except PDFExportError:
                            not_supported.append(file_info.filename)
                            continue

                    elif file_info.filename.lower().endswith(('.jpg', '.jpeg', '.tiff', '.tif', '.png')):
                        # Bilddateien
                        try:
                            temp_pdf_file = os.path.join(local_temp_dir, file_info.filename + '.pdf')
                            attach_file = convert_image_to_pdf(
                                file_path,
                                temp_pdf_file,
                            )
                        except PDFExportError:
                            not_supported.append(file_info.filename)
                            continue

                    elif file_info.filename.lower().endswith('.pdf'):
                        # Native PDF-Dateien
                        try:
                            # Versucht zu öffnen, um zu prüfen, dass nicht verschlüsselt
                            with Pdf.open(file_path) as src:
                                pass
                            attach_file = file_path
                        except Exception:
                            not_supported.append(file_info.filename)
                            continue

                    else:
                        # Prüft auf vorgenerierte PDF-Vorschau
                        preview_path = os.path.join(base_dir, file_info.filename + '.pdf')
                        if os.path.exists(preview_path):
                            attach_file = preview_path
                        else:
                            if not file_info.filename.lower().endswith(('.pkcs7', '.p7s', '.pks')):
                                not_supported.append(file_info.filename)
                            continue

                    # Hängt Datei an PDF an
                    if attach_file:
                        # Erstellt Gliederungseintrag
                        outline_name = create_outline_name(
                            file_info,
                            config.include_file_dates,
                        )

                        outline_item = OutlineItem(outline_name, page_count)

                        # Prüft, ob diese Datei einem Favoriten-Eintrag entspricht.
                        # TODO (Version 1.5+): Den `or file_info.filename in favorites_legacy`-
                        # Zweig entfernen, sobald keine Legacy-Einträge (anzeigename='') mehr
                        # vorkommen. Dann nur noch favorites_by_pair prüfen.
                        display = file_info.display_name or ''
                        is_favorite = (
                            (display, file_info.filename) in favorites_by_pair
                            or file_info.filename in favorites_legacy
                        )
                        fav_key = (display, file_info.filename)

                        if is_favorite and fav_key not in favorites_in_outline:
                            favorites_outline.children.append(outline_item)
                            favorites_in_outline.add(fav_key)

                        outline.root.append(outline_item)

                        # Fügt Seiten hinzu
                        with Pdf.open(attach_file) as src:
                            page_count += len(src.pages)
                            pdf.pages.extend(src.pages)

                        file_count += 1

                # Entfernt Favoriten-Bereich, falls leer oder nicht konfiguriert
                if not config.include_favorites_section or len(favorites_outline.children) == 0:
                    outline.root.remove(favorites_outline)

            # Speichert PDF, falls Dateien hinzugefügt wurden
            if file_count > 0:
                if status_callback:
                    status_callback(f'Saving PDF file: {export_filename}')
                pdf.save(export_filename)
                return True, not_supported
            else:
                return False, not_supported

    except Exception as e:
        raise PDFExportError(f"PDF export failed: {str(e)}")


def export_notes_to_pdf(
    notes_text: str,
    export_filename: str,
    font_dir: str,
    title: Optional[str] = None,
) -> None:
    """
    Exportiert Notizentext in eine PDF-Datei.

    Args:
        notes_text: Klartext-Inhalt der Notizen
        export_filename: Pfad für die Ausgabe-PDF-Datei
        font_dir: Verzeichnis mit Ubuntu-Schriftarten
        title: Optionaler Titel für die PDF (Standard ist Dateiname-Stamm)

    Raises:
        PDFExportError: Falls Export fehlschlägt

    Beispiel:
        >>> export_notes_to_pdf(
        ...     notes_text="My important notes",
        ...     export_filename="/path/to/notes.pdf",
        ...     font_dir="/path/to/fonts",
        ...     title="Case Notes",
        ... )
    """
    if not notes_text:
        raise PDFExportError("No notes text provided for export")

    # Verwendet Dateiname-Stamm als Titel, falls nicht angegeben
    if title is None:
        title = Path(export_filename).stem

    try:
        pdf = FPDF()

        # Fügt Ubuntu-Schriftfamilie hinzu
        ubuntu_font_path = os.path.join(font_dir, 'ubuntu-font-family-0.83')
        pdf.add_font("Ubuntu", style="", fname=f"{ubuntu_font_path}/Ubuntu-R.ttf")
        pdf.add_font("Ubuntu", style="b", fname=f"{ubuntu_font_path}/Ubuntu-B.ttf")
        pdf.add_font("Ubuntu", style="i", fname=f"{ubuntu_font_path}/Ubuntu-RI.ttf")
        pdf.add_font("Ubuntu", style="bi", fname=f"{ubuntu_font_path}/Ubuntu-BI.ttf")

        pdf.add_page()

        # Fügt Titel hinzu
        pdf.set_font("Ubuntu", style='b', size=20)
        pdf.multi_cell(
            w=0,
            text=title,
            padding=(0, 0, 5),
            new_x='LEFT',
            new_y='NEXT'
        )

        # Fügt Notizen-Inhalt hinzu (unterstützt Markdown)
        pdf.set_font("Ubuntu", style='', size=12)
        pdf.multi_cell(w=0, text=notes_text, markdown=True)

        pdf.output(export_filename)

    except Exception as e:
        raise PDFExportError(f"Saving notes failed: {str(e)}")


# print_pdf_worker removed - printing is handled by pdfjs_viewer


def validate_pdf_file(pdf_path: Path) -> bool:
    """
    Validiert, dass eine PDF-Datei existiert und geöffnet werden kann.

    Args:
        pdf_path: Pfad zur PDF-Datei

    Returns:
        True, falls PDF gültig und zugänglich ist, sonst False
    """
    try:
        with Pdf.open(pdf_path) as pdf:
            return True
    except Exception:
        return False


def get_pdf_page_count(pdf_path: Path) -> int:
    """
    Ruft die Anzahl der Seiten in einer PDF-Datei ab.

    Args:
        pdf_path: Pfad zur PDF-Datei

    Returns:
        Anzahl der Seiten in der PDF

    Raises:
        PDFExportError: Falls PDF nicht geöffnet werden kann
    """
    try:
        with Pdf.open(pdf_path) as pdf:
            return len(pdf.pages)
    except Exception as e:
        raise PDFExportError(f"Could not read PDF: {str(e)}")


# Example usage and testing
if __name__ == '__main__':
    # Beispiel: Export notes to PDF
    try:
        export_notes_to_pdf(
            notes_text="This is a test note.\n\nWith multiple paragraphs.",
            export_filename="/tmp/test_notes.pdf",
            font_dir="/path/to/fonts",
            title="Test Notes",
        )
        print("Notes exported successfully")
    except PDFExportError as e:
        print(f"Export failed: {e}")

    # Beispiel: Validate PDF
    pdf_valid = validate_pdf_file(Path("/tmp/test_notes.pdf"))
    print(f"PDF valid: {pdf_valid}")

    # Beispiel: Get page count
    try:
        page_count = get_pdf_page_count(Path("/tmp/test_notes.pdf"))
        print(f"PDF has {page_count} pages")
    except PDFExportError as e:
        print(f"Could not get page count: {e}")
