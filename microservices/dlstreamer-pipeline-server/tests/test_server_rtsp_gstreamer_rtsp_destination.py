#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

from collections import namedtuple

import pytest
from unittest.mock import MagicMock, patch
from src.server.rtsp.gstreamer_rtsp_destination import GStreamerRtspDestination
from src.server.rtsp.gstreamer_rtsp_server import Stream

EncodingRequestCase = namedtuple(
    "EncodingRequestCase", ["encoding_value", "expected_encoding", "expect_warning"]
)

@pytest.fixture
def mock_pipeline():
    return MagicMock()

@pytest.fixture
def Gst(mocker):
    return mocker.patch('src.server.rtsp.gstreamer_rtsp_destination.Gst')

@pytest.fixture
def mock_request():
    return {
                "cache-length": 30,
                "sync-with-source": True,
                "sync-with-destination": True,
                "encode-quality": 10,
                "overlay": True
            }

@pytest.fixture
def gstreamer_rtsp_destination(mock_request, mock_pipeline,mocker,Gst):
    mocker.patch('src.server.rtsp.gstreamer_rtsp_destination.AppDestination')
    return GStreamerRtspDestination(mock_request, mock_pipeline)

class TestGStreamerRtspDestination:
    def test_init(self, mock_request, mock_pipeline, Gst,gstreamer_rtsp_destination):
        assert gstreamer_rtsp_destination._pipeline == mock_pipeline
        assert gstreamer_rtsp_destination._rtsp_path == mock_pipeline.rtsp_path
        assert gstreamer_rtsp_destination._identifier == mock_pipeline.identifier
        assert gstreamer_rtsp_destination._clock == Gst.SystemClock()

    def test_get_request_parameters(self, gstreamer_rtsp_destination, mock_request):
        gstreamer_rtsp_destination._get_request_parameters(mock_request)
        assert gstreamer_rtsp_destination._cache_length == 30
        assert gstreamer_rtsp_destination._sync_with_source is True
        assert gstreamer_rtsp_destination._sync_with_destination is True
        assert gstreamer_rtsp_destination._encode_quality == 10
        assert gstreamer_rtsp_destination.overlay is True
        assert gstreamer_rtsp_destination.encoding == "mjpeg"

    @pytest.mark.parametrize(
        "case",
        [
            EncodingRequestCase("h264", "h264", False),
            EncodingRequestCase("H264", "h264", False),
            EncodingRequestCase("mjpeg", "mjpeg", False),
            EncodingRequestCase(None, "mjpeg", False),
            EncodingRequestCase("unsupported-codec", "mjpeg", True),
        ],
        ids=["h264", "h264_uppercase", "mjpeg", "encoding_absent", "unsupported_falls_back"],
    )
    def test_get_request_parameters_encoding(self, request, mocker, case):
        """_get_request_parameters must normalize/validate the 'encoding'
        field, falling back to 'mjpeg' with a warning for unsupported values."""
        destination = request.getfixturevalue("gstreamer_rtsp_destination")
        base_request = request.getfixturevalue("mock_request")
        mock_warning = mocker.patch.object(getattr(destination, '_logger'), 'warning')
        req = dict(base_request)
        if case.encoding_value is not None:
            req["encoding"] = case.encoding_value
        getattr(destination, '_get_request_parameters')(req)
        assert destination.encoding == case.expected_encoding
        if case.expect_warning:
            mock_warning.assert_called_once()
        else:
            mock_warning.assert_not_called()

    def test_init_stream(self, gstreamer_rtsp_destination, mock_pipeline):
        mock_sample = MagicMock()
        mock_buffer = MagicMock()
        mock_sample.get_buffer.return_value = mock_buffer
        mock_buffer.get_size.return_value = 1000
        mock_caps = MagicMock()
        mock_sample.get_caps.return_value = mock_caps
        mock_clock = MagicMock()
        gstreamer_rtsp_destination._clock = mock_clock
        mock_clock.get_time.return_value = 500
        gstreamer_rtsp_destination._init_stream(mock_sample)
        assert gstreamer_rtsp_destination._frame_size == 1000
        assert gstreamer_rtsp_destination._need_data is False
        mock_pipeline.rtsp_server.add_stream.assert_called_once_with(
            mock_pipeline.identifier, mock_pipeline.rtsp_path,
            Stream(
                gstreamer_rtsp_destination, mock_caps,
                gstreamer_rtsp_destination.overlay,
                gstreamer_rtsp_destination.overlay_properties,
                gstreamer_rtsp_destination.encoding
            )
        )
        assert gstreamer_rtsp_destination._last_timestamp == 500
        mock_pipeline.appsink_element.set_property.assert_called_once_with("sync", True)

    def test_on_need_data(self, gstreamer_rtsp_destination):
        gstreamer_rtsp_destination.on_need_data(None, None)
        assert gstreamer_rtsp_destination._need_data is True

    def test_on_enough_data(self, gstreamer_rtsp_destination):
        gstreamer_rtsp_destination.on_enough_data(None)
        assert gstreamer_rtsp_destination._need_data is False

    def test_set_app_src(self, gstreamer_rtsp_destination, mock_pipeline):
        mock_app_src = MagicMock()
        mock_rtsp_pipeline = MagicMock()
        mock_encoder = MagicMock()
        mock_rtsp_pipeline.get_by_name.return_value = mock_encoder
        gstreamer_rtsp_destination._frame_size = 1000
        gstreamer_rtsp_destination.set_app_src(mock_app_src, False, mock_rtsp_pipeline)
        assert gstreamer_rtsp_destination._app_src == mock_app_src
        assert gstreamer_rtsp_destination._is_audio_pipeline is False
        assert gstreamer_rtsp_destination._pts == 0
        mock_app_src.set_property.assert_any_call("is-live", True)
        mock_app_src.set_property.assert_any_call("do-timestamp", True)
        mock_app_src.set_property.assert_any_call("blocksize", 1000)
        mock_app_src.set_property.assert_any_call("block", True)
        mock_app_src.set_property.assert_any_call("min-percent", 100)
        mock_app_src.set_property.assert_any_call("max-bytes", 30000)
        mock_encoder.set_property.assert_called_once_with("quality", 10)
        mock_rtsp_pipeline.get_by_name.assert_any_call("jpegencoder")
        mock_rtsp_pipeline.get_by_name.assert_any_call("h264encoder")

    def test_set_app_src_h264_openh264enc_sets_bitrate(self, request):
        """set_app_src must apply the configured bitrate when the active
        H.264 encoder element is the software openh264enc."""
        destination = request.getfixturevalue("gstreamer_rtsp_destination")
        mock_app_src = MagicMock()
        mock_rtsp_pipeline = MagicMock()
        h264_encoder = MagicMock()
        h264_encoder.get_factory.return_value.get_name.return_value = "openh264enc"

        def get_by_name(name):
            return h264_encoder if name == "h264encoder" else None
        mock_rtsp_pipeline.get_by_name.side_effect = get_by_name
        setattr(destination, '_frame_size', 1000)
        setattr(destination, '_encode_bitrate', 2000000)
        destination.set_app_src(mock_app_src, False, mock_rtsp_pipeline)
        h264_encoder.set_property.assert_called_once_with("bitrate", 2000000)

    def test_set_app_src_h264_vah264enc_skips_bitrate(self, request):
        """set_app_src must NOT force a bitrate on the VA-API h264 encoder,
        since vah264enc manages bitrate/quality via its own rate-control."""
        destination = request.getfixturevalue("gstreamer_rtsp_destination")
        mock_app_src = MagicMock()
        mock_rtsp_pipeline = MagicMock()
        h264_encoder = MagicMock()
        h264_encoder.get_factory.return_value.get_name.return_value = "vah264enc"

        def get_by_name(name):
            return h264_encoder if name == "h264encoder" else None
        mock_rtsp_pipeline.get_by_name.side_effect = get_by_name
        setattr(destination, '_frame_size', 1000)
        setattr(destination, '_encode_bitrate', 2000000)
        destination.set_app_src(mock_app_src, False, mock_rtsp_pipeline)
        h264_encoder = mock_rtsp_pipeline.get_by_name("h264encoder")
        h264_encoder.set_property.assert_not_called()

    def test_push_buffer(self, gstreamer_rtsp_destination, mock_pipeline,Gst,mocker):
        mock_buffer = MagicMock()
        mock_clock = MagicMock()
        gstreamer_rtsp_destination._clock = mock_clock
        mock_clock.get_time.return_value = 2000
        gstreamer_rtsp_destination._last_timestamp = 500
        gstreamer_rtsp_destination._pts = 0
        mock_app_src = MagicMock()
        gstreamer_rtsp_destination._app_src = mock_app_src
        mock_end_stream = mocker.patch.object(gstreamer_rtsp_destination,'_end_stream')
        gstreamer_rtsp_destination._push_buffer(mock_buffer)
        assert mock_buffer.pts == 0
        assert mock_buffer.dts == 0
        assert mock_buffer.duration == 1500
        assert gstreamer_rtsp_destination._pts == 1500
        assert gstreamer_rtsp_destination._last_timestamp == 2000
        mock_app_src.emit.assert_called_once_with('push-buffer', mock_buffer)
        mock_end_stream.assert_called_once()

    def test_process_frame(self, gstreamer_rtsp_destination, mock_pipeline):
        mock_frame = MagicMock()
        mock_init = MagicMock()
        mock_process_frame = MagicMock()
        gstreamer_rtsp_destination._init_stream = mock_init
        gstreamer_rtsp_destination._process_frame = mock_process_frame
        gstreamer_rtsp_destination.process_frame(mock_frame)
        mock_init.assert_called_once_with(mock_frame)
        mock_process_frame.assert_called_once_with(mock_frame)

    def test_process_frame_after_init(self, gstreamer_rtsp_destination, mock_pipeline):
        mock_frame = MagicMock()
        mock_buffer = MagicMock()
        mock_clock = MagicMock()
        gstreamer_rtsp_destination._clock = mock_clock
        mock_clock.get_time.return_value = 10000
        mock_frame.get_buffer.return_value = mock_buffer
        gstreamer_rtsp_destination._need_data = True
        gstreamer_rtsp_destination._push_buffer = MagicMock()
        gstreamer_rtsp_destination._process_frame(mock_frame)
        gstreamer_rtsp_destination._push_buffer.assert_called_once_with(mock_buffer)
        gstreamer_rtsp_destination._need_data = False
        gstreamer_rtsp_destination._process_frame(mock_frame)
        mock_clock.get_time.assert_called_once()
        gstreamer_rtsp_destination._last_timestamp = 10000

    def test_end_stream(self, gstreamer_rtsp_destination):
        mock_app_src = MagicMock()
        gstreamer_rtsp_destination._app_src = mock_app_src
        gstreamer_rtsp_destination._end_stream()
        assert gstreamer_rtsp_destination._need_data is False
        if mock_app_src is not None:
            mock_app_src.end_of_stream.assert_called_once()
        assert gstreamer_rtsp_destination._app_src is None

    def test_finish(self, gstreamer_rtsp_destination,mocker):
        mock_rtsp_server = MagicMock()
        gstreamer_rtsp_destination._rtsp_server = mock_rtsp_server
        mock_end_stream = mocker.patch.object(gstreamer_rtsp_destination,'_end_stream')
        gstreamer_rtsp_destination.finish()
        mock_end_stream.assert_called_once()
        mock_rtsp_server.remove_stream.assert_called_once_with(gstreamer_rtsp_destination._rtsp_path)


class TestMediaLifecycle:
    """The destination outlives its media pipelines: a client leaving tears one down, the next client creates another.

    After 12-20 hours of relay reconnects a stream stayed dead (every DESCRIBE failed with "can't prepare media" and the
    pipeline had logged "'NoneType' object has no attribute 'emit'") because the signals and the teardown of an older
    media overwrote the state of the newer one.
    """

    @staticmethod
    def _media(destination):
        app_src, pipeline = MagicMock(), MagicMock()
        pipeline.get_by_name.return_value = None
        destination._frame_size = 1000
        destination.set_app_src(app_src, False, pipeline)
        return app_src

    def test_late_signals_of_an_older_media_are_ignored(self, gstreamer_rtsp_destination):
        old = self._media(gstreamer_rtsp_destination)
        new = self._media(gstreamer_rtsp_destination)
        gstreamer_rtsp_destination.on_need_data(old, 1000)
        assert gstreamer_rtsp_destination._need_data is False
        gstreamer_rtsp_destination.on_need_data(new, 1000)
        assert gstreamer_rtsp_destination._need_data is True
        gstreamer_rtsp_destination.on_enough_data(old)
        assert gstreamer_rtsp_destination._need_data is True
        gstreamer_rtsp_destination.on_enough_data(new)
        assert gstreamer_rtsp_destination._need_data is False

    def test_a_new_media_starts_without_the_need_data_of_the_previous_one(self, gstreamer_rtsp_destination):
        self._media(gstreamer_rtsp_destination)
        gstreamer_rtsp_destination._need_data = True
        self._media(gstreamer_rtsp_destination)
        assert gstreamer_rtsp_destination._need_data is False

    def test_ending_an_older_media_keeps_the_current_one(self, gstreamer_rtsp_destination):
        old = self._media(gstreamer_rtsp_destination)
        new = self._media(gstreamer_rtsp_destination)
        gstreamer_rtsp_destination._need_data = True
        gstreamer_rtsp_destination._end_stream(old)
        old.end_of_stream.assert_called_once()
        new.end_of_stream.assert_not_called()
        assert gstreamer_rtsp_destination._app_src is new
        assert gstreamer_rtsp_destination._need_data is True

    def test_a_failed_push_to_an_older_media_does_not_end_the_new_one(self, gstreamer_rtsp_destination, Gst):
        old = self._media(gstreamer_rtsp_destination)
        gstreamer_rtsp_destination._need_data = True
        new = MagicMock()

        def replaced_while_pushing(*_):                    # the next media is set up while the push to the old one runs
            gstreamer_rtsp_destination.set_app_src(new, False, MagicMock(**{"get_by_name.return_value": None}))
            return "flushing"
        old.emit.side_effect = replaced_while_pushing
        gstreamer_rtsp_destination._push_buffer(MagicMock())
        old.end_of_stream.assert_called_once()
        new.end_of_stream.assert_not_called()
        assert gstreamer_rtsp_destination._app_src is new

    def test_a_push_without_a_current_media_does_nothing(self, gstreamer_rtsp_destination):
        gstreamer_rtsp_destination._app_src = None
        gstreamer_rtsp_destination._need_data = True       # the signal of a media that ended just before
        gstreamer_rtsp_destination._pts = 123
        buffer = MagicMock()
        gstreamer_rtsp_destination._push_buffer(buffer)    # used to raise 'NoneType' object has no attribute 'emit'
        assert gstreamer_rtsp_destination._pts == 123

    def test_ending_the_stream_twice_is_harmless(self, gstreamer_rtsp_destination):
        media = self._media(gstreamer_rtsp_destination)
        gstreamer_rtsp_destination._end_stream()
        gstreamer_rtsp_destination._end_stream()
        media.end_of_stream.assert_called_once()

    def test_media_coming_and_going_while_frames_are_pushed(self, gstreamer_rtsp_destination, Gst):
        """Frames, signals, new media and teardowns at the same time never raise and always end on a usable state."""
        import threading
        import time
        Gst.FlowReturn.OK = "ok"
        errors, stop = [], threading.Event()
        gstreamer_rtsp_destination._clock = MagicMock(get_time=MagicMock(return_value=1))

        def guarded(fn):
            def run():
                while not stop.is_set():
                    try:
                        fn()
                    except Exception as exc:                # pylint: disable=broad-except
                        errors.append(repr(exc))
                        return
            return threading.Thread(target=run, daemon=True)

        media = []

        def new_media():
            app_src = MagicMock()
            app_src.emit.return_value = "ok"
            media.append(app_src)
            self._media_set(gstreamer_rtsp_destination, app_src)
            gstreamer_rtsp_destination.on_need_data(app_src, 1)

        def end_media():
            if media:
                gstreamer_rtsp_destination._end_stream(media[0] if len(media) > 1 else None)
                time.sleep(0.0005)

        def late_signals():
            if media:
                gstreamer_rtsp_destination.on_need_data(media[0], 1)
                gstreamer_rtsp_destination.on_enough_data(media[0])

        def frames():
            if gstreamer_rtsp_destination._need_data:
                gstreamer_rtsp_destination._push_buffer(MagicMock())

        threads = [guarded(f) for f in (new_media, end_media, late_signals, frames, frames)]
        for thread in threads:
            thread.start()
        time.sleep(0.4)
        stop.set()
        for thread in threads:
            thread.join(2)
        assert not errors, errors
        self._media_set(gstreamer_rtsp_destination, MagicMock())
        gstreamer_rtsp_destination.on_need_data(gstreamer_rtsp_destination._app_src, 1)
        assert gstreamer_rtsp_destination._need_data is True    # a media created afterwards works

    @staticmethod
    def _media_set(destination, app_src):
        pipeline = MagicMock()
        pipeline.get_by_name.return_value = None
        destination._frame_size = 1000
        destination.set_app_src(app_src, False, pipeline)
