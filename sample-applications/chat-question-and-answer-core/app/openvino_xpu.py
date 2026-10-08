"""
Accelerator (GPU/NPU) helpers for the OpenVINO backend.

- `StaticBatchModel` runs an optimum encoder (embedding, reranker) compiled with a static
  `[batch, seq]` shape, which the NPU requires, on inputs of any batch size. langchain's
  OpenVINO embeddings and reranker already pad the sequence to a static length.
- `GenAILLM` is a LangChain LLM over `openvino_genai.LLMPipeline`, used for the LLM on NPU,
  where the optimum (HF pipeline) path is not supported.
- `npu_lock` serializes inference across all models on the NPU.
"""

import queue
import threading
import time
from typing import Any, Callable, Iterator, List, Optional

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.llms import LLM
from langchain_core.outputs import GenerationChunk
from pydantic import PrivateAttr

from .logger import logger


class NpuLock:
    """
    Serializes NPU jobs and leaves `settle_s` between the end of one job and the start of the
    next. On the Panther Lake NPU (UMD 1.30 and 1.38), two models inferring at the same time,
    or back to back without a gap, cause an MMU translation fault, after which the device is
    lost for the process.
    """

    def __init__(self, settle_s: float = 0.005):
        self.settle_s = settle_s
        self._lock = threading.RLock()
        self._released = 0.0

    def __enter__(self):
        self._lock.acquire()
        wait = self._released + self.settle_s - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        return self

    def __exit__(self, *exc):
        self._released = time.monotonic()
        self._lock.release()
        return False


npu_lock = NpuLock()


class PromptTooLongError(ValueError):
    """The prompt exceeds the LLM prompt limit (MAX_PROMPT_LEN on NPU)."""


def _concat(parts):
    import numpy as np

    if hasattr(parts[0], "detach"):
        import torch

        return torch.cat(parts, dim=0)
    return np.concatenate(parts, axis=0)


def _copy(value):
    return value.clone() if hasattr(value, "clone") else value.copy()


def _pad_batch(value, batch_size: int):
    """Pads a tensor to `batch_size` rows by repeating its last row (a valid input)."""

    missing = batch_size - value.shape[0]
    if missing <= 0:
        return value
    return _concat([value] + [value[-1:]] * missing)


class StaticBatchModel:
    """
    Wraps an optimum OVModel compiled with a static batch size. Inputs are split into chunks
    of `batch_size` rows, the last chunk is padded, and outputs are trimmed back.
    Attribute access (e.g. `request`, used by langchain to read the static sequence length)
    is forwarded to the wrapped model.

    When `lock` is set, each batch runs under it. The NPU plugin shares input and output
    memory with the device, so the wrapper copies both and frees its copies inside the lock:
    freeing that memory while another NPU model infers also causes the NPU MMU fault.
    """

    def __init__(self, model: Any, batch_size: int, lock: Optional[Any] = None):
        self._model = model
        self.batch_size = batch_size
        self._lock = lock

    def __getattr__(self, name):
        return getattr(self._model, name)

    def __call__(self, **inputs):
        tensors = {k: v for k, v in inputs.items() if hasattr(v, "shape")}
        others = {k: v for k, v in inputs.items() if k not in tensors}
        total = next(iter(tensors.values())).shape[0]

        outputs = []
        for start in range(0, total, self.batch_size):
            if self._lock is None:
                outputs.append(self._run(tensors, others, start))
            else:
                with self._lock:
                    outputs.append(self._run(tensors, others, start))

        merged = {key: _concat([out[key] for out in outputs]) for key in outputs[0].keys()}
        return type(outputs[0])(**merged)

    def _run(self, tensors: dict, others: dict, start: int):
        """Runs one padded batch; returns copies of the real rows of every output."""

        chunk = {k: _copy(v[start : start + self.batch_size]) for k, v in tensors.items()}
        rows = next(iter(chunk.values())).shape[0]
        chunk = {k: _pad_batch(v, self.batch_size) for k, v in chunk.items()}
        output = self._model(**chunk, **others)
        return type(output)(**{key: _copy(output[key][:rows]) for key in output.keys()})


def make_static(model: Any, batch_size: int, seq_len: int) -> StaticBatchModel:
    """
    Reshapes an optimum encoder (loaded with `compile=False`) to `[batch_size, seq_len]`,
    compiles it and wraps it so that callers can pass any batch size. On NPU, inference runs
    under `npu_lock`.
    """

    max_positions = getattr(getattr(model, "config", None), "max_position_embeddings", None)
    if isinstance(max_positions, int) and 0 < max_positions < seq_len:
        seq_len = max_positions
    logger.info(
        f"Compiling {type(model).__name__} with static shape [{batch_size}, {seq_len}] "
        f"on {getattr(model, '_device', '?')}"
    )
    model.reshape(batch_size, seq_len)
    model.compile()

    on_npu = str(getattr(model, "_device", "")).upper() == "NPU"
    return StaticBatchModel(model, batch_size, lock=npu_lock if on_npu else None)


class TextQueue:
    """Iterator over text chunks produced on the generation thread."""

    _END = object()

    def __init__(self):
        self._queue: "queue.Queue" = queue.Queue()

    def put(self, text: str) -> None:
        self._queue.put(text)

    def end(self) -> None:
        self._queue.put(self._END)

    def __iter__(self):
        return self

    def __next__(self) -> str:
        item = self._queue.get()
        if item is self._END:
            raise StopIteration
        return item


class GenAILLM(LLM):
    """
    LangChain LLM over `openvino_genai.LLMPipeline`. On NPU the prompt is limited to
    `max_prompt_tokens` (MAX_PROMPT_LEN) and generation holds `npu_lock`, so other NPU models
    wait for it to finish. Elsewhere one generation runs at a time.
    """

    ov_pipe: Any = None
    max_new_tokens: int = 1024
    max_prompt_tokens: Optional[int] = None

    _lock: Any = PrivateAttr(default_factory=threading.Lock)

    @classmethod
    def load(
        cls,
        model_dir: str,
        device: str,
        max_new_tokens: int,
        max_prompt_tokens: Optional[int] = None,
        cache_dir: Optional[str] = None,
    ) -> "GenAILLM":
        import openvino_genai

        properties = {}
        if cache_dir:
            properties["CACHE_DIR"] = cache_dir
        if device == "NPU":
            # The NPU compiles the LLM for a fixed prompt and KV-cache size.
            properties["MAX_PROMPT_LEN"] = max_prompt_tokens
            properties["MIN_RESPONSE_LEN"] = max_new_tokens
        logger.info(f"Loading OpenVINO GenAI LLM from {model_dir} on {device} ({properties})")
        pipe = openvino_genai.LLMPipeline(model_dir, device, **properties)

        llm = cls(
            ov_pipe=pipe,
            max_new_tokens=max_new_tokens,
            max_prompt_tokens=max_prompt_tokens if device == "NPU" else None,
        )
        if device == "NPU":
            llm._lock = npu_lock
        return llm

    @property
    def _llm_type(self) -> str:
        return "openvino-genai"

    def count_tokens(self, text: str) -> int:
        return int(self.ov_pipe.get_tokenizer().encode(text).input_ids.get_shape()[-1])

    def stream_text(
        self,
        prompt: str,
        on_text: Optional[Callable[[str], None]] = None,
        cancel: Optional[threading.Event] = None,
        max_new_tokens: Optional[int] = None,
    ) -> str:
        """
        Generates text for a rendered prompt, calling `on_text` for each decoded chunk.
        Generation stops at the next token once `cancel` is set.

        Returns:
            str: The generated text.
        """

        import openvino_genai

        if self.max_prompt_tokens:
            tokens = self.count_tokens(prompt)
            if tokens > self.max_prompt_tokens:
                raise PromptTooLongError(
                    f"Prompt has {tokens} tokens; the LLM on this device accepts at most {self.max_prompt_tokens}."
                )

        generation_config = self.ov_pipe.get_generation_config()
        generation_config.max_new_tokens = min(max_new_tokens or self.max_new_tokens, self.max_new_tokens)
        # The prompt is already rendered by the prompt template (same as the HF pipeline path).
        generation_config.apply_chat_template = False

        parts: List[str] = []

        def streamer(text: str):
            parts.append(text)
            if on_text is not None:
                on_text(text)
            if cancel is not None and cancel.is_set():
                return openvino_genai.StreamingStatus.CANCEL
            return openvino_genai.StreamingStatus.RUNNING

        with self._lock:
            self.ov_pipe.generate(prompt, generation_config, streamer)

        return "".join(parts)

    def generate_text(self, prompt: str, max_new_tokens: Optional[int] = None) -> str:
        return self.stream_text(prompt, max_new_tokens=max_new_tokens)

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        return self.stream_text(prompt, on_text=run_manager.on_llm_new_token if run_manager else None)

    def _stream(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[GenerationChunk]:
        texts = TextQueue()
        cancel = threading.Event()
        errors: list = []

        def work():
            try:
                self.stream_text(prompt, on_text=texts.put, cancel=cancel)
            except Exception as exc:
                errors.append(exc)
            finally:
                texts.end()

        threading.Thread(target=work, daemon=True).start()
        try:
            for text in texts:
                chunk = GenerationChunk(text=text)
                if run_manager:
                    run_manager.on_llm_new_token(text, chunk=chunk)
                yield chunk
        finally:
            cancel.set()

        if errors:
            raise errors[0]
