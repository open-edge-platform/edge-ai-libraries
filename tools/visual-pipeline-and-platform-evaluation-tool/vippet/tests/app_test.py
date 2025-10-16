import unittest
from unittest import mock

# Patch SupportedModelsManager.__init__ before importing app
mock.patch(
    "models.SupportedModelsManager.__init__",
    lambda self: setattr(
        self,
        "_models",
        [
            mock.Mock(
                display_name="Model 1",
                model_type="detection",
                exists_on_disk=lambda: True,
            ),
            mock.Mock(
                display_name="Model 2",
                model_type="classification",
                exists_on_disk=lambda: True,
            ),
        ],
    ),
).start()

from app import create_interface  # noqa: E402


class TestApp(unittest.TestCase):
    def setUp(self):
        # No need to patch here, already patched above
        pass

    def test_create_interface(self):
        result = create_interface()
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
