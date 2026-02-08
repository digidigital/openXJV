#!/usr/bin/env python3
# coding: utf-8
"""
XSD Codelisten → JSON Konverter

Konvertiert alle XSD-Codelisten aus dem schemata-Ordner in JSON-Format
und legt sie im codelisten_json-Ordner ab.

Die Versionsnummer wird aus dem XSD extrahiert und im Dateinamen verwendet.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import xml.etree.ElementTree as ET


class XSDCodelistConverter:
    """Konvertiert XSD-Codelisten in JSON-Format."""

    # XML Namespaces
    NS = {
        'xs': 'http://www.w3.org/2001/XMLSchema',
        'tns': 'http://www.xjustiz.de'
    }

    def __init__(self, schemata_root: Path, output_dir: Path):
        """
        Initialisiert den Konverter.

        Args:
            schemata_root: Root-Verzeichnis mit XJustiz-Schemata
            output_dir: Zielverzeichnis für JSON-Dateien
        """
        self.schemata_root = Path(schemata_root)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        self.stats = {
            'processed': 0,
            'converted': 0,
            'skipped': 0,
            'errors': 0
        }

    def find_codelist_files(self) -> List[Path]:
        """
        Findet alle XSD-Codelisten-Dateien rekursiv.

        Returns:
            Liste von Pfaden zu XSD-Codelisten-Dateien
        """
        # Suche nach Dateien mit "cl" im Namen (Codelist-Indikator)
        files = list(self.schemata_root.rglob('*cl*.xsd'))

        # Filtere nur echte Codelisten (die xs:enumeration enthalten)
        codelist_files = []
        for file in files:
            try:
                tree = ET.parse(file)
                root = tree.getroot()
                # Prüfe ob Datei xs:enumeration enthält (Indikator für Codeliste)
                if root.findall('.//xs:enumeration', self.NS):
                    codelist_files.append(file)
            except Exception:
                continue

        return sorted(codelist_files)

    def extract_xjustiz_version(self, file_path: Path) -> Optional[str]:
        """
        Extrahiert XJustiz-Version aus Pfad.

        Args:
            file_path: Pfad zur XSD-Datei

        Returns:
            Versionsnummer (z.B. "3.3.1") oder None
        """
        # Suche nach Pattern wie "XJustiz_3_3_1_XSD" im Pfad
        match = re.search(r'XJustiz_(\d+)_(\d+)_(\d+)_XSD', str(file_path))
        if match:
            return f"{match.group(1)}.{match.group(2)}.{match.group(3)}"

        return None

    def extract_metadata(self, root: ET.Element) -> Dict:
        """
        Extrahiert Metadaten aus XSD.

        Args:
            root: XML Root-Element

        Returns:
            Dictionary mit Metadaten
        """
        metadata = {
            'kennung': '',
            'kennungInhalt': '',
            'version': '',
            'nameKurz': [],
            'nameLang': [],
            'nameTechnisch': '',
            'herausgebernameLang': [],
            'herausgebernameKurz': [],
            'beschreibung': [],
            'versionBeschreibung': [],
            'aenderungZurVorversion': [],
            'handbuchVersion': '',
            'xoevHandbuch': False,
            'gueltigAb': '',
            'bezugsorte': []
        }

        # Suche Codelisten-Metadaten im appinfo
        for appinfo in root.findall('.//xs:annotation/xs:appinfo', self.NS):
            # Codelisten-Info
            codeliste = appinfo.find('codeliste')
            if codeliste is not None:
                name_lang = codeliste.findtext('nameLang', '')
                name_kurz = codeliste.findtext('nameKurz', '')
                name_technisch = codeliste.findtext('nameTechnisch', '')
                kennung = codeliste.findtext('kennung', '')
                beschreibung = codeliste.findtext('beschreibung', '')
                herausgeber_lang = codeliste.findtext('herausgebernameLang', '')
                herausgeber_kurz = codeliste.findtext('herausgebernameKurz', '')

                if name_lang:
                    metadata['nameLang'] = [{'value': name_lang}]
                if name_kurz:
                    metadata['nameKurz'] = [{'value': name_kurz}]
                if name_technisch:
                    metadata['nameTechnisch'] = name_technisch
                if kennung:
                    metadata['kennung'] = kennung
                    metadata['kennungInhalt'] = kennung
                if beschreibung:
                    metadata['beschreibung'] = [{'value': beschreibung}]
                    metadata['versionBeschreibung'] = [{'value': beschreibung}]
                if herausgeber_lang:
                    metadata['herausgebernameLang'] = [{'value': herausgeber_lang}]
                if herausgeber_kurz:
                    metadata['herausgebernameKurz'] = [{'value': herausgeber_kurz}]

            # Versions-Info
            version_codeliste = appinfo.find('versionCodeliste')
            if version_codeliste is not None:
                version = version_codeliste.findtext('version', '')
                handbuch_version = version_codeliste.findtext('versionCodelistenHandbuch', '')

                if version:
                    metadata['version'] = version
                if handbuch_version:
                    metadata['handbuchVersion'] = handbuch_version

        return metadata

    def extract_columns(self, root: ET.Element) -> List[Dict]:
        """
        Extrahiert Spaltendefinitionen.

        Args:
            root: XML Root-Element

        Returns:
            Liste von Spaltendefinitionen
        """
        columns = []

        # Suche codelistenspalten
        for appinfo in root.findall('.//xs:annotation/xs:appinfo', self.NS):
            spalten_elem = appinfo.find('codelistenspalten')
            if spalten_elem is not None:
                # Code-Spalte
                code_elem = spalten_elem.find('code')
                if code_elem is not None:
                    columns.append({
                        'spaltennameLang': code_elem.findtext('spaltennameLang', 'Schlüssel'),
                        'spaltennameTechnisch': 'code',
                        'datentyp': code_elem.findtext('datentyp', 'string'),
                        'codeSpalte': True,
                        'verwendung': code_elem.findtext('verwendung', 'required'),
                        'empfohleneCodeSpalte': True
                    })

                # Wert-Spalte
                wert_elem = spalten_elem.find('wert')
                if wert_elem is not None:
                    columns.append({
                        'spaltennameLang': wert_elem.findtext('spaltennameLang', 'Wert'),
                        'spaltennameTechnisch': 'wert',
                        'datentyp': wert_elem.findtext('datentyp', 'string'),
                        'codeSpalte': False,
                        'verwendung': wert_elem.findtext('verwendung', 'required'),
                        'empfohleneCodeSpalte': False
                    })

        # Fallback wenn keine Spalten definiert
        if not columns:
            columns = [
                {
                    'spaltennameLang': 'Schlüssel',
                    'spaltennameTechnisch': 'code',
                    'datentyp': 'string',
                    'codeSpalte': True,
                    'verwendung': 'required',
                    'empfohleneCodeSpalte': True
                },
                {
                    'spaltennameLang': 'Wert',
                    'spaltennameTechnisch': 'wert',
                    'datentyp': 'string',
                    'codeSpalte': False,
                    'verwendung': 'required',
                    'empfohleneCodeSpalte': False
                }
            ]

        return columns

    def extract_data(self, root: ET.Element) -> List[List[str]]:
        """
        Extrahiert Code-Wert-Paare aus xs:enumeration-Elementen.

        Args:
            root: XML Root-Element

        Returns:
            Liste von [code, wert] Paaren
        """
        data = []

        # Finde alle xs:enumeration Elemente
        for enum in root.findall('.//xs:enumeration', self.NS):
            code = enum.get('value', '')

            # Extrahiere Wert aus appinfo
            wert = ''
            appinfo = enum.find('xs:annotation/xs:appinfo', self.NS)
            if appinfo is not None:
                wert_elem = appinfo.find('wert')
                if wert_elem is not None:
                    wert = wert_elem.text or ''

            if code:
                data.append([code, wert])

        return data

    def convert_xsd_to_json(self, xsd_file: Path) -> Optional[Tuple[str, Dict]]:
        """
        Konvertiert eine XSD-Codeliste in JSON-Format.

        Args:
            xsd_file: Pfad zur XSD-Datei

        Returns:
            Tuple (dateiname, json_data) oder None bei Fehler
        """
        try:
            tree = ET.parse(xsd_file)
            root = tree.getroot()

            # Extrahiere Komponenten
            metadata = self.extract_metadata(root)
            columns = self.extract_columns(root)
            data = self.extract_data(root)

            # Prüfe ob Daten vorhanden
            if not data:
                return None

            # Bestimme Dateinamen
            name_kurz = metadata['nameKurz'][0]['value'] if metadata['nameKurz'] else 'Unknown'
            version = metadata['version']

            # Falls keine Version in Metadaten, versuche aus Pfad zu extrahieren
            if not version:
                xjustiz_version = self.extract_xjustiz_version(xsd_file)
                if xjustiz_version:
                    version = xjustiz_version

            filename = f"{name_kurz}_{version}.json" if version else f"{name_kurz}.json"

            # Baue JSON-Struktur
            json_data = {
                'metadaten': metadata,
                'spalten': columns,
                'daten': data
            }

            return filename, json_data

        except Exception as e:
            print(f"  ❌ Fehler bei {xsd_file.name}: {e}")
            return None

    def convert_all(self, dry_run: bool = False) -> None:
        """
        Konvertiert alle gefundenen XSD-Codelisten.

        Args:
            dry_run: Wenn True, werden keine Dateien geschrieben
        """
        print(f"Suche XSD-Codelisten in: {self.schemata_root}")
        codelist_files = self.find_codelist_files()

        print(f"Gefunden: {len(codelist_files)} Codelisten-Dateien\n")

        if not codelist_files:
            print("⚠️  Keine Codelisten gefunden!")
            return

        # Gruppiere nach XJustiz-Version
        by_version = {}
        for file in codelist_files:
            version = self.extract_xjustiz_version(file)
            if version not in by_version:
                by_version[version] = []
            by_version[version].append(file)

        # Verarbeite jede Version
        for version in sorted(by_version.keys(), key=lambda x: (x is None, x)):
            version_label = version if version else "Unbekannt"
            files = by_version[version]

            print(f"📋 XJustiz {version_label}: {len(files)} Codelisten")
            print("=" * 70)

            for xsd_file in files:
                self.stats['processed'] += 1

                result = self.convert_xsd_to_json(xsd_file)
                if result is None:
                    self.stats['skipped'] += 1
                    print(f"  ⏭️  Übersprungen: {xsd_file.name}")
                    continue

                filename, json_data = result
                output_file = self.output_dir / filename

                # Prüfe ob Datei bereits existiert
                if output_file.exists():
                    print(f"  ⚠️  Existiert bereits: {filename}")
                    self.stats['skipped'] += 1
                    continue

                if not dry_run:
                    # Schreibe JSON-Datei
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(json_data, f, ensure_ascii=False, separators=(',', ':'))

                    print(f"  ✅ {filename} ({len(json_data['daten'])} Einträge)")
                    self.stats['converted'] += 1
                else:
                    print(f"  🔍 [DRY-RUN] {filename} ({len(json_data['daten'])} Einträge)")
                    self.stats['converted'] += 1

            print()

    def print_summary(self) -> None:
        """Gibt Zusammenfassung aus."""
        print("=" * 70)
        print("ZUSAMMENFASSUNG")
        print("=" * 70)
        print(f"Verarbeitet:  {self.stats['processed']}")
        print(f"Konvertiert:  {self.stats['converted']}")
        print(f"Übersprungen: {self.stats['skipped']}")
        print(f"Fehler:       {self.stats['errors']}")
        print("=" * 70)


def main():
    """Hauptfunktion."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Konvertiert XSD-Codelisten in JSON-Format'
    )
    parser.add_argument(
        '--schemata',
        type=Path,
        default=Path(__file__).parent / 'schemata',
        help='Pfad zum schemata-Ordner (default: ./schemata)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path(__file__).parent / 'codelisten_json',
        help='Pfad zum Ausgabe-Ordner (default: ./codelisten_json)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Testlauf ohne Dateien zu schreiben'
    )

    args = parser.parse_args()

    # Validierung
    if not args.schemata.exists():
        print(f"❌ Fehler: Schemata-Ordner nicht gefunden: {args.schemata}")
        return 1

    print("=" * 70)
    print("XSD → JSON Codelisten-Konverter")
    print("=" * 70)
    print(f"Quelle: {args.schemata}")
    print(f"Ziel:   {args.output}")
    if args.dry_run:
        print("Modus:  🔍 DRY-RUN (keine Dateien werden geschrieben)")
    print("=" * 70)
    print()

    # Konvertierung
    converter = XSDCodelistConverter(args.schemata, args.output)
    converter.convert_all(dry_run=args.dry_run)
    converter.print_summary()

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
