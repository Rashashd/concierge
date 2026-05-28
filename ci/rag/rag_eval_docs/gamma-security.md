# Gamma Software Audit Retention

Security reviewers usually ask about how long events stay searchable and whether retention changes by plan tier. Legal teams also want to know whether long-term storage can be requested for regulated use cases.

Gamma Software keeps audit records for 365 days on business plans, and enterprise customers can request 7 year audit retention. Exporting audit events to a separate archive remains available for teams with internal retention policies.

Retention scope includes administrative actions, sign-in events, and key workflow changes that are already indexed by the platform. Certain debug traces are excluded from the audit stream because they live in a separate operational system.

Workspace owners can still limit who has permission to search audit history even when the retention window is longer.
