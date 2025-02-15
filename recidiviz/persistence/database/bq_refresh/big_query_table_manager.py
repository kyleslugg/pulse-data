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
"""Manages the structure of BigQuery tables that share a schema with one of the
SQLAlchemy schemas defined in a schema.py file.
Used during deploy time to update the schema of the BigQuery datasets so that they
match that of the schema being deployed before the next CloudSqlToBQ export or data
pipelines attempt to write these datasets. Does not perform any migrations, only adds
and deletes columns where necessary.
"""
from typing import List, Optional

from google.cloud.bigquery import SchemaField
from sqlalchemy import Table

from recidiviz.big_query.big_query_client import BigQueryClient, BigQueryClientImpl
from recidiviz.big_query.big_query_utils import schema_for_sqlalchemy_table
from recidiviz.persistence.database.bq_refresh.cloud_sql_to_bq_refresh_config import (
    CloudSqlToBQConfig,
)
from recidiviz.persistence.database.schema_type import SchemaType
from recidiviz.persistence.database.schema_utils import (
    is_association_table,
    schema_has_region_code_query_support,
    schema_type_to_schema_base,
)


def bq_schema_for_sqlalchemy_table(
    schema_type: SchemaType, table: Table
) -> List[SchemaField]:
    """Derives a BigQuery table schema from a SQLAlchemy table. Adds region code columns
    to any association table.
    """
    add_state_code_field = schema_has_region_code_query_support(
        schema_type_to_schema_base(schema_type)
    ) and is_association_table(table.name)

    return schema_for_sqlalchemy_table(table, add_state_code_field=add_state_code_field)


def update_bq_schema_for_sqlalchemy_table(
    bq_client: BigQueryClient, schema_type: SchemaType, dataset_id: str, table: Table
) -> None:
    """Updates the schema of the BigQuery table in the dataset that stores the
    contents of the |table| to have all expected columns."""
    bq_dataset_ref = bq_client.dataset_ref_for_id(dataset_id)

    table_id = table.name

    schema_for_table = bq_schema_for_sqlalchemy_table(schema_type, table)

    if bq_client.table_exists(bq_dataset_ref, table_id):
        # Compare schema derived from schema table to existing dataset and
        # update if necessary.
        bq_client.update_schema(
            dataset_id,
            table_id,
            schema_for_table,
        )
    else:
        bq_client.create_table_with_schema(
            dataset_id,
            table_id,
            schema_for_table,
        )


def update_bq_dataset_to_match_sqlalchemy_schema(
    schema_type: SchemaType,
    dataset_id: str,
    default_table_expiration_ms: Optional[int],
    bq_region_override: Optional[str] = None,
) -> None:
    """For each table defined in the schema, ensures that the schema of the
    table the provided BigQuery dataset matches the schema defined in the corresponding
    schema.py.
    """
    bq_client = BigQueryClientImpl(region_override=bq_region_override)
    export_config = CloudSqlToBQConfig.for_schema_type(schema_type)
    bq_dataset_ref = bq_client.dataset_ref_for_id(dataset_id)

    bq_client.create_dataset_if_necessary(bq_dataset_ref, default_table_expiration_ms)

    for table in export_config.get_tables_to_export():
        update_bq_schema_for_sqlalchemy_table(
            bq_client=bq_client,
            schema_type=schema_type,
            dataset_id=dataset_id,
            table=table,
        )
