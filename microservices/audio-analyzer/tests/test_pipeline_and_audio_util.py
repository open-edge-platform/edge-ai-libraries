import io
import json
import os
import tempfile
import unittest
from types import MethodType
from unittest.mock import patch

from pipeline import Pipeline
from utils import app_paths
from utils.audio_util import save_audio_file
from utils.session_manager import normalize_session_id, resolve_requested_session_id


class DummyUploadFile:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self.file = io.BytesIO(content)


class PipelineLanguageTests(unittest.TestCase):
    def _pipeline_with_chunks(self, chunks):
        pipeline = Pipeline.__new__(Pipeline)
        pipeline.temperature = 0.0
        pipeline.append_to_session = False
        pipeline._session_state = {
            "language": None,
            "duration": 0.0,
            "text": "",
            "segments": [],
            "chunk_sentiments": [],
        }
        pipeline._persist_session_outputs = lambda *args, **kwargs: None

        def fake_iter_chunk_transcriptions(self, input_value, language=None):
            del input_value, language
            for chunk in chunks:
                yield chunk

        pipeline._iter_chunk_transcriptions = MethodType(fake_iter_chunk_transcriptions, pipeline)
        return pipeline

    def test_stream_transcribe_uses_backend_language_when_available(self):
        pipeline = self._pipeline_with_chunks([
            ({
                "text": "bonjour",
                "segments": [{"start": 0.0, "end": 1.0, "text": "bonjour"}],
                "start_time": 0.0,
                "end_time": 1.0,
                "language": "fr",
            }, {}),
        ])

        events = list(pipeline.stream_transcribe(object(), language=None))

        self.assertEqual(events[0]["language"], "fr")
        self.assertEqual(events[-1]["language"], "fr")

    def test_transcribe_leaves_language_none_when_not_supplied_or_detected(self):
        pipeline = self._pipeline_with_chunks([
            ({
                "text": "hello",
                "segments": [{"start": 0.0, "end": 1.0, "text": "hello"}],
                "start_time": 0.0,
                "end_time": 1.0,
            }, {}),
        ])

        result = pipeline.transcribe(object(), language=None)

        self.assertIsNone(result["language"])

    def test_transcribe_appends_existing_session_state(self):
        pipeline = self._pipeline_with_chunks([
            ({
                "text": "next line",
                "segments": [{"start": 0.0, "end": 1.5, "text": "next line"}],
                "start_time": 0.0,
                "end_time": 1.5,
                "language": "en",
            }, {"label": "happy", "score": 0.8, "scores": {"happy": 0.8}}),
        ])
        pipeline.append_to_session = True
        pipeline._session_state = {
            "language": "en",
            "duration": 2.0,
            "text": "prior line",
            "segments": [{"start": 0.0, "end": 2.0, "text": "prior line"}],
            "chunk_sentiments": [{"label": "neutral", "score": 0.4, "scores": {"neutral": 0.4}}],
        }
        persisted = {}
        pipeline._persist_session_outputs = lambda language, duration, text, segments, chunk_sentiments: persisted.update({
            "language": language,
            "duration": duration,
            "text": text,
            "segments": segments,
            "chunk_sentiments": chunk_sentiments,
        })

        result = pipeline.transcribe(object(), language=None)

        self.assertEqual(result["duration"], 3.5)
        self.assertEqual(result["text"], "prior line\nnext line")
        self.assertEqual(len(result["segments"]), 2)
        self.assertEqual(result["segments"][1]["start"], 2.0)
        self.assertEqual(result["segments"][1]["end"], 3.5)
        self.assertEqual(persisted["text"], "prior line\nnext line")
        self.assertEqual(len(persisted["chunk_sentiments"]), 2)

    def test_stream_transcribe_continues_chunk_index_for_existing_session(self):
        pipeline = self._pipeline_with_chunks([
            ({
                "text": "new chunk",
                "segments": [{"start": 0.0, "end": 1.0, "text": "new chunk"}],
                "start_time": 0.0,
                "end_time": 1.0,
                "language": "en",
            }, {"label": "happy", "score": 0.9, "scores": {"happy": 0.9}}),
        ])
        pipeline.append_to_session = True
        pipeline._session_state = {
            "language": "en",
            "duration": 5.0,
            "text": "old",
            "segments": [{"start": 0.0, "end": 5.0, "text": "old"}],
            "chunk_sentiments": [{"label": "neutral", "score": 0.2, "scores": {"neutral": 0.2}}],
        }
        pipeline._persist_session_outputs = lambda *args, **kwargs: None

        events = list(pipeline.stream_transcribe(object(), language=None))

        self.assertEqual(events[0]["chunk_index"], 1)
        self.assertEqual(events[0]["start_time"], 5.0)
        self.assertEqual(events[0]["end_time"], 6.0)
        self.assertEqual(events[-1]["duration"], 6.0)

    def test_session_state_round_trips_as_object_for_continuation(self):
        pipeline = Pipeline.__new__(Pipeline)
        pipeline.session_id = "session-state"
        pipeline.append_to_session = True

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(app_paths, "STORAGE_ROOT", temp_dir):
                pipeline._write_session_state({
                    "language": "en",
                    "duration": 4.5,
                    "text": "hello",
                    "segments": [{"start": 0.0, "end": 4.5, "text": "hello"}],
                    "chunk_sentiments": [{"label": "neutral", "score": 0.2, "scores": {"neutral": 0.2}}],
                })

                state_path = os.path.join(app_paths.get_session_dir("session-state"), "session_state.json")
                with open(state_path, encoding="utf-8") as handle:
                    on_disk = json.load(handle)

                loaded = pipeline._load_session_state()

        self.assertIsInstance(on_disk, dict)
        self.assertEqual(on_disk["text"], "hello")
        self.assertEqual(loaded["language"], "en")
        self.assertEqual(loaded["duration"], 4.5)
        self.assertEqual(loaded["segments"][0]["text"], "hello")

    def test_iter_chunk_transcriptions_runs_sentiment_before_chunk_cleanup(self):
        pipeline = Pipeline.__new__(Pipeline)
        pipeline.temperature = 0.0
        pipeline.session_id = "session-test"

        with tempfile.TemporaryDirectory() as temp_dir:
            chunk_path = os.path.join(temp_dir, "chunk.wav")
            with open(chunk_path, "wb") as handle:
                handle.write(b"chunk-data")

            class FakeASRComponent:
                def process(self, input_value, language=None):
                    del input_value, language
                    yield {
                        "chunk_path": chunk_path,
                        "text": "hello",
                        "segments": [{"start": 0.0, "end": 1.0, "text": "hello"}],
                        "start_time": 0.0,
                        "end_time": 1.0,
                    }

            class FakeSentimentComponent:
                def analyze(self, audio_path):
                    return {
                        "label": "happy" if os.path.exists(audio_path) else "missing",
                        "score": 1.0,
                        "scores": {"happy": 1.0},
                    }

            pipeline.asr_component = FakeASRComponent()
            pipeline.sentiment_component = FakeSentimentComponent()

            with patch("pipeline.SENTIMENT_ENABLED", True), patch("pipeline.DELETE_CHUNK_AFTER_USE", True):
                items = list(pipeline._iter_chunk_transcriptions(object(), language=None))

            self.assertEqual(items[0][1]["label"], "happy")
            self.assertFalse(os.path.exists(chunk_path))


class AudioUploadTests(unittest.TestCase):
    def test_normalize_session_id_rejects_unsafe_characters(self):
        with self.assertRaises(ValueError):
            normalize_session_id("../escape")

    def test_resolve_requested_session_id_treats_blank_as_new_session(self):
        session_id, continue_session = resolve_requested_session_id("   ")

        self.assertFalse(continue_session)
        self.assertTrue(session_id)
        self.assertNotEqual(session_id.strip(), "")

    def test_resolve_requested_session_id_preserves_valid_client_value(self):
        session_id, continue_session = resolve_requested_session_id("session-123")

        self.assertTrue(continue_session)
        self.assertEqual(session_id, "session-123")

    def test_get_chunks_dir_resolves_relative_path_under_project_root(self):
        chunks_dir = app_paths.get_chunks_dir("chunks/")

        self.assertTrue(os.path.isabs(chunks_dir))
        self.assertEqual(chunks_dir, os.path.join(app_paths.BASE_DIR, "chunks/"))

    def test_save_audio_file_uses_session_directory_and_sanitized_name(self):
        session_id = "session-123"
        upload = DummyUploadFile("../clip.wav", b"audio-bytes")

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(app_paths, "STORAGE_ROOT", temp_dir):
                filename, file_path = save_audio_file(upload, session_id=session_id)

            self.assertEqual(filename, "clip.wav")
            self.assertTrue(file_path.endswith(os.path.join(session_id, "clip.wav")))
            self.assertTrue(os.path.isfile(file_path))

    def test_save_audio_file_avoids_overwriting_existing_session_file(self):
        session_id = "session-123"
        upload_one = DummyUploadFile("clip.wav", b"first")
        upload_two = DummyUploadFile("clip.wav", b"second")

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(app_paths, "STORAGE_ROOT", temp_dir):
                first_name, first_path = save_audio_file(upload_one, session_id=session_id)
                second_name, second_path = save_audio_file(upload_two, session_id=session_id)

            self.assertEqual(first_name, "clip.wav")
            self.assertEqual(second_name, "clip_1.wav")
            self.assertNotEqual(first_path, second_path)
            self.assertTrue(os.path.isfile(first_path))
            self.assertTrue(os.path.isfile(second_path))


if __name__ == "__main__":
    unittest.main()