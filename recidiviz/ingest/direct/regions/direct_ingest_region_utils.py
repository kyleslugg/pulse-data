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
"""Shared util functions dealing with direct ingest of regions."""
import os
from typing import List, Set

from recidiviz.common.constants.states import StateCode
from recidiviz.common.file_system import is_non_empty_code_directory
from recidiviz.ingest.direct import direct_ingest_regions, regions

_REGIONS_DIR = os.path.dirname(regions.__file__)


def get_existing_region_dir_paths() -> List[str]:
    """Returns list of paths to all region directories in ingest/direct/regions."""
    return [os.path.join(_REGIONS_DIR, d) for d in get_existing_region_codes()]


def get_existing_region_codes() -> Set[str]:
    """Returns list of region directories existing in ingest/direct/regions."""
    return {
        d
        for d in os.listdir(_REGIONS_DIR)
        if is_non_empty_code_directory(os.path.join(_REGIONS_DIR, d))
        and not d.startswith("__")
    }


def get_existing_direct_ingest_states() -> List[StateCode]:
    return [
        StateCode(region_code.upper())
        for region_code in get_existing_region_codes()
        if StateCode.is_state_code(region_code)
    ]


def get_direct_ingest_states_existing_in_env() -> List[StateCode]:
    """Returns list of states that have existing direct ingest infrastructure in the environment"""
    return [
        state_code
        for state_code in get_existing_direct_ingest_states()
        if direct_ingest_regions.get_direct_ingest_region(
            state_code.value.lower()
        ).exists_in_env()
    ]


def get_direct_ingest_states_launched_in_env() -> List[StateCode]:
    """Returns list of states that have direct ingest launched in the environment"""
    return [
        state_code
        for state_code in get_existing_direct_ingest_states()
        if direct_ingest_regions.get_direct_ingest_region(
            state_code.value.lower()
        ).is_ingest_launched_in_env()
    ]
