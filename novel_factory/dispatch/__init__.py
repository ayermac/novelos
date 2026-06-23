"""Dispatch package for novel_factory.

v6.10.13: Added FlowRouter, StateLoader, Dispatcher for deterministic routing.
"""

from .dispatcher import AutoDispatcher, Dispatcher
from .flow_router import FlowAction, Instruction, RouterState, describe_resume, route
from .state_loader import StateLoader

__all__ = [
    "AutoDispatcher",
    "Dispatcher",
    "FlowAction",
    "Instruction",
    "RouterState",
    "StateLoader",
    "describe_resume",
    "route",
]
