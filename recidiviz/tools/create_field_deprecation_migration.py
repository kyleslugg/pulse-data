# Recidiviz - a data platform for criminal justice reform
# Copyright (C) 2021 Recidiviz, Inc.
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
# =============================================================================
"""Script to generate an alembic migration for deprecating a field on an entity for a
state_code by setting the value of all instances to null.

Usage:
python -m recidiviz.tools.create_field_deprecation_migration \
    --primary-table <primary table name> --column <column name> \
    --state-code-to-deprecate <state code to deprecate> \
    --migration-name <name for migration> \

Example:
python -m recidiviz.tools.create_field_deprecation_migration \
    --primary-table state_incarceration_period --column incarceration_type \
    --state-code-to-deprecate US_XX --state-code-to-deprecate US_YY \
    --migration-name drop_incarceration_type_us_xx_us_yy

"""
import argparse
import os
from typing import List

from recidiviz.persistence.database import migrations
from recidiviz.persistence.database.schema_type import SchemaType
from recidiviz.persistence.database.schema_utils import (
    get_table_class_by_name,
    schema_type_to_schema_base,
)
from recidiviz.persistence.database.sqlalchemy_database_key import SQLAlchemyDatabaseKey
from recidiviz.persistence.entity.base_entity import EnumEntity
from recidiviz.tools.utils.migration_script_helpers import (
    create_new_empty_migration_and_return_filename,
    get_migration_header_section,
    path_to_versions_directory,
)
from recidiviz.utils.string import StrictStringFormatter

_PATH_TO_BODY_SECTION_TEMPLATE = os.path.join(
    os.path.dirname(migrations.__file__), "field_deprecation_migration_template.txt"
)


def _get_migration_body_section(
    primary_table_name: str,
    columns_to_nullify: List[str],
    state_codes_to_deprecate: List[str],
) -> str:
    """Returns string of body section of field deprecation migration by interpolating
    provided values into field deprecation migration template
    """
    with open(_PATH_TO_BODY_SECTION_TEMPLATE, "r", encoding="utf-8") as template_file:
        template = template_file.read()

    return StrictStringFormatter().format(
        template,
        primary_table=primary_table_name,
        columns=", ".join([f"'{col}'" for col in columns_to_nullify]),
        state_codes_to_deprecate=", ".join(
            [f"'{state_code}'" for state_code in state_codes_to_deprecate]
        ),
    )


def _create_parser() -> argparse.ArgumentParser:
    """Creates an argparser for the script."""
    parser = argparse.ArgumentParser(description="Autogenerate local migration.")
    parser.add_argument(
        "--migration-name",
        type=str,
        help="String message passed to alembic to apply to the revision.",
        required=True,
    )
    parser.add_argument(
        "--primary-table",
        type=str,
        help="Name of the primary table where the migration will be run.",
        required=True,
    )
    parser.add_argument(
        "--column",
        type=str,
        help="Name of the column whose values will be updated to be null.",
        required=True,
    )
    parser.add_argument(
        "--state-code-to-deprecate",
        type=str,
        help="The state_code being deprecated. Can be repeated to deprecate the field for multiple states.",
        required=True,
        action="append",
        default=[],
    )

    return parser


def main() -> None:
    """Implements the main function of the script."""
    parser = _create_parser()
    args = parser.parse_args()

    table_class = get_table_class_by_name(
        args.primary_table,
        tables=schema_type_to_schema_base(SchemaType.STATE).metadata.sorted_tables,
    )

    all_column_names = [col.name for col in table_class.columns]
    if args.column not in all_column_names:
        raise ValueError(
            f"{args.column} is not a valid column name on table "
            f"{args.primary_table}."
        )

    columns_to_nullify = [args.column]

    raw_text_col = args.column + EnumEntity.RAW_TEXT_FIELD_SUFFIX
    if raw_text_col in all_column_names:
        # If this field has a corresponding _raw_text column in the table, deprecate that
        # as well
        columns_to_nullify.append(raw_text_col)

    # NOTE: We use prints instead of logging because the call out to alembic
    # does something to mess with our logging levels.
    key = SQLAlchemyDatabaseKey.canonical_for_schema(SchemaType.STATE)
    migration_filename = create_new_empty_migration_and_return_filename(
        key, args.migration_name
    )
    migration_filepath = os.path.join(
        path_to_versions_directory(key), migration_filename
    )
    header_section = get_migration_header_section(migration_filepath)
    body_section = _get_migration_body_section(
        args.primary_table,
        columns_to_nullify,
        args.state_code_to_deprecate,
    )
    file_content = f"{header_section}\n{body_section}"

    with open(migration_filepath, "w", encoding="utf-8") as migration_file:
        migration_file.write(file_content)

    print(f"Successfully generated migration: {migration_filename}")


if __name__ == "__main__":
    main()
