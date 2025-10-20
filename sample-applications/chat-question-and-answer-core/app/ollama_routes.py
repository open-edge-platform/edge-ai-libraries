from .logger import logger
from .ollama_backend import OllamaBackend
from http import HTTPStatus
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/ollama-models", tags=["Model API"], summary="Check status of OLLAMA models")
async def get_loaded_ollama_models():
    """
    Retrieves the list of currently loaded Ollama models.
    This asynchronous function attempts to fetch the active models using the
    `list_active_models` function. If successful, it returns a dictionary
    containing the list of models. In case of an error, it logs the exception
    and raises an HTTP 500 error.

    Returns:
        dict: A dictionary with the key "model_list" containing a list of loaded models.

    Raises:
        HTTPException: If an error occurs while retrieving the model list.
    """

    try:
        loaded_models = OllamaBackend.list_active_models()

        return {"model_list": loaded_models}

    except Exception as e:
        logger.exception("Error getting models list.")
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/ollama-model", tags=["Model API"], summary="Get OLLAMA model metadata")
async def get_ollama_model_metadata(model_id: str = ""):
    """
    Retrieves metadata for a specified OLLAMA model.

    Args:
        model_id (str): The identifier of the OLLAMA model.

    Returns:
        dict: Metadata information about the specified OLLAMA model.

    Raises:
        HTTPException: If an error occurs while retrieving the model metadata.
    """

    try:
        model_metadata = OllamaBackend.show_model_info(model_id)

        return model_metadata

    except Exception as e:
        logger.exception("Error getting model metadata.")
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=str(e))