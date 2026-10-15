# Two-tier drift response: WARN and Circuit Breaker

Drift detection classifies breaches into two severities. WARN records the observation and fires the webhook but lets data flow. Circuit Breaker (a >500 bp policy-rate jump, an unexpected NULL wipeout, >30% of historical rows vanishing) quarantines the Publication and halts Gold promotion for that Source.

The rejected single-tier alternatives both fail: alert-and-continue waves a corrupted upstream file straight into production, and halt-on-any-breach pages a human for every routine 20 bp move.

## Consequences

- Tier thresholds are per-indicator config (`relative | absolute_bp | absolute_val`); rate indicators default to absolute_bp because 5% relative on a 4% rate is noise.
- A quarantined Publication still lands in Bronze; only Silver-to-Gold promotion halts.
