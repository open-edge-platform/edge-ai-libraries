# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import io
import pathlib
import shutil
from http import HTTPStatus

from fastapi import UploadFile
from requests.exceptions import HTTPError

from src.common import Settings
from src.core.utils.config_utils import get_config as read_config
from src.core.utils.metadata_utils import store_enhanced_video_metadata
from src.core.utils.file_utils import save_video_to_temp as store_videos_to_temp


def mock_upload_and_write_temp_file(mocker):
    mock_response_json_datastore = {
        "status": "success",
        "bucket_name": "bucket",
        "files": ["file1.mp4", "file2.mp4"],
    }
    store_video_metadata_res = ("", {})

    # Mocking Datastore REST API by mocking POST request
    mock_res_datastore = mocker.MagicMock()
    mock_res_datastore.json.return_value = mock_response_json_datastore
    mock_res_datastore.raise_for_status.return_value = None
    mocker.patch("requests.post", return_value=mock_res_datastore)

    # Mocking methods which impact the filesystem - like saving video and meatadat in temp
    mocker.patch("src.app.store_videos_to_temp", return_value=None)
    mocker.patch("src.app.store_video_metadata", return_value=store_video_metadata_res)
    mocker.patch("src.core.db.read_config", return_value={})


def test_prep_data_endpoint(test_client, video_file, mocker):
    mock_upload_and_write_temp_file(mocker)

    mock_db = mocker.MagicMock()
    mock_db.create_embeddings.return_value = None
    mocker.patch("src.app.VDMSClient", return_value=mock_db)

    response = test_client.post("/videos", files=video_file)
    assert response.status_code == HTTPStatus.CREATED


def test_prep_data_invalid_video_file(test_client, invalid_video_file, mocker):
    mock_upload_and_write_temp_file(mocker)
    response = test_client.post("/videos", files=invalid_video_file)
    assert response.status_code == HTTPStatus.BAD_REQUEST


def test_prep_data_error_from_datastore(test_client, video_file, mocker):
    mock_response = {"status": "error"}

    mock_datastore = mocker.MagicMock()
    mock_datastore.json.return_value = mock_response
    mock_datastore.raise_for_status.side_effect = HTTPError
    mocker.patch("requests.post", return_value=mock_datastore)

    response = test_client.post("/videos", files=video_file)
    assert response.status_code == HTTPStatus.BAD_GATEWAY


def test_prep_data_internal_error(test_client, video_file, mocker):
    mock_response = {"status": "error"}

    mock_datastore = mocker.MagicMock()
    mock_datastore.json.return_value = mock_response
    mock_datastore.raise_for_status.side_effect = NameError
    mocker.patch("requests.post", return_value=mock_datastore)

    response = test_client.post("/videos", files=video_file)
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


def test_store_videos_to_temp(tmp_path, mocker):
    mock_open = mocker.mock_open()
    mocker.patch("builtins.open", mock_open)
    filename = "sample-video.mp4"

    video_file = io.BytesIO(b"binary content")
    mock_videofile = UploadFile(file=video_file)
    mocker.patch("shutil.copyfileobj")

    store_videos_to_temp(mock_videofile, filename, tmp_path)

    file_full_path = tmp_path / filename
    mock_open.assert_called_once_with(file_full_path, "wb")
    shutil.copyfileobj.assert_called_once_with(mock_videofile.file, mock_open())


def test_store_enhanced_video_metadata(mocker, tmp_path):
    """Test store_enhanced_video_metadata function (current implementation)."""

    mock_config = {
        "metadata_local_temp_dir": str(tmp_path),
    }
    mock_metadata = {"video_name": {"fps": 20, "total_frames": 10}}

    frame_interval = 15
    enable_object_detection = True
    detection_confidence = 0.85

    mock_open = mocker.mock_open()
    mocker.patch("builtins.open", mock_open)
    mock_extract = mocker.MagicMock()
    mock_extract.return_value = mock_metadata
    mocker.patch(
        "src.core.utils.metadata_utils.extract_enhanced_video_metadata",
        return_value=mock_metadata,
    )
    mocker.patch("pathlib.Path.mkdir")

    metadata_file = tmp_path / Settings().METADATA_FILENAME

    # Assert that result is a path and path matches the metadata_file
    result = store_enhanced_video_metadata(
        bucket_name="test-bucket",
        video_id="test-video",
        video_filename="test.mp4",
        temp_video_path=pathlib.Path("/tmp/test.mp4"),
        metadata_temp_path=str(tmp_path),
        frame_interval=frame_interval,
        enable_object_detection=enable_object_detection,
        detection_confidence=detection_confidence,
        tags=[]
    )
    assert type(result) is pathlib.PosixPath
    assert result == metadata_file

    pathlib.Path.mkdir.assert_called_once()
    mock_open.assert_called_with(metadata_file, "w")


def test_read_config(tmp_path, mocker):
    mock_open = mocker.mock_open()
    mocker.patch("builtins.open", mock_open)
    mocker.patch("yaml.safe_load", return_value={})
    mocker.patch("json.load", return_value={})

    assert type(read_config(tmp_path, type="yaml")) is dict
    mock_open.assert_called_once_with(tmp_path.absolute(), "r")
    assert type(read_config(tmp_path, type="json")) is dict
