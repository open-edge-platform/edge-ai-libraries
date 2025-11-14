# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Qwen text embedding handler with OpenVINO acceleration."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Union, Any

import torch
import torch.nn.functional as F
from torch import Tensor
from transformers import AutoModel, AutoTokenizer

from ..base import BaseEmbeddingModel
from ...utils import logger

try:  # pragma: no cover - optional dependency at runtime
    from optimum.intel import OVModelForFeatureExtraction  # type: ignore
except Exception:  # pragma: no cover - handled at runtime
    OVModelForFeatureExtraction = None  # type: ignore


class QwenEmbeddingHandler(BaseEmbeddingModel):
    """Handler for Qwen text embedding models."""

    DEFAULT_TASK_DESCRIPTION = (
        "Given a web search query, retrieve relevant passages that answer the query"
    )
    INSTRUCTION_TEMPLATE = "Instruct: {task_description}\nQuery:{query}"

    def __init__(self, model_config: Dict[str, Any]):
        config = dict(model_config)
        config.setdefault("modalities", ["text"])
        super().__init__(config)
        self.model_config = config

        self.hf_model_id: str = config["hf_model_id"]
        self.max_length: int = config.get("max_length", 8192)
        self.task_description: str = config.get(
            "task_description", self.DEFAULT_TASK_DESCRIPTION
        )
        self.instruction_template: str = config.get(
            "instruction_template", self.INSTRUCTION_TEMPLATE
        )
        self.weight_format: str = config.get("weight_format", "int8").lower()
        self.revision: str | None = config.get("revision")
        self.trust_remote_code: bool = bool(config.get("trust_remote_code", True))
        self.use_openvino: bool = bool(config.get("use_openvino", False))
        self.device: str = config.get("device", "CPU")

        self.model = None
        self.tokenizer = None
        self._embedding_dim: int | None = None

    # ------------------------------------------------------------------
    # Base overrides
    # ------------------------------------------------------------------
    def load_model(self) -> None:
        """Load tokenizer and either Torch or OpenVINO model."""
        logger.info(
            "Loading Qwen embedding model %s using %s",
            self.hf_model_id,
            "OpenVINO" if self.use_openvino else "PyTorch",
        )
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.hf_model_id,
            trust_remote_code=self.trust_remote_code,
            padding_side="left",
            revision=self.revision,
        )

        if self.use_openvino:
            if OVModelForFeatureExtraction is None:
                raise RuntimeError(
                    "optimum-intel is required for OpenVINO execution but could not be imported"
                )
            self.model = self._load_openvino_model()
        else:
            self.model = AutoModel.from_pretrained(
                self.hf_model_id,
                trust_remote_code=self.trust_remote_code,
                revision=self.revision,
            )
            self.model.eval()
            # Keep model on CPU for PyTorch inference (text embeddings work well on CPU)
        logger.info("Qwen model loaded successfully")

    def encode_text(self, texts: Union[str, List[str]]) -> torch.Tensor:
        if isinstance(texts, str):
            texts = [texts]
        prepared_texts = self.prepare_documents(list(texts))
        tokenized = self.tokenizer(
            prepared_texts,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        # Tokenized tensors stay on CPU (model is on CPU or handled by OpenVINO)

        if self.use_openvino:
            outputs = self.model(**tokenized)
        else:
            with torch.no_grad():
                outputs = self.model(**tokenized)

        embeddings = self._last_token_pool(
            outputs.last_hidden_state, tokenized["attention_mask"]
        )
        embeddings = F.normalize(embeddings, p=2, dim=1)
        embeddings = embeddings.to(torch.float32).cpu()
        if self._embedding_dim is None:
            self._embedding_dim = embeddings.shape[-1]
        return embeddings

    def encode_image(self, images):  # pragma: no cover - should be guarded upstream
        raise NotImplementedError("Qwen text embedding handler does not support images")

    def convert_to_openvino(self, ov_models_dir: str) -> tuple:
        xml_path = self._export_openvino(Path(ov_models_dir))
        return (str(xml_path),)

    def get_embedding_dim(self) -> int:
        if self._embedding_dim is not None:
            return self._embedding_dim
        probe = self.prepare_documents(["embedding-dimension-probe"])
        embedding = self.encode_text(probe)
        self._embedding_dim = int(embedding.shape[-1])
        return self._embedding_dim

    def prepare_query(self, text: str) -> str:
        return self.instruction_template.format(
            task_description=self.task_description,
            query=text,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _load_openvino_model(self):
        xml_path = self._export_openvino(Path(self.ov_models_dir))
        logger.info("Loading OpenVINO model from %s on %s", xml_path, self.device)
        return OVModelForFeatureExtraction.from_pretrained(
            xml_path.parent,
            device=self.device,
            export=False,
            trust_remote_code=self.trust_remote_code,
        )

    def _export_openvino(self, base_dir: Path) -> Path:
        export_dir = base_dir / self._sanitized_model_dir() / self.weight_format.upper()
        export_dir.mkdir(parents=True, exist_ok=True)
        xml_path = export_dir / "openvino_model.xml"
        if xml_path.exists():
            logger.info("Reusing existing OpenVINO artifacts at %s", export_dir)
            return xml_path

        if OVModelForFeatureExtraction is None:
            raise RuntimeError(
                "optimum-intel is required for OpenVINO export but could not be imported"
            )

        logger.info(
            "Exporting Qwen model %s to OpenVINO (%s) at %s",
            self.hf_model_id,
            self.weight_format.upper(),
            export_dir,
        )
        self._export_via_python_api(export_dir)
        return xml_path

    def _export_via_python_api(self, export_dir: Path) -> None:
        """
        Export model to OpenVINO format using optimum-intel Python API.
        
        This is equivalent to:
        optimum-cli export openvino --model <model> --task feature-extraction 
                                    --weight-format <format> --trust-remote-code
        """
        try:
            logger.info("Exporting model using optimum-intel Python API...")
            
            # Determine weight quantization parameter
            # int8/int4 -> load_in_8bit=True/load_in_4bit=True (applied during export)
            export_kwargs = {
                "export": True,  # Trigger conversion from PyTorch to OpenVINO
                "trust_remote_code": self.trust_remote_code,
            }
            
            if self.revision:
                export_kwargs["revision"] = self.revision
            
            # Apply weight compression based on format
            if self.weight_format == "int8":
                export_kwargs["load_in_8bit"] = True
            elif self.weight_format == "int4":
                export_kwargs["load_in_4bit"] = True
            # fp16/fp32 don't need special flags (default behavior)
            
            # Export using OVModelForFeatureExtraction
            logger.debug(f"Export kwargs: {export_kwargs}")
            ov_model = OVModelForFeatureExtraction.from_pretrained(
                self.hf_model_id,
                **export_kwargs
            )
            
            # Save the exported model
            logger.info(f"Saving exported model to {export_dir}")
            ov_model.save_pretrained(export_dir)
            logger.info("Export completed successfully")
            # Clean up
            del ov_model
            logger.debug("Cleaned up export model from memory")
            
        except Exception as exc:
            raise RuntimeError(
                f"Failed to export model {self.hf_model_id} to OpenVINO format: {exc}"
            ) from exc

    @staticmethod
    def _last_token_pool(last_hidden_states: Tensor, attention_mask: Tensor) -> Tensor:
        left_padding = attention_mask[:, -1].sum() == attention_mask.shape[0]
        if left_padding:
            return last_hidden_states[:, -1]
        sequence_lengths = attention_mask.sum(dim=1) - 1
        batch_size = last_hidden_states.shape[0]
        return last_hidden_states[
            torch.arange(batch_size, device=last_hidden_states.device),
            sequence_lengths,
        ]

    def _sanitized_model_dir(self) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9]+", "_", self.hf_model_id)
        return sanitized.lower().strip("_")