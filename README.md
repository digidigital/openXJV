# openXJV
Viewer for XJustiz files used for file / data transfers between courts, lawyers, agencies, etc. in  Germany's ERV-System

openXJV ist ein **kostenloses Anzeigeprogramm für XJustiz-Dateien (XJustiz Viewer)**, die im Rahmen des elektronischen Rechtsverkehrs (ERV) bei der Übertragung von Dokumenten Verwendung finden.

Dies ist z. B. **für die Akteneinsicht in Akten der Bundesanstalt für Arbeit (BA)** relevant, 
  da diese auf elektronischem Wege lediglich Einzeldateien mit einem begleitenden XJustiz-Datensatz übermittelt.   Erst das Auslesen des Datensatzes erzeugt aus der übermittelten "Dateisammlung" wieder eine sinnvolle Aktendarstellung.

**Es eignet sich auch zur Anzeige beliebiger XJustiz-Datensätze der "Schriftgutübermittlung" über beA, eBO, beN, etc.** 

## Funktionen
**openXJV unterstützt den XJustiz-Standard in den Versionen 3.6.2, 3.5.1, 3.4.1, 3.3.1, 3.2.1 sowie 2.4.1**. Es werden die wichtigsten Datentypen und Strukturen unterstützt - eine vollständige und abolut fehlerfreie Anzeige kann jedoch nicht garantiert werden. 
**Fachverfahren werden nicht unterstützt.**

* Darstellung der XJustiz-Nachricht in einer Aktenoberfläche
* Sortierfunktionen (alphabetisch / chronologisch)
* Filterfunktion über Dokumentenbezeichnung
* Volltextsuche in durchsuchbaren Dokumenten
* Texterkennung (OCR) für nicht-durchsuchbare Dokumentenscans
* Erstellung annotierbarer und bearbeitbarer PDF-Akten
* Favoritenfunktion

Ist die Texerkennung Tesseract inkl. der Erkennung für "Deutsch" und das Programm jbic2dec installiert, wird die Texerkennung für eingescannte - bisher nicht durchsuchbare - Dokumente unterstützt. Dies ermöglicht eine Volltextsuche über die Dokumenteninhalte. Der Windows-Installer und AppDir bringen die beiden Abhängigkeiten bereits mit. 

Die Inhalte der Nachricht lassen sich - sofern die Dateiformate unterstützt werden - in ein einzelnes PDF-Dokument umwandeln. 

## Werde Sponsor!

Du nutzt das Programm im kommerziellen Kontext? **Sei fair und unterstütze das Projekt!**: 🍕 [Spendiere dem Entwickler "eine Pizza" (gern auch mehrere)!](https://buymeacoffee.com/digidigital) 👍

## Installation
Die Installation ist mit einem Installer für Windows, einem AppImage für Linux (jeweils unter https://github.com/digidigital/openXJV/releases) und plattformübergreifend (Windows, Linux, macOS) mittels pip möglich: https://pypi.org/project/openXJV/

## Dokumentation
Das Benutzerhandbuch finden Sie in der Anwendung unter "Hilfe", hier auf Github im Unterverzeichnis "docs" oder zum Download auf https://openxjv.de  

Allgemeine Schulungsvideos auf [YouTube](https://www.youtube.com/watch?v=5Il65FuwW80&list=PLYwh5aIA0EYiSpG-rIWkc3ArgvlAIiYFa)

## Individuelle Schulungen / Einweisung in den Aktenviewer
Individuelle Schulung und Einweisung in die Nutzung des Aktenviewers online oder vor Ort: [Schulungsanfrage stellen!](mailto:support@digidigital.de?Subject=Schulungsanfrage)

2026-02-09 Björn Seipel
