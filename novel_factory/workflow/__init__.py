"""Workflow package for novel_factory.

v6.10.13: Added flow integration for deterministic routing.
"""

from .flow_integration import FlowIntegration, flow_control_node, create_flow_control_node

__all__ = [
    "FlowIntegration",
    "flow_control_node",
    "create_flow_control_node",
]
