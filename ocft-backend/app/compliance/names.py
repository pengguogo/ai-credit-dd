"""Run-scoped reversible aliases for known business and personal names."""
from __future__ import annotations

import re
from collections.abc import Iterable


class NameAliasMap:
    def __init__(self, names: Iterable[str]):
        ordered = sorted({name.strip() for name in names
                          if isinstance(name, str) and len(name.strip()) >= 2},
                         key=lambda name: (-len(name), name))
        self._to_alias = {name: f"实体#{index}" for index, name in enumerate(ordered, 1)}
        self._to_name = {alias: name for name, alias in self._to_alias.items()}
        self._names_pattern = (re.compile("|".join(re.escape(name) for name in ordered))
                               if ordered else None)
        self._aliases_pattern = (re.compile("|".join(
            re.escape(alias) for alias in sorted(self._to_name, key=len, reverse=True)))
            if self._to_name else None)

    def redact_text(self, text: str) -> str:
        if not text or not self._names_pattern:
            return text
        return self._names_pattern.sub(lambda match: self._to_alias[match.group(0)], text)

    def restore_text(self, text: str) -> str:
        if not text or not self._aliases_pattern:
            return text
        return self._aliases_pattern.sub(lambda match: self._to_name[match.group(0)], text)

    def redact_obj(self, value: object) -> object:
        if isinstance(value, dict):
            return {key: self.redact_obj(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.redact_obj(item) for item in value]
        if isinstance(value, tuple):
            return [self.redact_obj(item) for item in value]
        if isinstance(value, str):
            return self.redact_text(value)
        return value

    def restore_obj(self, value: object) -> object:
        if isinstance(value, dict):
            return {key: self.restore_obj(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.restore_obj(item) for item in value]
        if isinstance(value, tuple):
            return [self.restore_obj(item) for item in value]
        if isinstance(value, str):
            return self.restore_text(value)
        return value
