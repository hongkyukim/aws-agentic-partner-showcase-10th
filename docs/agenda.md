# Event agenda → workshop run-of-show

**AWS Agentic Partner Showcase Extended (10th Edition)** — AWS, Temporal, Arize, Databricks.

| Time | Event block | Use this repo for |
|---|---|---|
| 4:30–5:30 PM | Check-in, food, booth visiting | Clone repo, run `make demo` + `make test` (Lab 0). Skim `docs/booth-questions.md`. |
| 5:45–7:30 PM | Kick-off, tech talks, live demo | Follow along with Labs 1–5 as each partner presents (timings below). |
| 7:30–8:30 PM | Networking, Q&A over booths | Bring your trace tree, eval report, and gate output to the booths. |

## Facilitator run-of-show for the 105-minute talk block

| Clock | Min | Segment | Live command | Talking point |
|---|---|---|---|---|
| 5:45 | 10 | Kick-off: "code to deployment" stack | `make demo` | One agent, four production concerns: model, data, durability, observability |
| 5:55 | 15 | AWS: models + guardrails | `pytest tests/test_aws_bedrock.py -v` | Bounded inference config; model output is untrusted input |
| 6:10 | 15 | Databricks: governed data | `pytest tests/test_databricks.py -v` | Agents call parameterized, scoped tools — never free-form SQL |
| 6:25 | 20 | Temporal: durable execution | `make demo` (scenario 2) | LLM calls are activities; approvals can wait days; replay is crash recovery |
| 6:45 | 20 | Arize: traces + evals | `make trace`, `make eval`, `make eval-bad` | You can't ship what you can't see; evals are the regression suite |
| 7:05 | 15 | Capstone: release to AWS | `make gate` | Gate on evals + pinned image + approver before AgentCore/ECS deploy |
| 7:20 | 10 | Panel Q&A | — | Use questions from `docs/booth-questions.md` |

## Audience paths

- **Builders shipping agents now:** do every lab, then `extensions/live/`.
- **Engineering leaders / decision makers:** read `docs/architecture.md` and run `make demo`,
  `make eval-bad`, `make gate` — the three commands show where risk is controlled.
- **Learning agentic AI:** Labs 0, 1, 3 in order; the tests are executable explanations.
