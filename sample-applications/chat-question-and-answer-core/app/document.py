import os
from .config import config
from .logger import logger
from pathlib import Path
from fastapi import UploadFile
from langchain_community.document_loaders import (
    PyPDFLoader,
    Docx2txtLoader,
    TextLoader
)


def validate_document(file_object: UploadFile):
    """
    Validates the uploaded document based on its file extension.

    Args:
        file_object (UploadFile): The uploaded file object to be validated.

    Returns:
        bool: True if the file extension is supported, False otherwise.
    """

    validate_status = True

    file_name = os.path.basename(file_object.filename)
    file_extension = os.path.splitext(file_name)[1].lower()
    if file_extension not in config.SUPPORTED_FORMATS:
        validate_status = False

    return validate_status


async def save_document(file_object: UploadFile):
    """
    Save an uploaded file to a temporary directory.

    Args:
        file_object (UploadFile): The uploaded file object to be saved.

    Returns:
        tuple: A tuple containing the path to the saved file (Path) and an error (Exception) if any occurred.
               If the file is saved successfully, the error will be None. If an error occurs, the path will be None.
    """

    tmp_path = Path(config._TMP_FILE_PATH) / file_object.filename
    if not tmp_path.parent.exists():
        tmp_path.parent.mkdir(parents=True, exist_ok=True)

    # Read the file and save it to the tmp_path
    try:
        with tmp_path.open("wb") as buffer:
            await file_object.seek(0)
            content = await file_object.read()
            buffer.write(content)

        return tmp_path, None

    except Exception as err:
        logger.exception("Error saving file.", error=err)
        return None, err


def load_file_document(file_path):
    """
    Loads a document from the specified file path using the UnstructuredFileLoader.

    Args:
        file_path (str): The path to the file to be loaded.

    Returns:
        list: A list of documents loaded from the file.
    """

    if file_path.suffix.lower() == ".pdf":
        loader = PyPDFLoader(file_path)
    elif file_path.suffix.lower() == ".docx":
        loader = Docx2txtLoader(file_path)
    else:
        loader = TextLoader(
            file_path=file_path
        )

    docs = loader.load()

    return docs
