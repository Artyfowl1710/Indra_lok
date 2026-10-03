# Offline Operational Report

This document was generated 100% offline using INDRA's unified document suite.

## Executive Summary
All components are functioning within nominal parameters. Local inferencing, offline tool execution, and workspace persistence are operational.

## System Performance Metrics
| Metric | Baseline | Current | Status |
| --- | --- | --- | --- |
| Inference Latency | 45ms | 38ms | Optimal |
| VRAM Footprint | 5.8 GB | 5.2 GB | Protected |
| PDF Generation Speed | 1.8s | 0.4s | Accelerated |
| Token Throughput | 24 tps | 29 tps | Exceeded |

## Key Recommendations
- **Maintain local mode**: Keep `approvals.mode: smart` for user oversight or `off` for autonomous execution.
- **Utilize Platypus flowables**: Prevents text clipping and maintains page boundaries.
- **Export directly to ./outputs/**: Preserves deliverables across session teardowns.
