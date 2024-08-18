#!/usr/bin/env python3
import os
import time
import concurrent.futures
import shlex
import shutil
import subprocess
if os.name == 'nt':
    from subprocess import CREATE_NO_WINDOW
import re
from io import BytesIO
from uuid import uuid4
from multiprocessing import cpu_count, freeze_support
from sys import platform
from pikepdf import Pdf, PdfImage, Page, Rectangle, PdfError, models, _cpphelpers 
from tempfile import TemporaryDirectory
import pypdfium2 as pdfium
from PIL import Image, ImageEnhance 

def run_args(return_text=True):
    kwargs={'capture_output':True, 
            'text':return_text,
            'timeout':600}
    
    # Prevent console pop-ups in pyinstaller GUI-Applications
    if os.name == 'nt':
        kwargs['creationflags'] = CREATE_NO_WINDOW
    
    return kwargs

class PDFocr():
    def __init__(self, file=None, outpath='./output.pdf', open_when_done=False, threads = 0):     
        
        if not PDFocr.tesseractAvailable():
            raise RuntimeError('Tesseract und / oder deutsche Sprachdateien nicht verfügbar.')
        
        if not file or not file.lower().endswith('.pdf'):
            raise FileNotFoundError('Kein PDF-Dokument übergeben bzw. gefunden')

        self.posix = os.name == 'posix'
        
        self.startOCR(file, outpath, threads)
              
        if open_when_done and os.path.exists(outpath):
                if platform.startswith('linux'):
                    cmd=["xdg-open",  f"{outpath}"]
                    subprocess.call(cmd) 
                elif platform.lower().startswith('win'):
                    os.startfile(outpath)
                else:                  
                    os.popen(f"open '{outpath}'")
                
    def checkIfSupported (filepath):
        '''Checks if the file is a PDF file without text and just one image on each page'''
        # Check if only one image on each page
        if not filepath.lower().endswith('.pdf') or not os.path.exists(filepath):
            return False
        
        try:
            
            pdf = Pdf.open(filepath)
            # Check if PDF is encrypted
            if pdf.is_encrypted:
                pdf.close()
                return False   
            pdf.close()
            
            # Check if PDF has any text
            pdf =  pdfium.PdfDocument(filepath)  
            for page_number in range (len(pdf)):
                if len(pdf[page_number].get_textpage().get_text_bounded()):
                    pdf.close()
                    return False  
            pdf.close()
            
            return True
        except Exception as e:
            # In case of any error return False    
            return False
        
    def tesseractAvailable():      
        try:
            # Check if Tesseract is available, German language is installed 
            # and jbig2dec is installed
            list_languages = subprocess.run(["tesseract", "--list-langs"], **run_args())
            if list_languages.returncode == 0 and 'deu' in list_languages.stdout:
                if shutil.which('jbig2dec'):
                    return True    
        except Exception as e:
            return False     
        return False
    
    def startOCR (self, file, outpath, threads=0): 
        pdf = Pdf.open(file)
        
        # Fix for cases where some PDFs reference ALL images on ALL pages
        pdf.remove_unreferenced_resources()
              
        pageCollection=[]
        
        # Creating single page PDFs since passing a page directly raises a pickle exception / images can not be accessed :(
        for page in pdf.pages:
            tempPDF = Pdf.new()
            tempPDF.pages.append(page)
            pageCollection.append(tempPDF)

        textPages={}
        self.text = ''
            
        #start = time.time()
        with TemporaryDirectory() as tmpdir:
            if threads == 0:
                threads = cpu_count()-1
            
            # Some multithreading :)
            with concurrent.futures.ThreadPoolExecutor(threads) as executor:
                future_page_analyzer = {executor.submit(self.ocrPage, pageCollection[pageNumber], pageNumber, tmpdir, file): pageNumber for pageNumber in range(len(pdf.pages))}
                for future in concurrent.futures.as_completed(future_page_analyzer):
                    thread = future_page_analyzer[future]
                    try:
                        if future.result()[1] != None:
                            textPages[future.result()[0]] = future.result()[1]
                    except Exception as exc:
                        print(f'Thread {thread} generated an exception: {exc} - {file}')
            
            # Reassemble the PDF                 
            with Pdf.new() as ocrPdf:
                for pageNumber in range(len(pageCollection)):
                    src = textPages[pageNumber]
                    ocrPdf.pages.extend(src.pages)
                ocrPdf.save(outpath)     
        #print(f'Duration: {time.time()-start} with {threads} Threads')    
        
        pageCollection.clear()
        pdf.close() 
                
    def ocrPage(self, PDF, pageNumber, tmpdir, file):  
        ocrExceptions=''
        
        try:
            
            try:
                page_rotation = PDF.pages[0].obj.Rotate
            except:
                page_rotation = 0
            
            try:
                #Try to render page with pypdfium at 150dpi
                originalPDF = pdfium.PdfDocument(file)    
                pdfimage = originalPDF[pageNumber].render(scale = 150/72).to_pil()
                page_rotation = 0
                originalPDF.close()
                           
            except Exception as e:
                ocrExceptions+=e
                try:
                    # Try to extract image with pikepdf
                    listOfImages = list(PDF.pages[0].images.keys())
        
                    if not len(listOfImages) == 1:
                        raise RuntimeError('PDF has more than one image on a single page.')
                    
                    image = listOfImages[0]
                    pdfimage = PdfImage(PDF.pages[0].images[image]).as_pil_image() 
            
                    # Resize image to 150 DPI based on A4
                    limitA = 1240
                    limitB = 1754
                    if pdfimage.size[0] < pdfimage.size[1] and pdfimage.size[0] > limitA:  
                        targetSize = (limitA, int(limitA/pdfimage.size[0]*pdfimage.size[1])) 
                        pdfimage=pdfimage.resize(targetSize)
                    elif pdfimage.size[0] > pdfimage.size[1] and pdfimage.size[0] > limitB:  
                        targetSize = (limitB, int(limitB/pdfimage.size[0]*pdfimage.size[1])) 
                        pdfimage=pdfimage.resize(targetSize)   
            
                except Exception as e:
                    ocrExceptions+=e
                    # In case even pikepdf fails create an empty A4 dummy page   
                    # The result will be a page without text   
                    pdfimage = Image.new("RGBA", (1240, 1754), (255, 0, 0, 0))
                    page_rotation = 0

                  
            # Convert to RGB and enhance contrast (a bit)
            pdfimage=pdfimage.convert(mode='RGB')
            pdfimage = ImageEnhance.Contrast(pdfimage).enhance(2.3)
            
            # Analyze rotation
            try:
                tesseract_image = os.path.join(tmpdir, f'{uuid4().hex}.png')
                pdfimage.save ((tesseract_image),"PNG", dpi=(150,150))
                 
                tesseract_image_path = str(tesseract_image).replace('\\','\\\\') if os.name == 'nt' else str(tesseract_image)
                
                tesseract_command = f"tesseract {tesseract_image_path} stdout --psm 0 --dpi 150 -c min_characters_to_try=43"

                osd_output = subprocess.run(shlex.split(tesseract_command, posix=self.posix), **run_args())
                
                angle = re.search(r'Orientation in degrees: \d+', osd_output.stdout).group().split(':')[-1].strip()
                confidence= re.search(r'Orientation confidence: \d+\.\d+', osd_output.stdout).group().split(':')[-1].strip()
                
                if angle and float(confidence) >= 1.5:
                    rotateDegrees = int(angle)
                else:
                    rotateDegrees = 0 
                
            except Exception as e:
                rotateDegrees = 0           

            # Rotate image upright        
            if not rotateDegrees == 0:
                pdfimage= pdfimage.rotate(rotateDegrees, expand = 1) 
                pdfimage.save (tesseract_image,"PNG", dpi=(150,150)) 
            del pdfimage

            # OCR with tesseract and create transparent PDF
            tesseract_command = f"tesseract {tesseract_image_path} stdout -c textonly_pdf=1 --dpi 150 -l deu pdf"
            pdf_output = subprocess.run(shlex.split(tesseract_command, posix=self.posix), **run_args(return_text=False))
        
            os.remove(tesseract_image) 
            if not pdf_output.returncode == 0:      
                raise Exception('OCR-Operation failed')

            # Extra steps due to some issue with older versions of leptonica that invert 
            # colors of the image in exported PDF documents + rotate generated PDF to match source
            pdf = Pdf.open(BytesIO(pdf_output.stdout))
            
            rotateDegrees+=page_rotation
            if not rotateDegrees == 0:
                pdf.pages[0].rotate(rotateDegrees, relative=True)
            
            destination_page = Page(PDF.pages[0])
            overlayText = Page(pdf.pages[0])
            
            # Add transparent text to original page
            rect = destination_page.mediabox
            destination_page.add_overlay(overlayText, Rectangle(rect[0],rect[1],rect[2],rect[3]), expand=True)
            pdf.close()      
            
        # catch all exceptions and pass (returns the original page)
        except Exception as e:
            print(f'{e} - {file}')
            ocrExceptions += f'{e} - {file}'
            pass             
         
        return (pageNumber, PDF)     

if __name__ == "__main__":
    freeze_support() 
