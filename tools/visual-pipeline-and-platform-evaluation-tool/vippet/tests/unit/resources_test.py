import os
import shutil
import tempfile
import unittest
from pathlib import Path

from resources import (
    DirectoryResourceManager,
    get_labels_manager,
    get_scripts_manager,
    LABELS_PATH,
    SCRIPTS_PATH,
)


class TestDirectoryResourceManager(unittest.TestCase):
    """Test cases for DirectoryResourceManager class."""

    def setUp(self):
        """Set up test fixtures with temporary directory."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_initialization_with_path_object(self):
        """Test DirectoryResourceManager initialization with Path object."""
        path_obj = Path(self.temp_dir)
        manager = DirectoryResourceManager(path_obj)
        self.assertEqual(manager.directory, path_obj)

    def test_initialization_with_string(self):
        """Test DirectoryResourceManager initialization with string path."""
        manager = DirectoryResourceManager(self.temp_dir)
        self.assertEqual(manager.directory, Path(self.temp_dir))

    def test_get_filename_basic(self):
        """Test extracting filename from absolute path."""
        manager = DirectoryResourceManager(self.temp_dir)
        result = manager.get_filename("/path/to/file.txt")
        self.assertEqual(result, "file.txt")

    def test_get_filename_with_complex_path(self):
        """Test extracting filename from complex path."""
        manager = DirectoryResourceManager(self.temp_dir)
        result = manager.get_filename("/very/long/nested/path/to/myfile.json")
        self.assertEqual(result, "myfile.json")

    def test_get_filename_already_filename(self):
        """Test get_filename when input is already just a filename."""
        manager = DirectoryResourceManager(self.temp_dir)
        result = manager.get_filename("simple.txt")
        self.assertEqual(result, "simple.txt")

    def test_get_filename_no_extension(self):
        """Test extracting filename without extension."""
        manager = DirectoryResourceManager(self.temp_dir)
        result = manager.get_filename("/path/to/noextension")
        self.assertEqual(result, "noextension")

    def test_file_exists_true(self):
        """Test file_exists returns True for existing file."""
        # Create a test file
        test_file = Path(self.temp_dir) / "test.txt"
        test_file.write_text("test content")

        manager = DirectoryResourceManager(self.temp_dir)
        self.assertTrue(manager.file_exists("test.txt"))

    def test_file_exists_false(self):
        """Test file_exists returns False for non-existing file."""
        manager = DirectoryResourceManager(self.temp_dir)
        self.assertFalse(manager.file_exists("nonexistent.txt"))

    def test_file_exists_directory(self):
        """Test file_exists returns False for directory (not a file)."""
        # Create a subdirectory
        subdir = Path(self.temp_dir) / "subdir"
        subdir.mkdir()

        manager = DirectoryResourceManager(self.temp_dir)
        self.assertFalse(manager.file_exists("subdir"))

    def test_get_path_existing_file(self):
        """Test get_path returns full path for existing file."""
        # Create a test file
        test_file = Path(self.temp_dir) / "exists.txt"
        test_file.write_text("content")

        manager = DirectoryResourceManager(self.temp_dir)
        result = manager.get_path("exists.txt")
        expected = str(Path(self.temp_dir) / "exists.txt")
        self.assertEqual(result, expected)

    def test_get_path_nonexistent_file(self):
        """Test get_path returns None for non-existing file."""
        manager = DirectoryResourceManager(self.temp_dir)
        result = manager.get_path("missing.txt")
        self.assertIsNone(result)

    def test_get_path_with_subdirectory(self):
        """Test get_path with file in subdirectory structure."""
        # Create nested structure
        subdir = Path(self.temp_dir) / "nested"
        subdir.mkdir()
        test_file = subdir / "deep.txt"
        test_file.write_text("deep content")

        # Manager points to temp_dir, not subdir
        manager = DirectoryResourceManager(self.temp_dir)
        # Should not find file since it's looking in temp_dir, not nested/
        result = manager.get_path("deep.txt")
        self.assertIsNone(result)

    def test_multiple_files(self):
        """Test manager with multiple files in directory."""
        # Create multiple files
        file1 = Path(self.temp_dir) / "file1.txt"
        file2 = Path(self.temp_dir) / "file2.json"
        file3 = Path(self.temp_dir) / "file3.yaml"
        file1.write_text("content1")
        file2.write_text("content2")
        file3.write_text("content3")

        manager = DirectoryResourceManager(self.temp_dir)

        self.assertTrue(manager.file_exists("file1.txt"))
        self.assertTrue(manager.file_exists("file2.json"))
        self.assertTrue(manager.file_exists("file3.yaml"))
        self.assertFalse(manager.file_exists("file4.txt"))

    def test_get_filename_with_special_characters(self):
        """Test get_filename with special characters in path."""
        manager = DirectoryResourceManager(self.temp_dir)
        result = manager.get_filename("/path/to/file-with_special.chars.txt")
        self.assertEqual(result, "file-with_special.chars.txt")

    def test_get_path_returns_string_type(self):
        """Test that get_path returns string type, not Path object."""
        test_file = Path(self.temp_dir) / "type_test.txt"
        test_file.write_text("test")

        manager = DirectoryResourceManager(self.temp_dir)
        result = manager.get_path("type_test.txt")
        self.assertIsInstance(result, str)

    def test_directory_with_trailing_slash(self):
        """Test manager handles directory path with trailing slash."""
        dir_with_slash = self.temp_dir + "/"
        manager = DirectoryResourceManager(dir_with_slash)
        # Path should normalize this
        self.assertEqual(manager.directory, Path(self.temp_dir))


class TestGetLabelsManager(unittest.TestCase):
    """Test cases for get_labels_manager singleton function."""

    def test_get_labels_manager_returns_manager(self):
        """Test get_labels_manager returns DirectoryResourceManager instance."""
        manager = get_labels_manager()
        self.assertIsInstance(manager, DirectoryResourceManager)

    def test_get_labels_manager_uses_labels_path(self):
        """Test get_labels_manager uses LABELS_PATH constant."""
        manager = get_labels_manager()
        self.assertEqual(manager.directory, Path(LABELS_PATH))

    def test_get_labels_manager_multiple_calls(self):
        """Test multiple calls to get_labels_manager return the same instance."""
        manager1 = get_labels_manager()
        manager2 = get_labels_manager()
        # These should be the same instance (singleton pattern)
        self.assertIs(manager1, manager2)
        # And should have the same directory
        self.assertEqual(manager1.directory, manager2.directory)


class TestGetScriptsManager(unittest.TestCase):
    """Test cases for get_scripts_manager singleton function."""

    def test_get_scripts_manager_returns_manager(self):
        """Test get_scripts_manager returns DirectoryResourceManager instance."""
        manager = get_scripts_manager()
        self.assertIsInstance(manager, DirectoryResourceManager)

    def test_get_scripts_manager_uses_scripts_path(self):
        """Test get_scripts_manager uses SCRIPTS_PATH constant."""
        manager = get_scripts_manager()
        self.assertEqual(manager.directory, Path(SCRIPTS_PATH))

    def test_get_scripts_manager_multiple_calls(self):
        """Test multiple calls to get_scripts_manager return the same instance."""
        manager1 = get_scripts_manager()
        manager2 = get_scripts_manager()
        # These should be the same instance (singleton pattern)
        self.assertIs(manager1, manager2)
        # And should have the same directory
        self.assertEqual(manager1.directory, manager2.directory)


if __name__ == "__main__":
    unittest.main()
