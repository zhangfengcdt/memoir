"""
Intent Engine.

Analyzes request intent signatures for model routing optimization (arbitrage).
"""

from memoir.proxy.intent.classifier import Intent, IntentClassifier
from memoir.proxy.intent.routing import ModelRouter, RoutingDecision

__all__ = [
    "Intent",
    "IntentClassifier",
    "ModelRouter",
    "RoutingDecision",
]
