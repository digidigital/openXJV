#!/usr/bin/env python3
import os
import sys
import orjson as json
import concurrent.futures
from helperScripts import get_document_text
from multiprocessing import cpu_count, freeze_support

VERSION = '0.2'

def parse_text(filename, filepath):
    text = ''
    try:
        text = get_document_text(filepath, lower_case=True).replace('\r', '').replace('\n', '').replace('-', '').replace("", '')
    except:
        pass
    return filename, text

if __name__ == "__main__":
    freeze_support()
    if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        search_path = sys.argv[1]
        try:
            searchJobs=[]
            directory = os.fsencode(search_path)
            for file in os.listdir(directory):
                filename = os.fsdecode(file)
                documentPath=os.path.join(search_path, filename)          
                if not os.path.isfile(documentPath):
                    continue
                searchJobs.append((filename, documentPath))
            result={}
            if len(searchJobs) != 0:
                try:
                    processes = int(sys.argv[2])
                except:    
                    processes = cpu_count()
                with concurrent.futures.ProcessPoolExecutor(processes) as executor: 
                    future_search = {executor.submit(parse_text, job[0], job[1]): job for job in searchJobs}
                    for future in concurrent.futures.as_completed(future_search):
                        try:
                            if future.result() != None:
                                filename=future.result()[0]
                                text=future.result()[1] 
                                result[str(filename)] = text
                        except:
                            pass  
            sys.stdout.buffer.write(json.dumps(result))                   
        except Exception as e:
            print(e)
            sys.exit(1)    
    else:
        print(f'Version: {str(VERSION)}\nBenutzung: search_tool.exe <Ordnerpfad> <Anzahl Prozesse>\n\
Rückgabe: Typ dict (Key:Dateiname, Value:Text der Datei) in JSON serialisiert als Bytes-Objekt (Inhalt: UTF-8)\n\
Text der Datei: lower-case, Zeilenumbrüche und "-" werden entfernt. "" wenn Fehler oder nicht unterstützt\n\
Formate: pdf, docx, xlsx, txt, csv, xml, html, odt, ods\n\
Wird Anzahl Prozesse nicht angegeben, entspricht sie der Anzahl der Prozessorkerne.', end='')
        sys.exit(1)