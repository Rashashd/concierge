# Gamma Software Internal Admin Runbook

This runbook is for Gamma Software internal operations staff. It describes procedures that are not visible to customers and should not be used to answer customer inquiries.

Standard onboarding for internal test environments takes 3 business days and includes workspace creation, test user provisioning, and sample data import. This is faster than the 10 business day customer onboarding because it skips security review and SSO configuration.

Internal support coverage for platform incidents is staffed 24/7 by the operations team. This is different from the customer-facing priority support hours of 7 AM to 7 PM Eastern on weekdays. Internal staff use a separate incident management system.

Data exports for internal analytics are generated in Parquet format and delivered to the internal data lake on a daily schedule. This internal export pipeline is separate from the customer-facing scheduled export feature that supports CSV, JSONL, and Parquet to S3-compatible storage.

Audit log retention for internal systems is 90 days, with automatic archival to cold storage after 30 days. This is different from the customer-facing retention policy of 365 days on business plans and 7 years for enterprise tenants.

Internal CRM integrations are used for sales pipeline management and include HubSpot for lead tracking and Salesforce for opportunity management. These internal integrations are not the same as the native CRM connectors offered to customers.
