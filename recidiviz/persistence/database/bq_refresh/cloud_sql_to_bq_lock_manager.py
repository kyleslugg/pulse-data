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
"""Manages acquiring and releasing the lock for the Cloud SQL -> BQ refresh."""
import logging

from recidiviz.cloud_storage.gcs_pseudo_lock_manager import (
    GCSPseudoLockAlreadyExists,
    GCSPseudoLockDoesNotExist,
    GCSPseudoLockManager,
)
from recidiviz.ingest.direct.controllers.direct_ingest_region_lock_manager import (
    STATE_EXTRACT_AND_MERGE_INGEST_PROCESS_RUNNING_LOCK_PREFIX,
)
from recidiviz.ingest.direct.types.direct_ingest_instance import DirectIngestInstance
from recidiviz.persistence.database.bq_refresh.bq_refresh_utils import (
    postgres_to_bq_lock_name_for_schema,
)
from recidiviz.persistence.database.schema_type import SchemaType
from recidiviz.pipelines.normalized_state_update_lock_manager import (
    normalization_lock_name_for_ingest_instance,
)


class CloudSqlToBQLockManager:
    """Manages acquiring and releasing the lock for the Cloud SQL -> BQ refresh, as well
    as determining if the refresh can proceed given other ongoing processes.
    """

    def __init__(self) -> None:
        self.lock_manager = GCSPseudoLockManager()

    def acquire_lock(
        self,
        lock_id: str,
        schema_type: SchemaType,
        ingest_instance: DirectIngestInstance,
    ) -> None:
        """Acquires the CloudSQL -> BQ refresh lock for a given schema and instance, or refreshes the
         timeout of the lock if a lock with the given |lock_id| already exists. The
         presence of the lock tells other ongoing processes to yield until the lock has
         been released.

         Acquiring the lock does NOT tell us if we can proceed with the refresh. You
         must call can_proceed() to determine if all blocking processes have
         successfully yielded.

        Throws if a lock with a different lock_id exists for this schema.
        """
        lock_name = postgres_to_bq_lock_name_for_schema(schema_type, ingest_instance)
        try:
            self.lock_manager.lock(
                lock_name,
                payload=lock_id,
                expiration_in_seconds=self._export_lock_timeout_for_schema(
                    schema_type, ingest_instance
                ),
            )
        except GCSPseudoLockAlreadyExists as e:
            previous_lock_id = self.lock_manager.get_lock_payload(lock_name)
            logging.info("Lock contents: %s", previous_lock_id)
            if lock_id != previous_lock_id:
                raise GCSPseudoLockAlreadyExists(
                    f"UUID {lock_id} does not match existing lock's UUID {previous_lock_id}"
                ) from e

    def can_proceed(
        self, schema_type: SchemaType, ingest_instance: DirectIngestInstance
    ) -> bool:
        """Returns True if all blocking processes have stopped and we can proceed with
        the export, False otherwise.
        """

        if not self.is_locked(schema_type, ingest_instance):
            raise GCSPseudoLockDoesNotExist(
                f"Must acquire the lock for [{schema_type}] before checking if can proceed"
            )

        if schema_type not in (
            SchemaType.STATE,
            SchemaType.OPERATIONS,
        ):
            return True

        if schema_type == SchemaType.STATE:
            # The "update normalized state dataset" process reads from the state dataset
            # so it cannot be in progress while the BQ refresh is running.
            if self.lock_manager.is_locked(
                normalization_lock_name_for_ingest_instance(ingest_instance)
            ):
                logging.info(
                    "Normalized state update lock [%s] is already locked, cannot "
                    "proceed with lock for [%s] and [%s]",
                    normalization_lock_name_for_ingest_instance(ingest_instance),
                    schema_type,
                    ingest_instance,
                )
                return False

            blocking_ingest_lock_prefix = (
                STATE_EXTRACT_AND_MERGE_INGEST_PROCESS_RUNNING_LOCK_PREFIX
            )
            if not self.lock_manager.no_active_locks_with_prefix(
                blocking_ingest_lock_prefix, ingest_instance.value
            ):
                logging.info(
                    "Found active ingest locks with prefix [%s], cannot proceed with "
                    "lock for [%s] and [%s]",
                    blocking_ingest_lock_prefix,
                    schema_type,
                    ingest_instance,
                )
                return False
            return True

        if schema_type == SchemaType.OPERATIONS:
            # The operations export yields for any ingest extract and merge process since
            # those read from / write to the Postgres OPERATIONS DB.
            # TODO(#20930): We will not need to block on ingest extract and merge once
            #  all states have been migrated to ingest in Dataflow.
            blocking_ingest_lock_prefix = (
                STATE_EXTRACT_AND_MERGE_INGEST_PROCESS_RUNNING_LOCK_PREFIX
            )
            if not self.lock_manager.no_active_locks_with_prefix(
                blocking_ingest_lock_prefix, ingest_instance.value
            ):
                logging.info(
                    "Found active ingest locks with prefix [%s], cannot proceed with "
                    "lock for [%s] and [%s]",
                    blocking_ingest_lock_prefix,
                    schema_type,
                    ingest_instance,
                )
                return False
            return True

        raise ValueError(f"Unexpected schema type [{schema_type}]")

    def release_lock(
        self, schema_type: SchemaType, ingest_instance: DirectIngestInstance
    ) -> None:
        """Releases the CloudSQL -> BQ refresh lock for a given schema and ingest instance."""
        self.lock_manager.unlock(
            postgres_to_bq_lock_name_for_schema(schema_type, ingest_instance)
        )

    def is_locked(
        self, schema_type: SchemaType, ingest_instance: DirectIngestInstance
    ) -> bool:
        return self.lock_manager.is_locked(
            postgres_to_bq_lock_name_for_schema(schema_type, ingest_instance)
        )

    @staticmethod
    def _export_lock_timeout_for_schema(
        _schema_type: SchemaType, _ingest_instance: DirectIngestInstance
    ) -> int:
        """Defines the exported lock timeouts permitted based on the schema and ingest instance arg.
        For the moment all lock timeouts are set to one hour in length.

        Export jobs may take longer than the alotted time, but if they do so, they
        will de facto relinquish their hold on the acquired lock. The export lock is
        going to be longer than ingest locks because ingest crashes should not stop
        BQ refreshes from continuing."""
        return 3900
