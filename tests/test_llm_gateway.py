"""Tests for LLM circuit breaker behavior."""

from src.services import llm_gateway


class TestCircuitBreaker:
    def setup_method(self) -> None:
        llm_gateway.reset_circuit_breaker()

    def test_opens_after_max_failures(self) -> None:
        llm_gateway.configure_circuit_breaker(2)
        llm_gateway._record_failure()
        assert not llm_gateway.is_circuit_open()
        llm_gateway._record_failure()
        assert llm_gateway.is_circuit_open()

    def test_success_closes_circuit(self) -> None:
        llm_gateway.configure_circuit_breaker(1)
        llm_gateway._record_failure()
        assert llm_gateway.is_circuit_open()
        llm_gateway._record_success()
        assert not llm_gateway.is_circuit_open()

    def test_reset_clears_state(self) -> None:
        llm_gateway.configure_circuit_breaker(1)
        llm_gateway._record_failure()
        assert llm_gateway.is_circuit_open()
        llm_gateway.reset_circuit_breaker()
        assert not llm_gateway.is_circuit_open()
