# RET-C2-640 — Loyalty Dispute Resolution Agent

> **Category**: Cat 2 (domain workflow)
> **Industry**: Retail

## Overview

This template assembles the evidence behind a customer's loyalty-program dispute — a
disagreement over whether a purchase should have earned points, or whether a reward offer
applied — and produces a cited, human-reviewed response draft for a Customer Care or Retail
Operations agent to send. Given a dispute reference, the customer and offer it concerns, the
disputed period, and which record sources the operator is authorised to query, it retrieves the
offer's rules and the customer's loyalty activity from those approved sources, maps the rules
against the activity as structural applicability factors (not a ruling), pulls in any prior
disputes or documented policy exceptions on record, and drafts a factual evidence summary for
review. It makes **no determination about the dispute**: it does not decide eligibility, does
not grant or revoke loyalty rewards, and does not modify a customer's account or send anything to
the customer directly. Every draft carries an explicit "no eligibility decision has been made"
notice and stops at an interruptible human-review checkpoint before the pipeline can complete;
approving, correcting or rejecting that checkpoint is what a human reviewer does next, not
something this agent does on its own. When a record source is unreachable — no credential
configured, or the source itself returns nothing — the affected node says so and marks the
result partial rather than quietly treating "no data returned" as "no evidence exists".

This is an agent template built with the **AGENTIC STAR** development platform and the
**AgentCore Framework**. It is intended to be taken as a starting point: fork it, adapt it to
your own data and policies, and run it inside your own AGENTIC STAR deployment.

## Requirements

**This template does not run standalone.** It requires:

| Requirement | Notes |
|---|---|
| **AGENTIC STAR platform** | The agent connects to the platform at start-up. Without it, start-up fails immediately (see *Behaviour without the platform* below). Deployment guides and API documentation: [AGENTIC STAR Developers](https://developers.fd.agenticstar.tm.softbank.jp/) |
| **AgentCore Framework** (`agenticstar-agentcore`) | Installed from PyPI as a dependency. |
| Python | >=3.11 |

```bash
pip install -e .
```

### Behaviour without the platform

The framework is designed to run **only** on AGENTIC STAR. There is no fallback or degraded
mode. If the platform is unreachable or the SDK version does not match, the agent raises
`PlatformRequired` during graph compile / start-up preflight rather than starting in a partially
working state. This is intentional — a half-running agent is worse than one that refuses to start.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

Tests run without a platform connection. Running the agent itself does not.

## Project Structure

```
src/          agent implementation (nodes, services, schemas)
tests/        unit, integration and boundary tests
config/       agent configuration
docs/         design and test specifications
```

See `docs/` for the design specification and test specification.

## Customising

1. Adjust `config/config.yaml` for your own environment and policies — the approved source-ID
   allowlist, how many rules/history records/prior disputes to consider, the maximum dispute
   period, and whether HITL review is required are all declared there rather than hard-coded.
2. Implement `LoyaltyAdapter` in `src/services/loyalty_adapter.py` against your own loyalty and
   offer-catalog systems. Every method currently raises `NotImplementedError` by design — this
   template ships no sample dataset, and each retrieval call is deliberately unwired until a
   deployer connects it.
3. Review the node implementations under `src/nodes/` for domain-specific logic — in particular
   `PreProcessNode`'s field validation and source allowlist, and `ResponseDraftNode`'s HITL
   review contract.
4. Re-run the test suite.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This template is published **as is**, by its individual author, under the MIT license. It carries
**no warranty and no support commitment**, and no organisation stands behind its behaviour or
fitness for any purpose. Issues and pull requests may or may not receive a response; that is at
the sole discretion of the repository owner.
