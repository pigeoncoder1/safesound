import pytest

from safesound import llm


@pytest.fixture(autouse=True)
def no_real_llm_by_default(monkeypatch):
    monkeypatch.setattr(llm, "PROVIDER", "none")
