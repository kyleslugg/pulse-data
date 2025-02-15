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
"""Script for manage view updates to occur - to be called only within the Airflow DAG's
KubernetesPodOperator."""
import argparse

from recidiviz.big_query.view_update_manager import execute_update_all_managed_views
from recidiviz.entrypoints.entrypoint_interface import EntrypointInterface
from recidiviz.utils.metadata import project_id
from recidiviz.utils.params import str_to_bool, str_to_list


class UpdateAllManagedViewsEntrypoint(EntrypointInterface):
    """Entrypoint for updating managed views"""

    @staticmethod
    def get_parser() -> argparse.ArgumentParser:
        """Parses arguments for the managed views update process."""
        parser = argparse.ArgumentParser()

        parser.add_argument(
            "--sandbox_prefix",
            help="The sandbox prefix for which the refresh needs to write to",
            type=str,
        )

        parser.add_argument(
            "--dataset_ids_to_load",
            dest="dataset_ids_to_load",
            help="A list of dataset_ids to load separated by commas. If provided, only "
            "loads datasets in this list plus ancestors.",
            type=str_to_list,
            required=False,
        )

        parser.add_argument(
            "--clean_managed_datasets",
            help="If true (default), will clean all historically managed datasets before updating.",
            type=str_to_bool,
            default=True,
        )

        return parser

    @staticmethod
    def run_entrypoint(args: argparse.Namespace) -> None:
        execute_update_all_managed_views(
            project_id(),
            sandbox_prefix=args.sandbox_prefix,
            dataset_ids_to_load=args.dataset_ids_to_load,
            clean_managed_datasets=args.clean_managed_datasets,
            # Should allow slow views if not cleaning managed datasets and is updating is slow.
            allow_slow_views=not args.clean_managed_datasets,
        )
