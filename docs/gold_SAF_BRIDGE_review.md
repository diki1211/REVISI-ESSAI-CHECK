# Gold triples for SAF_BRIDGE — lecturer review

Validated by: ________  
Date: ________

| ID | Subjek (diterima) | Predikat | Objek | Kriteria | Bobot | OK? |
|---|---|---|---|---|---|---|
| R1 | BridgeTable | has | StationMapping | K1_Content (The table maps stations to LAN interfaces) | 1 | ☐ |
| R2 | BackwardLearning / Bridge | uses | SourceAddress | K2_Learning (Backward learning reads the source address of incoming frames) | 1 | ☐ |
| R3 | Forwarding / Bridge | uses | BridgeTable | K3_Forwarding (Forwarding looks up the table) | 1 | ☐ |
| R4 | Forwarding | reduces | Flooding | K4_Benefit (Less flooding than forwarding everywhere) | 1 | ☐ |

## Konsep dan alias

- **BridgeTable**: bridge table, the bridge table, the table, table, forwarding table
- **StationMapping**: station mapping, mapping, station to lan mapping, mapping between stations and lan interfaces, output line, output lines, outgoing lan
- **Bridge**: bridge, the bridge, transparent bridge, transparent bridges
- **BackwardLearning**: backward learning, backwards learning, backwards learning phase, backward learning phase
- **SourceAddress**: source address, source addresses, the source address, source
- **Forwarding**: forwarding, the forwarding process, selective forwarding, forwarding process
- **Flooding**: flooding, unnecessary flooding, duplication, unnecessary traffic
