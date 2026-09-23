"""DomainWorkflowGraph — inner BaseGraph for RET-C2-640 loyalty dispute workflow."""

from __future__ import annotations

from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from src.nodes.evidence_retrieval_node import EvidenceRetrievalNode
from src.nodes.exception_pattern_node import ExceptionPatternNode
from src.nodes.offer_rule_analysis_node import OfferRuleAnalysisNode
from src.nodes.response_draft_node import ResponseDraftNode
from src.schemas.state import State


class LoyaltyDisputeWorkflowGraph(BaseGraph):
    """Inner domain workflow graph for RET-C2-640 loyalty dispute resolution.

    Inherits BaseGraph directly for a fully custom node topology.
    Called by LoyaltyDisputeGraphNode.get_subgraph() in graph.py.

    Pipeline:
        START
          -> evidence_retrieval    (fetch offer rules + loyalty history)
             [ERROR -> END]
          -> offer_rule_analysis   (map rules to applicability factors)
             [ERROR -> END]
          -> exception_pattern     (map prior disputes / exception patterns)
          -> response_draft        (compose draft + HITL review interrupt)
             [ERROR -> END]
          -> END
    """

    @property
    def name(self) -> str:
        return "loyalty_dispute_workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        """No mandatory config keys for this inner graph."""
        pass

    def register_nodes(self) -> None:
        """Register all domain nodes (no super() — BaseGraph.register_nodes() is abstract)."""
        self._nodes["evidence_retrieval"] = EvidenceRetrievalNode()
        self._nodes["offer_rule_analysis"] = OfferRuleAnalysisNode()
        self._nodes["exception_pattern"] = ExceptionPatternNode()
        self._nodes["response_draft"] = ResponseDraftNode(llm=self.config.get("llm"))

    def add_edges(self) -> None:
        """Wire conditional edges: error in any node routes to END."""
        self._sg.add_edge(START, "evidence_retrieval")
        self._sg.add_conditional_edges(
            "evidence_retrieval",
            self._continue_or_end,
            {"continue": "offer_rule_analysis", "end": END},
        )
        self._sg.add_conditional_edges(
            "offer_rule_analysis",
            self._continue_or_end,
            {"continue": "exception_pattern", "end": END},
        )
        self._sg.add_edge("exception_pattern", "response_draft")
        self._sg.add_edge("response_draft", END)

    @staticmethod
    def _continue_or_end(state: AgentState) -> str:
        return "end" if state.get("status") == AgentStatus.ERROR.value else "continue"

    def route(self, state: AgentState) -> str:
        """Generic routing: ERROR -> END, else continue to next node.

        Required by BaseGraph ABC; used by offer_rule_analysis and response_draft edges.
        """
        return str(END)

    def get_output(self, state: AgentState) -> dict:
        """Shape the sub_result dict returned to the outer GraphNode.merge_output()."""
        return {
            "response_draft": state.get("response_draft", ""),
            "briefing_summary": state.get("briefing_summary", ""),
            "review_disposition": state.get("review_disposition", ""),
            "review_notes": state.get("review_notes", ""),
            "applicability_factors_json": state.get("applicability_factors_json", ""),
            "constraints_json": state.get("constraints_json", ""),
            "evidence_gaps_json": state.get("evidence_gaps_json", ""),
            "exception_factors_json": state.get("exception_factors_json", ""),
            "exception_citations_json": state.get("exception_citations_json", ""),
            "prior_outcomes_json": state.get("prior_outcomes_json", ""),
            "offer_rules_json": state.get("offer_rules_json", ""),
            "loyalty_history_json": state.get("loyalty_history_json", ""),
            "evidence_sources_json": state.get("evidence_sources_json", ""),
            "evidence_retrieved": state.get("evidence_retrieved", False),
            "retrieval_unavailable": state.get("retrieval_unavailable", False),
            "analysis_complete": state.get("analysis_complete", False),
            "exception_analysis_complete": state.get("exception_analysis_complete", False),
            "hitl_draft": state.get("hitl_draft", ""),
            "status": state.get("status", ""),
            "error_log": state.get("error_log", []),
        }


# Alias used in graph.py import
DomainWorkflowGraph = LoyaltyDisputeWorkflowGraph
