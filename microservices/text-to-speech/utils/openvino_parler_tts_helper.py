from collections import namedtuple
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from utils.parler_tts_compat import patch_parler_tts_compat


CHECKPOINT_PATH_FILE = "checkpoint_path.txt"
TEXT_ENCODER_XML = "text_encoder_ir.xml"
DECODER_STAGE_1_XML = "decoder_stage_1_ir.xml"
DECODER_STAGE_2_XML = "decoder_stage_2_ir.xml"

EncoderOutput = namedtuple("EncoderOutput", "last_hidden_state")
DecoderOutput = namedtuple(
    "DecoderOutput",
    ("last_hidden_state", "past_key_values", "hidden_states", "attentions", "cross_attentions"),
)


def parler_openvino_model_exists(output_dir: str | Path) -> bool:
    model_dir = Path(output_dir)
    required_files = [
        CHECKPOINT_PATH_FILE,
        TEXT_ENCODER_XML,
        TEXT_ENCODER_XML.replace(".xml", ".bin"),
        DECODER_STAGE_1_XML,
        DECODER_STAGE_1_XML.replace(".xml", ".bin"),
        DECODER_STAGE_2_XML,
        DECODER_STAGE_2_XML.replace(".xml", ".bin"),
    ]
    return all((model_dir / relative_path).exists() for relative_path in required_files)


def export_parler_tts_openvino_model(model_name_or_path: str, output_dir: str | Path, quantization_config=None) -> None:
    model_dir = Path(output_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    if parler_openvino_model_exists(model_dir):
        return
    convert_parler_tts_model(model_name_or_path, model_dir, quantization_config=quantization_config)


def _clear_torch_jit_state() -> None:
    torch._C._jit_clear_class_registry()
    torch.jit._recursive.concrete_type_store = torch.jit._recursive.ConcreteTypeStore()
    torch.jit._state._clear_class_state()


def _convert(module: torch.nn.Module, xml_path: Path, example_input, quantization_config=None) -> None:
    import openvino as ov

    if xml_path.exists():
        return

    xml_path.parent.mkdir(parents=True, exist_ok=True)
    with torch.no_grad():
        converted_model = ov.convert_model(module, example_input=example_input)
    if quantization_config is not None:
        import nncf

        converted_model = nncf.compress_weights(converted_model, **quantization_config)
    ov.save_model(converted_model, xml_path)
    _clear_torch_jit_state()


class _DecoderStage1Wrapper(torch.nn.Module):
    def __init__(self, decoder):
        super().__init__()
        self.decoder = decoder

    def forward(self, input_ids=None, encoder_hidden_states=None, encoder_attention_mask=None, prompt_hidden_states=None):
        return self.decoder(
            input_ids=input_ids,
            return_dict=False,
            encoder_hidden_states=encoder_hidden_states,
            encoder_attention_mask=encoder_attention_mask,
            prompt_hidden_states=prompt_hidden_states,
        )


class _DecoderStage2Wrapper(torch.nn.Module):
    def __init__(self, decoder):
        super().__init__()
        self.decoder = decoder

    def forward(self, input_ids=None, encoder_hidden_states=None, encoder_attention_mask=None, past_key_values=None):
        normalized_cache = tuple(tuple(past_key_values[i : i + 4]) for i in range(0, len(past_key_values), 4))
        return self.decoder(
            input_ids=input_ids,
            return_dict=False,
            encoder_hidden_states=encoder_hidden_states,
            encoder_attention_mask=encoder_attention_mask,
            past_key_values=normalized_cache,
        )


def _build_export_inputs(model):
    decoder_config = model.decoder.model.decoder.config
    audio_config = model.audio_encoder.config
    num_heads = int(decoder_config.num_attention_heads)
    hidden_size = int(decoder_config.hidden_size)
    head_dim = hidden_size // max(num_heads, 1)
    num_layers = int(decoder_config.num_hidden_layers)
    prompt_length = int(getattr(audio_config, "num_codebooks", 9))
    encoder_length = 39
    self_cache_length = prompt_length + 1
    encoder_hidden_states = torch.ones((1, encoder_length, hidden_size), dtype=torch.float32)
    encoder_attention_mask = torch.ones((1, encoder_length), dtype=torch.int64)

    stage_1_inputs = {
        "input_ids": torch.ones((prompt_length, 1), dtype=torch.int64),
        "encoder_hidden_states": encoder_hidden_states,
        "encoder_attention_mask": encoder_attention_mask,
        "prompt_hidden_states": torch.ones((1, prompt_length, hidden_size), dtype=torch.float32),
    }
    stage_2_layer = (
        torch.ones((1, num_heads, self_cache_length, head_dim), dtype=torch.float32),
        torch.ones((1, num_heads, self_cache_length, head_dim), dtype=torch.float32),
        torch.ones((1, num_heads, encoder_length, head_dim), dtype=torch.float32),
        torch.ones((1, num_heads, encoder_length, head_dim), dtype=torch.float32),
    )
    stage_2_inputs = {
        "input_ids": torch.ones((prompt_length, 1), dtype=torch.int64),
        "encoder_hidden_states": encoder_hidden_states,
        "encoder_attention_mask": encoder_attention_mask,
        "past_key_values": stage_2_layer * num_layers,
    }
    return stage_1_inputs, stage_2_inputs


def convert_parler_tts_model(model_name_or_path: str, output_dir: str | Path, quantization_config=None) -> None:
    patch_parler_tts_compat()

    from parler_tts import ParlerTTSForConditionalGeneration

    model_dir = Path(output_dir)
    if parler_openvino_model_exists(model_dir):
        return

    model = ParlerTTSForConditionalGeneration.from_pretrained(model_name_or_path).to("cpu")
    model.eval()

    _convert(
        model.text_encoder,
        model_dir / TEXT_ENCODER_XML,
        {"input_ids": torch.ones((1, 39), dtype=torch.int64)},
        quantization_config=quantization_config,
    )

    stage_1_inputs, stage_2_inputs = _build_export_inputs(model)
    _convert(
        _DecoderStage1Wrapper(model.decoder.model.decoder),
        model_dir / DECODER_STAGE_1_XML,
        stage_1_inputs,
        quantization_config=quantization_config,
    )
    _convert(
        _DecoderStage2Wrapper(model.decoder.model.decoder),
        model_dir / DECODER_STAGE_2_XML,
        stage_2_inputs,
        quantization_config=quantization_config,
    )

    checkpoint_path = model_dir / CHECKPOINT_PATH_FILE
    checkpoint_path.write_text(f"{model_name_or_path}\n", encoding="utf-8")


def _resolve_checkpoint_path(model_dir: Path) -> str:
    checkpoint_path = model_dir / CHECKPOINT_PATH_FILE
    if not checkpoint_path.exists():
        raise RuntimeError(f"Missing Parler OpenVINO checkpoint reference at {checkpoint_path}")
    return checkpoint_path.read_text(encoding="utf-8").strip()


class _TextEncoderModelWrapper(torch.nn.Module):
    def __init__(self, core, encoder_ir_path: Path, device: str, config):
        super().__init__()
        self.encoder = core.compile_model(str(encoder_ir_path), device)
        self.config = config
        self.dtype = self.config.torch_dtype

    def __call__(self, input_ids, **_):
        last_hidden_state = self.encoder(input_ids)[0]
        return EncoderOutput(torch.from_numpy(last_hidden_state))


class _DecoderWrapper(torch.nn.Module):
    def __init__(self, core, decoder_stage_1_ir_path: Path, decoder_stage_2_ir_path: Path, device: str, config):
        super().__init__()
        self.decoder_stage_1 = core.compile_model(str(decoder_stage_1_ir_path), device)
        self.decoder_stage_2 = core.compile_model(str(decoder_stage_2_ir_path), device)
        self.config = config
        embed_dim = int(config.vocab_size) + 1
        self.embed_tokens = nn.ModuleList([nn.Embedding(embed_dim, config.hidden_size) for _ in range(config.num_codebooks)])

    def __call__(
        self,
        input_ids=None,
        encoder_hidden_states=None,
        encoder_attention_mask=None,
        past_key_values=None,
        prompt_hidden_states=None,
        **_,
    ):
        inputs = {}
        if input_ids is not None:
            inputs["input_ids"] = input_ids
        if encoder_hidden_states is not None:
            inputs["encoder_hidden_states"] = encoder_hidden_states
        if encoder_attention_mask is not None:
            inputs["encoder_attention_mask"] = encoder_attention_mask
        if prompt_hidden_states is not None:
            inputs["prompt_hidden_states"] = prompt_hidden_states

        if past_key_values is not None:
            flattened_cache = tuple(cache_value for layer_cache in past_key_values for cache_value in layer_cache)
            arguments = (input_ids, encoder_hidden_states, encoder_attention_mask, *flattened_cache)
            outs = self.decoder_stage_2(arguments)
        else:
            outs = self.decoder_stage_1(inputs)

        outputs = [torch.from_numpy(output) for output in outs.values()]
        normalized_cache = list(list(outputs[index : index + 4]) for index in range(1, len(outputs), 4))
        return DecoderOutput(outputs[0], normalized_cache, None, None, None)


class OVParlerTTSModel:
    def __init__(self, model, tokenizer, sample_rate: int):
        self.model = model
        self.tokenizer = tokenizer
        self.sample_rate = int(sample_rate)

    @classmethod
    def from_pretrained(cls, model_dir: str | Path, device: str = "CPU"):
        import openvino as ov

        patch_parler_tts_compat()

        from parler_tts import ParlerTTSForConditionalGeneration
        from transformers import AutoTokenizer

        base_dir = Path(model_dir)
        checkpoint_source = _resolve_checkpoint_path(base_dir)
        model = ParlerTTSForConditionalGeneration.from_pretrained(checkpoint_source).to("cpu")
        tokenizer = AutoTokenizer.from_pretrained(checkpoint_source)
        model.eval()

        core = ov.Core()
        model.text_encoder = _TextEncoderModelWrapper(core, base_dir / TEXT_ENCODER_XML, device, model.text_encoder.config)
        model.decoder.model.decoder = _DecoderWrapper(
            core,
            base_dir / DECODER_STAGE_1_XML,
            base_dir / DECODER_STAGE_2_XML,
            device,
            model.decoder.model.decoder.config,
        )
        model._supports_cache_class = False
        model._supports_static_cache = False
        sample_rate = int(getattr(model.config, "sampling_rate", 44100))
        return cls(model, tokenizer, sample_rate)

    def generate(self, text: str, description: str, max_new_tokens: int = 512) -> tuple[np.ndarray, int]:
        description_inputs = self.tokenizer(description, return_tensors="pt")
        prompt_inputs = self.tokenizer(text, return_tensors="pt")

        with torch.inference_mode():
            generation = self.model.generate(
                input_ids=description_inputs.input_ids.to("cpu"),
                attention_mask=description_inputs.attention_mask.to("cpu"),
                prompt_input_ids=prompt_inputs.input_ids.to("cpu"),
                prompt_attention_mask=prompt_inputs.attention_mask.to("cpu"),
                max_new_tokens=max_new_tokens,
            )

        audio = generation.detach().cpu().numpy().reshape(-1).astype(np.float32)
        return audio, self.sample_rate