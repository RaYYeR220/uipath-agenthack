# Sentinel — Agentic QA for AI Agents

Adversarial reliability auditing for AI agents, executed on UiPath Test Cloud.
Built for UiPath AgentHack 2026 (Track 3). See `docs/superpowers/specs/` for design.

> README fleshed out in Phase 2 (submission). This stub keeps the repo licensed and described.

## Run the core locally (Phase 0)

```bash
uv sync
uv run pytest                 # all tests, no network
export ANTHROPIC_API_KEY=sk-...
uv run sentinel audit --mandate mandates/loanadvisor.yaml --target mock --out report
```

`--target mock` audits a deliberately-flawed local stand-in for the real
LoanAdvisor agent. The UiPath target (`--target uipath`) and Test Cloud execution
arrive in Phase 1, once the AgentHack Labs org is provisioned.
