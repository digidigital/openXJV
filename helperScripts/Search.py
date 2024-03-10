#!/usr/bin/env python3
import os
import sys
import pypdfium2 as pdfium
import docx2txt
import lxml.etree as ET 
from pathlib import Path
from zipfile import ZipFile
from tempfile import TemporaryDirectory

VERSION = '0.1'

class Baseclass():
    def __init__(self, path) -> None:
        self.text = ''    

    def print_text (self):
        print(self.text)

    def contains (self, words, case_sensitive = False):
        searchtext = self.text
        for item in ('\r\n', '\n'):
            searchtext = searchtext.replace (item, '')

        if not case_sensitive:
            searchtext = searchtext.lower()
        
        if isinstance(words,str):
            words = words.split()
        
        if not any(['-' in word for word in words]):
            searchtext = searchtext.replace ('-', '')     

        for word in words:
            
            if not case_sensitive:
                word = word.lower()
            
            if word in searchtext:
                return True
                       
        return False

class PDF(Baseclass):
    def __init__(self, path) -> None:
        super().__init__(path)
        
        pdf =  pdfium.PdfDocument(path)
        for page_number in range (len(pdf)):
            textpage = pdf[page_number].get_textpage()
            self.text += textpage.get_text_bounded()
        pdf.close()

class DOCX(Baseclass):
    def __init__(self, path) -> None:
        super().__init__(path)
        self.text = docx2txt.process(path) 

class TXT(Baseclass):
    def __init__(self, path) -> None:
        super().__init__(path)
        try:
            try:
                self.text = Path(path).read_text(encoding='utf-8')
            except UnicodeDecodeError:
                self.text = Path(path).read_text(encoding='cp1252')
        except:
            raise Exception(path)

class XLSX(Baseclass):
    def __init__(self, path) -> None:
        super().__init__(path)       
        with TemporaryDirectory() as tmpdir:
            with ZipFile(path, 'r') as zip: 
                zip.extractall(tmpdir) 
            sharedStrings = os.path.join(tmpdir, 'xl', 'sharedStrings.xml')    
            if os.path.exists(sharedStrings):
                self.text = XML(sharedStrings).text
        
class ODT(Baseclass):
    def __init__(self, path) -> None:
        super().__init__(path)
        with TemporaryDirectory() as tmpdir:
            with ZipFile(path, 'r') as zip: 
                zip.extractall(tmpdir)  
            content = os.path.join(tmpdir, 'content.xml')
            if os.path.exists(content):
                self.text = XML(content).text

class ODS(ODT):
    def __init__(self, path) -> None:
        super().__init__(path)
                  
class XML(Baseclass):
    def __init__(self, path) -> None:
        super().__init__(path)
        tree = ET.parse(path)
        self.text = ET.tostring(tree, encoding='unicode', method='text')
                
def phrase_search(path = None, phrase = '', case_sensitive = False):           
    if path.lower().endswith('.pdf'):
        document = PDF(path)
    elif path.lower().endswith('.docx'):
        document = DOCX(path)
    elif path.lower().endswith(('.txt', '.csv')):
        document = TXT(path)
    elif path.lower().endswith('.odt'): 
        document = ODT(path)    
    elif path.lower().endswith('.ods'): 
        document = ODT(path)  
    elif path.lower().endswith('.xlsx'): 
        document = XLSX(path)
    elif path.lower().endswith(('.xml', '.html')): 
        document = XML(path)
    else:
        raise ValueError(f"File not supported: {path}") 
    
    if len(document.text) == 0:
        raise EOFError(f"File contains no text: {path}")
       
    return document.contains(phrase, case_sensitive)

def get_document_text(path = None, lower_case = False):            
    if path.lower().endswith('.pdf'):
        text = PDF(path).text
    elif path.lower().endswith('.docx'):
        text = DOCX(path).text
    elif path.lower().endswith('.odt'):
        text = ODT(path).text
    elif path.lower().endswith('.ods'):
        text = ODS(path).text
    elif path.lower().endswith(('.txt', '.csv')):
        text = TXT(path).text
    elif path.lower().endswith('.xlsx'): 
        text = XLSX(path).text
    elif path.lower().endswith(('.xml', '.html')): 
        text = XML(path).text
    else:
        return ''

    return text.lower() if lower_case else text

if __name__ == "__main__":
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        try:
            print(get_document_text(file_path, lower_case=False), end='')
        except Exception as e:
            print(e)
            sys.exit(1)        
    else:
        print(f'Version {str(VERSION)}', end='')
        sys.exit(1)
    