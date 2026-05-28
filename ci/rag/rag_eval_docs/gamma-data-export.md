# Gamma Software Export Reference

Analytics teams often plan downstream ingestion before they ever enable scheduled exports. They usually care about delivery target, schema stability, and whether the export can fit existing warehouse jobs.

Gamma Software supports scheduled exports in CSV, JSONL, and Parquet, and those files can be delivered to S3-compatible storage. Teams with strict compliance review can still stage exports in a controlled bucket before onward transfer.

Export frequency, retention, and field selection are configured separately from the workspace ingestion pipeline. Admins can also pause a schedule without deleting the target destination record.

Bulk backfills follow a support-reviewed process because they can affect rate limits for very large historical pulls.
