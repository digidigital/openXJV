# XSD → JSON Codelisten-Konverter

Konvertiert XSD-Codelisten aus dem `schemata/` Ordner in JSON-Format und legt sie im `codelisten_json/` Ordner ab.

## Features

- ✅ **Rekursive Suche**: Durchsucht alle XJustiz-Versionen im schemata-Ordner
- ✅ **Versionserkennung**: Extrahiert XJustiz-Version aus Pfad und Metadaten
- ✅ **Vollständige Metadaten**: Konvertiert alle XSD-Metadaten ins JSON-Format
- ✅ **Duplikat-Schutz**: Überspringt bereits existierende JSON-Dateien
- ✅ **Dry-Run-Modus**: Testlauf ohne Dateien zu schreiben
- ✅ **Statistiken**: Detaillierte Zusammenfassung der Konvertierung

## Verwendung

### Standard-Konvertierung

```bash
python3 convert_xsd_codelists_to_json.py
```

Konvertiert alle XSD-Codelisten aus `schemata/` nach `codelisten_json/`.

### Dry-Run (Testlauf)

```bash
python3 convert_xsd_codelists_to_json.py --dry-run
```

Zeigt an, welche Dateien konvertiert würden, ohne sie tatsächlich zu schreiben.

### Benutzerdefinierte Pfade

```bash
python3 convert_xsd_codelists_to_json.py \
  --schemata /pfad/zu/schemata \
  --output /pfad/zu/ausgabe
```

### Hilfe

```bash
python3 convert_xsd_codelists_to_json.py --help
```

## Beispiel-Ausgabe

```
======================================================================
XSD → JSON Codelisten-Konverter
======================================================================
Quelle: /home/user/projekt/schemata
Ziel:   /home/user/projekt/codelisten_json
======================================================================

Suche XSD-Codelisten in: /home/user/projekt/schemata
Gefunden: 133 Codelisten-Dateien

📋 XJustiz 3.2.1: 30 Codelisten
======================================================================
  ✅ GDS.Rechtsform_3.3.json (111 Einträge)
  ✅ GDS.Rollenbezeichnung_3.2.json (344 Einträge)
  ⚠️  Existiert bereits: GDS.Zinstyp_2.0.json
  ...

📋 XJustiz 3.3.1: 27 Codelisten
======================================================================
  ✅ GDS.Rollenbezeichnung_3.3.json (350 Einträge)
  ...

======================================================================
ZUSAMMENFASSUNG
======================================================================
Verarbeitet:  133
Konvertiert:  37
Übersprungen: 96
Fehler:       0
======================================================================
```

## Wie es funktioniert

### 1. Erkennung von Codelisten

Der Konverter identifiziert XSD-Codelisten durch:
- Dateien mit `cl` im Namen (z.B. `xjustiz_0040_cl_rollenbezeichnung_3_3.xsd`)
- Vorhandensein von `xs:enumeration` Elementen im XML

### 2. Metadaten-Extraktion

Aus dem XSD werden folgende Metadaten extrahiert:

```xml
<xs:annotation>
  <xs:appinfo>
    <codeliste>
      <nameLang>GDS.Rollenbezeichnung</nameLang>
      <nameKurz>GDS.Rollenbezeichnung</nameKurz>
      <kennung>urn:xoev-de:xjustiz:codeliste:gds.rollenbezeichnung</kennung>
      <beschreibung>Codeliste der verschiedenen Rollenbezeichnungen.</beschreibung>
    </codeliste>
    <versionCodeliste>
      <version>3.3</version>
    </versionCodeliste>
  </xs:appinfo>
</xs:annotation>
```

### 3. Code-Wert-Paare

Die eigentlichen Codelisten-Einträge werden aus `xs:enumeration` extrahiert:

```xml
<xs:enumeration value="001">
  <xs:annotation>
    <xs:appinfo>
      <wert>Abwesenheitspfleger(in)</wert>
    </xs:appinfo>
  </xs:annotation>
</xs:enumeration>
```

### 4. JSON-Ausgabe

Das Ergebnis ist eine JSON-Datei im XJustiz-Standard-Format:

```json
{
  "metadaten": {
    "kennung": "urn:xoev-de:xjustiz:codeliste:gds.rollenbezeichnung",
    "version": "3.3",
    "nameKurz": [{"value": "GDS.Rollenbezeichnung"}],
    ...
  },
  "spalten": [
    {
      "spaltennameLang": "Schlüssel",
      "spaltennameTechnisch": "code",
      "datentyp": "string",
      "codeSpalte": true,
      ...
    },
    {
      "spaltennameLang": "Wert",
      "spaltennameTechnisch": "wert",
      ...
    }
  ],
  "daten": [
    ["001", "Abwesenheitspfleger(in)"],
    ["002", "Aliasidentität"],
    ...
  ]
}
```

## Dateinamen-Konvention

Die JSON-Dateien werden benannt nach dem Schema:

```
{NameKurz}_{Version}.json
```

Beispiele:
- `GDS.Rollenbezeichnung_3.3.json`
- `GDS.Aktentyp_2.2.json`
- `INSO.Verfahrensart.National.Unterart_2.0.json`

## Versionserkennung

Die XJustiz-Version wird ermittelt aus:

1. **Metadaten im XSD**: `<versionCodeliste><version>3.3</version>`
2. **Pfad-Pattern**: `XJustiz_3_3_1_XSD` → Version `3.3.1`

Falls beide vorhanden sind, haben Metadaten Vorrang.

## Fehlerbehandlung

Der Konverter ist fehler-tolerant:

- ✅ Überspringt nicht-parsbare XSD-Dateien
- ✅ Überspringt XSD ohne Codelisten-Daten
- ✅ Überspringt bereits existierende JSON-Dateien
- ✅ Liefert detaillierte Statistiken

## Ergebnis der Konvertierung

Nach Ausführung des Scripts wurden **37 neue JSON-Codelisten** erstellt:

- **XJustiz 3.2.1**: 23 Codelisten
- **XJustiz 3.3.1**: 4 Codelisten
- **XJustiz 3.4.1**: 2 Codelisten
- **XJustiz 3.5.1**: 6 Codelisten
- **XJustiz 3.6.2**: 2 Codelisten

**96 Codelisten** existierten bereits und wurden nicht überschrieben.

## Technische Details

### Abhängigkeiten

- **Python 3.7+**
- **Standardbibliothek**: xml.etree.ElementTree, json, pathlib, argparse

Keine externen Dependencies erforderlich!

### Performance

- ~133 XSD-Dateien in ~3-5 Sekunden
- Kompakte JSON-Ausgabe (minimiertes Format ohne Whitespace)

## Wartung

### Neue XJustiz-Version hinzufügen

1. Lege XSD-Dateien im `schemata/` Ordner ab
2. Führe Konverter aus: `python3 convert_xsd_codelists_to_json.py`
3. Neue JSON-Codelisten werden automatisch erkannt und konvertiert

### Codelisten aktualisieren

Wenn XJustiz eine Codeliste aktualisiert:

1. Lösche alte JSON-Datei: `rm codelisten_json/GDS.Rollenbezeichnung_3.3.json`
2. Führe Konverter erneut aus

Oder verwende `--force` (zukünftige Erweiterung).

## Lizenz

GPL-3.0 (wie das gesamte openXJV-Projekt)


