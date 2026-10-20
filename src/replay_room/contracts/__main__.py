"""Regenerate data/schema/causal_account.schema.json from the pydantic models."""

from replay_room.contracts.causal_account import SCHEMA_PATH, json_schema_text

SCHEMA_PATH.write_text(json_schema_text(), encoding="utf-8")
print(f"wrote {SCHEMA_PATH}")
