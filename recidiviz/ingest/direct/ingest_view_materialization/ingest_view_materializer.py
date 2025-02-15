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
"""Class that manages logic related to materializing ingest views for a region so
the results can be processed and merged into our Postgres database.
"""
import abc
import datetime
import logging
import uuid
from typing import Dict, List, Optional

from google.cloud import bigquery

from recidiviz.big_query.big_query_client import BigQueryClient
from recidiviz.big_query.big_query_utils import datetime_clause
from recidiviz.big_query.view_update_manager import (
    TEMP_DATASET_DEFAULT_TABLE_EXPIRATION_MS,
)
from recidiviz.ingest.direct import direct_ingest_regions
from recidiviz.ingest.direct.direct_ingest_regions import DirectIngestRegion
from recidiviz.ingest.direct.ingest_view_materialization.instance_ingest_view_contents import (
    LOWER_BOUND_DATETIME_COL_NAME,
    MATERIALIZATION_TIME_COL_NAME,
    UPPER_BOUND_DATETIME_COL_NAME,
    InstanceIngestViewContents,
)
from recidiviz.ingest.direct.metadata.direct_ingest_view_materialization_metadata_manager import (
    DirectIngestViewMaterializationMetadataManager,
)
from recidiviz.ingest.direct.types.cloud_task_args import IngestViewMaterializationArgs
from recidiviz.ingest.direct.types.direct_ingest_instance import DirectIngestInstance
from recidiviz.ingest.direct.views.direct_ingest_view_query_builder import (
    DestinationTableType,
    DirectIngestViewQueryBuilder,
)
from recidiviz.ingest.direct.views.direct_ingest_view_query_builder_collector import (
    DirectIngestViewQueryBuilderCollector,
)
from recidiviz.utils.environment import GCP_PROJECT_STAGING
from recidiviz.utils.metadata import local_project_id_override
from recidiviz.utils.string import StrictStringFormatter

SELECT_SUBQUERY = "SELECT * FROM `{project_id}.{dataset_id}.{table_name}`;"
TABLE_NAME_DATE_FORMAT = "%Y_%m_%d_%H_%M_%S"

DATAFLOW_INGEST_VIEW_DATE_DIFF_QUERY_TEMPLATE = f"""
WITH {{temp_upper_bound_table}} AS (
    {{upper_bound_query}}
),{{lower_bound_query}}
date_diff AS (
    SELECT * FROM {{temp_upper_bound_table}}{{lower_bound_table_results}}
)
SELECT *,
    CURRENT_DATETIME('UTC') AS {MATERIALIZATION_TIME_COL_NAME},
    {{upper_bound_datetime_inclusive}} AS {UPPER_BOUND_DATETIME_COL_NAME},
    {{lower_bound_datetime_exclusive}} AS {LOWER_BOUND_DATETIME_COL_NAME}
FROM date_diff;
"""


class IngestViewMaterializer:
    @abc.abstractmethod
    def materialize_view_for_args(
        self, ingest_view_materialization_args: IngestViewMaterializationArgs
    ) -> bool:
        """Materializes the results of a single ingest view with date bounds specified
        in the provided args. If the provided args contain an upper and lower bound
        date, the materialized view results will contain only the delta between the two
        dates. If only the upper bound is provided, then the materialized view results
        will contain historical results up until the bound date.
        """


class IngestViewMaterializerImpl(IngestViewMaterializer):
    """Class that manages logic related to materializing ingest views for a region so
    the results can be processed and merged into our Postgres database.
    """

    def __init__(
        self,
        *,
        region: DirectIngestRegion,
        raw_data_source_instance: DirectIngestInstance,
        ingest_instance: DirectIngestInstance,
        metadata_manager: DirectIngestViewMaterializationMetadataManager,
        ingest_view_contents: InstanceIngestViewContents,
        big_query_client: BigQueryClient,
        view_collector: DirectIngestViewQueryBuilderCollector,
        launched_ingest_views: List[str],
    ):
        self.region = region
        self.metadata_manager = metadata_manager
        self.ingest_view_contents = ingest_view_contents
        self.ingest_instance = ingest_instance
        self.raw_data_source_instance = raw_data_source_instance
        self.big_query_client = big_query_client
        self.ingest_views_by_name = {
            view.ingest_view_name: view
            for view in view_collector.collect_query_builders()
            if view.ingest_view_name in launched_ingest_views
        }
        self.request_id = self._generate_request_id()

    @classmethod
    def _generate_request_id(cls) -> str:
        """Generates a short, random alphanumeric string that can be appended to the
        names of temp tables generated by this class to prevent collisions with other
        tables created in parallel."""
        return str(uuid.uuid4())[:8]

    def _generate_ingest_view_query_job_for_date(
        self,
        table_name: str,
        ingest_view: DirectIngestViewQueryBuilder,
        date_bound: datetime.datetime,
    ) -> bigquery.QueryJob:
        """Generates a query for the provided |ingest view| on the given |date bound|
        and starts a job to load the results of that query into the provided
        |table_name|. Returns the potentially in progress QueryJob to the caller.
        """
        query = self._generate_ingest_view_query_for_date(
            ingest_view=ingest_view,
            raw_data_source_instance=self.raw_data_source_instance,
            destination_table_type=DestinationTableType.PERMANENT_EXPIRING,
            destination_dataset_id=self.ingest_view_contents.temp_results_dataset,
            destination_table_id=table_name,
            update_timestamp=date_bound,
        )

        logging.info("Generated bound query: [%s]", query)

        self.big_query_client.create_dataset_if_necessary(
            dataset_ref=self.big_query_client.dataset_ref_for_id(
                self.ingest_view_contents.temp_results_dataset
            ),
            default_table_expiration_ms=TEMP_DATASET_DEFAULT_TABLE_EXPIRATION_MS,
        )
        query_job = self.big_query_client.run_query_async(
            query_str=query, use_query_cache=False, query_parameters=[]
        )
        return query_job

    @staticmethod
    def _create_date_diff_query(
        upper_bound_query: str, upper_bound_prev_query: str
    ) -> str:
        """Provided the given |upper_bound_query| and |upper_bound_prev_query| returns a query which will return the
        delta between those two queries.
        """
        main_query, filter_query = (upper_bound_query, upper_bound_prev_query)
        filter_query = filter_query.rstrip().rstrip(";")
        main_query = main_query.rstrip().rstrip(";")
        query = f"(\n{main_query}\n) EXCEPT DISTINCT (\n{filter_query}\n);"
        return query

    @staticmethod
    def _get_upper_bound_intermediate_table_name(
        ingest_view_materialization_args: IngestViewMaterializationArgs, request_id: str
    ) -> str:
        """Returns name of the intermediate table that will store data for the view query with a date bound equal to the
        upper_bound_datetime_inclusive in the args.
        """
        return (
            f"{ingest_view_materialization_args.ingest_view_name}_"
            f"{ingest_view_materialization_args.upper_bound_datetime_inclusive.strftime(TABLE_NAME_DATE_FORMAT)}_"
            f"upper_bound_{request_id}"
        )

    @staticmethod
    def _get_lower_bound_intermediate_table_name(
        ingest_view_materialization_args: IngestViewMaterializationArgs, request_id: str
    ) -> str:
        """Returns name of the intermediate table that will store data for the view query with a date bound equal to the
        lower_bound_datetime_exclusive in the args.

        Throws if the args have a null lower_bound_datetime_exclusive.
        """
        if not ingest_view_materialization_args.lower_bound_datetime_exclusive:
            raise ValueError(
                f"Expected nonnull lower_bound_datetime_exclusive for args: {ingest_view_materialization_args}"
            )
        return (
            f"{ingest_view_materialization_args.ingest_view_name}_"
            f"{ingest_view_materialization_args.lower_bound_datetime_exclusive.strftime(TABLE_NAME_DATE_FORMAT)}_"
            f"lower_bound_{request_id}"
        )

    def _get_materialization_query_for_args(
        self, ingest_view_materialization_args: IngestViewMaterializationArgs
    ) -> str:
        """Returns a query that will produce the ingest view results for date bounds
        specified in the provided args. This query will only work if the intermediate
        tables have been loaded via the
        _load_individual_date_queries_into_intermediate_tables function.
        """
        ingest_view = self.ingest_views_by_name[
            ingest_view_materialization_args.ingest_view_name
        ]
        materialization_query = StrictStringFormatter().format(
            SELECT_SUBQUERY,
            project_id=self.big_query_client.project_id,
            dataset_id=self.ingest_view_contents.temp_results_dataset,
            table_name=self._get_upper_bound_intermediate_table_name(
                ingest_view_materialization_args, request_id=self.request_id
            ),
        )

        if ingest_view_materialization_args.lower_bound_datetime_exclusive:
            upper_bound_prev_query = StrictStringFormatter().format(
                SELECT_SUBQUERY,
                project_id=self.big_query_client.project_id,
                dataset_id=self.ingest_view_contents.temp_results_dataset,
                table_name=self._get_lower_bound_intermediate_table_name(
                    ingest_view_materialization_args, request_id=self.request_id
                ),
            )
            materialization_query = self._create_date_diff_query(
                upper_bound_query=materialization_query,
                upper_bound_prev_query=upper_bound_prev_query,
            )

        return DirectIngestViewQueryBuilder.add_order_by_suffix(
            query=materialization_query, order_by_cols=ingest_view.order_by_cols
        )

    def _load_individual_date_queries_into_intermediate_tables(
        self, ingest_view_materialization_args: IngestViewMaterializationArgs
    ) -> None:
        """Loads query results from the upper and lower bound queries for this
        materialization job into intermediate tables.
        """

        ingest_view = self.ingest_views_by_name[
            ingest_view_materialization_args.ingest_view_name
        ]

        single_date_table_materialization_jobs = []

        upper_bound_table_job = self._generate_ingest_view_query_job_for_date(
            table_name=self._get_upper_bound_intermediate_table_name(
                ingest_view_materialization_args, request_id=self.request_id
            ),
            ingest_view=ingest_view,
            date_bound=ingest_view_materialization_args.upper_bound_datetime_inclusive,
        )
        single_date_table_materialization_jobs.append(upper_bound_table_job)

        if ingest_view_materialization_args.lower_bound_datetime_exclusive:
            lower_bound_table_job = self._generate_ingest_view_query_job_for_date(
                table_name=self._get_lower_bound_intermediate_table_name(
                    ingest_view_materialization_args, request_id=self.request_id
                ),
                ingest_view=ingest_view,
                date_bound=ingest_view_materialization_args.lower_bound_datetime_exclusive_for_query(),
            )
            single_date_table_materialization_jobs.append(lower_bound_table_job)

        # Wait for completion of all async date queries
        for job in single_date_table_materialization_jobs:
            job.result()

    def _delete_intermediate_tables(
        self, ingest_view_materialization_args: IngestViewMaterializationArgs
    ) -> None:
        single_date_table_ids = [
            self._get_upper_bound_intermediate_table_name(
                ingest_view_materialization_args, request_id=self.request_id
            )
        ]
        if ingest_view_materialization_args.lower_bound_datetime_exclusive:
            single_date_table_ids.append(
                self._get_lower_bound_intermediate_table_name(
                    ingest_view_materialization_args, request_id=self.request_id
                )
            )

        for table_id in single_date_table_ids:
            self.big_query_client.delete_table(
                dataset_id=self.ingest_view_contents.temp_results_dataset,
                table_id=table_id,
            )
            logging.info("Deleted intermediate table [%s]", table_id)

    def materialize_view_for_args(
        self, ingest_view_materialization_args: IngestViewMaterializationArgs
    ) -> bool:
        """Materializes the results of a single ingest view with date bounds specified
        in the provided args. If the provided args contain an upper and lower bound
        date, the materialized view results will contain only the delta between the two
        dates. If only the upper bound is provided, then the materialized view results
        will contain historical results up until the bound date.

        Note: In order to prevent resource exhaustion in BigQuery, the ultimate query in
        this method is broken down into distinct parts. This method first persists the
        results of historical queries for each given bound date (upper and lower) into
        temporary tables. The delta between those tables is then queried separately using
        SQL's `EXCEPT DISTINCT` and those final results are saved to the appropriate
        location in BigQuery.
        """
        if not self.region.is_ingest_launched_in_env():
            raise ValueError(
                f"Ingest not enabled for region [{self.region.region_code}]"
            )

        job_completion_time = self.metadata_manager.get_job_completion_time_for_args(
            ingest_view_materialization_args
        )
        if job_completion_time:
            logging.warning(
                "Already materialized view for args [%s] - returning.",
                ingest_view_materialization_args,
            )
            return False

        ingest_view = self.ingest_views_by_name[
            ingest_view_materialization_args.ingest_view_name
        ]

        logging.info(
            "Start loading results of individual date queries into intermediate tables."
        )
        self._load_individual_date_queries_into_intermediate_tables(
            ingest_view_materialization_args
        )
        logging.info(
            "Completed loading results of individual date queries into intermediate tables."
        )

        materialization_query = self._get_materialization_query_for_args(
            ingest_view_materialization_args
        )

        logging.info(
            "Generated final materialization query [%s]", str(materialization_query)
        )

        self._materialize_query_results(
            ingest_view_materialization_args, ingest_view, materialization_query
        )

        logging.info("Deleting intermediate tables.")
        self._delete_intermediate_tables(ingest_view_materialization_args)
        logging.info("Done deleting intermediate tables.")

        self.metadata_manager.mark_ingest_view_materialized(
            ingest_view_materialization_args
        )

        return True

    @classmethod
    def debug_query_for_args(
        cls,
        ingest_views_by_name: Dict[str, DirectIngestViewQueryBuilder],
        raw_data_source_instance: DirectIngestInstance,
        ingest_view_materialization_args: IngestViewMaterializationArgs,
    ) -> str:
        """Returns a version of the materialization query for the provided args that can
        be run in the BigQuery UI.

        Generates a single query that is date bounded such that it represents the data
        that has changed for this view between the specified date bounds in the provided
         materialization args.

        If there is no lower bound, this produces a query for a historical query up to
        the upper bound date. Otherwise, it diffs two historical queries to produce a
        delta query, using the SQL 'EXCEPT DISTINCT' function.

        Important Note: This query is meant for debug/test use only. In the production
        ingest flow, query results for individual dates are persisted into temporary
        tables, and those temporary tables are then diff'd using SQL's `EXCEPT DISTINCT`
        function.
        """
        ingest_view = ingest_views_by_name[
            ingest_view_materialization_args.ingest_view_name
        ]

        request_id = cls._generate_request_id()
        upper_bound_table_id = cls._get_upper_bound_intermediate_table_name(
            ingest_view_materialization_args, request_id=request_id
        )
        query = cls._generate_ingest_view_query_for_date(
            ingest_view=ingest_view,
            raw_data_source_instance=raw_data_source_instance,
            destination_table_type=DestinationTableType.TEMPORARY,
            destination_dataset_id=None,
            destination_table_id=upper_bound_table_id,
            update_timestamp=ingest_view_materialization_args.upper_bound_datetime_inclusive,
            raw_table_subquery_name_prefix="upper_"
            if ingest_view.materialize_raw_data_table_views
            else "",
        )

        lower_bound_table_id = None
        if ingest_view_materialization_args.lower_bound_datetime_exclusive:
            lower_bound_table_id = cls._get_lower_bound_intermediate_table_name(
                ingest_view_materialization_args, request_id=request_id
            )
            lower_bound_query = cls._generate_ingest_view_query_for_date(
                ingest_view=ingest_view,
                raw_data_source_instance=raw_data_source_instance,
                destination_table_type=DestinationTableType.TEMPORARY,
                destination_dataset_id=None,
                destination_table_id=lower_bound_table_id,
                update_timestamp=ingest_view_materialization_args.lower_bound_datetime_exclusive_for_query(),
                raw_table_subquery_name_prefix="lower_"
                if ingest_view.materialize_raw_data_table_views
                else "",
            )
            query = f"{query}\n{lower_bound_query}"

        upper_bound_select = f"SELECT * FROM {upper_bound_table_id}"
        if lower_bound_table_id:
            diff_query = cls._create_date_diff_query(
                upper_bound_query=upper_bound_select,
                upper_bound_prev_query=f"SELECT * FROM {lower_bound_table_id}",
            )

            query = f"{query}\n{diff_query}"
        else:
            query = f"{query}\n{upper_bound_select}"

        query = DirectIngestViewQueryBuilder.add_order_by_suffix(
            query=query, order_by_cols=ingest_view.order_by_cols
        )

        return query

    @classmethod
    def dataflow_query_for_args(
        cls,
        view_builder: DirectIngestViewQueryBuilder,
        raw_data_source_instance: DirectIngestInstance,
        ingest_view_materialization_args: IngestViewMaterializationArgs,
    ) -> str:
        """Returns a version of the materialization query for the provided args that can
        be run in Dataflow.

        Generates a single query that is date bounded such that it represents the data
        that has changed for this view between the specified date bounds in the provided
        materialization args.

        If there is no lower bound, this produces a query for a historical query up to
        the upper bound date. Otherwise, it diffs two historical queries to produce a
        delta query, using the SQL 'EXCEPT DISTINCT' function.

        A note that this query for Dataflow cannot use materialized tables or temporary
        tables."""
        request_id = cls._generate_request_id()
        upper_bound_datetime_inclusive = (
            ingest_view_materialization_args.upper_bound_datetime_inclusive
        )
        temporary_upper_bound_table = cls._get_upper_bound_intermediate_table_name(
            ingest_view_materialization_args, request_id=request_id
        )
        upper_bound_ingest_query = cls._generate_ingest_view_query_for_date(
            ingest_view=view_builder,
            raw_data_source_instance=raw_data_source_instance,
            destination_table_type=DestinationTableType.NONE,
            destination_dataset_id=None,
            destination_table_id=None,
            raw_table_subquery_name_prefix=None,
            update_timestamp=upper_bound_datetime_inclusive,
            use_order_by=False,
            using_dataflow=True,
        ).rstrip(";")
        upper_bound_datetime_inclusive_clause = datetime_clause(
            upper_bound_datetime_inclusive, include_milliseconds=True
        )

        lower_bound_datetime_exclusive = (
            ingest_view_materialization_args.lower_bound_datetime_exclusive
        )
        temporary_lower_bound_table = (
            cls._get_lower_bound_intermediate_table_name(
                ingest_view_materialization_args, request_id=request_id
            )
            if lower_bound_datetime_exclusive
            else None
        )
        lower_bound_ingest_query = (
            cls._generate_ingest_view_query_for_date(
                ingest_view=view_builder,
                raw_data_source_instance=raw_data_source_instance,
                destination_table_type=DestinationTableType.NONE,
                destination_dataset_id=None,
                destination_table_id=None,
                raw_table_subquery_name_prefix=None,
                update_timestamp=lower_bound_datetime_exclusive,
                use_order_by=False,
                using_dataflow=True,
            ).rstrip(";")
            if lower_bound_datetime_exclusive
            else None
        )
        lower_bound_query = (
            f"\n{temporary_lower_bound_table} AS (\n{lower_bound_ingest_query}\n),"
            if lower_bound_datetime_exclusive
            else ""
        )
        lower_bound_table_results = (
            f"\nEXCEPT DISTINCT SELECT * FROM {temporary_lower_bound_table}"
            if temporary_lower_bound_table
            else ""
        )
        lower_bound_datetime_exclusive_clause = (
            datetime_clause(lower_bound_datetime_exclusive, include_milliseconds=True)
            if lower_bound_datetime_exclusive
            else "CAST(NULL AS DATETIME)"
        )

        return StrictStringFormatter().format(
            DATAFLOW_INGEST_VIEW_DATE_DIFF_QUERY_TEMPLATE,
            upper_bound_query=upper_bound_ingest_query,
            lower_bound_query=lower_bound_query,
            temp_upper_bound_table=temporary_upper_bound_table,
            lower_bound_table_results=lower_bound_table_results,
            upper_bound_datetime_inclusive=upper_bound_datetime_inclusive_clause,
            lower_bound_datetime_exclusive=lower_bound_datetime_exclusive_clause,
        )

    @staticmethod
    def _generate_ingest_view_query_for_date(
        *,
        ingest_view: DirectIngestViewQueryBuilder,
        raw_data_source_instance: DirectIngestInstance,
        update_timestamp: datetime.datetime,
        destination_table_type: DestinationTableType,
        destination_dataset_id: Optional[str],
        destination_table_id: Optional[str],
        raw_table_subquery_name_prefix: Optional[str] = None,
        use_order_by: bool = True,
        using_dataflow: bool = False,
    ) -> str:
        """Generates a single query for the provided |ingest view| that is date bounded by |update_timestamp|."""
        query = ingest_view.build_query(
            config=DirectIngestViewQueryBuilder.QueryStructureConfig(
                raw_data_source_instance=raw_data_source_instance,
                destination_table_type=destination_table_type,
                destination_dataset_id=destination_dataset_id,
                destination_table_id=destination_table_id,
                raw_table_subquery_name_prefix=raw_table_subquery_name_prefix,
                raw_data_datetime_upper_bound=update_timestamp,
                use_order_by=use_order_by,
            ),
            using_dataflow=using_dataflow,
        )
        return query

    def _materialize_query_results(
        self,
        args: IngestViewMaterializationArgs,
        ingest_view: DirectIngestViewQueryBuilder,
        query: str,
    ) -> None:
        """Materialized the results of |query| to the appropriate location."""
        self.ingest_view_contents.save_query_results(
            ingest_view_name=args.ingest_view_name,
            upper_bound_datetime_inclusive=args.upper_bound_datetime_inclusive,
            lower_bound_datetime_exclusive=args.lower_bound_datetime_exclusive,
            query_str=query,
            order_by_cols_str=ingest_view.order_by_cols,
        )


if __name__ == "__main__":
    # Update these variables and run to print a materialization query you can run in the BigQuery UI
    region_code_: str = "us_tn"
    ingest_view_name_: str = "DisciplinaryIncarcerationIncident"
    lower_bound_datetime_exclusive_: datetime.datetime = datetime.datetime(
        2022, 3, 23, 6, 2, 54, 633642
    )
    upper_bound_datetime_inclusive_: datetime.datetime = datetime.datetime(
        2023, 5, 2, 8, 3, 43, 383642
    )
    raw_data_instance: DirectIngestInstance = DirectIngestInstance.PRIMARY

    with local_project_id_override(GCP_PROJECT_STAGING):
        region_ = direct_ingest_regions.get_direct_ingest_region(region_code_)
        view_collector_ = DirectIngestViewQueryBuilderCollector(region_, [])
        views_by_name_ = {
            view.ingest_view_name: view
            for view in view_collector_.collect_query_builders()
        }

        debug_query = IngestViewMaterializerImpl.debug_query_for_args(
            ingest_views_by_name=views_by_name_,
            raw_data_source_instance=raw_data_instance,
            ingest_view_materialization_args=IngestViewMaterializationArgs(
                ingest_view_name=ingest_view_name_,
                ingest_instance=DirectIngestInstance.PRIMARY,
                lower_bound_datetime_exclusive=lower_bound_datetime_exclusive_,
                upper_bound_datetime_inclusive=upper_bound_datetime_inclusive_,
            ),
        )
        print(debug_query)
