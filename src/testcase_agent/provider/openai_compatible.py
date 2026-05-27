import httpx
from openai import OpenAI


class OpenAICompatibleProvider:
    provider_name: str
    model_name: str

    def __init__(
        self,
        api_key: str,
        model_name: str,
        base_url: str,
        provider_name: str = "openai_compatible",
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> None:
        self.model_name = model_name
        self.provider_name = provider_name
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = OpenAI(api_key=api_key or "ollama", base_url=base_url, timeout=httpx.Timeout(120.0, connect=10.0))

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        return response.choices[0].message.content or ""
