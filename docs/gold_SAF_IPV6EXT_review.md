# Gold triples for SAF_IPV6EXT — lecturer review

Validated by: ________  
Date: ________

| ID | Subjek (diterima) | Predikat | Objek | Kriteria | Bobot | OK? |
|---|---|---|---|---|---|---|
| R1 | ExtensionHeaders | provides | OptionalInformation | K1_Definition (Extension headers carry optional extra information) | 1 | ☐ |
| R2 | ExtensionHeaders | follows | FixedHeader | K2_Location (Between the fixed header and the payload) | 1 | ☐ |
| R3 | ExtensionHeaders | precedes | Payload | K2_Location (Between the fixed header and the payload) | 1 | ☐ |
| R4 | ExtensionHeaders | allows | NewOptions | K3_Advantage (New options without changing the fixed header) | 1 | ☐ |

## Konsep dan alias

- **ExtensionHeaders**: extension headers, extension header, ipv6 extension headers, extensions header, optional headers
- **OptionalInformation**: optional information, additional information, additional options, supplementary information, optional network layer information
- **FixedHeader**: fixed header, fixed headers, main header, ipv6 header, standard header, base header, the header
- **Payload**: payload, the payload, upper-layer header, transport-layer header, upper-level headers, the data
- **NewOptions**: new options, appending new options, future requirements, extensibility, flexibility
