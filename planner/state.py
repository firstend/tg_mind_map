"""Состояние мультишагового планировщика."""

from dataclasses import dataclass, field


@dataclass
class ToolResult:
    """Результат вызова инструмента на одном шаге."""
    server: str
    tool: str
    args_used: dict
    refined_prompt: str | None
    result: str


@dataclass
class StepState:
    """Состояние одного шага планирования."""
    original_query: str
    results: list[ToolResult] = field(default_factory=list)
    remaining_goal: str = ""
    step_number: int = 0
    max_steps: int = 20

    @property
    def is_done(self) -> bool:
        return self.step_number >= self.max_steps
