# INDRA offline document sandbox

Build once while the operator-approved package source is available:

```powershell
cd SIH-26/hermes-agent
docker build -t indra-documents:1 -f docker/Dockerfile.indra-documents .
```

The `SIH-26/config.yaml` terminal settings select this image, disable its network,
and mount the directory from which INDRA is launched at `/workspace`. Rebuild the
image on each installation (or distribute an approved, scanned image archive);
the tag alone does not transfer the image to another computer. Restart INDRA
after building or changing terminal settings.

Inputs uploaded to INDRA are read-only at `/root/.hermes/attachments` inside the
sandbox. Use `/tmp` for scripts and intermediate work; save all final deliverables
under `/workspace/outputs/` so they appear together in the host's `outputs` folder.
The local model server remains on the host; `docker_network: false` blocks only
the agent's execution container and does not prove the whole workstation is
air-gapped.

Smoke test, without network:

```powershell
docker run --rm --network=none indra-documents:1 python /opt/indra/smoke_indra_documents.py
```

The test creates and reads back a one-page PDF, `.xlsx` workbook and `.pptx`
deck. For demo runs, keep prompts focused and use the installed PDF/XLSX/PPTX
skill helpers; avoid installing packages or printing entire source documents
into tool output. If a missing dependency is found, capture a request for the
operator's approved build-time package channel and rebuild the image. Never
enable container networking as a task-level workaround.
