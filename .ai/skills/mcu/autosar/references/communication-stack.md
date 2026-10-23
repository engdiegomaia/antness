# AUTOSAR Communication Stack

## Contents
- [Trace a communication path](#trace-a-communication-path)
- [Understand COM and PduR](#understand-com-and-pdur)
- [Integrate CAN modules](#integrate-can-modules)
- [Review network management](#review-network-management)

## Trace a communication path

Follow an application signal from SWC port through RTE and communication services to the bus driver and physical network, then trace the receive path back. Identify data types, signal groups, PDU mapping, update timing, routing, and ownership at every boundary.

## Understand COM and PduR

COM handles signal-level packing, unpacking, and configured transmission/reception behavior. PduR routes protocol data units between modules. Configuration controls update modes, deadlines, filtering, and routing; verify behavior in the selected AUTOSAR release and supplier tool.

## Integrate CAN modules

The CAN communication path commonly involves CAN interface, transport protocol, network management, and lower-level driver modules. Determine whether a message is a signal PDU, diagnostic transport, or network-management traffic. Check controller configuration, baud rate, identifier, payload layout, bus load, error handling, and transceiver state.

## Review network management

Network management coordinates communication availability and network state transitions. Validate startup, sleep, wakeup, partial networking if used, and shutdown interactions. Test lost communication, bus-off recovery, and transitions while application components are active.

## Sources

- *AUTOSAR Fundamentals and Applications*, chapter 7.
