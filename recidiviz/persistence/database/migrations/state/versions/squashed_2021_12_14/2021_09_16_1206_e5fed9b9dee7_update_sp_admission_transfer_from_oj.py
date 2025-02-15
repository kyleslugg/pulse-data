# pylint: skip-file
"""update_sp_admission_transfer_from_oj

Revision ID: e5fed9b9dee7
Revises: 09fefc551098
Create Date: 2021-09-16 12:04:16.426658

"""
import sqlalchemy as sa
from alembic import op

from recidiviz.utils.string import StrictStringFormatter

# revision identifiers, used by Alembic.
revision = "e5fed9b9dee7"
down_revision = "09fefc551098"
branch_labels = None
depends_on = None


ENUM_VALUE_SELECT_IDS_QUERY = (
    "SELECT supervision_period_id FROM {table_name}"
    " WHERE admission_reason = '{enum_value}'"
)

UPDATE_QUERY = (
    "UPDATE {table_name} SET admission_reason = '{new_value}'"
    " WHERE supervision_period_id IN ({ids_query});"
)


SUPERVISION_PERIOD_TABLE_NAME = "state_supervision_period"
SUPERVISION_PERIOD_HISTORY_TABLE_NAME = "state_supervision_period_history"


def upgrade() -> None:
    connection = op.get_bind()

    old_value = "TRANSFER_OUT_OF_STATE"
    new_value = "TRANSFER_FROM_OTHER_JURISDICTION"

    with op.get_context().autocommit_block():
        for table_name in [
            SUPERVISION_PERIOD_TABLE_NAME,
            SUPERVISION_PERIOD_HISTORY_TABLE_NAME,
        ]:
            connection.execute(
                StrictStringFormatter().format(
                    UPDATE_QUERY,
                    table_name=table_name,
                    new_value=new_value,
                    ids_query=StrictStringFormatter().format(
                        ENUM_VALUE_SELECT_IDS_QUERY,
                        table_name=table_name,
                        enum_value=old_value,
                    ),
                )
            )


def downgrade() -> None:
    connection = op.get_bind()

    old_value = "TRANSFER_FROM_OTHER_JURISDICTION"
    new_value = "TRANSFER_OUT_OF_STATE"

    with op.get_context().autocommit_block():
        for table_name in [
            SUPERVISION_PERIOD_TABLE_NAME,
            SUPERVISION_PERIOD_HISTORY_TABLE_NAME,
        ]:
            connection.execute(
                StrictStringFormatter().format(
                    UPDATE_QUERY,
                    table_name=table_name,
                    new_value=new_value,
                    ids_query=StrictStringFormatter().format(
                        ENUM_VALUE_SELECT_IDS_QUERY,
                        table_name=table_name,
                        enum_value=old_value,
                    ),
                )
            )
