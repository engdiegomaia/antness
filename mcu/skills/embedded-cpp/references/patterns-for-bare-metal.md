Design patterns that fit bare-metal firmware: command, adapter, sequencer, observer (runtime and compile-time) and finite state machines.

## Contents

- [Pattern chooser](#pattern-chooser)
- [Sequencer instead of a growing super-loop](#sequencer-instead-of-a-growing-super-loop)
- [Observer](#observer)
- [Finite state machines](#finite-state-machines)
- [Pitfalls](#pitfalls)

## Pattern chooser

| Problem | Pattern | Notes |
|---|---|---|
| Run something later or from an interrupt | Command (callable stored and invoked later) | `std::function`, `etl::delegate` or function pointer; see [type-safety-and-lambdas.md](type-safety-and-lambdas.md) |
| Vendor C API behind your interface | Adapter | See [hal-and-c-interop.md](hal-and-c-interop.md) |
| Many flags and `if`s in a super-loop | Sequencer (prioritized task queue) | Below |
| One source, several consumers | Observer | Below |
| Many states and events | FSM, State pattern, or a table library | Below |

## Sequencer instead of a growing super-loop

A super-loop that polls a flag per ISR event scales badly: more global flags, more places to forget to clear
a flag or add a condition, and no clean way to prioritize.

- The ISR adds a **task** (a callable plus priority, not an OS task) to the sequencer. The main loop runs
  the sequencer, which always executes the highest-priority waiting task.
- Design follows the command pattern, with the sequencer as invoker.
- Task type: a class template over the callable holder, with `operator<` comparing priority.
- Storage: `std::priority_queue` over a fixed-capacity vector (for example `etl::vector`) so nothing
  allocates. The sequencer is a static template over task type and capacity.
- Callable holder: `std::function` may allocate for large captures; `etl::delegate` never allocates but does
  not hold capturing lambdas and is non-owning.
- The sequencer gives ordered, prioritized execution but not real-time guarantees. If there are deadlines,
  each task must monitor its own execution time. The sequencer is cooperative, so a long task delays all
  others. If you need preemption, move to an RTOS (see `freertos`).
- Adding from an ISR means the container needs protection against concurrent access if the main loop pops at
  the same time; decide on a critical section or a lock-free structure. This is a design point to check
  rather than a detail the book settles.

## Observer

A publisher keeps a list of subscribers and notifies them (temperature publisher with logger, display and
data-sender subscribers).

**Runtime version.** A `subscriber` interface with a pure virtual `update(float)`. The publisher holds an
`etl::vector<subscriber*, 8>` with `register_sub`, `unregister` and `notify`. Flexible at run time, with
virtual calls and a container to walk.

**Compile-time version.** A variadic template `publisher<Subs...>` whose `notify` calls
`Subs::update(value)` for each type with a fold expression. Subscribers are known at compile time, so there
is no container, no registration, no virtual call, and the compiler inlines the calls. The book calls this a
zero-cost abstraction and shows a smaller and faster result than the runtime version.

Limits of the simple compile-time form: subscribers must be listed up front in one place, and everything is
fixed at build time. Improve it by letting a publisher also accept other publishers: concepts (`Updatable`,
`Notifiable`) plus `if constexpr` pick `update` or `notify` per type, so subscriber groups compose.

Choose runtime when subscribers come and go while running, compile-time when the wiring is fixed.

## Finite state machines

An FSM holds one of a finite set of states, changes state on events, and can run actions on transitions
(Mealy style) and on entry or exit (Moore style). The book builds a BLE connection FSM (idle, advertising,
connected) four ways, in order of growing structure:

| Approach | Good for | Weakness |
|---|---|---|
| `switch` on state with `if` on event | Few states and events | Handler grows unreadable as states, events and actions multiply |
| State pattern: one class per state behind a common interface; the FSM holds pointers and the current state | Medium FSMs; behaviour grouped per state | Virtual calls; still `if/else` on events inside each state |
| State pattern with tag dispatch: events are empty types and each state overloads `handle_event` per event | Larger FSMs; no run-time event branching | More types and boilerplate |
| Table-driven library (Boost.SML) | Large FSMs; declarative `src + event [guard] / action = dst` rules | Third-party dependency, template-heavy errors |

The book reports that SML uses compile-time dispatch and typically beats both switch-based and virtual-call
State pattern versions; check the benchmark on your target before relying on it. A transition table is also
a clear way to document and review an FSM.

Design hygiene: draw the state diagram or table first, decide what unexpected events do, and test the FSM on
the host by feeding event sequences.

## Pitfalls

- A sequencer task that blocks.
- Unprotected access to the sequencer queue from ISR and main loop.
- Using the runtime observer with a heap-based container.
- Subscriber lists changed during `notify`.
- Letting an FSM `switch` grow past what a reviewer can hold in their head.
- Ignoring events in a state without deciding on purpose that they are ignorable.

Sources: C++ in Embedded Systems, ch 10 (command pattern), ch 13 (adapter), ch 14 (sequencer), ch 15 (observer, runtime and compile-time), ch 16 (finite state machines).
