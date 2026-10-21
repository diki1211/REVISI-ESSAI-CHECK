# Gold triples for SAF_DUPMETH — lecturer review

Validated by: ________  
Date: ________

| ID | Subjek (diterima) | Predikat | Objek | Kriteria | Bobot | OK? |
|---|---|---|---|---|---|---|
| R1 | TemporaryTSAP | prevents | DuplicatePackets | K1_TemporaryTSAP (Temporarily valid TSAPs) | 1 | ☐ |
| R2 | TemporaryTSAP | prevents | WellKnownTSAP | K1_TemporaryTSAP (Temporarily valid TSAPs) | 1 | ☐ |
| R3 | ConnectionIdentification | prevents | DuplicatePackets | K2_ConnectionIds (Identifying connections individually) | 1 | ☐ |
| R4 | ConnectionIdentification | requires | PersistentStorage | K2_ConnectionIds (Identifying connections individually) | 1 | ☐ |
| R5 | PDUSequenceNumbers | prevents | DuplicatePackets | K3_PduSeqNo (Identifying PDUs individually) | 1 | ☐ |
| R6 | PDUSequenceNumbers | requires | BandwidthOverhead | K3_PduSeqNo (Identifying PDUs individually) | 1 | ☐ |

## Konsep dan alias

- **TemporaryTSAP**: temporarily valid tsaps, temporarily valid tsap, temporary tsaps, temporary tsap, use temporarily valid tsaps, to use temporarily valid tsaps
- **ConnectionIdentification**: identify connections individually, to identify connections individually, identifying connections individually, connection identifiers, unique connection numbers, identify each connection by seqno
- **PDUSequenceNumbers**: identify pdus individually, to identify pdus individually, pdu sequence numbers, sequence numbers for each pdu, individual sequential numbers, sequence numbers, identify each pdu by seqno
- **DuplicatePackets**: duplicate packets, duplicates, duplicate pdus, the duplicate problem
- **WellKnownTSAP**: well-known tsaps, well known tsaps, well-known tsap, process server addressing, designated tsap, known tsap
- **PersistentStorage**: storage, memory, persistent storage, storing this information, large memory capacity, remembering assigned sequence numbers, store this information
- **BandwidthOverhead**: bandwidth overhead, higher usage of bandwidth and memory, more bandwidth, higher bandwidth usage, overhead
