<!-- From SAF (Filighera et al., 2022), CC-BY-4.0. -->
Extension headers are used to extend the fixed IPv6 header with additional, optional network layer information. If present, they are located between the fixed header/main header and payload/upper-layer header/ transport-layer header.

Main advantage: One of the following advantages are considered fully correct:
1. It allows the appending of new options without changing the header.
2. IPv6 packets with optional headers are typically processed faster/simpler by intermediate devices as most of the options are ignored (except “Hop-by-Hop Extension”) while they are processed by all routers in IPv4 unless ordered otherwise.
