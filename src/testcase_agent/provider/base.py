from typing import Protocol


class LlmProvider(Protocol):
    provider_name: str
    model_name: str

    def complete(self, system_prompt: str, user_prompt: str) -> str: ...
