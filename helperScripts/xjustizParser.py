#!/usr/bin/python3
# coding: utf-8
'''
    xjustizParser.py - parses XJustiz-XML-Files
    Copyright (C) 2022, 2023, 2024 Björn Seipel

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
'''
from helperScripts import Lookup

import lxml.etree as ET 
import re
from os import path
import sys  
import uuid

class parser321():
    
    def __init__(self, filename=None ):
        if filename:
            self._root=self._loadFile(filename)
            _root=''
            
        else:
            ###ggf besseren Fehler suchen###
            raise (AttributeError('No attribute "filename"')) 
    ##Konfigurierbar und schön machen... 
        self._newline='\n'
        self._xj_ns='{http://www.xjustiz.de}'
        # Wo liegen XML, XSD-Dateien mit Codelisten?
        script_path = path.dirname(path.realpath(__file__))
        path_to_json_lists = script_path + "/../codelisten_json/"
        path_to_xsd_lists = script_path + "/../codelisten_xsd/" 
        self.lookup=Lookup(path_to_json_lists, path_to_xsd_lists)  
        
        self.alleAktenIDs = []
        self._parseAllValues()  
                
    def _loadFile(self, inputfile): 
        self.nachricht={}
        self.absender={}
        self.empfaenger={}
        self.grunddaten={}
        self.schriftgutobjekte={}
        self.rollenverzeichnis={}
        self.beteiligtenverzeichnis={}
        return ET.parse(inputfile).getroot()
    
    # Setzt Namespace hinter /
    def _addNS(self, path, namespace=None):
        namespace = self._xj_ns if namespace is None else namespace
        return re.sub( "/(?!/)", "/" + namespace , path)

    # Wie "find", liest jedoch gleich .text aus
    # code=True hängt "/code" ohne Namespace and den Pfad 
    def _findElementText(self, path, element=None, namespace=None, code=False):
        namespace = self._xj_ns if namespace is None else namespace
        element = self._root if element is None else element
                
        path =self._addNS(path)

        try:
            if code=='name':
                path += '/name'     
            elif code==True: 
                path += '/code'            
            return element.find(path).text.strip()
        except AttributeError:
            return ''

    def _getListVersion(self, path, element=None, namespace=None):
        namespace = self._xj_ns if namespace is None else namespace
        element = self._root if element is None else element
                
        path =self._addNS(path)

        try:
            versionID = element.find(path).attrib.get('listVersionID')
            if versionID.isnumeric() or re.match(r"\d*\.\d*", str(versionID)):
                return float(versionID)
            else:
                return str(versionID) 
        except Exception:
            return None
        
    # Liest den Text von Attributen
    def _getElementText(self, path, element=None, namespace=None, code=False):
        namespace = self._xj_ns if namespace is None else namespace
        element = self._root if element is None else element
        
        path =self._addNS(path)
        if code: path += '/code'
        try:
            return element.get(path).text.strip()
        except AttributeError:
            return ''
    
    
    # Gibt alle Textelemente der mit findall gefundenen Elemente
    # mit _newline getrennt als string zurück
    def _getSubTexts(self, path, element=None, namespace=None, newline='\n'):
        namespace = self._xj_ns if namespace is None else namespace
        element = self._root if element is None else element
        
        path =self._addNS(path)
        text=''
        try:
            for child in element.findall(path):
                if text=='':
                    text=child.text.strip()
                else:
                    text+= newline+child.text.strip()    
            return text
        except AttributeError:
            return text

    # Wie find, fügt jedoch automatisch Namespace zu Pfad hinzu
    def _findElement(self, path, element=None, namespace=None):
        namespace = self._xj_ns if namespace is None else namespace
        element = self._root if element is None else element
        
        path =self._addNS(path)
        try:
            result = element.find(path)
            if result is None or str(result)=='-1':
                if str(result)=='-1':
                    print('Es wurde versucht, ein Kindelement eines nicht existierenden Knotens zu finden.')
                result=''
            return result
        except AttributeError:
            return ''

    # Wie findAll, fügt jedoch automatisch Namespace zu Pfad hinzu
    def _findAllElements (self, path, element=None, namespace=None, code=False):
        namespace = self._xj_ns if namespace is None else namespace
        element = self._root if element is None else element
        
        path =self._addNS(path)
        if code: path += '/code'
        try:
            return element.findall(path)
        except AttributeError:
            return ''

    # Prüft, ob ein übergebener Tag im Ergebnis-Node von find vorhanden ist
    def _tagInAuswahl (self, tag, auswahl, namespace=None):
        namespace = self._xj_ns if namespace is None else namespace
        
        if auswahl is not None:
            for child in auswahl:
                if child.tag == namespace + tag:
                    return True
        return False

    def _parseOrganisation(self, node):
        orgData={}
        orgData['type']='GDS.Organisation'
        orgData['bezeichnung.aktuell']=self._findElementText('./bezeichnung/bezeichnung.aktuell', node)
        orgData['kurzbezeichnung']    =self._findElementText('./kurzbezeichnung', node)
        orgData['bezeichnung.alt']=[]
        for bezeichnung in self._findAllElements ('./bezeichnung/bezeichnung.alt', node): 
            orgData['bezeichnung.alt'].append(bezeichnung.text)
        
        orgData['anschrift']=[]
        for anschrift in self._findAllElements ("./anschrift", node): 
            orgData['anschrift'].append(self._parseAnschrift(anschrift)) 
        
        orgData['angabenZurRechtsform']={}
        rechtsform = self._findElement('./angabenZurRechtsform', node)
        if rechtsform != '':
            orgData['angabenZurRechtsform']=self._parseRechtsform(rechtsform)
        
        orgData['geschlecht']    = self.lookup.xjustizValue ('GDS.Geschlecht', self._findElementText("./geschlecht", node, code=True), verNo = self._getListVersion("./geschlecht", element=node))
        
        orgData['telekommunikation']=[]
        for telekom in self._findAllElements ("./telekommunikation", node): 
            orgData['telekommunikation'].append(self._parseTelekommunikation(telekom))
              
        orgData['bankverbindung']=[]
        for bankverbindung in self._findAllElements ("./bankverbindung", node):
            orgData['bankverbindung'].append(self._parseBankverbindung(bankverbindung))
        
        orgData['umsatzsteuerID'] = self._findElementText('./umsatzsteuerID', node)
        
        orgData['registereintragung']={}
        registereintragung = self._findElement('./registereintragung', node)
        if registereintragung != '':
            orgData['registereintragung']=self._parseRegistrierung(registereintragung)
        
        orgData['sitz']=[]
        for sitz in self._findAllElements ("./sitz", node):
            orgData['sitz'].append(self._parseSitz(sitz))
       
        return orgData

    def _parseSitz(self, sitz):
        data={}
        data['ort']          = self._findElementText('./ort', sitz)
        data['postleitzahl'] = self._findElementText('./postleitzahl', sitz)
        data['staat']        = self._parseStaat (self._findElement("./staat", sitz))
        return data
    
    def _parseRechtsform(self, rechtsform):
        data={}
        data['rechtsform']         = self.lookup.xjustizValue ('GDS.Rechtsform', self._findElementText("./rechtsform", rechtsform, code=True), verNo = self._getListVersion("./rechtsform", element=rechtsform))
        data['weitereBezeichnung'] = self._findElementText('./weitereBezeichnung', rechtsform)
       
        return data
    
    def _parseRegistrierung(self, registrierung):
        data={}
        
        items=(
            'registernummer',
            'reid',
            'lei',
            'euid'             
        )
        
        for item in items:
            data[item]= self._findElementText('./' + item, registrierung)
        
        data['auswahl_registerbehoerde']={}
        
        data['auswahl_registerbehoerde']['inlaendischesRegistergericht']={}
        data['auswahl_registerbehoerde']['inlaendischesRegistergericht']['gericht']=self.lookup.xjustizValue ('GDS.Gerichte', self._findElementText("./auswahl_registerbehoerde/inlaendischesRegistergericht/gericht", registrierung, code=True), verNo = self._getListVersion("./auswahl_registerbehoerde/inlaendischesRegistergericht/gericht", element=registrierung))
        data['auswahl_registerbehoerde']['inlaendischesRegistergericht']['registerart']=self.lookup.xjustizValue ('GDS.Registerart', self._findElementText("./auswahl_registerbehoerde/inlaendischesRegistergericht/registerart", registrierung, code=True), verNo = self._getListVersion("./auswahl_registerbehoerde/inlaendischesRegistergericht/registerart", element=registrierung))
        
        data['auswahl_registerbehoerde']['sonstigeRegisterbehoerde']={}
        data['auswahl_registerbehoerde']['sonstigeRegisterbehoerde']['registerbehoerde']   =self._findElementText('./auswahl_registerbehoerde/sonstigeRegisterbehoerde/registerbehoerde', registrierung)
        data['auswahl_registerbehoerde']['sonstigeRegisterbehoerde']['registerbezeichnung']=self._findElementText('./auswahl_registerbehoerde/sonstigeRegisterbehoerde/registerbezeichnung', registrierung)
                
        return data

    def _parseKanzlei(self, node):
        kanzleiData={}
        kanzleiData['type']='GDS.RA.Kanzlei'
        kanzleiData['bezeichnung.aktuell']=self._findElementText('./bezeichnung/bezeichnung.aktuell', node)
        kanzleiData['bezeichnung.alt']=[]
        for bezeichnung in self._findAllElements ('./bezeichnung/bezeichnung.alt', node): 
            kanzleiData['bezeichnung.alt'].append(bezeichnung.text)
        
        kanzleiData['anschrift']=[]
        for anschrift in self._findAllElements ("./anschrift", node): 
            kanzleiData['anschrift'].append(self._parseAnschrift(anschrift)) 
        
        kanzleiData['geschlecht'] =self.lookup.xjustizValue ('GDS.Geschlecht', self._findElementText("./geschlecht", node, code=True), verNo = self._getListVersion("./geschlecht", element=node))
        kanzleiData['rechtsform'] = self._parseRechtsform(node)['rechtsform']
        kanzleiData['kanzleiform']=self.lookup.xjustizValue ('GDS.Kanzleiform', self._findElementText("./kanzleiform", node, code=True), verNo = self._getListVersion("./kanzleiform", element=node))
        
        kanzleiData['telekommunikation']=[]
        for telekom in self._findAllElements ("./telekommunikation", node): 
            kanzleiData['telekommunikation'].append(self._parseTelekommunikation(telekom))
        
        kanzleiData['raImVerfahren']=[]
        if self._findElement('./raImVerfahren', node)!='':
            kanzleiData['raImVerfahren']=self._parseNatuerlichePerson(self._findElement('./raImVerfahren', node))
        
        kanzleiData['umsatzsteuerID']= self._findElementText('./umsatzsteuerID', node)
        return kanzleiData

    def _parseNatuerlichePerson(self, node):
        personData={}
        personData['type']='GDS.NatuerlichePerson'
        personData['vollerName']=self._parseNameNatuerlichePerson(self._findElement('./vollerName', node))
        personData['aliasNatuerlichePerson']=[]
        for alias in self._findAllElements ("./aliasNatuerlichePerson", node): 
            personData['aliasNatuerlichePerson'].append(self._parseNatuerlichePerson(alias))
        
        personData['umsatzsteuerID']= self._findElementText('./umsatzsteuerID', node)
        
        personData['geschlecht']    =self.lookup.xjustizValue ('GDS.Geschlecht', self._findElementText("./geschlecht", node, code=True), verNo = self._getListVersion("./geschlecht", element=node))
        personData['familienstand'] =self.lookup.xjustizValue ('GDS.Familienstand', self._findElementText("./familienstand", node, code=True), verNo = self._getListVersion("./familienstand", element=node))
        personData['personalstatut']=self.lookup.xjustizValue ('GDS.Personalstatut', self._findElementText("./personalstatut", node, code=True), verNo = self._getListVersion("./personalstatut", element=node))
        
        personData['beruf']=[]
        for beruf in self._findAllElements ("./beruf", node): 
            personData['beruf'].append(beruf.text)
        
        personData['telekommunikation']=[]
        for telekom in self._findAllElements ("./telekommunikation", node): 
            personData['telekommunikation'].append(self._parseTelekommunikation(telekom))
            
        personData['anschrift']=[]
        for anschrift in self._findAllElements ("./anschrift", node): 
            personData['anschrift'].append(self._parseAnschrift(anschrift))    
        
        personData['zustaendigeInstitution']=[]
        for institution in self._findAllElements ("./zustaendigeInstitution/ref.rollennummer", node): 
            personData['zustaendigeInstitution'].append(institution.text)      
        
        personData['staatsangehoerigkeit']=[]
        for staat in self._findAllElements ("./staatsangehoerigkeit", node):
            if staat is not None:
                personData['staatsangehoerigkeit'].append(self._parseStaat (staat))              
                       
        personData['herkunftsland']=[]
        for staat in self._findAllElements ("./herkunftsland", node):
            if staat is not None:
                personData['herkunftsland'].append(self._parseStaat (staat))   
                                                       
        personData['sprache']=[]
        for sprache in self._findAllElements ("./sprache", node, code=True):
            personData['sprache'].append(self.lookup.xjustizValue ('GDS.Sprachen', sprache.text))
        
        personData['bankverbindung']=[]
        for bankverbindung in self._findAllElements ("./bankverbindung", node):
            personData['bankverbindung'].append(self._parseBankverbindung(bankverbindung))
               
        personData['registereintragungNatuerlichePerson']=[]
        registereintragung=self._findElement('./registereintragungNatuerlichePerson', node)
        if registereintragung != '':
            personData['registereintragungNatuerlichePerson']=self._parseRegistereintragungNatuerlichePerson(registereintragung)
        
        personData['tod']=[]
        tod=self._findElement('./tod', node)
        if tod != '':
            personData['tod']=self._parseTod(tod)
            
        personData['geburt']=[]
        geburt=self._findElement('./geburt', node)
        if geburt != '':
            personData['geburt']=self._parseGeburt(geburt)
                    
        personData['auswahl_auskunftssperre']=[]
        auskunftssperre=self._findElement('./auswahl_auskunftssperre', node)
        if auskunftssperre != '':
            personData['auswahl_auskunftssperre']=self._parseAuskunftssperre(auskunftssperre)
        
        return personData
    
    def _parseRegistereintragungNatuerlichePerson(self, registereintragung):
        data={}
        data['verwendeteFirma']                            = self._findElementText('./verwendeteFirma' , registereintragung)
        data['angabenZurRechtsform']                       = {}
        angaben=self._findElement('./angabenZurRechtsform', registereintragung)
        if angaben != '':
             data['angabenZurRechtsform'] =  self._parseRechtsform(angaben)
        else:
            data['angabenZurRechtsform']['weitereBezeichnung'] = ''
            data['angabenZurRechtsform']['rechtsform']         = ''
        data['registereintragung']                         = self._parseRegistrierung(self._findElement('./registereintragung', registereintragung))
        return data
    
    def _parseAuskunftssperre(self, auskunftssperre):
        data={}
        
        data['auskunftssperre.vorhanden']=self._findElementText('./auskunftssperre.vorhanden', auskunftssperre)    
           
        sperreitems=(
            'grundlage',
            'umfang',
            'sperrstufe'
        )
        data['auskunftssperre.details']={}
        
        for item in sperreitems:
            data['auskunftssperre.details'][item]=self._findElementText('./auskunftssperre.details/'+item, auskunftssperre)
            
        return data
    
    def _parseAnschrift(self, node):
        anschrift={}
        simpleValues=(
            'strasse',
            'hausnummer',
            'postfachnummer',
            'postleitzahl',
            'ort',
            'ortsteil',
            'wohnungsgeber',
            'ehemaligeAnschrift',
            'erfassungsdatum',
            'ort.unbekannt',
            'postleitzahl.unbekannt'             
        )
        for value in simpleValues:
            anschrift[value]= self._findElementText('./' + value, node)
        
        anschrift['anschriftenzusatz']=[]
        for zusatz in self._findAllElements ("./anschriftenzusatz", node): 
            anschrift['anschriftenzusatz'].append(zusatz.text)
        
        anschrift['anschriftstyp']=self.lookup.xjustizValue ('GDS.Anschriftstyp', self._findElementText("./anschriftstyp", node, code=True), verNo = self._getListVersion("./anschriftstyp", element=node))
       
        anschrift['staat']          = self._parseStaat (self._findElement("./staat", node))
        
            
        #Set default values as defined in the specification if empty
        if anschrift['ort.unbekannt']=='':
            anschrift['ort.unbekannt']='true'
        
        if anschrift['ort.unbekannt']=='':
            anschrift['ort.unbekannt']='true'
        
        if anschrift['ehemaligeAnschrift']=='':
            anschrift['ehemaligeAnschrift']='false'
            
        return anschrift
        
    def _parseBankverbindung(self, bankverbindung):
        data={}
        items=(
            'bankverbindungsnummer',
            'bank',
            'kontoinhaber',
            'iban',
            'bic',
            'sepa-mandat',
            'verwendungszweck'
        )

        for item in items:
            data[item]=self._findElementText('./'+item, bankverbindung)
        
        if not data['sepa-mandat']:
            data['sepa-mandat']='false'
        
        return data
    
    def _parseGeldbetrag(self, geldbetrag):
        return self._findElementText('.//zahl', geldbetrag) + ' ' + self.lookup.xjustizValue ("Währung", self._findElementText(".//waehrung", element=geldbetrag, code=True), verNo = self._getListVersion(".//waehrung", element=geldbetrag))
    
    def _parseGeburt(self, geburt):
        data={}
           
        items=(
            'geburtsdatum',
            'geburtsname.mutter',
            'geburtsdatum.unbekannt'
        )

        for item in items:
            data[item]=self._findElementText('./'+item, geburt)

        if data['geburtsdatum.unbekannt'].lower()!='true':
            data['geburtsdatum.unbekannt']='false'
        
        elternnameitems=(
            'nachname.vater',
            'vorname.vater',
            'nachname.mutter',
            'vorname.mutter',
        )
        data['name.eltern']={}
        data['name.eltern']['nachname.mutter']=[]
        data['name.eltern']['nachname.vater'] =[]
        data['name.eltern']['vorname.mutter'] =[]
        data['name.eltern']['vorname.vater']  =[]

        for item in elternnameitems:
            for name in self._findAllElements('./name.eltern/' + item, geburt): 
                data['name.eltern'][item].append(name.text)
    
        geburtsort={}
        
        data['geburtsort']={}
        data['geburtsort']['ort']  =self._findElementText('./geburtsort/ort', geburt)    
        data['geburtsort']['staat']= self._parseStaat (self._findElement ("./geburtsort/staat", geburt))  
            
        return data
    
    def _parseStaat(self, staat):
        staatAllgemein  = self.lookup.xjustizValue ('Country Codes', self._findElementText(".//staat", staat, code=True), keyColumnRef='ISOAlpha2code', getFromColumnRef="ShortName")
        staatAlternativ = self.lookup.xjustizValue ("GDS.Staaten.Alternativ", self._findElementText(".//staat.alternativ", staat, code=True), verNo = self._getListVersion(".//staat.alternativ", element=staat))

        if staatAllgemein:
            return staatAllgemein
        elif staatAlternativ:
            return staatAlternativ
        else:
            return ''
        
    def _parseTod(self, tod):
        
        data={}
        items=(
            'sterbedatum',
            'sterbestandesamtBehoerdennummer',
            'sterbestandesamtName',
            'sterberegisternummer',
            'eintragungsdatum',
            'todErklaert',
        )

        for item in items:
            data[item]=self._findElementText('./'+item, tod)
             
        data['sterbeort']=self._parseAnschrift(self._findElement ("./sterbeort", tod))
        
        data['sterbedatumZeitraum']={}
        data['sterbedatumZeitraum']['ende']   = self._findElementText('./sterbedatumZeitraum/ende', tod)
        data['sterbedatumZeitraum']['beginn']   = self._findElementText('./sterbedatumZeitraum/beginn', tod)

        data['sterberegisterart']=self.lookup.xjustizValue ("GDS.Registerart", self._findElementText("./sterberegisterart", tod, code=True), verNo = self._getListVersion("./sterberegisterart", element=tod))    
        
        return data
    
    def _parseNameNatuerlichePerson(self, node):
        namensbestandteile={}
        
        simpleValues=(  
                'vorname',
                'rufname',
                'titel',
                'nachname',
                'geburtsname',
                'namensvorsatz',
                'namenszusatz',
                'geburtsnamensvorsatz',
            )
        for simpleValue in simpleValues:
            namensbestandteile[simpleValue] = self._findElementText('./'+simpleValue, node)
        
        multiValues=(  
                'vorname.alt',
                'nachname.alt',
                'weitererName'            
            )    
        for multiValue in multiValues:    
            namensbestandteile[multiValue] = []
            for value in self._findAllElements ("./"+multiValue, node):  
                namensbestandteile[multiValue].append(value.text)       
                
        return namensbestandteile

    def _parseBeteiligung(self, beteiligungNode):
        beteiligung={}
        beteiligung['rolle']=[]
        for rolle in self._findAllElements ("./rolle", beteiligungNode):
            rolleData={}
            rolleData['rollennummer']= self._findElementText("./rollennummer", rolle)
            rolleData['nr']= self._findElementText("./nr", rolle)
            if not rolleData['nr']:
                rolleData['nr']=1
            rolleData['geschaeftszeichen']= self._findElementText("./geschaeftszeichen", rolle)
            rolleData['naehereBezeichnung']= self._findElementText("./naehereBezeichnung", rolle)
            rolleData['rollenbezeichnung']=self.lookup.xjustizValue ("GDS.Rollenbezeichnung", self._findElementText("./rollenbezeichnung", rolle, code=True), verNo = self._getListVersion("./rollenbezeichnung", element=rolle))
            
            rolleData['referenz']=[]
            for referenz in self._findAllElements ("./referenz", rolle): 
                rolleData['referenz'].append(self._findElementText("./ref.rollennummer", referenz))
            
            rolleData['rollenID']=[]
            for rollenID in self._findAllElements ("./rollenID", rolle): 
                rollenIDData={}
                rollenIDData['id']=self._findElementText("./id", rollenID)
                rollenIDData['ref.instanznummer']=self._findElementText("./ref.instanznummer", rollenID)
                rolleData['rollenID'].append(rollenIDData)
            
            self.rollenverzeichnis[str(rolleData['rollennummer'])]= "%s %s" % (rolleData['rollenbezeichnung'], rolleData['nr'])
                    
            beteiligung['rolle'].append(rolleData)
            
        beteiligung['beteiligtennummer']=self._findElementText("./beteiligter/beteiligtennummer", beteiligungNode)
                
        beteiligterAuswahl              =self._findElement("./beteiligter/auswahl_beteiligter", beteiligungNode)
        if   self._tagInAuswahl ('ra.kanzlei', beteiligterAuswahl):
            beteiligung['beteiligter']  = self._parseKanzlei(self._findElement('./ra.kanzlei',beteiligterAuswahl))
            name=beteiligung['beteiligter']['bezeichnung.aktuell']
        elif self._tagInAuswahl ('natuerlichePerson', beteiligterAuswahl):
            beteiligung['beteiligter']  = self._parseNatuerlichePerson(self._findElement('./natuerlichePerson',beteiligterAuswahl))
            name=beteiligung['beteiligter']['vollerName']['nachname'].upper()+' '+beteiligung['beteiligter']['vollerName']['vorname'] 
        elif self._tagInAuswahl ('organisation', beteiligterAuswahl):
            beteiligung['beteiligter']  = self._parseOrganisation(self._findElement('./organisation',beteiligterAuswahl))
            name=beteiligung['beteiligter']['bezeichnung.aktuell']
        else:
            beteiligung['beteiligter']  = {}
        
        if beteiligung['beteiligtennummer']:
            self.beteiligtenverzeichnis[beteiligung['beteiligtennummer']]=name
        
        return beteiligung

    def _parseVerfahrensgegenstand(self, node):
        gegenstandData={}
        gegenstandData['gegenstand']     =self._findElementText('.//gegenstand', node)
        gegenstandData['gegenstandswert']=self._parseGeldbetrag(self._findElement('.//gegenstandswert', node))

        gegenstandData['auswahl_zeitraumDesVerwaltungsaktes']=''
        auswahl = self._findElement("./auswahl_zeitraumDesVerwaltungsaktes", node)
        if   self._tagInAuswahl ('jahr', auswahl):
            gegenstandData['auswahl_zeitraumDesVerwaltungsaktes']=self._findElementText(".//jahr", node)
        elif self._tagInAuswahl ('stichtag', auswahl):
            gegenstandData['auswahl_zeitraumDesVerwaltungsaktes']=self._findElementText(".//stichtag", node)
        elif self._tagInAuswahl ('keinZeitraum', auswahl):
            gegenstandData['auswahl_zeitraumDesVerwaltungsaktes']=self._findElementText(".//keinZeitraum", node)        
        elif self._tagInAuswahl ('zeitraum', auswahl):
            gegenstandData['auswahl_zeitraumDesVerwaltungsaktes']=self._findElementText(".//beginn", node) + ' ' + self._findElementText(".//ende", node)
        
        return gegenstandData

    def _parseBehoerde(self, auswahlNode):
        behoerde={}
        if   self._tagInAuswahl ('sonstige', auswahlNode):
            behoerde['name'] = self._findElementText("./sonstige", auswahlNode)
            behoerde['type'] = 'sonstige'
        elif self._tagInAuswahl ('gericht', auswahlNode):
            behoerde['name'] = self.lookup.xjustizValue ("GDS.Gerichte", self._findElementText("./gericht", auswahlNode , code=True), verNo = self._getListVersion("./gericht", element=auswahlNode ))
            behoerde['type'] ='GDS.Gerichte'
        elif self._tagInAuswahl ('beteiligter', auswahlNode):
            behoerde['name'] = self._findElementText("./beteiligter/ref.beteiligtennummer", auswahlNode)
            behoerde['type'] ='GDS.Ref.Beteiligtennummer'
        return behoerde 

    def _parseAktenzeichen(self, aktenzeichen):
        aktenzeichenParts={}
        aktenzeichenParts['az.art']                      =self.lookup.xjustizValue ("GDS.Aktenzeichenart", self._findElementText("./az.art", element=aktenzeichen, code=True), verNo = self._getListVersion("./az.art", element=aktenzeichen))
        
        aktenzeichenParts['auswahl_az.vergebendeStation']=[]
        if self._findElement("./auswahl_az.vergebendeStation", element=aktenzeichen)!='':
            aktenzeichenParts['auswahl_az.vergebendeStation']=self._parseBehoerde(self._findElement("./auswahl_az.vergebendeStation", element=aktenzeichen))
        
        aktenzeichenParts['aktenzeichen.freitext']       =self._findElementText("./auswahl_aktenzeichen/aktenzeichen.freitext", element=aktenzeichen) 
        if len(aktenzeichenParts['aktenzeichen.freitext'])==0:
            aktenzeichenStrukturiert={}
            aktenzeichenElements=(  
                'sachgebietsschluessel',
                'zusatzkennung',
                'abteilung',
                'laufendeNummer',
                'jahr',
                'vorsatz',
                'zusatz',
                'dezernat',
                'erfassungsdatum'                       
            )
            for elementName in aktenzeichenElements:
                aktenzeichenStrukturiert[elementName]=self._findElementText(".//" + elementName, element=aktenzeichen)
            aktenzeichenStrukturiert['register']     =self.lookup.xjustizValue ("GDS.Registerzeichen", self._findElementText(".//register", element=aktenzeichen, code=True), verNo = self._getListVersion(".//register", element=aktenzeichen))
            aktenzeichenParts['aktenzeichen.strukturiert']=aktenzeichenStrukturiert
            
            aktenzeichenFreitext="%s %s %s %s/%s %s" % (aktenzeichenStrukturiert['vorsatz'],
                                                        aktenzeichenStrukturiert['abteilung'],
                                                        aktenzeichenStrukturiert['register'],
                                                        aktenzeichenStrukturiert['laufendeNummer'],
                                                        aktenzeichenStrukturiert['jahr'],
                                                        aktenzeichenStrukturiert['zusatz'])
            
            if aktenzeichenFreitext.strip() != '/':
                aktenzeichenParts['aktenzeichen.freitext']=aktenzeichenFreitext 
        
        return aktenzeichenParts

    def _parseTelekommunikation(self, node):
        telkodata={}
        telkodata['telekommunikationsart']   =self.lookup.xjustizValue ("GDS.Telekommunikationsart", self._findElementText("./telekommunikationsart", node, code=True), verNo = self._getListVersion("./telekommunikationsart", element=node))
        telkodata['telekommunikationszusatz']=self.lookup.xjustizValue ("GDS.Telekommunikationszusatz", self._findElementText("./telekommunikationszusatz", node, code=True), verNo = self._getListVersion("./telekommunikationszusatz", element=node))
        telkodata['verbindung']              =self._findElementText('.//verbindung', node)
        return telkodata

    # funktion def self._parseDokumente(docNode) returns dict
    def _parseDokumente(self, path='./schriftgutobjekte/dokument', element=None):
        element = self._root if element is None else element
        documents={}
        documentNodes= self._findAllElements(path, element)
        if documentNodes != '':
            simpleValues=(  
                'id',
                'nummerImUebergeordnetenContainer',
                'fremdesGeschaeftszeichen',
                'posteingangsdatum',
                'datumDesSchreibens',
                'anzeigename',
                'akteneinsicht',
                'veraktungsdatum',
                'absenderAnzeigename',
                'adressatAnzeigename',
                'justizkostenrelevanz',
                'ruecksendungEEB.erforderlich',
                'zustellung41StPO',
            )
            for documentNode in documentNodes:
                document={}
                for simpleValue in simpleValues:
                    document[simpleValue]=self._findElementText('.//'+simpleValue, documentNode)
                
                document['vertraulichkeitsstufe']=self.lookup.xjustizValue ("GDS.Vertraulichkeitsstufe", self._findElementText(".//vertraulichkeitsstufe", element=documentNode , code=True), verNo = self._getListVersion(".//vertraulichkeitsstufe", element=documentNode )) 
                document['dokumentklasse']       =self.lookup.xjustizValue ("GDS.Dokumentklasse", self._findElementText(".//dokumentklasse", element=documentNode , code=True), verNo = self._getListVersion(".//dokumentklasse", element=documentNode )) 
                document['dokumententyp']        =self.lookup.xjustizValue ("GDS.Dokumenttyp", self._findElementText(".//dokumententyp", element=documentNode , code=True), verNo = self._getListVersion(".//dokumententyp", element=documentNode ))  
                
                document['personen']=[]
                for person in self._findAllElements('.//person/ref.beteiligtennummer', element=documentNode):
                    document['personen'].append(person.text)
                
                document['verweise']=[]
                for verweis in self._findAllElements('.//verweis', element=documentNode):
                    verweisParts={}
                    verweisParts['anzeigenameSGO']=self._findElementText('./anzeigenameSGO', element=verweis)
                    verweisParts['id.sgo']        =self._findElementText('./id.sgo', element=verweis)
                    verweisParts['verweistyp']    =self.lookup.xjustizValue ("GDS.Verweistyp", self._findElementText("./verweistyp", element=verweis , code=True), verNo = self._getListVersion("./verweistyp", element=verweis ))   
                    document['verweise'].append(verweisParts)
                
                document['dateien']=[]
                for datei in self._findAllElements('.//datei', element=documentNode):
                    dateiData={}
                    dateiData['dateiname']     =self._findElementText('./dateiname', element=datei)
                    dateiData['versionsnummer']=self._findElementText('./versionsnummer', element=datei)
                    dateiData['bestandteil']   =self.lookup.xjustizValue ('GDS.Bestandteiltyp', self._findElementText("./bestandteil", element=datei , code=True), verNo = self._getListVersion("./bestandteil", element=datei))  
                    
                    dateiData['dateiname.bezugsdatei']=[]
                    for bezugsdatei in self._findAllElements ('./dateiname.bezugsdatei', element=datei):
                        dateiData['dateiname.bezugsdatei'].append(bezugsdatei.text)
                    
                    document['dateien'].append(dateiData)
                
                documents[document['id']]=document
        return documents

    # funktion def self._parseDokumente(docNode) returns dict
    def _parseAkten(self, path='./schriftgutobjekte/akte', element=None):
        element = self._root if element is None else element
        
        files={}
        fileNodes= self._findAllElements(path, element)
        if fileNodes != '':
            simpleValues=(  
                './anzeigename',
                './identifikation/id',
                './identifikation/nummerImUebergeordnetenContainer',
                './xjustiz.fachspezifischeDaten/anzeigename',
                './xjustiz.fachspezifischeDaten/weiteresOrdnungskriteriumBehoerde',
                './xjustiz.fachspezifischeDaten/erstellungszeitpunktAkteVersand',
                './xjustiz.fachspezifischeDaten/ruecksendungEEB.erforderlich',
                './xjustiz.fachspezifischeDaten/zustellung41StPO',
                # teilaktenspezifisch
                './xjustiz.fachspezifischeDaten/akteneinsicht',
                './xjustiz.fachspezifischeDaten/letztePaginierungProTeilakte',
            )
            for fileNode in fileNodes:
                file={}
                for simpleValue in simpleValues:
                    file[simpleValue.rsplit('/', 1)[1]]=self._findElementText(simpleValue, fileNode)
            
                file['dokumente']            = self._parseDokumente('./xjustiz.fachspezifischeDaten/inhalt/dokument', fileNode)
                file['teilakten']            = self._parseAkten('./xjustiz.fachspezifischeDaten/inhalt/teilakte', fileNode)
                file['abgebendeStelle']      = self.lookup.xjustizValue ('GDS.Gerichte', self._findElementText("./xjustiz.fachspezifischeDaten/abgebendeStelle", element=fileNode, code=True), verNo = self._getListVersion("../xjustiz.fachspezifischeDaten/abgebendeStelle", element=fileNode))
                file['aktentyp']             = self.lookup.xjustizValue ('GDS.Aktentyp', self._findElementText("./xjustiz.fachspezifischeDaten/aktentyp", element=fileNode, code=True), verNo = self._getListVersion("./xjustiz.fachspezifischeDaten/aktentyp", element=fileNode))
                file['vertraulichkeitsstufe']= self.lookup.xjustizValue ('GDS.Vertraulichkeitsstufe', self._findElementText("./vertraulichkeitsstufe", element=fileNode , code=True), verNo = self._getListVersion("./vertraulichkeitsstufe", element=fileNode))
                
                file['personen']=[]
                for person in self._findAllElements ('./xjustiz.fachspezifischeDaten/person/ref.beteiligtennummer', element=fileNode):
                        file['personen'].append(person.text)
                
                file['laufzeit']={}
                for laufzeit in self._findElement ('./laufzeit', element=fileNode):
                    # remove namespace and use tag as key
                    file['laufzeit'][laufzeit.tag.rsplit("}", 1)[1]]=laufzeit.text
                
                file['aktenreferenzen']=[]
                for aktenreferenz in self._findAllElements ('./xjustiz.fachspezifischeDaten/aktenreferenzen', element=fileNode):
                    referenceParts={}
                    referenceParts['id.referenzierteAkte']=self._findElementText("./id.referenzierteAkte", element=aktenreferenz)
                    referenceParts['aktenreferenzart']    =self.lookup.xjustizValue ("GDS.Aktenreferenzart", self._findElementText("./aktenreferenzart", element=aktenreferenz, code=True), verNo = self._getListVersion("./aktenreferenzart", element=aktenreferenz))
                    file['aktenreferenzen'].append(referenceParts)
                
                file['aktenzeichen']=[]
                for aktenzeichen in self._findAllElements ('./xjustiz.fachspezifischeDaten/aktenzeichen', element=fileNode):
                    file['aktenzeichen'].append(self._parseAktenzeichen(aktenzeichen))
                
                # Teilaktenspezifisch
                file['teilaktentyp']=self.lookup.xjustizValue ("GDS.Teilaktentyp", self._findElementText("./xjustiz.fachspezifischeDaten/teilaktentyp", element=fileNode, code=True), verNo = self._getListVersion("./xjustiz.fachspezifischeDaten/teilaktentyp", element=fileNode))
                
                files[file['id']]=file
                self.alleAktenIDs.append(file['id'])
                
        return files

    def _parseTermin(self, termin):
        data={}
        
        data['uuid']=str(uuid.uuid4())
        
        items=[
            'hauptterminsdatum',
            'hauptterminsID',
            'terminsID',
            'spruchkoerper',
            'oeffentlich'
        ]
        
        for item in items:
            data[item]=self._findElementText('./' + item, termin)
        
        data['auswahl_hauptterminszeit']={}
        data['auswahl_hauptterminszeit']['hauptterminsuhrzeit'] = self._findElementText('./auswahl_hauptterminszeit/hauptterminsuhrzeit', termin)
        data['auswahl_hauptterminszeit']['hauptterminszeit']    = self._findElementText('./auswahl_hauptterminszeit/hauptterminszeit', termin)
        
        itemsGerichtsort=[
            'gebaeude',
            'stockwerk',
            'raum'            
        ]
        
        data['auswahl_terminsort']                = {}
        data['auswahl_terminsort']['gerichtsort'] = {}
  
        for item in itemsGerichtsort:
            data['auswahl_terminsort']['gerichtsort'][item]        = self._findElementText('./auswahl_terminsort/gerichtsort/' + item, termin)
              
        data['auswahl_terminsort']['gerichtsort']['anschrift']={}
        anschrift=self._findElement("./auswahl_terminsort/gerichtsort/anschrift",termin)
        if anschrift != '':
            data['auswahl_terminsort']['gerichtsort']['anschrift'] = self._parseAnschrift(anschrift)
        
        data['auswahl_terminsort']['lokaltermin'] = {}
        data['auswahl_terminsort']['lokaltermin']['beschreibung']  = self._findElementText('./auswahl_terminsort/lokaltermin/beschreibung' , termin)
        data['auswahl_terminsort']['lokaltermin']['anschrift']={}        
        anschrift=self._findElement("./auswahl_terminsort/lokaltermin/anschrift",termin)
        if anschrift != '':
            data['auswahl_terminsort']['lokaltermin']['anschrift'] = self._parseAnschrift(anschrift)
        
        data['terminszeit']={}
        data['terminszeit']['terminsdatum']                             = self._findElementText('./terminszeit/terminsdatum' , termin)  
        data['terminszeit']['auswahl_terminszeit']={}
        data['terminszeit']['auswahl_terminszeit']['terminsuhrzeit']    = self._findElementText('./terminszeit/auswahl_terminszeit/terminsuhrzeit' , termin)
        data['terminszeit']['auswahl_terminszeit']['terminszeitangabe'] = self._findElementText('./terminszeit/auswahl_terminszeit/terminszeitangabe' , termin)             
        data['terminszeit']['terminsdauer']                             = self._findElementText('./terminszeit/terminsdauer' , termin)       
                 
        data['terminsart'] = self.lookup.xjustizValue ("GDS.Terminsart", self._findElementText("./terminsart", termin, code=True), verNo = self._getListVersion("./terminsart", element=termin))
        
        data['teilnehmer']=[]
        for teilnehmer in self._findAllElements ("./teilnehmer", termin):
            data['teilnehmer'].append(self._parseTerminTeilnehmer(teilnehmer))

        return data
    
    def _parseTerminTeilnehmer(self, teilnehmer):
        data={}
        data['ladungszusatz']    = self._findElementText('./ladungszusatz' , teilnehmer)
        data['ref.rollennummer'] = self._findElementText('./ref.rollennummer' , teilnehmer)

        data['ladungszeit']={}
        data['ladungszeit']['ladungsdatum'] = self._findElementText('./ladungszeit/ladungsdatum' , teilnehmer)
        data['ladungszeit']['ladungsdauer'] = self._findElementText('./ladungszeit/ladungsdauer' , teilnehmer)
        
        data['ladungszeit']['auswahl_ladungszeit']={}
        data['ladungszeit']['auswahl_ladungszeit']['ladungsuhrzeit']    = self._findElementText('./ladungszeit/auswahl_ladungszeit/ladungsuhrzeit' , teilnehmer)
        data['ladungszeit']['auswahl_ladungszeit']['ladungszeitangabe'] = self._findElementText('./ladungszeit/auswahl_ladungszeit/ladungszeitangabe' , teilnehmer)

        return data
    
    def _parseAllValues(self):
        
        
        ####### Nachrichtenkopf (Alle Werte nach Spezifikation 3.2.1 unterstützt) #######
           
        ## Allgemeine Infos
        self.nachricht['erstellungszeitpunkt']   = self._findElementText("./nachrichtenkopf/erstellungszeitpunkt")
        self.nachricht['eigeneID']               = self._findElementText("./nachrichtenkopf/eigeneNachrichtenID")
        self.nachricht['fremdeID']               = self._findElementText("./nachrichtenkopf/fremdeNachrichtenID")
        self.nachricht['prozessID']              = self._findElementText("./nachrichtenkopf/nachrichtenuebergreifenderProzess/prozessID")
        self.nachricht['nachrichtenNummer']      = self._findElementText("./nachrichtenkopf/nachrichtenuebergreifenderProzess/nachrichtenNummer")
        self.nachricht['nachrichtenAnzahl']      = self._findElementText("./nachrichtenkopf/nachrichtenuebergreifenderProzess/nachrichtenAnzahl")
        self.nachricht['produktName']            = self._findElementText("./nachrichtenkopf/herstellerinformation/nameDesProdukts")
        self.nachricht['produktHersteller']      = self._findElementText("./nachrichtenkopf/herstellerinformation/herstellerDesProdukts")
        self.nachricht['produktVersion']         = self._findElementText("./nachrichtenkopf/herstellerinformation/version")
        self.nachricht['sendungsprioritaet']     = self.lookup.xjustizValue ("GDS.Sendungsprioritaet", self._findElementText("./nachrichtenkopf/sendungsprioritaet", code=True), verNo = self._getListVersion("./nachrichtenkopf/sendungsprioritaet"))
    
        self.nachricht['ereignisse']             = ''
        for ereignis in self._findAllElements ("./nachrichtenkopf/ereignis", code=True):
            if len(ereignis.text)>0: 
                ereignisValue=self.lookup.xjustizValue ('GDS.Ereignis', ereignis.text)
                if len(self.nachricht['ereignisse'])>0: self.nachricht['ereignisse'] += ' | ' 
                self.nachricht['ereignisse'] += ereignisValue

        ## Absenderdaten auslesen
        self.absender['aktenzeichen'] = self._getSubTexts("./nachrichtenkopf/aktenzeichen.absender", newline=' | ')

        absenderAuswahl     = self._findElement("./nachrichtenkopf/auswahl_absender")
        
        if   self._tagInAuswahl ('absender.sonstige', absenderAuswahl):
            self.absender["name"]= self._findElementText(".//auswahl_absender/absender.sonstige")
        elif self._tagInAuswahl ('absender.gericht', absenderAuswahl):
            self.absender["name"]= self.lookup.xjustizValue ("GDS.Gerichte", self._findElementText(".//auswahl_absender/absender.gericht", code=True), verNo = self._getListVersion(".//auswahl_absender/absender.gericht"))

        elif self._tagInAuswahl ('absender.rvTraeger', absenderAuswahl):
            self.absender["name"]= self.lookup.xjustizValue ('GDS.RVTraeger', self._findElementText(".//auswahl_absender/absender.rvTraeger", code=True), verNo = self._getListVersion(".//auswahl_absender/absender.rvTraeger"))
        else:
            self.absender["name"]=''
        
        ## Empfängerdaten auslesen
        self.empfaenger['aktenzeichen'] = self._getSubTexts("./nachrichtenkopf/aktenzeichen.empfaenger", newline=' | ')
        
        empfaengerAuswahl       = self._findElement("./nachrichtenkopf/auswahl_empfaenger")
        if   self._tagInAuswahl ('empfaenger.sonstige', empfaengerAuswahl):
            self.empfaenger["name"]  = self._findElementText(".//auswahl_empfaenger/empfaenger.sonstige")
        elif self._tagInAuswahl ('empfaenger.gericht', empfaengerAuswahl):
            self.empfaenger["name"]  = self.lookup.xjustizValue ('GDS.Gerichte', self._findElementText(".//auswahl_empfaenger/empfaenger.gericht", code=True), verNo = self._getListVersion(".//auswahl_empfaenger/empfaenger.gericht"))
        elif self._tagInAuswahl ('empfaenger.rvTraeger', empfaengerAuswahl):
            self.empfaenger["name"]  = self.lookup.xjustizValue ('GDS.RVTraeger', self._findElementText(".//auswahl_empfaenger/empfaenger.rvTraeger", code=True), verNo = self._getListVersion(".//auswahl_empfaenger/empfaenger.rvTraeger"))
        else:
            self.empfaenger["name"]  = ''
        
        ####### Grunddaten #######

        self.grunddaten['verfahrensnummer'] = self._findElementText("./grunddaten/verfahrensdaten/verfahrensnummer")

        ## Beteiligungen ##

        self.grunddaten['beteiligung']=[]
        for beteiligung in self._findAllElements ("./grunddaten/verfahrensdaten/beteiligung"):
            self.grunddaten['beteiligung'].append(self._parseBeteiligung(beteiligung))

        ## Instanzdaten ##
        self.grunddaten['instanzen']={}
        simpleValues=(  
                    'instanznummer',
                    'sachgebietszusatz',
                    'abteilung',
                    'verfahrensinstanznummer',
                    'kurzrubrum'            
                )
        for instanz in self._findAllElements ("./grunddaten/verfahrensdaten/instanzdaten"):    
            instanzData={}
            for simpleValue in simpleValues:
                instanzData[simpleValue] = self._findElementText('.//'+simpleValue, instanz)

            instanzData['sachgebiet']    = self.lookup.xjustizValue ("GDS.Sachgebiet", self._findElementText(".//sachgebiet", element=instanz, code=True), verNo = self._getListVersion(".//sachgebiet", element=instanz))

            instanzData['verfahrensgegenstand']=[]
            for gegenstand in self._findAllElements ("./verfahrensgegenstand", instanz): 
                instanzData['verfahrensgegenstand'].append(self._parseVerfahrensgegenstand(gegenstand))

            instanzData['telekommunikation']=[]
            for telekomEintrag in self._findAllElements ("./telekommunikation", instanz): 
                instanzData['telekommunikation'].append(self._parseTelekommunikation(telekomEintrag))
            
            instanzData['aktenzeichen']=[]
            if self._findElement("./aktenzeichen", instanz)!='':
                instanzData['aktenzeichen']=self._parseAktenzeichen(self._findElement("./aktenzeichen", instanz))

            instanzData['auswahl_instanzbehoerde']=self._parseBehoerde(self._findElement("./auswahl_instanzbehoerde", instanz))

            self.grunddaten['instanzen'][instanzData['instanznummer']]=instanzData


        ## Terminsdaten ##
        self.termine=self._getTermine()
        
        ####### Schriftgutobjekte #######

        self.schriftgutobjekte['anschreiben'] = self._findElementText("./schriftgutobjekte/anschreiben/ref.sgo")
        self.schriftgutobjekte['dokumente']   = self._parseDokumente()
        self.schriftgutobjekte['akten']       = self._parseAkten()

    def _getTermine(self):
        termine=[]
        for termin in self._findAllElements ("./grunddaten/verfahrensdaten/auswahl_termin/terminsdaten"):
            termine.append(self._parseTermin(termin))
        for fortsetzungstermin in self._findAllElements ("./grunddaten/verfahrensdaten/auswahl_termin/fortsetzungsterminsdaten"):
            termine.append(self._parseTermin(fortsetzungstermin))
        return termine
    
    #Gibt alle Dokumente einer Akte zurück. 
    #Ohne ID werden die Dokumente der obersten Ebene zurückgegeben  
    def getDocuments(self, aktenID=None):
        documents={}
        if aktenID is None:
            if self.schriftgutobjekte['dokumente']:
                documents=self.schriftgutobjekte['dokumente']
        elif self.schriftgutobjekte['akten']:
            documents=self._findDocsInAktenbaum(self.schriftgutobjekte['akten'], aktenID)
                    
        return documents     
       
    
    #Gibt Liste der Dateien inkl. der übergeordneten Dokumentenmetadaten aus
    def getFileRows(self, aktenID=None):
        # Eine AktenID wurde angegeben
        if aktenID:
            documents=self.getDocuments(aktenID)        
        # Akten ID "None" oder '' zeigt oberste Ebene "Schriftgutobjekte" an
        else:
            documents=self.schriftgutobjekte.get('dokumente')
        
        fileRows=[]
        if documents:
            for document in documents.values():
                document = document.copy()                
                dateien  = document.pop('dateien')
                for datei in dateien:
                    datei.update(document)
                    fileRows.append(datei)                   
                 
        return fileRows
     
    def _findDocsInAktenbaum(self, aktenDict, aktenID):
        documents={}
        for file in aktenDict.values():
            if file['id']==aktenID:
                if file['dokumente']:
                    documents=file['dokumente']   
                    break 
            elif len(file['teilakten'])>0:
                documents=self._findDocsInAktenbaum(file['teilakten'], aktenID)
                if documents:
                    break
            
        return documents
      
    def getAkte(self, aktenDict, aktenID):
        akte={}
        for einzelakte in aktenDict.values():
            if einzelakte['id']==aktenID:
                return einzelakte 
            elif len(einzelakte['teilakten'])>0:
                akte=self.getAkte(einzelakte['teilakten'], aktenID)
                if akte:
                    break              
        return akte

class parser331(parser321):
    def __init__(self, filename=None):
        super().__init__(filename)
      
    def _parseAnschrift(self, node):
        anschrift={}
        simpleValues=(
            'strasse',
            'hausnummer',
            'postfachnummer',
            'postleitzahl',
            'ort',
            'ortsteil',
            'wohnungsgeber',
            'derzeitigerAufenthalt',
            'ehemaligeAnschrift',
            'erfassungsdatum',
            'ort.unbekannt',
            'postleitzahl.unbekannt'             
        )
        for value in simpleValues:
            anschrift[value]=self._findElementText('./' + value, node)
        
        anschrift['anschriftenzusatz']=[]
        for zusatz in self._findAllElements ("./anschriftenzusatz", node): 
            anschrift['anschriftenzusatz'].append(zusatz.text)
        
        anschrift['anschriftstyp']=self.lookup.xjustizValue ('GDS.Anschriftstyp', self._findElementText("./anschriftstyp", node, code=True), verNo = self._getListVersion("./anschriftstyp", element=node))
        
        anschrift['staat']      = self._parseStaat     (self._findElement("./staat", node))
        anschrift['bundesland'] = self._parseBundesland(self._findElement("./auswahl_bundesland", node))
                    
        #Set default values as defined in the specification if empty
        if anschrift['ort.unbekannt']=='':
            anschrift['ort.unbekannt']='true'
        
        if anschrift['ort.unbekannt']=='':
            anschrift['ort.unbekannt']='true'
        
        if anschrift['ehemaligeAnschrift']=='':
            anschrift['ehemaligeAnschrift']='false'
        
        if anschrift['derzeitigerAufenthalt']=='':
            anschrift['derzeitigerAufenthalt']='false'
            
        return anschrift
        
    def _parseAktenzeichen(self, aktenzeichen):
        aktenzeichenParts={}
        aktenzeichenParts['az.art']                      =self.lookup.xjustizValue ("GDS.Aktenzeichenart", self._findElementText("./az.art", element=aktenzeichen, code=True), verNo = self._getListVersion("./az.art", element=aktenzeichen))
        aktenzeichenParts['auswahl_az.vergebendeStation']=[]
        if self._findElement("./auswahl_az.vergebendeStation", element=aktenzeichen)!='':
            aktenzeichenParts['auswahl_az.vergebendeStation']=self._parseBehoerde(self._findElement("./auswahl_az.vergebendeStation", element=aktenzeichen))
           
        aktenzeichenParts['sammelvorgangsnummer']        =self._findElementText("./sammelvorgangsnummer", element=aktenzeichen) 
        
        aktenzeichenParts['aktenzeichen.freitext']       =self._findElementText("./auswahl_aktenzeichen/aktenzeichen.freitext", element=aktenzeichen) 
        if len(aktenzeichenParts['aktenzeichen.freitext'])==0:
            aktenzeichenStrukturiert={}
            aktenzeichenElements=(  
                'sachgebietsschluessel',
                'zusatzkennung',
                'abteilung',
                'laufendeNummer',
                'jahr',
                'vorsatz',
                'zusatz',
                'dezernat',
                'erfassungsdatum'                       
            )
            for elementName in aktenzeichenElements:
                aktenzeichenStrukturiert[elementName]=self._findElementText(".//" + elementName, element=aktenzeichen)
            aktenzeichenStrukturiert['register']     =self.lookup.xjustizValue ("GDS.Registerzeichen", self._findElementText(".//register", element=aktenzeichen, code=True), verNo = self._getListVersion(".//register", element=aktenzeichen))
            aktenzeichenParts['aktenzeichen.strukturiert']=aktenzeichenStrukturiert
            
            aktenzeichenFreitext="%s %s %s %s/%s %s" % (aktenzeichenStrukturiert['vorsatz'],
                                                        aktenzeichenStrukturiert['abteilung'],
                                                        aktenzeichenStrukturiert['register'],
                                                        aktenzeichenStrukturiert['laufendeNummer'],
                                                        aktenzeichenStrukturiert['jahr'],
                                                        aktenzeichenStrukturiert['zusatz'])
            
            if aktenzeichenFreitext.strip() != '/':
                aktenzeichenParts['aktenzeichen.freitext']=aktenzeichenFreitext 
        
        return aktenzeichenParts

    def _parseDokumente(self, path='./schriftgutobjekte/dokument', element=None):
        element = self._root if element is None else element
        documents={}
        documentNodes= self._findAllElements(path, element)
        if documentNodes != '':
            simpleValues=(  
                'id',
                'nummerImUebergeordnetenContainer',
                'fremdesGeschaeftszeichen',
                'posteingangsdatum',
                'datumDesSchreibens',
                'veraktungsdatum',
                'scanDatum',
                'anzeigename',
                'akteneinsicht',
                'absenderAnzeigename',
                'adressatAnzeigename',
                'justizkostenrelevanz',
                'ruecksendungEEB.erforderlich',
                'zustellung41StPO',
                'nurMetadaten',
                'ersteSeitennummer',
                'letzteSeitennummer',
                'erstellungszeitpunkt'
            )
            for documentNode in documentNodes:
                document={}
                for simpleValue in simpleValues:
                    document[simpleValue]=self._findElementText('.//'+simpleValue, documentNode)
                document['vertraulichkeitsstufe']=self.lookup.xjustizValue ("GDS.Vertraulichkeitsstufe", self._findElementText(".//vertraulichkeitsstufe", element=documentNode , code=True), verNo = self._getListVersion(".//vertraulichkeitsstufe", element=documentNode )) 
                document['dokumentklasse']       =self.lookup.xjustizValue ("GDS.Dokumentklasse", self._findElementText(".//dokumentklasse", element=documentNode , code=True), verNo = self._getListVersion(".//dokumentklasse", element=documentNode )) 
                document['dokumententyp']        =self.lookup.xjustizValue ("GDS.Dokumenttyp", self._findElementText(".//dokumententyp", element=documentNode , code=True), verNo = self._getListVersion(".//dokumententyp", element=documentNode ))  
                
                document['personen']=[]
                for person in self._findAllElements('.//person/ref.beteiligtennummer', element=documentNode):
                    document['personen'].append(person.text)
                
                document['verweise']=[]
                for verweis in self._findAllElements('.//verweis', element=documentNode):
                    verweisParts={}
                    verweisParts['anzeigenameSGO']=self._findElementText('./anzeigenameSGO', element=verweis)
                    verweisParts['id.sgo']        =self._findElementText('./id.sgo', element=verweis)
                    verweisParts['verweistyp']    =self.lookup.xjustizValue ("GDS.Verweistyp", self._findElementText("./verweistyp", element=verweis , code=True), verNo = self._getListVersion("./verweistyp", element=verweis ))   
                    document['verweise'].append(verweisParts)
                
                document['dateien']=[]
                for datei in self._findAllElements('.//datei', element=documentNode):
                    dateiData={}
                    dateiData['dateiname']     =self._findElementText('./dateiname', element=datei)
                    dateiData['versionsnummer']=self._findElementText('./versionsnummer', element=datei)
                    dateiData['bestandteil']   =self.lookup.xjustizValue ('GDS.Bestandteiltyp', self._findElementText("./bestandteil", element=datei , code=True), verNo = self._getListVersion("./bestandteil", element=datei))  
                    
                    dateiData['dateiname.bezugsdatei']=[]
                    for bezugsdatei in self._findAllElements ('./dateiname.bezugsdatei', element=datei):
                        dateiData['dateiname.bezugsdatei'].append(bezugsdatei.text)
                    
                    document['dateien'].append(dateiData)
                
                documents[document['id']]=document
        return documents

    def _parseAkten(self, path='./schriftgutobjekte/akte', element=None):
        element = self._root if element is None else element
        
        files={}
        fileNodes= self._findAllElements(path, element)
        if fileNodes != '':
            simpleValues=(  
                './anzeigename',
                './identifikation/id',
                './identifikation/nummerImUebergeordnetenContainer',
                './xjustiz.fachspezifischeDaten/anzeigename',
                './xjustiz.fachspezifischeDaten/weiteresOrdnungskriteriumBehoerde',
                './xjustiz.fachspezifischeDaten/erstellungszeitpunktAkteVersand',
                './xjustiz.fachspezifischeDaten/ruecksendungEEB.erforderlich',
                './xjustiz.fachspezifischeDaten/zustellung41StPO',
                # teilaktenspezifisch
                './xjustiz.fachspezifischeDaten/akteneinsicht',
                './xjustiz.fachspezifischeDaten/letztePaginierungProTeilakte',
                './justizinterneDaten/roemischPaginiert'
            )
            for fileNode in fileNodes:
                file={}
                for simpleValue in simpleValues:
                    file[simpleValue.rsplit('/', 1)[1]]=self._findElementText(simpleValue, fileNode)
            
                file['dokumente']            = self._parseDokumente('./xjustiz.fachspezifischeDaten/inhalt/dokument', fileNode)
                file['teilakten']            = self._parseAkten('./xjustiz.fachspezifischeDaten/inhalt/teilakte', fileNode)
                file['abgebendeStelle']      = self.lookup.xjustizValue ("GDS.Gerichte", self._findElementText("./xjustiz.fachspezifischeDaten/abgebendeStelle", element=fileNode, code=True), verNo = self._getListVersion("./xjustiz.fachspezifischeDaten/abgebendeStelle", element=fileNode))
                file['aktentyp']             = self.lookup.xjustizValue ("GDS.Aktentyp", self._findElementText("./xjustiz.fachspezifischeDaten/aktentyp", element=fileNode, code=True), verNo = self._getListVersion("./xjustiz.fachspezifischeDaten/aktentyp", element=fileNode))
                file['vertraulichkeitsstufe']= self.lookup.xjustizValue ("GDS.Vertraulichkeitsstufe", self._findElementText("./vertraulichkeitsstufe", element=fileNode , code=True), verNo = self._getListVersion("./vertraulichkeitsstufe", element=fileNode ))
                
                file['personen']=[]
                for person in self._findAllElements ('./xjustiz.fachspezifischeDaten/person/ref.beteiligtennummer', element=fileNode):
                        file['personen'].append(person.text)
                
                file['laufzeit']={}
                for laufzeit in self._findElement ('./laufzeit', element=fileNode):
                    # remove namespace and use tag as key
                    file['laufzeit'][laufzeit.tag.rsplit("}", 1)[1]]=laufzeit.text
                
                file['aktenreferenzen']=[]
                for aktenreferenz in self._findAllElements ('./xjustiz.fachspezifischeDaten/aktenreferenzen', element=fileNode):
                    referenceParts={}
                    referenceParts['id.referenzierteAkte']=self._findElementText("./id.referenzierteAkte", element=aktenreferenz)
                    referenceParts['aktenreferenzart']    =self.lookup.xjustizValue ("GDS.Aktenreferenzart", self._findElementText("./aktenreferenzart", element=aktenreferenz, code=True), verNo = self._getListVersion("./aktenreferenzart", element=aktenreferenz))
                    file['aktenreferenzen'].append(referenceParts)
                
                file['aktenzeichen']=[]
                for aktenzeichen in self._findAllElements ('./xjustiz.fachspezifischeDaten/aktenzeichen', element=fileNode):
                    file['aktenzeichen'].append(self._parseAktenzeichen(aktenzeichen))
                
                # Teilaktenspezifisch
                file['teilaktentyp']=self.lookup.xjustizValue ("GDS.Teilaktentyp", self._findElementText("./xjustiz.fachspezifischeDaten/teilaktentyp", element=fileNode, code=True), verNo = self._getListVersion("./xjustiz.fachspezifischeDaten/teilaktentyp", element=fileNode))
                
                files[file['id']]=file
                self.alleAktenIDs.append(file['id'])
                
        return files

    def _parseBankverbindung(self, bankverbindung):
        data={}
        items=(
            'bankverbindungsnummer',
            'bank',
            'kontoinhaber',
            'iban',
            'bic',
            'sepa-mandat',
            'verwendungszweck'
        )

        for item in items:
            data[item]=self._findElementText('.//'+item, bankverbindung)
        
        data['sepa-basislastschrift'] = {}
        eintrag                       = self._findElement ("./sepa-basislastschrift", bankverbindung)
        if eintrag is not None:
            data['sepa-basislastschrift']['lastschrifttyp']  = self.lookup.xjustizValue ("GDS.Lastschrifttyp", self._findElementText(".//lastschrifttyp", bankverbindung, code=True), verNo = self._getListVersion(".//lastschrifttyp", element=bankverbindung))
            data['sepa-basislastschrift']['mandatsreferenz'] = self._findElementText('.//mandatsreferenz', bankverbindung)
            data['sepa-basislastschrift']['mandatsdatum']    = self._findElementText('.//mandatsdatum'   , bankverbindung)

        if not data['sepa-mandat']:
            data['sepa-mandat']='false'
        
        return data
 
    def _parseOrganisation(self, node):
        orgData={}
        orgData['type']='GDS.Organisation'
        orgData['bezeichnung.aktuell']=self._findElementText('./bezeichnung/bezeichnung.aktuell', node)
        orgData['kurzbezeichnung']    =self._findElementText('./kurzbezeichnung', node)
        orgData['bundeseinheitlicheWirtschaftsnummer']    =self._findElementText('./bundeseinheitlicheWirtschaftsnummer', node)
        orgData['bezeichnung.alt']=[]
        for bezeichnung in self._findAllElements ('./bezeichnung/bezeichnung.alt', node): 
            orgData['bezeichnung.alt'].append(bezeichnung.text)
        
        orgData['anschrift']=[]
        for anschrift in self._findAllElements ("./anschrift", node): 
            orgData['anschrift'].append(self._parseAnschrift(anschrift)) 
        
        orgData['angabenZurRechtsform']={}
        rechtsform = self._findElement('./angabenZurRechtsform', node)
        if rechtsform != '':
            orgData['angabenZurRechtsform']=self._parseRechtsform(rechtsform)
        
        orgData['geschlecht']    = self.lookup.xjustizValue ('GDS.Geschlecht', self._findElementText("./geschlecht", node, code=True), verNo = self._getListVersion("./geschlecht", element=node))
        
        orgData['telekommunikation']=[]
        for telekom in self._findAllElements ("./telekommunikation", node): 
            orgData['telekommunikation'].append(self._parseTelekommunikation(telekom))
              
        orgData['bankverbindung']=[]
        for bankverbindung in self._findAllElements ("./bankverbindung", node):
            orgData['bankverbindung'].append(self._parseBankverbindung(bankverbindung))
        
        orgData['umsatzsteuerID'] = self._findElementText('./umsatzsteuerID', node)
        
        orgData['registereintragung']={}
        registereintragung = self._findElement('./registereintragung', node)
        if registereintragung != '':
            orgData['registereintragung']=self._parseRegistrierung(registereintragung)
        
        orgData['sitz']=[]
        for sitz in self._findAllElements ("./sitz", node):
            orgData['sitz'].append(self._parseSitz(sitz))
       
        return orgData

    def _parseKanzlei(self, node):
        kanzleiData={}
        kanzleiData['type']='GDS.RA.Kanzlei'
        kanzleiData['bezeichnung.aktuell']=self._findElementText('./bezeichnung/bezeichnung.aktuell', node)
        kanzleiData['bezeichnung.alt']=[]
        for bezeichnung in self._findAllElements ('./bezeichnung/bezeichnung.alt', node): 
            kanzleiData['bezeichnung.alt'].append(bezeichnung.text)
        
        kanzleiData['anschrift']=[]
        for anschrift in self._findAllElements ("./anschrift", node): 
            kanzleiData['anschrift'].append(self._parseAnschrift(anschrift)) 
        
        kanzleiData['geschlecht'] =self.lookup.xjustizValue ('GDS.Geschlecht', self._findElementText("./geschlecht", node, code=True), verNo = self._getListVersion("./geschlecht", element=node))
        kanzleiData['rechtsform'] = self._parseRechtsform(node)['rechtsform']
        kanzleiData['kanzleiform']=self.lookup.xjustizValue ("GDS.Kanzleiform", self._findElementText("./kanzleiform", node, code=True), verNo = self._getListVersion("./kanzleiform", element=node))
        
        kanzleiData['telekommunikation']=[]
        for telekom in self._findAllElements ("./telekommunikation", node): 
            kanzleiData['telekommunikation'].append(self._parseTelekommunikation(telekom))
        
        kanzleiData['raImVerfahren']=[]
        if self._findElement('./raImVerfahren', node)!='':
            kanzleiData['raImVerfahren']=self._parseNatuerlichePerson(self._findElement('./raImVerfahren', node))
        
        kanzleiData['umsatzsteuerID']= self._findElementText('./umsatzsteuerID', node)
        
        kanzleiData['bankverbindung']=[]
        for bankverbindung in self._findAllElements ("./bankverbindung", node):
            kanzleiData['bankverbindung'].append(self._parseBankverbindung(bankverbindung))
        
        return kanzleiData

    def _parseNatuerlichePerson(self, node):
        personData={}
        personData['type']='GDS.NatuerlichePerson'
        personData['vollerName']=self._parseNameNatuerlichePerson(self._findElement('./vollerName', node))
        
        personData['aliasNatuerlichePerson']=[]
        for alias in self._findAllElements ("./aliasNatuerlichePerson", node): 
            personData['aliasNatuerlichePerson'].append(self._parseNatuerlichePerson(alias))
        
        personData['umsatzsteuerID']= self._findElementText('./umsatzsteuerID', node)
        personData['bundeseinheitlicheWirtschaftsnummer']= self._findElementText('./bundeseinheitlicheWirtschaftsnummer', node)
        
        personData['geschlecht']    =self.lookup.xjustizValue ('GDS.Geschlecht', self._findElementText("./geschlecht", node, code=True), verNo = self._getListVersion("./geschlecht", element=node))
        personData['familienstand'] =self.lookup.xjustizValue ('GDS.Familienstand', self._findElementText("./familienstand", node, code=True), verNo = self._getListVersion("./familienstand", element=node))
        personData['personalstatut']=self.lookup.xjustizValue ('GDS.Personalstatut', self._findElementText("./personalstatut", node, code=True), verNo = self._getListVersion("./personalstatut", element=node))
        
        personData['beruf']=[]
        for beruf in self._findAllElements ("./beruf", node): 
            personData['beruf'].append(beruf.text)
        
        personData['telekommunikation']=[]
        for telekom in self._findAllElements ("./telekommunikation", node): 
            personData['telekommunikation'].append(self._parseTelekommunikation(telekom))
            
        personData['anschrift']=[]
        for anschrift in self._findAllElements ("./anschrift", node): 
            personData['anschrift'].append(self._parseAnschrift(anschrift))    
        
        personData['zustaendigeInstitution']=[]
        for institution in self._findAllElements ("./zustaendigeInstitution/ref.rollennummer", node): 
            personData['zustaendigeInstitution'].append(institution.text)      
        
        personData['staatsangehoerigkeit']=[]
        for staat in self._findAllElements ("./staatsangehoerigkeit", node):
            if staat is not None:
                personData['staatsangehoerigkeit'].append(self._parseStaat (staat))              
                       
        personData['herkunftsland']=[]
        for staat in self._findAllElements ("./herkunftsland", node):
            if staat is not None:
                personData['herkunftsland'].append(self._parseStaat (staat))                                          
        
        personData['sprache']=[]
        for sprache in self._findAllElements ("./sprache", node, code=True):
            personData['sprache'].append(self.lookup.xjustizValue ('GDS.Sprachen', sprache.text))
        
        personData['bankverbindung']=[]
        for bankverbindung in self._findAllElements ("./bankverbindung", node):
            personData['bankverbindung'].append(self._parseBankverbindung(bankverbindung))
               
        personData['registereintragungNatuerlichePerson']=[]
        registereintragung=self._findElement('./registereintragungNatuerlichePerson', node)
        if registereintragung != '':
            personData['registereintragungNatuerlichePerson']=self._parseRegistereintragungNatuerlichePerson(registereintragung)
        
        personData['tod']=[]
        tod=self._findElement('./tod', node)
        if tod != '':
            personData['tod']=self._parseTod(tod)
            
        personData['geburt']=[]
        geburt=self._findElement('./geburt', node)
        if geburt != '':
            personData['geburt']=self._parseGeburt(geburt)
                    
        personData['auswahl_auskunftssperre']=[]
        auskunftssperre=self._findElement('./auswahl_auskunftssperre', node)
        if auskunftssperre != '':
            personData['auswahl_auskunftssperre']=self._parseAuskunftssperre(auskunftssperre)
        
        personData['ausweisdokument']=[]
        for dokument in self._findAllElements ("./ausweisdokument", node): 
            personData['ausweisdokument'].append(self._parseAusweisdokument(dokument))
                
        return personData
        
    def _parseBundesland(self, bundesland):
        bundeslandBRD      = self.lookup.xjustizValue ("Bundesland", self._findElementText(".//bundesland.BRD", bundesland, code=True), verNo = self._getListVersion(".//bundesland.BRD", element=bundesland))
        bundeslandFreitext = self._findElementText(".//bundesland.freitext", bundesland)

        if bundeslandBRD:
            return bundeslandBRD
        elif bundeslandFreitext:
            return bundeslandFreitext
        else:
            return ''
      
    def _parseZeitraum(self, zeitraum):
        zeitraumData={}
        zeitraumData['beginn'] = self._findElementText('.//beginn', zeitraum)
        zeitraumData['ende']   = self._findElementText('.//ende'  , zeitraum)
        return zeitraumData      
        
    def _parseAusweisdokument(self, ausweisdokument):
        ausweisData                         = {}
        ausweisData['ausweis.ID']           = self._findElementText('./ausweis.ID', ausweisdokument)
        ausweisData['zusatzinformation']    = self._findElementText('./zusatzinformation', ausweisdokument)
        ausweisData['ausweisart']           = self.lookup.xjustizValue ("GDS.Ausweisart", self._findElementText("./ausweisart", ausweisdokument, code=True), verNo = self._getListVersion("./ausweisart", element=ausweisdokument))
        ausweisData['ausstellenderStaat']   = self._parseStaat   (self._findElement("./ausstellenderStaat", ausweisdokument))
        ausweisData['ausstellendeBehoerde'] = self._parseBehoerde(self._findElement("./ausstellendeBehoerde", ausweisdokument))
        ausweisData['gueltigkeit']          = self._parseZeitraum(self._findElement("./gueltigkeit", ausweisdokument))
        return ausweisData
   
    def _parseAbsenderEmpfaenger(self, type):
        aktenzeichen = self._getSubTexts(f'./nachrichtenkopf/aktenzeichen.{type}', newline=' | ')

        auswahl     = self._findElement(f'./nachrichtenkopf/auswahl_{type}')
        
        if   self._tagInAuswahl (f'{type}.sonstige', auswahl):
            name = self._findElementText(f'.//auswahl_{type}/{type}.sonstige')
        elif self._tagInAuswahl (f'{type}.gericht', auswahl):
            name = self.lookup.xjustizValue ("GDS.Gerichte", self._findElementText(f'.//auswahl_{type}/{type}.gericht', code=True), verNo = self._getListVersion(f'.//auswahl_{type}/{type}.gericht'))
        elif self._tagInAuswahl (f'{type}.rvTraeger', auswahl):
            name = self.lookup.xjustizValue ('GDS.RVTraeger', self._findElementText(f'.//auswahl_{type}/{type}.rvTraeger', code=True), verNo = self._getListVersion(f'.//auswahl_{type}/{type}.rvTraeger'))
        else:
            name = ''
        
        return (name, aktenzeichen)
      
    def _parseNachrichtenkopfBasics(self):  
        ####### Nachrichtenkopf (Alle Werte nach Spezifikation 3.3.1 unterstützt) #######
              
        self.nachricht['erstellungszeitpunkt']   = self._findElementText("./nachrichtenkopf/erstellungszeitpunkt")
        self.nachricht['eigeneID']               = self._findElementText("./nachrichtenkopf/eigeneNachrichtenID")
        self.nachricht['fremdeID']               = self._findElementText("./nachrichtenkopf/fremdeNachrichtenID")
        self.nachricht['prozessID']              = self._findElementText("./nachrichtenkopf/nachrichtenuebergreifenderProzess/prozessID")
        self.nachricht['nachrichtenNummer']      = self._findElementText("./nachrichtenkopf/nachrichtenuebergreifenderProzess/nachrichtenNummer")
        self.nachricht['nachrichtenAnzahl']      = self._findElementText("./nachrichtenkopf/nachrichtenuebergreifenderProzess/nachrichtenAnzahl")
        self.nachricht['produktName']            = self._findElementText("./nachrichtenkopf/herstellerinformation/nameDesProdukts")
        self.nachricht['produktHersteller']      = self._findElementText("./nachrichtenkopf/herstellerinformation/herstellerDesProdukts")
        self.nachricht['produktVersion']         = self._findElementText("./nachrichtenkopf/herstellerinformation/version")
        self.nachricht['sendungsprioritaet']     = self.lookup.xjustizValue ("GDS.Sendungsprioritaet", self._findElementText("./nachrichtenkopf/sendungsprioritaet", code=True), verNo = self._getListVersion("./nachrichtenkopf/sendungsprioritaet"))
    
        self.nachricht['ereignisse']             = ''
        for ereignis in self._findAllElements ("./nachrichtenkopf/ereignis", code=True):
            if len(ereignis.text)>0: 
                ereignisValue=self.lookup.xjustizValue ('GDS.Ereignis', ereignis.text)
                if len(self.nachricht['ereignisse'])>0: self.nachricht['ereignisse'] += ' | ' 
                self.nachricht['ereignisse'] += ereignisValue
        
        self.nachricht['vertraulichkeit']                          = {}
        self.nachricht['vertraulichkeit']['vertraulichkeitsstufe'] = self.lookup.xjustizValue ('GDS.Vertraulichkeitsstufe', self._findElementText("./nachrichtenkopf/vertraulichkeit/vertraulichkeitsstufe", code=True), verNo = self._getListVersion("./nachrichtenkopf/vertraulichkeit/vertraulichkeitsstufe"))
        self.nachricht['vertraulichkeit']['vertraulichkeitsgrund'] = self._findElementText("./nachrichtenkopf/vertraulichkeit/vertraulichkeitsgrund")
        
        return self.nachricht
               
    def _parseAllValues(self):
        ## Allgemeine Infos        
        self.nachricht = self._parseNachrichtenkopfBasics()
 
        ## Absenderdaten auslesen
        self.absender['name'], self.absender['aktenzeichen'] = self._parseAbsenderEmpfaenger('absender')
        
        ## Empfängerdaten auslesen
        self.empfaenger['name'], self.empfaenger['aktenzeichen'] = self._parseAbsenderEmpfaenger('empfaenger')
        
        ####### Grunddaten #######

        self.grunddaten['verfahrensnummer'] = self._findElementText("./grunddaten/verfahrensdaten/verfahrensnummer")

        ## Beteiligungen ##

        self.grunddaten['beteiligung']=[]
        for beteiligung in self._findAllElements ("./grunddaten/verfahrensdaten/beteiligung"):
            self.grunddaten['beteiligung'].append(self._parseBeteiligung(beteiligung))

        ## Instanzdaten ##
        self.grunddaten['instanzen']={}
        simpleValues=(  
                    'instanznummer',
                    'sachgebietszusatz',
                    'abteilung',
                    'verfahrensinstanznummer',
                    'kurzrubrum'            
                )
        for instanz in self._findAllElements ("./grunddaten/verfahrensdaten/instanzdaten"):    
            instanzData={}
            for simpleValue in simpleValues:
                instanzData[simpleValue] = self._findElementText('.//'+simpleValue, instanz)

            instanzData['sachgebiet']    = self.lookup.xjustizValue ("GDS.Sachgebiet", self._findElementText(".//sachgebiet", element=instanz, code=True), verNo = self._getListVersion(".//sachgebiet", element=instanz))

            instanzData['verfahrensgegenstand']=[]
            for gegenstand in self._findAllElements ("./verfahrensgegenstand", instanz): 
                instanzData['verfahrensgegenstand'].append(self._parseVerfahrensgegenstand(gegenstand))

            instanzData['telekommunikation']=[]
            for telekomEintrag in self._findAllElements ("./telekommunikation", instanz): 
                instanzData['telekommunikation'].append(self._parseTelekommunikation(telekomEintrag))
                
            instanzData['aktenzeichen']=[]
            if self._findElement("./aktenzeichen", instanz)!='':
                instanzData['aktenzeichen']=self._parseAktenzeichen(self._findElement("./aktenzeichen", instanz))

            instanzData['auswahl_instanzbehoerde']=self._parseBehoerde(self._findElement("./auswahl_instanzbehoerde", instanz))

            #self.grunddaten['instanzen'].append({instanzData['instanznummer']:instanzData})
            self.grunddaten['instanzen'][instanzData['instanznummer']]=instanzData

        ## Terminsdaten ##
        self.termine=self._getTermine()
        
        ####### Schriftgutobjekte #######

        self.schriftgutobjekte['anschreiben'] = self._findElementText("./schriftgutobjekte/anschreiben/ref.sgo")
        self.schriftgutobjekte['dokumente']   = self._parseDokumente()
        self.schriftgutobjekte['akten']       = self._parseAkten()

class parser341(parser331):  
    def __init__(self, filename=None):
        super().__init__(filename)
                   
    def _parseAkten(self, path='./schriftgutobjekte/akte', element=None):
        element = self._root if element is None else element
        
        files={}
        fileNodes= self._findAllElements(path, element)
        if fileNodes != '':
            simpleValues=(  
                './anzeigename',
                './identifikation/id',
                './identifikation/nummerImUebergeordnetenContainer',
                './xjustiz.fachspezifischeDaten/anzeigename',
                './xjustiz.fachspezifischeDaten/weiteresOrdnungskriteriumBehoerde',
                './xjustiz.fachspezifischeDaten/erstellungszeitpunktAkteVersand',
                './xjustiz.fachspezifischeDaten/ruecksendungEEB.erforderlich',
                './justizinterneDaten/zustellung41StPO',
                './justizinterneDaten/uebergabeAktenfuehrungsbefugnis',
                # teilaktenspezifisch
                './xjustiz.fachspezifischeDaten/akteneinsicht',
                './xjustiz.fachspezifischeDaten/letztePaginierungProTeilakte',
                './justizinterneDaten/roemischPaginiert'
            )
            for fileNode in fileNodes:
                file={}
                for simpleValue in simpleValues:
                    file[simpleValue.rsplit('/', 1)[1]]=self._findElementText(simpleValue, fileNode)

               
                file['dokumente']            = self._parseDokumente('./xjustiz.fachspezifischeDaten/inhalt/dokument', fileNode)
                file['teilakten']            = self._parseAkten('./xjustiz.fachspezifischeDaten/inhalt/teilakte', fileNode)
                file['abgebendeStelle']      = self.lookup.xjustizValue ("GDS.Gerichte", self._findElementText("./xjustiz.fachspezifischeDaten/abgebendeStelle", element=fileNode, code=True), verNo = self._getListVersion("./xjustiz.fachspezifischeDaten/abgebendeStelle", element=fileNode))
                file['aktentyp']             = self.lookup.xjustizValue ("GDS.Aktentyp", self._findElementText("./xjustiz.fachspezifischeDaten/aktentyp", element=fileNode, code=True), verNo = self._getListVersion("./xjustiz.fachspezifischeDaten/aktentyp", element=fileNode))
                file['vertraulichkeitsstufe']= self.lookup.xjustizValue ("GDS.Vertraulichkeitsstufe", self._findElementText("./vertraulichkeitsstufe", element=fileNode , code=True), verNo = self._getListVersion("./vertraulichkeitsstufe", element=fileNode ))
                
                file['personen']=[]
                for person in self._findAllElements ('./xjustiz.fachspezifischeDaten/person/ref.beteiligtennummer', element=fileNode):
                        file['personen'].append(person.text)
                
                file['laufzeit']={}
                for laufzeit in self._findElement ('./laufzeit', element=fileNode):
                    # remove namespace and use tag as key
                    file['laufzeit'][laufzeit.tag.rsplit("}", 1)[1]]=laufzeit.text
                
                file['aktenreferenzen']=[]
                for aktenreferenz in self._findAllElements ('./xjustiz.fachspezifischeDaten/aktenreferenzen', element=fileNode):
                    referenceParts={}
                    referenceParts['id.referenzierteAkte']=self._findElementText("./id.referenzierteAkte", element=aktenreferenz)
                    referenceParts['aktenreferenzart']    =self.lookup.xjustizValue ("GDS.Aktenreferenzart", self._findElementText("./aktenreferenzart", element=aktenreferenz, code=True), verNo = self._getListVersion("./aktenreferenzart", element=aktenreferenz))
                    file['aktenreferenzen'].append(referenceParts)
                
                file['aktenzeichen']=[]
                for aktenzeichen in self._findAllElements ('./xjustiz.fachspezifischeDaten/aktenzeichen', element=fileNode):
                    file['aktenzeichen'].append(self._parseAktenzeichen(aktenzeichen))
                
                # Teilaktenspezifisch
                file['teilaktentyp']=self.lookup.xjustizValue ("GDS.Teilaktentyp", self._findElementText("./xjustiz.fachspezifischeDaten/teilaktentyp", element=fileNode, code=True), verNo = self._getListVersion("./xjustiz.fachspezifischeDaten/teilaktentyp", element=fileNode))
                
                files[file['id']]=file
                self.alleAktenIDs.append(file['id'])
                
        return files

    def _parseNatuerlichePerson(self, node):
        personData={}
        personData['type']='GDS.NatuerlichePerson'
        personData['vollerName']=self._parseNameNatuerlichePerson(self._findElement('./vollerName', node))
        
        personData['aliasNatuerlichePerson']=[]
        for alias in self._findAllElements ("./aliasNatuerlichePerson", node): 
            personData['aliasNatuerlichePerson'].append(self._parseNatuerlichePerson(alias))
        
        personData['umsatzsteuerID']= self._findElementText('./umsatzsteuerID', node)
        personData['steueridentifikationsnummer']= self._findElementText('./steueridentifikationsnummer', node)
        personData['bundeseinheitlicheWirtschaftsnummer']= self._findElementText('./bundeseinheitlicheWirtschaftsnummer', node)
        
        personData['geschlecht']    =self.lookup.xjustizValue ('GDS.Geschlecht', self._findElementText("./geschlecht", node, code=True), verNo = self._getListVersion("./geschlecht", element=node))
        personData['familienstand'] =self.lookup.xjustizValue ('GDS.Familienstand', self._findElementText("./familienstand", node, code=True), verNo = self._getListVersion("./familienstand", element=node))
        personData['personalstatut']=self.lookup.xjustizValue ('GDS.Personalstatut', self._findElementText("./personalstatut", node, code=True), verNo = self._getListVersion("./personalstatut", element=node))
        
        personData['beruf']=[]
        for beruf in self._findAllElements ("./beruf", node): 
            personData['beruf'].append(beruf.text)
        
        personData['telekommunikation']=[]
        for telekom in self._findAllElements ("./telekommunikation", node): 
            personData['telekommunikation'].append(self._parseTelekommunikation(telekom))
            
        personData['anschrift']=[]
        for anschrift in self._findAllElements ("./anschrift", node): 
            personData['anschrift'].append(self._parseAnschrift(anschrift))    
        
        personData['zustaendigeInstitution']=[]
        for institution in self._findAllElements ("./zustaendigeInstitution/ref.rollennummer", node): 
            personData['zustaendigeInstitution'].append(institution.text)      
        
        personData['staatsangehoerigkeit']=[]
        for staat in self._findAllElements ("./staatsangehoerigkeit", node):
            if staat is not None:
                personData['staatsangehoerigkeit'].append(self._parseStaat (staat))              
                       
        personData['herkunftsland']=[]
        for staat in self._findAllElements ("./herkunftsland", node):
            if staat is not None:
                personData['herkunftsland'].append(self._parseStaat (staat))                                          
        
        personData['sprache']=[]
        for sprache in self._findAllElements ("./sprache", node, code=True):
            personData['sprache'].append(self.lookup.xjustizValue ('GDS.Sprachen', sprache.text))
        
        personData['bankverbindung']=[]
        for bankverbindung in self._findAllElements ("./bankverbindung", node):
            personData['bankverbindung'].append(self._parseBankverbindung(bankverbindung))
               
        personData['registereintragungNatuerlichePerson']=[]
        registereintragung=self._findElement('./registereintragungNatuerlichePerson', node)
        if registereintragung != '':
            personData['registereintragungNatuerlichePerson']=self._parseRegistereintragungNatuerlichePerson(registereintragung)
        
        personData['tod']=[]
        tod=self._findElement('./tod', node)
        if tod != '':
            personData['tod']=self._parseTod(tod)
            
        personData['geburt']=[]
        geburt=self._findElement('./geburt', node)
        if geburt != '':
            personData['geburt']=self._parseGeburt(geburt)
                    
        personData['auswahl_auskunftssperre']=[]
        auskunftssperre=self._findElement('./auswahl_auskunftssperre', node)
        if auskunftssperre != '':
            personData['auswahl_auskunftssperre']=self._parseAuskunftssperre(auskunftssperre)
        
        personData['ausweisdokument']=[]
        for dokument in self._findAllElements ("./ausweisdokument", node): 
            personData['ausweisdokument'].append(self._parseAusweisdokument(dokument))
                
        return personData
    
    def _parseGeldbetrag(self, geldbetragNode):
        geldbetrag = self._findElementText('.//zahl', geldbetragNode)
        
        waehrung = self.lookup.xjustizValue ("Währung", self._findElementText(".//waehrung", element=geldbetragNode, code=True), verNo = self._getListVersion(".//waehrung", element=geldbetragNode))
        if waehrung != '':
            return geldbetrag + ' ' + waehrung
      
        historischeWaehrung = self._findElementText('.//historischeWaehrung', geldbetragNode)
        if historischeWaehrung != '':
            return geldbetrag + ' ' + historischeWaehrung
        
        if geldbetrag != '':
            return geldbetrag
        
        return ''

    def _parseRechtsform(self, rechtsform):
        data={}
        data['rechtsform']         = self._findElementText("./rechtsform", rechtsform, code=True)
        data['weitereBezeichnung'] = self._findElementText('./weitereBezeichnung', rechtsform)
       
        return data

    def _parseRegistrierung(self, registrierung):
        data={}
        
        items=(
            'registernummer',
            'reid',
            'lei',
            'euid'             
        )
        
        for item in items:
            data[item]= self._findElementText('./' + item, registrierung)
        
        data['auswahl_registerbehoerde']={}
        
        data['auswahl_registerbehoerde']['inlaendischesRegistergericht']={}
        data['auswahl_registerbehoerde']['inlaendischesRegistergericht']['gericht']=self.lookup.xjustizValue ("GDS.Gerichte", self._findElementText("./auswahl_registerbehoerde/inlaendischesRegistergericht/gericht", registrierung, code=True), verNo = self._getListVersion("./auswahl_registerbehoerde/inlaendischesRegistergericht/gericht", element=registrierung))
        data['auswahl_registerbehoerde']['inlaendischesRegistergericht']['registerart']=self.lookup.xjustizValue ("GDS.Registerart", self._findElementText("./auswahl_registerbehoerde/inlaendischesRegistergericht/registerart", registrierung, code=True), verNo = self._getListVersion("./auswahl_registerbehoerde/inlaendischesRegistergericht/registerart", element=registrierung))
        
        data['auswahl_registerbehoerde']['sonstigeRegisterbehoerde']={}
        data['auswahl_registerbehoerde']['sonstigeRegisterbehoerde']['registerbehoerde']   =self._findElementText('./auswahl_registerbehoerde/sonstigeRegisterbehoerde/registerbehoerde', registrierung)
        data['auswahl_registerbehoerde']['sonstigeRegisterbehoerde']['registerbezeichnung']=self._findElementText('./auswahl_registerbehoerde/sonstigeRegisterbehoerde/registerbezeichnung', registrierung)
        
        data['auswahl_registerbehoerde']['auslaendischeRegisterbehoerde']=self.lookup.xjustizValue ("GDS.BRIS-ListOfRegisters", self._findElementText("./auswahl_registerbehoerde/auslaendischeRegisterbehoerde", registrierung, code=True), getFromColumnRef='English-name-of-register', verNo = self._getListVersion("./auswahl_registerbehoerde/auslaendischeRegisterbehoerde", element=registrierung))                    
        
        return data
    
    def _parseStaat(self, staat):
        staatAllgemein  = self.lookup.xjustizValue ('BfJ Staat', self._findElementText(".", staat, code=True), keyColumnRef='schluessel', getFromColumnRef="staat-oder-gebiet")
        if staatAllgemein:
            return staatAllgemein
        else:
            return ''
 
    def _getTermine(self):
        termine=[]
        for termin in self._findAllElements ("./grunddaten/verfahrensdaten/terminsdaten"):
            termine.append(self._parseTermin(termin))
        return termine
    
    def _parseTermin(self, termin):
        data={}
        
        data['uuid']=str(uuid.uuid4())
        
        items=[
            'terminsID',
            'spruchkoerper',
            'oeffentlich',
            'ref.bezugstermin'
        ]
        
        for item in items:
            data[item]=self._findElementText('./' + item, termin)
        
        itemsGerichtsort=[
            'gebaeude',
            'stockwerk',
            'raum'            
        ]
        
        data['auswahl_terminsort']                = {}
        data['auswahl_terminsort']['gerichtsort'] = {}
  
        for item in itemsGerichtsort:
            data['auswahl_terminsort']['gerichtsort'][item]        = self._findElementText('./auswahl_terminsort/gerichtsort/' + item, termin)
              
        data['auswahl_terminsort']['gerichtsort']['anschrift']={}
        anschrift=self._findElement("./auswahl_terminsort/gerichtsort/anschrift",termin)
        if anschrift != '':
            data['auswahl_terminsort']['gerichtsort']['anschrift'] = self._parseAnschrift(anschrift)
        
        data['auswahl_terminsort']['lokaltermin'] = {}
        data['auswahl_terminsort']['lokaltermin']['beschreibung']  = self._findElementText('./auswahl_terminsort/lokaltermin/beschreibung' , termin)
        data['auswahl_terminsort']['lokaltermin']['anschrift']={}        
        anschrift=self._findElement("./auswahl_terminsort/lokaltermin/anschrift",termin)
        if anschrift != '':
            data['auswahl_terminsort']['lokaltermin']['anschrift'] = self._parseAnschrift(anschrift)
        
        data['terminszeit']={}
        data['terminszeit']['terminsdatum']                             = self._findElementText('./terminszeit/terminsdatum' , termin)  
        data['terminszeit']['auswahl_terminszeit']={}
        data['terminszeit']['auswahl_terminszeit']['terminsuhrzeit']    = self._findElementText('./terminszeit/auswahl_terminszeit/terminsuhrzeit' , termin)
        data['terminszeit']['auswahl_terminszeit']['terminszeitangabe'] = self._findElementText('./terminszeit/auswahl_terminszeit/terminszeitangabe' , termin)             
        data['terminszeit']['terminsdauer']                             = self._findElementText('./terminszeit/terminsdauer' , termin)       
                 
        data['terminsart'] = self.lookup.xjustizValue ("GDS.Terminsart", self._findElementText("./terminsart", termin, code=True), verNo = self._getListVersion("./terminsart", element=termin))
        data['terminskategorie'] = self.lookup.xjustizValue ("GDS.Terminskategorie", self._findElementText("./terminskategorie", termin, code=True), verNo = self._getListVersion("./terminskategorie", element=termin))
        
        data['teilnehmer']=[]
        for teilnehmer in self._findAllElements ("./teilnehmer", termin):
            data['teilnehmer'].append(self._parseTerminTeilnehmer(teilnehmer))

        return data

class parser240(parser321):
    def __init__(self, filename=None):
        super().__init__(filename)

    def _parseOrganisation(self, node):
        orgData={}
        orgData['type']='GDS.Organisation'
        orgData['bezeichnung.aktuell']=self._findElementText('./bezeichnung/bezeichnung.aktuell', node)
        orgData['kurzbezeichnung']    =self._findElementText('./kurzbezeichnung', node)
        orgData['bezeichnung.alt']=[]
        for bezeichnung in self._findAllElements ('./bezeichnung/bezeichnung.alt', node): 
            orgData['bezeichnung.alt'].append(bezeichnung.text)
        
        orgData['anschrift']=[]
        for anschrift in self._findAllElements ("./anschrift", node): 
            orgData['anschrift'].append(self._parseAnschrift(anschrift)) 
        
        orgData['angabenZurRechtsform']={}
        rechtsform = self._findElement('./auswahl_Rechtsform', node)
        if rechtsform != '':
            orgData['angabenZurRechtsform']=self._parseRechtsform(rechtsform)
        
        orgData['telekommunikation']=[]
        for telekom in self._findAllElements ("./telekommunikation", node): 
            orgData['telekommunikation'].append(self._parseTelekommunikation(telekom))
              
        orgData['bankverbindung']=[]
        for bankverbindung in self._findAllElements ("./bankverbindung", node):
            orgData['bankverbindung'].append(self._parseBankverbindung(bankverbindung))
        
        orgData['registereintragung']={}
        registereintragung = self._findElement('./registereintragung', node)
        if registereintragung != '':
            orgData['registereintragung']=self._parseRegistrierung(registereintragung)
        
        orgData['sitz']=[]
        for sitz in self._findAllElements ("./sitz", node):
            orgData['sitz'].append(self._parseSitz(sitz))
        
        #Nur in 2.4.0 unterstützt
        orgData['anschrift.gerichtsfach']={}
        if self._findElement('./anschrift.gerichtsfach', node)!='':
            orgData['anschrift.gerichtsfach']['gericht']=self.lookup.xjustizValue ("GDS.Gerichte", self._findElementText("./anschrift.gerichtsfach/gericht", node, code=True), verNo = self._getListVersion("./anschrift.gerichtsfach/gericht", element=node))
            orgData['anschrift.gerichtsfach']['fach']=self._findElementText("./anschrift.gerichtsfach/fach", node)

        #Von 2.4.0 nicht unterstützt
        orgData['geschlecht']    = ''
        orgData['umsatzsteuerID'] = ''
        
        return orgData

    
    def _parseRechtsform(self, rechtsform):
        data={}
        data['rechtsform']         = self.lookup.xjustizValue ("GDS.Rechtsform", self._findElementText("./rechtsform", rechtsform, code=True), verNo = self._getListVersion("./rechtsform", element=rechtsform))
        data['weitereBezeichnung'] = self._findElementText('./vollstaendige_Bezeichnung', rechtsform)
       
        return data
    
    def _parseRegistrierung(self, registrierung):
        data={}
        
        items=(
            'registernummer',
            'reid',
            'lei',
            'euid'             
        )
        
        for item in items:
            data[item]= self._findElementText('./' + item, registrierung)
        
        data['auswahl_registerbehoerde']={}
        
        data['auswahl_registerbehoerde']['inlaendischesRegistergericht']={}
        data['auswahl_registerbehoerde']['inlaendischesRegistergericht']['gericht']=self.lookup.xjustizValue ("GDS.Gerichte", self._findElementText("./gericht", registrierung, code=True), verNo = self._getListVersion("./gericht", element=registrierung))
        
        #von 2.4.0 nicht unterstützt
        data['auswahl_registerbehoerde']['inlaendischesRegistergericht']['registerart']= ''
        data['auswahl_registerbehoerde']['sonstigeRegisterbehoerde']={}
        data['auswahl_registerbehoerde']['sonstigeRegisterbehoerde']['registerbehoerde']   = ''
        data['auswahl_registerbehoerde']['sonstigeRegisterbehoerde']['registerbezeichnung']= ''
                
        return data

    def _parseKanzlei(self, node):
        kanzleiData={}
        kanzleiData['type']='GDS.RA.Kanzlei'
        kanzleiData['bezeichnung.aktuell']=self._findElementText('./bezeichnung/bezeichnung.aktuell', node)
        kanzleiData['bezeichnung.alt']=[]
        for bezeichnung in self._findAllElements ('./bezeichnung/bezeichnung.alt', node): 
            kanzleiData['bezeichnung.alt'].append(bezeichnung.text)
        
        kanzleiData['anschrift']=[]
        for anschrift in self._findAllElements ("./anschrift", node): 
            kanzleiData['anschrift'].append(self._parseAnschrift(anschrift)) 
         
        kanzleiData['rechtsform'] =self.lookup.xjustizValue ("GDS.Rechtsform", self._findElementText("./rechtsform", node, code=True), verNo = self._getListVersion("./rechtsform", element=node))
        kanzleiData['kanzleiform']=self.lookup.xjustizValue ("GDS.Kanzleiform", self._findElementText("./kanzleiform", node, code=True), verNo = self._getListVersion("./kanzleiform", element=node))
        
        kanzleiData['telekommunikation']=[]
        for telekom in self._findAllElements ("./telekommunikation", node): 
            kanzleiData['telekommunikation'].append(self._parseTelekommunikation(telekom))
        
        kanzleiData['raImVerfahren']=[]
        if self._findElement('./raImVerfahren', node)!='':
            kanzleiData['raImVerfahren']=self._parseNatuerlichePerson(self._findElement('./ra_im_Verfahren', node))
       
        #Nur in 2.4.0 unterstützt
        kanzleiData['anschrift.gerichtsfach']={}
        if self._findElement('./anschrift.gerichtsfach', node)!='':
            kanzleiData['anschrift.gerichtsfach']['gericht']=self.lookup.xjustizValue ("GDS.Gerichte", self._findElementText("./anschrift.gerichtsfach/gericht", node, code=True), verNo = self._getListVersion("./anschrift.gerichtsfach/gericht", element=node))
            kanzleiData['anschrift.gerichtsfach']['fach']=self._findElementText("./anschrift.gerichtsfach/fach", node)
            
        #In 2.4.0 nicht unterstützt
        kanzleiData['umsatzsteuerID'] = ''
        kanzleiData['geschlecht']     = ''
        return kanzleiData

    def _parseNatuerlichePerson(self, node):
        personData={}
        personData['type']='GDS.NatuerlichePerson'
        personData['vollerName']=self._parseNameNatuerlichePerson(self._findElement('./vollerName', node))

        personData['geschlecht']    =self.lookup.xjustizValue ('GDS.Geschlecht', self._findElementText("./geschlecht", node, code=True), verNo = self._getListVersion("./geschlecht", element=node))
        personData['familienstand'] =self.lookup.xjustizValue ('GDS.Familienstand', self._findElementText("./familienstand", node, code=True), verNo = self._getListVersion("./familienstand", element=node))
        personData['personalstatut']=self.lookup.xjustizValue ('GDS.Personalstatut', self._findElementText("./personalstatut", node, code=True), verNo = self._getListVersion("./personalstatut", element=node))
        
        personData['beruf']=[]
        for beruf in self._findAllElements ("./beruf", node): 
            personData['beruf'].append(beruf.text)
        
        personData['telekommunikation']=[]
        for telekom in self._findAllElements ("./telekommunikation", node): 
            personData['telekommunikation'].append(self._parseTelekommunikation(telekom))
            
        personData['anschrift']=[]
        for anschrift in self._findAllElements ("./anschrift", node): 
            personData['anschrift'].append(self._parseAnschrift(anschrift))    
        
        personData['staatsangehoerigkeit']=[]
        for staat in self._findAllElements ("./staatsangehoerigkeit", node, code=True):
            if staat is not None:
                personData['staatsangehoerigkeit'].append(self.lookup.xjustizValue ('Country Codes', staat.text, keyColumnRef='ISOAlpha2code', getFromColumnRef="ShortName"))
        
        personData['herkunftsland']=[]
        for staat in self._findAllElements ("./herkunftsland", node, code=True):
            if staat is not None:
                personData['herkunftsland'].append(self.lookup.xjustizValue ('Country Codes', staat.text, keyColumnRef='ISOAlpha2code', getFromColumnRef="ShortName"))
                                        
        personData['sprache']=[]
        for sprache in self._findAllElements ("./sprache", node, code=True):
            personData['sprache'].append(sprache.text)
        
        personData['bankverbindung']=[]
        for bankverbindung in self._findAllElements ("./bankverbindung", node):
            personData['bankverbindung'].append(self._parseBankverbindung(bankverbindung))
            
        personData['tod']=[]
        tod=self._findElement('./tod', node)
        if tod != '':
            personData['tod']=self._parseTod(tod)
            
        personData['geburt']=[]
        geburt=self._findElement('./geburt', node)
        if geburt != '':
            personData['geburt']=self._parseGeburt(geburt)
                    
        personData['auswahl_auskunftssperre']=[]
        auskunftssperre=self._findElement('./auskunftssperre', node)
        if auskunftssperre != '':
            personData['auswahl_auskunftssperre']=self._parseAuskunftssperre(auskunftssperre)
        
        #Nur in 2.4.0 unterstützt
        personData['anschrift.gerichtsfach']={}
        if self._findElement('./anschrift.gerichtsfach', node)!='':
            personData['anschrift.gerichtsfach']['gericht']=self.lookup.xjustizValue ("GDS.Gerichte", self._findElementText("./anschrift.gerichtsfach/gericht", node, code=True), verNo = self._getListVersion("./anschrift.gerichtsfach/gericht", element=node))
            personData['anschrift.gerichtsfach']['fach']=self._findElementText("./anschrift.gerichtsfach/fach", node)
        
        personData['weitererName']=[]
        for name in self._findAllElements ("./weitererName", node): 
            personData['weitererName'].append(name.text)
        personData['vollerName']['weitererName']=personData['weitererName']
        
        #Von 2.4.0 nicht unterstützt
        personData['umsatzsteuerID']= ''
        personData['registereintragungNatuerlichePerson']=[]
        personData['aliasNatuerlichePerson']=[]
        personData['zustaendigeInstitution']=[]
        
        return personData
    
       
    def _parseAuskunftssperre(self, auskunftssperre):
        data={}
        
        sperreitems=(
            'grundlage',
            'umfang',
            'sperrstufe'
        )
        data['auskunftssperre.details']={}
        
        for item in sperreitems:
            data['auskunftssperre.details'][item]=self._findElementText('./'+item, auskunftssperre)
        
        # Von 2.4.0 nicht unterstützt
        data['auskunftssperre.vorhanden']=''    
        return data
    
    def _parseAnschrift(self, node):
        anschrift={}
        simpleValues=(
            'strasse',
            'hausnummer',
            'postfachnummer',
            'postleitzahl',
            'ort',
            'ortsteil',
            'wohnungsgeber',
            'ehemaligeAnschrift',
            'erfassungsdatum',
            'ort.unbekannt',
            'postleitzahl.unbekannt'             
        )
        for value in simpleValues:
            anschrift[value]= self._findElementText('./' + value, node)
        
        anschrift['anschriftenzusatz']=[]
        for zusatz in self._findAllElements ("./anschriftenzusatz", node): 
            anschrift['anschriftenzusatz'].append(zusatz.text)
        
        anschrift['anschriftstyp']=self.lookup.xjustizValue ('GDS.Anschriftstyp', self._findElementText("./anschriftstyp", node, code=True), verNo = self._getListVersion("./anschriftstyp", element=node))
       
        anschrift['staat']        =self.lookup.xjustizValue ('Country Codes', self._findElementText("./staat", node, code=True), keyColumnRef='ISOAlpha2code', getFromColumnRef="ShortName")
                    
        #Set default values as defined in the specification if empty
        if anschrift['ort.unbekannt']=='':
            anschrift['ort.unbekannt']='true'      
   
        return anschrift
        
    
    def _parseGeburt(self, geburt):
        data={}
           
        items=(
            'geburtsdatum',
            'geburtsname.mutter'            
        )

        for item in items:
            data[item]=self._findElementText('./'+item, geburt)

        geburtsort={}
        
        data['geburtsort']={}
        data['geburtsort']['ort']  =self._findElementText('./geburtsort/ort', geburt)
        data['geburtsort']['staat']=self.lookup.xjustizValue ('Country Codes', self._findElementText("./geburtsort/staat", geburt, code=True), keyColumnRef='ISOAlpha2code', getFromColumnRef="ShortName")
        
        #Von 2.4.0 nicht unterstützt
        data['geburtsdatum.unbekannt']=''
        data['name.eltern']={}
        data['name.eltern']['nachname.mutter']=[]
        data['name.eltern']['nachname.vater'] =[]
        data['name.eltern']['vorname.mutter'] =[]
        data['name.eltern']['vorname.vater']  =[] 
        
        return data
    
    def _parseTod(self, tod):
        data={}

        data['sterbedatum']= self._findElementText('./sterbedatum', tod)     
        data['sterbeort']= {}
        data['sterbeort']['ort']  =self._findElementText('./sterbeort/ort', tod)
        data['sterbeort']['staat']=self.lookup.xjustizValue ('Country Codes', self._findElementText("./sterbeort/staat", tod, code=True), keyColumnRef='ISOAlpha2code', getFromColumnRef="ShortName")

        #Von 2.4.0 nicht untertstützt        
        data['sterbedatumZeitraum']={}
        data['sterbedatumZeitraum']['ende']     = ''
        data['sterbedatumZeitraum']['beginn']   = ''
        items=(
            'sterberegisterart',
            'sterbestandesamtBehoerdennummer',
            'sterbestandesamtName',
            'sterberegisternummer',
            'eintragungsdatum',
            'todErklaert',
        )
        for item in items:
            data[item]=''        
        
        return data
    
    def _parseNameNatuerlichePerson(self, node):
        namensbestandteile={}
        
        simpleValues=(  
                'vorname',
                'rufname',
                'titel',
                'nachname',
                'geburtsname',
                'namensvorsatz',
                'namenszusatz',
                'geburtsnamensvorsatz',
            )
        for simpleValue in simpleValues:
            namensbestandteile[simpleValue] = self._findElementText('./'+simpleValue, node)
        
        multiValues=(  
                'vorname.alt',
                'nachname.alt',
                'weitererName'            
            )    
        for multiValue in multiValues:    
            namensbestandteile[multiValue] = []
            for value in self._findAllElements ("./"+multiValue, node):  
                namensbestandteile[multiValue].append(value.text)       
                
        return namensbestandteile

    def _parseBeteiligung(self, beteiligungNode):
        beteiligung={}
        beteiligung['rolle']=[]
        for rolle in self._findAllElements ("./rolle", beteiligungNode):
            rolleData={}
            rolleData['rollennummer']= self._findElementText("./rollennummer", rolle)
            rolleData['nr']= self._findElementText("./nr", rolle)
            if not rolleData['nr']:
                rolleData['nr']=1
            rolleData['geschaeftszeichen']= self._findElementText("./geschaeftszeichen", rolle)
            rolleData['rollenbezeichnung']=self.lookup.xjustizValue ("GDS.Rollenbezeichnung", self._findElementText("./rollenbezeichnung", rolle, code=True), verNo = self._getListVersion("./rollenbezeichnung", element=rolle))
            
            rolleData['referenz']=[]
            for referenz in self._findAllElements ("./referenz", rolle): 
                rolleData['referenz'].append(self._findElementText("./ref.rollennummer", referenz))
            
            rolleData['rollenID']=[]
            for rollenID in self._findAllElements ("./rollenId", rolle): 
                rollenIDData={}
                rollenIDData['id']=self._findElementText("./id", rollenID)
                rollenIDData['ref.instanznummer']=self._findElementText("./ref.instanznummer", rollenID)
                rolleData['rollenID'].append(rollenIDData)
            
            self.rollenverzeichnis[str(rolleData['rollennummer'])]= "%s %s" % (rolleData['rollenbezeichnung'], rolleData['nr'])
            
            ###Werte aus 2.4.0 in 3.2.1-Feld übersetzen
            anrede                  = self._findElementText("./anrede", rolle)
            if anrede:
                anrede              = 'Anrede: %s' % anrede
            
            dienstbezeichnung       = self._findElementText("./dienstbezeichnung", rolle)
            if dienstbezeichnung:
                dienstbezeichnung   ='Dienstbezeichnung: %s' % dienstbezeichnung
            
            funktionsbezeichnung    = self._findElementText("./funktionsbezeichnung", rolle)
            if funktionsbezeichnung:
                funktionsbezeichnung='Funktionsbezeichnung: %s' % funktionsbezeichnung
            
            rolleData['naehereBezeichnung']= ''
            delimiter=''
            for part in [anrede, dienstbezeichnung, funktionsbezeichnung]:
                if part:
                    rolleData['naehereBezeichnung']+=delimiter + part
                    delimiter=', '
                    
            beteiligung['rolle'].append(rolleData)
            
        beteiligung['beteiligtennummer']=self._findElementText("./beteiligter/beteiligtennummer", beteiligungNode)
                
        beteiligterAuswahl              =self._findElement("./beteiligter", beteiligungNode)
        if   self._tagInAuswahl ('ra.kanzlei', beteiligterAuswahl):
            beteiligung['beteiligter']  = self._parseKanzlei(self._findElement('./ra.kanzlei',beteiligterAuswahl))
            name=beteiligung['beteiligter']['bezeichnung.aktuell']
        elif self._tagInAuswahl ('natuerlichePerson', beteiligterAuswahl):
            beteiligung['beteiligter']  = self._parseNatuerlichePerson(self._findElement('./natuerlichePerson',beteiligterAuswahl))
            name=beteiligung['beteiligter']['vollerName']['nachname'].upper()+' '+beteiligung['beteiligter']['vollerName']['vorname'] 
        elif self._tagInAuswahl ('organisation', beteiligterAuswahl):
            beteiligung['beteiligter']  = self._parseOrganisation(self._findElement('./organisation',beteiligterAuswahl))
            name=beteiligung['beteiligter']['bezeichnung.aktuell']
        else:
            beteiligung['beteiligter']  = {}
        
        if beteiligung['beteiligtennummer']:
            self.beteiligtenverzeichnis[beteiligung['beteiligtennummer']]=name
        
        return beteiligung

    def _parseVerfahrensgegenstand(self, node):
        gegenstandData={}
        gegenstandData['gegenstand']     =self._findElementText('.//verfahrensgegenstand/gegenstand', node)
        gegenstandData['gegenstandswert']=self._findElementText('.//verfahrensgegenstand/gegenstandswert/zahl', node) + ' ' + self._findElementText('.//verfahrensgegenstand/gegenstandswert/waehrung', node)
        
        gegenstandData['auswahl_zeitraumDesVerwaltungsaktes']=''
        auswahl = self._findElement("./auswahl_Zeitraum_des_Verwaltungsaktes", node)
        if   self._tagInAuswahl ('jahr', auswahl):
            gegenstandData['auswahl_zeitraumDesVerwaltungsaktes']=self._findElementText(".//jahr", node)
        elif self._tagInAuswahl ('stichtag', auswahl):
            gegenstandData['auswahl_zeitraumDesVerwaltungsaktes']=self._findElementText(".//stichtag", node)
        elif self._tagInAuswahl ('kein_Zeitraum', auswahl):
            gegenstandData['auswahl_zeitraumDesVerwaltungsaktes']=self._findElementText(".//kein_Zeitraum", node)        
        elif self._tagInAuswahl ('zeitraum', auswahl):
            gegenstandData['auswahl_zeitraumDesVerwaltungsaktes']=self._findElementText(".//zeitraum", node)
        
        return gegenstandData

    def _parseBehoerde(self, auswahlNode):
        behoerde={}
        if   self._tagInAuswahl ('sonstige', auswahlNode):
            behoerde['name'] = self._findElementText("./sonstige", auswahlNode)
            behoerde['type'] = 'sonstige'
        elif self._tagInAuswahl ('gericht', auswahlNode):
            behoerde['name'] = self.lookup.xjustizValue ("GDS.Gerichte", self._findElementText("./gericht", auswahlNode, code=True), verNo = self._getListVersion("./gericht", element=auswahlNode))
            behoerde['type'] = 'GDS.Gerichte'
        elif self._tagInAuswahl ('beteiligter', auswahlNode):
            behoerde['name'] = self._findElementText("./beteiligter/ref.beteiligtennummer", auswahlNode)
            behoerde['type'] ='GDS.Ref.Beteiligtennummer'
        return behoerde 

    def _parseAktenzeichen(self, aktenzeichen):
        aktenzeichenParts={}
        aktenzeichenParts['az.art']                      =self.lookup.xjustizValue ("GDS.Aktenzeichenart", self._findElementText("./az.art", element=aktenzeichen, code=True), verNo = self._getListVersion("./az.art", element=aktenzeichen))
        aktenzeichenParts['auswahl_az.vergebendeStation']=[]
        if self._findElement("./auswahl_az.vergebendeStation", element=aktenzeichen)!='':
            aktenzeichenParts['auswahl_az.vergebendeStation']=self._parseBehoerde(self._findElement("./auswahl_az.vergebendeStation", element=aktenzeichen))
     
        aktenzeichenParts['aktenzeichen.freitext']       =self._findElementText("./auswahl_aktenzeichen/aktenzeichen.freitext", element=aktenzeichen) 
        if len(aktenzeichenParts['aktenzeichen.freitext'])==0:
            aktenzeichenStrukturiert={}
            aktenzeichenElements=(  
                'sachgebietsschluessel',
                'zusatzkennung',
                'abteilung',
                'laufendeNummer',
                'jahr',
                'vorsatz',
                'zusatz',
                'dezernat',
                'erfassungsdatum'                       
            )
            for elementName in aktenzeichenElements:
                aktenzeichenStrukturiert[elementName]=self._findElementText(".//" + elementName, element=aktenzeichen)
            aktenzeichenStrukturiert['register']     =self.lookup.xjustizValue ("GDS.Registerzeichen", self._findElementText(".//register", element=aktenzeichen, code=True), verNo = self._getListVersion(".//register", element=aktenzeichen))
            aktenzeichenParts['aktenzeichen.strukturiert']=aktenzeichenStrukturiert
            
            aktenzeichenFreitext="%s %s %s %s/%s %s" % (aktenzeichenStrukturiert['vorsatz'],
                                                        aktenzeichenStrukturiert['abteilung'],
                                                        aktenzeichenStrukturiert['register'],
                                                        aktenzeichenStrukturiert['laufendeNummer'],
                                                        aktenzeichenStrukturiert['jahr'],
                                                        aktenzeichenStrukturiert['zusatz'])
            
            if aktenzeichenFreitext.strip() != '/':
                aktenzeichenParts['aktenzeichen.freitext']=aktenzeichenFreitext 
        
        return aktenzeichenParts
    
    def _parseAktenzeichenEinfach(self, aktenzeichen):
        aktenzeichenParts={}
        aktenzeichenParts['az.art']                      =self.lookup.xjustizValue ("GDS.Aktenzeichenart", self._findElementText("./az_Art", element=aktenzeichen, code=True), verNo = self._getListVersion("./az_Art", element=aktenzeichen))
        
        aktenzeichenParts['aktenzeichen.freitext']       =self._findElementText("./az_Inhalt", element=aktenzeichen) 

        #vom einfachen Aktenzeichen in 2.4.0 nicht unterstützt
        aktenzeichenParts['aktenzeichen.strukturiert']={}
        aktenzeichenParts['auswahl_az.vergebendeStation']=''    
        return aktenzeichenParts


    # funktion def self._parseDokumente(docNode) returns dict
    def _parseDokumente(self, path='./dokument', element=None):
        element = self._root if element is None else element
        documents={}
        documentNodes= self._findAllElements(path, element)
        if documentNodes != '':
            simpleValues=(  
                'id',
                'nummerImUebergeordnetenContainer',
                'anzeigename',
                'akteneinsicht',
                'veraktungsdatum',
                'justizkostenrelevanz',
                'ruecksendungEEB.erforderlich',
                'zustellung41StPO',
            )
            for documentNode in documentNodes:
                document={}
                for simpleValue in simpleValues:
                    document[simpleValue]=self._findElementText('.//'+simpleValue, documentNode)
                
                
                document['posteingangsdatum']=self._findElementText('.//eingangszeitpunkt', documentNode)
                document['datumDesSchreibens']=self._findElementText('.//dokumentendatum', documentNode)
                document['absenderAnzeigename']=self._findElementText('.//absenderanzeigename', documentNode)
                document['adressatAnzeigename']=self._findElementText('.//adressatanzeigename', documentNode)
                document['fremdesGeschaeftszeichen']=self._findElementText('.//fremdes_Geschaeftszeichen', documentNode)
                document['ruecksendungEEB.erforderlich']=self._findElementText('.//ruecksendung_EEB_erforderlich', documentNode)

                dokumenttyp={
                '001':'Andere / Sonstige',
                '002':'Eingangsschreiben',
                '003':'Klage / Antrag',
                '004':'Ausgangsschreiben',
                '005':'Anlage',
                '006':'Urteil',
                '007':'Beschluss',
                '008':'Verfügung',
                '009':'Vermerk',
                '010':'Protokoll',
                '011':'Fehlblatt',
                '012':'Zustellungsdokument',
                '013':'Gutachten',
                '014':'Technische Information'
                }
                                
                document['dokumententyp']        = '' 
                typ=dokumenttyp.get(self._findElementText(".//dokumententyp", element=documentNode , code=True))  
                if typ:
                    document['dokumententyp'] = typ
                
                document['verweise']=[]
                for verweis in self._findAllElements('.//verweis', element=documentNode):
                    verweisParts={}
                    verweisParts['anzeigenameSGO']=self._findElementText('./anzeigename_SGO', element=verweis)
                    verweisParts['id.sgo']        =self._findElementText('./id_des_SGO_auf_das_verwiesen_wird', element=verweis)
                    verweisParts['verweistyp']    =self.lookup.xjustizValue ("GDS.Verweistyp", self._findElementText("./verweistyp", element=verweis , code=True), verNo = self._getListVersion("./verweistyp", element=verweis ))   
                    document['verweise'].append(verweisParts)
                
                document['dateien']=[]
                for datei in self._findAllElements('.//datei', element=documentNode):
                    dateiData={}
                    dateiData['dateiname']     =self._findElementText('./dateiname', element=datei)
                    dateiData['versionsnummer']=self._findElementText('./versionsnummer', element=datei)
                    dateiData['bestandteil']   =self.lookup.xjustizValue ('GDS.Bestandteiltyp', self._findElementText("./bestandteil", element=datei , code=True), verNo = self._getListVersion("./bestandteil", element=datei))  
                    
                    dateiData['dateiname.bezugsdatei']=[]
                    for bezugsdatei in self._findAllElements ('./dateiname_der_Bezugsdatei', element=datei):
                        dateiData['dateiname.bezugsdatei'].append(bezugsdatei.text)
                    
                    document['dateien'].append(dateiData)
                
                #Von 2.4.0 nicht unterstützt
                document['personen']=[]
                document['vertraulichkeitsstufe'] = ''
                document['dokumentklasse']        = ''
                document['scanDatum']             = ''
                                
                documents[document['id']]=document
        return documents

    # funktion def self._parseDokumente(docNode) returns dict
    def _parseAkten(self, path='./akte', element=None):
        element = self._root if element is None else element
        
        files={}
        fileNodes= self._findAllElements(path, element)
        if fileNodes != '':
            simpleValues=(  
                './anzeigename',
                './identifikation/id',
                './identifikation/nummerImUebergeordnetenContainer',
                './weiteresOrdnungskriteriumBehoerde',
              
                #von2.4.0 nicht unterstützt
                './zustellung41StPO',
                
                # teilaktenspezifisch
                './akteneinsicht'
                )
            for fileNode in fileNodes:
                file={}
                for simpleValue in simpleValues:
                    file[simpleValue.rsplit('/', 1)[1]]=self._findElementText(simpleValue, fileNode)

                file['erstellungszeitpunktAkteVersand']=self._findElementText('./erstellungszeitpunkt_der_Akte_fuer_den_Versand', fileNode)
                file['ruecksendungEEB.erforderlich']=self._findElementText('./ruecksendung_EEB_erforderlich', fileNode)
                file['letztePaginierungProTeilakte']=self._findElementText('./letzte_Paginierung_pro_Teilakte', fileNode)
                
                file['dokumente']            = self._parseDokumente('./inhalt/dokument', fileNode)
                file['teilakten']            = self._parseAkten('./inhalt/teilakte', fileNode)
                file['abgebendeStelle']      = self.lookup.xjustizValue ("GDS.Gerichte", self._findElementText("./abgebende_Stelle", element=fileNode, code=True), verNo = self._getListVersion("./abgebende_Stelle", element=fileNode))
                file['aktentyp']             = self.lookup.xjustizValue ("GDS.Aktentyp", self._findElementText("./aktentyp", element=fileNode, code=True), verNo = self._getListVersion("./aktentyp", element=fileNode))

                file['aktenreferenzen']=[]
                for aktenreferenz in self._findAllElements ('./aktenreferenzen', element=fileNode):
                    referenceParts={}
                    referenceParts['id.referenzierteAkte']=self._findElementText("./id_der_referenzierten_Akte", element=aktenreferenz)
                    referenceParts['aktenreferenzart']    =self.lookup.xjustizValue ("GDS.Aktenreferenzart", self._findElementText("./aktenreferenzart", element=aktenreferenz, code=True), verNo = self._getListVersion("./aktenreferenzart", element=aktenreferenz))
                    file['aktenreferenzen'].append(referenceParts)
                
                file['aktenzeichen']=[]
                for aktenzeichen in self._findAllElements ('./aktenzeichen', element=fileNode):
                    file['aktenzeichen'].append(self._parseAktenzeichenEinfach(aktenzeichen))
                
                # Teilaktenspezifisch
                file['teilaktentyp']=self.lookup.xjustizValue ("GDS.Teilaktentyp", self._findElementText("./teilaktentyp", element=fileNode, code=True), verNo = self._getListVersion("./teilaktentyp", element=fileNode))
                
                #Von 2.4.0 nicht unterstützt
                file['vertraulichkeitsstufe']= ''
                file['laufzeit']={}
                
                #Nicht von openXJV unterstützt
                file['personen']=[]
                
                files[file['id']]=file
                self.alleAktenIDs.append(file['id'])
                
        return files

    def _parseTermin(self, termin):
        data={}
        
        data['uuid']=str(uuid.uuid4())
        
        items=[
            'hauptterminsdatum',
            'spruchkoerper',
            'oeffentlich'
        ]
        
        for item in items:
            data[item]=self._findElementText('./' + item, termin)
        
        data['hauptterminsID']=self._findElementText('./hauptterminsId', termin)
        data['terminsID']=self._findElementText('./terminsId', termin)
        
        data['auswahl_hauptterminszeit']={}
        data['auswahl_hauptterminszeit']['hauptterminsuhrzeit'] = self._findElementText('.//hauptterminsuhrzeit', termin)
        data['auswahl_hauptterminszeit']['hauptterminszeit']    = self._findElementText('.//hauptterminszeit', termin)
        
        itemsGerichtsort=[
            'gebaeude',
            'stockwerk',
            'raum'            
        ]
        
        data['auswahl_terminsort']                = {}
        data['auswahl_terminsort']['gerichtsort'] = {}
  
        for item in itemsGerichtsort:
            data['auswahl_terminsort']['gerichtsort'][item]        = self._findElementText('./auswahl_Terminsort/gerichtsort/' + item, termin)
              
        data['auswahl_terminsort']['gerichtsort']['anschrift']={}
        anschrift=self._findElement("./auswahl_Terminsort/gerichtsort/anschrift",termin)
        if anschrift != '':
            data['auswahl_terminsort']['gerichtsort']['anschrift'] = self._parseAnschrift(anschrift)
        
        data['auswahl_terminsort']['lokaltermin'] = {}
        data['auswahl_terminsort']['lokaltermin']['beschreibung']  = self._findElementText('./auswahl_Terminsort/lokaltermin/beschreibung' , termin)
        data['auswahl_terminsort']['lokaltermin']['anschrift']={}        
        anschrift=self._findElement("./auswahl_Terminsort/lokaltermin/anschrift",termin)
        if anschrift != '':
            data['auswahl_terminsort']['lokaltermin']['anschrift'] = self._parseAnschrift(anschrift)
        
        data['terminszeit']={}
        data['terminszeit']['terminsdatum']                             = self._findElementText('./terminszeit/terminsdatum' , termin)  
        data['terminszeit']['auswahl_terminszeit']={}
        data['terminszeit']['auswahl_terminszeit']['terminsuhrzeit']    = self._findElementText('.//terminsuhrzeit' , termin)
        data['terminszeit']['auswahl_terminszeit']['terminszeitangabe'] = self._findElementText('.//terminszeitangabe' , termin)             
        data['terminszeit']['terminsdauer']                             = self._findElementText('./terminszeit/terminsdauer' , termin)       
                 
        data['terminsart'] = self.lookup.xjustizValue ("GDS.Terminsart", self._findElementText("./terminsart", termin, code=True), verNo = self._getListVersion("./terminsart", element=termin))
        
        data['teilnehmer']=[]
        for teilnehmer in self._findAllElements ("./teilnehmer", termin):
            data['teilnehmer'].append(self._parseTerminTeilnehmer(teilnehmer))

        return data
    
    def _parseTerminTeilnehmer(self, teilnehmer):
        data={}
        data['ladungszusatz']    = self._findElementText('.//ladungszusatz' , teilnehmer)
        data['ref.rollennummer'] = self._findElementText('.//ref.rollennummer' , teilnehmer)

        data['ladungszeit']={}
        data['ladungszeit']['ladungsdatum'] = self._findElementText('.//ladungszeit/ladungsdatum' , teilnehmer)
        data['ladungszeit']['ladungsdauer'] = self._findElementText('.//ladungszeit/ladungsdauer' , teilnehmer)
        
        data['ladungszeit']['auswahl_ladungszeit']={}
        data['ladungszeit']['auswahl_ladungszeit']['ladungsuhrzeit']    = self._findElementText('.//ladungsuhrzeit' , teilnehmer)
        data['ladungszeit']['auswahl_ladungszeit']['ladungszeitangabe'] = self._findElementText('.//ladungszeitangabe' , teilnehmer)

        return data
    
    def _parseAllValues(self):
        
        ####### Nachrichtenkopf (Alle Werte nach Spezifikation 2.4.0 unterstützt - werden in Struktur 3.2.1 abgebildet) #######
        
        # Keine Entsprechung in Grunddaten.SGO in Version 2.4.0
        self.nachricht['prozessID']              = ''
        self.nachricht['nachrichtenNummer']      = ''
        self.nachricht['nachrichtenAnzahl']      = ''
        self.nachricht['ereignisse']             = ''
              
        ## Allgemeine Infos
        self.nachricht['erstellungszeitpunkt']   = self._findElementText("./nachrichtenkopf/erstellungszeitpunkt")
        self.nachricht['eigeneID']               = self._findElementText("./nachrichtenkopf/eigene_Nachrichten_ID")
        self.nachricht['fremdeID']               = self._findElementText("./nachrichtenkopf/fremde_Nachrichten_ID")
                
        self.nachricht['produktName']            = self._findElementText("./grunddaten/verfahrensdaten/herstellerinformation/nameDesProdukts")
        self.nachricht['produktHersteller']      = self._findElementText("./grunddaten/verfahrensdaten/herstellerinformation/herstellerDesProdukts")
        self.nachricht['produktVersion']         = self._findElementText("./grunddaten/verfahrensdaten/herstellerinformation/version")
        self.nachricht['sendungsprioritaet']     = self.lookup.xjustizValue ("GDS.Sendungsprioritaet", self._findElementText("./nachrichtenkopf/sendungsprioritaet", code=True), verNo = self._getListVersion("./nachrichtenkopf/sendungsprioritaet"))
        
        ## Absenderdaten auslesen
        self.absender['aktenzeichen'] = self._getSubTexts("./nachrichtenkopf/aktenzeichen.absender", newline=' | ')

        absenderAuswahl     = self._findElement("./nachrichtenkopf")
        
        if   self._tagInAuswahl ('absender_Sonstige', absenderAuswahl):
            self.absender["name"]= self._findElementText(".//absender_Sonstige")
        elif self._tagInAuswahl ('absender_Gericht', absenderAuswahl):
            self.absender["name"]= self.lookup.xjustizValue ("GDS.Gerichte", self._findElementText(".//absender_Gericht", code=True), verNo = self._getListVersion(".//absender_Gericht"))
        elif self._tagInAuswahl ('absender_RVTraeger', absenderAuswahl):
            self.absender["name"]= self.lookup.xjustizValue ("GDS.RVTraeger", self._findElementText(".//absender_RVTraeger", code=True), verNo = self._getListVersion(".//absender_RVTraeger"))
        else:
            self.absender["name"]=''
        
        ## Empfängerdaten auslesen
        self.empfaenger['aktenzeichen'] = self._getSubTexts("./nachrichtenkopf/aktenzeichen.empfaenger", newline=' | ')
        
        empfaengerAuswahl       = self._findElement("./nachrichtenkopf")
        if   self._tagInAuswahl ('empfaenger_Sonstige', empfaengerAuswahl):
            self.empfaenger["name"]  = self._findElementText(".//empfaenger_Sonstige")
        elif self._tagInAuswahl ('empfaenger_Gericht', empfaengerAuswahl):
            self.empfaenger["name"]  = self.lookup.xjustizValue ("GDS.Gerichte", self._findElementText(".//empfaenger_Gericht", code=True), verNo = self._getListVersion(".//empfaenger_Gericht"))
        elif self._tagInAuswahl ('empfaenger_RVTraeger', empfaengerAuswahl):
            self.empfaenger["name"]  = self.lookup.xjustizValue ("GDS.RVTraeger", self._findElementText(".//empfaenger_RVTraeger", code=True), verNo = self._getListVersion(".//empfaenger_RVTraeger"))
        else:
            self.empfaenger["name"]  = ''
        
        ####### Grunddaten #######

        self.grunddaten['verfahrensnummer'] = self._findElementText("./grunddaten/verfahrensdaten/verfahrensnummer")

        ## Beteiligungen ##

        self.grunddaten['beteiligung']=[]
        for beteiligung in self._findAllElements ("./grunddaten/verfahrensdaten/beteiligung"):
            self.grunddaten['beteiligung'].append(self._parseBeteiligung(beteiligung))

        ## Instanzdaten ##
        self.grunddaten['instanzen']={}
        simpleValues=(  
                    'instanznummer',
                    'sachgebietszusatz',
                    'abteilung',
                    'verfahrensinstanznummer',
                    'kurzrubrum'
                               
                )
        for instanz in self._findAllElements ("./grunddaten/verfahrensdaten/instanzdaten_erweitert"):    
            instanzData={}
            for simpleValue in simpleValues:
                instanzData[simpleValue] = self._findElementText('.//instanzdaten/'+simpleValue, instanz)

            instanzData['sachgebiet']    = self.lookup.xjustizValue ("GDS.Sachgebiet", self._findElementText(".//instanzdaten/sachgebiet", element=instanz, code=True), verNo = self._getListVersion(".//instanzdaten/sachgebiet", element=instanz))

            instanzData['verfahrensgegenstand']=[]
            for gegenstand in self._findAllElements ("./verfahrensgegenstand_Zeitraum", instanz): 
                instanzData['verfahrensgegenstand'].append(self._parseVerfahrensgegenstand(gegenstand))

            instanzGericht=self.lookup.xjustizValue ("GDS.Gerichte", self._findElementText(".//instanzbehoerde/gericht", instanz, code=True), verNo = self._getListVersion(".//instanzbehoerde/gericht", instanz))
            instanzData['auswahl_instanzbehoerde']={
            'name':instanzGericht,            
            'type':'GDS.Gerichte'
            }
            instanzData['aktenzeichen']={}
            instanzData['aktenzeichen']['aktenzeichen.freitext'] = self._findElementText('.//instanzdaten/aktenzeichen', instanz)
            #Von 2.4.0 nicht unterstützt
            instanzData['telekommunikation']=[]
            
            self.grunddaten['instanzen'][instanzData['instanznummer']]=instanzData

        ## Terminsdaten ##
        self.termine=[]
        for termin in self._findAllElements ("./grunddaten/verfahrensdaten/terminsdaten"):
            self.termine.append(self._parseTermin(termin))
        for fortsetzungstermin in self._findAllElements ("./grunddaten/verfahrensdaten/fortsetzungsterminsdaten"):
            self.termine.append(self._parseTermin(fortsetzungstermin))
        
        ####### Schriftgutobjekte #######
        #Von 2.4.0 nicht unterstützt
        self.schriftgutobjekte['anschreiben'] = ''
        
        self.schriftgutobjekte['dokumente']   = self._parseDokumente()
        self.schriftgutobjekte['akten']       = self._parseAkten()
        
        self.schriftgutobjekte['akten'].update(self._parseAkten(path='./teilakte')) 
        #teilakten hinzufügen
        
    #Gibt alle Dokumente einer Akte zurück. 
    #Ohne ID werden die Dokumente der obersten Ebene zurückgegeben  
    def getDocuments(self, aktenID=None):
        documents={}
        if aktenID is None:
            if self.schriftgutobjekte['dokumente']:
                documents=self.schriftgutobjekte['dokumente']
        elif self.schriftgutobjekte['akten']:
            documents=self._findDocsInAktenbaum(self.schriftgutobjekte['akten'], aktenID)
                    
        return documents
    
class parser351(parser341):  
    def __init__(self, filename=None):
        super().__init__(filename)

    def _parseAbsenderEmpfaenger(self, type):
        aktenzeichen = self._getSubTexts(f'./nachrichtenkopf/aktenzeichen.{type}', newline=' | ')

        auswahl     = self._findElement(f'./nachrichtenkopf/auswahl_{type}')
        
        if   self._tagInAuswahl (f'{type}.sonstige', auswahl):
            name = self._findElementText(f'.//auswahl_{type}/{type}.sonstige')
        elif self._tagInAuswahl (f'{type}.gericht', auswahl):
            name = self.lookup.xjustizValue ("GDS.Gerichte", self._findElementText(f'.//auswahl_{type}/{type}.gericht', code=True), verNo = self._getListVersion(f'.//auswahl_{type}/{type}.gericht'))
        elif self._tagInAuswahl (f'{type}.rvTraeger', auswahl):
            name = self.lookup.xjustizValue ('GDS.RVTraeger', self._findElementText(f'.//auswahl_{type}/{type}.rvTraeger', code=True), verNo = self._getListVersion(f'.//auswahl_{type}/{type}.rvTraeger'))
        elif self._tagInAuswahl (f'{type}.polizeibehoerde', auswahl):
            name = self.lookup.xjustizValue ('GDS.Polizeibehoerden', self._findElementText(f'.//auswahl_{type}/{type}.polizeibehoerde', code=True), verNo = self._getListVersion(f'.//auswahl_{type}/{type}.polizeibehoerde'))
        else:
            name = ''
        
        return (name, aktenzeichen)

    def _parseBehoerde(self, auswahlNode):
        behoerde={}
        if   self._tagInAuswahl ('sonstige', auswahlNode):
            behoerde['name'] = self._findElementText("./sonstige", auswahlNode)
            behoerde['type'] = 'sonstige'
        elif self._tagInAuswahl ('gericht', auswahlNode):
            behoerde['name'] = self.lookup.xjustizValue ("GDS.Gerichte", self._findElementText("./gericht", auswahlNode , code=True), verNo = self._getListVersion("./gericht", element=auswahlNode ))
            behoerde['type'] ='GDS.Gerichte'
        elif self._tagInAuswahl ('polizeibehoerde', auswahlNode):
            behoerde['name'] = self.lookup.xjustizValue ("GDS.Polizeibehoerden", self._findElementText("./polizeibehoerde", auswahlNode , code=True), verNo = self._getListVersion("./polizeibehoerde", element=auswahlNode ))
            behoerde['type'] ='GDS.Polizeibehoerde'    
        elif self._tagInAuswahl ('beteiligter', auswahlNode):
            behoerde['name'] = self._findElementText("./beteiligter/ref.beteiligtennummer", auswahlNode)
            behoerde['type'] ='GDS.Ref.Beteiligtennummer'
        return behoerde 
    
    def _parseDokumente(self, path='./schriftgutobjekte/dokument', element=None):
        element = self._root if element is None else element
        documents={}
        documentNodes= self._findAllElements(path, element)
        if documentNodes != '':
            simpleValues=(  
                'id',
                'nummerImUebergeordnetenContainer',
                'fremdesGeschaeftszeichen',
                'posteingangsdatum',
                'datumDesSchreibens',
                'veraktungsdatum',
                'scanDatum',
                'ersetzenderScan',
                'anzeigename',
                'akteneinsicht',
                'absenderAnzeigename',
                'adressatAnzeigename',
                'justizkostenrelevanz',
                'ruecksendungEEB.erforderlich',
                'zustellung41StPO',
                'nurMetadaten',
                'ersteSeitennummer',
                'letzteSeitennummer',
                'erstellungszeitpunkt'
            )
            for documentNode in documentNodes:
                document={}
                for simpleValue in simpleValues:
                    document[simpleValue]=self._findElementText('.//'+simpleValue, documentNode)
                    
                if document['scanDatum']!='' and document['ersetzenderScan']=='':
                        document['ersetzenderScan']='true'
                document['vertraulichkeitsstufe']=self.lookup.xjustizValue ("GDS.Vertraulichkeitsstufe", self._findElementText(".//vertraulichkeitsstufe", element=documentNode , code=True), verNo = self._getListVersion(".//vertraulichkeitsstufe", element=documentNode )) 
                document['dokumentklasse']       =self.lookup.xjustizValue ("GDS.Dokumentklasse", self._findElementText(".//dokumentklasse", element=documentNode , code=True), verNo = self._getListVersion(".//dokumentklasse", element=documentNode )) 
                document['dokumententyp']        =self.lookup.xjustizValue ("GDS.Dokumenttyp", self._findElementText(".//dokumententyp", element=documentNode , code=True), verNo = self._getListVersion(".//dokumententyp", element=documentNode ))  
                
                document['personen']=[]
                for person in self._findAllElements('.//person/ref.beteiligtennummer', element=documentNode):
                    document['personen'].append(person.text)
                
                document['verweise']=[]
                for verweis in self._findAllElements('.//verweis', element=documentNode):
                    verweisParts={}
                    verweisParts['ref.sgo']        =self._findElementText('.//ref.sgo', element=verweis)
                    verweisParts['verweistyp']    =self.lookup.xjustizValue ("GDS.Verweistyp", self._findElementText("./verweistyp", element=verweis , code=True), verNo = self._getListVersion("./verweistyp", element=verweis ))   
                    document['verweise'].append(verweisParts)
                
                document['dateien']=[]
                for datei in self._findAllElements('.//datei', element=documentNode):
                    dateiData={}
                    dateiData['dateiname']     =self._findElementText('./dateiname', element=datei)
                    dateiData['versionsnummer']=self._findElementText('./versionsnummer', element=datei)
                    dateiData['bestandteil']   =self.lookup.xjustizValue ('GDS.Bestandteiltyp', self._findElementText("./bestandteil", element=datei , code=True), verNo = self._getListVersion("./bestandteil", element=datei))  
                    
                    dateiData['dateiname.bezugsdatei']=[]
                    for bezugsdatei in self._findAllElements ('./dateiname.bezugsdatei', element=datei):
                        dateiData['dateiname.bezugsdatei'].append(bezugsdatei.text)
                    
                    document['dateien'].append(dateiData)
                
                documents[document['id']]=document
        return documents    
    
    def _parseBeteiligung(self, beteiligungNode):
        beteiligung={}
        beteiligung['rolle']=[]
        for rolle in self._findAllElements ("./rolle", beteiligungNode):
            rolleData={}
            rolleData['rollennummer']= self._findElementText("./rollennummer", rolle)
            rolleData['nr']= self._findElementText("./nr", rolle)
            if not rolleData['nr']:
                rolleData['nr']=1
            rolleData['geschaeftszeichen']= self._findElementText("./geschaeftszeichen", rolle)      
            rolleData['sonstigeBezeichnung']=[]
            for bezeichnung in self._findAllElements (".//sonstigeBezeichnung", rolle): 
                rolleData['sonstigeBezeichnung'].append(bezeichnung.text)
            rolleData['dienstbezeichnung']=[]
            for bezeichnungNode in self._findAllElements (".//dienstbezeichnung", rolle): 
                rolleData['dienstbezeichnung'].append(self.lookup.xjustizValue ("GDS.Dienstbezeichnung", self._findElementText(".", bezeichnungNode, code=True), verNo = self._getListVersion(".", element=bezeichnungNode)))    
            rolleData['rollenbezeichnung']=self.lookup.xjustizValue ("GDS.Rollenbezeichnung", self._findElementText("./rollenbezeichnung", rolle, code=True), verNo = self._getListVersion("./rollenbezeichnung", element=rolle))
            
            rolleData['referenz']=[]
            for referenz in self._findAllElements ("./referenz", rolle): 
                rolleData['referenz'].append(self._findElementText("./ref.rollennummer", referenz))
            
            rolleData['rollenID']=[]
            for rollenID in self._findAllElements ("./rollenID", rolle): 
                rollenIDData={}
                rollenIDData['id']=self._findElementText("./id", rollenID)
                rollenIDData['ref.instanznummer']=self._findElementText("./ref.instanznummer", rollenID)
                rolleData['rollenID'].append(rollenIDData)
            
            self.rollenverzeichnis[str(rolleData['rollennummer'])]= "%s %s" % (rolleData['rollenbezeichnung'], rolleData['nr'])
                    
            beteiligung['rolle'].append(rolleData)
            
        beteiligung['beteiligtennummer']=self._findElementText("./beteiligter/beteiligtennummer", beteiligungNode)
                
        beteiligterAuswahl              =self._findElement("./beteiligter/auswahl_beteiligter", beteiligungNode)
        if   self._tagInAuswahl ('ra.kanzlei', beteiligterAuswahl):
            beteiligung['beteiligter']  = self._parseKanzlei(self._findElement('./ra.kanzlei',beteiligterAuswahl))
            name=beteiligung['beteiligter']['bezeichnung.aktuell']
        elif self._tagInAuswahl ('natuerlichePerson', beteiligterAuswahl):
            beteiligung['beteiligter']  = self._parseNatuerlichePerson(self._findElement('./natuerlichePerson',beteiligterAuswahl))
            name=beteiligung['beteiligter']['vollerName']['nachname'].upper()+' '+beteiligung['beteiligter']['vollerName']['vorname'] 
        elif self._tagInAuswahl ('organisation', beteiligterAuswahl):
            beteiligung['beteiligter']  = self._parseOrganisation(self._findElement('./organisation',beteiligterAuswahl))
            name=beteiligung['beteiligter']['bezeichnung.aktuell']
        else:
            beteiligung['beteiligter']  = {}
        
        if beteiligung['beteiligtennummer']:
            self.beteiligtenverzeichnis[beteiligung['beteiligtennummer']]=name
        
        return beteiligung
    
    def _parseNachrichtenkopfBasics(self):  
        ####### Nachrichtenkopf (Alle Werte nach Spezifikation 3.5.1 unterstützt) #######
              
        self.nachricht['erstellungszeitpunkt']   = self._findElementText("./nachrichtenkopf/erstellungszeitpunkt")
        self.nachricht['eigeneID']               = self._findElementText("./nachrichtenkopf/eigeneNachrichtenID")
        self.nachricht['fremdeID']               = self._findElementText("./nachrichtenkopf/fremdeNachrichtenID")
        self.nachricht['prozessID']              = self._findElementText("./nachrichtenkopf/nachrichtenuebergreifenderProzess/prozessID")
        self.nachricht['nachrichtenNummer']      = self._findElementText("./nachrichtenkopf/nachrichtenuebergreifenderProzess/nachrichtenNummer")
        self.nachricht['nachrichtenAnzahl']      = self._findElementText("./nachrichtenkopf/nachrichtenuebergreifenderProzess/nachrichtenAnzahl")
        self.nachricht['produktName']            = self._findElementText("./nachrichtenkopf/herstellerinformation/nameDesProdukts")
        self.nachricht['produktHersteller']      = self._findElementText("./nachrichtenkopf/herstellerinformation/herstellerDesProdukts")
        self.nachricht['produktVersion']         = self._findElementText("./nachrichtenkopf/herstellerinformation/version")
        self.nachricht['routingInformationAusSafe']   = self._findElementText("./nachrichtenkopf/routingInformationAusSafeverzeichnis.empfaenger")
        self.nachricht['sendungsprioritaet']     = self.lookup.xjustizValue ("GDS.Sendungsprioritaet", self._findElementText("./nachrichtenkopf/sendungsprioritaet", code=True), verNo = self._getListVersion("./nachrichtenkopf/sendungsprioritaet"))

        self.nachricht['ereignisse']             = ''
        for ereignis in self._findAllElements ("./nachrichtenkopf/ereignis", code=True):
            if len(ereignis.text)>0: 
                ereignisValue=self.lookup.xjustizValue ('GDS.Ereignis', ereignis.text)
                if len(self.nachricht['ereignisse'])>0: self.nachricht['ereignisse'] += ' | ' 
                self.nachricht['ereignisse'] += ereignisValue
        
        self.nachricht['vertraulichkeit']                          = {}
        self.nachricht['vertraulichkeit']['vertraulichkeitsstufe'] = self.lookup.xjustizValue ('GDS.Vertraulichkeitsstufe', self._findElementText("./nachrichtenkopf/vertraulichkeit/vertraulichkeitsstufe", code=True), verNo = self._getListVersion("./nachrichtenkopf/vertraulichkeit/vertraulichkeitsstufe"))
        self.nachricht['vertraulichkeit']['vertraulichkeitsgrund'] = self._findElementText("./nachrichtenkopf/vertraulichkeit/vertraulichkeitsgrund")
        
        return self.nachricht
    
    def _parseRechtsform(self, rechtsform):
        data={}
        data['rechtsform']         = self.lookup.xjustizValue ('Rechtsformen', self._findElementText("./rechtsform", rechtsform, code=True), verNo = self._getListVersion("./rechtsform", element=rechtsform))
        data['weitereBezeichnung'] = self._findElementText('./weitereBezeichnung', rechtsform)
        
        return data
        
    def _parseRegistrierung(self, registrierung):
        data={}
        
        items=(
            'registernummer',
            'reid',
            'lei',
            'euid'             
        )
        
        for item in items:
            data[item]= self._findElementText('./' + item, registrierung)
        
        data['auswahl_registerbehoerde']={}
        
        data['auswahl_registerbehoerde']['inlaendischesRegistergericht']={}
        data['auswahl_registerbehoerde']['inlaendischesRegistergericht']['gericht']=self.lookup.xjustizValue ("GDS.Gerichte", self._findElementText("./auswahl_registerbehoerde/inlaendischesRegistergericht/gericht", registrierung, code=True), verNo = self._getListVersion("./auswahl_registerbehoerde/inlaendischesRegistergericht/gericht", element=registrierung))
        data['auswahl_registerbehoerde']['inlaendischesRegistergericht']['registerart']=self.lookup.xjustizValue ("GDS.Registerart", self._findElementText("./auswahl_registerbehoerde/inlaendischesRegistergericht/registerart", registrierung, code=True), verNo = self._getListVersion("./auswahl_registerbehoerde/inlaendischesRegistergericht/registerart", element=registrierung))
        
        data['auswahl_registerbehoerde']['sonstigeRegisterbehoerde']={}
        data['auswahl_registerbehoerde']['sonstigeRegisterbehoerde']['registerbehoerde']   =self._findElementText('./auswahl_registerbehoerde/sonstigeRegisterbehoerde/registerbehoerde', registrierung)
        data['auswahl_registerbehoerde']['sonstigeRegisterbehoerde']['registerbezeichnung']=self._findElementText('./auswahl_registerbehoerde/sonstigeRegisterbehoerde/registerbezeichnung', registrierung)
        
        data['auswahl_registerbehoerde']['auslaendischeRegisterbehoerde']=self.lookup.xjustizValue ("GDS.BRIS-ListOfRegisters", self._findElementText("./auswahl_registerbehoerde/auslaendischeRegisterbehoerde", registrierung, code=True), getFromColumnRef='English-name-of-register', verNo = self._getListVersion("./auswahl_registerbehoerde/auslaendischeRegisterbehoerde", element=registrierung))
        data['auswahl_registerbehoerde']['auslaendischeRegisterbehoerdeName']=self._findElementText("./auswahl_registerbehoerde/auslaendischeRegisterbehoerde", registrierung, code='name')                    
        
        return data