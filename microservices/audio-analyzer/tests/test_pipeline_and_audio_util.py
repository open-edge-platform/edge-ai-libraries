import io
import json
import os
import sys
import tempfile
import unittest
from types import ModuleType
from types import MethodType
from unittest.mock import patch

from pipeline import Pipeline
from components.asr.openai.whisper import Whisper as OpenAIWhisper
from components.asr.whispercpp.whisper import WhisperCpp
from components.asr_component import ASRComponent
from utils.ensure_model import ensure_sentiment_model, get_asr_model_path, get_sentiment_model_path, get_whispercpp_model_filename
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

    def test_get_session_chunks_dir_stays_under_session_storage(self):
        session_chunks_dir = app_paths.get_session_chunks_dir("session-123")

        self.assertEqual(
            session_chunks_dir,
            os.path.join(app_paths.STORAGE_ROOT, "session-123", "chunks"),
        )

    def test_save_audio_file_uses_session_directory_and_sanitized_name(self):
        session_id = "session-123"
        upload = DummyUploadFile("../clip.wav", b"audio-bytes")

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(app_paths, "STORAGE_ROOT", temp_dir), patch(
                "utils.audio_util._audio_stream_exists", return_value=True
            ):
                filename, file_path = save_audio_file(upload, session_id=session_id)

            self.assertEqual(filename, "clip.wav")
            self.assertTrue(file_path.endswith(os.path.join(session_id, "clip.wav")))
            self.assertTrue(os.path.isfile(file_path))

    def test_save_audio_file_avoids_overwriting_existing_session_file(self):
        session_id = "session-123"
        upload_one = DummyUploadFile("clip.wav", b"first")
        upload_two = DummyUploadFile("clip.wav", b"second")

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(app_paths, "STORAGE_ROOT", temp_dir), patch(
                "utils.audio_util._audio_stream_exists", return_value=True
            ):
                first_name, first_path = save_audio_file(upload_one, session_id=session_id)
                second_name, second_path = save_audio_file(upload_two, session_id=session_id)

            self.assertEqual(first_name, "clip.wav")
            self.assertEqual(second_name, "clip_1.wav")
            self.assertNotEqual(first_path, second_path)
            self.assertTrue(os.path.isfile(first_path))
            self.assertTrue(os.path.isfile(second_path))


class ASRBackendSelectionTests(unittest.TestCase):
    def tearDown(self):
        ASRComponent._model = None
        ASRComponent._config = None

    def test_whispercpp_backend_forces_cpu(self):
        with patch("components.asr_component.WhisperCpp") as whispercpp_cls:
            ASRComponent(session_id="test", provider="whispercpp", model_name="whisper-small", device="GPU")

        whispercpp_cls.assert_called_once_with("whisper-small", "CPU", None)

    def test_openvino_backend_honors_ov_genai_toggle(self):
        with patch("components.asr_component.OVGenAIWhisper") as ov_genai_cls, patch(
            "components.asr_component.OV_Whisper"
        ) as ov_cls, patch("components.asr_component.config.app.use_ov_genai", True):
            ASRComponent(session_id="test", provider="openvino", model_name="whisper-small", device="CPU")

        ov_genai_cls.assert_called_once_with("whisper-small", "CPU", None)
        ov_cls.assert_not_called()


class WhisperCppTests(unittest.TestCase):
    def _install_fake_pywhispercpp(self, model_factory):
        package = ModuleType("pywhispercpp")
        model_module = ModuleType("pywhispercpp.model")
        model_module.Model = model_factory
        package.model = model_module
        return patch.dict(sys.modules, {"pywhispercpp": package, "pywhispercpp.model": model_module})

    def test_whispercpp_transcribe_returns_language_and_meta(self):
        class FakeSegment:
            def __init__(self, text, start, end, probability, no_speech_prob=0.0):
                self.text = text
                self.t0 = int(start * 100)
                self.t1 = int(end * 100)
                self.probability = probability
                self.no_speech_prob = no_speech_prob
                self.tokens = []

        class FakeModel:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs
                self.transcribe_kwargs = None

            def transcribe(self, media, **kwargs):
                del media
                self.transcribe_kwargs = kwargs
                return [
                    FakeSegment("bonjour bonjour", 0.0, 0.8, 0.9),
                    FakeSegment("bonjour bonjour", 0.8, 1.4, 0.9),
                ]

        with self._install_fake_pywhispercpp(FakeModel), patch(
            "components.asr.whispercpp.whisper.os.path.isfile", return_value=True
        ), patch("utils.ensure_model.get_asr_model_path", return_value="/tmp/models"):
            asr = WhisperCpp(model_name="whisper-small", device="CPU")
            result = asr.transcribe("/tmp/audio.wav", temperature=0.0, language=None)

        self.assertIsNone(result["language"])
        self.assertEqual(result["text"], "bonjour")
        self.assertEqual(result["meta"]["segments_total"], 2)
        self.assertEqual(result["meta"]["segments_kept"], 1)
        self.assertEqual(result["meta"]["segments_dropped"], 0)
        self.assertNotIn("language", asr.model.transcribe_kwargs)

    def test_whispercpp_filters_hallucination_like_segments(self):
        class FakeToken:
            def __init__(self, plog, ptsum, token_id=1):
                self.plog = plog
                self.ptsum = ptsum
                self.id = token_id

        class FakeSegment:
            def __init__(self, text, start, end, tokens):
                self.text = text
                self.t0 = int(start * 100)
                self.t1 = int(end * 100)
                self.tokens = tokens

        class FakeModel:
            def __init__(self, *args, **kwargs):
                pass

            def transcribe(self, media, **kwargs):
                del media, kwargs
                return [
                    FakeSegment("uh", 0.0, 0.1, [FakeToken(-2.0, 0.95)]),
                    FakeSegment("real speech", 0.1, 1.2, [FakeToken(-0.1, 0.1)]),
                ]

        with self._install_fake_pywhispercpp(FakeModel), patch(
            "components.asr.whispercpp.whisper.os.path.isfile", return_value=True
        ), patch("utils.ensure_model.get_asr_model_path", return_value="/tmp/models"):
            asr = WhisperCpp(model_name="whisper-small", device="CPU")
            result = asr.transcribe("/tmp/audio.wav", temperature=0.0, language="en")

        self.assertEqual(result["language"], "en")
        self.assertEqual(result["text"], "real speech")
        self.assertEqual(len(result["segments"]), 1)
        self.assertEqual(result["meta"]["segments_dropped"], 1)

    def test_whispercpp_transcribe_uses_configured_decoder_options(self):
        class FakeSegment:
            def __init__(self, text, start, end, probability=0.9):
                self.text = text
                self.t0 = int(start * 100)
                self.t1 = int(end * 100)
                self.probability = probability
                self.tokens = []

        class FakeModel:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs
                self.transcribe_kwargs = None

            def transcribe(
                self,
                media,
                temperature,
                token_timestamps,
                extract_probability,
                print_realtime,
                print_progress,
                no_context,
                entropy_thold,
                logprob_thold,
                no_speech_thold,
                suppress_non_speech_tokens,
                greedy,
                beam_search,
                language,
            ):
                del media
                self.transcribe_kwargs = {
                    "temperature": temperature,
                    "token_timestamps": token_timestamps,
                    "extract_probability": extract_probability,
                    "print_realtime": print_realtime,
                    "print_progress": print_progress,
                    "no_context": no_context,
                    "entropy_thold": entropy_thold,
                    "logprob_thold": logprob_thold,
                    "no_speech_thold": no_speech_thold,
                    "suppress_non_speech_tokens": suppress_non_speech_tokens,
                    "greedy": greedy,
                    "beam_search": beam_search,
                    "language": language,
                }
                return [FakeSegment("hello", 0.0, 1.0)]

        with self._install_fake_pywhispercpp(FakeModel), patch(
            "components.asr.whispercpp.whisper.os.path.isfile", return_value=True
        ), patch("utils.ensure_model.get_asr_model_path", return_value="/tmp/models"), patch(
            "components.asr.whispercpp.whisper.config.models.asr.beam_size", 3
        ), patch("components.asr.whispercpp.whisper.config.models.asr.best_of", 2), patch(
            "components.asr.whispercpp.whisper.config.models.asr.word_timestamps", True
        ):
            asr = WhisperCpp(model_name="whisper-small", device="CPU")
            result = asr.transcribe("/tmp/audio.wav", temperature=0.2, language="en")

        self.assertEqual(result["text"], "hello")
        self.assertEqual(asr.model.transcribe_kwargs["greedy"], {"best_of": 2})
        self.assertEqual(asr.model.transcribe_kwargs["beam_search"], {"beam_size": 3, "patience": -1.0})
        self.assertTrue(asr.model.transcribe_kwargs["token_timestamps"])
        self.assertEqual(asr.model.transcribe_kwargs["language"], "en")


class WhisperCppQuantizationTests(unittest.TestCase):
    def _install_fake_pywhispercpp(self, model_factory):
        package = ModuleType("pywhispercpp")
        model_module = ModuleType("pywhispercpp.model")
        model_module.Model = model_factory
        package.model = model_module
        return patch.dict(sys.modules, {"pywhispercpp": package, "pywhispercpp.model": model_module})

    def test_whispercpp_weight_format_aliases_resolve_expected_filename(self):
        self.assertEqual(get_whispercpp_model_filename("whisper-medium", "q5"), "ggml-medium-q5_0.bin")
        self.assertEqual(get_whispercpp_model_filename("whisper-small", "int8"), "ggml-small-q8_0.bin")

    def test_whispercpp_model_path_includes_quantized_suffix(self):
        with patch("utils.ensure_model.config.models.asr.provider", "whispercpp"), patch(
            "utils.ensure_model.config.models.asr.name", "whisper-medium"
        ), patch("utils.ensure_model.config.models.asr.weight_format", "q5"), patch(
            "utils.ensure_model.config.models.asr.models_base_path", "models"
        ):
            self.assertEqual(get_asr_model_path(), os.path.join("models", "whispercpp", "whisper-medium-q5_0"))

    def test_whispercpp_uses_all_cores_when_threads_not_positive(self):
        with patch("components.asr.whispercpp.whisper.os.path.isfile", return_value=True), patch(
            "utils.ensure_model.get_asr_model_path", return_value="/tmp/models"
        ), patch("components.asr.whispercpp.whisper.os.cpu_count", return_value=22), patch(
            "components.asr.whispercpp.whisper.config.models.asr.threads", 0
        ):
            with self._install_fake_pywhispercpp(lambda *args, **kwargs: type("FakeModel", (), {})()):
                asr = WhisperCpp(model_name="whisper-small", device="CPU")

        self.assertEqual(asr.n_threads, 22)


class OpenAIWhisperConfigTests(unittest.TestCase):
    def test_openai_transcribe_uses_configured_beam_size_and_best_of(self):
        class FakeModel:
            def __init__(self):
                self.kwargs = None

            def transcribe(self, audio_path, **kwargs):
                del audio_path
                self.kwargs = kwargs
                return {
                    "text": "hello",
                    "language": "en",
                    "segments": [
                        {
                            "start": 0.0,
                            "end": 1.0,
                            "text": "hello",
                            "avg_logprob": -0.1,
                            "compression_ratio": 1.0,
                            "no_speech_prob": 0.0,
                        }
                    ],
                }

        fake_model = FakeModel()

        with patch("components.asr.openai.whisper.whisper.load_model", return_value=fake_model), patch(
            "components.asr.openai.whisper.config.models.asr.beam_size", 1
        ), patch("components.asr.openai.whisper.config.models.asr.best_of", 2):
            asr = OpenAIWhisper(model_name="whisper-base", device="cpu")
            result = asr.transcribe("/tmp/audio.wav", temperature=0.0, language="en")

        self.assertEqual(result["text"], "hello")
        self.assertEqual(fake_model.kwargs["beam_size"], 1)
        self.assertEqual(fake_model.kwargs["best_of"], 2)


class SentimentExportTests(unittest.TestCase):
    def test_speechbrain_openvino_export_forces_cpu(self):
        with patch("utils.ensure_model.config.sentiment.provider", "openvino"), patch(
            "utils.ensure_model.config.sentiment.model", "speechbrain/emotion-recognition-wav2vec2-IEMOCAP"
        ), patch("utils.ensure_model.config.sentiment.models_base_path", "models"), patch(
            "utils.ensure_model.config.sentiment.weight_format", "int8"
        ), patch("utils.ensure_model.config.sentiment.device", "GPU"), patch(
            "utils.ensure_model._export_speechbrain_sentiment_openvino"
        ) as export_cls:
            ensure_sentiment_model()

        export_cls.assert_called_once_with(
            "speechbrain/emotion-recognition-wav2vec2-IEMOCAP",
            os.path.join("models", "sentiment", "speechbrain_emotion-recognition-wav2vec2-IEMOCAP"),
            "CPU",
        )

    def test_speechbrain_openvino_model_path_ignores_weight_format(self):
        with patch("utils.ensure_model.config.sentiment.provider", "openvino"), patch(
            "utils.ensure_model.config.sentiment.model", "speechbrain/emotion-recognition-wav2vec2-IEMOCAP"
        ), patch("utils.ensure_model.config.sentiment.models_base_path", "models"), patch(
            "utils.ensure_model.config.sentiment.weight_format", "int8"
        ):
            self.assertEqual(
                get_sentiment_model_path(),
                os.path.join("models", "sentiment", "speechbrain_emotion-recognition-wav2vec2-IEMOCAP"),
            )


if __name__ == "__main__":
    unittest.main()