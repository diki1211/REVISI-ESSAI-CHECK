<!-- From SAF (Filighera et al., 2022), CC-BY-4.0. -->
1.A mapping between destinations/stations (MACs) and outgoing LAN interfaces.
2.This table is initially empty and received packages are flooded on every line. When a bridge receives a frame (as the bridge runs in promiscuous mode it listens in on all the traffic arriving at its LAN links) with source address Q on LAN L, it adds the timestamped entry “Q can be reached over L” to the table and the next time a packet with destination Q arrives, it is forwarded on link L. The time-stamp is used to update or purge old entries. Therefore, it learns by observing the incoming traffic.
3.To do selective forwarding instead of flooding. 
4.i)less duplication/unnecessary flooding is prevented.
ii)less congestion.
iii)better bandwidth usage than flooding.
