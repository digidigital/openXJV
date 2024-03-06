# openXJV
Viewer for XJustiz files used for file / data transfers between courts, lawyers, agencies, etc. in  Germany's ERV-System

openXJV ist ein **kostenloses Anzeigeprogramm für XJustiz-Dateien (XJustiz Viewer)**, die im Rahmen des elektronischen Rechtsverkehrs (ERV) bei der Übertragung von Dokumenten Verwendung finden.

Dies ist z. B. **für die Akteneinsicht in Akten der Bundesanstalt für Arbeit (BA)** relevant, 
  da diese auf elektronischem Wege lediglich Einzeldateien mit einem begleitenden XJustiz-Datensatz übermittelt.   Erst das Auslesen des Datensatzes erzeugt aus der übermittelten "Dateisammlung" wieder eine sinnvolle Aktendarstellung.

**Es eignet sich auch zur Anzeige beliebiger XJustiz-Datensätze der "Schriftgutübermittlung" über beA, eBO, beN, etc.** 

openXJV ist entstanden, da zum Zeitpunkt des Projektstarts keine plattformübergreifende Anzeigelösung bereit stand.
  
**openXJV unterstützt den XJustiz-Standard in den Versionen 3.5.1, 3.4.1, 3.3.1, 3.2.1 sowie 2.4.1**. Es werden die wichtigsten Datentypen und Strukturen unterstützt - eine vollständige und abolut fehlerfreie Anzeige kann jedoch nicht garantiert werden. 
**Fachverfahren werden nicht unterstützt.**

Ist die Texerkennung Tesseract inkl. der Erkennung für "Deutsch" und das Programm jbic2dec installiert, wird die Texerkennung für eingescannte - bisher nicht durchsuchbare - Dokumente unterstützt. Dies ermöglicht eine Volltextsuche über die Dokumenteninhalte. Der Windows-Installer und AppDir bringen die beiden Abhängigkeiten bereits mit. 

Die Inhalte der Nachricht lassen sich - sofern die Dateiformate unterstützt werden - in ein einzelnes PDF-Dokument umwandeln. 

Das Benutzerhandbuch finden Sie in der Anwendung unter "Hilfe", hier auf Github im Unterverzeichnis "docs" 
oder zum Download auf https://openxjv.de  

Die Installation ist mit einem Installer für Windows, einem AppImage für Linux (jeweils unter https://github.com/digidigital/openXJV/releases) und plattformübergreifend (Windows, Linux, macOS) mittels pip möglich > https://pypi.org/project/openXJV/

Björn Seipel
