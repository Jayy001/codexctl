import requests
import os


class RmWebInterfaceAPI(object):
    def __init__(self, BASE="http://10.11.99.1/"):
        self.BASE = BASE
        self.NAME_ATTRIBUTE = "VissibleName"
        self.ID_ATTRIBUTE = "ID"

    def __POST(self, endpoint, data={}):
        try:
            result = requests.post(self.BASE + endpoint, data=data)
            if "application/json" in result.headers["Content-Type"]:
                return result.json()
            return result.content

        except Exception:
            return None

    def __get_documents_recursive(
        self, folderId="", currentLocation="", currentDocuments=[]
    ):
        data = self.__POST(f"documents/{folderId}")

        for item in data:
            if "fileType" in item:
                item["location"] = currentLocation
                currentDocuments.append(item)
            else:
                self.__get_documents_recursive(
                    item[self.ID_ATTRIBUTE],
                    f"{currentLocation}/{item[self.NAME_ATTRIBUTE]}",
                    currentDocuments,
                )

        return currentDocuments

    def __get_folder_id(self, folderName, _from=""):
        results = self.__POST(f"documents/{_from}")
        
        if results is None:
            return None
        
        results.reverse() # We only want folders
        
        for data in results:
            if "fileType" in data:
                return None

            if data[self.NAME_ATTRIBUTE].strip() == folderName.strip():
                return data[self.ID_ATTRIBUTE]

            recursiveResults = self.__get_folder_id(folderName, data[self.ID_ATTRIBUTE])
            if recursiveResults is None:
                continue
            else:
                return recursiveResults

    def __get_docs(self, folderName="", recursive=True):
        folderId = ""

        if folderName:
            folderId = self.__get_folder_id(folderName)

            if folderId is None:
                return {}

        if recursive:
            return self.__get_documents_recursive(
                folderId=folderId, currentLocation=folderName
            )

        data = self.__POST(f"documents/{folderId}")
        
        for item in data:
            item['location'] = ''
            
        return [item for item in data if "fileType" in item]

    def __download(self, document, location="", overwrite=False):
        filename = document[self.NAME_ATTRIBUTE]
        if "/" in filename:
            filename = filename.replace("/", "_")

        if not os.path.exists(location):
            os.makedirs(location)

        try:
            fileLocation = f"{location}/{filename}.pdf"

            if os.path.isfile(fileLocation) and overwrite is False:
                return True

            binaryData = self.__POST(f"download/{document[self.ID_ATTRIBUTE]}/placeholder")

            if isinstance(binaryData, dict):
                print(f"Error trying to download {filename}: {binaryData}")
                return False

            with open(fileLocation, "wb") as outFile:
                outFile.write(binaryData)

            return True

        except Exception as error:
            print(f"Error trying to download {filename}: {error}")
            return False

    def sync(self, localFolder, remoteFolder="", overwrite=False, recursive=True):
        count = 0
        
        if not os.path.exists(localFolder):
            os.mkdir(localFolder)

        documents = self.__get_docs(remoteFolder, recursive)

        if documents == {}:
            print('No documents were found!')
        
        else:
            for doc in documents:
                count += 1
                self.__download(
                    doc, f"{localFolder}/{doc['location']}", overwrite=overwrite
                )      
            print(f'Done! {count} files were exported.')