# -*- coding: utf-8 -*-
"""临时探针：直接用 vector_search.LocalEmbedder 把全集 5018 个文本块重编码，
逐条与向量索引里的存量向量比余弦，确认编码路径与建索引完全同口径。

非交付物，跑完即删。
"""
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "代码", "检索"))

import numpy as np  # noqa: E402

import vector_search as vs  # noqa: E402

index, forward, backward, chunks = vs.load_pool()
embedder = vs.LocalEmbedder(verbose=True)
embedder._torch.set_num_threads(8)          # 仅探针加速；正式自证保持单线程

order = sorted(forward)
texts = [chunks[forward[v][0]]["content"] for v in order]
stored = np.asarray(index.reconstruct_n(0, index.ntotal), dtype="float32")

t0 = time.time()
fresh = embedder.encode(texts)
seconds = time.time() - t0
cos = np.sum(fresh * stored, axis=1) / (np.linalg.norm(fresh, axis=1) * np.linalg.norm(stored, axis=1))
worst = int(np.argmin(cos))
print("全集复核 %d 条  耗时=%.1fs  min=%.10f  均值=%.10f  <0.999 条数=%d  <0.99999 条数=%d"
      % (len(cos), seconds, float(cos[worst]), float(cos.mean()),
         int((cos < 0.999).sum()), int((cos < 0.99999).sum())))
print("最差一条：vector_id=%d chunk_id=%d cos=%.10f"
      % (order[worst], forward[order[worst]][0], float(cos[worst])))
