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
"""Query containing MDOC client information."""
from recidiviz.ingest.direct.regions.us_me.ingest_views.us_me_view_query_fragments import (
    VIEW_CLIENT_FILTER_CONDITION,
)
from recidiviz.ingest.direct.views.direct_ingest_view_query_builder import (
    DirectIngestViewQueryBuilder,
)
from recidiviz.utils.environment import GCP_PROJECT_STAGING
from recidiviz.utils.metadata import local_project_id_override

VIEW_QUERY_TEMPLATE = f""" # nosec
    SELECT DISTINCT
        Client_Id,
        First_Name,
        -- Remove matches for names like (cd-01-03), **Warrant**, and '--'
        -- Formats middle names to remove digits, colons, parenthesis, or "maiden", i.e. (First), A:, FIRST (maiden: LAST)
        IF(REGEXP_CONTAINS(Middle_Name, r'[\\*~\\d]|\\(cd|^[-]+'), NULL, TRIM(REGEXP_REPLACE(Middle_Name, r'["\\d\\(\\):]|maiden:\\s', ''))) AS Middle_Name,
        Last_Name,
        Birth_Date,
        Cis_9012_Gender_Cd AS Gender,
        Cis_1016_Hispanic_Cd AS Ethnicity,
        Cis_1006_Race_Cd AS Race
    FROM {{CIS_100_CLIENT}}
    WHERE {VIEW_CLIENT_FILTER_CONDITION}
"""

VIEW_BUILDER = DirectIngestViewQueryBuilder(
    region="us_me",
    ingest_view_name="CLIENT",
    view_query_template=VIEW_QUERY_TEMPLATE,
    order_by_cols="Client_Id",
)

if __name__ == "__main__":
    with local_project_id_override(GCP_PROJECT_STAGING):
        VIEW_BUILDER.build_and_print()
