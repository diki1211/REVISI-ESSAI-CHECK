# Gold triples for SAF_TCP1 — lecturer review

Validated by: ________  
Date: ________

| ID | Subjek (diterima) | Predikat | Objek | Kriteria | Bobot | OK? |
|---|---|---|---|---|---|---|
| R1 | CongestionControl | has | SlowStart | K1_Phases (Names slow start and congestion avoidance) | 1 | ☐ |
| R2 | CongestionControl | has | CongestionAvoidance | K1_Phases (Names slow start and congestion avoidance) | 1 | ☐ |
| R3 | SlowStart | increases | Cwnd | K2_Growth (Explains how cwnd grows in each phase) | 1 | ☐ |
| R4 | CongestionAvoidance | increases | Cwnd | K2_Growth (Explains how cwnd grows in each phase) | 1 | ☐ |
| R5 | PacketLoss | decreases | SsThresh | K3_Loss (Explains what happens to ss_thresh and cwnd after a loss) | 1 | ☐ |
| R6 | PacketLoss | decreases | Cwnd | K3_Loss (Explains what happens to ss_thresh and cwnd after a loss) | 1 | ☐ |

## Konsep dan alias

- **CongestionControl**: congestion control, tcp congestion control, the two phases, the 2 phases, congestion control with tcp
- **SlowStart**: slow start, slow-start, slow start phase, phase 1, the first phase
- **CongestionAvoidance**: congestion avoidance, congestion avoidance phase, phase 2, the second phase
- **Cwnd**: cwnd, congestion window, the congestion window, congestion window (cwnd)
- **SsThresh**: ss_thresh, ssthresh, ss-thresh, slow start threshold, the threshold, ss_tresh, threshhold
- **PacketLoss**: packet loss, loss, lost packet, a lost packet, timeout, a timeout, time out, congestion, a packet is lost, package loss
