# Processes, threads, IPC and scheduling

## Choose by failure and data boundaries

Use separate processes when independent restart, address-space protection, privilege separation, or independently managed components matter. Use threads when shared in-process state and low-overhead coordination are valuable. Neither a large process count nor a large thread count is inherently efficient; measure scheduling, memory, and communication costs on the target.

Keep the unit of work clear: a process has its own virtual address space and resources; threads share process memory and many resources. Shared memory reduces copying but requires explicit synchronization and lifetime rules. Message passing often simplifies ownership and fault boundaries at the cost of serialization or queueing.

## Select IPC

| Mechanism | Useful when | Main design cost |
|---|---|---|
| Unix-domain socket | Local client/server, request/reply, credentials or descriptor passing | Connection lifecycle, framing, backpressure |
| FIFO | Simple one-way stream between related local programs | Limited message structure and awkward bidirectional flow |
| POSIX message queue | Local bounded messages with priorities | Capacity, naming, cleanup and platform configuration |
| Shared memory | High-volume data with predictable copy cost | Synchronization, ABI/layout agreement, crash recovery |
| Network socket or messaging library | Components may move across hosts or need richer routing | Network failure, protocol compatibility, security |

Define ownership, message framing, queue limits, timeouts, restart behavior, and version compatibility before implementation. Do not use shared memory merely to avoid designing a protocol.

## Lifecycle and scheduling

- Define who starts, supervises, and terminates each process. Handle signals, child reaping, cleanup, and restart loops deliberately.
- A daemon or service should report startup failure and health through the platform's service manager or a documented interface.
- Default Linux scheduling is appropriate for most work. Real-time policies and priorities need a measured deadline requirement, bounded critical section, and analysis of priority inversion and starvation.
- Separate hard timing requirements from best-effort UI, logging, and network work. Do not assume that increasing priority makes an overloaded design deterministic.

## Review

- [ ] Every shared object has a synchronization and ownership rule.
- [ ] Buffers and queues are bounded; overload behavior is explicit.
- [ ] Processes recover from peer restart and stale IPC endpoints.
- [ ] Priority and scheduling policy reflect measured requirements.
- [ ] Shutdown and restart paths are tested, including partial initialization.

Sources: *Mastering Embedded Linux Development*, 4th ed., ch 17 (process lifecycle, IPC, threads and scheduling).
