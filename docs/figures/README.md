# Gambar

> 🚧 **Gambar final belum matang.** Sampai gambar final siap, diagram Mermaid di bawah dipakai sebagai
> acuan. GitHub merendernya langsung. Deskripsi lengkap dan aturan tiap gambar ada di
> `docs/pa-context.md`, bagian 11.

| Berkas (nanti) | Keterangan |
|---|---|
| `gambar-1-arsitektur.png` | Gambar 1. Arsitektur platform indoor navigation terintegrasi AI avatar assistant berbasis RAG |
| `gambar-2-alur.png` | Gambar 2. Alur pemrosesan pertanyaan pengguna hingga navigasi AR |

## Gambar 1. Arsitektur (versi Mermaid)

```mermaid
flowchart LR
  subgraph HP["Perangkat Pengguna (Android)"]
    AR["ARCore Motion Tracking"]
    subgraph UNITY["Aplikasi Unity"]
      NAV["NavMesh (Pathfinding)"]
      OVL["AR Route Overlay"]
    end
    MIC["Input Mikrofon"]
    AVA["Avatar 3D (UniVRM + Lip Sync)"]
  end

  subgraph SRV["Server Instansi (On-Premise)"]
    subgraph NAVSVC["Layanan Navigasi"]
      VPS["VPS Service (FastAPI)<br/>hloc + LightGlue + PnP"]
      MAP["Peta 3D (COLMAP)"]
      POIDB["Basis Data POI"]
      ANC["Anchoring Tool (Dashboard Web)"]
    end
    subgraph AISVC["Layanan AI"]
      STT["Speech-to-Text"]
      VEC["Vector Database"]
      LLM["Model Bahasa (LLM)"]
      TTS["Text-to-Speech (sherpa-onnx)"]
    end
  end

  AR --> UNITY
  AR -- "Frame kamera (koreksi berkala)" --> VPS
  VPS -- "Pose 6-DoF" --> UNITY
  VPS --> MAP
  ANC -- "Kelola POI" --> POIDB
  POIDB -- "Koordinat POI" --> UNITY
  MIC -- "Audio pertanyaan" --> STT
  STT -- "Retrieval (RAG)" --> VEC
  VEC --> LLM
  LLM -- "ID POI tujuan" --> POIDB
  LLM --> TTS
  TTS -- "Audio jawaban" --> AVA
```

## Gambar 2. Alur (versi Mermaid)

```mermaid
flowchart TD
  subgraph T1["Tahap 1: Penentuan Tujuan"]
    L0(["Mulai"])
    L1["Pengguna mengajukan pertanyaan suara"]
    L2["Speech-to-Text mengubah suara menjadi teks"]
    L3["RAG mengambil konteks dari basis pengetahuan"]
    L4["Model bahasa menghasilkan jawaban dan ID POI tujuan"]
    L5{"POI tujuan ditemukan?"}
    L6["Avatar meminta pengguna memperjelas pertanyaan"]
    L7["Avatar 3D menyampaikan jawaban (Text-to-Speech + Lip Sync)"]
    L8["Aplikasi mengambil koordinat POI dari basis data"]
  end

  subgraph T2["Tahap 2: Navigasi"]
    R1["Kamera mengirim satu frame ke VPS Service"]
    R2["VPS mengestimasi pose 6-DoF (hloc + LightGlue + PnP)"]
    R3{"Lokalisasi berhasil?"}
    R4["Pengguna diarahkan memindai area lain"]
    R5["Menyelaraskan koordinat ARCore dengan koordinat gedung"]
    R6["NavMesh menghitung jalur menuju POI"]
    R7["Menampilkan jalur AR, ARCore melacak pergerakan"]
    R8{"Sampai di tujuan?"}
    R9{"Waktunya koreksi berkala?"}
    R10(["Selesai"])
  end

  L0 --> L1 --> L2 --> L3 --> L4 --> L5
  L5 -- "Ya" --> L7
  L5 -- "Tidak" --> L6 --> L1
  L7 --> L8 --> R1
  R1 --> R2 --> R3
  R3 -- "Ya" --> R5
  R3 -- "Tidak" --> R4 --> R1
  R5 --> R6 --> R7 --> R8
  R8 -- "Ya" --> R10
  R8 -- "Tidak" --> R9
  R9 -- "Ya" --> R1
  R9 -- "Tidak" --> R7
```

## Pilihan untuk gambar final

| Pilihan | Dirender GitHub? | Bisa disunting ulang? | Cocok untuk |
|---|---|---|---|
| **Mermaid** (di atas) | ✅ langsung | ✅ teks biasa, mudah dilacak di git | Acuan hidup di repo |
| **Excalidraw, ekspor SVG atau PNG dengan opsi *embed scene*** | ✅ sebagai gambar | ✅ berkasnya bisa dibuka lagi di excalidraw.com atau ekstensi Excalidraw di VS Code | Gambar final bergaya sketsa |
| **Berkas `.excalidraw` mentah** | ❌ hanya JSON | ✅ | Tidak disarankan di repo ini |
| **draw.io, ekspor `.drawio.svg`** | ✅ sebagai gambar | ✅ | Gambar final bergaya formal untuk dokumen PA |

**Saran:** Mermaid tetap jadi acuan di repo. Untuk dokumen PA, buat gambar final dengan Excalidraw
atau draw.io, lalu ekspor SVG yang menyertakan data gambarnya supaya bisa disunting ulang. Pastikan isi
gambar final tetap sama dengan diagram Mermaid di atas.

Sebelum commit gambar apa pun, pastikan tidak ada nama server internal, alamat IP, atau data pribadi,
karena repo ini publik.
