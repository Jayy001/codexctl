import glob
from inspect import currentframe
from locale import currency
import logging
import os
import time

import requests

from typing import IO, Any, cast


class RmWebInterfaceAPI:  # TODO: Add docstrings
    def __init__(
        self, BASE: str = "http://10.11.99.1/", logger: logging.Logger | None = None
    ):
        self.logger: logging.Logger = logger or cast(logging.Logger, logging)  # pyright:ignore [reportInvalidCast]

        self.BASE: str = BASE
        self.ID_ATTRIBUTE: str = "ID"
        self.NAME_ATTRIBUTE: str = "VissibleName"
        self.MTIME_ATTRIBUTE: str = "ModifiedClient"

        self.logger.debug(f"Base is: {BASE}")

    def __POST(
        self,
        endpoint: str,
        data: dict[str, str | IO[bytes]] | None = None,
        fileUpload: bool = False,
    ) -> bytes | Any:
        if data is None:
            data = {}

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
        self,
        folderId: str = "",
        currentLocation: str = "",
        currentDocuments: list[dict[str, Any]] | None = None,
    ):
        data = self.__POST(f"documents/{folderId}")
        if not isinstance(data, list):
            raise Exception("Unexpected result from server")

        if currentDocuments is None:
            currentDocuments = []

        for item in cast(list[dict[str, Any]], data):
            self.logger.debug(f"Checking item: {item}")

            if "fileType" in item:
                item["location"] = currentLocation
                currentDocuments.append(item)
            else:
                self.logger.debug(
                    f"Getting documents over {item[self.ID_ATTRIBUTE]}, current location is {currentLocation}/{item[self.NAME_ATTRIBUTE]}"
                )
                _ = self.__get_documents_recursive(
                    cast(str, item[self.ID_ATTRIBUTE]),
                    f"{currentLocation}/{item[self.NAME_ATTRIBUTE]}",
                    currentDocuments,
                )

        return currentDocuments

    def __get_folder_id(self, folderName: str, _from: str = "") -> str | None:
        results = self.__POST(f"documents/{_from}")

        if results is None:
            return None

        if not isinstance(results, list):
            raise Exception("Unexpected result from server")

        results.reverse()  # We only want folders

        for data in cast(list[dict[str, Any]], results):
            self.logger.debug(f"Folder: {data}")

            if "fileType" in data:
                return None

            identifier = cast(str, data[self.ID_ATTRIBUTE])
            if cast(str, data[self.NAME_ATTRIBUTE]).strip() == folderName.strip():
                return identifier

            self.logger.debug(f"Getting folders over {folderName}, {identifier}")

            recursiveResults = self.__get_folder_id(folderName, identifier)
            if recursiveResults is not None:
                return recursiveResults

    def __get_docs(
        self, folderName: str = "", recursive: bool = True
    ) -> list[dict[str, Any]]:
        folderId = ""

        if folderName:
            folderId = self.__get_folder_id(folderName)

            if folderId is None:
                return []

        if recursive:
            self.logger.debug(f"Calling recursive function on {folderName}")
            return self.__get_documents_recursive(
                folderId=folderId, currentLocation=folderName
            )

        data = self.__POST(f"documents/{folderId}")

        if not isinstance(data, list):
            raise Exception("Unexpected result from server")

        data = cast(list[dict[str, Any]], data)
        for item in data:
            item["location"] = ""

        return [item for item in data if "fileType" in item]

    def download(
        self,
        document: dict[str, Any],
        location: str = "",
        overwrite: bool = False,
        incremental: bool = False,
    ):
        filename = cast(str, document[self.NAME_ATTRIBUTE])
        if "/" in filename:
            filename = filename.replace("/", "_")

        self.logger.debug(f"Downloading {filename}, location {location}")

        if not os.path.exists(location):
            self.logger.debug("Download folder does not exist, creating it")
            os.makedirs(location)

        try:
            fileLocation = f"{location}/{filename}.pdf"
            isFile = os.path.isfile(fileLocation)

            if isFile and not overwrite:
                self.logger.debug("Not overwriting file")
                return True

            if isFile and incremental and not self.__is_newer(document, fileLocation):
                self.logger.debug("Local file already exists and is newer, skipping")
                return True

            binaryData = self.__POST(
                f"download/{document[self.ID_ATTRIBUTE]}/placeholder"
            )

            if isinstance(binaryData, dict):
                print(f"Error trying to download {filename}: {binaryData}")
                return False

            with open(fileLocation, "wb") as outFile:
                _ = outFile.write(binaryData)

            return True

        except Exception as error:
            print(f"Error trying to download {filename}: {error}")
            return False

    def __is_newer(self, document: dict[str, Any], fileLocation: str):
        remote_ts = cast(str, document[self.MTIME_ATTRIBUTE])

        local_mtime = os.path.getmtime(fileLocation)
        local_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(local_mtime))

        return remote_ts > local_ts

    def upload(self, input_paths: list[str], remoteFolder: str):
        folderId = ""
        if remoteFolder:
            folderId = self.__get_folder_id(remoteFolder)

            if folderId is None:
                raise SystemError(f"Error: Folder {remoteFolder} does not exist!")

        _ = self.__POST(f"documents/{folderId}")  # Setting up for upload...

        errors: list[str] = []
        documents: list[str] = []

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
                response = self.__POST("upload", data={"file": inFile}, fileUpload=True)

                if response is None:
                    self.logger.error(
                        f"Error: Unknown error while uploading {document}!"
                    )
                    errors.append(document)
                elif response == {"status": "Upload successful"}:
                    self.logger.debug(f"Uploaded {document} successfully!")

        if len(errors) > 0:
            print("The following files failed to upload: " + ",".join(errors))

        print(f"Done! {len(documents) - len(errors)} files were uploaded.")

    def sync(
        self,
        localFolder: str,
        remoteFolder: str = "",
        overwrite: bool = False,
        incremental: bool = False,
        recursive: bool = True,
    ):
        count = 0

        if not os.path.exists(localFolder):
            self.logger.debug("Local folder does not exist, creating it")
            os.mkdir(localFolder)

        documents = self.__get_docs(remoteFolder, recursive)

        if not documents:
            print("No documents were found!")
            return

        for doc in documents:
            self.logger.debug(f"Processing {doc}")
            count += 1
            _ = self.download(
                document=doc,
                location=f"{localFolder}/{doc['location']}",
                overwrite=overwrite,
                incremental=incremental,
            )
        print(f"Done! {count} files were exported.")
