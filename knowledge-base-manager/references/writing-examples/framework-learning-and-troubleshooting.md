# Worked Example: EventRunner Task Stream Consumer Implementation and Troubleshooting

> Note: This document is a fictional instructional worked example designed to illustrate the integration of practical skill acquisition (R4), conceptual mechanism explanation, and problem diagnosis experience (R6) within a single reading task. Names, APIs, and telemetry logs do not represent real production frameworks. The accompanying code provides an in-memory instructional simulation demonstrating protocol state transitions rather than a production-grade distributed broker.

## Background Context and Common Input

**Reader Profile & Goals**: A backend engineer needs to build a reliable message consumer using Python for a lightweight asynchronous task stream framework named `EventRunner` (fictional). The reader has not previously worked with lease-based message acknowledgments. After reading this guide, the reader must be able to:
1. Implement and run a minimal consumer equipped with local backpressure and error isolation;
2. Understand the underlying mechanics of lease-based sliding window acknowledgments;
3. Independently diagnose and resolve two common failure patterns: "worker deadlock / hang" and "retry storm / duplicate execution loop".

**Authorized Input Material**:
- Framework Baseline: `EventRunner v0.4.1` (pure asynchronous Python driver).
- Core Protocol Contract: Every pulled event payload carries a lease duration (default 1.0 second in local test environments; 30 seconds in production clusters) represented by a `lease_token`. Before the lease deadline, the consumer must either call `ack(lease_token)` upon successful processing, or `nack(lease_token, retry=True)` to schedule backoff. If the lease deadline passes without an acknowledgment, the broker considers the worker stalled or crashed and allows the event to be reclaimed or re-delivered.
- Lease Renewal: Long-running tasks may call `renew_lease(lease_token, extension=...)` before expiration to extend the active deadline.
- Configuration Limits: `max_in_flight` limits the maximum unacknowledged messages processed concurrently on a single worker node (default 5). When in-flight tasks reach this ceiling, `fetch()` must wait until active tasks complete.

---

## Worked Example Body

### 1. Objective and Observable Runtime Behavior

When the consumer is properly connected and operating normally, the terminal output displays a steady interleaving of message fetches, processing completion, and acknowledgments (ACKs), with local in-flight concurrency remaining bounded within the configured window:

```text
[INFO] Worker started. max_in_flight=2, total_events=5
[INFO] Processing evt-1001...
[INFO] Processing evt-1002...
[INFO] Event evt-1001 -> ACK ok
[INFO] Processing evt-1003...
[INFO] Event evt-1002 -> ACK ok
[INFO] Processing evt-1004...
[INFO] Event evt-1003 -> ACK ok
[INFO] Processing evt-1005...
[INFO] Event evt-1004 -> ACK ok
[INFO] Event evt-1005 -> ACK ok
[INFO] Worker gracefully stopped. All permits cleanly reclaimed.
```

If the console produces no new logs while the Python process remains alive, or if logs report `LeaseExpiredError` followed by repeated re-processing of the same event ID, the consumer has encountered in-flight slot starvation or premature lease expiration.

### 2. Minimal Runnable Consumer Implementation

In Python 3.10+, standard `asyncio` is sufficient to drive this consumer logic. Below is a minimal complete implementation featuring an instructional mock client that actively enforces lease deadlines, backpressure, and structured error isolation across four demonstrated execution scenarios:

```python
import asyncio
import logging
import sys
import time

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("worker")

class LeaseExpiredError(Exception):
    """Raised when an ACK is attempted on an expired or reclaimed lease."""
    pass

class MockEventClient:
    """Fictional instructional EventRunner client with active lease tracking.

    Boundary Notice:
    This is an in-memory pedagogical mock demonstrating protocol state transitions.
    It does not implement wire network transport, broker persistence, or automatic
    broker-side redelivery queues.
    """
    def __init__(self, lease_duration: float = 1.0):
        self._seq = 1000
        self._lease_duration = lease_duration
        self._active_leases: dict[str, float] = {}

    async def fetch(self, batch_size: int = 1) -> list[dict]:
        await asyncio.sleep(0.01)
        self._seq += 1
        evt_id = f"evt-{self._seq}"
        token = f"tok-{self._seq}"
        self._active_leases[token] = time.monotonic() + self._lease_duration
        return [{"id": evt_id, "token": token, "payload": "sample_data"}]

    async def ack(self, token: str) -> bool:
        await asyncio.sleep(0.01)
        expire_at = self._active_leases.get(token)
        if expire_at is None or time.monotonic() > expire_at:
            self._active_leases.pop(token, None)
            raise LeaseExpiredError(f"Lease for token {token} expired before ACK was received.")
        del self._active_leases[token]
        return True

    async def nack(self, token: str, retry: bool = True) -> bool:
        await asyncio.sleep(0.01)
        self._active_leases.pop(token, None)
        return True

    async def renew_lease(self, token: str, extension: float = 0.2) -> bool:
        await asyncio.sleep(0.01)
        if token in self._active_leases and time.monotonic() <= self._active_leases[token]:
            self._active_leases[token] += extension
            return True
        return False

async def process_single_event(
    client: MockEventClient,
    event: dict,
    semaphore: asyncio.Semaphore,
    simulated_delay: float = 0.05,
    heartbeat_renewal: bool = False,
    fail_with_business_error: bool = False,
):
    """Processes an individual event, guaranteeing slot release across all execution paths."""
    evt_id = event["id"]
    token = event["token"]
    renewal_task = None
    try:
        logger.info(f"Processing {evt_id}...")
        if heartbeat_renewal:
            async def heartbeat():
                while True:
                    await asyncio.sleep(0.06)
                    renewed = await client.renew_lease(token, extension=0.15)
                    if not renewed:
                        break
            renewal_task = asyncio.create_task(heartbeat())

        # Simulate business computation
        await asyncio.sleep(simulated_delay)

        if fail_with_business_error:
            raise ValueError(f"Simulated data corruption in {evt_id}")

        await client.ack(token)
        logger.info(f"Event {evt_id} -> ACK ok")
    except LeaseExpiredError as err:
        logger.warning(f"Event {evt_id} lease expired: {err}")
    except Exception as err:
        logger.error(f"Event {evt_id} failed: {err}, sending nack")
        try:
            await client.nack(token, retry=True)
        except Exception as nack_err:
            logger.critical(f"Failed to nack {token}: {nack_err}")
    finally:
        if renewal_task and not renewal_task.done():
            renewal_task.cancel()
        # Crucial: Always release the backpressure slot across all exit paths
        semaphore.release()

async def run_consumer(
    client: MockEventClient,
    max_in_flight: int = 2,
    total_events: int = 5,
    simulated_delay: float = 0.05,
    heartbeat_renewal: bool = False,
    fail_with_business_error: bool = False,
):
    semaphore = asyncio.Semaphore(max_in_flight)
    logger.info(f"Worker started. max_in_flight={max_in_flight}, total_events={total_events}")

    tasks = []
    for _ in range(total_events):
        await semaphore.acquire()  # Acquire concurrency slot before fetching
        events = await client.fetch(batch_size=1)
        if not events:
            semaphore.release()
            await asyncio.sleep(0.02)
            continue

        for event in events:
            tasks.append(
                asyncio.create_task(
                    process_single_event(
                        client,
                        event,
                        semaphore,
                        simulated_delay=simulated_delay,
                        heartbeat_renewal=heartbeat_renewal,
                        fail_with_business_error=fail_with_business_error,
                    )
                )
            )

    if tasks:
        await asyncio.gather(*tasks)

    # Rigorous verification: all permits returned and no leaked active leases
    assert semaphore._value == max_in_flight, (
        f"Concurrency slot leak detected! Expected {max_in_flight} permits, found {semaphore._value}."
    )
    assert len(client._active_leases) == 0, (
        f"Uncleaned active leases in client tracking: {client._active_leases}"
    )
    logger.info("Worker gracefully stopped. All permits cleanly reclaimed.")

async def main(mode: str = "all"):
    if mode in ("normal", "all"):
        logger.info("=== Running Mode: Normal Backpressure (5 events, concurrency=2) ===")
        client = MockEventClient(lease_duration=1.0)
        await run_consumer(client, max_in_flight=2, total_events=5, simulated_delay=0.05)

    if mode in ("nack", "all"):
        logger.info("=== Running Mode: Business Error & nack (5 events, concurrency=2) ===")
        client = MockEventClient(lease_duration=1.0)
        await run_consumer(client, max_in_flight=2, total_events=5, simulated_delay=0.05, fail_with_business_error=True)

    if mode in ("timeout", "all"):
        logger.info("=== Running Mode: Lease Timeout Detection (3 events, lease=0.08s, work=0.18s) ===")
        client = MockEventClient(lease_duration=0.08)
        await run_consumer(client, max_in_flight=2, total_events=3, simulated_delay=0.18, heartbeat_renewal=False)

    if mode in ("renewal", "all"):
        logger.info("=== Running Mode: Heartbeat Lease Renewal (3 events, lease=0.08s, work=0.18s) ===")
        client = MockEventClient(lease_duration=0.08)
        await run_consumer(client, max_in_flight=2, total_events=3, simulated_delay=0.18, heartbeat_renewal=True)

if __name__ == "__main__":
    selected_mode = sys.argv[1].lower() if len(sys.argv) > 1 else "all"
    asyncio.run(main(selected_mode))
```

#### Verification Criteria and Permutations
When executing this script in Python 3.10+:
1. **Backpressure and Permit Reclamation**: With `total_events` (5) exceeding `max_in_flight` (2), tasks cannot run concurrently without permit reuse. If `semaphore.release()` were omitted, the worker would hang indefinitely on event 3 awaiting a permit. Upon completion, the explicit assertion `semaphore._value == max_in_flight` and `len(_active_leases) == 0` guarantees that no permits or lease trackers were leaked.
2. **Direct CLI Execution**: The entrypoint accepts an optional command-line argument (`all`, `normal`, `nack`, `timeout`, `renewal`). By default (`all`), it executes all four scenarios sequentially and terminates with exit code 0.

### 3. Internal Mechanisms: Lease Lifecycle and Backpressure

Beginners often treat message pulling as simple file downloading, neglecting distributed message ownership.

- **Lease Lifecycle**: When emitting an event, the broker records an expiration timestamp for `lease_token`. If the consumer calls `ack` within the lease duration, the broker permanently retires the event. If the deadline elapses without an acknowledgment, the broker marks the worker as stalled or dead and makes the event available for redelivery.
- **Local Semaphore Backpressure**: Why can't the worker poll continuously? While the broker enforces connection-level limits, unconstrained local polling during downstream I/O slowdowns would allocate thousands of pending coroutines into Python heap memory, causing out-of-memory (OOM) crashes. Binding `fetch()` to `asyncio.Semaphore(max_in_flight)` synchronizes the fetch rate directly with the processing completion rate: a new message is pulled only after `semaphore.release()` has occurred for an existing slot.

### 4. Troubleshooting Patterns and Diagnostic Experience

When operational anomalies occur, isolate the cause using the diagnostic trees below:

#### Failure Mode 1: Worker stops fetching but process remains alive (Concurrency Hang)

- **Symptoms & Trigger**: After running for several hours, logs cease completely. CPU usage drops near 0%, and the process does not terminate.
- **Diagnostic Telemetry**:
  1. Inspecting internal metrics shows `semaphore._value == 0`.
  2. Examining stack traces reveals that an unhandled exception occurred inside `process_single_event`.
- **Investigation Steps & Hypotheses**:
  - *Hypothesis 1*: Upstream broker disconnected, hanging the `fetch()` network socket. Test: Verified network connectivity via TCP probe; socket telemetry confirmed the client was simply not issuing fetch requests. Hypothesis rejected.
  - *Hypothesis 2*: Semaphore slot leakage. Adding counter logging revealed that in previous code, `semaphore.release()` was placed only at the end of the `try` block. When unhandled exceptions occurred, the coroutine aborted, permanently losing a concurrency permit.
- **Root Cause & Fix**: Move `semaphore.release()` into the `finally` block (as shown in the reference code), guaranteeing slot reclamation across all exit paths.

#### Failure Mode 2: Identical message repeatedly re-pulled, triggering duplicate execution (Retry Storm)

- **Symptoms & Trigger**: Downstream services alert that an event is executed repeatedly by the same worker. Worker logs report `LeaseExpiredError` followed by broker re-delivery.
- **Diagnostic Evidence Chain**:
  - Broker metrics show delivery attempt counter `delivery_count` incrementing continuously.
  - Latency logging shows this specific workload involves heavy data processing, taking an average of 1.4 seconds in an environment configured with a 1.0-second lease.
- **The Attribution Trap (Attributing Single Root Causes to Multi-Variable Changes)**:
  - During an emergency debugging session on a production cluster, engineers simultaneously applied two changes: (1) Reduced worker concurrency from 10 to 2; (2) Increased broker lease timeout from 1.0s to 3.0s. The issue immediately disappeared.
  - **Flawed Conclusion**: *"Reducing concurrency eliminated CPU contention, resolving duplicate delivery."*
  - **Isolated Verification**:
    - *Isolation Test A (Hold lease at 1.0s, reduce concurrency to 2)*: Injected 1.4s processing delay. Result: `LeaseExpiredError` continued to trigger on every run. Specifically, the worker completed its simulated work at second 1.4, but upon calling `ack()`, the client rejected the token because the 1.0s deadline had expired at $t=1.0\text{s}$. This disproved that concurrency reduction alone resolved the issue.
    - *Isolation Test B (Hold concurrency at 10, extend lease to 2.0s or enable `renew_lease`)*: Injected 1.4s processing delay. Result: In the local mock runner, `ack()` succeeded at second 1.4 without raising `LeaseExpiredError`. In the production cluster telemetry, extending lease duration and enabling periodic renewal prevented broker-side lease reclamation, dropping duplicate broker re-deliveries to zero.
  - **Honest Operational Boundary**:
    - While extending the lease or enabling periodic renewal solves the immediate protocol timeout, it does not explain *why* the task required 1.4 seconds. Disentangling downstream I/O latency from genuine CPU starvation requires independent profiler telemetry rather than guesswork based on lease settings.
    - *Simulation vs. Production Boundaries*: The accompanying Python script is an in-memory pedagogical mock designed to demonstrate state transitions, lease checks, and concurrency limits. It does not contain a real network transport or a broker-side redelivery queue. Furthermore, if `fetch()` itself encounters a fatal network error in a real environment, the exception occurs outside `process_single_event`; production consumers must wrap the polling loop in connection retry and exponential backoff logic.

### 5. Follow-Up Exercises and Pre-Flight Checks

Before deploying to production, execute verification tests against the four distinct execution boundaries using the script entrypoint:

1. **Normal Backpressure**:
   Run `python script.py normal`. Confirm that 5 events process across concurrency ceiling 2 and exit cleanly with all permits reclaimed.
2. **Business Error Handling (`nack`)**:
   Run `python script.py nack`. Confirm that injected exceptions trigger `sending nack` and that subsequent events continue processing smoothly without hanging.
3. **Lease Timeout Detection**:
   Run `python script.py timeout`. Confirm that `LeaseExpiredError` is caught upon calling `ack()` when task execution exceeds lease duration.
4. **Lease Renewal for Long Tasks**:
   Run `python script.py renewal`. Confirm that background `renew_lease` extends the active deadline, allowing long tasks to log `ACK ok`.

---

## Organizational Acceptance Review

- **Why keep this in a single entry rather than three separate documents**:
  - Splitting this content into *"EventRunner Concepts"*, *"EventRunner Quickstart"*, and *"EventRunner Post-Mortem"* would force readers to jump between files to reconcile lease mechanics with semaphore code.
  - Consolidating concept, code, and failure modes around the unified reader objective (*"reliably integrate and operate an EventRunner consumer"*) minimizes cognitive overhead.
- **Troubleshooting rigor**:
  - Specifically addresses the multi-variable attribution fallacy, complying strictly with troubleshooting knowledge standards by documenting isolated single-variable verification tests.
