"""
FinSpark Module 4 — Simulation & Testing Framework.

Public surface:

    from finspark.simulation import (
        MockAPIServer,
        IntegrationSimulator,
        VersionTester,
        RollbackManager,
        ConfigSnapshot,
        Sandbox,
        SandboxRegistry,
        validate_contract,
        text_report,
        json_report,
        junit_xml,
        print_report,
        version_comparison_text,
    )

All data-model types live in `finspark.simulation.types`.
"""
from finspark.simulation.contract import validate_contract
from finspark.simulation.mock_server import MockAPIServer, generate_mock_response
from finspark.simulation.reporter import (
    json_report,
    junit_xml,
    print_report,
    text_report,
    version_comparison_text,
)
from finspark.simulation.rollback import ConfigSnapshot, RollbackManager
from finspark.simulation.sandbox import Sandbox, SandboxRegistry
from finspark.simulation.simulator import IntegrationSimulator
from finspark.simulation.types import (
    AdapterKind,
    AdapterSchema,
    EndpointSchema,
    FieldAccuracy,
    FieldMapping,
    IntegrationConfig,
    SimulationReport,
    StepResult,
    StepStatus,
    VersionComparisonResult,
)
from finspark.simulation.version_tester import VersionTester

__all__ = [
    # HTTP mocking
    "MockAPIServer",
    "generate_mock_response",
    # Simulation
    "IntegrationSimulator",
    "VersionTester",
    # Rollback
    "RollbackManager",
    "ConfigSnapshot",
    # Sandbox
    "Sandbox",
    "SandboxRegistry",
    # Contract
    "validate_contract",
    # Reporting
    "text_report",
    "json_report",
    "junit_xml",
    "print_report",
    "version_comparison_text",
    # Types
    "AdapterKind",
    "AdapterSchema",
    "EndpointSchema",
    "FieldAccuracy",
    "FieldMapping",
    "IntegrationConfig",
    "SimulationReport",
    "StepResult",
    "StepStatus",
    "VersionComparisonResult",
]
