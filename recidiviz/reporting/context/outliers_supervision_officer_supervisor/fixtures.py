# Recidiviz - a data platform for criminal justice reform
# Copyright (C) 2023 Recidiviz, Inc.
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
"""Fixtures for developing and testing the OutliersSupervisionOfficerSupervisor report"""
from typing import Dict, List, Optional

from recidiviz.outliers.constants import (
    ABSCONSIONS_BENCH_WARRANTS,
    EARLY_DISCHARGE_REQUESTS,
    INCARCERATION_STARTS,
    INCARCERATION_STARTS_TECHNICAL_VIOLATION,
    TASK_COMPLETIONS_FULL_TERM_DISCHARGE,
    TASK_COMPLETIONS_TRANSFER_TO_LIMITED_SUPERVISION,
)
from recidiviz.outliers.querier.querier import (
    OfficerMetricEntity,
    OutlierMetricInfo,
    TargetStatus,
)
from recidiviz.outliers.types import (
    OutliersMetricConfig,
    PersonName,
    TargetStatusStrategy,
)

metric_fixtures = {
    INCARCERATION_STARTS: OutliersMetricConfig.build_from_metric(
        metric=INCARCERATION_STARTS,
        title_display_name="Incarceration Rate",
        body_display_name="incarceration rate",
        event_name="incarcerations",
        event_name_singular="incarceration",
    ),
    ABSCONSIONS_BENCH_WARRANTS: OutliersMetricConfig.build_from_metric(
        metric=ABSCONSIONS_BENCH_WARRANTS,
        title_display_name="Absconsion Rate",
        body_display_name="absconsion rate",
        event_name="absconsions",
        event_name_singular="absconsion",
    ),
    TASK_COMPLETIONS_FULL_TERM_DISCHARGE: OutliersMetricConfig.build_from_metric(
        metric=TASK_COMPLETIONS_FULL_TERM_DISCHARGE,
        title_display_name="Successful Completion Rate",
        body_display_name="successful completion rate",
        event_name="successful completions",
        event_name_singular="successful completion",
    ),
    TASK_COMPLETIONS_TRANSFER_TO_LIMITED_SUPERVISION: OutliersMetricConfig.build_from_metric(
        metric=TASK_COMPLETIONS_TRANSFER_TO_LIMITED_SUPERVISION,
        title_display_name="Limited Supervision Unit Transfer Rate",
        body_display_name="Limited Supervision Unit transfer rate",
        event_name="LSU transfers",
        event_name_singular="LSU transfer",
    ),
    EARLY_DISCHARGE_REQUESTS: OutliersMetricConfig.build_from_metric(
        metric=EARLY_DISCHARGE_REQUESTS,
        title_display_name="Earned Discharge Request Rate",
        body_display_name="earned discharge request rate",
        event_name="earned discharge requests",
        event_name_singular="earned discharge request",
    ),
    INCARCERATION_STARTS_TECHNICAL_VIOLATION: OutliersMetricConfig.build_from_metric(
        metric=INCARCERATION_STARTS_TECHNICAL_VIOLATION,
        title_display_name="Technical Incarceration Rate",
        body_display_name="technical incarceration rate",
        event_name="technical incarcerations",
        event_name_singular="technical incarceration",
    ),
}

target_fixture_adverse = 0.05428241659992843

other_officers_fixture_adverse = {
    TargetStatus.MET: [
        0.013664782299427202,
        0,
        0,
        0.01986070301447383,
        0.023395936157938592,
    ],
    TargetStatus.NEAR: [
        0.05557247259439707,
        0.06803989188181564,
        0.0880180859080633,
    ],
    TargetStatus.FAR: [
        0.24142872891632675,
        0.2114256751864456,
        0.10346978115432588,
    ],
}

target_fixture_favorable = 0.093735
other_officers_fixture_favorable = {
    TargetStatus.FAR: [
        0.013664782299427202,
        0,
        0,
        0.01986070301447383,
        0.023395936157938592,
    ],
    TargetStatus.NEAR: [
        0.05557247259439707,
        0.06803989188181564,
        0.0880180859080633,
    ],
    TargetStatus.MET: [
        0.24142872891632675,
        0.2114256751864456,
        0.10346978115432588,
    ],
}

target_fixture_favorable_zero = 0.038641985
other_officers_fixture_favorable_zero = {
    TargetStatus.NEAR: [
        0.013664782299427202,
        0.014664782299427202,
        0.017299427202,
        0.01986070301447383,
        0.023395936157938592,
    ],
    TargetStatus.MET: [
        0.05557247259439707,
        0.06803989188181564,
        0.0880180859080633,
        0.24142872891632675,
        0.2114256751864456,
        0.10346978115432588,
    ],
    TargetStatus.FAR: [
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
    ],
}


class FakeNames:
    JSC = PersonName("JEANETTE", "SCHNEIDER-COX")
    MM = PersonName("MARIO", "MCCARTHY")
    RL = PersonName("RYAN", "LUNA")
    TF = PersonName("TONY", "FARMER")
    SD = PersonName("SAMUEL", "DUNN")


# there is no particular order to these, can be mixed and matched as needed
highlighted_officers_fixture_adverse = [
    OfficerMetricEntity(
        FakeNames.JSC,
        0.19904024430145054,
        TargetStatus.FAR,
        0.15804024430145053,
        "abc123",
        "1",
    ),
    OfficerMetricEntity(
        FakeNames.MM,
        0.10228673915480327,
        TargetStatus.FAR,
        0.08228673915480327,
        "abc123",
        "1",
    ),
    OfficerMetricEntity(
        FakeNames.RL, 0.129823, TargetStatus.FAR, 0.121354, "abc123", "1"
    ),
]

highlighted_officers_fixture_favorable = [
    OfficerMetricEntity(
        FakeNames.TF,
        0.01854,
        TargetStatus.FAR,
        0,
        "abc123",
        "1",
    ),
    OfficerMetricEntity(
        FakeNames.SD,
        0,
        TargetStatus.FAR,
        0,
        "abc123",
        "1",
    ),
]

highlighted_officers_fixture_favorable_zero = [
    OfficerMetricEntity(
        FakeNames.JSC,
        0,
        TargetStatus.FAR,
        0.01854,
        "abc123",
        "1",
    ),
    OfficerMetricEntity(
        FakeNames.SD,
        0,
        TargetStatus.FAR,
        0,
        "abc123",
        "1",
    ),
]


def create_fixture(
    metric: OutliersMetricConfig,
    target: float,
    other_officers: Dict[TargetStatus, List[float]],
    highlighted_officers: List[OfficerMetricEntity],
    target_status_strategy: Optional[TargetStatusStrategy] = None,
) -> OutlierMetricInfo:
    optional_args = []
    if target_status_strategy:
        optional_args.append(target_status_strategy)
    return OutlierMetricInfo(
        metric, target, other_officers, highlighted_officers, *optional_args
    )
