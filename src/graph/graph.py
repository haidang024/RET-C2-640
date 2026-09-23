"""Cat 2 outer AgentBaseGraph for RET-C2-640."""

from __future__ import annotations

from typing import Any, ClassVar, cast

from framework.graph.agent_base_graph import AgentBaseGraph
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from langgraph.checkpoint.memory import MemorySaver
from src.graph.domain_workflow_graph import LoyaltyDisputeWorkflowGraph
from src.nodes.post_process_node import PostProcessNode
from src.nodes.pre_process_node import PreProcessNode
from src.schemas.state import State


class LoyaltyDisputeGraphNode(GraphNode):
    """Main-slot wrapper around the loyalty dispute domain workflow."""

    error_strategy: ClassVar[str] = "propagate"
    propagate_hitl: ClassVar[bool] = True
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, config: dict | None = None, llm: object | None = None) -> None:
        self._config = config or {}
        self._llm = llm
        self._subgraph: LoyaltyDisputeWorkflowGraph | None = None
        super().__init__()

    def get_subgraph(self):
        if self._subgraph is None:
            self._subgraph = LoyaltyDisputeWorkflowGraph(config=self._parent_config())
            hitl_config = self._config.get("hitl", {})
            checkpointer = MemorySaver() if hitl_config.get("enabled", False) else None
            self._subgraph.compile(checkpointer=checkpointer)
        return self._subgraph

    def extract_input(self, state: AgentState) -> str:
        return state.get("normalized_input", state.get("user_input", ""))

    def merge_output(self, state: AgentState, sub_result: dict) -> dict:
        return {
            "response_draft": sub_result.get("response_draft", ""),
            "briefing_summary": sub_result.get("briefing_summary", ""),
            "review_disposition": sub_result.get("review_disposition", ""),
            "review_notes": sub_result.get("review_notes", ""),
            "applicability_factors_json": sub_result.get("applicability_factors_json", ""),
            "constraints_json": sub_result.get("constraints_json", ""),
            "evidence_gaps_json": sub_result.get("evidence_gaps_json", ""),
            "exception_factors_json": sub_result.get("exception_factors_json", ""),
            "exception_citations_json": sub_result.get("exception_citations_json", ""),
            "prior_outcomes_json": sub_result.get("prior_outcomes_json", ""),
            "offer_rules_json": sub_result.get("offer_rules_json", ""),
            "loyalty_history_json": sub_result.get("loyalty_history_json", ""),
            "evidence_sources_json": sub_result.get("evidence_sources_json", ""),
            "evidence_retrieved": sub_result.get("evidence_retrieved", False),
            "retrieval_unavailable": sub_result.get("retrieval_unavailable", False),
            "analysis_complete": sub_result.get("analysis_complete", False),
            "exception_analysis_complete": sub_result.get("exception_analysis_complete", False),
            "status": sub_result.get("status", ""),
            "error_log": sub_result.get("error_log", state.get("error_log", [])),
        }

    def execute(self, state: AgentState) -> dict[str, Any]:
        if state.get("input_error_message"):
            return {"status": AgentStatus.SUCCESS.value}
        return cast(dict[str, Any], super().execute(state))

    def _parent_config(self) -> dict:
        return {**self._config, "llm": self._llm}


class Graph(AgentBaseGraph):
    """Loyalty Dispute Resolution Agent."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config=config)

    @property
    def name(self) -> str:
        return "RET-C2-640"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()
        self._nodes["pre_process"] = PreProcessNode()
        self._nodes["main"] = LoyaltyDisputeGraphNode(
            config=self.config,
            llm=self.config.get("llm"),
        )
        self._nodes["post_process"] = PostProcessNode(
            llm=self.config.get("llm"),
            config=self.config,
        )

    def get_output(self, state: AgentState) -> dict[str, Any]:
        output = {
            "output": (
                state.get("formatted_output")
                or state.get("output_response")
                or state.get("report_artefact")
                or state.get("result", "")
            ),
            "result": state.get("result", ""),
            "status": state.get("status", AgentStatus.ERROR.value),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
            "generation_mode": state.get("generation_mode"),
            "provider_error_message": state.get("provider_error_message"),
        }
        _set_marketplace_guidance(output, state, "Loyalty-dispute request")
        return output


def _set_marketplace_guidance(output: dict[str, Any], state: AgentState, subject: str) -> None:
    context = state.get("input_context")
    message = state.get("input_error_message")
    if not (isinstance(context, dict) and "conversation_history" in context and message):
        return
    lines = [f"{subject} could not be processed.", "", f"Reason: {message}"]
    guidance = state.get("input_error_guidance")
    if isinstance(guidance, list) and guidance:
        lines.extend(["", "How to continue:"])
        lines.extend(f"- {item}" for item in guidance)
    elif isinstance(guidance, str) and guidance:
        lines.extend(["", "How to continue:"])
        lines.extend(f"- {item}" for item in guidance.splitlines())
    output["output"] = "\n".join(lines)
