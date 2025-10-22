#!/usr/bin/python3
# coding: utf-8
from .GDS_Reader import CodelistReader, Codeliste, Codelistmaker, Lookup
from .xjustizParser import parser321, parser331, parser341, parser351, parser362, parser240 
from .xjustizDeckblatt import CreateDeckblatt
from .Search import phrase_search, get_document_text, PDF, DOCX, TXT, XML, XLSX, ODT, ODS 
from .OCR import PDFocr
from .openXJV_UI import Ui_MainWindow