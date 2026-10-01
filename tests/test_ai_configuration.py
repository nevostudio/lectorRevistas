from types import SimpleNamespace

import pytest

import core.detector as detector_module
from core.detector import (
    AIDetector,
    AI_OUTPUT_SCHEMA,
    DEFAULT_AI_MODEL,
)


class _FakeMessages:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text='{"anuncios":[]}')],
            stop_reason="end_turn",
            usage=SimpleNamespace(
                input_tokens=0,
                output_tokens=0,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
        )


def _configured_detector(model=DEFAULT_AI_MODEL):
    instance = object.__new__(AIDetector)
    messages = _FakeMessages()
    instance.client = SimpleNamespace(messages=messages)
    instance.model = model
    instance._progress = lambda _message: None
    instance.usage = {
        "input": 0,
        "output": 0,
        "cache_write": 0,
        "cache_read": 0,
    }
    return instance, messages


def test_modelo_por_defecto_es_sonnet_5_5(monkeypatch):
    fake_client = SimpleNamespace(messages=_FakeMessages())
    monkeypatch.setattr(
        detector_module.anthropic,
        "Anthropic",
        lambda **_kwargs: fake_client,
    )

    detector = AIDetector(api_key="clave-simulada")

    assert detector.model == "claude-sonnet-5-5"


def test_llamada_usa_structured_outputs_sin_acceder_a_la_api():
    detector, messages = _configured_detector()

    response, truncated = detector._call_with_retry([], [1, 2])

    assert response is not None
    assert truncated is False
    assert messages.kwargs["model"] == "claude-sonnet-5-5"
    expected_schema = detector._output_schema([1, 2])
    assert messages.kwargs["output_config"] == {
        "format": {"type": "json_schema", "schema": expected_schema}
    }
    page_schema = expected_schema["properties"]["anuncios"]["items"][
        "properties"]["pagina"]
    assert page_schema["enum"] == [1, 2]
    assert "enum" not in AI_OUTPUT_SCHEMA["properties"]["anuncios"][
        "items"]["properties"]["pagina"]


def test_coste_usa_tarifa_del_modelo_elegido():
    detector, _messages = _configured_detector()
    detector.usage = {
        "input": 1_000_000,
        "output": 1_000_000,
        "cache_write": 1_000_000,
        "cache_read": 1_000_000,
    }

    assert detector.estimated_cost_usd() == pytest.approx(14.70)

    detector.model = "claude-sonnet-4-6"
    assert detector.estimated_cost_usd() == pytest.approx(22.05)
