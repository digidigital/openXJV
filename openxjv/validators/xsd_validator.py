#!/usr/bin/env python3
# coding: utf-8
"""XSD-Validierungslogik fuer XJustiz-XML-Dateien.

Stellt die Klasse XSDValidator bereit, die XML-Dateien gegen
XSD-Schemata validiert und das passende Schema automatisch erkennt.
"""

import os
import re
import glob
import time
from typing import Optional, List
from dataclasses import dataclass, field
from lxml import etree
from lxml.etree import XMLSyntaxError, XMLSchemaParseError


@dataclass
class ValidationError:
    """Einzelner Validierungsfehler mit strukturierten Feldern."""
    line: int
    column: int
    message: str
    type_name: str = ""
    filename: str = ""


@dataclass
class ValidationResult:
    """Ergebnis einer XSD-Validierung."""
    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    error_count: int = 0
    elapsed_seconds: float = 0.0
    xml_path: str = ""
    xsd_path: str = ""
    summary_text: str = ""


class XSDValidator:
    """Validiert XJustiz-XML-Dateien gegen XSD-Schemata.

    Stellt statische Methoden zur Schema-Erkennung und eine
    Instanzmethode zur Validierung bereit.
    """

    @staticmethod
    def find_schema_folder(app_base_path: str, version: str) -> Optional[str]:
        """Sucht den Schema-Ordner passend zur XJustiz-Version.

        Scannt das Verzeichnis ``schemata/`` unterhalb von *app_base_path*
        nach Ordnern im Format ``XJustiz_X_Y_Z_XSD`` und gibt den Pfad
        zum enthaltenen ``XJustiz_XSD``-Unterordner zurueck.

        Args:
            app_base_path: Basisverzeichnis der Anwendung.
            version: XJustiz-Version als String, z.B. ``"3.6.2"``.

        Returns:
            Pfad zum ``XJustiz_XSD``-Ordner oder ``None``.
        """
        schemata_dir = os.path.join(app_base_path, 'schemata')
        if not os.path.isdir(schemata_dir):
            return None

        # Version "3.6.2" -> Ordnername "XJustiz_3_6_2_XSD"
        version_underscored = version.replace('.', '_')
        target_name = f'XJustiz_{version_underscored}_XSD'

        # Direkter Treffer
        candidate = os.path.join(schemata_dir, target_name, 'XJustiz_XSD')
        if os.path.isdir(candidate):
            return candidate

        # Fallback: Alle Ordner scannen und Version vergleichen
        pattern = os.path.join(schemata_dir, 'XJustiz_*_XSD')
        for folder in sorted(glob.glob(pattern)):
            folder_name = os.path.basename(folder)
            match = re.match(r'XJustiz_(\d+_\d+_\d+)_XSD', folder_name)
            if match:
                folder_version = match.group(1).replace('_', '.')
                if folder_version == version:
                    xsd_subdir = os.path.join(folder, 'XJustiz_XSD')
                    if os.path.isdir(xsd_subdir):
                        return xsd_subdir

        return None

    @staticmethod
    def find_nachrichten_xsd(schema_folder: str) -> Optional[str]:
        """Findet die Haupt-Nachrichten-XSD im Schema-Ordner.

        Sucht nach ``xjustiz_0005_nachrichten_*.xsd`` im angegebenen Ordner.

        Args:
            schema_folder: Pfad zum ``XJustiz_XSD``-Unterordner.

        Returns:
            Vollstaendiger Pfad zur Nachrichten-XSD oder ``None``.
        """
        pattern = os.path.join(schema_folder, 'xjustiz_0005_nachrichten_*.xsd')
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
        return None

    def validate(self, xml_path: str, xsd_path: str) -> ValidationResult:
        """Validiert eine XML-Datei gegen ein XSD-Schema.

        Verwendet einen sicheren Parser (kein Netzwerkzugriff, keine
        Entity-Aufloesung) und gibt strukturierte Fehler zurueck.
        XSD-interne Referenzen (``xs:import``, ``xs:include``) werden
        von lxml automatisch relativ zur XSD-Datei aufgeloest.

        Args:
            xml_path: Pfad zur XML-Datei.
            xsd_path: Pfad zur Haupt-XSD-Datei.

        Returns:
            ``ValidationResult`` mit Ergebnis, Fehlerliste und Laufzeit.
        """
        start_time = time.monotonic()
        errors: List[ValidationError] = []
        is_valid = False

        try:
            # Dateien pruefen
            if not os.path.isfile(xml_path):
                errors.append(ValidationError(
                    line=0, column=0,
                    message=f"XML-Datei nicht gefunden: {xml_path}",
                    type_name="FILE_NOT_FOUND"
                ))
                return self._build_result(False, errors, start_time, xml_path, xsd_path)

            if not os.path.isfile(xsd_path):
                errors.append(ValidationError(
                    line=0, column=0,
                    message=f"XSD-Datei nicht gefunden: {xsd_path}",
                    type_name="FILE_NOT_FOUND"
                ))
                return self._build_result(False, errors, start_time, xml_path, xsd_path)

            # Sicherer Parser: kein Netzwerk, keine Entity-Aufloesung (XXE-Schutz)
            parser = etree.XMLParser(
                no_network=True,
                resolve_entities=False
            )

            # XSD einlesen
            try:
                with open(xsd_path, 'rb') as f:
                    schema_doc = etree.parse(f, parser)
            except XMLSyntaxError as e:
                errors.append(ValidationError(
                    line=0, column=0,
                    message=f"XSD-Syntaxfehler in {os.path.basename(xsd_path)}: {e}",
                    type_name="XSD_SYNTAX_ERROR"
                ))
                return self._build_result(False, errors, start_time, xml_path, xsd_path)
            except (FileNotFoundError, OSError) as e:
                errors.append(ValidationError(
                    line=0, column=0,
                    message=f"Fehler beim Lesen der XSD-Datei: {e}",
                    type_name="IO_ERROR"
                ))
                return self._build_result(False, errors, start_time, xml_path, xsd_path)

            # XMLSchema-Objekt erstellen
            try:
                schema = etree.XMLSchema(schema_doc)
            except XMLSchemaParseError as e:
                errors.append(ValidationError(
                    line=0, column=0,
                    message=f"XSD-Schema konnte nicht geladen werden: {e}",
                    type_name="SCHEMA_PARSE_ERROR"
                ))
                return self._build_result(False, errors, start_time, xml_path, xsd_path)

            # XML einlesen
            try:
                xml_tree = etree.parse(xml_path, parser)
            except XMLSyntaxError as e:
                errors.append(ValidationError(
                    line=0, column=0,
                    message=f"XML-Syntaxfehler in {os.path.basename(xml_path)}: {e}",
                    type_name="XML_SYNTAX_ERROR"
                ))
                return self._build_result(False, errors, start_time, xml_path, xsd_path)
            except (FileNotFoundError, OSError) as e:
                errors.append(ValidationError(
                    line=0, column=0,
                    message=f"Fehler beim Lesen der XML-Datei: {e}",
                    type_name="IO_ERROR"
                ))
                return self._build_result(False, errors, start_time, xml_path, xsd_path)

            # Validierung durchfuehren
            is_valid = schema.validate(xml_tree)

            # Fehler strukturiert auslesen
            if schema.error_log:
                for entry in schema.error_log:
                    errors.append(ValidationError(
                        line=entry.line,
                        column=entry.column,
                        message=entry.message,
                        type_name=entry.type_name or "",
                        filename=entry.filename or ""
                    ))

            if not is_valid and not errors:
                errors.append(ValidationError(
                    line=0, column=0,
                    message="Validierung fehlgeschlagen, aber keine detaillierten Fehler verfuegbar.",
                    type_name="UNKNOWN"
                ))

        except Exception as e:
            errors.append(ValidationError(
                line=0, column=0,
                message=f"Unerwarteter Fehler: {type(e).__name__}: {e}",
                type_name="UNEXPECTED"
            ))
            is_valid = False

        return self._build_result(is_valid, errors, start_time, xml_path, xsd_path)

    def _build_result(
        self,
        is_valid: bool,
        errors: List[ValidationError],
        start_time: float,
        xml_path: str,
        xsd_path: str
    ) -> ValidationResult:
        """Erstellt ein ValidationResult mit formatierter Zusammenfassung."""
        elapsed = time.monotonic() - start_time
        summary = self._format_summary(is_valid, errors, elapsed, xml_path, xsd_path)
        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            error_count=len(errors),
            elapsed_seconds=elapsed,
            xml_path=xml_path,
            xsd_path=xsd_path,
            summary_text=summary
        )

    @staticmethod
    def _format_summary(
        is_valid: bool,
        errors: List[ValidationError],
        elapsed: float,
        xml_path: str,
        xsd_path: str
    ) -> str:
        """Formatiert das Validierungsergebnis als lesbaren Text."""
        lines = []
        lines.append(f"XML-Datei:  {xml_path}")
        lines.append(f"XSD-Schema: {xsd_path}")
        lines.append("")

        if is_valid:
            lines.append("Ergebnis: XML ist GUELTIG.")
        else:
            lines.append("Ergebnis: XML ist NICHT gueltig.")

        lines.append(f"Anzahl Fehler: {len(errors)}")
        lines.append(f"Validierungsdauer: {elapsed:.2f} Sekunden")
        lines.append("")
        lines.append("=" * 60)
        lines.append("")

        for i, err in enumerate(errors, 1):
            lines.append(f"Fehler {i}:")
            if err.line > 0:
                lines.append(f"  Zeile {err.line}, Spalte {err.column}")
            if err.type_name:
                lines.append(f"  Fehlertyp: {err.type_name}")
            lines.append(f"  Meldung: {err.message}")
            lines.append("-" * 60)
            lines.append("")

        return "\n".join(lines)
