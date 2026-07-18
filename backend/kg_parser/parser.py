"""KG Parser Module  —  WO-20260609-001, Sprint 1"""
from __future__ import annotations
import json, logging
from pathlib import Path
from typing import Union
from pydantic import ValidationError
from models.kg_models import KnowledgeGraph

logger = logging.getLogger(__name__)


class KGParseError(ValueError):
    pass


class KGParser:
    def parse_file(self, path: Union[str, Path]) -> KnowledgeGraph:
        path = Path(path)
        if not path.exists():
            raise KGParseError(f"File not found: {path}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise KGParseError(f"Invalid JSON: {e}") from e
        return self._validate(raw, str(path))

    def parse_string(self, s: str) -> KnowledgeGraph:
        try:
            raw = json.loads(s)
        except json.JSONDecodeError as e:
            raise KGParseError(f"Invalid JSON: {e}") from e
        return self._validate(raw, "<string>")

    def parse_dict(self, raw: dict) -> KnowledgeGraph:
        return self._validate(raw, "<dict>")

    def _validate(self, raw: dict, source: str) -> KnowledgeGraph:
        try:
            kg = KnowledgeGraph(**raw)
        except ValidationError as e:
            errors = "; ".join(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors())
            raise KGParseError(f"Schema validation failed ({source}): {errors}") from e
        logger.info("KG parsed (%s): %d devices | %d events | %d relationships",
                    source, len(kg.devices), len(kg.events), len(kg.relationships))
        return kg
