# Interim Detective Audit Report

## Input

- Repository Target: `https://github.com/yohans-kasaw/CodeDueProcess.git`
- PDF Report: `/tmp/peer_reports/intrim_report.pdf`

## Evidence Index

### doc.citation_check
- Goal: Cross-reference cited files against repository artifacts.
- Found: `False`
- Confidence: `0.80`
- Location: `/tmp/peer_reports/intrim_report.pdf`
- Rationale: Compared path-like citations extracted from PDF to repo file list.
- Content:
```text
missing=src/api/, src/models/, src/utils/
```
- Tags: docs, hallucination

### doc.concept_verification
- Goal: Verify conceptual treatment of metacognition and dialectical synthesis.
- Found: `False`
- Confidence: `0.70`
- Location: `/tmp/peer_reports/intrim_report.pdf`
- Rationale: Chunked query over parsed PDF content (RAG-lite retrieval).
- Content:
```text
chunks=35, hits=4, metacognition=False, dialectical=False
```
- Tags: docs, concept

### doc.visual_audit
- Goal: Verify architectural diagrams in the report using Vision AI.
- Found: `False`
- Confidence: `1.00`
- Location: `/tmp/peer_reports/intrim_report.pdf`
- Rationale: Vision API error: Error calling model 'gemini-2.0-flash' (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 0, model: gemini-2.0-flash\n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 0, model: gemini-2.0-flash\n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_input_token_count, limit: 0, model: gemini-2.0-flash\nPlease retry in 51.440389927s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-2.0-flash'}}, {'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier', 'quotaDimensions': {'model': 'gemini-2.0-flash', 'location': 'global'}}, {'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_input_token_count', 'quotaId': 'GenerateContentInputTokensPerModelPerMinute-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-2.0-flash'}}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '51s'}]}}
- Tags: docs, vision

### repo.git_narrative
- Goal: Assess whether engineering happened in atomic increments.
- Found: `True`
- Confidence: `0.70`
- Location: `git log`
- Rationale: >=4 recent commits treated as minimal iterative signal.
- Content:
```text
dbbe739 2026-02-24T10:58:39+03:00 Initial commit
16b0fc7 2026-02-24T12:17:10+03:00 speckit added
a9e780d 2026-02-24T16:21:51+03:00 first agent workflow try
c8996d4 2026-02-25T10:21:07+03:00 feat: ignore pydantic warning
f2c3265 2026-02-25T11:29:43+03:00 langgraph studio support
```
- Tags: effort, process, git

### repo.graph_wiring
- Goal: Verify fan-out/fan-in graph topology.
- Found: `False`
- Confidence: `0.98`
- Location: `/var/folders/w0/hbswmr8x4xlb2hy7b6g474tr0000gn/T/tmp05iec2wi/repo/src/graph.py`
- Rationale: Missing src/graph.py.
- Tags: orchestration, parallelism

### repo.security_scan
- Goal: Identify risky command execution patterns.
- Found: `True`
- Confidence: `0.75`
- Location: `/var/folders/w0/hbswmr8x4xlb2hy7b6g474tr0000gn/T/tmp8eur0x94/repo`
- Rationale: Pattern scan for unsafe execution primitives.
- Content:
```text
No risky patterns matched.
```
- Tags: security

### repo.state_structure
- Goal: Verify typed state definitions.
- Found: `False`
- Confidence: `0.98`
- Location: `/var/folders/w0/hbswmr8x4xlb2hy7b6g474tr0000gn/T/tmp43u24177/repo`
- Rationale: Neither src/state.py nor src/graph.py exists.
- Tags: orchestration, state

## Execution Log

- OrchestrationPrecheck heuristic selected doc_analyst
- RepoInvestigator completed
- VisionInspector completed
- DocAnalyst completed
- EvidenceAggregator completed: evidence_count=5, repo_evidence=True, doc_evidence=False, doc_required=True, status=incomplete
- EvidenceAggregator completed: evidence_count=7, repo_evidence=True, doc_evidence=False, doc_required=True, status=incomplete
- OrchestrationPostcheck heuristic selected missing_artifacts
- MissingArtifactsHandler: required detective evidence was incomplete; continuing with partial output for graceful degradation.
- OrchestrationPostcheck heuristic selected missing_artifacts
- MissingArtifactsHandler: required detective evidence was incomplete; continuing with partial output for graceful degradation.
