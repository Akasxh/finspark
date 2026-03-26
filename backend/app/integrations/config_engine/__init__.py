"""
Auto-Configuration Generation Engine for FinSpark.

Public surface:
    FieldMapper       — fuzzy + semantic field matching with confidence scoring
    SchemaTransformer — type casting, format conversion, nested field flattening
    ConfigGenerator   — orchestrates parsing output + adapter → JSON config
    ConfigDiffEngine  — compare two configs (additions / deletions / modifications)
"""

from app.integrations.config_engine.field_mapper import FieldMapper, FieldMatch
from app.integrations.config_engine.schema_transformer import SchemaTransformer, TransformRule
from app.integrations.config_engine.config_generator import ConfigGenerator, GeneratedConfig
from app.integrations.config_engine.config_diff import ConfigDiffEngine, ConfigDiff, DiffEntry, DiffOp

__all__ = [
    "FieldMapper",
    "FieldMatch",
    "SchemaTransformer",
    "TransformRule",
    "ConfigGenerator",
    "GeneratedConfig",
    "ConfigDiffEngine",
    "ConfigDiff",
    "DiffEntry",
    "DiffOp",
]
