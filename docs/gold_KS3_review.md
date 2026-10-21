# Gold triples for KS3 — lecturer review

Validated by: ________  
Date: ________

| ID | Subjek (diterima) | Predikat | Objek | Kriteria | Bobot | Premis | OK? |
|---|---|---|---|---|---|---|---|
| R1 | QueryDinamis | menyebabkan | SQLInjection | K1_Penyebab (Menjelaskan penyebab SQL injection) | 2 | — | ☐ |
| R2 | Penyerang | menyisipkan | PerintahSQL | K1_Penyebab (Menjelaskan penyebab SQL injection) | 1 | — | ☐ |
| R3 | PreparedStatement | memisahkan | KodeDanData | K2_Pencegahan (Menjelaskan pertahanan utama dan alasannya) | 1 | — | ☐ |
| R4 | PreparedStatement | mencegah | SQLInjection | K2_Pencegahan (Menjelaskan pertahanan utama dan alasannya) | 2 | R3 | ☐ |
| R5 | ValidasiAllowList | mengurangi | RisikoSQLInjection | K2_Pencegahan (Menjelaskan pertahanan utama dan alasannya) | 1 | — | ☐ |
| R6 | LeastPrivilege | mengurangi | DampakSerangan | K3_Mitigasi (Menyebutkan pertahanan tambahan) | 1 | — | ☐ |

## Konsep dan alias

- **QueryDinamis**: query dinamis yang menggabungkan input pengguna tanpa validasi, query dinamis, penggabungan input pengguna ke query, konkatenasi input, konkatenasi string, input pengguna tanpa validasi, input yang tidak divalidasi, query yang menggabungkan input pengguna
- **SQLInjection**: sql injection, injeksi sql, serangan sql injection, sqli
- **Penyerang**: penyerang, peretas, hacker, pelaku, attacker
- **PerintahSQL**: perintah sql, kode sql, query sql berbahaya, perintah sql berbahaya, sintaks sql
- **PreparedStatement**: prepared statement, prepared statements, parameterized query, query berparameter, kueri berparameter, parameterized queries
- **KodeDanData**: kode sql dari data, kode dan data, kode sql dan data, perintah dan data
- **ValidasiAllowList**: validasi input dengan allow list, validasi input, allow list, whitelist, validasi masukan
- **RisikoSQLInjection**: risiko sql injection, risiko injeksi sql, risiko serangan
- **LeastPrivilege**: prinsip hak akses minimal, hak akses minimal, least privilege, principle of least privilege, hak akses terbatas
- **DampakSerangan**: dampak serangan, dampak, kerusakan akibat serangan
