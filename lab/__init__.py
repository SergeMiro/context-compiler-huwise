"""AutoContext Lab (proposed layer): autoresearch-style loop over context artifacts, preprod only.
collect -> diagnose -> hypothesize (one edit) -> fork (preprod DB/index) -> patch -> static check -> eval ->
quality gate -> keep | revert -> append-only log. Promotion to production is a separate, human-approved step."""
