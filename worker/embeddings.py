"""Local ONNX encoder. The pinned revision defines the stored vector space."""
import os

import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from huggingface_hub.errors import LocalEntryNotFoundError
from tokenizers import Tokenizer

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"


class Encoder:
    def __init__(self):
        def asset(name):
            try:
                return hf_hub_download(MODEL, name, revision=REVISION, local_files_only=True)
            except LocalEntryNotFoundError:
                return hf_hub_download(MODEL, name, revision=REVISION)

        self.tokenizer = Tokenizer.from_file(asset("tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=128)
        self.tokenizer.enable_padding(pad_id=self.tokenizer.token_to_id("<pad>") or 0)
        options = ort.SessionOptions()
        options.intra_op_num_threads = int(os.getenv("EMBEDDING_THREADS", "2"))
        self.session = ort.InferenceSession(asset("onnx/model.onnx"), options,
                                            providers=["CPUExecutionProvider"])

    def encode(self, texts):
        # Pool all token windows, including overflow beyond the first 128 tokens.
        windows = []
        for i, encoding in enumerate(self.tokenizer.encode_batch(texts)):
            windows.extend((i, part) for part in [encoding, *encoding.overflowing])
        sums = np.zeros((len(texts), 384), dtype=np.float32)
        for start in range(0, len(windows), 16):
            batch = windows[start:start + 16]
            width = max(len(item.ids) for _, item in batch)
            def tensor(field):
                return np.array([list(getattr(e, field)) + [0] * (width-len(e.ids))
                                 for _, e in batch], dtype=np.int64)
            fields = {"input_ids": "ids", "attention_mask": "attention_mask", "token_type_ids": "type_ids"}
            inputs = {node.name: tensor(fields[node.name]) for node in self.session.get_inputs()}
            hidden = self.session.run(None, inputs)[0]
            pooled = (hidden * inputs["attention_mask"][:, :, None]).sum(axis=1)
            for (i, _), vector in zip(batch, pooled):
                sums[i] += vector
        return sums / np.maximum(np.linalg.norm(sums, axis=1, keepdims=True), 1e-12)
