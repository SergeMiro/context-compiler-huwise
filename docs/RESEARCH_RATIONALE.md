# Research rationale and attribution

None of the works below measured a Huwise portal. Their reported gains are not transferred to this project:
only the numbers in `docs/EVAL_METHODOLOGY.md` (measured here) count.

## AutoResearch — Andrej Karpathy

- Source: <https://github.com/karpathy/autoresearch>, <https://github.com/karpathy/autoresearch/blob/master/program.md>
- What it shows: an agent edits a small language model's training code, runs a short training with a fixed time
  budget, compares the validation metric, keeps or discards the change, logs it, and repeats autonomously.
- What we adapt: the loop shape — hypothesis → one scoped change → reproducible run → compare → keep/revert → log →
  repeat, under a hard budget. Our editable artifacts are context cards (description, synonyms, query template,
  note). The evaluator, golden labels, test data, validator and log are out of the loop's reach.
- What we do **not** claim: AutoResearch is about model training. "AutoContext" is our transposition; Karpathy did
  not propose it, nor anything about MCP.
- How we measure: `lab/cycle.py` gate on failing + control cases; final effect only on the locked holdout.
- Limits: a free model, small budgets; one cycle shows the mechanism, not a converged optimiser.

## DSPy / MIPRO — Opsahl-Ong et al., EMNLP 2024

- Source: <https://aclanthology.org/2024.emnlp-main.525/> ("Optimizing Instructions and Demonstrations for
  Multi-Stage Language Model Programs").
- What it shows: jointly searching instructions and few-shot demonstrations for multi-stage LM programs improves
  task metrics on their benchmarks, with a surrogate model guiding the search.
- What we adapt: nothing is run. The edit proposer in `evals/improve.py` is the extension point where a MIPRO-like
  optimiser could plug in; it would be kept only if it wins on the holdout.
- Why not now: a search over instructions costs hundreds of model calls per iteration; the free daily budget is
  ~1 000 requests shared with other projects. Adding DSPy as a dependency for a citation is not justified.

## LLMCompiler — Kim et al., 2023

- Source: <https://arxiv.org/abs/2312.04511> ("An LLM Compiler for Parallel Function Calling").
- What it shows: planning a DAG of tool calls and executing independent calls in parallel reduces latency and cost
  versus sequential ReAct on their tasks.
- What we adapt: on the FAST route the plan is known in advance (resolve place → count) and needs no model at all.
  Dependencies are respected: records are never queried before the schema/value is known.
- Not done: parallel execution of independent tool calls inside the agent loop.

## RouteLLM — Ong et al., 2024

- Source: <https://arxiv.org/abs/2406.18665> ("RouteLLM: Learning to Route LLMs with Preference Data").
- What it shows: a learned router sending each query to a strong or a weak model cuts cost while keeping quality
  close to the strong model on their benchmarks.
- What we adapt: route by risk and difficulty, but between **paths** (FAST / STANDARD / DEEP), not models; rules
  are deterministic and versioned (`optimizer/router.py: POLICY_VERSION`); low confidence goes up a level
  (unresolved place → agent).
- Measured here: share of FAST answers, model calls and latency per configuration (A/B/C), not the paper's numbers.

## Metamorphic and property-based testing

- Sources: Chen, Cheung, Yiu (1998) "Metamorphic testing: a new approach for generating next test cases";
  overview <https://en.wikipedia.org/wiki/Metamorphic_testing>; property-based testing (QuickCheck, Claessen &
  Hughes 2000).
- What it shows: relations between outputs of related inputs find faults without a complete oracle.
- What we adapt: `optimizer_check` verifies *public ≤ all* and *public + private ≤ all* for the same place, the same
  dataset and the same moment (18 relations); `optimizer/tests.py` runs seeded property checks on the ODSQL
  validator (random unknown identifiers rejected, generated valid queries accepted, comments and extra parameters
  rejected).
- Limits: relations complement the golden answers; they never replace them.

## Observability and reliability (OpenTelemetry, SRE)

- Sources: <https://opentelemetry.io/docs/concepts/signals/traces/>; Beyer et al., *Site Reliability Engineering*
  (Google, 2016), chapters on SLIs/SLOs and error budgets.
- What we adapt: every answer carries spans (`route`, `query`, `llm`, `verify`) with duration and status, never the
  API key or the prompt; `ToolCall` logs tool, latency and error code only. The quality gate plays the role of an
  error budget for context changes.
- Not done: an OTel collector or SLO dashboards — unnecessary at this scale.
