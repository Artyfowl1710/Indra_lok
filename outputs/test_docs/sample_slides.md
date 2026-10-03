# INDRA Autonomous System
A High-Performance, 100% Offline AI Agent Architecture

# System Architecture & Core Pillars
- **Local Model Serving**: llama-swap dynamically manages local GGUF models within 6GB VRAM.
- **Unified Tool Suite**: Pre-packaged, context-agnostic PDF, PPTX, and XLSX generation engines.
- **Interactive UI Bridge**: Real-time WebSocket approvals and clarification prompts.

# Performance & Benchmarks
- **Context Window**: 32K token context with flash-attention and Q4_K_M quantization.
- **GPU Offload**: 28 layers offloaded to NVIDIA RTX GPU with zero CUDA out-of-memory faults.
- **Delivery Guarantee**: All generated files persisted to workspace ./outputs/ directory.
