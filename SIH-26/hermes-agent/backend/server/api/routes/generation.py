"""
Async generation endpoints: image, video, audio.
POST /v1/generate/{image|video|audio}  → { job_id }
GET  /v1/jobs/{job_id}                 → { status, result_url }

Also: POST /v1/generate/raw_workflow (admin only, gated by allow_raw_workflow flag)
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from server.backends import comfyui_driver
from server.config import settings
from server.core.auth import require_admin, require_auth
from server.core.lifecycle import lifecycle
from server.core.schemas import GenerateRequest, JobResponse, JobStatusResponse
from server.db import ApiKey, GenerationJob, ModelRecord, get_db
log = logging.getLogger(__name__)
router = APIRouter(tags=["generation"])


def _get_model_or_404(model_id: str, db: Session) -> ModelRecord:
    m = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
    if m is None:
        raise HTTPException(404, f"Model {model_id!r} not registered")
    return m


async def _run_generation_job(job_id: str, job_type: str, model_id: str, prompt: str, params: dict):
    """Background task: submit to ComfyUI, poll, update DB."""
    from server.db import SessionLocal
    with SessionLocal() as db:
        job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
        if job:
            job.status = "running"
            job.updated_at = datetime.utcnow()
            db.commit()

    try:
        async with lifecycle.track_request(model_id):
            from server.db import SessionLocal as SL
            with SL() as db:
                m = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
                checkpoint = Path(m.local_path or m.source_ref).name

            prompt_id = await comfyui_driver.submit_job(job_type, prompt, checkpoint, params)
            result = await comfyui_driver.wait_for_job(prompt_id)

        output_path = _extract_output_path(result)

        from server.db import SessionLocal as SL2
        with SL2() as db:
            job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
            if job:
                job.status = "done"
                job.result_path = output_path
                job.updated_at = datetime.utcnow()
                db.commit()

    except Exception as exc:
        log.exception("Generation job %s failed", job_id)
        from server.db import SessionLocal as SL3
        with SL3() as db:
            job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
            if job:
                job.status = "failed"
                job.error = str(exc)
                job.updated_at = datetime.utcnow()
                db.commit()


def _extract_output_path(comfyui_result: dict) -> str:
    """Pull the first output filename from a ComfyUI history entry."""
    for node_output in comfyui_result.get("outputs", {}).values():
        for key in ("images", "videos", "audio"):
            items = node_output.get(key, [])
            if items:
                item = items[0]
                return f"/outputs/{item.get('filename', '')}"
    return ""


def _make_job(job_type: str, model_id: str, db: Session) -> GenerationJob:
    job = GenerationJob(
        id=str(uuid.uuid4()),
        model_id=model_id,
        job_type=job_type,
        status="queued",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


# ── generation endpoints ──────────────────────────────────────────────────────

@router.post("/v1/generate/image", response_model=JobResponse, status_code=202)
async def generate_image(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_auth),
):
    m = _get_model_or_404(req.model_id, db)
    if m.backend != "comfyui":
        raise HTTPException(400, "Image generation requires a comfyui backend model")
    job = _make_job("image", req.model_id, db)
    background_tasks.add_task(_run_generation_job, job.id, "image", req.model_id, req.prompt, req.params)
    return JobResponse(job_id=job.id)


@router.post("/v1/generate/video", response_model=JobResponse, status_code=202)
async def generate_video(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_auth),
):
    m = _get_model_or_404(req.model_id, db)
    if m.backend != "comfyui":
        raise HTTPException(400, "Video generation requires a comfyui backend model")
    job = _make_job("video", req.model_id, db)
    background_tasks.add_task(_run_generation_job, job.id, "video", req.model_id, req.prompt, req.params)
    return JobResponse(job_id=job.id)


@router.post("/v1/generate/audio", response_model=JobResponse, status_code=202)
async def generate_audio(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_auth),
):
    m = _get_model_or_404(req.model_id, db)
    if m.backend != "comfyui":
        raise HTTPException(400, "Audio generation requires a comfyui backend model")
    job = _make_job("audio", req.model_id, db)
    background_tasks.add_task(_run_generation_job, job.id, "audio", req.model_id, req.prompt, req.params)
    return JobResponse(job_id=job.id)


@router.get("/v1/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_auth),
):
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
    if job is None:
        raise HTTPException(404, "Job not found")
    result_url = None
    if job.result_path:
        result_url = f"{settings.public_api_base}{job.result_path}"
    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        result_url=result_url,
        error=job.error,
    )


from fastapi.responses import FileResponse


@router.get("/outputs/{filename}")
def serve_output_file(filename: str, _: ApiKey = Depends(require_auth)):
    output_dir = settings.comfyui_models_dir / "output"
    file_path = output_dir / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, "Generated output file not found")
    return FileResponse(path=file_path)


# ── raw workflow (admin only, gated) ─────────────────────────────────────────

@router.post("/v1/generate/raw_workflow", response_model=JobResponse, status_code=202)
async def raw_workflow(
    workflow: dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_admin),
):
    if not settings.allow_raw_workflow:
        raise HTTPException(403, "raw_workflow endpoint is disabled in this deployment")
    # Bypasses registry/lifecycle — admin use only, documented as such
    job_id = str(uuid.uuid4())
    job = GenerationJob(
        id=job_id, model_id="__raw__", job_type="image",
        status="queued", created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()

    async def _run_raw_job():
        from server.db import SessionLocal
        with SessionLocal() as db:
            j = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
            if j:
                j.status = "running"
                j.updated_at = datetime.utcnow()
                db.commit()

        try:
            r = await comfyui_driver.get_client().post("/prompt", json={"prompt": workflow})
            r.raise_for_status()
            prompt_id = r.json()["prompt_id"]
            result = await comfyui_driver.wait_for_job(prompt_id)
            output_path = _extract_output_path(result)
            with SessionLocal() as db:
                j = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
                if j:
                    j.status = "done"
                    j.result_path = output_path
                    j.updated_at = datetime.utcnow()
                    db.commit()
        except Exception as exc:
            log.exception("Raw workflow job %s failed", job_id)
            with SessionLocal() as db:
                j = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
                if j:
                    j.status = "failed"
                    j.error = str(exc)
                    j.updated_at = datetime.utcnow()
                    db.commit()

    background_tasks.add_task(_run_raw_job)
    return JobResponse(job_id=job_id)
