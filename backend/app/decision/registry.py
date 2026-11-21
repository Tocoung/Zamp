"""Registry and singleton instance management for the decision engine."""

from app.decision.config import DecisionConfig
from app.decision.engine import DecisionEngine


class DecisionRegistry:
    """Manages global decision engine and configuration instances."""

    def __init__(self):
        self._config = DecisionConfig()
        self._engine = DecisionEngine(default_config=self._config)

    @property
    def config(self) -> DecisionConfig:
        return self._config

    @property
    def engine(self) -> DecisionEngine:
        return self._engine

    def reset(self):
        """Resets registry to default configuration."""
        self._config = DecisionConfig()
        self._engine = DecisionEngine(default_config=self._config)


decision_registry = DecisionRegistry()
decision_engine = decision_registry.engine
