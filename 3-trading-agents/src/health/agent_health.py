from dataclasses import dataclass
from src.models.schemas import HealthStatus

@dataclass
class AgentHealthRecord:
    schema_failures: int = 0
    retries: int = 0
    hallucination_incidents: int = 0
    timeouts: int = 0

def calculate_health(r: AgentHealthRecord) -> HealthStatus:
    if r.hallucination_incidents >= 2 or r.schema_failures >= 3 or r.timeouts >= 3:
        return HealthStatus.FAILED
    if r.schema_failures or r.retries >= 2 or r.hallucination_incidents or r.timeouts:
        return HealthStatus.DEGRADED
    return HealthStatus.HEALTHY
