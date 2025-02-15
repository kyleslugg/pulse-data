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
# =============================================================================
"""Persons to their most recent county of residence."""

from recidiviz.big_query.big_query_view import SimpleBigQueryViewBuilder
from recidiviz.calculator.query.state import dataset_config
from recidiviz.utils.environment import GCP_PROJECT_STAGING
from recidiviz.utils.metadata import local_project_id_override

PERSONS_TO_RECENT_COUNTY_OF_RESIDENCE_VIEW_NAME = (
    "persons_to_recent_county_of_residence"
)

PERSONS_TO_RECENT_COUNTY_OF_RESIDENCE_DESCRIPTION = (
    """Persons to their most recent county of residence."""
)

PERSONS_TO_RECENT_COUNTY_OF_RESIDENCE_QUERY_TEMPLATE = """
    WITH zip_code_county_map AS (
      SELECT
        UPPER(REPLACE(county_name, " ", "_")) AS normalized_county_name,
        zip AS zip_code,
      FROM
        `{project_id}.{static_reference_dataset}.zip_city_county_state`
    ),
    persons_with_current_zip AS (
      SELECT
        person_id,
        state_code,
        SUBSTR(current_address, -5) AS zip_code,
      FROM
        `{project_id}.{normalized_state_dataset}.state_person`
    )
    SELECT
      state_code,
      person_id,
      CONCAT(state_code, '_', normalized_county_name) AS county_of_residence,
    FROM
      persons_with_current_zip
    JOIN
      zip_code_county_map
    USING (zip_code)
    WHERE state_code IN ('US_ND', 'US_MO')
"""

PERSONS_TO_RECENT_COUNTY_OF_RESIDENCE_VIEW_BUILDER = SimpleBigQueryViewBuilder(
    dataset_id=dataset_config.REFERENCE_VIEWS_DATASET,
    view_id=PERSONS_TO_RECENT_COUNTY_OF_RESIDENCE_VIEW_NAME,
    view_query_template=PERSONS_TO_RECENT_COUNTY_OF_RESIDENCE_QUERY_TEMPLATE,
    description=PERSONS_TO_RECENT_COUNTY_OF_RESIDENCE_DESCRIPTION,
    static_reference_dataset=dataset_config.STATIC_REFERENCE_TABLES_DATASET,
    normalized_state_dataset=dataset_config.NORMALIZED_STATE_DATASET,
)

if __name__ == "__main__":
    with local_project_id_override(GCP_PROJECT_STAGING):
        PERSONS_TO_RECENT_COUNTY_OF_RESIDENCE_VIEW_BUILDER.build_and_print()
