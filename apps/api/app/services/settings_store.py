"""Reglages modifiables a chaud depuis l'admin, sans redemarrage."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import AppSetting


def get_setting(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(AppSetting, key)
    if row is None:
        return default
    return row.value.get("value", default)


def set_setting(db: Session, key: str, value: Any) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value={"value": value}))
    else:
        row.value = {"value": value}
