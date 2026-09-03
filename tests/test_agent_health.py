from src.health.agent_health import AgentHealthRecord, calculate_health
from src.models.schemas import HealthStatus


def test_healthy_agent():
    record = AgentHealthRecord()
    assert calculate_health(record) == HealthStatus.HEALTHY


def test_agent_becomes_degraded():
    record = AgentHealthRecord(retries=2)
    assert calculate_health(record) == HealthStatus.DEGRADED


def test_agent_fails_after_repeated_schema_errors():
    record = AgentHealthRecord(schema_failures=3)
    assert calculate_health(record) == HealthStatus.FAILED
