#!/usr/bin/python3
# coding: utf-8
'''
    openXJV.py - a viewer for XJustiz-Data
    Copyright (C) 2022 Björn Seipel

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
import os
import sys
import re
import subprocess
from shutil import copyfile
from pathlib import Path
from zipfile import ZipFile
from tempfile import TemporaryDirectory
from PyQt5.Qt import (QSettings,  
                      QStandardItemModel, 
                      QStandardItem, 
                      QHeaderView,
                      
)

from PyQt5.QtCore import QUrl, Qt, QSize
from PyQt5.QtWebEngineWidgets import (QWebEngineView, QWebEngineSettings)
from PyQt5 import uic, QtPrintSupport
from PyQt5.QtGui import (QIcon,
                         QFont, 
                         QColor, 
                         QFontDatabase,
                         QDesktopServices
                       
)
from PyQt5.QtWidgets import (QFileDialog,
                             QApplication,
                             QTableWidgetItem,
                             QListWidgetItem,
                             QMainWindow,
                             QMessageBox,
)
from appdirs import AppDirs

from xjustizParser import *

class StandardItem(QStandardItem):
    def __init__(self, txt='', id='root', font_size=12, set_bold=False, color=QColor(0, 0, 0)):
        super().__init__()
        self.id=id
        self.setEditable(False)
        self.setText(txt)

class TextObject():
    def __init__(self, delimiter=': ', newline='<br>'):
        self.text = ''
        self.delimiter=delimiter
        self.newline=newline
        self.headline=''
        self.ignoreEmptyText=False

    def addLine(self, value1=None, value2=None, prepend=False):
        if value1 and value2:
            self.text+='%s%s%s%s' % (str(value1), self.delimiter, str(value2), self.newline)

    def addRaw(self, text='', prepend=False):  
        if prepend:
            self.text=str(text) + self.text
        else:
            self.text+=str(text)

    def addHeading(self, headline, ignoreEmptyText=False):
        self.headline='<br><b><i>' + str(headline)+ '</b></i>'+self.newline
        self.ignoreEmptyText=bool(ignoreEmptyText)

    def getText(self):
        if self.ignoreEmptyText:
            return self.headline + self.text
        elif self.text:
            return self.headline + self.text
        else:
            return ''

class UI(QMainWindow):
    def __init__(self, file=None, ziplist=None):
        super(UI, self).__init__() 
        self.tempDir=TemporaryDirectory()
        self.tempfile=''
        # Needed for pyinstaller onefile...
        try:
            self.scriptRoot = sys._MEIPASS
        except Exception:
            self.scriptRoot = os.path.dirname(os.path.realpath(__file__))
        
        icon16 =os.path.join(self.scriptRoot, 'icons', 'appicon16.png')
        icon32 =os.path.join(self.scriptRoot, 'icons', 'appicon32.png')
        icon64 =os.path.join(self.scriptRoot, 'icons', 'appicon64.png')
        icon128=os.path.join(self.scriptRoot, 'icons', 'appicon128.png')
        icon256=os.path.join(self.scriptRoot, 'icons', 'appicon256.png')
        windowIcon=QIcon()
        windowIcon.addFile(icon16,(QSize(16,16)))
        windowIcon.addFile(icon32,(QSize(32,32)))
        windowIcon.addFile(icon64,(QSize(64,64)))
        windowIcon.addFile(icon128,(QSize(128,128)))
        windowIcon.addFile(icon256,(QSize(256,256)))
        self.setWindowIcon(windowIcon)

        self.dirs = AppDirs("OpenXJV", "digidigital", version="0.1")
        os.makedirs(self.dirs.user_data_dir, exist_ok=True) 
        
        
        #Don't use Path.home() directly in case we are in a snap package
        self.homedir=os.environ.get('SNAP_REAL_HOME', Path.home())
        
        # Load the .ui file
        uic.loadUi(self.scriptRoot + '/ui/openxjv.ui', self) 
        
        ###Prepare settings###
        self.settings = QSettings('OpenXJV','Björn Seipel')
        # settings.setValue("monkey", 1)
        # margin = int(settings.value("editor/wrapMargin", None))
        # settings.remove(value)
        
        QWebEngineSettings.globalSettings().setAttribute(QWebEngineSettings.PluginsEnabled,True)
        QWebEngineSettings.globalSettings().setAttribute(QWebEngineSettings.ErrorPageEnabled,False)
        
        ###Load fonts###
        fontDir = self.scriptRoot + '/fonts/'
        fontDatabase=QFontDatabase() ; 
        fontFiles=[
            "ubuntu-font-family-0.83/Ubuntu-R.ttf",
            "materialicons/MaterialIcons-Regular.ttf"
        ] 
        for font in fontFiles:          
            fontDatabase.addApplicationFont(fontDir + font) 
       
        self.setFont(QFont('Ubuntu'))
        self.tabs.setFont(QFont('Ubuntu'))
        
        ###set toolbarButtonwidth###        
        for child in self.toolBar.children():
            if child.__class__.__name__ == 'QToolButton':
                child.setFixedWidth(25)
        

        
        #Adjust table header style         
        self.docTableView.horizontalHeader().setHighlightSections(False)
        self.termineTableView.horizontalHeader().setHighlightSections(False)    
       
        ###setpaths to PDF viewers###
        if sys.platform.lower().startswith('win'):
            urlPath = self.scriptRoot.replace("\\","/")
            winslash='/'
        else:
            urlPath = self.scriptRoot
            winslash=''
        self.viewerPaths={
            "PDFjs":"file://%s%s/html/pdfjs/web/viewer.html?file=" % (winslash, urlPath),   
            "chromium":"file://%s" % winslash, 
        }            
        
        
        ###columns/order to display in document view###
        self.docTableAttributes = [
            'nummerImUebergeordnetenContainer',
            'datumDesSchreibens',
            'posteingangsdatum',
            'veraktungsdatum',
            'anzeigename',
            'dokumententyp',
            'dokumentklasse',
            'bestandteil',
            'ruecksendungEEB.erforderlich',
            'fremdesGeschaeftszeichen',
            'akteneinsicht',
            'absenderAnzeigename',
            'adressatAnzeigename',
            'justizkostenrelevanz',
            'zustellung41StPO',
            'vertraulichkeitsstufe',
            'dateiname.bezugsdatei',
            'versionsnummer',
            'dateiname',
            
        ]

        self.docHeaderColumnsSettings={
            #key                                 headertext                         action for menu-item /config                    default visibility  width of column                 
            ''                               :{'headertext':''                   ,'setting':None                                  ,'default':True , 'width':10},
            ''                               :{'headertext':''                   ,'setting':None                                  ,'default':True , 'width':10},
            'nummerImUebergeordnetenContainer':{'headertext':'#'                   ,'setting':None                                  ,'default':True , 'width':45},
            'dateiname'                       :{'headertext':'Dateiname'           ,'setting':None                                  ,'default':True , 'width':None},
            'anzeigename'                     :{'headertext':'Anzeige-\nname'      ,'setting':None                                  ,'default':True , 'width':None},
            'datumDesSchreibens'              :{'headertext':'Datum'               ,'setting':self.actionDatumColumn                ,'default':True , 'width':95},
            'posteingangsdatum'               :{'headertext':'Eingang'             ,'setting':self.actionEingangsdatumColumn        ,'default':True,  'width':195},
            'veraktungsdatum'                 :{'headertext':'Veraktung'           ,'setting':self.actionVeraktungsdatumColumn      ,'default':True,  'width':95},
            'dokumententyp'                   :{'headertext':'Typ'                 ,'setting':self.actionDokumententypColumn        ,'default':True , 'width':None},
            'dokumentklasse'                  :{'headertext':'Klasse'              ,'setting':self.actionDokumentenklasseColumn     ,'default':True , 'width':None},
            'bestandteil'                     :{'headertext':'Bestandteil'         ,'setting':self.actionBestandteilColumn          ,'default':True , 'width':None},
            'versionsnummer'                  :{'headertext':'Version-\nnr.'       ,'setting':self.actionVersionsnummerColumn       ,'default':False, 'width':None},
            'dateiname.bezugsdatei'           :{'headertext':'Bezug\nzu'           ,'setting':self.actionBezugsdateinameColumn      ,'default':False, 'width':None},
            'ruecksendungEEB.erforderlich'    :{'headertext':'EEB'                 ,'setting':self.actionEEB_HinweisColumn          ,'default':True,  'width':45},
            'zustellung41StPO'                :{'headertext':'§41\nStPO'           ,'setting':self.actionZustellung_StPO_41Column   ,'default':False, 'width':40},
            'akteneinsicht'                   :{'headertext':'Akten-\neinsicht'    ,'setting':self.actionAkteneinsichtColumn        ,'default':False, 'width':60},
            'absenderAnzeigename'             :{'headertext':'Absender'            ,'setting':self.actionAbsenderColumn             ,'default':False, 'width':None},
            'adressatAnzeigename'             :{'headertext':'Adressat'            ,'setting':self.actionAdressatColumn             ,'default':False, 'width':None},
            'justizkostenrelevanz'            :{'headertext':'Kosten-\nrele-\nvanz','setting':self.actionJustizkostenrelevanzColumn ,'default':False, 'width':58},
            'fremdesGeschaeftszeichen'        :{'headertext':'fr. Gz.'             ,'setting':self.actionfrGeschaeftszeichenColumn  ,'default':False, 'width':None},
            'vertraulichkeitsstufe'           :{'headertext':'Vertraulich'         ,'setting':self.actionVertraulichkeitsstufeColumn,'default':False, 'width':None},           
        }
         
        self.isDocColumnEmpty={}
        
  
        
        
        
        ####initial settings####
        self.inhaltView.setHeaderHidden(True)
        
        self.plusFilter.setText(self.settings.value("plusFilter", ''))
        self.minusFilter.setText(self.settings.value("minusFilter", ''))
        self.__readSettings()
        
        #Load empty viewer
        self.url=self.viewerPaths['PDFjs'] 
        self.browser.setUrl(QUrl.fromUserInput(self.url))
      

        #########self.favoriteniew##########
        self.favorites = set()

        #########load initial files##########
        inputfile=self.settings.value("lastFile", None)
        if file and file.lower().endswith('xml'):
            self.getFile(file)
        elif ziplist:
            for zip in ziplist:
                if not zip.lower().endswith('zip'):
                    sys.exit("Fehler: Die übergebene Liste enthält nicht ausschließlich ZIP-Dateien.")
            print(ziplist)
            self.getZipFiles(files=ziplist)    
        elif inputfile:
            self.getFile(inputfile)

        ####connections####
        self.actionOeffnen.triggered.connect(lambda:self.getFile())
        self.actionZIP_ArchiveOeffnen.triggered.connect(self.__selectZipFiles)
        self.actionUeberOpenXJV.triggered.connect(self.__displayInfo)
        self.actionAnleitung.triggered.connect(self.__openManual)
        self.actionSupport_anfragen.triggered.connect(self.__supportAnfragen)
        self.actionAktenverzeichnis_festlegen.triggered.connect(lambda:self.__chooseStartFolder())
        self.inhaltView.clicked.connect(lambda clicked: self.__updateSelectedInhalt(clicked, self.akte))
        self.docTableView.doubleClicked.connect(self.__getDocTableAction)
        self.termineTableView.clicked.connect(self.__setTerminDetailView)
        self.plusFilter.textChanged.connect(self.__filtersTriggered)
        self.minusFilter.textChanged.connect(self.__filtersTriggered)
        self.filterLeeren.clicked.connect(self.__resetFilters)
        self.filterMagic.clicked.connect(self.__magicFilters)
        self.favoritenView.doubleClicked.connect(self.__getFavoriteViewAction)
        self.deleteFavoriteButton.clicked.connect(self.__removeFavorite)
        self.actionZuruecksetzen.triggered.connect(self.__resetSettings)   
        self.actionNachrichtenkopf.triggered.connect(self.__updateSettings)
        self.actionFavoriten.triggered.connect(self.__updateSettings)
        self.actionLeereSpaltenAusblenden.triggered.connect(self.__updateSettings)
        self.actionnativ.triggered.connect(self.__viewerSwitch)
        self.actionPDF_js.triggered.connect(self.__viewerSwitch)
        self.actionChromium.triggered.connect(self.__viewerSwitch)
        self.browser.page().profile().downloadRequested.connect(self.__downloadRequested)
        self.browser.page().printRequested.connect(self.__printRequested)
        for columnSetting in self.docHeaderColumnsSettings.values():
            if columnSetting['setting']:
                columnSetting['setting'].triggered.connect(self.__updateSettings)
        
        def __del__(self):
            self.settings.sync()
        
    def __displayInfo(self):
        QMessageBox.information(self, "Information",
        "openXJV 0.5\n"
        "Lizenz: GPL v3\n"
        "(c) 2022 Björn Seipel\nKontakt: support@digidigital.de\nWebsite: https://openXJV.de\n\n" 
        "Die Anwendung nutzt folgende Komponenten:\n"
        "Qt5 - LGPLv3\n"
        "PyQT4 - GNU GPL v3\n"
        "appdirs - MIT License\n"
        "lxml - BSD License\n"
        "PDF.js - Apache 2.0 License\n"
        "Ubuntu Font - UBUNTU FONT LICENCE Version 1.0\n"
        "Material Icons Font - Apache 2.0 License\n"
        "pyinstaller - GPLv2 or later\n"
        "python 3.x - PSF License\n\n"
        "Lizenztexte und Quellcode-Links können dem Benutzerhandbuch entnommen werden."
        
        
        )
    
    def __supportAnfragen(self):
        QDesktopServices.openUrl(QUrl("mailto:?to=support@digidigital.de&subject=Supportanfrage zu openXJV", QUrl.TolerantMode))
    
    def __updateSelectedInhalt(self, val, akte):
        aktenID=val.siblingAtColumn(val.column()+1).data()
        self.__setMetadata(akte, aktenID)
        self.__setDocumentTable(aktenID)
        self.__filtersTriggered()   
    
    def __filtersTriggered(self):
        filteredRows = self.__filterTableRows(self.docTableView, self.plusFilter.text(), self.minusFilter.text())
        
        for row in range(self.docTableView.rowCount()):
            self.docTableView.hideRow(row)
        for row in filteredRows:
            self.docTableView.showRow(row)

        self.settings.setValue("minusFilter", self.minusFilter.text())
        self.settings.setValue("plusFilter", self.plusFilter.text())
   
    def __magicFilters(self):
        self.minusFilter.setText(self.minusFilter.text()+' .pks .p7s .xml .pkcs7')
        self.__filtersTriggered()
        
    def __resetFilters(self):
        self.plusFilter.setText('')
        self.minusFilter.setText('')
        self.__filtersTriggered()
                
    def __filterTableRows (self, tableObj, plusFilterStr, minusFilterStr):
        rows=set()
        if plusFilterStr.replace(" ", ""):
            for filter in plusFilterStr.split():
                for hit in  tableObj.findItems(filter, Qt.MatchContains):
                    rows.add(hit.row())
        else:            
            for row in range(self.docTableView.rowCount()):
                rows.add(row)
                    
        for filter in minusFilterStr.split():
            for hit in  tableObj.findItems(filter, Qt.MatchContains):
                if hit.row() in rows:
                    rows.remove(hit.row()) 
        return rows
   
    def __setTerminTable (self, termine):
        #clear tableWidget
        self.termineTableView.setRowCount(0)
        self.termineTableView.setColumnCount(0)  
        self.isTerminColumnEmpty={}
        
        self.terminTableColumnsHeader=[
            'UUID',
            'Datum',
            'Zeit',
            'Öffent-\nlich',
            'Haupt- oder\nFolgetermin',
            'Terminsart',
            'Spruchkörper'
        ]
        
        if len(termine):
            self.termineTableView.setRowCount(len(termine))
            self.termineTableView.setColumnCount(7) 
            
            #set header
            self.termineTableView.horizontalHeader().setStretchLastSection(True)
            self.termineTableView.horizontalHeader().setDefaultAlignment(Qt.AlignHCenter)
            self.termineTableView.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
           
                                              
            columnCount=0
            for item in self.terminTableColumnsHeader:
                headerItem=self.__tableItem(item, 'Ubuntu')
                headerItem.setTextAlignment(Qt.AlignCenter)
                self.termineTableView.setHorizontalHeaderItem(columnCount, headerItem)
                columnCount+=1
            #add rows
            rowNo=0    
            
            for termin in termine:
                
                tempItem=self.__tableItem(termin['uuid'])
                self.termineTableView.setItem(rowNo, 0, tempItem)    
                
                datum=zeit=termin['terminszeit']['terminsdatum']
                tempItem=self.__tableItem(datum)
                tempItem.setTextAlignment(Qt.AlignCenter)
                self.termineTableView.setItem(rowNo, 1, tempItem)
                
                zeit=termin['terminszeit']['auswahl_terminszeit']['terminsuhrzeit'] + termin['terminszeit']['auswahl_terminszeit']['terminszeitangabe']
                tempItem=self.__tableItem(zeit)
                tempItem.setTextAlignment(Qt.AlignCenter)
                self.termineTableView.setItem(rowNo, 2, tempItem)
                
                oeffentlich=self.__replaceTrueFalse(termin['oeffentlich'])
                tempItem=self.__tableItem(oeffentlich)
                tempItem.setTextAlignment(Qt.AlignCenter)
                self.termineTableView.setItem(rowNo, 3, tempItem)
                
                
                if termin['hauptterminsdatum']:
                    terminTyp='Folgetermin'
                else:
                    terminTyp='Haupttermin'
                tempItem=self.__tableItem(terminTyp)
                tempItem.setTextAlignment(Qt.AlignCenter)
                self.termineTableView.setItem(rowNo, 4, tempItem)
                
                terminsart=termin['terminsart']
                tempItem=self.__tableItem(terminsart)
                tempItem.setTextAlignment(Qt.AlignCenter)
                self.termineTableView.setItem(rowNo, 5, tempItem)
                
                spruchkoerper=termin['spruchkoerper']
                tempItem=self.__tableItem(spruchkoerper)
                tempItem.setTextAlignment(Qt.AlignCenter)
                self.termineTableView.setItem(rowNo, 6, tempItem)
                
                rowNo+=1
                
            
            self.termineTableView.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
            self.termineTableView.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)    
            self.termineTableView.setColumnWidth(3,40)
            self.termineTableView.setColumnWidth(4,115)
            self.termineTableView.sortItems(1)
            self.termineTableView.hideColumn(0)
            self.termineTableView.clearSelection()   
            
    def __setDocumentTable(self, akteID=None):      
        #clear tableWidget
        self.docTableView.setRowCount(0)
        self.docTableView.setColumnCount(0)  
        
        data=[]
        #sort data & add action Icons
        for row in self.akte.getFileRows(akteID):
            rowData= []
            
            #Bookmark+ icon, Open external icon in "Material Font"
            actionIcons= ['','']
            
            #Icons first
            rowData+=actionIcons
            #data second
            rowData+=self.__arrangeData(row, self.docTableAttributes)
            
            #add row
            data.append(rowData)
            
            
        #set data
        if data:

            self.docTableView.setRowCount(len(data))
            self.docTableView.setColumnCount(len(data[0]))
            
            #Add columns with icons for "add to favorits" and "open external"
            self.docTableView.setHorizontalHeaderItem(0, self.__tableItem('', 'Material Icons'))
            if self.docHeaderColumnsSettings['']['width']:
                self.docTableView.setColumnWidth(0, self.docHeaderColumnsSettings['']['width'])
                self.docTableView.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
            self.docTableView.setHorizontalHeaderItem(1,  self.__tableItem('', 'Material Icons'))
            if self.docHeaderColumnsSettings['']['width']:
                self.docTableView.setColumnWidth(1, self.docHeaderColumnsSettings['']['width'])
                self.docTableView.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
            
            columnCount=2
            for item in self.docTableAttributes:
                headerText=self.docHeaderColumnsSettings[item]['headertext']
                self.docTableView.setHorizontalHeaderItem(columnCount, self.__tableItem(headerText, 'Ubuntu'))

                # set fixed width for items that have one defined...
                if self.docHeaderColumnsSettings[item]['width']:
                    self.docTableView.setColumnWidth(columnCount, self.docHeaderColumnsSettings[item]['width'])
                    self.docTableView.horizontalHeader().setSectionResizeMode(columnCount, QHeaderView.Fixed)
                columnCount+=1
                
            rowNo=0
            self.isDocColumnEmpty={}
            for row in data:
                itemNo=0
                for item in row:
                    #Material Icons font for first two columns
                    if itemNo > 1:
                        font='Ubuntu'  
                    else: 
                        font='Material Icons'
                    
                    #Leading zeros fo '#'-Items that are not empty   
                    if itemNo==2 and item:
                        item=item.zfill(4) 
                           
                    tempItem=self.__tableItem(item, font)
                    tempItem.setTextAlignment(Qt.AlignCenter)
                    if itemNo==0:
                        tempItem.setToolTip('Doppelklick fügt Datei den Favoriten hinzu.')    
                    elif itemNo==1:
                        tempItem.setToolTip('Doppelklick öffnet Datei mit Standardprogramm.') 
                    
                    self.docTableView.setItem(rowNo, itemNo, tempItem) 
                    
                    #Set column to not empty (False) if item has content
                    #Set to empty (True) if value for column does not exist 
                    #or has any other value than False  
                    if item!='':
                        self.isDocColumnEmpty[itemNo]=False
                    elif self.isDocColumnEmpty.get(itemNo) != False:
                        self.isDocColumnEmpty[itemNo]=True                
                    itemNo+=1
                rowNo+=1
            self.__updateVisibleColumns()
            
    def __updateVisibleColumns(self):
        for columnNo in range(self.docTableView.columnCount()):
            self.docTableView.setColumnHidden(columnNo, False)
        
        columnNo=2
        for attribute in self.docTableAttributes:
            if self.docHeaderColumnsSettings[attribute]['setting']:
               self.docTableView.setColumnHidden(columnNo, not self.docHeaderColumnsSettings[attribute]['setting'].isChecked())     
            columnNo+=1  
        
        if self.actionLeereSpaltenAusblenden.isChecked():       
            self.__hideEmptyColumns() 
       
    def __hideEmptyColumns(self):
        for columnNo, isEmpty in self.isDocColumnEmpty.items():
            if isEmpty:
                self.docTableView.setColumnHidden(columnNo, True)       
    
    def __arrangeData(self, dictOfMetadata, attributes):
        arrangedRow=[]      
        for attribute in attributes:
            if isinstance(dictOfMetadata[attribute], str):
                arrangedRow.append(self.__replaceTrueFalse(dictOfMetadata[attribute]))
            if isinstance(dictOfMetadata[attribute], list):
                text=''
                newline=''
                for item in dictOfMetadata[attribute]:
                    if item:
                        text+=newline + item
                        newline=' '
                arrangedRow.append(text)     
        return arrangedRow
    
    def __replaceTrueFalse(self, value):
       if value.lower()=='true':
           return 'ja' 
       elif value.lower()=='false':
           return 'nein'
       return value
    
    def __tableItem (self, text, font='Ubuntu'):
        item = QTableWidgetItem(text)
        item.setFont(QFont(font))
        return item
    
    def __setMetadata(self, nachricht, aktenID=None):
        
        text=TextObject(newline='\n')
        if aktenID==None or aktenID=='':
            labelList =[
                ['nachrichtenNummer','Nachricht Nr.'],
                ['nachrichtenAnzahl','Von Nachrichten gesamt'],
                ['ereignisse','Ereignis'],
                ['eigeneID','Abs. Nachr.-ID'],
                ['fremdeID','Empf. Nachr.-ID'],
                ['prozessID','Prozess-ID'],
                ['produktName','Software'],
                ['produktHersteller','Hersteller'],
                ['produktVersion','Version'],
            ]
            for label in labelList:
                text.addLine(label[1], nachricht.nachricht[label[0]])
        else:
            akte=nachricht.getAkte(nachricht.schriftgutobjekte['akten'], aktenID)    
    
            if akte:
                text.addLine('AktenID', aktenID)
                
                eeb = 'Abgabe nicht erforderlich'
                if akte['ruecksendungEEB.erforderlich'].lower() == 'true':
                    eeb = 'Abgabe angefordert'
                text.addLine('EEB', eeb)
                
                if akte['aktentyp']:
                    for aktenzeichen in akte['aktenzeichen']:
                        text.addLine('Aktenzeichen', aktenzeichen['aktenzeichen.freitext'])
            
                for person in akte['personen']:
                    name=self.akte.beteiligtenverzeichnis.get(person)
                    if name:
                        text.addLine('Personenbezug', name)
                
                for referenz in akte['aktenreferenzen']:
                    text.addLine('ReferenzaktenID ('+referenz['aktenreferenzart']+')', referenz['id.referenzierteAkte'])
                    
                labelList =[
                ['anzeigename','Anzeigename'],    
                ['aktentyp','Aktentyp'],
                ['teilaktentyp','Teilaktentyp'],
                ['id','Akten-ID'],
                ['weiteresOrdnungskriteriumBehoerde','Weiteres Ordnungskriterium'],              
                ['abgebendeStelle','Abgebende Stelle'], 
                ['letztePaginierungProTeilakte', 'Letzte Paginierung'],
                ['vertraulichkeitsstufe','Vertraulichkeitsstufe'],              
                ['erstellungszeitpunktAkteVersand','Erstellungszeitpunkt'], 
                ]
            for label in labelList:
                text.addLine(label[1], akte[label[0]])
            
            if akte['laufzeit']:
                if akte['laufzeit']['beginn']:
                    text.addLine('Laufzeit ab', akte['laufzeit']['beginn'])
                if akte['laufzeit']['ende']:         
                    text.addLine('Laufzeit bis', akte['laufzeit']['ende'])
            
            if akte['zustellung41StPO'].lower() == 'true':
                text.addLine('Zustellung gem. §41StPO', 'ja')        
            elif akte['zustellung41StPO'].lower() == 'false':    
                text.addLine('Zustellung gem. §41StPO', 'nein')
           
        self.metadatenText.setPlainText(text.getText())
                        
    def __setNachrichtenkopf (self, absender, empfaenger, nachrichtenkopf):
        ###Inhalte setzen###
        self.absenderText.setText(absender['name'])
        self.absenderAktenzeichenText.setText(absender['aktenzeichen'])
        self.empfaengerText.setText(empfaenger['name'])
        self.empfaengerAktenzeichenText.setText(empfaenger['aktenzeichen'])
        self.erstellungszeitpunktText.setText(nachrichtenkopf['erstellungszeitpunkt'])
        self.sendungsprioritaetText.setText(self.__isSet(nachrichtenkopf['sendungsprioritaet']))
               
        ###Cursor auf erstes Zeichen setzen###
        self.absenderText.setCursorPosition(0)
        self.absenderAktenzeichenText.setCursorPosition(0)
        self.empfaengerText.setCursorPosition(0)
        self.empfaengerAktenzeichenText.setCursorPosition(0)
    
    def __isSet(self, value):
        if value == '':
            return 'nicht angegeben'
        else:
            return value
        
    def __setInhaltView(self, schriftgutobjekte):
        treeModel = QStandardItemModel()
        rootNode = treeModel.invisibleRootItem()
        
        if len(schriftgutobjekte['dokumente'])>0:
            dokumente = StandardItem('Dokumente')
            key       = StandardItem(None)
            rootNode.appendRow([dokumente, key])
        
        if len(schriftgutobjekte['akten'])>0:
            self.__getAktenSubBaum(schriftgutobjekte['akten'], rootNode) 

        self.inhaltView.setModel(treeModel)
        self.inhaltView.setColumnHidden(1, True)
        self.inhaltView.expandAll()
    
    def __addFavorite(self, filename):
            self.favorites.add(filename) 
            self.__setFavorites()
            self.statusBar.showMessage(filename + ' zu Favoriten hinzugefügt.')
    
    def __setFavorites(self):
        self.favoritenView.clear()
        
        for favorite in self.favorites:
            self.favoritenView.addItem(QListWidgetItem(favorite))
        
        self.__saveFavorites()    
    
    def __removeFavorite(self):
        if self.favoritenView.currentItem():
            filename = self.favoritenView.currentItem().text()
            self.favorites.remove(filename)
            self.__setFavorites()
            self.__saveFavorites()
            self.statusBar.showMessage(filename + ' aus Favoriten entfernt.')
            
    def __loadFavorites(self):
        self.favorites.clear()
        if self.akte.nachricht['eigeneID']:
            filepath = os.path.join(self.dirs.user_data_dir , self.akte.nachricht['eigeneID'])
            if os.path.exists(filepath):
                with open(filepath , 'r') as favoriteFile:
                    for filename in favoriteFile.readlines():
                        self.favorites.add(filename.rstrip("\n"))
            
        self.__setFavorites()
         
    def __saveFavorites(self):
        if self.akte.nachricht['eigeneID']:
            filepath = os.path.join(self.dirs.user_data_dir , self.akte.nachricht['eigeneID'])
            if self.favorites:
                with open(filepath , 'w') as favoriteFile:
                    for filename in self.favorites: 
                        favoriteFile.write(filename + '\n')
            elif os.path.exists(filepath):
                os.remove(filepath)
    
            
    def __getAktenSubBaum(self, akten, node):    
        for einzelakte in akten.values():
           
            if einzelakte['aktentyp']:
                name = einzelakte['aktentyp']
                for aktenzeichen in einzelakte['aktenzeichen']:
                    if aktenzeichen['aktenzeichen.freitext']:
                        name += ' ' + aktenzeichen['aktenzeichen.freitext']
            elif einzelakte['teilaktentyp'] != '': 
                name = einzelakte['teilaktentyp']
                 
            value = StandardItem(name)
            key   = StandardItem(einzelakte['id'])
            
            if len(einzelakte['teilakten'])>0:
                self.__getAktenSubBaum(einzelakte['teilakten'], value)
            
            node.appendRow([value, key])
    
    def __getDocTableAction (self, val):
        filenameColumn=self.docTableAttributes.index('dateiname')+2
        filename=self.docTableView.item( val.row(), filenameColumn).text()
        
        if val.column()==0:
            self.__addFavorite(filename) 
        elif self.settings.value('pdfViewer', 'PDFjs')=='nativ' or val.column()==1 or not filename.lower().endswith(".pdf"):
            self.__openFileExternal(filename)
        else:
            self.__openFileInBrowser(filename)
    
    def __openFileInBrowser(self, filename):
        filepath = os.path.join(self.basedir , filename)
        if os.path.exists(filepath): 
            self.loadedPDFpath=filepath
            self.loadedPDFfilename=filename
                        
            #Clean up any old tempfile
            if self.tempfile and os.path.isfile(self.tempfile):
                os.remove(self.tempfile)

            #Copy PDF to local temporary folder to circumvent CORS issues with PDFjs
            #if file is stored on e.g. a network share 
            self.tempfile=os.path.join(self.tempDir.name, filename)
            copyfile(filepath, self.tempfile)
            filepath=self.tempfile
            
            if sys.platform.lower().startswith('win'):
                filePath = filepath.replace("\\","/")
            else:
                filePath = filepath
            self.url=self.viewerPaths[self.settings.value('pdfViewer', 'PDFjs')] + "%s" % (filePath)
                
            self.browser.setUrl(QUrl.fromUserInput(self.url))
        else: 
            self.statusBar.showMessage('Datei existiert nicht: '+ filename) 
    
    def __getFavoriteViewAction (self, val):
        self.__openFileExternal(val.data()) 
        
    
    def __selectZipFiles(self):
        files , check = QFileDialog.getOpenFileNames(None, "XJustiz-ZIP-Archive öffnen",
                                               str(self.settings.value("defaultFolder", self.homedir)), "XJustiz-Archive (*.zip *.ZIP)")
        if check:
            self.getZipFiles(files)
    
    def getZipFiles(self, files=None):
        if files:
            self.tempPath=TemporaryDirectory()
            
            for file in files:
                try:
                    with ZipFile(file, 'r') as zip: 
                        zip.extractall(self.tempPath.name)    
                except:
                    self.statusBar.showMessage(file + ' konnte nicht entpackt werden.')
                
            self.getFile(folder=self.tempPath.name)
            
            
    def getFile(self, file=None, folder=None):
        if file and os.path.exists(file):
            self.__loadFile(file)
        elif file and not os.path.exists(file):
            pass
        elif file==None:
            
            if folder==None:
                folder=str(self.settings.value("defaultFolder", self.homedir))
            
            file , check = QFileDialog.getOpenFileName(None, "XJustiz-Datei öffnen",
                                               folder, "XJustiz-Dateien (*.xml *.XML)")
            if check:
                self.__loadFile(file)
        
    def __loadFile(self, file):    
        type=None
        with open(file) as fp:
            while True:
                line = fp.readline()
                if not line:
                    break
                if 'xjustizVersion="2.4.0"' in line:
                    type="2.4.0"
                    break
                if 'xjustizVersion="3.2.1"' in line:
                    type="3.2.1"
                    break 
        if type=="2.4.0":
            self.akte=parser240(file)
        elif type=="3.2.1":
            self.akte=parser321(file)
        else:
            self.statusBar.showMessage('Konnte keine unterstützte XJustiz-Version auslesen: %s' % file)
            return None
        try:
            type=None
            with open(file) as fp:
                while True:
                    line = fp.readline()
                    if not line:
                        break
                    if 'xjustizVersion="2.4.0"' in line:
                        type="2.4.0"
                        break
                    if 'xjustizVersion="3.2.1"' in line:
                        type="3.2.1"
                        break 
            if type=="2.4.0":
                self.akte=parser240(file)
            elif type=="3.2.1":
                self.akte=parser321(file)
            else:
                self.statusBar.showMessage('Konnte keine unterstützte XJustiz-Version auslesen: %s' % file)
                return None
        except:
            self.statusBar.showMessage('Fehler beim Öffnen der Datei: %s' % file)
            return None 
        
        self.__setDocumentTable()
        self.__setInhaltView(self.akte.schriftgutobjekte)
        self.__setNachrichtenkopf(self.akte.absender, self.akte.empfaenger, self.akte.nachricht)   
        self.__setMetadata(self.akte)
        self.__filtersTriggered()
        self.__loadFavorites()
        self.__setInstanzenView()
        self.__setBeteiligteView()
        self.__setTerminTable(self.akte.termine)
        self.terminDetailView.setHtml('')
        self.basedir=os.path.dirname(os.path.realpath(file))
        #Load empty viewer                     
        self.url=self.viewerPaths['PDFjs'] 
        self.browser.setUrl(QUrl.fromUserInput(self.url))
        self.statusBar.showMessage('Eingelesene Datei: %s - XJustiz-Version: %s' % (file, type))
        self.settings.setValue("lastFile", file)
                          
    def __chooseStartFolder(self):       
         folder = QFileDialog.getExistingDirectory(None, "Standardverzeichnis wählen",
                                        str(self.settings.value("defaultFolder", '')),
                                        QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks)
         
         if folder:
             self.settings.setValue("defaultFolder", folder)
    
    def __updateSettings(self):
        for key, value in self.docHeaderColumnsSettings.items(): 
            if value['setting']:
                self.settings.setValue(key , value['setting'].isChecked())
        self.settings.setValue('nachrichtenkopf' , self.actionNachrichtenkopf.isChecked())
        self.settings.setValue('favoriten' , self.actionFavoriten.isChecked())
        self.settings.setValue('leereSpalten' , self.actionLeereSpaltenAusblenden.isChecked())
               
        
        if self.actionChromium.isChecked():
            self.settings.setValue('pdfViewer', 'chromium')
        elif self.actionnativ.isChecked():
            self.settings.setValue('pdfViewer', 'nativ')                       
        else:    
            self.settings.setValue('pdfViewer', 'PDFjs')     
                              
        self.__updateVisibleColumns()
        self.__updateVisibleViews()

        
    def __viewerSwitch(self):
      
        if self.actionChromium.isChecked() and self.actionChromium.isEnabled():
            self.actionChromium.setEnabled(False)
            self.actionPDF_js.setChecked(False)
            self.actionPDF_js.setEnabled(True)
            self.actionnativ.setChecked(False)
            self.actionnativ.setEnabled(True)
            self.browser.setVisible(True)
           
        
        elif self.actionnativ.isChecked() and self.actionnativ.isEnabled():
            self.actionnativ.setEnabled(False)
            self.actionPDF_js.setChecked(False)
            self.actionPDF_js.setEnabled(True)
            self.actionChromium.setChecked(False)
            self.actionChromium.setEnabled(True)
            self.browser.setVisible(False)
          
        else:    
            self.actionPDF_js.setChecked(True)
            self.actionPDF_js.setEnabled(False)
            self.actionChromium.setChecked(False)
            self.actionChromium.setEnabled(True)
            self.actionnativ.setChecked(False)
            self.actionnativ.setEnabled(True)
            self.browser.setVisible(True)   
            
            
        self.__updateSettings()
    
        
    def __readSettings(self):
        for key, value in self.docHeaderColumnsSettings.items(): 
            if value['setting']:
                setTo = self.settings.value(key, 'default')
                if setTo.lower() == 'true':
                    value['setting'].setChecked(True) 
                elif setTo.lower() == 'false':
                    value['setting'].setChecked(False)
                else:    
                    value['setting'].setChecked(self.docHeaderColumnsSettings[key]['default'])
        self.actionNachrichtenkopf.setChecked(True if self.settings.value('nachrichtenkopf', 'true').lower()=='true' else False)
        self.actionFavoriten.setChecked(True if self.settings.value('favoriten', 'true').lower()=='true' else False)
        self.actionLeereSpaltenAusblenden.setChecked(True if self.settings.value('leereSpalten', 'true').lower()=='true' else False)
        
        self.actionChromium.setChecked(True if self.settings.value('pdfViewer', 'PDFjs')=='chromium' else False)
        self.actionnativ.setChecked(True if self.settings.value('pdfViewer', 'PDFjs')=='nativ' else False)     
        
        self.__viewerSwitch()
        self.__updateVisibleViews()
                
    def __resetSettings(self):
        for key, value in self.docHeaderColumnsSettings.items():
            if value['setting']:
                value['setting'].setChecked(self.docHeaderColumnsSettings[key]['default'])
        self.actionNachrichtenkopf.setChecked(True)
        self.actionFavoriten.setChecked(True)
        self.actionLeereSpaltenAusblenden.setChecked(True)  
        self.actionPDF_js.setChecked(True)  
        self.__viewerSwitch()        
        self.__updateSettings()
        
    def __updateVisibleViews(self):
        self.nachrichtenkopf.setVisible(self.actionNachrichtenkopf.isChecked())
        self.favoriten.setVisible(self.actionFavoriten.isChecked())
    
    def __openManual(self):
        manualPath = os.path.join(self.scriptRoot , 'docs', 'openXJV_Benutzerhandbuch.pdf')
        self.__openFileExternal(manualPath, True, True)
    
    def __openFileExternal(self, filename, ignoreWarnings=False, absolutePath=False):
        msgBox=QMessageBox()
        msgBox.setIcon(QMessageBox.Warning)
        msgBox.setWindowTitle("Sicherheitshinweis!")
        msgBox.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        buttonY = msgBox.button(QMessageBox.Yes)
        buttonY.setText('Ja')
        buttonN = msgBox.button(QMessageBox.No)
        buttonN.setText('Nein')
        msgBox.setDefaultButton(QMessageBox.No)

        illegalChars = re.findall(r"[^-A-ZÄÖÜa-zäöüß_0-9\.]", filename)
        if illegalChars and not ignoreWarnings:
            msgBox.setText("Der Dateiname enthält unzulässige Zeichen.\n\nDies kann ein Sicherheitsrisiko bedeuten, falls ausführbare Befehle im Dateinamen versteckt wurden! Es kann sich jedoch auch schlicht um Nachlässigkeit des Absenders handeln.\n\nTrotzdem öffnen?")
            msgBox.exec()
            if msgBox.clickedButton() == buttonY:
                self.__openFileExternal(filename, ignoreWarnings=True)
        
        elif len(filename)>90 and not ignoreWarnings:
            msgBox.setText("Der Dateiname ist länger als 90 Zeichen.n\Dies entspricht nicht den Vorgaben des XJustiz-Stnadards.\n\nTrotzdem öffnen?")
            msgBox.exec()
            if msgBox.clickedButton() == buttonY:
                self.__openFileExternal(filename, ignoreWarnings=True)
          
        else:
            if absolutePath:
                fullPath=filename
            else:
                fullPath = os.path.join(self.basedir, filename)  
            if os.path.exists(fullPath):
                if sys.platform.startswith('linux'):
                    cmd=["xdg-open",  "%s" % fullPath]
                    subprocess.call(cmd) 
                elif sys.platform.lower().startswith('win'):
                    os.startfile(fullPath)
                else:
                    os.popen("open '%s'" % fullPath)
            else: 
                self.statusBar.showMessage('Datei existiert nicht: '+ filename) 

    def __downloadRequested(self, download):
        download.accept()
        QMessageBox.information(self, "Information",
                               "Die Datei wurde im Standard-Download-Ordner gespeichert.")
        
    def __printRequested(self):
        if sys.platform.lower().startswith('win'):
            QMessageBox.information(self, "Information",
                               "Der Ausdruck von PDF-Dateien aus OpenXJV wird unter Windows momentan noch nicht unterstützt.")
        elif not re.findall(r"[^-A-ZÄÖÜa-zäöüß_0-9\.]", self.loadedPDFfilename):
                os.system("lpr '%s'" % self.loadedPDFpath)
                self.statusBar.showMessage('Datei %s wurde an den Standarddrucker gesendet.' % self.loadedPDFfilename) 
        else:
            self.statusBar.showMessage('Druck aufgrund von Sicherheitsbedenken abgebrochen (Unzulässiger Dateiname).')
          
    def __setInstanzenView(self):
        singleValues=[        
            ['abteilung','<b>Abteilung:</b> %s<br>'],
            ['kurzrubrum','<b>Kurzrubrum:</b> %s<br>'],
            ['verfahrensinstanznummer','<b>Verfahrensinstanznummer:</b> %s<br>'],
            ['sachgebiet','<b>Sachgebiet:</b> %s<br>'],
            ['sachgebietszusatz','<b>Sachgebietszusatz:</b> %s<br>']     
        ]
                
        text=''
        if self.akte.grunddaten['verfahrensnummer']:
            text+='<b><i>Verfahrensnummer:</i></b> %s<br>' % self.akte.grunddaten['verfahrensnummer']
            
        keys=list(self.akte.grunddaten['instanzen'].keys())
        for key in keys:
            instanz=self.akte.grunddaten['instanzen'][key]
            hr='________________________________________________________________________________________________<br><br>'
            text+="%s<b>Instanz %s</b><br>%s<b><i>Instanzdaten</i></b><br>" % (hr, key, hr)       
            text+='<b>Behörde:</b> %s<br>' % instanz['auswahl_instanzbehoerde']['name']
            
            if instanz['aktenzeichen']['aktenzeichen.freitext']:
                text+='<b>Aktenzeichen:</b> %s<br>' % instanz['aktenzeichen']['aktenzeichen.freitext']
            
            for value in singleValues:
                if instanz[value[0]]:
                    text+= value[1] % instanz[value[0]]
            
            for gegenstand in instanz['verfahrensgegenstand']:
                setBR=False
                if gegenstand['gegenstand']:
                    text+='<b>Gegenstand:</b> %s' % gegenstand['gegenstand']
                    setBR=True
                if gegenstand['gegenstandswert'].strip():
                   text+=', Streitwert: %s' % (gegenstand['gegenstandswert'])
                   setBR=True
                if gegenstand['auswahl_zeitraumDesVerwaltungsaktes'].strip():
                   text+=', Datum/Zeitraum: %s' % (gegenstand['auswahl_zeitraumDesVerwaltungsaktes'])   
                   setBR=True 
                if setBR:
                    text+='<br>'
            
            text+=self.__telkoTemplate(instanz['telekommunikation'])
            
        self.instanzenText.setHtml(text)

    def __telkoTemplate(self, telekommunikation):
        text=TextObject()
        text.addHeading('Telekommunikationsverbindungen')
        for eintrag in telekommunikation:
                text.addRaw('%s: %s' % (eintrag['telekommunikationsart'],eintrag['verbindung']))
                if eintrag['telekommunikationszusatz']:
                    text.addRaw(" (%s)" % eintrag['telekommunikationszusatz'])
                    text.addRaw('<br>')
        return text.getText()
    
    def __rollenTemplate(self, rollen):
        text=''
        for rolle in rollen:
            if rolle['rollenbezeichnung'] and rolle['rollennummer']:
 
                text+='<b>Rolle'
                if rolle['rollenID']:
                    text+=' in Instanz '
                    delimiter=''
                    for rollenID in rolle['rollenID']:
                        text+='%s%s' % (delimiter, rollenID['ref.instanznummer'])
                        delimiter=', ' 
                    text+=':</b> <u>%s</u><br>' % self.akte.rollenverzeichnis.get(str(rolle['rollennummer']))
                else:
                    if rolle['rollenbezeichnung']:
                        text+=':</b> %s %s<br>' % (rolle['rollenbezeichnung'], rolle['nr'])
                if rolle['naehereBezeichnung']:
                    text+='Nähere Bezeichnung: %s<br>' % rolle['naehereBezeichnung']
                for referenz in rolle['referenz']:
                    text+='Bezug zu: %s<br>' %  self.akte.rollenverzeichnis.get(str(referenz))  
                if rolle['geschaeftszeichen']:
                    text+='Geschäftszeichen: %s<br>' % rolle['geschaeftszeichen']
        return text
             
    def __anschriftTemplate (self, anschriften, heading='Postalische Anschrift'):   
        if not isinstance(anschriften, list):
            anschriften=[anschriften]
        items={
            'erfassungsdatum':'Erfasst am: %s<br>',
            'wohnungsgeber':'Wohnungsgeber: %s<br>'                                  
        }
        text=''
        
        delimiter=''
        for anschrift in anschriften:
            text+=delimiter
            if anschrift['anschriftstyp']:
                text+='<u>%s</u><br>' % anschrift['anschriftstyp']
               
            for key, value in items.items():
                if anschrift[key]:
                    text += value % anschrift[key]
                
            if anschrift['strasse'] or anschrift['hausnummer']:
                text+='%s %s<br>' % (anschrift['strasse'], anschrift['hausnummer'])
            if anschrift['anschriftenzusatz']: 
                delimiter=''
                for zusatz in anschrift['anschriftenzusatz']:
                    text+=delimiter + zusatz
                    delimiter=', '
                text+='<br>'
            if anschrift['postfachnummer']:
                text+='Postfach %s<br>' % anschrift['postfachnummer']
            if anschrift['postleitzahl'] or anschrift['ort']:
                text+='%s %s %s<br>' % (anschrift['postleitzahl'], anschrift['ort'], anschrift['ortsteil'])
            if anschrift['staat']:
                text+='%s<br>' % anschrift['staat']
            if anschrift['staatAlternativ']:
                text+='%s<br>' % anschrift['staatAlternativ']      
            delimiter='<br>'
            
        #if anschriften:
        if text:
            text='<br><b><i>%s</i></b><br>%s' % (heading, text)
        return text

    def __vollerNameTemplate(self, vollerName):
        text=''
        namensbestandteile=[
            'titel',
            'vorname',
            'namensvorsatz',
            'nachname',
            'namenszusatz'
        ]
        
        geburtsnamensbestandteile=[
            'geburtsnamensvorsatz',
            'geburtsname',
        ]
        
        if vollerName['vorname'] or vollerName['nachname']: 
            text+='Voller Name:'
            for bestandteil in namensbestandteile: 
                if vollerName[bestandteil]=='None' or not vollerName[bestandteil]:
                    continue
                elif bestandteil == 'nachname' or bestandteil == 'namensvorsatz':
                    text+=' <u>%s</u>' % vollerName[bestandteil] 
                else:
                    text+=' %s' % vollerName[bestandteil]
            text+='<br>'
        if vollerName['rufname']:    
            text+='Rufname: %s<br>' % vollerName['rufname'] 
            
        if vollerName['geburtsname']:    
            text+='Geburtsname:'
            for bestandteil in geburtsnamensbestandteile:
                if vollerName[bestandteil]=='None' or not vollerName[bestandteil]:
                    continue
                else:
                    text+=' %s' % vollerName[bestandteil]
            text+='<br>'
        
        for weitererName in vollerName['vorname.alt']:
            text+='Weiterer Name: %s<br>' % weitererName
        
        for altvorname in vollerName['vorname.alt']:
            text+='Ehemaliger Vorname: %s<br>' % altvorname    
        
        for altname in vollerName['nachname.alt']:
            text+='Ehemaliger Nachname: %s<br>' % altname    
        return text

    def __kanzleiTemplate(self,beteiligter):
        text='<br><b><u>Kanzlei / Rechtsanwalt</u></b><br>'
        
        if beteiligter['bezeichnung.aktuell']:
            text+='Bezeichnung: %s<br>' % beteiligter['bezeichnung.aktuell']
        
        for alteBezeichnung in beteiligter['bezeichnung.alt']:
            text+='Ehemals: %s<br>' % alteBezeichnung
        
        if beteiligter['kanzleiform']:
            text+='Kanzleiform: %s<br>' % beteiligter['kanzleiform']
            
            if beteiligter['rechtsform']:
                text+='Rechtsform: %s<br>' % beteiligter['rechtsform']
            
        if beteiligter['geschlecht']:
            text+='Geschlecht: %s<br>' % beteiligter['geschlecht']
            
        text+=self.__anschriftTemplate(beteiligter['anschrift'])
        
        text+=self.__telkoTemplate(beteiligter['telekommunikation'])
        
        if beteiligter['umsatzsteuerID']:
            text+='<br><b><i>Steuerdaten</i></b><br>'
            text+='Umsatzsteuer-ID: %s<br>' % beteiligter['umsatzsteuerID']
        
        if beteiligter['raImVerfahren']:
            raDaten=self.__natPersonTemplate(beteiligter['raImVerfahren'])
            if raDaten:
                text+='<blockquote><b><u>Rechtsanwalt im Verfahren</u></b>%s</blockquote>' % raDaten
            
        
        return text
    
    def __orgTemplate(self, beteiligter):
        text='<br><b><u>Organisation / Juristische Person</u></b><br>'
        if beteiligter['bezeichnung.aktuell']:
            text+='Bezeichnung: %s</b><br>' % beteiligter['bezeichnung.aktuell']
        
        for alteBezeichnung in beteiligter['bezeichnung.alt']:
            text+='Ehemals: %s<br>' % alteBezeichnung
            
        if beteiligter['kurzbezeichnung']: 
            text+='Kurzbezeichnung: %s<br>' % beteiligter['kurzbezeichnung']
            
        if beteiligter['geschlecht']:
            text+='Geschlecht: %s<br>' % beteiligter['geschlecht']
        
        if beteiligter['angabenZurRechtsform']:
            text+=self.__rechtsformTemplate(beteiligter['angabenZurRechtsform'])
        
        for sitz in beteiligter['sitz']:
            text+=self.__sitzTemplate(sitz)
                        
        text+=self.__anschriftTemplate(beteiligter['anschrift'])
        text+=self.__telkoTemplate(beteiligter['telekommunikation'])
        
        if beteiligter['registereintragung']:
            text+=self.__registerTemplate(beteiligter['registereintragung'])
        
        if beteiligter['bankverbindung']:
            text+=self.__bankverbindungTemplate(beteiligter['bankverbindung'])
        
        if beteiligter['umsatzsteuerID']:
            text+='<br><b><i>Steuerdaten</i></b><br>'
            text+='Umsatzsteuer-ID: %s<br>' % beteiligter['umsatzsteuerID']
        return text
    
    def __sitzTemplate(self, sitz):
        text=TextObject()
        text.addHeading('Sitz')
        text.addLine('Ort', sitz['ort'])
        text.addLine('Postleitzahl', sitz['postleitzahl'])
        text.addLine('Staat', sitz['staat'])
                    
        return text.getText()
    
    def __rechtsformTemplate (self, rechtsform):
        text=TextObject()
        text.addHeading('Rechtsform')
        text.addLine('Rechtsform', rechtsform['rechtsform'])
        text.addLine('Weitere Bezeichnung', rechtsform['weitereBezeichnung'])
       
        return text.getText()
    
    def __natPersonTemplate(self, beteiligter):              
        text=''
        text+=self.__vollerNameTemplate(beteiligter['vollerName'])
        
        for staatsangehoerigkeit in beteiligter['staatsangehoerigkeit']:
            text+='Staatsangehörigkeit: %s<br>' % staatsangehoerigkeit  
        
        for herkunftsland in beteiligter['herkunftsland']:
            text+='Herkunftsland: %s<br>' % herkunftsland
        
        for sprache in beteiligter['sprache']:
            text+='Sprache: %s<br>' % sprache
        
        if beteiligter['beruf']:
            text+='<br><b><i>Berufliche Daten</i></b><br>'
            for beruf in beteiligter['beruf']:
                text+='Beruf: %s<br>' % beruf
                
        text+=self.__anschriftTemplate(beteiligter['anschrift'])
        text+=self.__telkoTemplate(beteiligter['telekommunikation'])
        
        if beteiligter['zustaendigeInstitution']:
            text+='<br><b><i>Zuständige Institution(en)</i></b><br>'
            for rollennummer in beteiligter['zustaendigeInstitution']:
                text+='%s<br>' % self.akte.rollenverzeichnis.get(str(rollennummer))
        
        if beteiligter['bankverbindung']:
            text+=self.__bankverbindungTemplate(beteiligter['bankverbindung'])
        
        if beteiligter['umsatzsteuerID']:
            text+='<br><b><i>Steuerdaten</i></b><br>'
            text+='Umsatzsteuer-ID: %s<br>' % beteiligter['umsatzsteuerID']
        
        for alias in beteiligter['aliasNatuerlichePerson']:
            text+='<blockquote><b><u>Aliasdaten</u></b>%s</blockquote>' % self.__natPersonTemplate(alias)
        
        if beteiligter['geburt']:
            text+=self.__geburtTemplate(beteiligter['geburt'])  
        
        if beteiligter['tod']:
            text+=self.__todTemplate(beteiligter['tod'])
            
        if beteiligter['geburt']:
            text+=self.__geburtTemplate(beteiligter['geburt'])

        if beteiligter['registereintragungNatuerlichePerson']:
            text+=self.__registerNatPersonTemplate(beteiligter['registereintragungNatuerlichePerson'])
        
        if beteiligter['auswahl_auskunftssperre']:
            text+=self.__sperreTemplate(beteiligter['auswahl_auskunftssperre'])
        
        if text:
            text='<br><b><i>Personendaten</i></b><br>'+text
            
        return text 
   
    def __registerNatPersonTemplate(self, registereintragung):
        text=TextObject()
       
        text.addHeading('Registrierung natürliche Person')

        text.addLine('Firma', registereintragung['verwendeteFirma'])
        text.addLine('Weitere Bezeichnung', registereintragung['angabenZurRechtsform']['weitereBezeichnung'])
        text.addLine('Rechtsform', registereintragung['angabenZurRechtsform']['rechtsform']) 
        
        if registereintragung['registereintragung']:
            text.addRaw(self.__registerTemplate(registereintragung['registereintragung']))
            
        return text.getText()
    
    def __registerTemplate(self, registrierung):
        text=TextObject()
        
        text.addHeading('Registrierungsdaten')
        
        items=(
            ['registernummer','Registernummer'],
            ['reid','REID'],
            ['lei','LEI'],
            ['euid','EUID']             
        )
        
        for item in items:            
            text.addLine(item[1],registrierung[item[0]])

        text.addLine('Registergericht', registrierung['auswahl_registerbehoerde']['inlaendischesRegistergericht']['gericht'])
        text.addLine('Registerart', registrierung['auswahl_registerbehoerde']['inlaendischesRegistergericht']['registerart'])  
        text.addLine('Registerbehörde', registrierung['auswahl_registerbehoerde']['sonstigeRegisterbehoerde']['registerbehoerde'])
        text.addLine('Registerbezeichnung', registrierung['auswahl_registerbehoerde']['sonstigeRegisterbehoerde']['registerbezeichnung'])
                    
        return text.getText()
    
    def __sperreTemplate(self, sperre):
        text=TextObject()
        
        text.addHeading('Auskunftssperrdaten')
        
        if sperre['auskunftssperre.vorhanden'].lower()=='true':
            text.addRaw('Auskunftssperre vorhanden: ja<br>')
        elif sperre['auskunftssperre.vorhanden'].lower()=='false':
            text.addRaw('Auskunftssperre vorhanden: nein<br>')
        
        items=[
            'grundlage',
            'umfang',
            'sperrstufe'
        ]
        
        for item in items:
            text.addLine(item.capitalize(), sperre['auskunftssperre.details'][item])
        
        return text.getText()
    
    def __geburtTemplate(self, geburt):
        text=TextObject()
        text.addHeading('Geburtsdaten')
        text.addLine('Geburtsdatum', geburt['geburtsdatum'])
        if geburt['geburtsdatum.unbekannt'].lower() =='true': 
            text.addRaw('Geburtsdatum: unbekannt<br>')
        text.addLine('Geburtsort', geburt['geburtsort']['ort'])
        text.addLine('Staat des Geburtsortes', geburt['geburtsort']['staat'])
        text.addLine('Geburtsname der Mutter', geburt['geburtsname.mutter'])    
        
        items=[
            ['nachname.vater','Nachname des Vaters'],
            ['vorname.vater','Vorname des Vaters'],
            ['nachname.mutter','Nachname der Mutter'],
            ['vorname.mutter','Vorname der Mutter']
        ]
        
        for item in items:
            if geburt['name.eltern'][item[0]]:
                for name in geburt['name.eltern'][item[0]]:    
                    text.addLine(item[1], name)
                                                 
        return text.getText()   
    
    def __todTemplate(self, tod):
        text=TextObject()
        text.addHeading('Sterbedaten')
        items=[
            ['sterbedatum','Sterbedatum'],
            ['sterbestandesamtBehoerdennummer','Behördennummer des Standesamts'],
            ['sterbestandesamtName','Names des Standesamts'],
            ['sterberegisternummer','Sterberegisternr.'],
            ['eintragungsdatum','Eintragungsdatum'],
            ['sterberegisterart', 'Sterberegisterart'],
            ['todErklaert', 'Tod erklärt']
        ]

        sterbezeitraum=''
        if tod['sterbedatumZeitraum']['beginn']:
            sterbezeitraum = tod['sterbedatumZeitraum']['beginn']
        if tod['sterbedatumZeitraum']['ende']:
            sterbezeitraum += ' - %s' % tod['sterbedatumZeitraum']['ende']
       
        text.addLine('Sterbezeitraum' , sterbezeitraum)
       
        for item in items:
            
            itemValue = tod[item[0]]
            
            if item[0]=='todErklaert' and itemValue.lower()=='true':
                itemValue='ja'
            elif item[0]=='todErklaertt' and itemValue.lower()=='false':
                itemValue='nein'    
            
            text.addLine(item[1], itemValue)
        
        if tod['sterbeort']: 
            text.addRaw(self.__anschriftTemplate ([tod['sterbeort']],'Sterbeort'))
               
        return text.getText()            
    
    def __bankverbindungTemplate(self, bankverbindungen):
        text=TextObject()
        text.addHeading('Bankverbindungsdaten')
        items=[
            ['bankverbindungsnummer','Bankverbindungsnummer'],
            ['iban','IBAN'],
            ['bic','BIC'],
            ['bank','Bank'],
            ['kontoinhaber','Kontoinhaber'],
            ['sepa-mandat', 'Sepa-Mandat'],
            ['verwendungszweck', 'Verwendungszweck']
        ]
        delimiter=''
        for bankverbindung in bankverbindungen:
            for item in items:
                text.addRaw(delimiter)
                itemValue = bankverbindung[item[0]]
                
                if item[0]=='sepa-mandat' and itemValue.lower()=='true':
                    itemValue='Erteilt'
                elif item[0]=='sepa-mandat' and itemValue.lower()=='false':
                    itemValue='Nicht erteilt'    
                
                text.addLine(item[1], itemValue)
                    
            delimiter='<br>'
                  
        return text.getText()                      
                  
    def __setBeteiligteView(self):
        text=TextObject()
        for beteiligung in self.akte.grunddaten['beteiligung']:
            text.addLine('<b>Beteiligtennummer</b>', beteiligung['beteiligtennummer'])
            
            if beteiligung['rolle']:
                text.addRaw(self.__rollenTemplate(beteiligung['rolle']))
                
            beteiligter=beteiligung['beteiligter']
                   
            if beteiligter['type']=='GDS.Organisation':
                text.addRaw(self.__orgTemplate(beteiligter))
            if beteiligter['type']=='GDS.RA.Kanzlei':
                text.addRaw(self.__kanzleiTemplate(beteiligter))
            if beteiligter['type']=='GDS.NatuerlichePerson':  
                text.addRaw(self.__natPersonTemplate(beteiligter))
            text.addRaw('__________________________________________________________________________________<br><br>')
           
        self.beteiligteText.setHtml(text.getText())
        
    def __terminTemplate(self, termin):
        text=TextObject()
        text.addHeading('Terminsdetails')
        hr='________________________________________________________________________________________________<br><br>'
        if termin['hauptterminsdatum']:
            if termin['auswahl_hauptterminszeit']['hauptterminsuhrzeit']:
                zeit = "%s Uhr" % termin['auswahl_hauptterminszeit']['hauptterminsuhrzeit']
            else:
                zeit = termin['auswahl_hauptterminszeit']['hauptterminszeit'] 
            text.addRaw('Fortsetzungstermin des Haupttermins vom %s, %s<br>' % (termin['hauptterminsdatum'], zeit))   
            if termin['hauptterminsID']:
                text.addLine('Haupttermins-ID', termin['hauptterminsID'])
            text.addRaw(hr)
        
        text.addLine('Termins-ID', termin['terminsID'])
            
        if termin['terminsart']:
            text.addRaw('<b>Art des Termins: %s</b><br>' % termin['terminsart'])
                
        text.addLine('Spruchkörper', termin['spruchkoerper'])
                
        if termin['oeffentlich'].lower()=='true':
            text.addRaw("Es handelt sich um einen öffentlichen Termin.<br>") 
        elif termin['oeffentlich'].lower()=='false':
            text.addRaw("Dieser Termin ist nicht öffentlich.<br>")   
        
        datum=termin['terminszeit']['terminsdatum']
        if termin['terminszeit']['auswahl_terminszeit']['terminsuhrzeit']:
            zeit = "%s Uhr" % termin['terminszeit']['auswahl_terminszeit']['terminsuhrzeit']
        else:
            zeit = termin['terminszeit']['auswahl_terminszeit']['terminszeitangabe'] 
        text.addRaw('<b>Termin: %s, %s</b><br>' % (datum,zeit))
        
        if termin['terminszeit']['terminsdauer']:
            text.addLine('Angesetzte Dauer', '%s h' % termin['terminszeit']['terminsdauer'])
        
        gerichtsort=TextObject()
        if termin['auswahl_terminsort']['gerichtsort']['anschrift']:
            gerichtsort.addRaw(self.__anschriftTemplate(termin['auswahl_terminsort']['gerichtsort']['anschrift'], heading='Terminsort'))
        gerichtsort.addLine('Gebäude', termin['auswahl_terminsort']['gerichtsort']['gebaeude'])
        gerichtsort.addLine('Stockwerk', termin['auswahl_terminsort']['gerichtsort']['stockwerk'])
        gerichtsort.addLine('Raum', termin['auswahl_terminsort']['gerichtsort']['raum'])
        if gerichtsort.getText():
            text.addRaw(gerichtsort.getText())
        
        lokaltermin=TextObject()
        if termin['auswahl_terminsort']['lokaltermin']['anschrift']:
            lokaltermin.addRaw(self.__anschriftTemplate(termin['auswahl_terminsort']['lokaltermin']['anschrift'], heading='Terminsort (Lokaltermin)'))
        lokaltermin.addLine('Beschreibung', termin['auswahl_terminsort']['lokaltermin']['beschreibung'])
        if lokaltermin.getText():
            text.addRaw(lokaltermin.getText())
        
        geladene=TextObject()
        for teilnehmer in termin['teilnehmer']:
            geladene.addRaw(self.__geladenTemplate(teilnehmer))
        geladene.addHeading('Geladene:<br>')
        if geladene.getText():
            text.addRaw(geladene.getText())
            
        return text.getText() 
    
    def __geladenTemplate(self, teilnehmer):
        ladungszusatz=teilnehmer['ladungszusatz']    
        geladener=self.akte.rollenverzeichnis.get(str(teilnehmer['ref.rollennummer']))      
        datum=teilnehmer['ladungszeit']['ladungsdatum'] 
        dauer=teilnehmer['ladungszeit']['ladungsdauer']        
        ladungsuhrzeit=teilnehmer['ladungszeit']['auswahl_ladungszeit']['ladungsuhrzeit']   
        zeitangabeFreitext=teilnehmer['ladungszeit']['auswahl_ladungszeit']['ladungszeitangabe'] 
        
        text=TextObject()
        text.addRaw('<b>%s</b>' % geladener)
        if datum:
            text.addRaw(' am %s' % datum)
        if ladungsuhrzeit:
            text.addRaw(' um %s Uhr' % ladungsuhrzeit)
        if zeitangabeFreitext:
            text.addRaw(', %s' % zeitangabeFreitext)   
        if dauer:
            text.addRaw(' für %s h' % dauer)    
        text.addRaw('<br>')
        text.addLine('Ladungszusatz', ladungszusatz)
        text.addRaw('<br>')
        return text.getText()
    
        
    def __setTerminDetailView(self, val):
        text=''
        uuid=self.termineTableView.item( val.row(), 0).text()
        for termin in self.akte.termine:
            if termin['uuid']==uuid:
                text+=self.__terminTemplate(termin)
        
        self.terminDetailView.setHtml(text) 
                                        
if __name__ == "__main__":
    app = QApplication([])
    app.setStyle('Fusion')

    #Parse sys.argv
    file=None
    ziplist=None
    if len(sys.argv)==2 and sys.argv[1].lower().endswith('xml'):
        file=sys.argv[1]
        
    elif len(sys.argv)>=2:
        ziplist=[]
        for file in sys.argv[1:]:
            ziplist.append(file)
            
    widget = UI(file=file, ziplist=ziplist)
    widget.show()
    sys.exit(app.exec_())
