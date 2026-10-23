# FPGA Logic and Implementation Flow

## Contents
- [Describe synchronous behavior](#describe-synchronous-behavior)
- [Simulate before implementation](#simulate-before-implementation)
- [Synthesize and constrain](#synthesize-and-constrain)
- [Close timing incrementally](#close-timing-incrementally)

## Describe synchronous behavior

HDL describes hardware that exists concurrently; it is not ordinary software executed line by line. Separate combinational logic from clocked state updates. Define reset polarity and behavior, clock edges, data widths, and signedness explicitly. Avoid inferred latches unless they are intentional and supported by the design methodology.

Use a consistent coding style for the chosen SystemVerilog, Verilog, or VHDL subset. Tool support differs; check language version and synthesis semantics. A simulation passing does not guarantee the synthesizer inferred the intended circuit, so inspect warnings and synthesized structure.

## Simulate before implementation

Build testbenches that check behavior rather than only produce waveforms. Exercise boundary values, reset assertion and release, consecutive transactions, stalls, and invalid inputs. Use assertions or scoreboards where practical. Keep simulation models consistent with the intended hardware and document any behavioral abstraction.

## Synthesize and constrain

Synthesis maps RTL into device resources. Review inferred memories, multipliers, clock enables, latches, and high-fanout nets. Constraints describe clocks and timing relationships, including I/O delays and asynchronous clock groups where justified. A missing or incorrect constraint can make reports look clean while the real interface fails.

Separate functional correctness from timing closure. Use timing reports to identify path start/end points, logic depth, routing contribution, and setup/hold requirements. Do not add false-path or multicycle exceptions without a functional and timing rationale.

## Close timing incrementally

Use pipelining, balanced logic, appropriate resource inference, and placement-aware design to shorten critical paths. Re-run implementation after changes; synthesis estimates do not include all routing effects. Check worst negative slack, unconstrained paths, clock uncertainty, and resource use. Keep timing closure linked to actual board clocks and I/O specifications.

## Sources

- *FPGA Programming Handbook*, 2nd ed., chapters 1–5 and 14.
- *Architecting and Building High-Speed SoCs*, chapters 2 and 7.
