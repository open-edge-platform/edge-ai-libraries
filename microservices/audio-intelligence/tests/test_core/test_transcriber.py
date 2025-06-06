from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from audio_intelligence.core.transcriber import TranscriptionService
from audio_intelligence.schemas.types import DeviceType, TranscriptionBackend, WhisperModel


@pytest.mark.unit
def test_transcription_service_init(mock_settings):
    """Test initializing the TranscriptionService"""

    with patch("audio_intelligence.core.transcriber.settings", mock_settings):
        # Test with default parameters
        service = TranscriptionService()
        
        assert service.model == None
        assert service.model_name == mock_settings.DEFAULT_WHISPER_MODEL
        assert service.device_type == mock_settings.DEFAULT_DEVICE

    # Test with custom parameters
    service = TranscriptionService(
        model_name="base.en",
        device=DeviceType.GPU
    )

    assert service.model_name == WhisperModel.BASE_EN
    assert service.device_type == DeviceType.GPU


@pytest.mark.unit
def test_determine_backend_cpu():
    """Test backend determination when CPU is selected"""
    service = TranscriptionService(device="cpu")
    
    assert service.backend == TranscriptionBackend.WHISPER_CPP


@pytest.mark.unit
@patch("audio_intelligence.core.transcriber.importlib.util.find_spec")
@patch("audio_intelligence.core.transcriber.ModelManager.is_model_downloaded")
def test_determine_backend_gpu_with_openvino(mock_is_model_downloaded, mock_find_spec):
    """Test backend determination when GPU is selected and OpenVINO is available"""
    
    mock_find_spec.return_value = True  # OpenVINO is available
    mock_is_model_downloaded.return_value = True  # Model is downloaded for GPU
    
    # Create service with GPU device
    service = TranscriptionService(model_name="tiny.en", device="gpu")
    
    # Check that OpenVINO backend is selected
    assert service.backend == TranscriptionBackend.OPENVINO
    mock_find_spec.assert_called_once_with("openvino")
    mock_is_model_downloaded.assert_called_once_with(WhisperModel.TINY_EN, use_gpu=True)


@pytest.mark.unit
@patch("audio_intelligence.core.transcriber.importlib.util.find_spec")
def test_determine_backend_gpu_without_openvino(mock_find_spec):
    """Test backend determination when GPU is selected but OpenVINO is not available"""

    mock_find_spec.return_value = False  # OpenVINO is not available
    
    # Create service with GPU device
    service = TranscriptionService(model_name="tiny.en", device="gpu")
    
    # Check that it falls back to WhisperCPP
    assert service.backend == TranscriptionBackend.WHISPER_CPP
    mock_find_spec.assert_called_once_with("openvino")


@pytest.mark.unit
@patch("audio_intelligence.core.transcriber.is_intel_gpu_available")
@patch("audio_intelligence.core.transcriber.ModelManager.is_model_downloaded")
def test_determine_backend_auto_with_gpu(mock_is_model_downloaded, mock_is_intel_gpu_available):
    """Test backend determination with 'auto' when GPU is available"""
    # Mock dependencies
    mock_is_intel_gpu_available.return_value = True  # Intel GPU is available
    mock_is_model_downloaded.return_value = True  # Model is downloaded for GPU
    
    # Create service with auto device detection
    service = TranscriptionService(model_name="tiny.en", device="auto")
    
    # Check that OpenVINO backend is selected
    assert service.backend == TranscriptionBackend.OPENVINO
    mock_is_intel_gpu_available.assert_called_once()
    mock_is_model_downloaded.assert_called_once_with(WhisperModel.TINY_EN, use_gpu=True)


@pytest.mark.unit
@patch("audio_intelligence.core.transcriber.is_intel_gpu_available")
def test_determine_backend_auto_without_gpu(mock_is_intel_gpu_available):
    """Test backend determination with 'auto' when no GPU is available"""
    # Mock dependencies
    mock_is_intel_gpu_available.return_value = False  # No Intel GPU
    
    # Create service with auto device detection
    service = TranscriptionService(device="auto")
    
    # Check that it falls back to WhisperCPP
    assert service.backend == TranscriptionBackend.WHISPER_CPP
    mock_is_intel_gpu_available.assert_called_once()


@pytest.mark.unit
def test_load_model_whisper_cpp(mock_settings):
    """Test loading a WhisperCPP model"""
    with patch("audio_intelligence.core.transcriber.ModelManager.get_model_path") as mock_get_model_path, \
         patch("audio_intelligence.core.transcriber.settings", mock_settings), \
         patch("pywhispercpp.model.Model") as MockModel:
        
        mock_model_path = mock_settings.GGML_MODEL_DIR / "tiny.en.bin"
        mock_get_model_path.return_value = mock_model_path
        mock_model_instance = MagicMock()
        MockModel.return_value = mock_model_instance
        
        # Create service and load model
        service = TranscriptionService(model_name="tiny.en", device="cpu")
        service.backend = TranscriptionBackend.WHISPER_CPP

        with patch.object(Path, "is_file", return_value=True):
            service._load_model()
        
        # Verify the model was loaded correctly
        mock_get_model_path.assert_called_once_with(WhisperModel.TINY_EN, use_gpu=False)
        MockModel.assert_called_once_with(str(mock_model_path), n_threads=24)
        assert service.model == mock_model_instance


@pytest.mark.unit
def test_load_model_openvino(mock_settings):
    """Test loading an OpenVINO model"""
    with patch("audio_intelligence.core.transcriber.ModelManager.get_model_path") as mock_get_model_path, \
         patch("openvino.Core") as MockCore, \
         patch("transformers.AutoProcessor") as MockAutoProcessor, \
         patch("audio_intelligence.core.transcriber.settings", mock_settings):
        # Configure mocks
        mock_model_dir = mock_settings.OPENVINO_MODEL_DIR / "tiny.en"
        mock_get_model_path.return_value = mock_model_dir
        
        mock_core = MagicMock()
        MockCore.return_value = mock_core
        
        mock_encoder_model = MagicMock()
        mock_decoder_model = MagicMock()
        mock_core.read_model.side_effect = [mock_encoder_model, mock_decoder_model]
        
        mock_encoder_compiled = MagicMock()
        mock_decoder_compiled = MagicMock()
        mock_core.compile_model.side_effect = [mock_encoder_compiled, mock_decoder_compiled]
        
        mock_processor = MagicMock()
        MockAutoProcessor.from_pretrained.return_value = mock_processor
        
        # Create service by mocking _determine_backend method to avoid calling get_model_path twice
        with patch.object(TranscriptionService, "_determine_backend", return_value=TranscriptionBackend.OPENVINO):
            service = TranscriptionService(model_name="tiny.en", device="gpu")
        
        # Mock Path.is_file and Path.is_dir to return True and run the method to be
        with patch.object(Path, "is_file", return_value=True), \
             patch.object(Path, "is_dir", return_value=True):
            service._load_model()
        
        # Verify the model was loaded correctly
        mock_get_model_path.assert_called_once_with(WhisperModel.TINY_EN, use_gpu=True)
        mock_core.read_model.assert_any_call(mock_model_dir / "encoder_model.xml")
        mock_core.read_model.assert_any_call(mock_model_dir / "decoder_model.xml")
        mock_core.compile_model.assert_any_call(mock_encoder_model, "GPU")
        mock_core.compile_model.assert_any_call(mock_decoder_model, "GPU")
        MockAutoProcessor.from_pretrained.assert_called_once_with(str(mock_model_dir))
        
        # Check model structure
        assert service.model["encoder"] == mock_encoder_compiled
        assert service.model["decoder"] == mock_decoder_compiled
        assert service.model["processor"] == mock_processor


@pytest.mark.asyncio
@pytest.mark.unit
async def test_transcribe_with_whisper_cpp(mock_settings, mock_audio_file):
    """Test transcription with WhisperCPP backend"""
    with patch.object(TranscriptionService, "_load_model") as mock_load_model, \
         patch.object(TranscriptionService, "_transcribe_with_whisper_cpp") as mock_transcribe_whisper, \
         patch.object(TranscriptionService, "_determine_backend", return_value=TranscriptionBackend.WHISPER_CPP), \
         patch("audio_intelligence.core.transcriber.uuid.uuid4", return_value="12345678-1234-5678") as mock_uuid, \
         patch("audio_intelligence.core.transcriber.settings", mock_settings):
        
        # Configure mocks
        job_id = mock_uuid()[-8:]
        filename = mock_audio_file.stem
        srt_path = mock_settings.OUTPUT_DIR / "transcript" / f"{filename}-{job_id}.srt"
        txt_path = mock_settings.OUTPUT_DIR / "transcript" / f"{filename}-{job_id}.txt"
        
        # Configure the transcription service
        service = TranscriptionService(model_name="tiny.en", device="cpu")
        
        _id, output_path = await service.transcribe(
            mock_audio_file,
            include_timestamps=True,
            video_duration=59.0
        )
    
        # Check the job_id and output path
        assert _id == job_id
        assert output_path == srt_path
        
        # Verify _transcribe_with_whisper_cpp was called correctly
        mock_transcribe_whisper.assert_called_once()
        mock_load_model.assert_called_once()

        # Verify all parameters were passed correctly
        _, call_args, _ = mock_transcribe_whisper.mock_calls[0]
        assert call_args[0] == mock_audio_file
        assert call_args[1] == srt_path
        assert call_args[2] == txt_path
        assert call_args[3] == None
        assert call_args[4] is True
        assert call_args[5] == 59.0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_transcribe_with_openvino(mock_settings, mock_audio_file):
    """Test transcription with OpenVINO backend"""
    with patch.object(TranscriptionService, "_load_model"), \
         patch.object(TranscriptionService, "_transcribe_with_openvino") as mock_transcribe_openvino, \
         patch.object(TranscriptionService, "_determine_backend", return_value=TranscriptionBackend.OPENVINO), \
         patch("audio_intelligence.core.transcriber.uuid.uuid4", return_value="12345678-1234-5678") as mock_uuid, \
         patch("audio_intelligence.core.transcriber.settings", mock_settings):
        
        # Configure mocks
        job_id = mock_uuid()[-8:]
        filename = mock_audio_file.stem
        srt_path = mock_settings.OUTPUT_DIR / "transcript" / f"{filename}-{job_id}.srt"
        txt_path = mock_settings.OUTPUT_DIR / "transcript" / f"{filename}-{job_id}.txt"
        
        # Configure the transcription service
        service = TranscriptionService(model_name="tiny.en", device="gpu")
        
        _id, output_path = await service.transcribe(
            mock_audio_file,
            include_timestamps=True
        )
    
        # Check the job_id and output path
        assert job_id == _id
        assert output_path == srt_path
        
        # Verify _transcribe_with_openvino was called correctly with correct parameters
        mock_transcribe_openvino.assert_called_once()
        _, call_args, _ = mock_transcribe_openvino.mock_calls[0]
        assert call_args[0] == mock_audio_file
        assert call_args[1] == srt_path
        assert call_args[2] == txt_path
        assert call_args[3] == None
        assert call_args[4] is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_transcribe_with_whisper_cpp_implementation():
    """Test the implementation of _transcribe_with_whisper_cpp method"""
    with patch("pywhispercpp.utils.output_srt") as mock_output_srt, \
         patch("pywhispercpp.utils.output_txt") as mock_output_txt, \
         patch("audio_intelligence.core.transcriber.settings") as mock_settings:
        
        # Configure mocks
        audio_path = Path("/tmp/audio/test.wav")
        srt_path = Path("/tmp/output/transcript/test-123456.srt")
        txt_path = Path("/tmp/output/transcript/test-123456.txt")
        mock_settings.TRANSCRIPT_LANGUAGE = None
        
        # Create mock model
        mock_model = MagicMock()
        mock_segments = [{"start": 0.0, "end": 5.0, "text": "Test transcript"}]
        mock_model.transcribe.return_value = mock_segments
        
        # Configure the transcription service
        service = TranscriptionService()
        service.model = mock_model
        
        # Call the method
        await service._transcribe_with_whisper_cpp(
            audio_path,
            srt_path,
            txt_path,
            language="en",
            include_timestamps=True,
            video_duration=60.0
        )
        
        # Verify model.transcribe was called correctly
        mock_model.transcribe.assert_called_once_with(
            str(audio_path),
            n_processors=1,  # 60 seconds = 1 processor
            language="en",
            beam_search={"beam_size": 5, "patience": 1.5},
            greedy={"best_of": 1}
        )
        
        # Verify output functions were called
        mock_output_txt.assert_called_once_with(mock_segments, str(txt_path))
        mock_output_srt.assert_called_once_with(mock_segments, str(srt_path))
