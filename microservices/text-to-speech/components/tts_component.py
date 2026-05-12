from components.base_component import PipelineComponent
from components.tts.factory import create_tts_service


class TTSComponent(PipelineComponent):
    def __init__(
        self,
        session_id: str,
        model_name: str,
        runtime: str,
        device: str,
        dtype: str,
        model_variant: str,
        default_speaker: str,
        default_language: str,
    ):
        self.service = create_tts_service(
            session_id=session_id,
            model_name=model_name,
            runtime=runtime,
            device=device,
            dtype=dtype,
            model_variant=model_variant,
            default_speaker=default_speaker,
            default_language=default_language,
        )

    def synthesize(
        self,
        text: str,
        language: str | None = None,
        speaker: str | None = None,
        instructions: str | None = None,
    ) -> dict:
        return self.service.synthesize(text, language, speaker, instructions)

    def get_model_info(self) -> dict:
        return self.service.get_model_info()