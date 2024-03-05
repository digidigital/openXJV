#!/usr/bin/env python3
import os
import sys
import json
import concurrent.futures
from Search import get_document_text
from multiprocessing import cpu_count, freeze_support

VERSION = '0.1'

def parse_text(filename, filepath):
    text = ''
    try:
        if not filename.lower().endswith(('.cer', '.zip', '.p7s', '.pks', '.pkcs7', '.doc', '.xls', '.tiff', '.tif', '.png', '.jpg')) and not 'laufzettel' in filepath:
            text = get_document_text(filepath, lower_case=True)
    except Exception as e:
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
                with concurrent.futures.ProcessPoolExecutor(cpu_count()) as executor: 
                    future_search = {executor.submit(parse_text, job[0], job[1]): job for job in searchJobs}
                    for future in concurrent.futures.as_completed(future_search):
                        try:
                            if future.result() != None:
                                filename=future.result()[0]
                                text=future.result()[1] 
                                result[filename] = text
                        except Exception as e:
                            pass 
            print(json.dumps(result))                     
        except Exception as e:
            print(e)
            sys.exit(1)    
    else:
        print(f'Version {str(VERSION)}', end='')
        sys.exit(1)