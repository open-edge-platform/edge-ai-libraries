# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from io import BytesIO
import functools
import math
import os
import threading
from typing import Any, Callable, ClassVar, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple, Union, runtime_checkable

import numpy as np

from core.layout import (
    LayoutBlock,
    LayoutDetector,
    PPDocLayoutV3Runtime,
    as_pil_image,
    pp_doclayout_v3_onnx_path,
)
import config
from inference.meta import (
    RUNTIME_OV_CORE,
    RUNTIME_OV_GENAI,
    RUNTIME_OV_GME,
    RUNTIME_OV_LLAMAINDEX,
    RUNTIME_OV_OPTIMUM,
    InferenceMeta,
)
from llama_index.core.base.embeddings.base import DEFAULT_EMBED_BATCH_SIZE, BaseEmbedding
from llama_index.core.bridge.pydantic import Field, PrivateAttr
from llama_index.core.callbacks import CallbackManager, CBEventType, EventPayload
from llama_index.core.instrumentation import get_dispatcher
from llama_index.core.instrumentation.events.rerank import ReRankEndEvent, ReRankStartEvent
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.schema import MetadataMode, NodeWithScore, QueryBundle

dispatcher = get_dispatcher(__name__)


class OpenVINOGenAIEmbedding(InferenceMeta, BaseEmbedding):
    BACKEND: ClassVar[str] = config.LOCAL_OPENVINO
    RUNTIME: ClassVar[str] = RUNTIME_OV_GENAI
    SUPPORT_MULTIMODAL: ClassVar[Optional[bool]] = False

    model_path: str = Field(description="Local path.")
    max_length: Optional[int] = Field(description="Maximum length of input.")
    pooling: str = Field(description="Pooling strategy. One of ['cls', 'mean'].")
    normalize: bool = Field(default=True, description="Normalize embeddings or not.")
    query_instruction: Optional[str] = Field(description="Instruction to prepend to query text.")
    text_instruction: Optional[str] = Field(description="Instruction to prepend to text.")

    _ov_pipe: Any = PrivateAttr()
    _lock: Any = PrivateAttr()

    def __init__(
        self,
        model_path: str,
        pooling: str = "cls",
        max_length: int = 2048,
        pad_to_max_length: bool = False,
        normalize: bool = False,
        padding_side: Optional[str] = None,
        query_instruction: Optional[str] = None,
        text_instruction: Optional[str] = None,
        embed_batch_size: int = DEFAULT_EMBED_BATCH_SIZE,
        callback_manager: Optional[CallbackManager] = None,
        model_kwargs: Dict[str, Any] = {},
        device: Optional[str] = "auto",
    ):
        try:
            import openvino_genai
        except ImportError:
            raise ImportError("Could not import OpenVINO GenAI package. Install it with `pip install openvino-genai`.")

        if pooling not in ["cls", "mean"]:
            raise ValueError(f"Pooling {pooling} not supported.")

        config = openvino_genai.TextEmbeddingPipeline.Config()
        config.normalize = normalize
        if device == "NPU":
            config.batch_size = embed_batch_size
        config.pad_to_max_length = pad_to_max_length
        config.max_length = max_length
        if padding_side:
            config.padding_side = padding_side
        config.pooling_type = (
            openvino_genai.TextEmbeddingPipeline.PoolingType.MEAN
            if pooling == "mean"
            else openvino_genai.TextEmbeddingPipeline.PoolingType.CLS
        )
        config.query_instruction = query_instruction
        try:
            config.embed_instruction = text_instruction
        except Exception:
            pass
        super().__init__(
            embed_batch_size=embed_batch_size,
            callback_manager=callback_manager or CallbackManager([]),
            model_path=model_path,
            max_length=max_length,
            pooling=pooling,
            normalize=normalize,
            query_instruction=query_instruction,
            text_instruction=text_instruction,
            pad_to_max_length=pad_to_max_length,
        )
        self._ov_pipe = openvino_genai.TextEmbeddingPipeline(model_path, device, config, **model_kwargs)
        self._device = device
        self._model = self._ov_pipe
        # The pipeline drives a single infer request; concurrent embed calls must be serialized.
        self._lock = threading.Lock()

    @classmethod
    def class_name(cls) -> str:
        return "OpenVINOGenAIEmbedding"

    def _get_query_embedding(self, query: str) -> List[float]:
        with self._lock:
            return self._ov_pipe.embed_query(query)

    async def _aget_query_embedding(self, query: str) -> List[float]:
        with self._lock:
            return self._ov_pipe.embed_query(query)

    async def _aget_text_embedding(self, text: str) -> List[float]:
        with self._lock:
            return self._ov_pipe.embed_documents([text])[0]

    def _get_text_embedding(self, text: str) -> List[float]:
        with self._lock:
            return self._ov_pipe.embed_documents([text])[0]

    def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        with self._lock:
            return self._ov_pipe.embed_documents(texts)


@functools.lru_cache(maxsize=None)
def _serialized_openvino_embedding_class():
    from llama_index.embeddings.huggingface_openvino import OpenVINOEmbedding

    class SerializedOpenVINOEmbedding(InferenceMeta, OpenVINOEmbedding):
        """llama-index's OpenVINOEmbedding with `_embed` serialized ("Infer Request is busy")."""

        BACKEND: ClassVar[str] = config.LOCAL_OPENVINO
        RUNTIME: ClassVar[str] = RUNTIME_OV_LLAMAINDEX
        SUPPORT_MULTIMODAL: ClassVar[Optional[bool]] = False

        _lock: Any = PrivateAttr(default_factory=threading.Lock)

        @classmethod
        def class_name(cls) -> str:
            return "SerializedOpenVINOEmbedding"

        def _embed(self, sentences: List[str]) -> List[List[float]]:
            with self._lock:
                return super()._embed(sentences)

    return SerializedOpenVINOEmbedding


def serialized_openvino_embedding(**options) -> BaseEmbedding:
    """An `OpenVINOEmbedding(**options)` whose inference is serialized."""
    from core.embedding import require_openvino_model

    options["model_id_or_path"] = require_openvino_model(
        options["model_id_or_path"], "embedding model"
    )
    from transformers import AutoTokenizer
    options["model_kwargs"] = {
        **(options.get("model_kwargs") or {}),
        "local_files_only": True,
        "export": False,
    }
    # The upstream adapter does not forward model_kwargs to its tokenizer.
    if options.get("tokenizer") is None:
        options["tokenizer"] = AutoTokenizer.from_pretrained(
            options["model_id_or_path"], local_files_only=True
        )
    return _serialized_openvino_embedding_class()(**options)


@functools.lru_cache(maxsize=None)
def _llamaindex_rerank_class():
    from llama_index.postprocessor.openvino_rerank import OpenVINORerank

    class LlamaIndexOpenVINORerank(InferenceMeta, OpenVINORerank):
        BACKEND: ClassVar[str] = config.LOCAL_OPENVINO
        RUNTIME: ClassVar[str] = RUNTIME_OV_LLAMAINDEX
        SUPPORT_MULTIMODAL: ClassVar[Optional[bool]] = False

    return LlamaIndexOpenVINORerank


def llamaindex_openvino_rerank(**options) -> BaseNodePostprocessor:
    """An `OpenVINORerank(**options)` that reports its backend and runtime."""
    return _llamaindex_rerank_class()(**options)


class OpenVINOGenAIReranking(InferenceMeta, BaseNodePostprocessor):
    BACKEND: ClassVar[str] = config.LOCAL_OPENVINO
    RUNTIME: ClassVar[str] = RUNTIME_OV_GENAI
    SUPPORT_MULTIMODAL: ClassVar[Optional[bool]] = False

    model_id_or_path: str = Field(description="Huggingface model id or local path.")
    top_n: int = Field(description="Number of nodes to return sorted by score.")
    keep_retrieval_score: bool = Field(default=False, description="Whether to keep the retrieval score in metadata.")

    _ov_pipe: Any = PrivateAttr()

    def __init__(
        self,
        model_id_or_path: str,
        top_n: Optional[int] = 3,
        max_length: int = 2048,
        pad_to_max_length: bool = False,
        padding_side: Optional[str] = None,
        device: Optional[str] = "auto",
        model_kwargs: Dict[str, Any] = {},
        keep_retrieval_score: Optional[bool] = False,
    ):
        try:
            import openvino_genai
        except ImportError:
            raise ImportError("Could not import OpenVINO GenAI package. Install it with `pip install openvino-genai`.")

        super().__init__(
            top_n=top_n,
            max_length=max_length,
            model_id_or_path=model_id_or_path,
            device=device,
            keep_retrieval_score=keep_retrieval_score,
        )

        config = openvino_genai.TextRerankPipeline.Config()
        # top_n is fixed at construction; keep all candidates so a cached pipeline serves any top_n.
        config.top_n = np.iinfo(np.uintp).max
        if max_length:
            config.max_length = max_length
        config.pad_to_max_length = pad_to_max_length
        config.padding_side = padding_side
        self._ov_pipe = openvino_genai.TextRerankPipeline(model_id_or_path, device, config, **model_kwargs)
        self._model = self._ov_pipe
        self._device = device

    @classmethod
    def class_name(cls) -> str:
        return "OpenVINOGenAIReranking"

    def _postprocess_nodes(
        self, nodes: List[NodeWithScore], query_bundle: Optional[QueryBundle] = None
    ) -> List[NodeWithScore]:
        dispatcher.event(
            ReRankStartEvent(query=query_bundle, nodes=nodes, top_n=self.top_n, model_name=self.model_id_or_path)
        )
        if query_bundle is None:
            raise ValueError("Missing query bundle in extra info.")
        if len(nodes) == 0:
            return []

        nodes_text_list = [str(node.node.get_content(metadata_mode=MetadataMode.EMBED)) for node in nodes]
        with self.callback_manager.event(
            CBEventType.RERANKING,
            payload={
                EventPayload.NODES: nodes,
                EventPayload.MODEL_NAME: self.model_id_or_path,
                EventPayload.QUERY_STR: query_bundle.query_str,
                EventPayload.TOP_K: self.top_n,
            },
        ) as event:
            outputs = self._ov_pipe.rerank(query_bundle.query_str, nodes_text_list)
            ranked = []
            # Copy nodes so reranking cannot overwrite recall scores/metadata.
            for index, score in outputs:
                node = nodes[index].model_copy(deep=True)
                if self.keep_retrieval_score:
                    node.node.metadata["retrieval_score"] = node.score
                node.score = float(score)
                ranked.append(node)
            ranked.sort(key=lambda node: node.score, reverse=True)
            ranked = ranked[:self.top_n]
            event.on_end(payload={EventPayload.NODES: ranked})

        dispatcher.event(ReRankEndEvent(nodes=ranked))
        return ranked


from inference.multimodal.qwen3_vl_reranker_ov import OpenVINOVLReranking


class OpenVINOVLReranker(InferenceMeta, BaseNodePostprocessor):
    """Request-scoped LlamaIndex postprocessor over the Qwen VL media scorer."""

    BACKEND: ClassVar[str] = config.LOCAL_OPENVINO
    RUNTIME: ClassVar[str] = RUNTIME_OV_CORE
    SUPPORT_MULTIMODAL: ClassVar[Optional[bool]] = True

    model_id_or_path: str
    top_n: int

    _scorer: Any = PrivateAttr()
    _document_fn: Callable = PrivateAttr()

    def __init__(self, model_id_or_path: str, top_n: int, scorer: Any, document_fn: Callable):
        super().__init__(model_id_or_path=model_id_or_path, top_n=top_n)
        self._scorer = scorer
        self._document_fn = document_fn

    @classmethod
    def class_name(cls) -> str:
        return "OpenVINOVLReranker"

    def _postprocess_nodes(
        self, nodes: List[NodeWithScore], query_bundle: Optional[QueryBundle] = None
    ) -> List[NodeWithScore]:
        if query_bundle is None:
            raise ValueError("Missing query bundle in extra info.")
        dispatcher.event(ReRankStartEvent(
            query=query_bundle, nodes=nodes, top_n=self.top_n,
            model_name=self.model_id_or_path,
        ))
        if not nodes:
            dispatcher.event(ReRankEndEvent(nodes=[]))
            return []

        with self.callback_manager.event(
            CBEventType.RERANKING,
            payload={
                EventPayload.NODES: nodes,
                EventPayload.MODEL_NAME: self.model_id_or_path,
                EventPayload.QUERY_STR: query_bundle.query_str,
                EventPayload.TOP_K: self.top_n,
            },
        ) as event:
            documents = [
                self._document_fn(index, item.node) for index, item in enumerate(nodes)
            ]
            scores = self._scorer.score_batch(query_bundle.query_str, documents)

            # Commit only after every retained candidate has a valid score.
            result = []
            for item, score in zip(nodes, scores):
                if not math.isfinite(score):
                    raise ValueError("nonfinite media rerank score")
                output = item.model_copy(deep=True)
                output.score = score
                result.append(output)
            result.sort(key=lambda item: item.score, reverse=True)
            result = result[:self.top_n]
            event.on_end(payload={EventPayload.NODES: result})

        dispatcher.event(ReRankEndEvent(nodes=result))
        return result


# --- document layout ---------------------------------------------------------


class OpenVINOLayoutDetector(InferenceMeta, LayoutDetector):
    """PP-DocLayoutV3 OpenVINO inference as a `LayoutDetector`, compiled lazily on first `detect`."""

    BACKEND: ClassVar[str] = config.LOCAL_OPENVINO
    RUNTIME: ClassVar[str] = RUNTIME_OV_CORE

    def __init__(
        self,
        model_path: str,
        device: str = "CPU",
        model_id: Optional[str] = None,
        score_threshold: float = 0.5,
        compiled_model: Any = None,
        image_processor: Any = None,
        id2label: Optional[Mapping[int, str]] = None,
    ):
        self.model_path = model_path
        self.device = device
        self.model_id = model_id
        self.score_threshold = float(score_threshold)
        self._compiled = compiled_model
        self._inference_batch_size = None
        self._runtime = PPDocLayoutV3Runtime(
            score_threshold=self.score_threshold,
            image_processor=image_processor,
            id2label=id2label,
        )
        self._lock = threading.Lock()

    def _ensure_loaded(self) -> None:
        if self._compiled is not None:
            return
        with self._lock:
            if self._compiled is not None:
                return
            from core.embedding import resolve_model_path

            resolved = resolve_model_path(self.model_path)
            model_dir = resolved
            model_file = pp_doclayout_v3_onnx_path(model_dir)
            if not os.path.isfile(model_file):
                raise FileNotFoundError(
                    f"No prepared PP-DocLayoutV3 ONNX model at {model_file!r}. "
                    "Prepare it with scripts/export_pp_doclayout_v3.py before "
                    "starting the engine; runtime downloading/exporting is disabled."
                )
            import openvino as ov

            core = ov.Core()
            if self.device.upper().split(".", 1)[0] == "GPU":
                model = core.read_model(model_file)
                input_shape = model.input().get_partial_shape()
                input_shape[0] = 1
                model.reshape({model.input(): input_shape})
                self._compiled = core.compile_model(model, self.device)
                self._inference_batch_size = 1
            else:
                self._compiled = core.compile_model(model_file, self.device)
            self._runtime.load_metadata(model_dir)

    def detect(self, images: Sequence[Any]) -> List[List[LayoutBlock]]:
        self._ensure_loaded()

        pils = [as_pil_image(image) for image in images]
        if not pils:
            return []
        pixel_values = self._runtime.preprocess(pils)
        input_name = "pixel_values"
        if hasattr(self._compiled, "inputs"):
            input_name = self._compiled.inputs[0].get_any_name()
        if self._inference_batch_size == 1:
            outputs = [
                self._run({input_name: pixel_values[index:index + 1]})
                for index in range(len(pils))
            ]
            logits = np.concatenate([output[0] for output in outputs])
            boxes = np.concatenate([output[1] for output in outputs])
        else:
            logits, boxes = self._run({input_name: pixel_values})
        return self._runtime.postprocess(
            logits,
            boxes,
            [(pil.width, pil.height) for pil in pils],
        )

    def _run(
        self, inputs: Mapping[str, Any]
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Resolve raw OpenVINO outputs to `(logits, pred_boxes)` arrays."""
        result = self._compiled(inputs)
        if not hasattr(self._compiled, "outputs"):
            return np.asarray(result["logits"]), np.asarray(result["pred_boxes"])
        ports = list(self._compiled.outputs)
        arrays = [np.asarray(result[port]) for port in ports]
        logits = boxes = None
        for port, array in zip(ports, arrays):
            try:
                name = " ".join(port.get_names()).lower()
            except Exception:  # noqa: BLE001
                name = ""
            if "logit" in name:
                logits = array
            elif "box" in name:
                boxes = array
        if logits is None:
            logits = arrays[0]
        if boxes is None:
            boxes = arrays[1] if len(arrays) > 1 else arrays[0]
        return logits, boxes


# --- multimodal OV embedding --------------------------------------------------


@runtime_checkable
class OVEmbeddingRuntime(Protocol):
    """The model-specific inference half `MultimodalOVEmbedding` drives; methods return ``(N, D)`` arrays."""

    def get_text_embeddings(
        self,
        texts: Sequence[str],
        instruction: Optional[str] = None,
        is_query: bool = True,
        show_progress_bar: bool = False,
    ) -> Any:
        ...

    def get_fused_embeddings(
        self,
        texts: Sequence[Any],
        images: Sequence[Any],
        is_query: bool = True,
        show_progress_bar: bool = False,
    ) -> Any:
        ...

    def get_image_embeddings(
        self,
        images: Sequence[Any],
        is_query: bool = True,
        show_progress_bar: bool = False,
    ) -> Any:
        ...


class MultimodalOVEmbedding(InferenceMeta, BaseEmbedding):
    """A llama-index `BaseEmbedding` over an `OVEmbeddingRuntime`, with extra fused and image paths."""

    BACKEND: ClassVar[str] = config.LOCAL_OPENVINO
    RUNTIME: ClassVar[str] = RUNTIME_OV_GME
    SUPPORT_MULTIMODAL: ClassVar[Optional[bool]] = True

    query_instruction: Optional[str] = Field(
        default=None, description="Instruction prepended to a query (is_query=True)."
    )
    fused_instruction: Optional[str] = Field(
        default=None,
        description="Instruction for the fused image+text corpus side; None keeps the default.",
    )

    _runtime: Any = PrivateAttr()
    _supported_roles: Any = PrivateAttr(default=frozenset())

    def __init__(
        self,
        runtime: OVEmbeddingRuntime,
        query_instruction: Optional[str] = None,
        fused_instruction: Optional[str] = None,
        embed_batch_size: int = DEFAULT_EMBED_BATCH_SIZE,
        callback_manager: Optional[CallbackManager] = None,
        supported_roles: Sequence[str] = (),
    ):
        super().__init__(
            embed_batch_size=embed_batch_size,
            callback_manager=callback_manager or CallbackManager([]),
            query_instruction=query_instruction,
            fused_instruction=fused_instruction,
        )
        self._runtime = runtime
        self._supported_roles = frozenset(supported_roles)

    @classmethod
    def class_name(cls) -> str:
        return "MultimodalOVEmbedding"

    # --- `core.multimodal.MultimodalEmbedding` contract ---

    @property
    def dimension(self) -> int:
        return int(self._runtime.embedding_dim)

    @property
    def supported_roles(self) -> frozenset:
        return self._supported_roles

    @property
    def model_path(self) -> str:
        return str(self._runtime.model_dir)

    @property
    def device(self) -> str:
        return self._runtime.device

    @property
    def max_image_tokens(self) -> int:
        return self._runtime.max_image_tokens

    # The runtime returns an (N, D) L2-normalized np.ndarray.
    def _encode(self, texts: List[str], is_query: bool) -> List[List[float]]:
        instruction = self.query_instruction if is_query else None
        arr = self._runtime.get_text_embeddings(
            texts, instruction=instruction, is_query=is_query, show_progress_bar=False
        )
        return arr.tolist()

    def _get_query_embedding(self, query: str) -> List[float]:
        return self._encode([query], is_query=True)[0]

    def _get_text_embedding(self, text: str) -> List[float]:
        return self._encode([text], is_query=False)[0]

    def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        return self._encode(list(texts), is_query=False)

    # --- fused (image + reference text) ---------------------------------------

    @staticmethod
    def _as_image(image: Union[bytes, bytearray, Any]):
        """A PIL image from raw bytes; a path or PIL image is passed through."""
        if isinstance(image, (bytes, bytearray)):
            from PIL import Image

            return Image.open(BytesIO(bytes(image))).convert("RGB")
        return image

    def get_fused_embeddings(
        self, texts: Sequence[str], images: Sequence[Any]
    ) -> List[List[float]]:
        """One joint vector per (text, image) pair, in the runtime's unified space."""
        texts = list(texts)
        pixels = [self._as_image(image) for image in images]
        if len(texts) != len(pixels):
            raise ValueError("texts and images must have the same length")
        arr = self._runtime.get_fused_embeddings(
            texts=texts, images=pixels, is_query=False,
            instruction=self.fused_instruction, show_progress_bar=False
        )
        return arr.tolist()

    def get_fused_embedding(self, text: str, image: Any) -> List[float]:
        return self.get_fused_embeddings([text], [image])[0]

    def get_image_embeddings(self, images: Sequence[Any]) -> List[List[float]]:
        """One vector per image, in the same space as the text path."""
        images = [self._as_image(image) for image in images]
        if not images:
            return []
        arr = self._runtime.get_image_embeddings(
            images, is_query=False, show_progress_bar=False
        )
        return arr.tolist()

    async def _aget_query_embedding(self, query: str) -> List[float]:
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text: str) -> List[float]:
        return self._get_text_embedding(text)

    async def _aget_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        return self._get_text_embeddings(texts)
