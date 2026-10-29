"""Versi kontrak jawaban /localize dan /navgraph untuk klien (roadmap M1-8).

Aturan (docs/contract.md): menambah bidang baru tidak mengubah versi, karena klien lama mengabaikan
bidang yang tidak dikenal. Mengubah arti bidang yang ada, menghapusnya, atau mengubah tipenya
menaikkan CONTRACT_VERSION, dan endpoint lama tetap dilayani sampai klien lama tidak dipakai lagi.
Berkas contoh bersama di tests/fixtures/ diubah bersamaan, dan eutopos-mobile menyalinnya.
"""

CONTRACT_VERSION = 1
