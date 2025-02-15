# Recidiviz - a data platform for criminal justice reform
# Copyright (C) 2019 Recidiviz, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ============================================================================

"""Utilities for working with the database schemas."""
import inspect
import sys
from functools import lru_cache
from types import ModuleType
from typing import Any, Iterator, List, Optional, Tuple, Type

import sqlalchemy
from sqlalchemy import ForeignKeyConstraint, Table
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.orm import RelationshipProperty

from recidiviz.persistence.database.base_schema import (
    CaseTriageBase,
    JusticeCountsBase,
    OperationsBase,
    PathwaysBase,
    StateBase,
)
from recidiviz.persistence.database.database_entity import DatabaseEntity
from recidiviz.persistence.database.schema.case_triage import (
    schema as case_triage_schema,
)
from recidiviz.persistence.database.schema.justice_counts import (
    schema as justice_counts_schema,
)
from recidiviz.persistence.database.schema.operations import schema as operations_schema
from recidiviz.persistence.database.schema.outliers import schema as outliers_schema
from recidiviz.persistence.database.schema.outliers.schema import OutliersBase
from recidiviz.persistence.database.schema.pathways import schema as pathways_schema
from recidiviz.persistence.database.schema.state import schema as state_schema
from recidiviz.persistence.database.schema_type import SchemaType

_SCHEMA_MODULES: List[ModuleType] = [
    case_triage_schema,
    justice_counts_schema,
    pathways_schema,
    state_schema,
    operations_schema,
    outliers_schema,
]

BQ_TYPES = {
    sqlalchemy.Boolean: "BOOL",
    sqlalchemy.Date: "DATE",
    sqlalchemy.DateTime: "DATETIME",
    sqlalchemy.Enum: "STRING",
    sqlalchemy.Integer: "INT64",
    sqlalchemy.String: "STRING",
    sqlalchemy.Text: "STRING",
    sqlalchemy.ARRAY: "ARRAY",
}


def get_all_table_classes() -> Iterator[Table]:
    for module in _SCHEMA_MODULES:
        yield from get_all_table_classes_in_module(module)


def get_foreign_key_constraints(table: Table) -> List[ForeignKeyConstraint]:
    return [
        constraint
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    ]


def get_table_class_by_name(table_name: str, tables: List[Table]) -> Table:
    """Return a Table class object by its table_name"""
    for table in tables:
        if table.name == table_name:
            return table
    raise ValueError(f"{table_name}: Table name not found in list of tables.")


def get_region_code_col(metadata_base: DeclarativeMeta, table: Table) -> str:
    if metadata_base == StateBase:
        if hasattr(table.c, "state_code") or is_association_table(table.name):
            return "state_code"
    if metadata_base == OperationsBase:
        if hasattr(table.c, "region_code"):
            return "region_code"
    raise ValueError(f"Unexpected table is missing a region code field: [{table.name}]")


def schema_has_region_code_query_support(metadata_base: DeclarativeMeta) -> bool:
    """NOTE: The CloudSQL -> BQ refresh must run once without any filtered region codes for each newly added SchemaType.
    This ensures the region_code column is added to tables that are missing it before a query tries to
    filter for that column.
    """
    return metadata_base in (StateBase, OperationsBase)


def is_association_table(table_name: str) -> bool:
    return table_name.endswith("_association")


def get_all_table_classes_in_module(module: ModuleType) -> Iterator[Type[Table]]:
    all_members_in_current_module = inspect.getmembers(sys.modules[module.__name__])
    for _, member in all_members_in_current_module:
        if isinstance(member, Table):
            yield member
        elif _is_database_entity_subclass(member):
            if "__tablename__" in member.__dict__:
                # When using SQLAlchemy's single table inheritance (https://docs.sqlalchemy.org/en/14/orm/inheritance.html#single-table-inheritance)
                # we define a class in our schema that extends from another class, and will look like its own table,
                # but is actually not. Instances of this subclass will actually exist as rows in the parent class's table.
                # The way we can distinguish this case is that the subclass does not have a "__tablename__" attribute.
                yield member.__table__


def get_justice_counts_table_classes() -> Iterator[Table]:
    yield from get_all_table_classes_in_module(justice_counts_schema)


def get_state_table_classes() -> Iterator[Table]:
    yield from get_all_table_classes_in_module(state_schema)


def get_state_entity_names() -> Iterator[str]:
    for state_table_class in get_all_table_classes_in_module(state_schema):
        yield state_table_class.name


def get_operations_table_classes() -> Iterator[Table]:
    yield from get_all_table_classes_in_module(operations_schema)


def get_case_triage_table_classes() -> Iterator[Table]:
    yield from get_all_table_classes_in_module(case_triage_schema)


def get_pathways_table_classes() -> Iterator[Table]:
    yield from get_all_table_classes_in_module(pathways_schema)


def get_pathways_database_entities() -> List[Type[DatabaseEntity]]:
    return list(get_all_database_entities_in_module(pathways_schema))


def get_outliers_database_entities() -> List[Type[DatabaseEntity]]:
    return list(get_all_database_entities_in_module(outliers_schema))


def get_outliers_table_classes() -> Iterator[Table]:
    yield from get_all_table_classes_in_module(outliers_schema)


def get_state_database_entities() -> List[Type[DatabaseEntity]]:
    to_return = []
    for cls in get_all_database_entities_in_module(state_schema):
        to_return.append(cls)
    return to_return


def get_all_database_entities_in_module(
    module: ModuleType,
) -> Iterator[Type[DatabaseEntity]]:
    """This should only be called in tests and by the
    `get_state_database_entity_with_name` function."""
    all_members_in_current_module = inspect.getmembers(sys.modules[module.__name__])
    for _, member in all_members_in_current_module:
        if _is_database_entity_subclass(member):
            yield member


def get_database_entity_by_table_name(
    module: ModuleType, table_name: str
) -> Type[DeclarativeMeta]:
    for name in dir(module):
        member = getattr(module, name)
        if not _is_database_entity_subclass(member):
            continue

        if member.__table__.name == table_name:
            return member

    raise ValueError(f"Could not find model with table named {table_name}")


def get_database_entities_by_association_table(
    module: ModuleType, table_name: str
) -> Tuple[Type[DeclarativeMeta], Type[DeclarativeMeta]]:
    """Returns the database entities associated with the association table."""
    parent_member = None
    child_member = None
    for name in dir(module):
        member = getattr(module, name)
        if not _is_database_entity_subclass(member):
            continue

        try:
            for (
                relationship
            ) in member.get_relationship_property_names_and_properties().values():
                if relationship.secondary.name == table_name:
                    parent_member = member
                    child_member = getattr(module, relationship.argument)
        except AttributeError:
            continue

    if not child_member or not parent_member:
        raise ValueError(
            f"Could not find model with association table named {table_name}"
        )

    return child_member, parent_member


def get_primary_key_column_name(
    schema_module: ModuleType, table_name: str
) -> Optional[str]:
    """Return the column name of the primary key associated with the given table name"""
    if is_association_table(table_name):
        # Association tables don't have primary keys
        return None

    database_entity = get_database_entity_by_table_name(schema_module, table_name)
    return database_entity.get_primary_key_column_name()


def _is_database_entity_subclass(member: Any) -> bool:
    return (
        inspect.isclass(member)
        and issubclass(member, DatabaseEntity)
        and member is not DatabaseEntity
        and member is not JusticeCountsBase
        and member is not StateBase
        and member is not OperationsBase
        and member is not CaseTriageBase
        and member is not PathwaysBase
        and member is not OutliersBase
    )


@lru_cache(maxsize=None)
def get_state_database_entity_with_name(class_name: str) -> Type[StateBase]:
    state_table_classes = get_all_database_entities_in_module(state_schema)

    for member in state_table_classes:
        if member.__name__ == class_name:
            return member

    raise LookupError(
        f"Entity class {class_name} does not exist in " f"{state_schema.__name__}."
    )


@lru_cache(maxsize=None)
def get_state_database_association_with_names(
    child_class_name: str, parent_class_name: str
) -> Table:
    parent_entity = get_state_database_entity_with_name(parent_class_name)
    parent_relationships: List[
        RelationshipProperty
    ] = parent_entity.get_relationship_property_names_and_properties().values()

    for relationship in parent_relationships:
        if (
            relationship.secondary is not None
            and relationship.argument == child_class_name
        ):
            return relationship.secondary

    raise LookupError(
        f"Association table with {child_class_name} and {parent_class_name} does not in exist in "
        f"{state_schema.__name__}"
    )


def schema_type_for_schema_module(module: ModuleType) -> SchemaType:
    if module == state_schema:
        return SchemaType.STATE
    if module == operations_schema:
        return SchemaType.OPERATIONS

    raise ValueError(f"Unsupported module: {module}")


def schema_type_for_object(schema_object: DatabaseEntity) -> SchemaType:
    if isinstance(schema_object, JusticeCountsBase):
        return SchemaType.JUSTICE_COUNTS
    if isinstance(schema_object, StateBase):
        return SchemaType.STATE
    if isinstance(schema_object, OperationsBase):
        return SchemaType.OPERATIONS
    if isinstance(schema_object, CaseTriageBase):
        return SchemaType.CASE_TRIAGE
    if isinstance(schema_object, PathwaysBase):
        return SchemaType.PATHWAYS
    if isinstance(schema_object, OutliersBase):
        return SchemaType.OUTLIERS

    raise ValueError(f"Object of type [{type(schema_object)}] has unknown schema base.")


def schema_type_to_schema_base(schema_type: SchemaType) -> DeclarativeMeta:
    if schema_type == SchemaType.STATE:
        return StateBase
    if schema_type == SchemaType.OPERATIONS:
        return OperationsBase
    if schema_type == SchemaType.JUSTICE_COUNTS:
        return JusticeCountsBase
    if schema_type == SchemaType.CASE_TRIAGE:
        return CaseTriageBase
    if schema_type == SchemaType.PATHWAYS:
        return PathwaysBase
    if schema_type == SchemaType.OUTLIERS:
        return OutliersBase

    raise ValueError(f"Unexpected schema type [{schema_type}].")
