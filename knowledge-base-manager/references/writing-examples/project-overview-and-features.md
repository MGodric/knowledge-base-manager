# Worked Example: LightKV Distributed Cache Overview and Failover Monograph

> Note: This document is a fictional instructional worked example designed to demonstrate multi-depth project documentation (R8), architectural trade-off analysis, and end-to-end feature tracing. Systems, APIs, code paths, and benchmarks represent illustrative patterns rather than real production software. Source code paths refer to the fictional repository layout.

## Background Context and Common Input

**Fictional Project Specification**:
- **Project Identity**: `LightKV` (fictional out-of-process metadata cache daemon and client SDK).
- **Core Problem & Baseline**: Microservice clusters perform millions of read-only configuration lookups per second. Routing every read to a centralized cluster incurs 5~10ms network round-trip overhead. LightKV provides a local in-memory read mirror achieving sub-0.5ms reads.
- **Constraints & Non-Goals**:
  - Capacity limit: 500,000 keys logical dataset capacity cluster-wide (fully mirrored across all nodes without sharding), with a physical ceiling of 4GB RAM per node.
  - No distributed multi-key ACID transactions.
  - Single administrative ingress publisher; microservices have read-only access.
- **Master Lease & Client Lease Clamping Model**:
  - Ingress Admin publishes configuration updates with a strictly incrementing `epoch_id` and grants a 5.0-second master lease (`master_lease_ttl = 5.0s`) to active read nodes. Nodes renew this lease periodically (every 1.5s).
  - Nodes exchange state via UDP Gossip. A node serves client reads only while its own master lease remains valid.
  - If a node is partitioned from Ingress Admin, its master lease expires at most 5.0 seconds from the last renewal.
  - **Client Lease Clamping Rule**: When a client requests or renews its local cache lease (default `client_lease_ttl = 2.0s`), the node clamps the granted lease duration to the remaining lifetime of its own master lease:
    $$\text{granted\_client\_ttl} = \min(\text{client\_lease\_ttl}, \max(0, \text{master\_lease\_expires\_at} - \text{now}))$$
    If $\text{master\_lease\_expires\_at} \le \text{now}$, the node refuses renewals with `StaleMasterLeaseError`.
  - **Strict Bounded Staleness (Instructional Model Conditions)**:
    Within an idealized instructional model assuming shared reference clocks and negligible network transit/installation delay:
    Suppose a node disconnects from Ingress Admin at $t=0$ with a master lease expiring at $t=5.0\text{s}$. At $t=1.0\text{s}$, a client receives $\min(2.0, 4.0) = 2.0\text{s}$ (expires $t=3.0\text{s}$). At $t=4.5\text{s}$, a client receives $\min(2.0, 0.5) = 0.5\text{s}$ (clamped to expire at $t=5.0\text{s}$). At $t=4.9\text{s}$, the client receives a 0.1s lease (expires $t=5.0\text{s}$). At $t \ge 5.0\text{s}$, renewals are rejected. Consequently, no client read can execute against a cached lease extending beyond $t=5.0\text{s}$, guaranteeing a strict 5.0-second upper bound on stale reads during partitions.
    *Physical Boundary Note*: In a real physical network, if a client receives a 0.1s lease grant after a network transit delay of 0.2s (granted at $t=4.9\text{s}$, received at $t=5.1\text{s}$) and starts counting from reception, local reads would run until $t=5.2\text{s}$. Therefore, production implementations must either convey absolute expiration timestamps or deduct round-trip transmission latency.

---

## Part 1: Project Overview (Worked Example)

### LightKV: Distributed In-Memory Read-Only Metadata Cache

#### 1. System Positioning and Boundaries

LightKV is an out-of-process, read-only configuration and metadata distribution cache designed for microservice environments.
- **Problem Solved**: Reduces read latency for configurations under high read concurrency from 5~10ms in centralized stores to sub-0.5ms within the local subnet.
- **Explicit Non-Goals**:
  1. Does not provide cross-node ACID transactions or write-heavy synchronization.
  2. Does not serve as a durable persistence store or large-object blob store (capacity ceiling: 500,000 keys logical dataset capacity cluster-wide, 4GB RAM physical ceiling per node, with the full dataset mirrored on each node).
  3. Writes are published solely through a dedicated single administrative gateway; no public microservice write APIs are exposed.

#### 2. Current Baseline and Capability State

- **Baseline Date**: 2026-09-20
- **Code Baseline**: Git commit `c48e10af92` (Release `v0.3.2`).
- **Capability State Snapshot**:
  - *Released & Production-Verified*: Embedded LMDB read engine, UDP Gossip peer discovery, transparent client-side lease caching with master lease clamping.
  - *Implemented Unreleased*: Prometheus latency histogram exporter on branch `v0.4.0-rc1` (pending soak testing).
  - *Planned Unimplemented*: Automated cross-datacenter multi-region synchronization.
  - *Known Limitations*: When cluster size exceeds 64 nodes, Gossip convergence latency degrades from 1.2s to over 8s; recommended deployment scale is $\le 32$ nodes per cluster.

#### 3. Core Design Principles and Architectural Decisions

During initial architecture design, the team evaluated a Raft-based strong consensus store against a weakly consistent Gossip-and-lease model:

| Evaluation Dimension | Option A: Full Sync via Consensus (Raft) | Option B (Selected): Gossip + Node Leases with Clamping |
| --- | --- | --- |
| Read Latency | 0.8~2.5ms (requires consensus state validation) | 0.18ms average (reads local in-memory mirror directly) |
| Partition Tolerance | Minority partition rejects writes and halts reads | Allows bounded stale reads ($\le 5.0\text{s}$ enforced via lease clamping); 99.999% availability |
| Operational Footprint | Requires quorum election, WAL management, and snapshots | Leaderless decentralized daemon with zero external dependencies |

- **Rationale & Trade-offs**: Microservices can tolerate configuration updates taking up to 5.0 seconds to propagate, but cannot tolerate configuration outages halting service clusters during transient network partitions. Option B accepts bounded eventual consistency in exchange for extreme read availability and trivial operations.
- **Lease Clamping Enforcement**: To prevent partitioned nodes from extending client leases past the master lease boundary within the idealized shared-clock model, all client lease grants are strictly clamped: $\text{granted\_ttl} = \min(2.0\text{s}, \text{master\_lease\_remaining})$. Thus, even if a client requests a renewal at $t=4.9\text{s}$ from an isolated node, the lease is clamped to 0.1s, ensuring that all client caches expire simultaneously with the node's master lease at $t=5.0\text{s}$ (precluding lease extensions into the partition window, assuming transmission latency is negligible or absolute expiration timestamps are communicated).
- **Revisit Trigger**: If new billing or credential revocation requirements demand sub-millisecond global write consistency, that subsystem must be extracted from LightKV into a dedicated consensus store.

#### 4. System Architecture and Data Flow

The system consists of an Ingress Admin gateway, peer Read Nodes, and client SDKs:

```text
[Write API] Ingress Admin (Single Master)
                 │  (gRPC Broadcast + 5.0s Master Lease)
                 ▼
         ┌───────────────┐  Gossip Sync    ┌───────────────┐
         │ LightKV Node A │ ◄─────────────► │ LightKV Node B │
         └───────┬───────┘ (Epoch Version) └───────┬───────┘
                 ▲                                 ▲
                 │ (Clamped Client Lease Probe)    │ (Failover Backup)
         ┌───────┴─────────────────────────────────┴───────┐
         │               Client SDK (In-App)               │
         └─────────────────────────────────────────────────┘
```

- **Dependency Direction**: Client SDKs depend on static seed lists; Clients only pull from Nodes; Nodes exchange peer state over Gossip; Nodes maintain zero awareness of individual client identities.

#### 5. Version Evolution and Breaking Changes

- **v0.2.x -> v0.3.0 (June 2026)**:
  - **Trigger**: v0.2 used fixed 3000ms heartbeat timeouts. In hybrid-cloud links, intermittent 3.2s network congestion caused false node-failure reports, inducing client reconnection storms.
  - **Architectural Change**: Replaced fixed timeouts with a $\Phi$-Accrual Failure Detector that models inter-arrival heartbeat intervals dynamically.
  - **Migration Impact**: Deprecated `heartbeat_timeout_ms` in configuration, replacing it with `phi_threshold: 8.0` and `window_size: 100`. Running v0.3 with v0.2 configurations triggers immediate validation panics. Migrate using `scripts/migrate_v02_v03.py`.

#### 6. Navigational Pointers and Evidence Anchors
- Client Failover Deep Dive: See [Part 2: Feature Monograph](#part-2-feature-monograph-worked-example) in this document.
- Illustrative Repository Paths: `src/server/` (node daemon), `src/client/` (client SDK), `tests/chaos/partition_tests.rs` (chaos partition suite).

---

## Part 2: Feature Monograph (Worked Example)

### LightKV Client Failover and Lease Renewal Flow

> Context: Feature deep-dive for [Part 1: Project Overview](#part-1-project-overview-worked-example)
> Knowledge Role: `method` (operational mechanism)
> Verification Baseline: Git commit `c48e10af92` (v0.3.2)

#### 1. Contract and Trigger Scenarios

- **User Scenario**: Microservice instances call `client.get("service.db.url")` continuously. When the currently connected LightKV node crashes or suffers network disconnection, the SDK must fail over transparently to a secondary node within 200ms, incurring at most one retry latency penalty.
- **Prerequisites**: The client holds a locally cached `LeaseToken` containing `epoch_id`, `lease_expires_at`, and `data_hash`.

#### 2. End-to-End Execution Flow (Normal and Error Paths)

```text
[Operation] client.get(key)
   │
   ├─► Is local lease valid? (now < lease_expires_at)
   │      ├─► YES ──► Return local mirror immediately (0.1ms)
   │      └─► NO  ──► Initiate async lease renewal / probe
   │
   ▼
[Network Probe] Send PingLease(epoch_id) to active node
   │
   ├─► Success (RTT <= 50ms) ──► Advance lease_expires_at to min(now + 2.0s, master_lease_expiry); reset fail counter
   │
   └─► Timeout (Threshold 80ms) ──► Trigger Failover State Machine:
          │
          ├─ 1. Mark active node SUSPECT; quarantine for 30s
          ├─ 2. Select optimal backup Node_B from SeedNodes via weighted RTT
          ├─ 3. Transmit AttachAndRenewRequest(epoch_id, data_hash) to Node_B
          │      │
          │      ├─► Branch 2.1 (Hash Match): Node_B returns RenewOk with clamped lease
          │      │      └─► Switch active binding to Node_B; service restored
          │      │
          │      └─► Branch 2.2 (Hash Mismatch): Client cache epoch is stale
          │             ├─► Node_B returns StaleHashReject(latest_epoch)
          │             ├─► Client purges local cache mirror
          │             ├─► Client triggers full SyncSnapshot from Node_B
          │             └─► Rebuilds memory table and installs clamped lease
```

#### 3. Concurrency Controls and Side Effects

- **Lock Contention Under Thundering Herd**: If failover triggers while 100 application threads call `get()`, the SDK employs a `SingleFlight` coalescer: exactly one background request is dispatched to Node_B. The remaining 99 threads suspend and await that single result, preventing connection floods against backup nodes.
- **Stale Read Window and Linearizability Boundary**: During network partitions, clients continue reading locally cached values only until their clamped client lease expires (at most 2.0 seconds normally, and never past the partitioned node's 5.0-second master lease deadline). Inspecting `record.created_timestamp` allows clients to observe the age of cached entries or detect regressions, but cannot guarantee that concurrent updates were not committed at Ingress Admin during a partition. Workloads requiring strict linearizability or absolute zero-staleness must bypass local caches and issue synchronized read probes directly to the authoritative Ingress Admin gateway.

#### 4. Source Code Anchors (Illustrative Repository Paths)

In the LightKV source repository, the core implementation is structured across these modules (paths are illustrative code locations within the project repository):
- **Failover State Machine**: `src/client/failover.rs:142-215` (`FailoverManager::handle_timeout`, quarantine logic and weighted peer selection).
- **Concurrency Coalescing**: `src/client/singleflight.rs:30-75` (`SingleFlightGroup::do_chan`, deduplication of in-flight renewal RPCs).
- **Protocol Encodings**: `src/protocol/messages.rs:88-120` (`PingLease` and `AttachAndRenewRequest` binary layout).

#### 5. Validation Evidence and Operational Limitations

- **Automated Verification**:
  - Chaos benchmark `tests/chaos/failover_benchmark_test.rs`: Under 10,000 continuous QPS, simulated network packet drops disconnected the active node. 99.9% of requests recovered on Node_B within 142ms without unhandled panics or truncated responses.
- **Untested Boundary Conditions**:
  - High-latency WAN links (RTT > 200ms) were not tested; an 80ms probe timeout causes false failovers in high-latency environments. Adaptive RTT timeouts are planned for v0.4.
