from __future__ import annotations

import logging
from dataclasses import dataclass

from orasnap.config import OracleConfig, ScopeConfig
from orasnap.models import DbObject, ExtractedDdl

try:
    import oracledb
except ImportError:  # pragma: no cover - covered by runtime integration.
    oracledb = None


METADATA_TYPE_MAP = {
    "PACKAGE BODY": "PACKAGE_BODY",
    "TYPE BODY": "TYPE_BODY",
    "MATERIALIZED VIEW": "MATERIALIZED_VIEW",
    "JAVA SOURCE": "JAVA_SOURCE",
    "JAVA CLASS": "JAVA_CLASS",
    "JAVA RESOURCE": "JAVA_RESOURCE",
}


@dataclass(frozen=True)
class ExtractionResult:
    items: list[ExtractedDdl]
    failures: list[str]


class OracleMetadataExtractor:
    def __init__(
        self,
        oracle_config: OracleConfig,
        scope_config: ScopeConfig,
        logger: logging.Logger | None = None,
    ) -> None:
        self.oracle_config = oracle_config
        self.scope_config = scope_config
        self.logger = logger or logging.getLogger(__name__)

    def _require_driver(self) -> None:
        if oracledb is None:
            raise RuntimeError(
                "oracledb package is required. Install dependencies first: pip install -e ."
            )

    def _metadata_type(self, object_type: str) -> str:
        return METADATA_TYPE_MAP.get(object_type.upper(), object_type.upper())

    def _should_bundle_table_related(self) -> bool:
        object_types = {item.upper() for item in self.scope_config.object_types}
        return "TABLE" in object_types and "INDEX" in object_types

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    @staticmethod
    def _quote_literal(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def _configure_transform(self, cursor: "oracledb.Cursor") -> None:
        cursor.execute(
            """
            BEGIN
              DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SQLTERMINATOR', TRUE);
              DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'PRETTY', TRUE);
              DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SEGMENT_ATTRIBUTES', FALSE);
              DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'STORAGE', FALSE);
              DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'TABLESPACE', FALSE);
              DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'PARTITIONING', FALSE);
            END;
            """
        )

    def _discover_objects(self, cursor: "oracledb.Cursor") -> list[DbObject]:
        object_types = [ot.upper() for ot in self.scope_config.object_types]
        if not object_types:
            return []

        include = [schema.upper() for schema in self.scope_config.include_schemas]
        exclude = [schema.upper() for schema in self.scope_config.exclude_schemas]

        bind_values: list[str] = []
        type_placeholders = ", ".join(f":{index}" for index in range(1, len(object_types) + 1))
        bind_values.extend(object_types)

        where_clauses = [
            f"OBJECT_TYPE IN ({type_placeholders})",
            "GENERATED = 'N'",
        ]

        if include:
            start = len(bind_values) + 1
            include_placeholders = ", ".join(
                f":{index}" for index in range(start, start + len(include))
            )
            where_clauses.append(f"OWNER IN ({include_placeholders})")
            bind_values.extend(include)
        elif exclude:
            start = len(bind_values) + 1
            exclude_placeholders = ", ".join(
                f":{index}" for index in range(start, start + len(exclude))
            )
            where_clauses.append(f"OWNER NOT IN ({exclude_placeholders})")
            bind_values.extend(exclude)

        where_sql = "\n              AND ".join(where_clauses)
        sql = f"""
            SELECT OWNER, OBJECT_TYPE, OBJECT_NAME
            FROM ALL_OBJECTS
            WHERE {where_sql}
            ORDER BY OWNER, OBJECT_TYPE, OBJECT_NAME
        """
        cursor.execute(sql, bind_values)
        rows = cursor.fetchall()

        objects: list[DbObject] = []
        bundle_table_related = self._should_bundle_table_related()
        for owner, object_type, object_name in rows:
            owner_upper = str(owner).upper()
            object_type_upper = str(object_type).upper()
            if bundle_table_related and object_type_upper == "INDEX":
                # TABLE 파일에 인덱스를 병합해서 저장하므로 INDEX 단독 파일은 제외.
                continue
            objects.append(
                DbObject(owner=owner_upper, object_type=object_type_upper, object_name=str(object_name))
            )

        if not objects:
            self.logger.warning(
                "No objects discovered. include_schemas=%s, exclude_schemas=%s, object_types=%s",
                include,
                exclude,
                object_types,
            )
        return objects

    def _extract_ddl(self, cursor: "oracledb.Cursor", db_object: DbObject) -> str:
        metadata_type = self._metadata_type(db_object.object_type)
        cursor.execute(
            "SELECT DBMS_METADATA.GET_DDL(:1, :2, :3) FROM DUAL",
            [metadata_type, db_object.object_name, db_object.owner],
        )
        value = cursor.fetchone()[0]
        if value is None:
            raise RuntimeError("GET_DDL returned NULL.")
        if hasattr(value, "read"):
            return value.read()
        return str(value)

    def _extract_table_comments(self, cursor: "oracledb.Cursor", db_object: DbObject) -> list[str]:
        owner = db_object.owner
        table_name = db_object.object_name
        owner_q = self._quote_identifier(owner)
        table_q = self._quote_identifier(table_name)

        statements: list[str] = []

        cursor.execute(
            """
            SELECT c.COLUMN_NAME, c.COMMENTS
            FROM ALL_COL_COMMENTS c
            JOIN ALL_TAB_COLUMNS t
              ON t.OWNER = c.OWNER
             AND t.TABLE_NAME = c.TABLE_NAME
             AND t.COLUMN_NAME = c.COLUMN_NAME
            WHERE c.OWNER = :1
              AND c.TABLE_NAME = :2
              AND c.COMMENTS IS NOT NULL
            ORDER BY t.COLUMN_ID
            """,
            [owner, table_name],
        )
        for column_name, comment_text in cursor.fetchall():
            if comment_text is None:
                continue
            column_q = self._quote_identifier(str(column_name))
            comment_q = self._quote_literal(str(comment_text))
            statements.append(
                f"COMMENT ON COLUMN {owner_q}.{table_q}.{column_q} IS {comment_q};"
            )

        cursor.execute(
            """
            SELECT COMMENTS
            FROM ALL_TAB_COMMENTS
            WHERE OWNER = :1
              AND TABLE_NAME = :2
              AND COMMENTS IS NOT NULL
            """,
            [owner, table_name],
        )
        row = cursor.fetchone()
        if row and row[0] is not None:
            table_comment_q = self._quote_literal(str(row[0]))
            statements.append(f"COMMENT ON TABLE {owner_q}.{table_q} IS {table_comment_q};")

        return statements

    def _extract_table_indexes(self, cursor: "oracledb.Cursor", db_object: DbObject) -> list[str]:
        object_types = {item.upper() for item in self.scope_config.object_types}
        if "INDEX" not in object_types:
            return []

        statements: list[str] = []
        cursor.execute(
            """
            SELECT OWNER, INDEX_NAME
            FROM ALL_INDEXES
            WHERE TABLE_OWNER = :1
              AND TABLE_NAME = :2
              AND GENERATED = 'N'
            ORDER BY OWNER, INDEX_NAME
            """,
            [db_object.owner, db_object.object_name],
        )
        for index_owner, index_name in cursor.fetchall():
            index_object = DbObject(
                owner=str(index_owner).upper(),
                object_type="INDEX",
                object_name=str(index_name),
            )
            try:
                statements.append(self._extract_ddl(cursor, index_object).strip())
            except Exception as exc:  # pragma: no cover - integration path.
                self.logger.warning(
                    "INDEX extraction failed for %s.%s (table=%s.%s): %s",
                    index_object.owner,
                    index_object.object_name,
                    db_object.owner,
                    db_object.object_name,
                    exc,
                )
        return statements

    def _extract_table_bundle_ddl(self, cursor: "oracledb.Cursor", db_object: DbObject) -> str:
        base_ddl = self._extract_ddl(cursor, db_object).strip()
        comments = self._extract_table_comments(cursor, db_object)
        indexes = self._extract_table_indexes(cursor, db_object)

        sections: list[str] = [base_ddl]
        if comments:
            sections.append("\n".join(comments))
        if indexes:
            sections.append("\n\n".join(indexes))
        return "\n\n".join(section for section in sections if section).strip() + "\n"

    def extract(self) -> ExtractionResult:
        self._require_driver()

        items: list[ExtractedDdl] = []
        failures: list[str] = []

        connection = oracledb.connect(
            user=self.oracle_config.username,
            password=self.oracle_config.password,
            dsn=self.oracle_config.dsn,
        )

        try:
            cursor = connection.cursor()
            self._configure_transform(cursor)
            objects = self._discover_objects(cursor)
            self.logger.info("Discovered %s objects.", len(objects))

            for db_object in objects:
                try:
                    if db_object.object_type == "TABLE":
                        ddl = self._extract_table_bundle_ddl(cursor, db_object)
                    else:
                        ddl = self._extract_ddl(cursor, db_object)
                    items.append(ExtractedDdl(db_object=db_object, ddl=ddl))
                except Exception as exc:  # pragma: no cover - integration path.
                    message = (
                        f"{db_object.owner}.{db_object.object_type}.{db_object.object_name}: {exc}"
                    )
                    failures.append(message)
                    self.logger.warning("DDL extraction failed: %s", message)
        finally:
            connection.close()

        return ExtractionResult(items=items, failures=failures)

