"""Regression: /api/v1/tasks SQL query must compile for PostgreSQL.

Protects against accidental use of diaclect-specific helpers like
`.astext` on the generic `sqlalchemy.JSON` comparator, which fails at
runtime with AttributeError.
"""

from __future__ import annotations

from sqlalchemy import cast, func, select, String
from sqlalchemy.dialects import postgresql

from src.models.db import Task


def test_tasks_query_compiles_for_postgres():
    gen_url_filter = (
        cast(Task.result["generated_image_url"], String).isnot(None)
        | cast(Task.result["image_url"], String).isnot(None)
        | cast(Task.result["generated_image_path"], String).isnot(None)
    )
    q = select(func.count(Task.id)).where(gen_url_filter)
    sql = str(
        q.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "CAST" in sql.upper()
    assert "generated_image_url" in sql
    assert "image_url" in sql
    assert "generated_image_path" in sql
