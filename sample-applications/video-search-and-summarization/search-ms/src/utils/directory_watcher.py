# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
import os
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from threading import Timer, Thread, Lock
from src.utils.common import settings, logger
from src.utils.utils import upload_videos_to_dataprep

initial_upload_status = {"total": 0, "completed": 0, "pending": 0}


class DebouncedHandler(FileSystemEventHandler):
    last_updated = None  # Class-level attribute
    lock = Lock()  # Lock for thread safety

    def __init__(self, debounce_time, action):
        self.debounce_time = debounce_time
        self.action = action
        self.timer = None
        self.file_paths = set()
        self.first_event_time = None

    def on_created(self, event):
        if event.src_path.endswith(".mp4") and os.path.getsize(event.src_path) > 524288:
            with self.lock:
                self.file_paths.add(event.src_path)
            self._debounce()

    def on_modified(self, event):
        if event.src_path.endswith(".mp4") and os.path.getsize(event.src_path) > 524288:
            with self.lock:
                self.file_paths.add(event.src_path)
            self._debounce()

    def _debounce(self):
        if self.first_event_time is None:
            self.first_event_time = datetime.now()
            self.timer = Timer(self.debounce_time, self._process_files)
            self.timer.start()
        else:
            elapsed_time = (datetime.now() - self.first_event_time).total_seconds()
            if elapsed_time >= self.debounce_time:
                self._process_files()

    def _process_files(self):
        def run_action():
            global initial_upload_status
            try:
                with self.lock:
                    initial_upload_status["total"] += len(self.file_paths)
                    initial_upload_status["pending"] += len(self.file_paths)
                    self.action(self.file_paths)
                    initial_upload_status["completed"] += len(self.file_paths)
                    initial_upload_status["pending"] -= len(self.file_paths)
                    self.file_paths.clear()
                    self.first_event_time = None
            except Exception as e:
                logger.error(f"Error in _process_files: {str(e)}")
            finally:
                DebouncedHandler.last_updated = datetime.now()
                logger.info(f"Last updated time set to {DebouncedHandler.last_updated}")

        action_thread = Thread(target=run_action)
        action_thread.start()


def upload_initial_videos(path):
    global initial_upload_status
    logger.debug(f"Starting initial upload of videos from {path}")
    
    video_files = []
    if settings.WATCH_DIRECTORY_RECURSIVE:
        # Recursively find all MP4 files in subdirectories
        for root, dirs, files in os.walk(path):
            for f in files:
                if f.endswith(".mp4"):
                    file_path = os.path.join(root, f)
                    if os.path.getsize(file_path) > 524288:
                        video_files.append(file_path)
        logger.debug(f"Recursive scan found {len(video_files)} video files for initial upload")
    else:
        # Only scan the top-level directory
        video_files = [
            os.path.join(path, f)
            for f in os.listdir(path)
            if f.endswith(".mp4") and os.path.getsize(os.path.join(path, f)) > 524288
        ]
        logger.debug(f"Top-level scan found {len(video_files)} video files for initial upload")
    
    initial_upload_status["total"] = len(video_files)
    initial_upload_status["pending"] = len(video_files)

    def upload_batch(batch):
        global initial_upload_status
        try:
            logger.debug(f"Uploading batch of {len(batch)} videos: {batch}")
            success = upload_videos_to_dataprep(batch)
            if success:
                initial_upload_status["completed"] += len(batch)
                initial_upload_status["pending"] -= len(batch)
                logger.debug(
                    f"Batch upload complete. Completed: {initial_upload_status['completed']}, Pending: {initial_upload_status['pending']}"
                )
                if settings.DELETE_PROCESSED_FILES:
                    for file_path in batch:
                        os.remove(file_path)
                        logger.info(f"Deleted processed file {file_path}")
            else:
                logger.error(f"Batch upload failed for batch: {batch}")
        except Exception as e:
            logger.error(f"Error in upload_batch: {str(e)}")

    for i in range(0, len(video_files), 10):
        batch = video_files[i : i + 10]
        batch_thread = Thread(target=upload_batch, args=(batch,))
        batch_thread.start()
        logger.debug(f"Started thread for batch {i//10 + 1}")


def start_watcher():
    if not settings.WATCH_DIRECTORY:
        logger.error("WATCH_DIRECTORY is not set in settings.")
        return
    path = settings.WATCH_DIRECTORY_CONTAINER_PATH
    if not os.path.exists(path):
        os.makedirs(path)
    debounce_time = settings.DEBOUNCE_TIME

    if settings.VS_INITIAL_DUMP:
        initial_upload_thread = Thread(target=upload_initial_videos, args=(path,))
        initial_upload_thread.start()
        logger.debug("Started initial upload thread")

    event_handler = DebouncedHandler(debounce_time, upload_videos_to_dataprep)
    observer = Observer()
    recursive = settings.WATCH_DIRECTORY_RECURSIVE
    observer.schedule(event_handler, path, recursive=recursive)
    observer.start()
    logger.info(
        f"Started directory watcher on {path} with debounce time of {debounce_time} seconds. Recursive: {recursive}"
    )

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


def get_initial_upload_status():
    return initial_upload_status


def get_last_updated():
    return DebouncedHandler.last_updated
