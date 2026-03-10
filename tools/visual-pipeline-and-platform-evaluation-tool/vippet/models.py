import logging
import os
import threading
import yaml

from typing import Optional

# Path to the file containing the list of supported models
SUPPORTED_MODELS_FILE: str = os.environ.get(
    "SUPPORTED_MODELS_FILE", "/models/supported_models.yaml"
)
# Path to the directory where models are stored
MODELS_PATH: str = os.environ.get("MODELS_PATH", "/models/output")

logger = logging.getLogger("models")


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
        self.source: str = source
        self.model_type: str = model_type
        self.model_path: str = model_path
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

        Returns:
            bool: True if the model exists, False otherwise.
        """
        return os.path.isfile(self.model_path_full)


class SupportedModelsManager:
    """
    Thread-safe singleton responsible for reading supported_models.yaml and filtering available models.

    Implements singleton pattern using __new__ with double-checked locking.
    Create instances with SupportedModelsManager() to get the shared singleton instance.

    Raises:
        RuntimeError: On file errors or validation failures during first initialization.
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
        Loads and validates the supported models from SUPPORTED_MODELS_FILE.
        Populates self._models with SupportedModel instances.
        Protected against multiple initialization.

        Raises:
            RuntimeError: On file errors or validation failures.
        """
        # Protect against multiple initialization
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        self._models: list[SupportedModel] = []
        try:
            with open(SUPPORTED_MODELS_FILE, "r") as f:
                models_yaml = yaml.safe_load(f)
                # Ensure the loaded YAML is a list
                if not isinstance(models_yaml, list):
                    raise RuntimeError(
                        f"Invalid format in '{SUPPORTED_MODELS_FILE}': expected a list."
                    )

                def require_str_field(
                    model_entry: dict, field_name: str, index: int
                ) -> str:
                    """
                    Helper function to validate that a required field exists,
                    is of type str, and is not empty or whitespace only.

                    Args:
                        model_entry (dict): Dictionary representing a model entry.
                        field_name (str): Name of the required field.
                        index (int): Index of the entry in the list (for error context).

                    Returns:
                        str: The validated string value for the field.

                    Raises:
                        ValueError: If the field is missing, not a string, or empty.
                    """
                    value = model_entry.get(field_name)
                    if not isinstance(value, str) or not value.strip():
                        raise ValueError(
                            f"Missing or invalid required field '{field_name}' in supported model entry at index {index}."
                        )
                    return value

                for idx, entry in enumerate(models_yaml):
                    # Validate and extract top-level required fields
                    name = require_str_field(entry, "name", idx)
                    display_name = require_str_field(entry, "display_name", idx)
                    source = require_str_field(entry, "source", idx)
                    model_type = require_str_field(entry, "type", idx)
                    unsupported_devices = entry.get("unsupported_devices", None)
                    default = entry.get("default", False)
                    extra_model_procs = entry.get("extra_model_procs", None)

                    # Validate precisions list
                    precisions = entry.get("precisions")
                    if not isinstance(precisions, list) or len(precisions) == 0:
                        raise ValueError(
                            f"Missing or invalid required field 'precisions' in supported model entry at index {idx}."
                        )

                    # Check if extra_model_procs exists and is a non-empty list
                    has_extra_procs = (
                        extra_model_procs
                        and isinstance(extra_model_procs, list)
                        and len(extra_model_procs) > 0
                    )

                    for prec_entry in precisions:
                        precision = require_str_field(prec_entry, "precision", idx)
                        model_path = require_str_field(prec_entry, "model_path", idx)
                        model_proc = prec_entry.get("model_proc", None)

                        # Append precision suffix to display_name for clarity
                        prec_display_name = f"{display_name} ({precision})"

                        # Determine if we need to modify the name/display_name for variants
                        should_modify_for_variant = (
                            has_extra_procs and model_proc and model_proc.strip()
                        )

                        # Set name and display_name based on whether this is a variant
                        if should_modify_for_variant:
                            proc_filename = os.path.splitext(
                                os.path.basename(model_proc)
                            )[0]
                            model_name = f"{name}_{proc_filename}"
                            model_display_name = (
                                f"{prec_display_name} [model-proc: {proc_filename}]"
                            )
                        else:
                            model_name = name
                            model_display_name = prec_display_name

                        # Add the base model for this precision
                        self._models.append(
                            SupportedModel(
                                name=model_name,
                                display_name=model_display_name,
                                source=source,
                                model_type=model_type,
                                model_path=model_path,
                                model_proc=model_proc,
                                unsupported_devices=unsupported_devices,
                                precision=precision,
                                default=default,
                            )
                        )

                        # If extra_model_procs is provided, create additional entries for this precision
                        if has_extra_procs:
                            for extra_proc in extra_model_procs:
                                if (
                                    extra_proc
                                    and isinstance(extra_proc, str)
                                    and extra_proc.strip()
                                ):
                                    # Note: extra_model_procs contains full absolute paths, not relative paths
                                    # Extract the filename without extension from the extra_proc path
                                    proc_filename = os.path.splitext(
                                        os.path.basename(extra_proc)
                                    )[0]
                                    extra_display_name = f"{prec_display_name} [model-proc: {proc_filename}]"
                                    self._models.append(
                                        SupportedModel(
                                            name=f"{name}_{proc_filename}",
                                            display_name=extra_display_name,
                                            source=source,
                                            model_type=model_type,
                                            model_path=model_path,
                                            model_proc=extra_proc,
                                            unsupported_devices=unsupported_devices,
                                            precision=precision,
                                            default=False,  # Variants are not default
                                            model_proc_is_full_path=True,  # extra_model_procs contains full paths
                                        )
                                    )

        except Exception as e:
            # Raise a descriptive error if the file cannot be read or parsed
            raise RuntimeError(
                f"Cannot read supported models file '{SUPPORTED_MODELS_FILE}': {e}"
            )
        # Raise an error if no valid models are found
        if not self._models:
            raise RuntimeError(
                f"No supported models found in '{SUPPORTED_MODELS_FILE}'."
            )

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

    def filter_detection_models(
        self, model_names: list[str], default_model: str
    ) -> tuple[list[str], str | None]:
        """
        Filters detection models based on availability and input arguments.

        Args:
            model_names (list[str]): List of detection model display names to consider.
            default_model (str): The default detection model's display name.

        Returns:
            tuple[list[str], str | None]: A tuple containing the filtered list of detection model display names
                                          and the selected default model name (or None).
        """
        return self._filter_models(model_names, default_model, "detection")

    def filter_classification_models(
        self, model_names: list[str], default_model: str
    ) -> tuple[list[str], str | None]:
        """
        Filters classification models based on availability and input arguments.

        Args:
            model_names (list[str]): List of classification model display names to consider.
            default_model (str): The default classification model's display name.

        Returns:
            tuple[list[str], str | None]: A tuple containing the filtered list of classification model display names
                                          and the selected default model name (or None).
        """
        return self._filter_models(model_names, default_model, "classification")

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

    def find_installed_model_by_model_and_proc_path(
        self, model_path: str, model_proc_path: Optional[str] = None
    ) -> Optional[SupportedModel]:
        """
        Finds an installed model by its model path and, if provided, by its model_proc_path.

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

        Returns:
            Optional[SupportedModel]: The installed SupportedModel instance if found, otherwise None.
        """
        # Extract the model filename and precision directory from the provided path.
        # Model paths follow the pattern: .../precision_dir/filename.xml
        # e.g. /models/output/public/yolov10s/INT8/yolov10s.xml  -> precision_dir = 'INT8'
        model_filename = os.path.basename(model_path)
        model_precision_dir = os.path.basename(os.path.dirname(model_path))

        # Step 1: find all installed models matching the filename
        matching_models = [
            model
            for model in self._models
            if os.path.basename(model.model_path) == model_filename
            and model.exists_on_disk()
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
