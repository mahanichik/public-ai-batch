# Public AI Workers

Generic public/non-sensitive batch AI workers for reusable classification and analysis tasks.

Supported tasks:
- `prospect_classify`
- `market_trends`
- `content_brief`
- `outcome_analysis`

Execution:
1. deterministic empty/stale/duplicate filtering
2. bounded batch analysis
3. structured results
4. exact `result.json` + `receipt.json`

Available execution modes:
- local open model on the runner
- configured free-tier providers
- deterministic-only mode

No paid fallback is enabled.

Do not provide credentials, private records, confidential prompts, or production configuration to this repository.


## Deterministic analysis

- `rapidfuzz_dedupe`: conservative fuzzy clustering with an explicit threshold.
- `splink_entity_resolution`: deterministic Splink linking on caller-selected public identifiers; it does not train or expose private matching policy.
- `zen_evaluate`: executes caller-supplied public JDM decisions with the open-source ZEN engine.

Private or proprietary rules do not belong in public workflow inputs.
