#!/usr/bin/env python3
# coding: utf-8
'''
    openXJV.py - a viewer for XJustiz-Data
    Copyright (C) 2022 - 2024 Björn Seipel

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

#on ubuntu package sudo apt install libxcb-cursor0 in case of xcb-error

import os
import sys
import re
import urllib.request
import subprocess
import platform
import darkdetect
import multiprocessing
from threading import Thread
from shutil import copyfile
from pathlib import Path
from zipfile import ZipFile
from tempfile import TemporaryDirectory
from itertools import count
from PIL import (
    Image
)
from PIL.ImageQt import ImageQt
from PyQt6.QtCore import (
    QT_VERSION_STR, 
    QSettings, 
    QCoreApplication, 
    QUrl, 
    Qt, 
    QSize, 
    QRect, 
    QLibraryInfo,
    QObject, 
    QThread, 
    pyqtSignal,
    QEvent
) 
from PyQt6 import uic, QtPrintSupport 
from PyQt6.QtPrintSupport import (
    QPrinter, 
    QPrintDialog
)
from PyQt6.QtGui import (
    QStandardItemModel, 
    QStandardItem, 
    QCursor,
    QIcon,
    QFont, 
    QColor,
    QPalette, 
    QPainter, 
    QFontDatabase,
    QDesktopServices,
    QPainter
)
from PyQt6.QtWidgets import (
 
    QToolTip,
    QHeaderView,
    QDialog,
    QFileDialog,
    QApplication,
    QTableWidgetItem,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QComboBox,
    QSpinBox,
    QLabel,
    QPushButton,
    QFormLayout
)
from PyQt6.QtWebEngineWidgets import QWebEngineView 
from PyQt6.QtWebEngineCore import QWebEngineSettings
from appdirs import AppDirs


from helperScripts import parser240, parser321, parser331, parser341, parser351

import pypdfium2 as pdfium

global VERSION 
VERSION = '0.6.4'

class StandardItem(QStandardItem):
    def __init__(self, txt='', id='root', font_size=15, set_bold=False, color=QColor(0, 0, 0)):
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
        '''Fügt eine Zeile Text hinzu, sofern beide Textwerte nicht None sind. Der Trenner wird in self.delimiter ferstgelegt.'''
        if value1 and value2:
            self.text+='%s%s%s%s' % (str(value1), self.delimiter, str(value2), self.newline)

    def addRaw(self, text='', prepend=False):  
        '''Fügt dem Text unveränderten Rohtext hinzu- "prepend=True" fügt den Text am Textanfang ein'''
        if prepend:
            self.text=str(text) + self.text
        else:
            self.text+=str(text)

    def addHeading(self, headline, ignoreEmptyText=False):
        '''Fügt dem Text eine Überschrift hinzu.'''
        self.headline='<br><b><i>' + str(headline)+ '</b></i>'+self.newline
        self.ignoreEmptyText=bool(ignoreEmptyText)

    def getText(self):
        '''Gibt den Text des Objektes zurück. Sofern addHeading ohne ignoreEmptyText=True aufgerufen wurde, wird auch bei gesetzter Überschrift ein leerer String zurückgegeben, sofern der eigentliche Text leer ist.'''
        if self.ignoreEmptyText:
            return self.headline + self.text
        elif self.text:
            return self.headline + self.text
        else:
            return ''

    def update_range_to(self, value):
        self.range_to.setMinimum(value)

    def update_range_from(self, value):
        self.range_from.setMaximum(value)

class printPdfWorker(QObject):
    '''Worker class for long running PDF print task'''
    finished = pyqtSignal()
    progress = pyqtSignal(int)

    def __init__(self, pdf=None, printer=None, parent=None):
        super().__init__(parent)
        if pdf == None:
            raise AttributeError('pdf (Type:str, Path or pyFPDF-Object) needs to be passed to printWorker')
        
        if isinstance(pdf, str) or isinstance(pdf, Path) or not os.path.exists(pdf):
            self.pdf_file = Path(pdf)            
        else:
            raise TypeError('pdf not of Type str, Path or file does not exist')    
        self._printer=printer
        self.painter=QPainter(printer)
                                         
    def run(self):
        """Long-running print task."""    
           
        rect = self.painter.viewport()

        pdf = pdfium.PdfDocument(self.pdf_file)
        n_pages = len(pdf)  
        printRange=[]
        
        fromPage = self._printer.fromPage()
        toPage = self._printer.toPage()  
        printRange = range(n_pages) if fromPage == 0 else range(fromPage-1, toPage)  
        
        page_indices = [i for i in printRange]  
        
        renderer = pdf.render(
            pdfium.PdfBitmap.to_pil,
            page_indices = page_indices,
            scale = 200/72,  # 200dpi resolution
        )
        
        for i, pil_image, pageNumber in zip(page_indices, renderer, count(1)):
            
            if pageNumber > 1:
                self._printer.newPage()

            pilWidth, pilHeight = pil_image.size
            imageRatio = pilHeight/pilWidth
            viewportRatio= rect.height()/rect.width()   
            
            # Rotate image if orientation is not the same as print format orientation
            if (viewportRatio < 1 and imageRatio > 1) or (viewportRatio > 1 and imageRatio < 1): 
                pil_image = pil_image.transpose(Image.ROTATE_90)
                pilWidth, pilHeight = pil_image.size  
                imageRatio = pilHeight/pilWidth
  
            # Adjust drawing area to available viewport 
            if viewportRatio > imageRatio:
                y=int(rect.width()/(pilWidth/pilHeight))                   
                printArea=QRect(0,0,rect.width(),y)
            else:
                x = int(pilWidth/pilHeight*rect.height())
                printArea=QRect(0,0,x,rect.height())
            
            image = ImageQt(pil_image)    

            # Print image                   
            self.painter.drawImage(printArea, image)
            firstPage=False
            self.progress.emit(int(pageNumber*100/len(page_indices)))
        
        # Cleanup        
        pdf.close()
        self.painter.end()
        self.finished.emit()

class UI(QMainWindow):
    def __init__(self, file=None, ziplist=None, app=None):
        super(UI, self).__init__() 
        if os.environ.get('USERDOMAIN')=='DGBRS': 
            self.supportMail="servicedesk@dgbrechtsschutz.de"
        else:
            self.supportMail="support@digidigital.de" 
        self.app=app

        self.tempDir=TemporaryDirectory()
        self.tempfile=''
        # Needed for pyinstaller onefile...
        try:
            self.scriptRoot = sys._MEIPASS
        except Exception:
            self.scriptRoot = os.path.dirname(os.path.realpath(__file__))
        
        if sys.platform.lower().startswith('win'):
            windowIcon=QIcon(os.path.join(self.scriptRoot, 'icons', 'openxjv_desktop.ico'))
        else:
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
        
        self.lastExceptionString=''

        self.dirs = AppDirs("OpenXJV", "digidigital", version="0.1")
        os.makedirs(self.dirs.user_data_dir, exist_ok=True) 
        
        #Don't use Path.home() directly in case we are in a snap package
        self.homedir=os.environ.get('SNAP_REAL_HOME', Path.home())
        
        ###Load fonts###
        fontDir = self.scriptRoot + '/fonts/'
        
        fontFiles=[
            "materialicons/MaterialIcons-Regular.ttf",
            "ubuntu-font-family-0.83/Ubuntu-L.ttf",
            "ubuntu-font-family-0.83/Ubuntu-R.ttf"
        ] 

        for font in fontFiles:          
            QFontDatabase.addApplicationFont(fontDir + font) 
        
        # Load the .ui file
        uic.loadUi(self.scriptRoot + '/ui/openxjv.ui', self) 

        # Set Fonts
        self.buttonFont=QFont('Material Icons')
        self.buttonFont.setWeight(QFont.Weight.Thin.value)
        self.iconFont=QFont('Material Icons')
        self.iconFont.setWeight(QFont.Weight.Thin.value)
        self.appFont=QFont('Ubuntu')
        self.__setFontsizes()
       
        self.setWindowTitle('openXJV %s' % VERSION)
        
        #Hide "New version" icon
        self.newVersionIndicator=self.toolBar.actions()[11]
        self.newVersionIndicator.setVisible(False)
        
        ###Prepare settings###
        self.settings = QSettings('openXJV','digidigital')

        self.browser.settings().setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled,True)
        self.browser.settings().setAttribute(QWebEngineSettings.WebAttribute.ErrorPageEnabled,False)
        self.browser.settings().setAttribute(QWebEngineSettings.WebAttribute.NavigateOnDropEnabled,False)
        
        ###set toolbarButtonwidth###        
        for child in self.toolBar.children():
            if child.__class__.__name__ == 'QToolButton':
                child.setFixedWidth(25)
        
        #Adjust table header style         
        self.docTableView.horizontalHeader().setHighlightSections(False)
        self.termineTableView.horizontalHeader().setHighlightSections(False)  
        
        ###initial print lock state####
        self.printLock=False
        
        ###set paths to PDF viewers###
        if sys.platform.lower().startswith('win'):
            urlPath = self.scriptRoot.replace("\\","/")
            winslash='/'
            pdfjsVariant="file://%s%s/html/pdfjs/web/viewer.html?file=" % (winslash, urlPath)  
        else:
            urlPath = self.scriptRoot
            winslash=''
            pdfjsVariant= "file://%s%s/html/pdfjs/web/viewer.html?file=" % (winslash, urlPath)    
        self.viewerPaths={
            "PDFjs":pdfjsVariant,   
            "chromium":"file://%s" % winslash, 
        }            
        
        ###columns/order to display in document view###
        self.docTableAttributes = [
            'nummerImUebergeordnetenContainer',
            'nurMetadaten', 
            'datumDesSchreibens',
            'erstellungszeitpunkt',
            'posteingangsdatum',
            'veraktungsdatum',
            'scanDatum',
            'ersetzenderScan',
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
            'ersteSeitennummer',
            'letzteSeitennummer', 
            'dateiname',
            
        ]

        self.docHeaderColumnsSettings={
            #key                              headertext                              action for menu-item /config                     default visibility width of column (no real effect - set to auto width if not None)                 
            ''                               :{'headertext':''                      ,'setting':None                                  ,'default':True    ,'width':10},
            ''                               :{'headertext':''                      ,'setting':None                                  ,'default':True    ,'width':10},
            'nummerImUebergeordnetenContainer':{'headertext':'#'                      ,'setting':None                                  ,'default':True    ,'width':45},
            'ersteSeitennummer'               :{'headertext':'Erste\nSeitennr.'       ,'setting':self.actionErste_SnrColumn            ,'default':False   ,'width':45},
            'letzteSeitennummer'              :{'headertext':'Letzte\nSeitennr.'      ,'setting':self.actionLetzte_SnrColumn           ,'default':False   ,'width':45},            
            'dateiname'                       :{'headertext':'Dateiname'              ,'setting':None                                  ,'default':True    ,'width':None},
            'anzeigename'                     :{'headertext':'Anzeige-\nname'         ,'setting':None                                  ,'default':True    ,'width':200},
            'nurMetadaten'                    :{'headertext':'Nur\nMetadaten'         ,'setting':self.actionNur_MetadatenColumn        ,'default':False   ,'width':45},
            'datumDesSchreibens'              :{'headertext':'Datum'                  ,'setting':self.actionDatumColumn                ,'default':True    ,'width':95},
            'erstellungszeitpunkt'            :{'headertext':'Erstellungs-\nzeitpunkt','setting':self.actionEingangsdatumColumn        ,'default':True    ,'width':195},
            'posteingangsdatum'               :{'headertext':'Eingang'                ,'setting':self.actionErstellungszeitpunktColumn ,'default':False   ,'width':195},
            'veraktungsdatum'                 :{'headertext':'Veraktung'              ,'setting':self.actionVeraktungsdatumColumn      ,'default':True    ,'width':95},
            'scanDatum'                       :{'headertext':'Scandatum'              ,'setting':self.actionScandatumColumn            ,'default':False   ,'width':95},
            'ersetzenderScan'                 :{'headertext':'Ersetzender\nScan'      ,'setting':self.actionErsetzenderScanColumn      ,'default':False   ,'width':40},
            'dokumententyp'                   :{'headertext':'Typ'                    ,'setting':self.actionDokumententypColumn        ,'default':True    ,'width':None},
            'dokumentklasse'                  :{'headertext':'Klasse'                 ,'setting':self.actionDokumentenklasseColumn     ,'default':True    ,'width':200},
            'bestandteil'                     :{'headertext':'Bestandteil'            ,'setting':self.actionBestandteilColumn          ,'default':True    ,'width':None},
            'versionsnummer'                  :{'headertext':'Version-\nnr.'          ,'setting':self.actionVersionsnummerColumn       ,'default':False   ,'width':None},
            'dateiname.bezugsdatei'           :{'headertext':'Bezug\nzu'              ,'setting':self.actionBezugsdateinameColumn      ,'default':False   ,'width':None},
            'ruecksendungEEB.erforderlich'    :{'headertext':'EEB'                    ,'setting':self.actionEEB_HinweisColumn          ,'default':True    ,'width':45},
            'zustellung41StPO'                :{'headertext':'§41\nStPO'              ,'setting':self.actionZustellung_StPO_41Column   ,'default':False   ,'width':40},
            'akteneinsicht'                   :{'headertext':'Akten-\neinsicht'       ,'setting':self.actionAkteneinsichtColumn        ,'default':False   ,'width':60},
            'absenderAnzeigename'             :{'headertext':'Absender'               ,'setting':self.actionAbsenderColumn             ,'default':False   ,'width':None},
            'adressatAnzeigename'             :{'headertext':'Adressat'               ,'setting':self.actionAdressatColumn             ,'default':False   ,'width':None},
            'justizkostenrelevanz'            :{'headertext':'Kosten-\nrele-\nvanz'   ,'setting':self.actionJustizkostenrelevanzColumn ,'default':False   ,'width':58},
            'fremdesGeschaeftszeichen'        :{'headertext':'fr. Gz.'                ,'setting':self.actionfrGeschaeftszeichenColumn  ,'default':False   ,'width':None},
            'vertraulichkeitsstufe'           :{'headertext':'Vertraulich'            ,'setting':self.actionVertraulichkeitsstufeColumn,'default':False   ,'width':None},           
        }
         
        self.isDocColumnEmpty={}
        
        ####initial settings####
        self.inhaltView.setHeaderHidden(True)
        
        self.plusFilter.setText(self.settings.value("plusFilter", ''))
        self.minusFilter.setText(self.settings.value("minusFilter", ''))
        self.__readSettings()
          
        #better readability of inactive items on windows 10
        if sys.platform.lower().startswith('win'):
            xjvPalette = self.palette()
            xjvPalette.setColor(QPalette.ColorRole.Highlight, QColor(150, 150, 255, 255))
            xjvPalette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255, 255))
            self.setPalette(xjvPalette)
        
        #fix issue with palette used by gnome / ubuntu - set inactive colors to active colors
        if sys.platform.lower() == 'linux': 
            self.__fixGnomeDarkPalette() 
             
        #Load empty viewer
        self.__loadEmptyViewer()        
            
        #########self.favoriteniew##########
        self.favorites = set()

        #########self.favoriteniew##########
        self.downloadFolder = ''
        
        #######load browsing history #####
       
        self.browsingHistory = self.__loadHistory()
       
        #########load initial files##########
        lastfile=self.settings.value("lastFile", None)
        if file and file.lower().endswith('xml'):
            self.getFile(file)
        elif ziplist:
            for zip in ziplist:
                if not zip.lower().endswith('zip'):
                    sys.exit("Fehler: Die übergebene Liste enthält nicht ausschließlich ZIP-Dateien.")
            self.getZipFiles(files=ziplist)    
        elif lastfile:
            self.getFile(lastfile)


        ####connections####
        self.actionOeffnen.triggered.connect(lambda:self.getFile())
        self.actionHistorieVor.triggered.connect(lambda:self.__fileHistory('forward'))
        self.actionHistorieZurück.triggered.connect(lambda:self.__fileHistory('backward'))
        self.actionZIP_ArchiveOeffnen.triggered.connect(self.__selectZipFiles)
        self.actionUeberOpenXJV.triggered.connect(self.__displayInfo)
        self.actionAnleitung.triggered.connect(self.__openManual)
        self.actionSupport_anfragen.triggered.connect(self.__supportAnfragen)       
        self.actionAktenverzeichnis_festlegen.triggered.connect(lambda:self.__chooseStartFolder())
        self.inhaltView.clicked.connect(self.__updateSelectedInhalt)
        # Connection in __setInhaltView: self.inhaltView.selectionModel().selectionChanged.connect(self.__updateSelectedInhalt)
        self.docTableView.doubleClicked.connect(self.__dClickDocTableAction)
        self.docTableView.selectionModel().selectionChanged.connect(self.__browseDocTableAction)
        self.termineTableView.clicked.connect(self.__setTerminDetailView)
        self.plusFilter.textChanged.connect(self.__filtersTriggered)
        self.minusFilter.textChanged.connect(self.__filtersTriggered)
        self.filterLeeren.clicked.connect(self.__resetFilters)
        self.filterMagic.clicked.connect(self.__magicFilters)
        self.favoritenView.doubleClicked.connect(self.__getDClickFavoriteViewAction)
        self.favoritenView.selectionModel().selectionChanged.connect(self.__getFavoriteViewAction)
        self.deleteFavoriteButton.clicked.connect(self.__removeFavorite)
        self.saveFavouritesButton.clicked.connect(self.__exportToFolderAction)
        self.exportFavoritesButton.clicked.connect(self.__exportZipAction)
        self.actionZuruecksetzen.triggered.connect(self.__resetSettings)   
        self.actionNachrichtenkopf.triggered.connect(self.__updateSettings)
        self.actionAnwendungshinweise.triggered.connect(self.__updateSettings)
        self.actionFavoriten.triggered.connect(self.__updateSettings)
        self.actionMetadaten.triggered.connect(self.__updateSettings)
        self.actionNotizen.triggered.connect(self.__updateSettings)
        self.actionLeereSpaltenAusblenden.triggered.connect(self.__updateSettings)
        self.actionOnlineAufUpdatesPruefen.triggered.connect(self.__updateSettings)
        self.actionnativ.triggered.connect(self.__viewerSwitch)
        self.actionPDF_js.triggered.connect(self.__viewerSwitch)
        self.actionChromium.triggered.connect(self.__viewerSwitch)
        self.actionAlleSpaltenMarkieren.triggered.connect(self.__checkAllColumns)
        self.browser.page().profile().downloadRequested.connect(self.__downloadRequested)
        self.browser.page().printRequested.connect(self.__printRequested)
        self.actionNeueVersion.triggered.connect(lambda triggered: QDesktopServices.openUrl(QUrl("https://openxjv.de")))
        self.actionGrosse_Schrift.triggered.connect(self.__updateSettings)
        for columnSetting in self.docHeaderColumnsSettings.values():
            if columnSetting['setting']:
                columnSetting['setting'].triggered.connect(self.__updateSettings)
        
        # Workaround für sich nicht aktualisierenden Tabelleninhalt unter Fedora 35 & Ubuntu 22.04 -> Wayland ???
        self.docTableView.horizontalHeader().sectionClicked.connect(self.docTableView.viewport().update)       
        
        # Defaultgröße setzen
        screen_resolution = app.instance().screens()[0].size()
        self.resize(int(screen_resolution.width()/1.5),int(screen_resolution.height()/1.5))
        
        #Check for updates
        if self.actionOnlineAufUpdatesPruefen.isChecked():
            self.__checkForUpdates(updateIndicator=self.newVersionIndicator)
    
    def __fixGnomeDarkPalette(self):
        xjvPalette = self.palette()
        for role in QPalette.ColorRole:
            if not role.name in ('NColorRoles', 'ToolTipBase', 'ToolTipText'):
                xjvPalette.setColor(QPalette.ColorGroup.Inactive, role, xjvPalette.color(QPalette.ColorGroup.Active, role))
            xjvPalette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipText,  QColor(0, 0, 0, 255))          
        self.setPalette(xjvPalette)                
        QToolTip.setPalette(xjvPalette)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.PaletteChange:  
            #workaround for gnome palette / ubuntu
            if sys.platform.lower() == 'linux':
                self.__fixGnomeDarkPalette()    
               
        return super(UI, self).changeEvent(event)
    
    def cleanUp(self):
        self.__saveNotes() 
        self.settings.sync()
    
    def __loadEmptyViewer(self):
        urlPath = self.scriptRoot.replace("\\","/")

        winslash = '/' if sys.platform.lower().startswith('win') else ''    
            
        blankPage="file://%s%s/html/blank/blank.html" % (winslash, urlPath)
        
        self.url=blankPage 

        if darkdetect.isDark():
            self.url+='?darkmode=True'
        
        self.browser.setUrl(QUrl.fromUserInput(self.url))
  
    def __displayInfo(self):
        QMessageBox.information(self, "Information",
        "openXJV " + VERSION + "\n"
        "Lizenz: GPL v3\n"
        "(c) 2022 - 2023 Björn Seipel\nKontakt: " + self.supportMail + "\nWebsite: https://openXJV.de\n\n" 
        "Die Anwendung nutzt folgende Komponenten:\n"
        "Qt6 - LGPLv3\n"
        "PyQT6 - GNU GPL v3\n"
        "appdirs - MIT License\n"
        "lxml - BSD License\n"
        "PDF.js - Apache 2.0 License\n"
        "Ubuntu Font - UBUNTU FONT LICENCE Version 1.0\n"
        "Material Icons Font - Apache 2.0 License\n"
        "pyinstaller - GPLv2 or later\n"
        "Pillow - The open source HPND License\n"
        "darkdetect - BSD license\n"
        "pypdfium2 - Apace 2.0 / BSD 3 Clause\n"
        "python 3.x - PSF License\n\n"
        "Lizenztexte und Quellcode-Links können dem Benutzerhandbuch entnommen werden."
        )
    
    def __supportAnfragen(self):
        mailbody="\n\n------ Ihre Anfrage bitte oberhalb dieser Linie einfügen ------\n\nEinstellungen\n"
        
        for key in self.settings.allKeys():
            if key not in ['history', 'lastFile', 'defaultFolder']:  
                mailbody+="%s - %s\n" % (str(key),str(self.settings.value(key))) 
        
        if len(self.lastExceptionString)>0:
            mailbody+='\n\nLetzte Fehlermeldung\n'+self.lastExceptionString
        
        QDesktopServices.openUrl(QUrl("mailto:%s?subject=Supportanfrage zu openXJV %s unter %s&body=%s" % (self.supportMail, VERSION, platform.platform() ,str(mailbody)), QUrl.ParsingMode.TolerantMode ))
    
    def __updateSelectedInhalt(self):
        val = self.inhaltView.currentIndex() 
        akte = self.akte 
    
        aktenID=val.siblingAtColumn(val.column()+1).data()
        self.__setMetadata(akte, aktenID)
        self.__setDocumentTable(aktenID)
        if self.actionAnwendungshinweise.isChecked() and self.docTableView.rowCount() == 0: 
                self.__informIfNoDocsVisible()
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
        '''Fügt dem -Filter Dateiendungen bekannter technsicher Dokumente hinzu'''
        filterItems=self.minusFilter.text().split()
        for fileextension in [".pks",  ".p7s", ".xml", ".pkcs7"]: 
            if fileextension not in filterItems:
                self.minusFilter.setText(self.minusFilter.text() + ' ' + fileextension)
        self.__filtersTriggered()
        
    def __resetFilters(self):
        '''Leert die Filter-Felder''' 
        self.plusFilter.setText('')
        self.minusFilter.setText('')
        self.__filtersTriggered()
                
    def __filterTableRows (self, tableObj, plusFilterStr, minusFilterStr):
        rows=set()
        if plusFilterStr.replace(" ", ""):
            for filter in plusFilterStr.split():
                for hit in  tableObj.findItems(filter, Qt.MatchFlag.MatchContains):
                    rows.add(hit.row())
        else:            
            for row in range(self.docTableView.rowCount()):
                rows.add(row)
                    
        for filter in minusFilterStr.split():
            for hit in  tableObj.findItems(filter, Qt.MatchFlag.MatchContains):
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
            self.termineTableView.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.termineTableView.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
           
                                              
            columnCount=0
            for item in self.terminTableColumnsHeader:
                headerItem=self.__tableItem(item, self.appFont)
                headerItem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.termineTableView.setHorizontalHeaderItem(columnCount, headerItem)
                columnCount+=1
            #add rows
            rowNo=0    
            
            for termin in termine:
                
                tempItem=self.__tableItem(termin['uuid'], self.appFont)
                self.termineTableView.setItem(rowNo, 0, tempItem)    
                
                datum=zeit=termin['terminszeit']['terminsdatum']
                tempItem=self.__tableItem(datum, self.appFont)
                tempItem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.termineTableView.setItem(rowNo, 1, tempItem)
                
                zeit=termin['terminszeit']['auswahl_terminszeit']['terminsuhrzeit'] + termin['terminszeit']['auswahl_terminszeit']['terminszeitangabe']
                tempItem=self.__tableItem(zeit, self.appFont)
                tempItem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.termineTableView.setItem(rowNo, 2, tempItem)
                
                oeffentlich=self.__replaceTrueFalse(termin['oeffentlich'])
                tempItem=self.__tableItem(oeffentlich, self.appFont)
                tempItem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.termineTableView.setItem(rowNo, 3, tempItem)
                
                if termin.get('hauptterminsdatum') or termin.get('terminskategorie')=='Fortsetzungstermin':
                    terminTyp='Fortsetzung'
                elif termin.get('terminskategorie')=='Umladung':
                    terminTyp='Umladung'
                else:
                    terminTyp='Haupttermin'
                tempItem=self.__tableItem(terminTyp, self.appFont)
                tempItem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.termineTableView.setItem(rowNo, 4, tempItem)
                
                terminsart=termin['terminsart']
                tempItem=self.__tableItem(terminsart, self.appFont)
                tempItem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.termineTableView.setItem(rowNo, 5, tempItem)
                
                spruchkoerper=termin['spruchkoerper']
                tempItem=self.__tableItem(spruchkoerper, self.appFont)
                tempItem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.termineTableView.setItem(rowNo, 6, tempItem)
                
                rowNo+=1
                
            
            self.termineTableView.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
            self.termineTableView.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)    
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
        if akteID == 'Alle_Dokumente':
            rows = self.akte.getFileRows()
            for akteID in self.akte.alleAktenIDs:
                rows.extend(self.akte.getFileRows(akteID))
        else:
            rows = self.akte.getFileRows(akteID)
        
        filename = []
        #sort data & add action Icons
        for row in rows:
            
            #Ensure documents with the same filename are displayed only one time  
            if row['dateiname'] in filename:
                continue
            else:
                filename.append(row['dateiname']) 
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
            self.docTableView.setHorizontalHeaderItem(0, self.__tableItem('', self.buttonFont))
            if self.docHeaderColumnsSettings['']['width']:
                self.docTableView.setColumnWidth(0, self.docHeaderColumnsSettings['']['width'])
                self.docTableView.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            self.docTableView.setHorizontalHeaderItem(1,  self.__tableItem('', self.buttonFont))
            if self.docHeaderColumnsSettings['']['width']:
                self.docTableView.setColumnWidth(1, self.docHeaderColumnsSettings['']['width'])
                self.docTableView.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
            
            columnCount=2
            for item in self.docTableAttributes:
                headerText=self.docHeaderColumnsSettings[item]['headertext']
                self.docTableView.setHorizontalHeaderItem(columnCount, self.__tableItem(headerText, self.appFont))

                # set width to auto for items that have a width defined (due to option to adjust font size width is ignored)...
                if self.docHeaderColumnsSettings[item]['width']:
                    self.docTableView.horizontalHeader().setSectionResizeMode(columnCount, QHeaderView.ResizeMode.ResizeToContents)
            
                columnCount+=1
                
            rowNo=0
            self.isDocColumnEmpty={}
            for row in data:
                itemNo=0
                for item in row:
                    #Material Icons font for first two columns
                    if itemNo > 1:
                        font=self.appFont  
                    else: 
                        font=self.buttonFont
                    
                    #Leading zeros fo '#'-Items that are not empty   
                    if itemNo==2 and item:
                        item=item.zfill(4) 
                           
                    tempItem=self.__tableItem(item, font)
                    tempItem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
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
            self.statusBar.showMessage('Der ausgewählte Inhalt enthält %s Dateien' % rowNo)
        else:
            self.statusBar.showMessage('Der ausgewählte Inhalt enthält keine Dateien')


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
        '''Blendet leere Spalten aus.'''
        for columnNo, isEmpty in self.isDocColumnEmpty.items():
            if isEmpty:
                self.docTableView.setColumnHidden(columnNo, True)       
    
    def __arrangeData(self, dictOfMetadata, attributes):
        '''Gibt die Werte eines Dictionaries in der Reihenfolge einer übergebenen Schlüsselliste zurück. Ist für einen Schlüssel kein Eintrag vorhanden, wird ein leeres Listenelement eingefügt.'''
        arrangedRow=[]      
        for attribute in attributes:
            if isinstance(dictOfMetadata.get(attribute), str):
                arrangedRow.append(self.__replaceTrueFalse(dictOfMetadata[attribute]))
            if isinstance(dictOfMetadata.get(attribute), list):
                text=''
                newline=''
                for item in dictOfMetadata[attribute]:
                    if item:
                        text+=newline + item
                        newline=' '
                arrangedRow.append(text)
                
            if dictOfMetadata.get(attribute) is None:
                arrangedRow.append('')
            
        return arrangedRow
    
    def __replaceTrueFalse(self, value):
       '''Ersetzt Strings "True" mit "ja" und "False" mit "nein". Nicht case-sensitiv.'''
       if value.lower()=='true':
           return 'ja' 
       elif value.lower()=='false':
           return 'nein'
       return value
    
    def __tableItem (self, text, font=QFont('Ubuntu', 11, 50)):
        '''Erstellt TableItem und setzt für dieses einen Font'''
        item = QTableWidgetItem(text)
        item.setFont(font)
        return item
    
    def __setMetadata(self, nachricht, aktenID=None):
        
        text=TextObject(newline='\n')
        if aktenID is None or aktenID=='' or aktenID == 'Alle_Dokumente':
            
            if nachricht.nachricht.get('vertraulichkeit'):
                text.addLine('Vertraulichkeitsstufe', nachricht.nachricht['vertraulichkeit'].get('vertraulichkeitsstufe'))
                text.addLine('Vertraulichkeitsgrund', nachricht.nachricht['vertraulichkeit'].get('vertraulichkeitsgrund'))
            
            labelList =[
                ['nachrichtenNummer','Nachricht Nr.'],
                ['nachrichtenAnzahl','Von Nachrichten gesamt'],
                ['ereignisse','Ereignis'],
                ['eigeneID','Abs. Nachr.-ID'],
                ['fremdeID','Empf. Nachr.-ID'],
                ['prozessID','Prozess-ID'],
                ['routingInformationAusSafe', 'Routinginformation'],
                ['produktName','Software'],
                ['produktHersteller','Hersteller'],
                ['produktVersion','Version'],
            ]
            for label in labelList:
                if nachricht.nachricht.get(label[0]):
                    text.addLine(label[1], nachricht.nachricht[label[0]])
        else:
            akte=nachricht.getAkte(nachricht.schriftgutobjekte['akten'], aktenID)    
    
            if akte:
                                
                eeb = 'Abgabe nicht erforderlich'
                if akte['ruecksendungEEB.erforderlich'].lower() == 'true':
                    eeb = 'Abgabe angefordert'
                text.addLine('EEB', eeb)
                
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
            
            if akte.get('laufzeit'):
                text.addLine('Laufzeit ab', akte['laufzeit'].get('beginn'))        
                text.addLine('Laufzeit bis', akte['laufzeit'].get('ende'))
            
            if akte.get('justizinterneDaten'):
                if akte.get('roemischPaginiert'):
                    text.addLine('Römisch Paginiert',  self.__replaceTrueFalse(akte['justizinterneDaten']['roemischPaginiert']))
                    
            if akte['zustellung41StPO'].lower() == 'true':
                text.addLine('Zustellung gem. §41StPO', 'ja')        
            elif akte['zustellung41StPO'].lower() == 'false':    
                text.addLine('Zustellung gem. §41StPO', 'nein')
                
            if akte.get('uebergabeAktenfuehrungsbefugnis') == 'true':
                text.addLine('Übergabe der Aktenführungsbefugnis', 'erteilt')     
           
        self.metadatenText.setPlainText(text.getText())
                        
    def __setNachrichtenkopf (self, absender, empfaenger, nachrichtenkopf):
        '''Inhalte der Nachrichtenkopf-Box setzen'''
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
    
    def __exportZipAction(self):
        '''Exportiert die Dateien der Favoritenliste nach Auswahl eines Dateinamens in eine Zip-Datei'''
        msgBox=QMessageBox()
        msgBox.setIcon(QMessageBox.Icon.Information)
        msgBox.setWindowTitle("Information")
        msgBox.setStandardButtons(QMessageBox.StandardButton.Ok)
        
        if not self.favorites:
            msgText='Aktion nicht verfügbar. Die Favoritenliste ist leer!'
        else:
            zipPath , extension = QFileDialog.getSaveFileName(None, "In ZIP-Datei exportieren",
                                                self.settings.value("defaultFolder", ''), "ZIP-Dateien (*.zip *.ZIP)")
                
            if zipPath and not zipPath.lower().endswith('.zip'):
                zipPath = zipPath + '.zip'
            
            if zipPath and self.favorites:
                filelist=[]
                for filename in self.favorites:
                    filelist.append(os.path.join(self.basedir , filename))
                filelist.append(os.path.join(self.basedir , self.settings.value("lastFile", None)))    
                try:
                    self.__createZip(zipPath, filelist)
                    msgText='Die Dateien wurden erfolgreich exportiert - %s' % zipPath
                except Exception as e:
                    msgText='Bei der Erzeugung der Zip-Datei ist ein Fehler aufgetreten.'      
                    msgBox.setIcon(QMessageBox.Icon.Warning)
                    self.lastExceptionString=str(e)        
            else:
                return
        msgBox.setText(msgText)
        self.statusBar.showMessage(msgText)
        msgBox.exec()
            
    def __createZip (self, zipname, filelist):
        '''Erzeugt aus einer Liste von Dateien in eine Zip-Datei'''
        with ZipFile(zipname, 'w') as outzip:
            for file in filelist:
                outzip.write(file, os.path.basename(file))
          
    def __exportToFolderAction(self):
        '''Fragt Zielordner in Dialog ab und exportiert Dateien'''
        msgBox=QMessageBox()
        msgBox.setWindowTitle("Information")
        msgBox.setIcon(QMessageBox.Icon.Information)
        msgBox.setStandardButtons(QMessageBox.StandardButton.Ok)
        
        if not self.favorites:
            msgText='Aktion nicht verfügbar. Die Favoritenliste ist leer!'
        else:
            folder = QFileDialog.getExistingDirectory(None, "Exportverzeichnis wählen",
                                            str(self.settings.value("defaultFolder", '')),
                                            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks)       
            if folder and self.favorites:       
                try:
                    for filename in self.favorites:
                        filepath = os.path.join(self.basedir , filename)
                        targetpath = os.path.join(folder , filename)
                        copyfile(filepath, targetpath)               
                    copyfile(self.settings.value("lastFile", None), os.path.join(folder , self.xmlFile))
                    msgText='Die Dateien wurden erfolgreich nach %s kopiert.' % folder    
                except Exception as e:
                    msgText='Es ist ein Fehler während des Kopiervorgangs aufgetreten.'
                    msgBox.setIcon(QMessageBox.Icon.Warning) 
                    self.lastExceptionString = str(e)
            else:
                return
        msgBox.setText(msgText)
        self.statusBar.showMessage(msgText)
        msgBox.exec()
         
    def __isSet(self, value):
        '''Ersetzt einen leeren String '' mit 'nicht angegeben'.'''
        if value == '':
            return 'nicht angegeben'
        else:
            return value
        
    def __setInhaltView(self, schriftgutobjekte):
        treeModel = QStandardItemModel()
        rootNode = treeModel.invisibleRootItem()
        
        if (len(schriftgutobjekte['dokumente'])>0 or len(schriftgutobjekte['akten'])>0):
            alle_dokumente = StandardItem('Alle Inhalte anzeigen')
            alle_dokumente.setIcon(QIcon(os.path.join(self.scriptRoot, 'icons', 'double_arrow_down_icon.png')))
            alle_key       = StandardItem('Alle_Dokumente')
            rootNode.appendRow([alle_dokumente, alle_key])            
                
        if len(schriftgutobjekte['dokumente'])>0:
            dokumente = StandardItem('Einzeldokumente')
            dokumente.setIcon(QIcon(os.path.join(self.scriptRoot, 'icons', 'dokument_icon.png')))
            key       = StandardItem(None)
            rootNode.appendRow([dokumente, key])
        
        if len(schriftgutobjekte['akten'])>0:
            self.__getAktenSubBaum(schriftgutobjekte['akten'], rootNode) 
            
        self.inhaltView.setModel(treeModel)
        self.inhaltView.setColumnHidden(1, True)
        self.inhaltView.expandAll()
        self.inhaltView.setCurrentIndex(treeModel.index(0,0))
        # Re-connect nach jedem Laden / Setzen eines Models
        self.inhaltView.selectionModel().selectionChanged.connect(self.__updateSelectedInhalt)
        
    def __addFavorite(self, filename):
        '''Fügt eine Datei zu den  Favoriten hinzu'''
        self.favorites.add(filename) 
        self.__setFavorites()
        self.statusBar.showMessage(filename + ' zu Favoriten hinzugefügt.')
    
    def __setFavorites(self):
        '''Aktualisiert die Einträge in der Favoriten-View und initiiert die Speicherung der Werte'''
        self.favoritenView.clear()
        
        for favorite in self.favorites:
            self.favoritenView.addItem(QListWidgetItem(favorite))
        
        self.__saveFavorites()    
    
    def __setFontsizes(self, appFontsize=15, buttonFontSize=17, iconFontSize=24, appFontWeight=QFont.Weight.Normal.value):
        '''Setzt die Schriftgröße für die Anwendung und Buttons'''
        self.appFontsize = appFontsize
        self.buttonFontSize = buttonFontSize
        self.iconFontSize = iconFontSize
        self.appFontWeight = appFontWeight
        
        self.iconFont.setPixelSize(iconFontSize)
        self.buttonFont.setPixelSize(buttonFontSize)    
        self.appFont.setPixelSize(appFontsize)
        self.appFont.setWeight(appFontWeight)
        self.setFont(self.appFont)
        if self.app:
            self.app.setFont(self.appFont)
        
        docTableRows       = self.docTableView.rowCount()
        docTableColumns    = self.docTableView.columnCount()
        
        if docTableRows > 0 and docTableColumns > 0:
            for column in range(docTableColumns):
                    if column > 1:
                        font=self.appFont
                    else:
                        font=self.buttonFont
                    self.docTableView.horizontalHeaderItem(column).setFont(font)
            for row in range(docTableRows):
                for column in range(docTableColumns):
                    if column > 1:
                        font=self.appFont
                    else:
                        font=self.buttonFont
                    self.docTableView.item(row, column).setFont(font)    
          
        termineTableRows    = self.termineTableView.rowCount()
        termineTableColumns = self.termineTableView.columnCount()
        
        if termineTableRows > 0 and termineTableColumns > 0:
            for column in range(termineTableColumns):
                self.termineTableView.horizontalHeaderItem(column).setFont(self.appFont)
            for row in range(termineTableRows):
                for column in range(termineTableColumns):
                    self.termineTableView.item(row, column).setFont(self.appFont)
            
        self.deleteFavoriteButton.setFont(self.buttonFont)
        self.filterMagic.setFont(self.buttonFont)
        self.toolBar.setFont(self.iconFont)

    def __toggleFontsizes(self):
        '''Toggle die Schriftgröße für die Anwendung und die Buttons'''
        if self.actionGrosse_Schrift.isChecked():
            self.__setFontsizes(appFontsize=20, buttonFontSize=20, iconFontSize=28)
        else:
            self.__setFontsizes()
        
    def __removeFavorite(self):
        '''Entfernt den aktuell in der FavoritenView markierten Eintrag aus der Liste der Favoriten.'''
        if self.favoritenView.currentItem():
            filename = self.favoritenView.currentItem().text()
            self.favorites.remove(filename)
            self.__setFavorites()
            self.__saveFavorites()
            self.statusBar.showMessage(filename + ' aus Favoriten entfernt.')
            
    def __loadFavorites(self):
        '''Lädt die Favoriten aus einer Datei, deren Dateinamen dem Wert der 'eigeneID' entspricht.'''
        self.favorites.clear()
        if self.akte.nachricht['eigeneID']:
            filepath = os.path.join(self.dirs.user_data_dir , self.akte.nachricht['eigeneID'])
            if os.path.exists(filepath):
                with open(filepath , 'r', encoding = 'utf-8') as favoriteFile:
                    for filename in favoriteFile.readlines():
                        self.favorites.add(filename.rstrip("\n"))
            
        self.__setFavorites()
         
    def __saveFavorites(self):
        '''Speichert die Favoriten in einer Datei, deren Dateinamen dem Wert der 'eigeneID' entspricht.'''
        if self.akte.nachricht['eigeneID']:
            filepath = os.path.join(self.dirs.user_data_dir , self.akte.nachricht['eigeneID'])
            if self.favorites:
                with open(filepath , 'w', encoding = 'utf-8') as favoriteFile:
                    for filename in self.favorites: 
                        favoriteFile.write(filename + '\n')
            elif os.path.exists(filepath):
                os.remove(filepath)
    
    def __loadNotes(self):
        '''Lädt die Notizen aus einer Datei, deren Dateinamen dem Wert der notizen + 'eigeneID' entspricht.'''
        self.notizenText.clear()
        if self.akte.nachricht['eigeneID']:
            filepath = os.path.join(self.dirs.user_data_dir , 'notizen' + self.akte.nachricht['eigeneID'])
            if os.path.exists(filepath):
                try:
                    with open(filepath , 'r', encoding = 'utf-8') as notesFile:
                        notes_text=notesFile.read()
                except Exception:
                    # Unter Windows wurden "alte" Notizen ggf. nicht als UTF-8 gespeichert und werfen Fehler
                    with open(filepath , 'r') as notesFile:
                        notes_text=notesFile.read()
                self.notizenText.setPlainText(notes_text)
         
    def __saveNotes(self):
        '''Speichert die Favoriten in einer Datei, deren Dateinamen dem Wert der 'eigeneID' entspricht.'''
        notizen=self.notizenText.toPlainText()
        try:
            if self.akte.nachricht['eigeneID']:
                filepath = os.path.join(self.dirs.user_data_dir , 'notizen' + self.akte.nachricht['eigeneID'])
                if re.sub(r"[\n\t\s]*", "", notizen):
                    with open(filepath , 'w', encoding = 'utf-8') as notesFile:
                        notesFile.write(notizen)
                elif os.path.exists(filepath):
                    os.remove(filepath)
        except AttributeError:
            pass

    def __getAktenSubBaum(self, akten, node):    
        for einzelakte in akten.values():
           
            if einzelakte['aktentyp']:
                name = einzelakte['anzeigename'] if not einzelakte['anzeigename'] in ('', None) else einzelakte['aktentyp']
            elif einzelakte['teilaktentyp'] != '': 
                name = einzelakte['anzeigename'] if not einzelakte['anzeigename'] in ('', None) else einzelakte['teilaktentyp']             
            else:
                name = "Akte"
            
            for aktenzeichen in einzelakte['aktenzeichen']:
                    if aktenzeichen['aktenzeichen.freitext']:
                        name += ' ' + aktenzeichen['aktenzeichen.freitext']
                     
            value = StandardItem(name)
            value.setIcon(QIcon(os.path.join(self.scriptRoot, 'icons', 'aktenbox_icon.png')))
            key   = StandardItem(einzelakte['id'])
            
            if len(einzelakte['teilakten'])>0:
                self.__getAktenSubBaum(einzelakte['teilakten'], value)
            
            node.appendRow([value, key])
    
    def __dClickDocTableAction (self, val):
       
        filenameColumn=self.docTableAttributes.index('dateiname')+2
        filename=self.docTableView.item( val.row(), filenameColumn).text()
        
        if val.column()==0:
            self.__addFavorite(filename) 
        elif self.settings.value('pdfViewer', 'PDFjs')=='nativ' or val.column()==1 or not filename.lower().endswith(".pdf"):
            self.__openFileExternal(filename)
            
    def __browseDocTableAction (self, val):     
        currentIndex=self.docTableView.currentIndex()
        
        if currentIndex.row() == -1:
            return
        filenameColumn=self.docTableAttributes.index('dateiname')+2
        filename=self.docTableView.item(currentIndex.row(), filenameColumn).text()
        
        if self.settings.value('pdfViewer', 'PDFjs')!='nativ':
            supportedFiles=('.pdf','.jpg', '.jpeg', '.png', '.gif', '.txt')
            # Check if a preview-file in PDF-format exists if 
            # used as viewer for exported case files
            # make sure the preview file is loaded in the browser  
            if not filename.lower().endswith(supportedFiles):
                previewFilepath = os.path.join(self.basedir , filename + '.pdf')
                if os.path.exists(previewFilepath): 
                    filename = filename + '.pdf'
                    
            if filename.lower().endswith(supportedFiles):
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
            
            if filename.lower().endswith(".pdf"):
                self.url=self.viewerPaths[self.settings.value('pdfViewer', 'PDFjs')] + "%s" % (filePath)
                
                if darkdetect.isDark() and self.settings.value('pdfViewer', 'PDFjs')=='PDFjs':
                    self.url+='&darkmode=True'
            
            else:
                winslash = '/' if sys.platform.lower().startswith('win') else ''    
            
                self.url =" file://%s%s" % (winslash, filePath)
  
            self.browser.setUrl(QUrl.fromUserInput(self.url))
        else: 
            self.statusBar.showMessage('Datei existiert nicht: %s' % filename) 
    
    def __getFavoriteViewAction (self, val):     
        filename =  self.favoritenView.currentIndex().data()
    
        if self.settings.value('pdfViewer', 'PDFjs')!='nativ':
            supportedFiles=('.pdf','.jpg', '.jpeg', '.png', '.gif', '.txt')
            # Check if a preview-file in PDF-format exists if 
            # used as viewer for exported case files
            # make sure the preview file is loaded in the browser  
            if not filename.lower().endswith(supportedFiles):
                previewFilepath = os.path.join(self.basedir , filename + '.pdf')
                if os.path.exists(previewFilepath): 
                    filename = filename + '.pdf'
                    
            if filename.lower().endswith(supportedFiles):
                self.__openFileInBrowser(filename)
            
    def __getDClickFavoriteViewAction (self, val):
             
        self.__openFileExternal(val.data()) 
        
    
    def __selectZipFiles(self):
        files , check = QFileDialog.getOpenFileNames(None, "XJustiz-ZIP-Archive öffnen",
                                               str(self.settings.value("defaultFolder", self.homedir)), "XJustiz-Archive (*.zip *.ZIP)")
        if check:
            self.getZipFiles(files)
    
    def getZipFiles(self, files=None):
        if files:
            self.app.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
            self.tempPath=TemporaryDirectory()
            
            for file in files:
                try:
                    with ZipFile(file, 'r') as zip: 
                        zip.extractall(self.tempPath.name)    
                except Exception as e:
                    self.app.restoreOverrideCursor()
                    self.statusBar.showMessage(file + ' konnte nicht entpackt werden.')
                    self.lastExceptionString=str(e)
                    return
            
            self.app.restoreOverrideCursor()
            self.getFile(folder=self.tempPath.name)
            
    def getFile(self, file=None, folder=None):
        #Notes eines ggf. geöffneten Datensatzes speichern
        if len(self.notizenText.toPlainText()):
            self.__saveNotes()
        
        if file and os.path.exists(file):
            self.__loadFile(file)
        elif file and not os.path.exists(file):
            pass
        elif file is None:
            
            if folder is None:
                folder=str(self.settings.value("defaultFolder", self.homedir))
            
            file , check = QFileDialog.getOpenFileName(None, "XJustiz-Datei öffnen",
                                               folder, "XJustiz-Dateien (*.xml *.XML)")
            if check:
                self.__loadFile(file)
                
            # Windows loses focus loading ZIP-files
            self.activateWindow()
        
    def __fileHistory(self, direction):
        '''Blättert durch die Aktenhistorie und lädt die nächste / letzte Akte in der Liste'''

        while len(self.browsingHistory)>0:
            if direction == 'forward':
                self.browsingHistory.insert(0, self.browsingHistory.pop())
            else:
                self.browsingHistory.append(self.browsingHistory.pop(0))
            if os.path.exists(self.browsingHistory[0]):
                self.getFile(self.browsingHistory.pop(0))
                break
        
        if self.actionAnwendungshinweise.isChecked():
                self.__informIfFiltersSet()           
                if self.docTableView.rowCount() == 0: 
                    self.__informIfNoDocsVisible()

    def __addToHistory(self, file):
        '''Fügt die zuletzt geöffnete XJustiz-Datei in die Historienliste ein'''
        if file in self.browsingHistory:
            self.browsingHistory.remove(file)
        self.browsingHistory.insert(0,file)

        while len(self.browsingHistory)>10:
            self.browsingHistory.pop()
        
        historyString=''
        for filepath in self.browsingHistory:
            historyString+=filepath + "\x07"
        historyString=historyString.strip("\x07")
        
        self.settings.setValue("history", historyString)

    def __loadHistory(self):
        '''Lädt die zuletzt geladenen XJustiz-Dateien in die Historienliste'''
        browsingHistory=self.settings.value("history", '').split('\x07')
        return browsingHistory

    def __loadFile(self, file):
        '''Lädt einen XJustiz-Datensatz und aktualisiert die Ansicht'''
        self.app.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            type=None
            with open(file, 'r', encoding='utf-8') as fp:
                while True:
                    line = fp.readline()
                    if not line:
                        break
                    
                    line=line.replace(" ", "")
                    
                    searchForVersion = re.search('xjustizVersion\W*=\W*[^\d](\d+\.\d+\.\d+)[^\d]', line)
                    
                    if searchForVersion:
                        type = searchForVersion.group(1)
                        break

            if   type=="2.4.0":
                self.akte=parser240(file)
            elif type=="3.2.1":
                self.akte=parser321(file)
            elif type=="3.3.1":
                self.akte=parser331(file)
            elif type=="3.4.1":
                self.akte=parser341(file)   
            else:
                # Wähle neueste Version, falls kein unterstützter Standard gefunden wird
                self.akte=parser351(file)        
            
        except Exception as e:
            self.statusBar.showMessage('Fehler beim Öffnen der Datei: %s' % file)
            self.app.restoreOverrideCursor()
            self.lastExceptionString=str(e)
            raise e
            return None 
        
        self.app.restoreOverrideCursor()
        
        self.__setDocumentTable('Alle_Dokumente')
        self.__setInhaltView(self.akte.schriftgutobjekte)
        self.__setNachrichtenkopf(self.akte.absender, self.akte.empfaenger, self.akte.nachricht)   
        self.__setMetadata(self.akte)
        self.__filtersTriggered()
        self.__loadFavorites()
        self.__loadNotes()
        self.__setInstanzenView()
        self.__setBeteiligteView()
        self.__setTerminTable(self.akte.termine)
        self.terminDetailView.setHtml('')
        self.basedir=os.path.dirname(os.path.realpath(file))
        self.xmlFile=os.path.basename(file)
        #Load empty viewer                     
        self.__loadEmptyViewer()   
        self.statusBar.showMessage('Eingelesene Datei: %s - XJustiz-Version: %s' % (file, type))
        self.settings.setValue("lastFile", file)
        self.__addToHistory(file)

    def __informIfNoDocsVisible(self):
        '''Überprüft, ob Dokumente angezeigt werden und gibt Hinweis aus.'''
        if not self.docTableView.rowCount():
            QMessageBox.information(self, "Anwendungshinweis", "Es werden aktuell keine Dateien angezeigt, da der ausgewählte Inhalt keine Dateien enthält.\n\nBitte wählen Sie einen anzuzeigenden Inhalt in der Box 'Inhalt' durch Anklicken aus.\n\n(Anwendungshinweise können unter 'Optionen' ausgeschaltet werden.)")
 
    def __informIfFiltersSet(self):
        '''Überprüft, ob Filterbegriffe gesetzt wurden und informiert per Pop-up'''
        minusFilterText=self.minusFilter.text().replace(" ","")

        #Ausnahme für Filter für technische Dateien
        for extension in [".pks",".p7s",".xml",".pkcs7"]:
            minusFilterText=minusFilterText.replace(extension, "")

        if minusFilterText or self.plusFilter.text():
            QMessageBox.information(self, "Anwendungshinweis", "Es sind eigene Filterbegriffe gesetzt.\n\nDaher werden ggf. nicht alle Dokumente angezeigt.\nBei Bedarf den Button 'Filter leeren' anklicken, um die Filter zu löschen.\n\n(Anwendungshinweise können unter 'Optionen' ausgeschaltet werden.)")
 
    def __chooseStartFolder(self):
        '''Öffnet Dialog, um ein Default-Verzeichnis festzulegen, das beim Aufruf von "Datei öffnen" geöffnet wird.'''       
        folder = QFileDialog.getExistingDirectory(None, "Standardverzeichnis wählen",
                                        str(self.settings.value("defaultFolder", '')),
                                        QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks)
         
        if folder:
            self.settings.setValue("defaultFolder", folder)
    
    def __updateSettings(self):
        for key, value in self.docHeaderColumnsSettings.items(): 
            if value['setting']:
                self.settings.setValue(key , value['setting'].isChecked())
        self.settings.setValue('nachrichtenkopf' , self.actionNachrichtenkopf.isChecked())
        self.settings.setValue('favoriten' , self.actionFavoriten.isChecked())
        self.settings.setValue('metadaten' , self.actionMetadaten.isChecked())
        self.settings.setValue('notizen' , self.actionNotizen.isChecked())
        self.settings.setValue('leereSpalten' , self.actionLeereSpaltenAusblenden.isChecked())
        self.settings.setValue('grosseSchrift' , self.actionGrosse_Schrift.isChecked())
        self.settings.setValue('anwendungshinweise' , self.actionAnwendungshinweise.isChecked())
        
        if self.actionChromium.isChecked():
            self.settings.setValue('pdfViewer', 'chromium')
        elif self.actionnativ.isChecked():
            self.settings.setValue('pdfViewer', 'nativ')                       
        else:    
            self.settings.setValue('pdfViewer', 'PDFjs')     
         
        self.settings.setValue('checkUpdates', self.actionOnlineAufUpdatesPruefen.isChecked()) 
         
        self.__updateVisibleColumns()
        self.__updateVisibleViews()
        self.__toggleFontsizes()
        
    def __viewerSwitch(self):
        '''Aktivert / deaktiviert die Viewerauswahl(-möglichkeiten) in Abhängigkeit vom ausgelösten Ereignis'''
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
    
    def __checkForUpdates(self, updateIndicator=None):
        '''Prüft online, ob eine neue Programmversion veröffentlicht wurde.'''
        updateAvailable=False
        
        #Download version info for supported platforms / hide option for unsupported ones
        if os.environ.get('APPIMAGE'):
            updateAvailable=self.__checkUrlforNewVersion('https://openXJV.de/latestAppImage.xml')
        elif sys.platform.lower().startswith('win'):
            updateAvailable=self.__checkUrlforNewVersion('https://openXJV.de/latestWinInstaller.xml')
        else:
            self.actionOnlineAufUpdatesPruefen.setVisible(False)
        
        if updateAvailable:
            if updateIndicator:
                updateIndicator.setVisible(True)
            self.statusBar.showMessage('Es steht eine neue Version der Software zum Download bereit.')
            return True
        else:
            return False
        
    def __checkUrlforNewVersion(self, url=None):
        if url: 
            try:
                with urllib.request.urlopen(url) as content:
                    for line in content.readlines():
                        result=(re.findall('<version>.+?</version>',str(line))) 
                        if result and result[0]: 
                            for newVer , oldVer in zip(result[0][9:-10].split('.'), VERSION.split('.')):
                                if newVer > oldVer:
                                    return True   
                                elif newVer < oldVer:
                                    return False
            except Exception as e:
                self.statusBar.showMessage('Online-Überprüfung auf neue Version konnte nicht durchgeführt werden.')
                self.lastExceptionString=str(e)
        return False
    
    def __readSettings(self):
        for key, value in self.docHeaderColumnsSettings.items(): 
            if value['setting']:
                setTo = str(self.settings.value(key, 'default'))
                if setTo.lower() == 'true':
                    value['setting'].setChecked(True) 
                elif setTo.lower() == 'false':
                    value['setting'].setChecked(False)
                else:    
                    value['setting'].setChecked(self.docHeaderColumnsSettings[key]['default'])
        self.actionNachrichtenkopf.setChecked           (True if str(self.settings.value('nachrichtenkopf', 'true')).lower()=='true'     else False)
        self.actionFavoriten.setChecked                 (True if str(self.settings.value('favoriten', 'true')).lower()      =='true'     else False)
        self.actionMetadaten.setChecked                 (True if str(self.settings.value('metadaten', 'false')).lower()      =='true'     else False)
        self.actionNotizen.setChecked                   (True if str(self.settings.value('notizen', 'false')).lower()       =='true'     else False)
        self.actionLeereSpaltenAusblenden.setChecked    (True if str(self.settings.value('leereSpalten', 'true')).lower()   =='true'     else False)
        self.actionChromium.setChecked                  (True if     self.settings.value('pdfViewer', 'PDFjs')              =='chromium' else False)
        self.actionnativ.setChecked                     (True if     self.settings.value('pdfViewer', 'PDFjs')              =='nativ'    else False)     
        self.actionGrosse_Schrift.setChecked            (True if str(self.settings.value('grosseSchrift', 'false')).lower() =='true'     else False)
        self.actionAnwendungshinweise.setChecked        (True if str(self.settings.value('anwendungshinweise', 'true')).lower() =='true' else False)
        self.actionOnlineAufUpdatesPruefen.setChecked   (True if str(self.settings.value('checkUpdates', 'true')).lower()   =='true'     else False)
        
        self.__viewerSwitch()
        self.__updateVisibleViews()
        self.__toggleFontsizes()
                
    def __resetSettings(self):
        '''Setzt Spalten und Ansichtsoptionen auf Defaultwerte zurück'''
        for key, value in self.docHeaderColumnsSettings.items():
            if value['setting']:
                value['setting'].setChecked(self.docHeaderColumnsSettings[key]['default'])
        self.actionNachrichtenkopf.setChecked       (True)
        self.actionFavoriten.setChecked             (True)
        self.actionMetadaten.setChecked             (False)
        self.actionNotizen.setChecked               (False)
        self.actionLeereSpaltenAusblenden.setChecked(True)  
        self.actionPDF_js.setChecked                (True)  
        self.__viewerSwitch()        
        self.__updateSettings()
        
    def __checkAllColumns(self):
        '''Setzt den Haken in den Ansichtsoptionen bei allen Spalten'''
        for key, value in self.docHeaderColumnsSettings.items():
            if value['setting']:
                value['setting'].setChecked(True)       
        self.__updateSettings()
        
    def __updateVisibleViews(self):
        self.nachrichtenkopf.setVisible(self.actionNachrichtenkopf.isChecked())
        self.favoriten.setVisible(self.actionFavoriten.isChecked())
        self.metadaten.setVisible(self.actionMetadaten.isChecked())
        self.notizen.setVisible(self.actionNotizen.isChecked())
        
    def __openManual(self):
        manualPath = os.path.join(self.scriptRoot , 'docs', 'openXJV_Benutzerhandbuch.pdf')
        self.__openFileExternal(manualPath, True, True)
    
    def __openFileExternal(self, filename, ignoreWarnings=False, absolutePath=False):
        msgBox=QMessageBox()
        msgBox.setIcon(QMessageBox.Icon.Warning)
        msgBox.setWindowTitle("Sicherheitshinweis!")
        msgBox.setStandardButtons(QMessageBox.StandardButton.Yes  | QMessageBox.StandardButton.No)
        buttonY = msgBox.button(QMessageBox.StandardButton.Yes )
        buttonY.setText('Ja')
        buttonN = msgBox.button(QMessageBox.StandardButton.No)
        buttonN.setText('Nein')
        msgBox.setDefaultButton(QMessageBox.StandardButton.No)

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
        if self.downloadFolder != '':
            startFolder = self.downloadFolder
        else:
            startFolder = download.downloadDirectory()

        folder = QFileDialog.getExistingDirectory(self, 
                                "Speicherort wählen",
                                startFolder,
                                QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks)
    
        if folder:
            download.setDownloadDirectory(folder)
            self.downloadFolder = folder
            download.accept()

    def __printToFileRequested(self, fileExtension):
        file = QFileDialog.getSaveFileName(self, 
                                "Zieldatei wählen",                        
                                '',
                                fileExtension,
                                fileExtension,
                                QFileDialog.Option.DontResolveSymlinks)
        if file[0]=='':
            raise Exception("Keine Zieldatei für Druck in Datei ausgewählt")    
        elif file[0].endswith(file[1]):
            return file[0]
        else:
            return file[0] + file[1]

    def __reportPrintProgress(self, n):
        self.statusBar.showMessage(f"Druckaufbereitung: {n}%")        
    
    def __printFinished(self):
        self.printLock=False
        del self._printer                 
    
    def printPdfWorker(self, pdf=None, printer=None):
        '''Worker function for long running PDF print task'''
        if pdf == None:
            raise AttributeError('pdf (Type:str, Path or pyFPDF-Object) needs to be passed to printWorker')
        
        if isinstance(pdf, str) or isinstance(pdf, Path) or not os.path.exists(pdf):
            self.pdf_file = Path(pdf)            
        else:
            raise TypeError('pdf not of Type str, Path or file does not exist')    
        
        painter=QPainter(printer)
                                           
        """Long-running print task."""    
        rect = painter.viewport()

        pdf = pdfium.PdfDocument(self.pdf_file)
        n_pages = len(pdf)  
        printRange=[]
        
        fromPage = printer.fromPage()
        toPage = printer.toPage()  
        printRange = range(n_pages) if fromPage == 0 else range(fromPage-1, toPage)  
        
        page_indices = [i for i in printRange]  
        
        renderer = pdf.render(
            pdfium.PdfBitmap.to_pil,
            page_indices = page_indices,
            scale = 200/72,  # 200dpi resolution
        )
        
        for i, pil_image, pageNumber in zip(page_indices, renderer, count(1)):
            
            if pageNumber > 1:
                self._printer.newPage()
            pilWidth, pilHeight = pil_image.size
            imageRatio = pilHeight/pilWidth
            
            viewportRatio= rect.height()/rect.width()   
            
            # Rotate image if orientation is not the same as print format orientation
            if (viewportRatio < 1 and imageRatio > 1) or (viewportRatio > 1 and imageRatio < 1): 
                pil_image = pil_image.transpose(Image.ROTATE_90)
                pilWidth, pilHeight = pil_image.size                  
                imageRatio = pilHeight/pilWidth
                
            # Adjust drawing area to available viewport 
            if viewportRatio > imageRatio:
                y=int(rect.width()/(pilWidth/pilHeight))                   
                printArea=QRect(0,0,rect.width(),y)
            else:
                x = int(pilWidth/pilHeight*rect.height())
                printArea=QRect(0,0,x,rect.height())
            
            image = ImageQt(pil_image)    

            # Print image                   
            painter.drawImage(printArea, image)
            firstPage=False
            self.__reportPrintProgress(int(pageNumber*100/len(page_indices)))          

        # Cleanup        
        pdf.close()
        painter.end()
        self.__printFinished()

    def __printRequested(self):
        '''Wird aufgerufen, wenn der Browser einen Druckauftrag  - window.print() - anfragt. Druckt das aktuell geladene PDF.'''
        if self.printLock:
            self.statusBar.showMessage('Der Drucker ist momentan belegt.')
            return 
        try:
            try:
                filepath = os.path.join(self.basedir , self.loadedPDFfilename)        
            except AttributeError as e:
                self.statusBar.showMessage('Keine druckbare Datei in Vorschau geladen.')
                self.lastExceptionString=str(e)
                return

            if not os.path.exists(filepath):     
                self.statusBar.showMessage('Die zu druckende Datei existiert nicht.')
                return     

            self._printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            if QPrintDialog(self._printer).exec():
                #Bekannte "print to file" Drucker    
                if self._printer.printerName() == 'Microsoft Print to PDF':
                    self._printer.setOutputFileName(self.__printToFileRequested('.pdf'))
                #Bekannte, nicht unterstützte Drucker
                elif self._printer.printerName() in ('Microsoft XPS Document Writer') or self._printer.printerName().startswith('OneNote'):
                    raise Exception("Der gewählte Drucker wird nicht unterstützt") 
                
                self.printLock=True  
                self.thread=Thread(target=self.printPdfWorker, args=(filepath, self._printer))    
                self.thread.start()             
            else:

                del self._printer       
            #Browser reload - Workaround, da PDF.js das Dokument nach Druck nicht mehr angezeigt
            self.browser.reload()            
        except Exception as e:     
            self.statusBar.showMessage('Der Druck ist fehlgeschlagen. ' + str(e))
            self.lastExceptionString=str(e)
            self.printLock=False 
            return    
            
    def __setInstanzenView(self):
        text=TextObject()
        singleValues=[        
            ['abteilung','<b>Abteilung:</b> %s<br>'],
            ['kurzrubrum','<b>Kurzrubrum:</b> %s<br>'],
            ['verfahrensinstanznummer','<b>Verfahrensinstanznummer:</b> %s<br>'],
            ['sachgebiet','<b>Sachgebiet:</b> %s<br>'],
            ['sachgebietszusatz','<b>Sachgebietszusatz:</b> %s<br>']     
        ]
                
        if self.akte.grunddaten.get('verfahrensnummer'):
            text.addLine('<b><i>Verfahrensnummer:</i></b>', self.akte.grunddaten['verfahrensnummer'])
            
        keys=list(self.akte.grunddaten['instanzen'].keys())
        for key in keys:
            instanz=self.akte.grunddaten['instanzen'][key]
            hr='________________________________________________________________________________________________<br><br>'
            text.addRaw("%s<b>Instanz %s</b><br>%s<b><i>Instanzdaten</i></b><br>" % (hr, key, hr))       
            if instanz.get('auswahl_instanzbehoerde'):
                text.addLine('<b>Behörde</b>', instanz['auswahl_instanzbehoerde'].get('name'))
            
            if instanz.get('aktenzeichen'):
                text.addLine('<b>Aktenzeichen</b>', instanz['aktenzeichen'].get('aktenzeichen.freitext'))      
                text.addLine('<b>Sammelvorgangsnummer</b>', instanz['aktenzeichen'].get('sammelvorgangsnummer'))
            
            for value in singleValues:
                if instanz.get(value[0]):
                    text.addRaw(value[1] % instanz[value[0]])
            
            for gegenstand in instanz['verfahrensgegenstand']:
                setBR=False
                if gegenstand.get('gegenstand'):
                   text.addRaw('<b>Gegenstand:</b> %s' % gegenstand['gegenstand'])
                   setBR=True
                if gegenstand.get('gegenstandswert').strip():
                   text.addRaw(', Streitwert: %s' % gegenstand['gegenstandswert'])
                   setBR=True
                if gegenstand.get('auswahl_zeitraumDesVerwaltungsaktes').strip():
                   text.addRaw(', Datum/Zeitraum: %s' % (gegenstand['auswahl_zeitraumDesVerwaltungsaktes']))   
                   setBR=True 
                if setBR:
                    text.addRaw('<br>')
            
            text.addRaw(self.__telkoTemplate(instanz['telekommunikation']))
            
        self.instanzenText.setHtml(text.getText())

    def __telkoTemplate(self, telekommunikation):
        text=TextObject()
        text.addHeading('Telekommunikationsverbindungen')
        for eintrag in telekommunikation:
                text.addRaw('%s: %s' % (eintrag.get('telekommunikationsart'),eintrag.get('verbindung')))
                if eintrag.get('telekommunikationszusatz'):
                    text.addRaw(" (%s)" % eintrag['telekommunikationszusatz'])
                text.addRaw('<br>')
        return text.getText()
    
    def __rollenTemplate(self, rollen):
        text=''
        for rolle in rollen:
            text+='<b>Rolle'
            if rolle.get('rollenID'):
                text+=' in Instanz '
                delimiter=''
                for rollenID in rolle['rollenID']:
                    text+='%s%s' % (delimiter, rollenID.get('ref.instanznummer'))
                    delimiter=', ' 
                text+=':</b> <u>%s</u><br>' % self.akte.rollenverzeichnis.get(str(rolle.get('rollennummer')))
            else:
                if rolle.get('rollenbezeichnung'):
                    text+=':</b> %s %s<br>' % (rolle.get('rollenbezeichnung'), rolle.get('nr'))
                else:
                    text+='</b><br>'    
            if rolle.get('naehereBezeichnung'):
                text+='Nähere Bezeichnung: %s<br>' % rolle['naehereBezeichnung']
            if rolle.get('sonstigeBezeichnung'):
                for bezeichnung in rolle.get('sonstigeBezeichnung'):
                    text+='Sonstige Bezeichnung: %s<br>' % bezeichnung       
            if rolle.get('dienstbezeichnung'):
                for bezeichnung in rolle.get('dienstbezeichnung'):
                    text+='Dienstbezeichnung: %s<br>' % bezeichnung   
            if rolle.get('referenz'):
                for referenz in rolle.get('referenz'):
                    text+='Bezug zu: %s<br>' %  self.akte.rollenverzeichnis.get(str(referenz))  
            if rolle.get('geschaeftszeichen'):
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
            if anschrift.get('anschriftstyp'):
                text+='<u>%s</u><br>' % anschrift['anschriftstyp']
            
            if anschrift.get('derzeitigerAufenthalt') and anschrift.get('derzeitigerAufenthalt').lower()=='true':
                text+='Hierbei handelt es sich um den derzeitigen Aufenthalt.<br>' 
            
            for key, value in items.items():
                if anschrift[key]:
                    text += value % anschrift[key]
                
            if anschrift.get('strasse') or anschrift.get('hausnummer'):
                text+='%s %s<br>' % (anschrift.get('strasse'), anschrift.get('hausnummer'))
            if anschrift.get('anschriftenzusatz'): 
                delimiter=''
                for zusatz in anschrift['anschriftenzusatz']:
                    text+=delimiter + zusatz
                    delimiter=', '
                text+='<br>'
            if anschrift.get('postfachnummer'):
                text+='Postfach %s<br>' % anschrift['postfachnummer']
            if anschrift.get('postleitzahl') or anschrift.get('ort'):
                text+='%s %s %s<br>' % (anschrift.get('postleitzahl'), anschrift.get('ort'), anschrift.get('ortsteil'))
            if anschrift.get('staat'):
                text+='%s<br>' % anschrift['staat']
            if anschrift.get('bundesland'):
                text+='%s<br>' % anschrift['bundesland']
            delimiter='<br>'
            
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
                if vollerName[bestandteil] is None or not vollerName[bestandteil]:
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
                if vollerName[bestandteil] is None or not vollerName[bestandteil]:
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
        
        if beteiligter.get('bezeichnung.aktuell'):
            text+='Bezeichnung: %s<br>' % beteiligter['bezeichnung.aktuell']
        
        for alteBezeichnung in beteiligter['bezeichnung.alt']:
            text+='Ehemals: %s<br>' % alteBezeichnung
        
        if beteiligter.get('kanzleiform'):
            text+='Kanzleiform: %s<br>' % beteiligter['kanzleiform']
            
            if beteiligter.get('rechtsform'):
                text+='Rechtsform: %s<br>' % beteiligter['rechtsform']
            
        if beteiligter.get('geschlecht'):
            text+='Geschlecht: %s<br>' % beteiligter['geschlecht']
            
        text+=self.__anschriftTemplate(beteiligter['anschrift'])
        
        text+=self.__telkoTemplate(beteiligter['telekommunikation'])

        if beteiligter.get('bankverbindung'):
            text+=self.__bankverbindungTemplate(beteiligter['bankverbindung'])
        
        if beteiligter.get('umsatzsteuerID'):
            text+='<br><b><i>Steuerdaten</i></b><br>'
            text+='Umsatzsteuer-ID: %s<br>' % beteiligter['umsatzsteuerID']
        
        if beteiligter.get('raImVerfahren'):
            raDaten=self.__natPersonTemplate(beteiligter['raImVerfahren'])
            if raDaten:
                text+='<blockquote><b><u>Rechtsanwalt im Verfahren</u></b>%s</blockquote>' % raDaten
            
        return text
    
    def __orgTemplate(self, beteiligter):
        text='<br><b><u>Organisation / Juristische Person</u></b><br>'
        if beteiligter.get('bezeichnung.aktuell'):
            text+='Bezeichnung: %s</b><br>' % beteiligter['bezeichnung.aktuell']
        
        for alteBezeichnung in beteiligter['bezeichnung.alt']:
            text+='Ehemals: %s<br>' % alteBezeichnung
            
        if beteiligter.get('kurzbezeichnung'): 
            text+='Kurzbezeichnung: %s<br>' % beteiligter['kurzbezeichnung']
            
        if beteiligter.get('geschlecht'):
            text+='Geschlecht: %s<br>' % beteiligter['geschlecht']
        
        if beteiligter.get('angabenZurRechtsform'):
            text+=self.__rechtsformTemplate(beteiligter['angabenZurRechtsform'])
        
        for sitz in beteiligter['sitz']:
            text+=self.__sitzTemplate(sitz)
                        
        text+=self.__anschriftTemplate(beteiligter['anschrift'])
        text+=self.__telkoTemplate(beteiligter['telekommunikation'])
        
        if beteiligter.get('bundeseinheitlicheWirtschaftsnummer'):
            text+='<br><b><i>Bundeseinheitliche Wirtschaftsnummer</i></b><br>'
            text+='Bundeseinheitliche Wirtschaftsnr.: %s<br>' % beteiligter['bundeseinheitlicheWirtschaftsnummer']
        
        if beteiligter.get('registereintragung'):
            text+=self.__registerTemplate(beteiligter['registereintragung'])
        
        if beteiligter.get('bankverbindung'):
            text+=self.__bankverbindungTemplate(beteiligter['bankverbindung'])
        
        if beteiligter.get('umsatzsteuerID'):
            text+='<br><b><i>Steuerdaten</i></b><br>'
            text+='Umsatzsteuer-ID: %s<br>' % beteiligter['umsatzsteuerID']
        return text
    
    def __sitzTemplate(self, sitz):
        text=TextObject()
        text.addHeading('Sitz')
        text.addLine('Ort', sitz.get('ort'))
        text.addLine('Postleitzahl', sitz.get('postleitzahl'))
        text.addLine('Staat', sitz.get('staat'))
                    
        return text.getText()
    
    def __rechtsformTemplate (self, rechtsform):
        text=TextObject()
        text.addHeading('Rechtsform')
        text.addLine('Rechtsform', rechtsform.get('rechtsform'))
        text.addLine('Weitere Bezeichnung', rechtsform.get('weitereBezeichnung'))
       
        return text.getText()
    
    def __natPersonTemplate(self, beteiligter):              
        text=TextObject()
        text.addHeading('Personendaten')
        text.addRaw(self.__vollerNameTemplate(beteiligter.get('vollerName')))
        
        for staatsangehoerigkeit in beteiligter['staatsangehoerigkeit']:
            text.addLine('Staatsangehörigkeit', staatsangehoerigkeit)  
        
        for herkunftsland in beteiligter['herkunftsland']:
            text.addLine('Herkunftsland', herkunftsland)
        
        for sprache in beteiligter['sprache']:
            text.addLine('Sprache', sprache)
        
        if beteiligter.get('beruf'):
            text.addRaw('<br><b><i>Berufliche Daten</i></b><br>')
            for beruf in beteiligter['beruf']:
                text.addLine('Beruf', beruf)
                
        text.addRaw(self.__anschriftTemplate(beteiligter.get('anschrift')))
        text.addRaw(self.__telkoTemplate(beteiligter.get('telekommunikation')))
        
        if beteiligter.get('zustaendigeInstitution'):
            text.addRaw('<br><b><i>Zuständige Institution(en)</i></b><br>')
            for rollennummer in beteiligter['zustaendigeInstitution']:
                text.addRaw('%s<br>' % self.akte.rollenverzeichnis.get(str(rollennummer)))
        
        if beteiligter.get('bankverbindung'):
            text.addRaw(self.__bankverbindungTemplate(beteiligter['bankverbindung']))
        
        if beteiligter.get('bundeseinheitlicheWirtschaftsnummer'):
            text.addRaw('<br><b><i>Bundeseinheitliche Wirtschaftsnummer</i></b><br>')
            text.addLine('Wirtschaftsnummer', beteiligter['bundeseinheitlicheWirtschaftsnummer'])
        
        if beteiligter.get('umsatzsteuerID') or beteiligter.get('steueridentifikationsnummer'):
            text.addRaw('<br><b><i>Steuerdaten</i></b><br>')
            if beteiligter.get('umsatzsteuerID'):
                text.addLine('Umsatzsteuer-ID', beteiligter.get('umsatzsteuerID'))
            if beteiligter.get('steueridentifikationsnummer'):
                text.addLine('Steueridentifikationsnummer', beteiligter.get('steueridentifikationsnummer'))
                
        for alias in beteiligter.get('aliasNatuerlichePerson'):
            text.addRaw('<blockquote><b><u>Aliasdaten</u></b>%s</blockquote>' % self.__natPersonTemplate(alias))
        
        if beteiligter.get('geburt'):
            text.addRaw(self.__geburtTemplate(beteiligter['geburt']))  
        
        if beteiligter.get('tod'):
            text.addRaw(self.__todTemplate(beteiligter['tod']))
            
        if beteiligter.get('geburt'):
            text.addRaw(self.__geburtTemplate(beteiligter['geburt']))

        if beteiligter.get('ausweisdokument'):
             text.addRaw(self.__ausweisTemplate(beteiligter['ausweisdokument']))
              
        if beteiligter.get('registereintragungNatuerlichePerson'):
            text.addRaw(self.__registerNatPersonTemplate(beteiligter['registereintragungNatuerlichePerson']))
        
        if beteiligter.get('auswahl_auskunftssperre'):
            text.addRaw(self.__sperreTemplate(beteiligter['auswahl_auskunftssperre']))
            
        return text.getText() 
   
    def __ausweisTemplate (self, ausweise):
        text=TextObject()
        text.addHeading('Ausweisdokumente')
        for ausweis in ausweise:
            if text.getText():
                text.addRaw('<br>')
            text.addLine('Ausweisart', ausweis.get('ausweisart'))  
            text.addLine('Ausweis-ID', ausweis.get('ausweis.ID'))
            text.addLine('Ausstellender Staat', ausweis.get('ausstellenderStaat')) 
            if ausweis.get('ausstellendeBehoerde'): 
                text.addLine('Ausstellende Behörde', self.__behoerdeResolver(ausweis['ausstellendeBehoerde']))
            if ausweis.get('gueltigkeit'):
                text.addLine('Gültigkeit', self.__zeitraumResolver(ausweis['gueltigkeit']))
            text.addLine('Zusatzinformationen', ausweis.get('zusatzinformation'))
        return text.getText()

    def __zeitraumResolver(self, zeitraum):
        text=''
        if zeitraum.get('beginn'):
            text+=zeitraum['beginn']   
        if zeitraum.get('ende'):
            if text:
                text+=' - '
            text+=zeitraum['ende']
        return text
    
    def __behoerdeResolver(self, behoerde):
        if behoerde.get('type')=='GDS.Ref.Beteiligtennummer':
            return self.akte.beteiligtenverzeichnis.get(behoerde.get('name'))   
        else:
            return behoerde.get('name')
        
    def __registerNatPersonTemplate(self, registereintragung):
        text=TextObject()
       
        text.addHeading('Registrierung natürliche Person')

        text.addLine('Firma', registereintragung.get('verwendeteFirma'))
        text.addLine('Weitere Bezeichnung', registereintragung['angabenZurRechtsform'].get('weitereBezeichnung'))
        text.addLine('Rechtsform', registereintragung['angabenZurRechtsform'].get('rechtsform')) 
        
        if registereintragung.get('registereintragung'):
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
        text.addLine('Ausländische Registerbehörde', registrierung['auswahl_registerbehoerde'].get('auslaendischeRegisterbehoerde'))
        text.addLine('Ausländische Registerbehörde (lokaler Name)', registrierung['auswahl_registerbehoerde'].get('auslaendischeRegisterbehoerdeName'))
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
        text.addLine('Geburtsdatum', geburt.get('geburtsdatum'))
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
        verbindungNr=1
        for bankverbindung in bankverbindungen:
            for item in items:
                
                itemValue = bankverbindung.get(item[0])
                
                if item[0]=='sepa-mandat' and itemValue.lower()=='true':
                    itemValue='Erteilt'
                elif item[0]=='sepa-mandat' and itemValue.lower()=='false':
                    itemValue='Nicht erteilt'    
                
                text.addLine(item[1], itemValue)
            
            if bankverbindung.get('sepa-basislastschrift'):
                text.addLine('Lastschrifttyp' , bankverbindung['sepa-basislastschrift'].get('lastschrifttyp' ))
                text.addLine('Mandatsreferenz', bankverbindung['sepa-basislastschrift'].get('mandatsreferenz'))
                text.addLine('Mandatsdatum'   , bankverbindung['sepa-basislastschrift'].get('mandatsdatum'   ))
            
            if verbindungNr < len(bankverbindungen):
                text.addRaw('<br>')
            verbindungNr+=1            
        
        return text.getText()                      
                  
    def __setBeteiligteView(self):
        text=TextObject()
        for beteiligung in self.akte.grunddaten['beteiligung']:
            text.addLine('<b>Beteiligtennummer</b>', beteiligung.get('beteiligtennummer'))
            
            if beteiligung['rolle']:
                text.addRaw(self.__rollenTemplate(beteiligung['rolle']))
                
            beteiligter=beteiligung['beteiligter']
      
            beteiligtentyp=beteiligter.get('type')
            if beteiligtentyp=='GDS.Organisation':
                text.addRaw(self.__orgTemplate(beteiligter))
            elif beteiligtentyp=='GDS.RA.Kanzlei':
                text.addRaw(self.__kanzleiTemplate(beteiligter))
            elif beteiligtentyp=='GDS.NatuerlichePerson':  
                text.addRaw(self.__natPersonTemplate(beteiligter))
            text.addRaw('__________________________________________________________________________________<br><br>')
           
        self.beteiligteText.setHtml(text.getText())
        
    def __terminTemplate(self, termin):
        text=TextObject()
        text.addHeading('Terminsdetails')
        hr='________________________________________________________________________________________________<br><br>'
        
        #Alte Werte Fortsetzungstermin vor 3.4.1
        if termin.get('hauptterminsdatum'):
            if termin['auswahl_hauptterminszeit']['hauptterminsuhrzeit']:
                zeit = "%s Uhr" % termin['auswahl_hauptterminszeit']['hauptterminsuhrzeit']
            else:
                    zeit = termin['auswahl_hauptterminszeit']['hauptterminszeit'] 
            text.addRaw('Fortsetzungstermin des Haupttermins vom %s, %s<br>' % (termin['hauptterminsdatum'], zeit))   
            if termin['hauptterminsID']:
                text.addLine('Haupttermins-ID', termin['hauptterminsID'])
                
        #Neue Werte Fortsetzungstermin ab 3.4.1
        if termin.get('terminskategorie'):
            text.addLine('Terminskategorie', termin['terminskategorie'])
        if termin.get('ref.bezugstermin'):
            text.addLine('Bezieht sich auf ursprüngliche Termins-ID', termin['ref.bezugstermin'])
                                      
        text.addLine('Termins-ID', termin['terminsID'])
            
        if termin['terminsart']:
            text.addRaw('<b>Art des Termins: %s</b><br>' % termin['terminsart'])
                
        text.addLine('Spruchkörper', termin.get('spruchkoerper'))
                
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
        geladene.addHeading('Geladene')
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
                                        
def launchApp():

    print("QT_VERSION_STR: %s" % QT_VERSION_STR)
    print('Disabling Chromium-Sandbox for compatibility reasons (Seems to be unavailable on Debian / Ubuntu based systems anyway).')
    os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"]  = "--log-level=3"
    os.environ["QT_FONT_DPI"] = "96"
    
    if sys.platform.lower().startswith('win'):
        os.environ["QT_QPA_PLATFORM"] = "windows:darkmode=2"

    app = QApplication([sys.argv[0]])
    app.setStyle('Fusion')
    app.setObjectName('openXJV')
    app.setApplicationName('openXJV %s' % VERSION)
    app.setApplicationVersion(VERSION)
    
    #Parse sys.argv
    file=None
    ziplist=None
    if len(sys.argv)==2 and sys.argv[1].lower().endswith('xml'):
        file=sys.argv[1]
        
    elif len(sys.argv)>=2:
        ziplist=[]
        for file in sys.argv[1:]:
            if file.lower().endswith('zip'):
                ziplist.append(file)
            
    widget = UI(file=file, ziplist=ziplist, app=app)
    widget.setWindowFlags((widget.windowFlags() & ~Qt.WindowType.WindowFullscreenButtonHint) | Qt.WindowType.CustomizeWindowHint )
    app.aboutToQuit.connect(widget.cleanUp)
    widget.showMaximized()
    sys.exit(app.exec())
    
if __name__ == "__main__":
    #pypdfium with frozen application on windows
    multiprocessing.freeze_support() 
    
    launchApp()