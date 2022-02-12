#!/usr/bin/python3
# coding: utf-8
from os import path
import glob
import lxml.etree as ET

class Lookup:
    def __init__(self, filepath) -> None:
        # XML Dateinamen im Lookup-Verzeichnis einlesen
        # Hier werden später - bei Aufruf von xjustizValue() - Codes
        # ausgelesen. Ist keine Datei mit passendem Dateinamen vorhanden, 
        # wird in den XSD-Codelisten nachgeschlagen.
        # Aktuell werden die XSD-Dateien bereits bei der Initialisierung
        # geparst, da vom Dateinamen nicht auf die beinhalteten Codelisten
        # geschlossen werden kann.
        self.filelistXML=[]
        for filename in glob.glob(filepath + '*.xml'):
            if not 'fehlerhaft' in filename.lower():
                self.filelistXML.append(filename)
        self._codelistenXSD={}
        
        # Codelisten-XSD einlesen und in dict ablegen
        for filename in glob.glob(filepath + '*_cl_*.xsd'):
            ns = '{http://www.w3.org/2001/XMLSchema}'
            content = ET.parse(filename).getroot()
            # Für Dateien nach XOEV 1.7.1
            lists= (content.findall('.//' +ns+'simpleType'))
            
            for list in lists:
                shortName = list.find('.//codeliste/nameKurz').text
                    
                tempDict={}
                elements=list.findall('.//'+ns+'enumeration')
                for element in elements:
                    tempDict[element.get('value')]= element.find('.//wert').text
                if len(tempDict)!=0:
                    self._codelistenXSD[shortName]=tempDict
                                             
        # Standard-XPath - Enthält Platzhalter für Spaltenbezeichnungsattribute
        # und Suchwert          
        self.gcode3Query =".//Row[Value[@ColumnRef = '%s']/SimpleValue/text() = '%s']/Value[@ColumnRef = '%s']/SimpleValue/text()"

    # Überprüft auf passenden Typnamen einer Datei in der Dateiliste
    # Gibt entweder Dateipfad oder None zurück
    def _checkForList(self, type):
        listFile = [y for y in self.filelistXML if type in y]        
        if len(listFile)>0:
            return listFile[0]
        else:
            return None

    # Liest XML-Datei ein und gibt root zurück
    def _lookupRoot(self, pathToXML):
        return ET.parse(pathToXML).getroot() 

    # Sucht nach Wert und gibt diesen oder None zurück
    def _getValue(self, gdsRoot, searchKey, keyColumnRef, getFromColumnRef):
        value=gdsRoot.xpath(self.gcode3Query % (keyColumnRef, searchKey, getFromColumnRef))
        if len(value)>0:
            return value[0]
        else:
            return None

    # Bildet Suchlogik ab und liefert Wert zurück    
    def xjustizValue (self, type, searchKey=None, keyColumnRef=None, getFromColumnRef=None):

        if searchKey==None or searchKey=='': return '' 
        
        # Überprüfen, ob Datei mir passendem Typnamen existiert und XML Dateipfad zurückgeben
        listFile=self._checkForList(type)
        
        # Falls keine Datei gefunden wurde, auf Vorhandensein
        # eines aus den XSD-Dateien ausgelesenen Dict für den Typ prüfen
        if listFile == None:
            if type in self._codelistenXSD.keys():
                
                if str(searchKey) in self._codelistenXSD[type].keys():
                    return self._codelistenXSD[type][str(searchKey)]
                else:
                    #print('Wert mit Code %s vom Typ %s nicht in XSDs gefunden.' % (searchKey, type))
                    return 'Wert mit Code %s vom Typ %s nicht in XSDs gefunden.' % (searchKey, type)
            else:
                #print('Keine Codeliste vom Typ %s hinterlegt.' % type)
                return 'Keine Codeliste vom Typ %s hinterlegt.' % type   

        # Einlesen der XML-Datei
        gdsRoot=self._lookupRoot(listFile)

        # Die als key spezifizierte Spalte identifizieren, 
        # sofern kein key beimFunktionsaufruf angegeben wurde
        if keyColumnRef == None:
            keyColumnRef=gdsRoot.find('.//ColumnSet/Key/ColumnRef').get('Ref')
            
        # Sofern nicht beim Funktionsaufruf übergeben, die 
        # erste Spalte, die eine von "key" abweichende 
        # Bezeichnung hat als Wert-Spalte festlegen 
        if getFromColumnRef == None:
            getFromColumnRef = [x.text for x in gdsRoot.findall(".//ColumnSet/Column[@Use='required']/ShortName") if x.text != keyColumnRef][0]
        
        value = self._getValue(gdsRoot, searchKey, keyColumnRef, getFromColumnRef)
        if value != None:
            return value
        else:
            return 'Wert mit Code %s vom Typ %s nicht in Datei gefunden' % (searchKey, type)