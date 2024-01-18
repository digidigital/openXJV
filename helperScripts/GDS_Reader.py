#!/usr/bin/env python3
'''
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
import re
import os
import json
import lxml.etree as ET
from datetime import datetime

class Codelistmaker:
    def __init__(self):
        self.debug = False
        self.metadaten = {'version':'0.0',
                          'nameTechnisch':'unbekannt',
                          'nameKurz':{0:{'value':'unbekannt'}},
                          'nameLang':{0:{'value':'unbekannt'}},
                          }
        self.spalten= {}
        self.daten={}
        
    def add_metadata(self, version=None, nameTechnisch=None, nameKurz=None, nameLang=None):
        if version:
            #TODO
            self.metadaten['version'] = float(version) if isinstance(version, int) else version    
        if nameTechnisch:
            self.metadaten['nameTechnisch'] = nameTechnisch
        if nameKurz:
            self.metadaten['nameKurz'][0]['value'] = nameKurz
        if nameLang:
            self.metadaten['nameLang'][0]['value'] = nameLang            
    
    def add_data(self, row):
        rowDict={}
        for item in row:
            rowDict[len(rowDict)]=item
        self.daten[len(self.daten)]=rowDict

    def add_column(self, spaltennameLang='', spaltennameTechnisch='', datentyp = "string", codeSpalte = False, verwendung='required', empfohleneCodeSpalte = False):    
        column = {'spaltennameLang': str(spaltennameLang),
                 'spaltennameTechnisch': str(spaltennameTechnisch),
                 'datentyp': datentyp,
                 'codeSpalte': codeSpalte,
                 'verwendung': verwendung,
                 'empfohleneCodeSpalte': empfohleneCodeSpalte}
        self.spalten[len(self.spalten)]=column

    def get_list(self):
        return {'metadaten':self.metadaten,
                'spalten':self.spalten,
                'daten':self.daten}

class Codeliste:

    def __init__(self, codelist=None):
        self.debug = False
        self.list_name = None
        self.lists = {}
        self.newest_version = 0

        if codelist:         
            self.add_version(codelist)
    
    def add_version(self, codelist=None):
        self.list_name=codelist['metadaten']['nameKurz'][0]['value']
        list_version=codelist['metadaten']['version']
        if re.match(r"\d{4}-\d\d-\d\d", str(list_version)):
            version1 = datetime.strptime(list_version, "%Y-%m-%d")
            version2 = datetime.strptime(self.newest_version, "%Y-%m-%d") if self.newest_version != 0 else datetime.strptime('1000-01-01', "%Y-%m-%d") 
            self.newest_version = list_version if version1 > version2 else self.newest_version
            self.lists[str(list_version)]=codelist
        else:
            self.newest_version = float(list_version) if float(list_version) > self.newest_version else float(self.newest_version) 
            self.lists[float(list_version)]=codelist

        if self.debug and len(codelist['spalten']) > 2:
            print(f"More than two columns ({len(codelist['spalten'])}): {self.list_name} {list_version}")
    
    def versions(self):
        return [str(version) for version in self.lists.keys()]
        
    def __get_columnnumber(self, columnname = None, list_version = None):
        if not list_version:
            list_version = self.newest_version         

        columns_data=self.lists[list_version]['spalten']
        columns_count = len(columns_data)
        for column_number in range(columns_count):
            name_of_current_column_tech = columns_data[column_number]['spaltennameTechnisch']
            name_of_current_column_long = columns_data[column_number]['spaltennameLang']
            if str(columnname) in (name_of_current_column_tech, name_of_current_column_long):
                return column_number            
        
    def __get_preferred_key_column(self, list_version = None):
        if not list_version:
            list_version = self.newest_version
        columns_data=self.lists[list_version]['spalten']
        columns_count = len(columns_data)
        for column_number in range(columns_count):
            if columns_data[column_number]['empfohleneCodeSpalte']:
                return column_number   
        for column_number in range(columns_count):
            if columns_data[column_number]['codeSpalte']:
                return column_number   
        return 0    
        
    def __get_preferred_value_column(self, list_version = None):
        if not list_version:
            list_version = self.newest_version    
        columns_data=self.lists[list_version]['spalten']
        columns_count = len(columns_data)
        for column_number in range(columns_count):
            if not columns_data[column_number]['codeSpalte'] and columns_data[column_number]['verwendung'] == 'required':
                return column_number    
        for column_number in range(columns_count):
            if not columns_data[column_number]['codeSpalte']:
                return column_number  
        return 1    
        
    def get_value (self, search_term = None,  columnname_values = None, columnname_key = None, list_version = None):
        value=None
        list_version = self.newest_version if str(list_version) not in str(self.lists.keys()) or list_version == None or list_version == '' else list_version
        if columnname_key:
            keycolumnnumber = self.__get_columnnumber(columnname_key, list_version)
        else: 
            keycolumnnumber = self.__get_preferred_key_column()            
        
        if columnname_values:
            valuecolumnnumber = self.__get_columnnumber(columnname_values, list_version)
        else:
            valuecolumnnumber = self.__get_preferred_value_column()

        data=self.lists[list_version]['daten']
        row_count=len(data)
        for row in range(row_count):
            if search_term in data[row][keycolumnnumber]:
                value = data[row][valuecolumnnumber]
                break

        if self.debug and value == None:
            print('No value for: "%s" in list %s with version %s' % (str(search_term), self.list_name, str(list_version)))
                    
        return value    

class CodelistReader:
    def __init__(self, path_to_json_lists = None , path_to_xsd_lists = None):
        self.debug = False
        if path_to_json_lists == None or path_to_xsd_lists == None:
            raise AttributeError ('Path to codelists missing')
            
        #Stores all lists with name    
        self.codelist_store={}
        #Read JSON codelists
        for filename in os.listdir(path_to_json_lists):
            if filename.endswith(".json"):    
                with open(os.path.join(path_to_json_lists , filename), 'r', encoding = 'utf-8') as file:
                    codelist = json.load(file)                          
                    
                    name_kurz=codelist['metadaten']['nameKurz'][0]['value']
                    
                    if self.codelist_store.get(name_kurz):
                        
                        self.codelist_store[name_kurz].add_version(codelist)
                        if self.debug:
                            print("List %s Version %s added (%s)" % (name_kurz, str(codelist['metadaten']['version']), str(filename)))
                    else:
                        self.codelist_store[name_kurz] = Codeliste(codelist)
                        if self.debug:
                            print("List %s Version %s created (%s)" % (name_kurz, str(codelist['metadaten']['version']), str(filename)))
                              
        # Codelisten-XSD einlesen 
        ns = '{http://www.w3.org/2001/XMLSchema}'
        for filename in os.listdir(path_to_xsd_lists):
            
            if re.search("_cl_.*\.xsd$",filename) :   
            
                content = ET.parse(os.path.join(path_to_xsd_lists, filename)).getroot()
                if not "1.6" in content.find('.//versionXOEVProfil').text:
                    # Für Dateien nach XOEV 1.7.1+
                    lists= (content.findall('.//' + ns + 'simpleType'))
                else:
                    # für Dateinen nach XOEV 1.6.1    
                    lists= (content.findall('.//' + ns + 'complexType'))
                    
                for list in lists: 
                    #Metadaten auslesen
                    try:
                        name_kurz = list.find('.//codeliste/nameKurz').text
                        list_version = list.find('.//versionCodeliste/version').text
                    except Exception:
                        continue
                    
                    new_codelist = Codelistmaker() 

                    
                    if self.codelist_store.get(name_kurz) and str(list_version) in self.codelist_store[name_kurz].versions():
                        continue    
                    new_codelist.add_metadata(nameKurz = name_kurz)    
                    new_codelist.add_metadata(nameLang = list.find('.//codeliste/nameLang').text)
                    new_codelist.add_metadata(nameTechnisch = list.find('.//codeliste/nameTechnisch').text)
                    new_codelist.add_metadata(version = list_version)                                                       

                    #Spaltenbezeichnungen auslesen
                    metadata_all_columns = list.find('.//codelistenspalten')
                    for column_metadata in metadata_all_columns:
                        spaltennameTechnisch = column_metadata.tag
                        spaltennameLang =  column_metadata.find('.//spaltennameLang').text
                        datentyp = column_metadata.find('.//datentyp').text
                        codeSpalte = True if  column_metadata.find('.//codeSpalte').text == 'true' else False
                        verwendung =  column_metadata.find('.//verwendung').text
                        empfohleneCodeSpalte = True if  column_metadata.find('.//empfohleneCodeSpalte').text == 'true' else False
                        new_codelist.add_column(spaltennameLang, spaltennameTechnisch, datentyp, codeSpalte , verwendung , empfohleneCodeSpalte)

                    # Zeileninhalte auslesen und Spalten zuordnen
                    elements=list.findall('.//'+ns+'enumeration')
                    for element in elements:

                        row=[]
                        for column_number in range(len(new_codelist.spalten)):
                            column_metadata = new_codelist.spalten[column_number]                          
                            
                            if column_metadata['empfohleneCodeSpalte']:
                                row.append(element.get('value'))

                                continue
                            item_found = False
                            values = element.find('.//' + ns + 'appinfo')
                            for value in values:  

                                if value.tag == column_metadata['spaltennameTechnisch']:
                                    row.append(value.text)
                                    item_found = True
                            
                            if not item_found:
                                row.append('')
                                                                
                        new_codelist.add_data(row)
                    
                    #Codeliste speichern, sofern Zeilen ausgelesen werden konnten
                    if len(new_codelist.daten) > 0:
                        if self.codelist_store.get(name_kurz):
                            self.codelist_store[name_kurz].add_version(new_codelist.get_list())
                            if self.debug:
                                print("List %s Version %s added -> %s" % (name_kurz, str(new_codelist.get_list()['metadaten']['version']), str(filename)))
                        else:
                            
                            self.codelist_store[name_kurz] = Codeliste(new_codelist.get_list())
                            if self.debug:
                                print("List %s Version %s created -> %s" % (name_kurz, str(new_codelist.get_list()['metadaten']['version']), str(filename)))
  
    def get_value (self, list_name = None, search_term = None, list_version = None, columnname_values = None, columnname_key = None):

        if self.codelist_store.get(list_name):
            return self.codelist_store[list_name].get_value(search_term,  columnname_values, columnname_key, list_version)            
        else:
            raise ValueError('Liste %s existiert nicht' % str(list_name))
                    
class Lookup:
    '''Kompatibilitätsklasse - Übersetzt Aufruf der veralteten Lookup-Klasse auf CodelistReader'''
    def __init__(self, path_to_json_lists, path_to_xsd_lists) -> None:
        self.debug = False
        self.store = CodelistReader(path_to_json_lists, path_to_xsd_lists)
        
  
    # Bildet Suchlogik ab und liefert Wert zurück    
    def xjustizValue (self, type, searchKey=None, keyColumnRef=None, getFromColumnRef=None, verNo=None) :
            if self.debug:
                print ('Type: ' + type +' - searchKey: ' + searchKey + ' verNo: ' + str(verNo)) 
            if searchKey is None or searchKey == '': 
                if self.debug:
                    print('No Searchkey')
                return ''
            
            result = self.store.get_value(list_name = type, search_term = searchKey, list_version = verNo, columnname_values = getFromColumnRef, columnname_key = keyColumnRef)
            return_value = result if result else 'Unbekannter Wert: ' + str (searchKey) + ' in Liste: ' + str(type)
            if self.debug:
                print (return_value) 
            return return_value 
                                   
if __name__ == "__main__":
    pass
    