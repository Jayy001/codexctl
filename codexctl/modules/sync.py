import requests
import os
import glob

import logging


class RmWebInterfaceAPI:  # TODO: Add docstrings
    def __init__(self, BASE="http://10.11.99.1/", logger=None):
        self.logger = logger

        if self.logger is None:
            self.logger = logging

        self.BASE = BASE
        self.NAME_ATTRIBUTE = "VissibleName"
        self.ID_ATTRIBUTE = "ID"

        self.logger.debug(f"Base is: {BASE}")

    def __POST(self, endpoint, data={}, fileUpload=False):
        try:
            logging.debug(
                f"Sending POST request to {self.BASE + endpoint} with data {data}"
            )

            if fileUpload:
                result = requests.post(self.BASE + endpoint, files=data)
            else:
                result = requests.post(self.BASE + endpoint, data=data)

            if result.status_code == 408:
                self.logger.error("Request timed out!")

            logging.debug(f"Result headers: {result.headers}")
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
            self.logger.debug(f"Checking item: {item}")

            if "fileType" in item:
                item["location"] = currentLocation
                currentDocuments.append(item)
            else:
                self.logger.debug(
                    f"Getting documents over {item[self.ID_ATTRIBUTE]}, current location is {currentLocation}/{item[self.NAME_ATTRIBUTE]}"
                )
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

        results.reverse()  # We only want folders

        for data in results:
            self.logger.debug(f"Folder: {data}")

            if "fileType" in data:
                return None

            if data[self.NAME_ATTRIBUTE].strip() == folderName.strip():
                return data[self.ID_ATTRIBUTE]

            self.logger.debug(
                f"Getting folders over {folderName}, {data[self.ID_ATTRIBUTE]}"
            )

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
            self.logger.debug(f"Calling recursive function on {folderName}")
            return self.__get_documents_recursive(
                folderId=folderId, currentLocation=folderName
            )

        data = self.__POST(f"documents/{folderId}")

        for item in data:
            item["location"] = ""

        return [item for item in data if "fileType" in item]

    def download(self, document, location="", overwrite=False):
        filename = document[self.NAME_ATTRIBUTE]
        if "/" in filename:
            filename = filename.replace("/", "_")

        self.logger.debug(f"Downloading {filename}, location {location}")

        if not os.path.exists(location):
            self.logger.debug("Download folder does not exist, creating it")
            os.makedirs(location)

        try:
            fileLocation = f"{location}/{filename}.pdf"

            if os.path.isfile(fileLocation) and overwrite is False:
                self.logger.debug(f"Not overwriting file")
                return True

            binaryData = self.__POST(
                f"download/{document[self.ID_ATTRIBUTE]}/placeholder"
            )

            if isinstance(binaryData, dict):
                print(f"Error trying to download {filename}: {binaryData}")
                return False

            with open(fileLocation, "wb") as outFile:
                outFile.write(binaryData)

            return True

        except Exception as error:
            print(f"Error trying to download {filename}: {error}")
            return False

    def upload(self, input_paths, remoteFolder):
        folderId = ""
        if remoteFolder:
            folderId = self.__get_folder_id(remoteFolder)

            if folderId is None:
                raise SystemExit(f"Error: Folder {remoteFolder} does not exist!")

        self.__POST(f"documents/{folderId}")  # Setting up for upload...

        errors, documents = [], []

        for document in input_paths:  # This needs improvement...
            if os.path.isdir(document):
                for file in glob.glob(f"{document}/*"):
                    if not file.endswith(".pdf"):
                        self.logger.error(f"Error: {document} is not a pdf!")
                    else:
                        documents.append(file)
            elif os.path.isfile(document):
                if not document.endswith(".pdf"):
                    errors.append(document)
                    self.logger.error(f"Error: {document} is not a pdf!")
                else:
                    documents.append(document)
            else:
                errors.append(document)
                self.logger.error(f"Error: {document} is not a file or directory!")

        for document in documents:
            self.logger.debug(
                f"Uploading {document} to {remoteFolder if remoteFolder else 'root'}"
            )
            with open(document, "rb") as inFile:
                response = self.__POST(
                    f"upload", data={"file": inFile}, fileUpload=True
                )

                if response is None:
                    self.logger.error(
                        f"Error: Unknown error while uploading {document}!"
                    )
                    errors.append(document)
                elif response == {"status": "Upload successful"}:
                    self.logger.debug(f"Uploaded {document} successfully!")

        if len(errors) > 0:
            print("The following files failed to upload: " + ",".join(errors))

        print(f"Done! {len(documents)-len(errors)} files were uploaded.")

    def sync(self, localFolder, remoteFolder="", overwrite=False, recursive=True):
        count = 0

        if not os.path.exists(localFolder):
            self.logger.debug("Local folder does not exist, creating it")
            os.mkdir(localFolder)

        documents = self.__get_docs(remoteFolder, recursive)

        if documents == {}:
            print("No documents were found!")

        else:
            for doc in documents:
                self.logger.debug(f"Processing {doc}")
                count += 1
                self.download(
                    doc, f"{localFolder}/{doc['location']}", overwrite=overwrite
                )
            print(f"Done! {count} files were exported.")
