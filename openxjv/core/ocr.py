#!/usr/bin/env python3
"""
OCR (Optical Character Recognition) functionality for PDFs.

Migrated from helperScripts/OCR.py to openxjv.core module.
Provides Tesseract-based OCR with automatic page rotation detection.
"""
import os
import sys
import threading
from openxjv.utils.url_utils import is_in_bundle
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
from PIL import Image, ImageEnhance, ImageFilter

# pypdfium2 is not thread-safe when multiple threads open the same file
# simultaneously — concurrent PdfDocument() calls corrupt internal xref
# parsing state. This lock serializes only the fast open+render+close step;
# the slow Tesseract OCR still runs fully in parallel.
_pdfium_lock = threading.Lock()


def run_args(return_text=True):
    """
    Returns standard kwargs for subprocess.run commands.

    Args:
        return_text: Whether to capture output as text

    Returns:
        dict: Configuration for subprocess.run
    """
    kwargs={'capture_output':True,
            'text':return_text,
            'timeout':600}

    if os.name == 'nt':
        # Prevent console pop-ups in PyInstaller GUI applications
        kwargs['creationflags'] = CREATE_NO_WINDOW
    elif getattr(sys, 'frozen', False):
        # PyInstaller/AppImage set LD_LIBRARY_PATH to their internal libs.
        # Child processes must not inherit it or they may load wrong .so files.
        # Only apply when frozen — otherwise a legitimate user LD_LIBRARY_PATH
        # (e.g. Conda, custom Tesseract build) would be silently dropped.
        env = os.environ.copy()
        env.pop("LD_LIBRARY_PATH", None)
        kwargs['env'] = env

    return kwargs

class PDFocr():
    """
    OCR handler for PDF documents using Tesseract.

    This class provides OCR functionality for scanned PDFs, including:
    - Automatic page rotation detection
    - Multi-threaded processing
    - Support for both Tesseract and gocr orientation detection
    """

    def __init__(self, file=None, outpath='./output.pdf', open_when_done=False, threads=0, skip_osd=False):
        """
        Initialize OCR processor and start OCR.

        Args:
            file: Path to input PDF file
            outpath: Path for output PDF with OCR layer
            open_when_done: Whether to open result after completion
            threads: Number of threads (0 = auto)
            skip_osd: Skip orientation detection

        Raises:
            RuntimeError: If Tesseract not available
            FileNotFoundError: If input file invalid
        """

        if not PDFocr.tesseractAvailable():
            raise RuntimeError('Tesseract und / oder deutsche Sprachdateien nicht verfügbar.')

        if not file or not file.lower().endswith('.pdf'):
            raise FileNotFoundError('Kein PDF-Dokument übergeben bzw. gefunden')

        self.gocr_available = bool(
            shutil.which("gocr") or shutil.which("gocr049")
        )

        self.posix = os.name == 'posix'

        self.startOCR(file, outpath, threads, skip_osd)

        if open_when_done and os.path.exists(outpath):
                if platform.startswith('linux'):
                    env = os.environ.copy()
                    if is_in_bundle():
                        env.pop("LD_LIBRARY_PATH", None)
                    subprocess.Popen(
                        ["xdg-open", outpath],
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                elif platform.lower().startswith('win'):
                    os.startfile(outpath)
                else:
                    os.popen(f"open '{outpath}'")

    def checkIfSupported (filepath):
        """
        Checks if the file is suitable for OCR.

        A file is suitable if it's a PDF without text and with only images.

        Args:
            filepath: Path to PDF file

        Returns:
            bool: True if file can be processed with OCR
        """
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
        """
        Check if Tesseract is available with German language support.

        Returns:
            bool: True if Tesseract with German language and jbig2dec available
        """
        try:
            # Check if Tesseract is available, German language is installed
            # and jbig2dec is installed
            list_languages = subprocess.run(["tesseract", "--list-langs"], **run_args())
            if list_languages.returncode == 0 and 'deu' in list_languages.stdout:
                if shutil.which('jbig2dec'):
                    return True
                else:
                    pass
        except Exception as e:
            return False
        return False

    def startOCR (self, file, outpath, threads=0, skip_osd=False):
        """
        Start OCR process on PDF file.

        Args:
            file: Input PDF path
            outpath: Output PDF path
            threads: Number of threads (0 = auto)
            skip_osd: Skip orientation detection
        """
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

        with TemporaryDirectory() as tmpdir:
            if threads == 0:
                threads = cpu_count()-1

            # Some multithreading :)
            with concurrent.futures.ThreadPoolExecutor(threads) as executor:
                future_page_analyzer = {executor.submit(self.ocrPage, pageCollection[pageNumber], pageNumber, tmpdir, file, skip_osd): pageNumber for pageNumber in range(len(pdf.pages))}
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

        pageCollection.clear()
        pdf.close()

    def word_count(self, text, lang='deu')->int:
        """
        Count common word fragments to assess orientation quality.

        Args:
            text: Text to analyze
            lang: Language ('deu' or 'eng')

        Returns:
            int: Count of recognized word fragments
        """

        word_list_deu = [
            'ab', 'am', 'an', 'gu', 'ge', 'en', 'er', 'ch', 'an', 'de',
            'ei', 'in', 'te', 'un', 'um', 'nn', 'mm', 'tt', 're', 'ig',
            'sam', 'bar', 'los', 'ich', 'ein', 'der', 'ver', 'sch', 'die', 'und',
            'che', 'den', 'ung', 'heit', 'keit', 'nis', 'aft']

        word_list_eng = [
            'th', 'he', 'in', 'er', 'an', 're', 'rd', 'on', 'at', 'en', 'nd',
            'the', 'and', 'ing', 'ent', 'ion', 'her', 'for', 'tha', 'ter',
            'ere', 'al', 'ar', 'as', 'ed', 'is', 'it', 'or', 'ou', 'st', 've']

        counter=0
        text = text.lower()

        word_list = word_list_deu if lang =='deu' else word_list_eng

        for word in word_list:
            counter += text.count(word)

        return counter

    def is_page_empty(self, pil_image, threshold=0.03):
        """
        Check if page is mostly empty (blank).

        Args:
            pil_image: PIL Image object
            threshold: Maximum black pixel ratio to consider empty

        Returns:
            bool: True if page appears empty
        """
        import numpy as np
        # Load the image
        image = pil_image.convert('L') if pil_image.mode != 'L' else pil_image

        # Convert the image to a numpy array
        image_array = np.array(image)

        # Binarize the image
        binary_image = (image_array < 128).astype(np.uint8)

        # Calculate the percentage of black pixels
        black_pixels = np.sum(binary_image == 0)
        total_pixels = binary_image.size
        black_percentage = black_pixels / total_pixels

        # Check if the black percentage is below the threshold
        return black_percentage < threshold

    def ocrPage(self, PDF, pageNumber, tmpdir, file, skip_osd=False):
        """
        Process a single PDF page with OCR.

        Args:
            PDF: Single-page PDF object
            pageNumber: Page index
            tmpdir: Temporary directory for processing
            file: Original file path
            skip_osd: Skip orientation detection

        Returns:
            tuple: (pageNumber, processed_PDF)
        """
        ocrExceptions=''

        try:

            try:
                page_rotation = PDF.pages[0].obj.Rotate
            except:
                page_rotation = 0

            try:
                #Try to render page with pypdfium at 200dpi
                with _pdfium_lock:
                    originalPDF = pdfium.PdfDocument(file)
                    pdfimage = originalPDF[pageNumber].render(scale = 200/72).to_pil()
                    originalPDF.close()
                page_rotation = 0

            except Exception as e:
                ocrExceptions += str(e)
                try:
                    # Try to extract image with pikepdf
                    listOfImages = list(PDF.pages[0].images.keys())

                    if not len(listOfImages) == 1:
                        raise RuntimeError('PDF has more than one image on a single page.')

                    image = listOfImages[0]
                    pdfimage = PdfImage(PDF.pages[0].images[image]).as_pil_image()

                    # Resize image to 300 DPI based on A4
                    limitA = 1654
                    limitB = 2338
                    if pdfimage.size[0] < pdfimage.size[1] and pdfimage.size[0] > limitA:
                        targetSize = (limitA, int(limitA/pdfimage.size[0]*pdfimage.size[1]))
                        pdfimage=pdfimage.resize(targetSize)
                    elif pdfimage.size[0] > pdfimage.size[1] and pdfimage.size[0] > limitB:
                        targetSize = (limitB, int(limitB/pdfimage.size[0]*pdfimage.size[1]))
                        pdfimage=pdfimage.resize(targetSize)

                except Exception as e:
                    ocrExceptions += str(e)
                    # In case even pikepdf fails create an empty A4 dummy page
                    # The result will be a page without text
                    pdfimage = Image.new("RGBA", (1654, 2338), (255, 0, 0, 0))
                    page_rotation = 0


            # Graustufen
            pdfimage = pdfimage.convert("L")

            # Kontrast erhöhen
            pdfimage = ImageEnhance.Contrast(pdfimage).enhance(1.4)

            # Schärfen
            pdfimage = pdfimage.filter(ImageFilter.SHARPEN)

            # Analyze rotation
            tesseract_image = os.path.join(tmpdir, f'{uuid4().hex}.png')
            pdfimage.save ((tesseract_image),"PNG", dpi=(200,200))
            tesseract_image_path = str(tesseract_image).replace('\\','\\\\') if os.name == 'nt' else str(tesseract_image)

            # Check if page is empty (less than 3% black)
            # TODO: (workaround) removed due to incompatibility of new numpy ith older CPUs
            #if self.is_page_empty(pdfimage, threshold=0.03):
            #    skip_osd=True
            
            # Check orientation
            if skip_osd:
                rotateDegrees = 0

            else:
                if not self.gocr_available:
                    try:
                        # TODO double check if rotation is correctly interpreted
                        tesseract_command = f"tesseract {tesseract_image_path} stdout -l deu --psm 0 --dpi 200 -c min_characters_to_try=43"

                        osd_output = subprocess.run(shlex.split(tesseract_command, posix=self.posix), **run_args())

                        angle = re.search(r'Orientation in degrees: \d+', osd_output.stdout).group().split(':')[-1].strip()
                        confidence= re.search(r'Orientation confidence: \d+\.\d+', osd_output.stdout).group().split(':')[-1].strip()

                        if angle and float(confidence) >= 1.5:
                            rotateDegrees = int(angle)
                        else:
                            rotateDegrees = 0

                    except Exception as e:
                        rotateDegrees = 0
                else:
                    try:
                        max_count = -1
                        gocr_result = 0

                        # passenden gocr-Befehl suchen
                        gocr_bin = shutil.which("gocr049") or shutil.which("gocr")
                        if not gocr_bin:
                            raise RuntimeError("Kein gocr/gocr049 im PATH gefunden")

                        # rotate pages and do quick gocr ocr to get orientation
                        for angle in [0, 180, 90, 270]:
                            gocr_image = pdfimage.rotate(angle, expand=1)
                            gocr_image_path = os.path.join(tmpdir, f'{uuid4().hex}.pbm')
                            gocr_image.save(gocr_image_path, dpi=(200, 200))

                            # Windows: Backslashes escapen
                            if os.name == 'nt':
                                gocr_image_path = gocr_image_path.replace('\\', '\\\\')

                            gocr_command = f'{gocr_bin} -i {gocr_image_path} -m 8 -m 16 -m 32 -C "abcdeghiklmnorstuv" -a 30 -f ASCII'
                            command = shlex.split(gocr_command, posix=self.posix)
                            gocr_output = subprocess.run(command, **run_args())

                            word_count = self.word_count(gocr_output.stdout)
                            if word_count > max_count:
                                max_count = word_count
                                gocr_result = angle
                                if max_count > 300:
                                    break

                        rotateDegrees = gocr_result

                    except Exception as e:
                        rotateDegrees = 0

            # Rotate image upright
            if not rotateDegrees == 0:
                pdfimage= pdfimage.rotate(rotateDegrees, expand = 1)
                pdfimage.save (tesseract_image,"PNG", dpi=(200,200))
            del pdfimage

            # OCR with tesseract and create transparent PDF
            tesseract_command = f"tesseract {tesseract_image_path} stdout -c textonly_pdf=1 --dpi 200 -l deu pdf"
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

        if ocrExceptions and '--debug' in sys.argv:
            print(f'[OCR debug] Seite {pageNumber} Fallback-Fehler: {ocrExceptions}')

        return (pageNumber, PDF)

if __name__ == "__main__":
    freeze_support()
