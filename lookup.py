#!/usr/bin/python3
# coding: utf-8
from os import path
import glob
import lxml.etree as ET

class Lookup:
    def __init__(self, filepath) -> None:
        
        # XML Dateinamen im Lookup-Verzeichnis einlesen
        # Hier werden später Codes ausgelesen
        self.filelistXML=[]
        for filename in glob.glob(filepath + '*.xml'):
            if not 'fehlerhaft' in filename.lower():
                self.filelistXML.append(filename)
        self._codelistenXSD={}
                
        # Codelisten XSD einlesen und in dict ablegen
        for filename in glob.glob(filepath + '*_cl_*.xsd'):
            ns = '{http://www.w3.org/2001/XMLSchema}'
            content = ET.parse(filename).getroot()
            lists=(content.findall('.//'+ns+'complexType'))
            for list in lists:
                if 'Code.' in list.get('name'):
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

    # Überprüft Typname in einer Datei in der Dateiliste
    # vorkommt und gibt Dateipfad oder None zurück
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
        
        # XML Dateipfad zurückgeben, falls Typ in Dateinamen
        listFile=self._checkForList(type)
        
        # Falls keine Datei eingelesen wurde, auf Vorhandensein
        # eines statischen Dict für den typ prüfen
        if listFile == None:
            if type in self._codelistenXSD.keys():
                
                if str(searchKey) in self._codelistenXSD[type].keys():
                    return self._codelistenXSD[type][str(searchKey)]
                else:
                    return 'Wert mit Code %s vom Typ %s nicht in XSDs gefunden' % (searchKey, type)
            '''
            elif type in self._codelistenStatic.keys():
                if str(searchKey) in self._codelistenStatic[type].keys():
                    return self._codelistenStatic[type][str(searchKey)]
                else:
                    return 'Wert mit Code %s vom Typ %s nicht in staticDict gefunden' % (searchKey, type) 
            '''
        # Einlesen der XML-Datei
        gdsRoot=self._lookupRoot(listFile)

        # Die als Key spezifizierte Spalte identifizieren, sofern kein Key angegeben
        
        if keyColumnRef == None:
            keyColumnRef=gdsRoot.find('.//ColumnSet/Key/ColumnRef').get('Ref')

            
        # Die erste Spalte, die eine von "key" abweichende 
        # Bezeichnung hat als wert-Spalte festlegen (sofern nicht übergeben)
        if getFromColumnRef == None:
            getFromColumnRef = [x.text for x in gdsRoot.findall(".//ColumnSet/Column[@Use='required']/ShortName") if x.text != keyColumnRef][0]
        
        value = self._getValue(gdsRoot, searchKey, keyColumnRef, getFromColumnRef)

        if value != None:
            return value
        else:
            return 'Wert mit Code %s vom Typ %s nicht in Datei gefunden' % (searchKey, type)
    '''
    # Statische Codelisten aus XJustiz-Spezifikation, sofern anderweitig
    # nicht und / oder nur 'fehlerhaft' im xrepository verfügbar
    _codelistenStatic={}

    _codelistenStatic['GDS.RVTraeger']={
    '02': 'Deutsche Rentenversicherung Nord',
    '09':'Deutsche Rentenversicherung Mitteldeutschland',
    '10':'Deutsche Rentenversicherung Braunschweig-Hannover',
    '11':'Deutsche Rentenversicherung Westfalen',
    '12':'Deutsche Rentenversicherung Hessen',
    '13':'Deutsche Rentenversicherung Rheinland',
    '15':'Deutsche Rentenversicherung Bayern Süd',
    '16':'Deutsche Rentenversicherung Rheinland-Pfalz',
    '17':'Deutsche Rentenversicherung Saarland',
    '18':'Deutsche Rentenversicherung Nordbayern',
    '21':'Deutsche Rentenversicherung Schwaben',
    '24':'Deutsche Rentenversicherung Baden-Württemberg',
    '25':'Deutsche Rentenversicherung Berlin-Brandenburg',
    '28':'Deutsche Rentenversicherung Oldenburg-Bremen',
    '70':'Deutsche Rentenversicherung Bund',
    '80':'Deutsche Rentenversicherung Knappschaft-Bahn-See'}
    '''
