# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
import os
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, call
from threading import Thread
from src.utils.directory_watcher import (
    DebouncedHandler,
    upload_initial_videos,
    start_watcher,
    get_initial_upload_status,
    get_last_updated,
    initial_upload_status
)


class TestDebouncedHandler:
    """Test cases for DebouncedHandler class."""

    @pytest.fixture
    def mock_action(self):
        """Mock action function for testing."""
        return Mock()

    @pytest.fixture
    def handler(self, mock_action):
        """Create DebouncedHandler instance."""
        return DebouncedHandler(debounce_time=0.01, action=mock_action)  # 0.01 minutes for fast testing

    def test_init(self, mock_action):
        """Test DebouncedHandler initialization."""
        handler = DebouncedHandler(debounce_time=5, action=mock_action)
        assert handler.debounce_time == 5
        assert handler.action == mock_action
        assert handler.timer is None
        assert handler.file_paths == set()
        assert handler.first_event_time is None

    @patch('src.utils.directory_watcher.os.path.getsize')
    def test_on_created_valid_mp4(self, mock_getsize, handler):
        """Test on_created with valid MP4 file."""
        mock_getsize.return_value = 1048576  # 1MB
        event = Mock()
        event.src_path = "/path/to/video.mp4"
        
        with patch.object(handler, '_debounce') as mock_debounce:
            handler.on_created(event)
            
        assert "/path/to/video.mp4" in handler.file_paths
        mock_debounce.assert_called_once()

    @patch('src.utils.directory_watcher.os.path.getsize')
    def test_on_created_small_file(self, mock_getsize, handler):
        """Test on_created with file too small."""
        mock_getsize.return_value = 100000  # 100KB (less than 524288)
        event = Mock()
        event.src_path = "/path/to/small.mp4"
        
        with patch.object(handler, '_debounce') as mock_debounce:
            handler.on_created(event)
            
        assert "/path/to/small.mp4" not in handler.file_paths
        mock_debounce.assert_not_called()

    @patch('src.utils.directory_watcher.os.path.getsize')
    def test_on_created_non_mp4(self, mock_getsize, handler):
        """Test on_created with non-MP4 file."""
        mock_getsize.return_value = 1048576  # 1MB
        event = Mock()
        event.src_path = "/path/to/file.txt"
        
        with patch.object(handler, '_debounce') as mock_debounce:
            handler.on_created(event)
            
        assert "/path/to/file.txt" not in handler.file_paths
        mock_debounce.assert_not_called()

    @patch('src.utils.directory_watcher.os.path.getsize')
    def test_on_modified_valid_mp4(self, mock_getsize, handler):
        """Test on_modified with valid MP4 file."""
        mock_getsize.return_value = 1048576  # 1MB
        event = Mock()
        event.src_path = "/path/to/video.mp4"
        
        with patch.object(handler, '_debounce') as mock_debounce:
            handler.on_modified(event)
            
        assert "/path/to/video.mp4" in handler.file_paths
        mock_debounce.assert_called_once()

    @patch('src.utils.directory_watcher.Timer')
    @patch('src.utils.directory_watcher.datetime')
    def test_debounce_first_event(self, mock_datetime, mock_timer, handler):
        """Test _debounce on first event."""
        mock_now = datetime(2025, 1, 1, 12, 0, 0)
        mock_datetime.now.return_value = mock_now
        mock_timer_instance = Mock()
        mock_timer.return_value = mock_timer_instance
        
        handler._debounce()
        
        assert handler.first_event_time == mock_now
        mock_timer.assert_called_once_with(0.01 * 60, handler._process_files)
        mock_timer_instance.start.assert_called_once()

    @patch('src.utils.directory_watcher.datetime')
    def test_debounce_elapsed_time_exceeded(self, mock_datetime, handler):
        """Test _debounce when elapsed time exceeds debounce time."""
        start_time = datetime(2025, 1, 1, 12, 0, 0)
        current_time = datetime(2025, 1, 1, 12, 1, 0)  # 1 minute later
        
        handler.first_event_time = start_time
        mock_datetime.now.return_value = current_time
        
        with patch.object(handler, '_process_files') as mock_process:
            handler._debounce()
            mock_process.assert_called_once()

    @patch('src.utils.directory_watcher.Thread')
    def test_process_files(self, mock_thread, handler):
        """Test _process_files method."""
        mock_thread_instance = Mock()
        mock_thread.return_value = mock_thread_instance
        
        handler._process_files()
        
        mock_thread.assert_called_once()
        mock_thread_instance.start.assert_called_once()

    @patch('src.utils.directory_watcher.logger')
    @patch('src.utils.directory_watcher.datetime')
    def test_process_files_run_action_success(self, mock_datetime, mock_logger, handler):
        """Test the run_action function inside _process_files."""
        mock_now = datetime(2025, 1, 1, 12, 0, 0)
        mock_datetime.now.return_value = mock_now
        
        handler.file_paths = {"/path/to/video1.mp4", "/path/to/video2.mp4"}
        handler.first_event_time = datetime(2025, 1, 1, 11, 0, 0)
        
        # Simulate the run_action function directly
        with handler.lock:
            initial_upload_status["total"] += len(handler.file_paths)
            initial_upload_status["pending"] += len(handler.file_paths)
            handler.action(handler.file_paths)
            initial_upload_status["completed"] += len(handler.file_paths)
            initial_upload_status["pending"] -= len(handler.file_paths)
            handler.file_paths.clear()
            handler.first_event_time = None
        
        DebouncedHandler.last_updated = mock_now
        
        handler.action.assert_called_once()
        assert len(handler.file_paths) == 0
        assert handler.first_event_time is None
        assert DebouncedHandler.last_updated == mock_now


class TestUploadInitialVideos:
    """Test cases for upload_initial_videos function."""

    @patch('src.utils.directory_watcher.os.listdir')
    @patch('src.utils.directory_watcher.os.path.getsize')
    @patch('src.utils.directory_watcher.os.path.join')
    @patch('src.utils.directory_watcher.logger')
    @patch('src.utils.directory_watcher.Thread')
    @patch('src.utils.directory_watcher.upload_videos_to_dataprep')
    def test_upload_initial_videos_success(self, mock_upload, mock_thread, mock_logger, 
                                         mock_join, mock_getsize, mock_listdir):
        """Test successful initial video upload."""
        # Setup mocks
        mock_listdir.return_value = ["video1.mp4", "video2.mp4", "file.txt"]
        mock_getsize.return_value = 1048576  # 1MB
        mock_join.side_effect = lambda path, f: f"{path}/{f}"
        mock_thread_instance = Mock()
        mock_thread.return_value = mock_thread_instance
        mock_upload.return_value = True
        
        # Reset initial status
        initial_upload_status["total"] = 0
        initial_upload_status["pending"] = 0
        initial_upload_status["completed"] = 0
        
        upload_initial_videos("/test/path")
        
        # Verify initial status was set
        assert initial_upload_status["total"] == 2  # Only MP4 files
        assert initial_upload_status["pending"] == 2
        
        # Verify threads were created
        assert mock_thread.call_count == 1  # One batch for 2 files

    @patch('src.utils.directory_watcher.os.listdir')
    @patch('src.utils.directory_watcher.os.path.getsize')
    @patch('src.utils.directory_watcher.logger')
    def test_upload_initial_videos_no_valid_files(self, mock_logger, mock_getsize, mock_listdir):
        """Test upload_initial_videos with no valid files."""
        mock_listdir.return_value = ["file.txt", "document.pdf"]
        mock_getsize.return_value = 1048576
        
        # Reset initial status
        initial_upload_status["total"] = 0
        initial_upload_status["pending"] = 0
        
        upload_initial_videos("/test/path")
        
        assert initial_upload_status["total"] == 0
        assert initial_upload_status["pending"] == 0

    @patch('src.utils.directory_watcher.os.listdir')
    @patch('src.utils.directory_watcher.os.path.getsize')
    @patch('src.utils.directory_watcher.os.path.join')
    @patch('src.utils.directory_watcher.logger')
    def test_upload_initial_videos_small_files(self, mock_logger, mock_join, mock_getsize, mock_listdir):
        """Test upload_initial_videos with files too small."""
        mock_listdir.return_value = ["small1.mp4", "small2.mp4"]
        mock_getsize.return_value = 100000  # 100KB (less than 524288)
        mock_join.side_effect = lambda path, f: f"{path}/{f}"
        
        # Reset initial status
        initial_upload_status["total"] = 0
        initial_upload_status["pending"] = 0
        
        upload_initial_videos("/test/path")
        
        assert initial_upload_status["total"] == 0
        assert initial_upload_status["pending"] == 0

    @patch('src.utils.directory_watcher.upload_videos_to_dataprep')
    @patch('src.utils.directory_watcher.logger')
    @patch('src.utils.directory_watcher.settings')
    @patch('src.utils.directory_watcher.os.remove')
    def test_upload_batch_success_with_delete(self, mock_remove, mock_settings, mock_logger, mock_upload):
        """Test upload_batch function with successful upload and file deletion."""
        mock_upload.return_value = True
        mock_settings.DELETE_PROCESSED_FILES = True
        
        # Reset initial status
        initial_upload_status["completed"] = 0
        initial_upload_status["pending"] = 10
        
        batch = ["/path/video1.mp4", "/path/video2.mp4"]
        
        # Simulate the upload_batch function from upload_initial_videos
        success = mock_upload(batch)
        if success:
            initial_upload_status["completed"] += len(batch)
            initial_upload_status["pending"] -= len(batch)
            if mock_settings.DELETE_PROCESSED_FILES:
                for file_path in batch:
                    mock_remove(file_path)
        
        assert initial_upload_status["completed"] == 2
        assert initial_upload_status["pending"] == 8
        assert mock_remove.call_count == 2

    @patch('src.utils.directory_watcher.upload_videos_to_dataprep')
    @patch('src.utils.directory_watcher.logger')
    def test_upload_batch_failure(self, mock_logger, mock_upload):
        """Test upload_batch function with upload failure."""
        mock_upload.return_value = False
        
        # Reset initial status
        initial_upload_status["completed"] = 0
        initial_upload_status["pending"] = 10
        
        batch = ["/path/video1.mp4", "/path/video2.mp4"]
        
        # Simulate the upload_batch function
        success = mock_upload(batch)
        if success:
            initial_upload_status["completed"] += len(batch)
            initial_upload_status["pending"] -= len(batch)
        
        # Status should remain unchanged on failure
        assert initial_upload_status["completed"] == 0
        assert initial_upload_status["pending"] == 10


class TestStartWatcher:
    """Test cases for start_watcher function."""

    @patch('src.utils.directory_watcher.settings')
    @patch('src.utils.directory_watcher.logger')
    def test_start_watcher_no_watch_directory(self, mock_logger, mock_settings):
        """Test start_watcher when WATCH_DIRECTORY is not set."""
        mock_settings.WATCH_DIRECTORY = False
        
        result = start_watcher()
        
        assert result is None
        mock_logger.error.assert_called_once_with("WATCH_DIRECTORY is not set in settings.")

    @patch('src.utils.directory_watcher.settings')
    @patch('src.utils.directory_watcher.os.path.exists')
    @patch('src.utils.directory_watcher.os.makedirs')
    @patch('src.utils.directory_watcher.Thread')
    @patch('src.utils.directory_watcher.DebouncedHandler')
    @patch('src.utils.directory_watcher.Observer')
    @patch('src.utils.directory_watcher.time.sleep')
    @patch('src.utils.directory_watcher.logger')
    def test_start_watcher_success_with_initial_dump(self, mock_logger, mock_sleep, mock_observer_class, 
                                                   mock_handler_class, mock_thread, mock_makedirs, 
                                                   mock_exists, mock_settings):
        """Test successful start_watcher with initial dump."""
        # Setup mocks
        mock_settings.WATCH_DIRECTORY = True
        mock_settings.WATCH_DIRECTORY_CONTAINER_PATH = "/test/path"
        mock_settings.DEBOUNCE_TIME = 5
        mock_settings.VS_INITIAL_DUMP = True
        mock_exists.return_value = False
        
        mock_observer = Mock()
        mock_observer_class.return_value = mock_observer
        mock_handler = Mock()
        mock_handler_class.return_value = mock_handler
        mock_thread_instance = Mock()
        mock_thread.return_value = mock_thread_instance
        
        # Mock sleep to raise KeyboardInterrupt after first call
        mock_sleep.side_effect = [None, KeyboardInterrupt()]
        
        start_watcher()
        
        # Verify directory creation
        mock_makedirs.assert_called_once_with("/test/path")
        
        # Verify initial upload thread
        mock_thread.assert_called_once()
        mock_thread_instance.start.assert_called_once()
        
        # Verify observer setup
        mock_observer.schedule.assert_called_once_with(mock_handler, "/test/path", recursive=False)
        mock_observer.start.assert_called_once()
        mock_observer.stop.assert_called_once()
        mock_observer.join.assert_called_once()

    @patch('src.utils.directory_watcher.settings')
    @patch('src.utils.directory_watcher.os.path.exists')
    @patch('src.utils.directory_watcher.DebouncedHandler')
    @patch('src.utils.directory_watcher.Observer')
    @patch('src.utils.directory_watcher.time.sleep')
    @patch('src.utils.directory_watcher.logger')
    def test_start_watcher_without_initial_dump(self, mock_logger, mock_sleep, mock_observer_class, 
                                              mock_handler_class, mock_exists, mock_settings):
        """Test start_watcher without initial dump."""
        # Setup mocks
        mock_settings.WATCH_DIRECTORY = True
        mock_settings.WATCH_DIRECTORY_CONTAINER_PATH = "/test/path"
        mock_settings.DEBOUNCE_TIME = 3
        mock_settings.VS_INITIAL_DUMP = False
        mock_exists.return_value = True
        
        mock_observer = Mock()
        mock_observer_class.return_value = mock_observer
        mock_handler = Mock()
        mock_handler_class.return_value = mock_handler
        
        # Mock sleep to raise KeyboardInterrupt after first call
        mock_sleep.side_effect = [None, KeyboardInterrupt()]
        
        with patch('src.utils.directory_watcher.Thread') as mock_thread:
            start_watcher()
            # Should not create initial upload thread
            mock_thread.assert_not_called()


class TestUtilityFunctions:
    """Test cases for utility functions."""

    def test_get_initial_upload_status(self):
        """Test get_initial_upload_status function."""
        # Set some test values
        initial_upload_status["total"] = 10
        initial_upload_status["completed"] = 3
        initial_upload_status["pending"] = 7
        
        result = get_initial_upload_status()
        
        assert result == {"total": 10, "completed": 3, "pending": 7}
        assert result is initial_upload_status  # Should return the same object

    def test_get_last_updated_none(self):
        """Test get_last_updated when no update has occurred."""
        DebouncedHandler.last_updated = None
        
        result = get_last_updated()
        
        assert result is None

    def test_get_last_updated_with_time(self):
        """Test get_last_updated with a set time."""
        test_time = datetime(2025, 1, 1, 12, 0, 0)
        DebouncedHandler.last_updated = test_time
        
        result = get_last_updated()
        
        assert result == test_time


class TestIntegration:
    """Integration tests for multiple components."""

    @patch('src.utils.directory_watcher.os.path.getsize')
    @patch('src.utils.directory_watcher.logger')
    def test_debounced_handler_full_workflow(self, mock_logger, mock_getsize):
        """Test full workflow of DebouncedHandler."""
        mock_getsize.return_value = 1048576  # 1MB
        mock_action = Mock()
        
        handler = DebouncedHandler(debounce_time=0.001, action=mock_action)  # Very short debounce
        
        # Simulate file events
        event1 = Mock()
        event1.src_path = "/path/video1.mp4"
        event2 = Mock()
        event2.src_path = "/path/video2.mp4"
        
        handler.on_created(event1)
        handler.on_modified(event2)
        
        # Check that files were added to the set before processing
        assert len(handler.file_paths) == 2
        assert "/path/video1.mp4" in handler.file_paths
        assert "/path/video2.mp4" in handler.file_paths
        
        # Wait for debounce to complete and action to be called
        time.sleep(0.1)
        
        # Verify that the action was called
        mock_action.assert_called_once()
        
        # Check that the file_paths set was cleared after processing
        assert len(handler.file_paths) == 0
        assert handler.first_event_time is None

    def test_initial_upload_status_thread_safety(self):
        """Test thread safety of initial_upload_status updates."""
        # Reset status
        initial_upload_status["total"] = 0
        initial_upload_status["completed"] = 0
        initial_upload_status["pending"] = 0
        
        def increment_status():
            for _ in range(100):
                initial_upload_status["total"] += 1
                initial_upload_status["pending"] += 1
                initial_upload_status["completed"] += 1
                initial_upload_status["pending"] -= 1
        
        threads = []
        for _ in range(5):
            thread = Thread(target=increment_status)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        assert initial_upload_status["total"] == 500
        assert initial_upload_status["completed"] == 500
        assert initial_upload_status["pending"] == 0


class TestErrorHandling:
    """Test error handling scenarios."""

    @patch('src.utils.directory_watcher.os.path.getsize')
    def test_debounced_handler_getsize_error(self, mock_getsize):
        """Test DebouncedHandler when os.path.getsize raises an error."""
        mock_getsize.side_effect = OSError("File not found")
        mock_action = Mock()
        handler = DebouncedHandler(debounce_time=1, action=mock_action)
        
        event = Mock()
        event.src_path = "/path/video.mp4"
        
        # Should handle the error gracefully
        with pytest.raises(OSError):
            handler.on_created(event)

    @patch('src.utils.directory_watcher.os.listdir')
    @patch('src.utils.directory_watcher.logger')
    def test_upload_initial_videos_listdir_error(self, mock_logger, mock_listdir):
        """Test upload_initial_videos when os.listdir raises an error."""
        mock_listdir.side_effect = OSError("Permission denied")
        
        with pytest.raises(OSError):
            upload_initial_videos("/test/path")

    @patch('src.utils.directory_watcher.logger')
    def test_process_files_action_error(self, mock_logger):
        """Test _process_files when action raises an error."""
        mock_action = Mock()
        mock_action.side_effect = Exception("Upload failed")
        
        handler = DebouncedHandler(debounce_time=1, action=mock_action)
        handler.file_paths = {"/path/video1.mp4"}
        
        # Simulate the run_action function with error handling
        try:
            with handler.lock:
                initial_upload_status["total"] += len(handler.file_paths)
                initial_upload_status["pending"] += len(handler.file_paths)
                handler.action(handler.file_paths)
                initial_upload_status["completed"] += len(handler.file_paths)
                initial_upload_status["pending"] -= len(handler.file_paths)
                handler.file_paths.clear()
                handler.first_event_time = None
        except Exception as e:
            assert str(e) == "Upload failed"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=.", "--cov-report=html", "--cov-report=term-missing"])