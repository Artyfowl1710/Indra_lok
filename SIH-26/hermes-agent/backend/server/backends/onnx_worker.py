"""
Standalone ONNX Runtime worker process.
Launched as a subprocess by onnx_driver.py — one process per model.
Exposes a minimal HTTP API so the gateway can proxy to it.

Usage: python onnx_worker.py --model-path <path> --port <port>
"""
from __future__ import annotations

import argparse
import logging

import numpy as np
import onnxruntime as ort
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)
app = FastAPI()
_session: ort.InferenceSession | None = None


class InferRequest(BaseModel):
    inputs: dict   # name → list (will be converted to np arrays)
    output_names: list[str] | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/infer")
def infer(req: InferRequest):
    if _session is None:
        raise HTTPException(503, "Model not loaded")
    feeds = {k: np.array(v) for k, v in req.inputs.items()}
    out_names = req.output_names or None
    try:
        results = _session.run(out_names, feeds)
        output_names = [o.name for o in _session.get_outputs()]
        return {"outputs": {name: r.tolist() for name, r in zip(output_names, results)}}
    except Exception as exc:
        raise HTTPException(500, str(exc))


def main():
    global _session
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    _session = ort.InferenceSession(args.model_path, providers=providers)
    log.info("ONNX model loaded from %s", args.model_path)

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
