import os

# Path to the file containing the list of supported models
SUPPORTED_MODELS_FILE = "/models/supported_models.lst"
# Path to the directory where models are stored
MODELS_PATH = os.environ.get("MODELS_PATH", "/models/output")


class SupportedModel:
    """
    Represents a single supported model with its metadata.
    """

    def __init__(self, name, display_name, source, model_type, default_flag=None):
        self.name = name
        self.display_name = display_name
        self.source = source
        self.model_type = model_type
        self.default_flag = default_flag

    def model_dir(self):
        """
        Returns the directory path where the model should be located on disk.
        """
        return os.path.join(MODELS_PATH, self.source, self.name)

    def exists_on_disk(self):
        """
        Checks if the model directory exists on disk.
        """
        return os.path.isdir(self.model_dir())


class SupportedModelsManager:
    """
    Responsible for reading supported_models.lst and filtering available models.
    """

    def __init__(self):
        self._models = []
        try:
            with open(SUPPORTED_MODELS_FILE, "r") as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("|")
                    # Each line must have exactly 5 columns
                    if len(parts) != 5:
                        continue
                    name, display_name, source, model_type, default_flag = parts
                    self._models.append(
                        SupportedModel(
                            name, display_name, source, model_type, default_flag
                        )
                    )
        except Exception as e:
            raise RuntimeError(
                f"Cannot read supported models file '{SUPPORTED_MODELS_FILE}': {e}"
            )
        if not self._models:
            raise RuntimeError(
                f"No supported models found in '{SUPPORTED_MODELS_FILE}'."
            )

    def _filter_models(self, model_names, default_model, model_type):
        """
        Filters models of a given type, returning only those present on disk and in model_names.
        Handles 'Disabled' as a special option.
        Returns a tuple: (filtered_list, default_model).
        """
        filtered = []
        # Add 'Disabled' as the first option if present in model_names
        if "Disabled" in model_names:
            filtered.append("Disabled")
        filtered += [
            m.display_name
            for m in self._models
            if m.model_type == model_type
            and m.display_name in model_names
            and m.exists_on_disk()
        ]
        # Try to select the default model
        default = (
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

    def filter_detection_models(self, model_names, default_model):
        """
        Filters detection models based on availability and input arguments.
        """
        return self._filter_models(model_names, default_model, "detection")

    def filter_classification_models(self, model_names, default_model):
        """
        Filters classification models based on availability and input arguments.
        """
        return self._filter_models(model_names, default_model, "classification")
