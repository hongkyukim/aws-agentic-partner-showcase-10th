# Questions to bring to the booths (7:30–8:30 PM)

Bring your `make trace` output and `reports/eval.md`; concrete artifacts get better answers.

## AWS
- When should an agent run on AgentCore Runtime vs. ECS/Fargate vs. Lambda? What drives the choice: session length, memory, isolation?
- How do you combine Bedrock Guardrails with app-level output validation like `parse_decision`?
- How do teams manage model-version upgrades without eval regressions? Inference profiles, pinning, canaries?
- How do you scope IAM for an agent that calls several tools?

## Temporal
- What belongs in a workflow vs. an activity when the "logic" is an LLM call?
- How do you version a long-running agent workflow (patching vs. worker versioning) while approvals are still pending?
- Patterns for human-in-the-loop: signals vs. updates, timeouts, and escalation?
- How do people bound cost when an LLM activity retries?

## Arize
- Which evals give the best signal for tool-using agents: correctness, groundedness, tool-call accuracy?
- How do you sample and redact traces in production without losing debuggability?
- How do online evals feed back into the offline golden set?
- What does a good alert on agent quality look like?

## Databricks
- Unity Catalog permission patterns for agent service principals: row filters, column masks?
- Keeping a Vector Search index fresh as policy docs change (Delta Sync vs. direct access)?
- Where does Mosaic AI Agent Framework / MLflow tracing overlap with an Arize setup, and how do teams split it?
- Serving models on Databricks vs. Bedrock for the same agent: what's the tradeoff?
