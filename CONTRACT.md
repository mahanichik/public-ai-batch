# Public Worker Contract

This repository processes public/non-sensitive inputs only.

## Record

```json
{
  "id": "stable-source-id",
  "text": "bounded public evidence",
  "observed_at": "ISO-8601-or-null",
  "metadata": {"source": "source-key"}
}
```

## Work receipt

```json
{
  "worker_key": "public_ai_worker",
  "activity_type": "analysis-task",
  "compute_class": "github_public",
  "provider": "local_or_free_provider",
  "model": "model-id",
  "status": "completed",
  "input_count": 100,
  "output_count": 20,
  "rejected_count": 50,
  "duplicate_count": 20,
  "stale_count": 10,
  "promoted_count": 20,
  "reasons": {},
  "metrics": {},
  "summary": "human-readable exact summary",
  "started_at": "ISO-8601",
  "completed_at": "ISO-8601"
}
```

Counts must reflect the actual run.

## Security boundary

Do not provide:
- credentials or access tokens
- private records
- confidential prompts or documents
- production database access
- private configuration or business logic
