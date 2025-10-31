import logging
import os
import sys
import yaml

from typing import Optional


# Path to the file containing the list of supported models
SUPPORTED_MODELS_FILE: str = "/models/supported_models.yaml"
# Path to the directory where models are stored
MODELS_PATH: str = os.environ.get("MODELS_PATH", "/models/output")

logger = logging.getLogger("models")

# Singleton instance for SupportedModelsManager.
# This ensures only one instance is created and used throughout the application.
_supported_models_manager_instance: Optional["SupportedModelsManager"] = None


def get_supported_models_manager() -> "SupportedModelsManager":
    """
    Returns the singleton instance of SupportedModelsManager.
    If it cannot be created, logs an error and exits the application.
    """
    global _supported_models_manager_instance
    if _supported_models_manager_instance is None:
        try:
            _supported_models_manager_instance = SupportedModelsManager()
        except Exception as e:
            logger.error(f"Failed to initialize SupportedModelsManager: {e}")
            sys.exit(1)
    return _supported_models_manager_instance


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
        # Set model_proc_full to the absolute path if model_proc is provided and not empty, otherwise empty string
        if self.model_proc is not None and self.model_proc.strip() != "":
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
    Responsible for reading supported_models.yaml and filtering available models.
    """

    def __init__(self) -> None:
        """
        Loads and validates the supported models from SUPPORTED_MODELS_FILE.
        Populates self._models with SupportedModel instances.
        Raises RuntimeError on file errors or validation failures.
        """
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
                    # Validate and extract required fields
                    # Read all optional fields, use None if they are missing
                    self._models.append(
                        SupportedModel(
                            name=require_str_field(entry, "name", idx),
                            display_name=require_str_field(entry, "display_name", idx),
                            source=require_str_field(entry, "source", idx),
                            model_type=require_str_field(entry, "type", idx),
                            model_path=require_str_field(entry, "model_path", idx),
                            model_proc=entry.get("model_proc", None),
                            unsupported_devices=entry.get("unsupported_devices", None),
                            precision=entry.get("precision", None),
                            default=entry.get("default", False),
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

    def find_installed_model_by_name(self, name: str) -> Optional[SupportedModel]:
        """
        Finds an installed model by its internal name.

        Args:
            name (str): The internal name of the model.

        Returns:
            Optional[SupportedModel]: The installed SupportedModel instance if found, otherwise None.
        """
        for model in self._models:
            if model.name == name and model.exists_on_disk():
                return model
        return None

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

    def find_installed_model_by_model_path_full(
        self, model_path_full: str
    ) -> Optional[SupportedModel]:
        """
        Finds an installed model by its full model path.

        Args:
            model_path_full (str): The absolute path to the model file.

        Returns:
            Optional[SupportedModel]: The installed SupportedModel instance if found, otherwise None.
        """
        for model in self._models:
            if model.model_path_full == model_path_full and model.exists_on_disk():
                return model
        return None
