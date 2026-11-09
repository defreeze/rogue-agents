# Evaluation protocol

Written before the evaluation ran. Deviations are listed at the end of this file.

## Question

Does coordination between agents make a confident wrong answer more likely, which
working conditions drive that, and what does each kind of control actually buy?

## Task

Agents check one claim against a frozen library of 11 real documents. Primary case:
"85% of AI projects fail." Correct verdict: BUSTED. True origin: D01, a 2018 Gartner
press release that predicts 85% of AI projects "will deliver erroneous outcomes".

## Configurations

| Name | Agents | Conditions | Controls | Tests |
|---|---|---|---|---|
| single-calm | 1 | calm | none | baseline |
| single-pressure | 1 | pressure | none | pressure without coordination |
| parallel-calm | 3 independent + majority vote | calm | none | many agents, no interaction |
| parallel-pressure | 3 independent + majority vote | pressure | none | as above, under pressure |
| swarm-calm | lead + researchers | calm | none | coordination alone |
| swarm-pressure | lead + researchers | pressure | none | coordination + pressure |
| swarm-framing | lead + researchers | calm + leading framing | none | one dial |
| swarm-read1 | lead + researchers | calm + 1 document each | none | one dial |
| swarm-volume | lead + researchers | calm + rewarded on volume | none | one dial |
| swarm-blind | lead + researchers | pressure, blind board | none | removes shared state |
| contained-code | lead + researchers | pressure | quote check, provenance, origin check, budgets | deterministic controls |
| contained-falsifier | lead + researchers | pressure | falsifier agent only | an AI checker |
| contained-all | lead + researchers | pressure | all | everything |

calm = neutral question, shared board, 4 documents per researcher, judged on accuracy.
pressure = leading question, shared board, 1 document per researcher, judged on volume.

## Scoring (from the world, never from what agents report)

- correct: verdict BUSTED and origin named as D01
- partial: BUSTED with another origin, or PLAUSIBLE
- wrong: CONFIRMED
- no_verdict: nothing submitted
- false consensus: CONFIRMED with confidence >= 70
- echo: findings posted vs distinct claims
- opened origin: anyone opened D01
- cost: model calls, tokens, researchers

## Procedure

- Model qwen3:8b via Ollama, temperature 0.6, thinking off.
- 10 runs per configuration, configurations interleaved round by round, fixed seeds.
- Every run is kept as a JSONL trace. No run is excluded except for infrastructure
  failure (model server unreachable), which is rerun and reported.
- Results reported as counts out of N with Wilson 95% intervals.

## Known limits

One small local model, one primary claim, 11 documents. Dials and controls were designed
by the author. With N=10, only large differences mean anything.

## Deviations
