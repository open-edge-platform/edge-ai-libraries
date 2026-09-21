import asyncio
import logging
import os
import threading

from typing import Optional

# Path to the directory where models are stored
MODELS_PATH: str = os.environ.get("MODELS_PATH", "/models/output")
# Main language model file that every OpenVINO GenAI model must contain.
GENAI_SENTINEL_FILE: str = "openvino_language_model.xml"

logger = logging.getLogger("models")
MAX_MODEL_DESCRIPTION_LENGTH = 200


class SupportedModel:
    """
    Represents a single supported model with its metadata.
    """

    def __init__(
        self,
        name: str,
        display_name: str,
        source: str,
        model_type: str,
        model_path: str,
        model_proc: str | None = None,
        unsupported_devices: str | None = None,
        precision: str | None = None,
        default: bool = False,
        model_proc_is_full_path: bool = False,
        hub: str | None = None,
        canonical_name: str | None = None,
        canonical_display_name: str | None = None,
        description: str | None = None,
    ) -> None:
        """
        Initializes the SupportedModel instance.

        Args:
            name (str): Model name (unique identifier).
            display_name (str): Human-readable display name.
            source (str): Model source identifier (e.g., 'public', 'omz', 'pipeline-zoo-models').
            model_type (str): Type of the model (e.g., 'detection', 'classification').
            model_path (str): Path to the model file relative to model_dir.
            model_proc (str | None, optional): Path or identifier for the model's preprocessing file. Defaults to None.
            unsupported_devices (str | None, optional): String listing unsupported devices. Defaults to None.
            precision (str | None, optional): Model precision (e.g., 'FP32', 'INT8'). Defaults to None.
            default (bool, optional): Whether this model should be a default choice. Defaults to False.
            model_proc_is_full_path (bool, optional): If True, model_proc is treated as an absolute path. Defaults to False.
        """
        self.name: str = name
        self.display_name: str = display_name
        self.description: str | None = description
        # Canonical (YAML-level) identifiers. For model-proc variants
        # ``name``/``display_name`` carry suffixes such as
        # ``_preproc-aspect-ratio`` / ``[model-proc: ...]`` while the
        # canonical pair stays equal to the original YAML entry. This
        # lets the API collapse variants into a single installable model
        # while the PipelineBuilder keeps fine-grained choices.
        self.canonical_name: str = canonical_name if canonical_name else name
        self.canonical_display_name: str = (
            canonical_display_name if canonical_display_name else display_name
        )
        self.source: str = source
        # YAML ``hub`` field. Identifies the actual download backend
        # (e.g. ``ultralytics``, ``omz``, ``huggingface``). ``source``
        # stays as the legacy on-disk grouping key (``public``, ``omz``,
        # ``pipeline-zoo-models``, ...). When ``hub`` is missing in
        # YAML we fall back to ``source`` for backward compatibility.
        self.hub: str = hub if hub else source
        self.model_type: str = model_type
        # Normalize once so downstream string-level path comparisons (e.g. in `find_installed_model_by_model_and_proc_path`)
        # are stable against trailing slashes, redundant separators, or `./` segments.
        self.model_path: str = os.path.normpath(model_path)
        self.model_proc: str | None = model_proc
        self.unsupported_devices: str | None = unsupported_devices
        self.precision: str | None = precision
        self.default: bool = bool(default)

        self.model_path_full: str = os.path.join(MODELS_PATH, self.model_path)
        # Set model_proc_full based on whether it's a full path or relative path
        if self.model_proc is not None and self.model_proc.strip() != "":
            if model_proc_is_full_path:
                # Use the full path directly (from extra_model_procs)
                self.model_proc_full: str = self.model_proc
            else:
                # Join with MODELS_PATH for relative paths
                self.model_proc_full: str = os.path.join(MODELS_PATH, self.model_proc)
        else:
            self.model_proc_full: str = ""

    def exists_on_disk(self) -> bool:
        """
        Checks if the model exists on disk.

        For `genai` models, `model_path` is expected to be a directory that
        contains the main OpenVINO language model file
        (``GENAI_SENTINEL_FILE``).  Checking only for the directory is
        not sufficient: the download process creates the output directory early
        and may fail part-way through (e.g. due to a missing or invalid
        HF_TOKEN or a network error), leaving an empty or partial directory
        behind.  The presence of ``GENAI_SENTINEL_FILE`` confirms that
        the language model weights were actually downloaded.

        Returns:
            bool: True if the model exists, False otherwise.
        """
        if self.model_type == "vision_language_models":
            if not os.path.isdir(self.model_path_full):
                logger.debug(
                    f"GenAI model directory not found for '{self.display_name}' at path '{self.model_path_full}'"
                )
                return False
            # Require the main language model file to be present so that an
            # empty or partially-downloaded directory is not treated as installed.
            main_model_file = os.path.join(self.model_path_full, GENAI_SENTINEL_FILE)
            if not os.path.isfile(main_model_file):
                logger.debug(
                    f"GenAI model directory exists but '{GENAI_SENTINEL_FILE}' is missing "
                    f"for '{self.display_name}' at '{main_model_file}'"
                )
                return False
            return True

        return os.path.isfile(self.model_path_full)


class SupportedModelsManager:
    """
    Thread-safe singleton, in-memory read cache of the `models`/`model_variants`
    DB tables, used for fast synchronous model lookups (pipeline graph
    parsing/building, device-support checks).

    The DB is the source of truth; this cache is populated once at app
    startup (via :meth:`reload`, called from :class:`ModelManager`'s
    background-thread pre-warm, so a blocking DB read never runs on the
    event-loop thread) and explicitly refreshed after every mutation
    (download completion, upload) via :meth:`reload` (sync callers) or
    :meth:`reload_async` (async callers already on the event loop).
    It is never refreshed on a timer or lazily re-scanned - only on
    startup and right after a mutation, mirroring the DB's own
    install-status semantics.

    Implements singleton pattern using __new__ with double-checked locking.
    Create instances with SupportedModelsManager() to get the shared singleton instance.
    """

    _instance: Optional["SupportedModelsManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "SupportedModelsManager":
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """
        Protected against multiple initialization. Starts empty; call
        :meth:`reload` (or :meth:`reload_async`) to populate from the DB.
        """
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._models: list[SupportedModel] = []

    def reload(self) -> None:
        """Synchronously (re)load the cache from the DB.

        Only safe to call from a thread that is not already running an
        asyncio event loop (e.g. the background init thread or a
        download worker thread) - it opens a fresh event loop via
        ``asyncio.run``. Async callers already on the event loop must
        use :meth:`reload_async` instead.
        """
        self._models = asyncio.run(self._fetch_models_from_db())

    async def reload_async(self) -> None:
        """Async equivalent of :meth:`reload`, for callers already on the event loop."""
        self._models = await self._fetch_models_from_db()

    @staticmethod
    async def _fetch_models_from_db() -> list["SupportedModel"]:
        """Query `models`/`model_variants` and rebuild the `SupportedModel` list.

        One `SupportedModel` is produced per `ModelVariant` row, mirroring
        the old YAML fan-out (one entry per precision, plus one per
        model-proc alias). ``model_proc_is_full_path`` is derived from
        whether the stored path is absolute rather than a separate column,
        since only ``extra_model_procs`` aliases were ever stored as
        absolute paths.
        """
        # Imported lazily to avoid a module import cycle (database.py already
        # imports orm_models lazily for the same reason).
        from sqlalchemy import select

        from database import async_session_maker
        from orm_models import Model, ModelVariant

        if async_session_maker is None:
            logger.warning("Database not initialized yet; model cache stays empty")
            return []

        built: list[SupportedModel] = []
        async with async_session_maker() as session:
            db_models = (await session.execute(select(Model))).scalars().all()
            for db_model in db_models:
                variants = (
                    (
                        await session.execute(
                            select(ModelVariant).where(
                                ModelVariant.model_id == db_model.id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for variant in variants:
                    built.append(
                        SupportedModel(
                            name=variant.name,
                            display_name=variant.display_name,
                            source=db_model.source,
                            model_type=db_model.category or "",
                            model_path=variant.model_path,
                            model_proc=variant.model_proc,
                            unsupported_devices=db_model.unsupported_devices,
                            precision=variant.precision,
                            model_proc_is_full_path=bool(
                                variant.model_proc
                                and os.path.isabs(variant.model_proc)
                            ),
                            hub=db_model.hub,
                            canonical_name=db_model.name,
                            canonical_display_name=db_model.display_name,
                            description=db_model.description,
                        )
                    )
        return built

    def _filter_models(
        self, model_names: list[str], default_model: str, model_type: str
    ) -> tuple[list[str], str | None]:
        """
        Filters models of a given type, returning only those present on disk and in model_names.
        Handles 'Disabled' as a special option.
        Returns a tuple: (filtered_list, default_model).

        Args:
            model_names (list[str]): List of model display names to consider.
            default_model (str): The default model's display name.
            model_type (str): The required model type.

        Returns:
            tuple[list[str], str | None]: A tuple with the filtered list of display names and the selected default model name (or None).
        """
        filtered: list[str] = []
        # Add 'Disabled' as the first option if present in model_names
        if "Disabled" in model_names:
            filtered.append("Disabled")
        # Add all models of the required type, present in model_names and on disk
        filtered += [
            m.display_name
            for m in self._models
            if m.model_type == model_type
            and m.display_name in model_names
            and m.exists_on_disk()
        ]
        # Try to select the default model if available, otherwise None
        default: str | None = (
            "Disabled"
            if default_model == "Disabled"
            else next(
                (
                    m.display_name
                    for m in self._models
                    if m.model_type == model_type
                    and m.display_name == default_model
                    and m.exists_on_disk()
                ),
                None,
            )
        )
        # If default is not found, pick the first non-'Disabled' from filtered,
        # otherwise pick 'Disabled', or None if filtered is empty
        if default is None:
            non_disabled = next((x for x in filtered if x != "Disabled"), None)
            if non_disabled is not None:
                default = non_disabled
            elif "Disabled" in filtered:
                default = "Disabled"
            else:
                default = None
        return filtered, default

    def filter_object_detection_models(
        self, model_names: list[str], default_model: str
    ) -> tuple[list[str], str | None]:
        """
        Filters object detection models based on availability and input arguments.

        Args:
            model_names (list[str]): List of object detection model display names to consider.
            default_model (str): The default object detection model's display name.

        Returns:
            tuple[list[str], str | None]: A tuple containing the filtered list of object detection model display names
                                          and the selected default model name (or None).
        """
        return self._filter_models(model_names, default_model, "object_detection")

    def filter_image_classification_models(
        self, model_names: list[str], default_model: str
    ) -> tuple[list[str], str | None]:
        """
        Filters image classification models based on availability and input arguments.

        Args:
            model_names (list[str]): List of image classification model display names to consider.
            default_model (str): The default image classification model's display name.

        Returns:
            tuple[list[str], str | None]: A tuple containing the filtered list of image classification model display names
                                          and the selected default model name (or None).
        """
        return self._filter_models(model_names, default_model, "image_classification")

    def filter_vision_language_models(
        self, model_names: list[str], default_model: str
    ) -> tuple[list[str], str | None]:
        """
        Filters vision-language models based on availability and input arguments.

        Args:
            model_names (list[str]): List of vision-language model display names to consider.
            default_model (str): The default vision-language model's display name.

        Returns:
            tuple[list[str], str | None]: A tuple containing the filtered list of vision-language model display names
                                          and the selected default model name (or None).
        """
        return self._filter_models(model_names, default_model, "vision_language_models")

    def get_all_installed_models(self) -> list[SupportedModel]:
        """
        Returns a list of SupportedModel instances that are available on disk.

        Returns:
            list[SupportedModel]: List of available SupportedModel objects.
        """
        return [m for m in self._models if m.exists_on_disk()]

    def get_all_supported_models(self) -> list[SupportedModel]:
        """
        Returns a list of all supported models, regardless of whether they are installed.

        Returns:
            list[SupportedModel]: List of all SupportedModel objects from the YAML file.
        """
        return list(self._models)

    def is_model_supported_on_device(self, display_name: str, device: str) -> bool:
        """
        Checks if the model with the given display_name is supported on the specified device.

        Args:
            display_name (str): The display name of the model.
            device (str): The device name to check (case-insensitive).

        Returns:
            bool: True if the model is supported on the device, False otherwise.
        """
        for model in self._models:
            if model.display_name == display_name:
                if model.unsupported_devices:
                    unsupported = [
                        d.strip().lower()
                        for d in model.unsupported_devices.split(",")
                        if d.strip()
                    ]
                    return device.lower() not in unsupported
                return True
        # If model not found, treat as not supported
        return False

    def find_installed_model_by_display_name(
        self, display_name: str
    ) -> Optional[SupportedModel]:
        """
        Finds an installed model by its display name.

        Args:
            display_name (str): The human-readable display name of the model.

        Returns:
            Optional[SupportedModel]: The installed SupportedModel instance if found, otherwise None.
        """
        for model in self._models:
            if model.display_name == display_name and model.exists_on_disk():
                return model
        return None

    def find_model_by_model_and_proc_path(
        self,
        model_path: str,
        model_proc_path: Optional[str] = None,
        installed_only: bool = True,
    ) -> Optional[SupportedModel]:
        """
        Finds a model by its model path and, if provided, by its model_proc_path.

        Models are stored at paths with the structure:
            {source}/{model_name}/{precision_dir}/{filename}.xml
        where precision_dir is e.g. 'INT8', 'FP16', 'FP32', 'FP16-INT8'.

        Matching is performed in two steps:
        1. Match by filename (e.g. 'yolov10s.xml').
        2. Narrow down by the precision directory (parent dir of the file, e.g. 'INT8').
           If the precision directory extracted from model_path is non-empty and any candidates
           match it, the result is restricted to those candidates.
        3. Optionally match by model_proc filename if model_proc_path is provided.

        Args:
            model_path (str): The path to the model file (full or relative).
            model_proc_path (Optional[str]): The path to the model-proc file, or None.
            installed_only (bool): When True (default) only return models that
                are currently present on disk. Set to False to also match
                supported-but-not-yet-installed models (used by pipeline graph
                ingestion so ``used_by_pipelines`` is populated regardless of
                install status).

        Returns:
            Optional[SupportedModel]: The matching SupportedModel instance if found, otherwise None.
        """
        normalized_model_path = os.path.normpath(model_path)
        # Compare with trailing-slash stripped (pipeline descriptions may omit the slash).
        for model in self._models:
            if (
                model.model_type == "vision_language_models"
                and (not installed_only or model.exists_on_disk())
                and os.path.normpath(model.model_path_full).rstrip("/")
                == normalized_model_path.rstrip("/")
            ):
                return model

        # Extract the model filename and precision directory from the provided path.
        # Model paths follow the pattern: .../precision_dir/filename.xml
        # e.g. /models/output/public/yolov10s/INT8/yolov10s.xml  -> precision_dir = 'INT8'
        model_filename = os.path.basename(normalized_model_path)
        model_precision_dir = os.path.basename(os.path.dirname(normalized_model_path))

        # Step 1: find all models matching the filename
        matching_models = [
            model
            for model in self._models
            if os.path.basename(model.model_path) == model_filename
            and (not installed_only or model.exists_on_disk())
        ]

        if not matching_models:
            return None

        # Step 2: narrow down by precision directory name
        if model_precision_dir:
            precision_matching = [
                model
                for model in matching_models
                if os.path.basename(os.path.dirname(model.model_path))
                == model_precision_dir
            ]
            if precision_matching:
                matching_models = precision_matching
                logger.debug(
                    f"Narrowed to {len(matching_models)} model(s) by precision dir '{model_precision_dir}'"
                )

        # Step 3: if model_proc_path is specified, find a variant with a matching proc filename
        if model_proc_path is not None and model_proc_path.strip():
            for model in matching_models:
                if model.model_proc_full and os.path.basename(
                    model.model_proc_full
                ) == os.path.basename(model_proc_path):
                    logger.debug(f"Found matching model: {model.display_name}")
                    return model
            logger.debug(
                f"No matching model variant found for model-proc: {model_proc_path}"
            )
            return None

        # Return the first (best) matching model
        return matching_models[0]
