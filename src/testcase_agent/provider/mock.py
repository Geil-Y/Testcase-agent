class MockProvider:
    provider_name = "mock"
    model_name = "mock"

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return (
            '{"mock": true, "message": "MockProvider returned a placeholder. '
            'Use stage-specific fake providers in review_pipeline tests."}'
        )
