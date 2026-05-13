def patch_parler_tts_compat() -> None:
    try:
        from parler_tts.configuration_parler_tts import ParlerTTSConfig
    except ImportError as exc:
        raise RuntimeError(
            "parler-tts is not installed. Install dependencies from requirements.txt before starting the service."
        ) from exc

    ParlerTTSConfig.has_no_defaults_at_init = True