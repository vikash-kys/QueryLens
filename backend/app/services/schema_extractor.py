"""
Schema Extractor: Auto-introspects PostgreSQL schema for LLM context.
Extracts tables, columns, types, FK relationships, comments, and sample values.
"""
from sqlalchemy import text, inspect
from app.core.database import admin_session
from app.models.schemas import TableInfo, ColumnInfo, SchemaResponse
import structlog
import json
from functools import lru_cache
from datetime import datetime, timedelta

log = structlog.get_logger()

_schema_cache: dict = {}
_cache_time: datetime | None = None
_CACHE_TTL = timedelta(minutes=10)


def get_schema(force_refresh: bool = False) -> SchemaResponse:
    """Return full schema, using cache unless stale or forced."""
    global _schema_cache, _cache_time

    if not force_refresh and _cache_time and datetime.utcnow() - _cache_time < _CACHE_TTL:
        return _schema_cache

    log.info("Refreshing schema cache")
    schema = _extract_schema()
    _schema_cache = schema
    _cache_time = datetime.utcnow()
    return schema


def _extract_schema() -> SchemaResponse:
    with admin_session() as conn:
        # Get all tables and views
        tables_query = text("""
            SELECT
                c.table_name,
                c.table_type,
                obj_description(
                    ('"' || c.table_schema || '"."' || c.table_name || '"')::regclass, 'pg_class'
                ) AS comment
            FROM information_schema.tables c
            WHERE c.table_schema = 'public'
              AND c.table_type IN ('BASE TABLE', 'VIEW')
            ORDER BY c.table_name
        """)
        table_rows = conn.execute(tables_query).fetchall()

        tables = []
        relationships = []

        for table_row in table_rows:
            table_name = table_row[0]
            table_comment = table_row[2]

            # Columns
            col_query = text("""
                SELECT
                    col.column_name,
                    col.data_type,
                    col.is_nullable,
                    col_description(
                        ('"public"."' || :tbl || '"')::regclass,
                        col.ordinal_position
                    ) AS comment,
                    col.column_default
                FROM information_schema.columns col
                WHERE col.table_schema = 'public'
                  AND col.table_name = :tbl
                ORDER BY col.ordinal_position
            """)
            col_rows = conn.execute(col_query, {"tbl": table_name}).fetchall()

            # Primary keys
            pk_query = text("""
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                WHERE tc.table_schema = 'public'
                  AND tc.table_name = :tbl
                  AND tc.constraint_type = 'PRIMARY KEY'
            """)
            pks = [r[0] for r in conn.execute(pk_query, {"tbl": table_name}).fetchall()]

            # Foreign keys
            fk_query = text("""
                SELECT
                    kcu.column_name,
                    ccu.table_name AS foreign_table,
                    ccu.column_name AS foreign_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.table_schema = 'public'
                  AND tc.table_name = :tbl
                  AND tc.constraint_type = 'FOREIGN KEY'
            """)
            fks = conn.execute(fk_query, {"tbl": table_name}).fetchall()

            fk_list = []
            for fk in fks:
                fk_list.append({
                    "column": fk[0],
                    "references_table": fk[1],
                    "references_column": fk[2],
                })
                relationships.append({
                    "from_table": table_name,
                    "from_column": fk[0],
                    "to_table": fk[1],
                    "to_column": fk[2],
                })

            # Row count
            try:
                count_res = conn.execute(
                    text(f'SELECT COUNT(*) FROM "{table_name}"')
                ).scalar()
            except Exception:
                count_res = None

            # Build columns with sample values
            columns = []
            for col in col_rows:
                col_name, data_type, nullable, col_comment, _ = col

                # Fetch sample values for categorical / low-cardinality columns
                samples = []
                if data_type in ("character varying", "varchar", "text", "boolean", "USER-DEFINED"):
                    try:
                        sample_query = text(f"""
                            SELECT DISTINCT "{col_name}"
                            FROM "{table_name}"
                            WHERE "{col_name}" IS NOT NULL
                            LIMIT 8
                        """)
                        sample_rows = conn.execute(sample_query).fetchall()
                        samples = [str(r[0]) for r in sample_rows]
                    except Exception:
                        pass

                columns.append(ColumnInfo(
                    name=col_name,
                    type=data_type,
                    nullable=(nullable == "YES"),
                    comment=col_comment,
                    sample_values=samples,
                ))

            tables.append(TableInfo(
                name=table_name,
                comment=table_comment,
                columns=columns,
                row_count=count_res,
                primary_keys=pks,
                foreign_keys=fk_list,
            ))

        return SchemaResponse(tables=tables, relationships=relationships)


def schema_to_prompt_context(schema: SchemaResponse, relevant_tables: list[str] | None = None) -> str:
    """Format schema as a compact, LLM-friendly string."""
    lines = ["DATABASE SCHEMA (PostgreSQL)\n" + "=" * 60]

    for table in schema.tables:
        if relevant_tables and table.name not in relevant_tables:
            continue

        header = f"\nTABLE: {table.name}"
        if table.comment:
            header += f"\n  Description: {table.comment}"
        if table.row_count is not None:
            header += f"\n  Approximate rows: {table.row_count:,}"
        lines.append(header)

        lines.append("  Columns:")
        for col in table.columns:
            col_line = f"    - {col.name} ({col.type})"
            if not col.nullable:
                col_line += " NOT NULL"
            if col.name in table.primary_keys:
                col_line += " [PK]"
            if col.comment:
                col_line += f" -- {col.comment}"
            if col.sample_values:
                samples_str = ", ".join(repr(s) for s in col.sample_values[:6])
                col_line += f"\n      Sample values: {samples_str}"
            lines.append(col_line)

        if table.foreign_keys:
            lines.append("  Foreign Keys:")
            for fk in table.foreign_keys:
                lines.append(f"    - {fk['column']} → {fk['references_table']}.{fk['references_column']}")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)
