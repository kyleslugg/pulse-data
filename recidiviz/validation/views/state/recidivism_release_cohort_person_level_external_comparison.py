# Recidiviz - a data platform for criminal justice reform
# Copyright (C) 2020 Recidiviz, Inc.
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

"""A view comparing various values from internal person-level recidivism metrics to the person-level values from
external metrics provided by the state.
"""

from recidiviz.big_query.big_query_view import SimpleBigQueryViewBuilder
from recidiviz.calculator.query.state import dataset_config as state_dataset_config
from recidiviz.utils.environment import GCP_PROJECT_STAGING
from recidiviz.utils.metadata import local_project_id_override
from recidiviz.validation.views import dataset_config
from recidiviz.validation.views.state.recidivism_person_level_template import (
    recidivism_person_level_query,
)

RECIDIVISM_RELEASE_COHORT_PERSON_LEVEL_EXTERNAL_COMPARISON_VIEW_NAME = (
    "recidivism_release_cohort_person_level_external_comparison"
)

RECIDIVISM_RELEASE_COHORT_PERSON_LEVEL_EXTERNAL_COMPARISON_DESCRIPTION = """
Comparison of values between internal and external lists of person-level release cohorts and follow-up periods.
"""

RECIDIVISM_RELEASE_COHORT_PERSON_LEVEL_EXTERNAL_COMPARISON_QUERY_TEMPLATE = f"""
{recidivism_person_level_query(include_unmatched_people=True)}
"""

RECIDIVISM_RELEASE_COHORT_PERSON_LEVEL_EXTERNAL_COMPARISON_VIEW_BUILDER = SimpleBigQueryViewBuilder(
    dataset_id=dataset_config.VIEWS_DATASET,
    view_id=RECIDIVISM_RELEASE_COHORT_PERSON_LEVEL_EXTERNAL_COMPARISON_VIEW_NAME,
    view_query_template=RECIDIVISM_RELEASE_COHORT_PERSON_LEVEL_EXTERNAL_COMPARISON_QUERY_TEMPLATE,
    description=RECIDIVISM_RELEASE_COHORT_PERSON_LEVEL_EXTERNAL_COMPARISON_DESCRIPTION,
    external_accuracy_dataset=dataset_config.EXTERNAL_ACCURACY_DATASET,
    materialized_metrics_dataset=state_dataset_config.DATAFLOW_METRICS_MATERIALIZED_DATASET,
    should_materialize=True,
)

if __name__ == "__main__":
    with local_project_id_override(GCP_PROJECT_STAGING):
        RECIDIVISM_RELEASE_COHORT_PERSON_LEVEL_EXTERNAL_COMPARISON_VIEW_BUILDER.build_and_print()
