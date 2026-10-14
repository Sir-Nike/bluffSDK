# Provenance

This CPU verification participant is ported from the original event-runtime PR.
Its previous policy is preserved at `history/strategy.py` for the
paired development checks. The current policy sheds truthful rank groups and
uses only publicly revealed challenges to estimate opponent bluff rates. It
accounts for configured player and deck counts.

The adapter derives from the sibling bluffSDK. The protocol and schemas are
regenerated from the sibling organizer checkout by
`Bluff/tools/update_contracts.py`; VENDOR manifests record their committed LF
byte hashes. `tools/check_competitive_agent.py` checks these hashes against this
submission and runs paired simulations.

This participant uses Python's standard library, with no pretrained weights,
external training data, or runtime evaluator/benchmark imports. Historical
performance reports from the earlier workspace are not included and do not
establish performance on the ported runtime. The separate CUDA fixture trains
synthetic data solely to verify model packaging and inference.
