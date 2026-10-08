import json
import sys
import threading
import time
import types

import numpy as np
import pytest
from langchain_core.documents import Document

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")
from transformers.modeling_outputs import BaseModelOutput, SequenceClassifierOutput  # noqa: E402


class FakeStaticEncoder:
    """Stands in for an optimum encoder compiled with a static batch size."""

    def __init__(self, batch_size, output="hidden"):
        self.batch_size = batch_size
        self.output = output
        self.calls = []
        self.request = "compiled-model"

    def __call__(self, input_ids, attention_mask, **kwargs):
        assert input_ids.shape[0] == self.batch_size
        self.calls.append((input_ids.clone(), kwargs))
        if self.output == "hidden":
            return BaseModelOutput(last_hidden_state=input_ids.float().unsqueeze(-1).repeat(1, 1, 3))
        return SequenceClassifierOutput(logits=input_ids[:, :1].float())


def test_static_batch_model_pads_and_trims():
    from app.openvino_xpu import StaticBatchModel

    encoder = FakeStaticEncoder(batch_size=2)
    model = StaticBatchModel(encoder, batch_size=2)
    input_ids = torch.arange(15).reshape(5, 3)

    out = model(input_ids=input_ids, attention_mask=torch.ones_like(input_ids))

    assert len(encoder.calls) == 3
    # The last chunk repeats its last row to fill the static batch.
    assert encoder.calls[-1][0].tolist() == [[12, 13, 14], [12, 13, 14]]
    assert out[0].shape == (5, 3, 3)
    assert torch.equal(out.last_hidden_state[:, :, 0], input_ids.float())
    # Attributes such as `request` (read by langchain for the static length) are forwarded.
    assert model.request == "compiled-model"


def test_static_batch_model_keeps_keyword_arguments():
    from app.openvino_xpu import StaticBatchModel

    encoder = FakeStaticEncoder(batch_size=2, output="logits")
    model = StaticBatchModel(encoder, batch_size=2)
    input_ids = torch.tensor([[7, 1], [8, 1], [9, 1]])

    out = model(input_ids=input_ids, attention_mask=torch.ones_like(input_ids), return_dict=True)

    assert out[0].flatten().tolist() == [7.0, 8.0, 9.0]
    assert all(kwargs == {"return_dict": True} for _, kwargs in encoder.calls)


def test_make_static_reshapes_compiles_and_clamps_length():
    from app.openvino_xpu import StaticBatchModel, make_static

    class Model:
        config = types.SimpleNamespace(max_position_embeddings=256)
        _device = "NPU"

        def __init__(self):
            self.calls = []

        def reshape(self, batch, seq):
            self.calls.append(("reshape", batch, seq))

        def compile(self):
            self.calls.append(("compile",))

    model = Model()
    wrapped = make_static(model, 2, 512)

    assert isinstance(wrapped, StaticBatchModel)
    assert wrapped.batch_size == 2
    assert model.calls == [("reshape", 2, 256), ("compile",)]
    from app.openvino_xpu import npu_lock

    assert wrapped._lock is npu_lock


class FakeStreamingStatus:
    RUNNING = "running"
    CANCEL = "cancel"


class FakeGenerationConfig:
    max_new_tokens = 0
    apply_chat_template = True


class FakeTokenizer:
    def encode(self, text):
        n = len(text.split())
        return types.SimpleNamespace(input_ids=types.SimpleNamespace(get_shape=lambda: [1, n]))


class FakeOVPipe:
    """Stands in for openvino_genai.LLMPipeline."""

    def __init__(self, chunks=None):
        self.chunks = chunks
        self.calls = []
        self.produced = 0

    def get_tokenizer(self):
        return FakeTokenizer()

    def get_generation_config(self):
        return FakeGenerationConfig()

    def generate(self, prompt, generation_config, streamer):
        self.calls.append((prompt, generation_config.max_new_tokens, generation_config.apply_chat_template))
        chunks = self.chunks if self.chunks is not None else (f"t{i} " for i in range(1000))
        for chunk in chunks:
            self.produced += 1
            if streamer(chunk) == FakeStreamingStatus.CANCEL:
                break
            time.sleep(0.001)


@pytest.fixture
def fake_genai(monkeypatch):
    module = types.ModuleType("openvino_genai")
    module.StreamingStatus = FakeStreamingStatus
    module.LLMPipeline = None
    monkeypatch.setitem(sys.modules, "openvino_genai", module)
    return module


def make_genai_llm(pipe, max_prompt_tokens=None):
    from app.openvino_xpu import GenAILLM

    return GenAILLM(ov_pipe=pipe, max_new_tokens=100, max_prompt_tokens=max_prompt_tokens)


def test_genai_llm_generates_raw_prompt(fake_genai):
    pipe = FakeOVPipe(chunks=["Hello", " world"])
    llm = make_genai_llm(pipe)

    assert llm.invoke("Human: hi") == "Hello world"
    assert llm.generate_text("prompt", max_new_tokens=8) == "Hello world"
    # The prompt template is already applied; the generation length never exceeds MAX_TOKENS.
    assert pipe.calls == [("Human: hi", 100, False), ("prompt", 8, False)]


def test_genai_llm_streams_chunks(fake_genai):
    llm = make_genai_llm(FakeOVPipe(chunks=["a", "b", "c"]))

    assert [chunk for chunk in llm.stream("prompt")] == ["a", "b", "c"]


def test_genai_llm_stops_on_cancel(fake_genai):
    pipe = FakeOVPipe()
    llm = make_genai_llm(pipe)
    cancel = threading.Event()
    seen = []

    def on_text(text):
        seen.append(text)
        if len(seen) == 3:
            cancel.set()

    llm.stream_text("prompt", on_text=on_text, cancel=cancel)

    assert pipe.produced == 3


def test_genai_llm_rejects_long_prompt(fake_genai):
    from app.openvino_xpu import PromptTooLongError

    pipe = FakeOVPipe(chunks=["x"])
    llm = make_genai_llm(pipe, max_prompt_tokens=3)

    with pytest.raises(PromptTooLongError):
        llm.generate_text("one two three four")
    assert pipe.calls == []
    assert llm.generate_text("one two three") == "x"


def test_genai_llm_load_sets_npu_properties(fake_genai):
    from app.openvino_xpu import GenAILLM

    created = {}

    def pipeline(model_dir, device, **properties):
        created.update(model_dir=model_dir, device=device, properties=properties)
        return FakeOVPipe()

    fake_genai.LLMPipeline = pipeline
    llm = GenAILLM.load("/m/npu", "NPU", max_new_tokens=512, max_prompt_tokens=4096, cache_dir="/m/npu/cache")

    assert created == {
        "model_dir": "/m/npu",
        "device": "NPU",
        "properties": {"CACHE_DIR": "/m/npu/cache", "MAX_PROMPT_LEN": 4096, "MIN_RESPONSE_LEN": 512},
    }
    assert llm.max_prompt_tokens == 4096

    gpu = GenAILLM.load("/m/npu", "GPU", max_new_tokens=512, max_prompt_tokens=4096)
    assert created["properties"] == {}
    assert gpu.max_prompt_tokens is None


class OverlapProbe:
    """Records whether two inferences ran at the same time."""

    def __init__(self):
        self.active = 0
        self.overlapped = False
        self._guard = threading.Lock()

    def run(self):
        with self._guard:
            self.active += 1
            self.overlapped |= self.active > 1
        time.sleep(0.05)
        with self._guard:
            self.active -= 1


def test_npu_models_never_infer_concurrently(fake_genai):
    """Two NPU models inferring at the same time fault the NPU (MMU translation fault)."""

    from app.openvino_xpu import GenAILLM, StaticBatchModel, npu_lock

    probe = OverlapProbe()

    class ProbeEncoder(FakeStaticEncoder):
        def __call__(self, input_ids, attention_mask, **kwargs):
            probe.run()
            return super().__call__(input_ids, attention_mask, **kwargs)

    class ProbePipe(FakeOVPipe):
        def generate(self, prompt, config, streamer=None):
            probe.run()
            return super().generate(prompt, config, streamer)

    fake_genai.LLMPipeline = lambda model_dir, device, **properties: ProbePipe()
    llm = GenAILLM.load("/m/npu", "NPU", max_new_tokens=8, max_prompt_tokens=4096)
    embedder = StaticBatchModel(ProbeEncoder(2), batch_size=2, lock=npu_lock)
    reranker = StaticBatchModel(ProbeEncoder(2), batch_size=2, lock=npu_lock)
    ids = torch.ones((2, 4), dtype=torch.long)

    workers = [
        threading.Thread(target=llm.generate_text, args=("question",)),
        threading.Thread(target=lambda: embedder(input_ids=ids, attention_mask=ids)),
        threading.Thread(target=lambda: reranker(input_ids=ids, attention_mask=ids)),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert not probe.overlapped


def test_gpu_models_do_not_share_the_npu_lock(fake_genai):
    from app.openvino_xpu import GenAILLM, StaticBatchModel, npu_lock

    fake_genai.LLMPipeline = lambda model_dir, device, **properties: FakeOVPipe()
    assert GenAILLM.load("/m/npu", "GPU", max_new_tokens=8)._lock is not npu_lock
    assert StaticBatchModel(FakeStaticEncoder(2), batch_size=2)._lock is None


# --- chain.py with the GenAI LLM (NPU) ---------------------------------------------------

DOCS = [
    Document(page_content="alpha " * 5, metadata={"source": "/d/a.pdf", "page": 0}),
    Document(page_content="beta " * 5, metadata={"source": "/d/b.pdf", "page": 1}),
    Document(page_content="gamma " * 5, metadata={"source": "/d/c.pdf", "page": 2}),
]


class FakeVectorStore:
    def __init__(self, docs):
        self.docs = docs

    def as_retriever(self, **kwargs):
        docs = self.docs
        return types.SimpleNamespace(invoke=lambda query: list(docs))


class PassThroughReranker:
    top_n = 3

    def compress_documents(self, documents, query):
        return [
            Document(page_content=d.page_content, metadata={"id": i, "relevance_score": 1.0 - 0.1 * i})
            for i, d in enumerate(documents)
        ]


@pytest.fixture
def chain(mocker):
    from langchain_core.prompts import ChatPromptTemplate

    from app import chain as chain_module
    from app.config import config

    mocker.patch.object(config, "_ENABLE_RERANK", True)
    mocker.patch.object(chain_module, "prompt", ChatPromptTemplate.from_template("{context}\nQ: {question}"), create=True)
    mocker.patch.object(chain_module, "vectorstore", FakeVectorStore(DOCS))
    mocker.patch.object(chain_module, "reranker", PassThroughReranker(), create=True)
    return chain_module


def test_fit_documents_drops_lowest_ranked(fake_genai, mocker, chain):
    llm = make_genai_llm(FakeOVPipe(), max_prompt_tokens=22)
    mocker.patch.object(chain, "llm", llm)

    fitted = chain.fit_documents(DOCS, "question")

    assert [d.metadata["source"] for d in fitted] == ["/d/a.pdf", "/d/b.pdf"]
    assert llm.count_tokens(chain._render_prompt(fitted, "question")) <= 22


def test_fit_documents_without_limit(mocker, chain):
    mocker.patch.object(chain, "llm", object())

    assert chain.fit_documents(DOCS, "question") is DOCS


def test_chat_stream_with_genai_llm(test_client, fake_genai, mocker, chain):
    from app.config import config

    mocker.patch.object(config, "RETURN_SOURCES", True)
    pipe = FakeOVPipe(chunks=["1. Alpha", "\n", "2. Beta [S2]"])
    mocker.patch.object(chain, "llm", make_genai_llm(pipe, max_prompt_tokens=22))

    response = test_client.post("/chat", json={"input": "How?", "stream": True})

    assert response.status_code == 200
    frames = [f for f in response.text.split("\n\n") if f]
    assert frames[0].startswith("event: sources\ndata: ")
    sources = json.loads(frames[0].split("data: ", 1)[1])["sources"]
    # Only the chunks that fit the NPU prompt limit are sent and cited.
    assert [s["source"] for s in sources] == ["a.pdf", "b.pdf"]
    assert "".join(line[6:] for f in frames[1:] for line in f.split("\n")) == "1. Alpha2. Beta [S2]"
    assert pipe.calls[0][0].startswith("Human: [S1] a.pdf, page 1\n")


def test_chat_json_with_genai_llm(test_client, fake_genai, mocker, chain):
    from app.config import config

    mocker.patch.object(config, "RETURN_SOURCES", True)
    mocker.patch.object(chain, "llm", make_genai_llm(FakeOVPipe(chunks=["Answer [S1]."])))

    response = test_client.post("/chat", json={"input": "How?", "stream": False})

    assert response.status_code == 200
    assert response.json()["metadata"] == "Answer [S1]."
    assert len(response.json()["sources"]) == 3


def test_retrieval_query_with_genai_llm(fake_genai, mocker, chain):
    from app.config import config

    pipe = FakeOVPipe(chunks=["  How to torque?\n", "extra"])
    mocker.patch.object(chain, "llm", make_genai_llm(pipe))
    mocker.patch.object(config, "RETRIEVAL_TRANSLATE_PROMPT", "Translate: {question}")

    assert chain.retrieval_query("Jak?") == "How to torque?"
    assert pipe.calls == [("Translate: Jak?", 64, False)]


async def test_stream_answer_with_genai_stops_when_consumer_goes_away(fake_genai, mocker, chain):
    pipe = FakeOVPipe()
    mocker.patch.object(chain, "llm", make_genai_llm(pipe))

    stream = chain.stream_answer("prompt")
    assert (await stream.__anext__()) == "t0 "
    await stream.aclose()

    assert chain._generation_lock.acquire(timeout=5)
    chain._generation_lock.release()
    assert pipe.produced < 1000


# --- openvino_backend wiring ---------------------------------------------------------------

def test_encoder_compile_per_device(mocker):
    from app import openvino_backend
    from app.config import config
    from app.openvino_xpu import StaticBatchModel

    backend = openvino_backend.OpenVINOBackend()
    backend.cache_dir = "/cache"

    assert backend._encoder_kwargs("org/emb", "GPU") == {"device": "GPU", "compile": False}
    assert backend._encoder_kwargs("org/emb", "NPU") == {
        "device": "NPU",
        "compile": False,
        "ov_config": {"CACHE_DIR": "/cache/org/emb/model_cache"},
    }

    model = mocker.Mock(config=types.SimpleNamespace(max_position_embeddings=512))
    assert backend._compile_encoder(model, "GPU", 4) is model
    model.compile.assert_called_once_with()

    # Embedding and reranker have their own static batch on NPU.
    for batch in (config.NPU_EMBEDDING_BATCH, config.NPU_RERANKER_BATCH):
        model = mocker.Mock(config=types.SimpleNamespace(max_position_embeddings=512))
        wrapped = backend._compile_encoder(model, "NPU", batch)
        assert isinstance(wrapped, StaticBatchModel)
        model.reshape.assert_called_once_with(batch, config.NPU_ENCODER_SEQ_LEN)
    assert (config.NPU_EMBEDDING_BATCH, config.NPU_RERANKER_BATCH, config.NPU_ENCODER_SEQ_LEN) == (4, 2, 512)


def test_init_models_uses_genai_for_npu_llm(mocker):
    from app import openvino_backend

    backend = openvino_backend.OpenVINOBackend()
    backend.cache_dir = "/cache"
    backend.llm_device = "NPU"
    backend.embedding_device = "CPU"
    backend.reranker_device = "CPU"
    backend.huggingface_token = ""
    backend.llm_npu_model_dir = "/cache/org/llm/npu"
    mocker.patch.object(backend, "download_huggingface_model")
    mocker.patch.object(backend, "convert_model")
    convert_npu = mocker.patch.object(backend, "convert_npu_llm")
    mocker.patch.object(openvino_backend, "OpenVINOBgeEmbeddings")
    mocker.patch.object(openvino_backend, "OpenVINOReranker")
    hf_pipeline = mocker.patch.object(openvino_backend, "HuggingFacePipeline")
    load = mocker.patch.object(openvino_backend.GenAILLM, "load", return_value="genai-llm")

    _, llm, _ = backend.init_models()

    assert llm == "genai-llm"
    convert_npu.assert_called_once_with(backend.llm_model_id, "/cache/org/llm/npu")
    hf_pipeline.from_model_id.assert_not_called()
    assert load.call_args.args == ("/cache/org/llm/npu", "NPU")
    assert load.call_args.kwargs["max_prompt_tokens"] == 4096
    assert load.call_args.kwargs["cache_dir"] == "/cache/org/llm/npu/model_cache"


def test_convert_npu_llm_skips_existing_export(tmp_path, mocker):
    from app import openvino_backend

    (tmp_path / "openvino_model.xml").write_text("")
    export = mocker.patch.object(openvino_backend.OVModelForCausalLM, "from_pretrained")

    openvino_backend.OpenVINOBackend().convert_npu_llm("org/llm", str(tmp_path))

    export.assert_not_called()


def test_npu_lock_settles_between_jobs():
    """Back-to-back jobs of different NPU models also fault the NPU without a short gap."""

    from app.openvino_xpu import NpuLock

    lock = NpuLock(settle_s=0.05)
    with lock:
        pass
    started = time.monotonic()
    with lock:
        waited = time.monotonic() - started

    assert waited >= 0.04
