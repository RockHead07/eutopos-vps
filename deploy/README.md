# Deploy layanan eutopos

Docker Compose menjalankan **PostgreSQL** dan **API** (FastAPI + hloc). Rancangan: spesifikasi
`docs/specs/2026-09-29-capture-and-map-pipeline-design.md` bagian 2, 11, dan 12.

## 1. Menyiapkan host Windows dengan WSL2 (sudah terbukti di PC lab, 2026-09-29)

PC lab: Windows 10 22H2 (19045), i7-10700K, RTX 3070, driver NVIDIA 616.92, hanya partisi C:.
Semua langkah di bawah sudah dijalankan dan lolos di sana.

**PowerShell sebagai Administrator:**

```powershell
wsl --install --no-distribution
# restart Windows
wsl --update
wsl --version                  # harus menampilkan "WSL version: 2.x"
wsl --install -d Ubuntu-24.04 --location C:\wsl\ubuntu
# buat username dan password Linux saat diminta, lalu "exit" kembali ke PowerShell
wsl -l -v                      # Ubuntu-24.04, VERSION 2
```

**Di dalam Ubuntu** (`wsl -d Ubuntu-24.04`):

```bash
nvidia-smi                     # RTX 3070 terlihat; JANGAN pasang driver NVIDIA Linux di WSL
systemctl is-system-running    # running

# Docker Engine (https://docs.docker.com/engine/install/ubuntu/)
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
# exit, lalu masuk lagi supaya grup docker berlaku
docker run --rm hello-world

# NVIDIA Container Toolkit, untuk varian GPU
# (https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
docker run --rm --gpus all ubuntu nvidia-smi   # RTX 3070 terlihat dari dalam container
```

Versi terpasang di PC lab: WSL 2.7.14, Docker 29.8.1, Compose 5.5.1, NVIDIA Container Toolkit 1.20.1.

**Jebakan yang ditemui:**
- `wsl.exe` bawaan Windows 10 tidak mengenal `--location`. Pasang WSL versi baru dulu
  (`--install --no-distribution`), restart, baru pasang Ubuntu.
- Perintah `wsl` hanya jalan di PowerShell, bukan di dalam Ubuntu.
- `wsl --manage ... --set-sparse true` ditolak WSL karena risiko kerusakan data. **Jangan** dipaksa
  dengan `--allow-unsafe`.
- **Jangan memakai git Linux pada salinan repo di `C:`** (akhir baris CRLF terbaca sebagai perubahan).
  Salinan untuk Docker di-clone terpisah di folder rumah Linux.
- Kalau Docker Desktop terpasang di host yang sama, matikan **Settings > Resources > WSL integration**
  untuk `Ubuntu-24.04` supaya perintah `docker`-nya tidak bentrok dengan Docker Engine.
- Unduhan dari Docker Hub kadang terputus (`connection reset by peer`). Ulangi. Kalau sering, tambahkan
  `"registry-mirrors": ["https://mirror.gcr.io"]` ke `/etc/docker/daemon.json` tanpa menghapus bagian
  `runtimes.nvidia`, lalu `sudo systemctl restart docker`.

## 2. Menjalankan layanan (di dalam Ubuntu)

```bash
git clone https://github.com/RockHead07/eutopos-vps.git ~/eutopos-vps
mkdir -p ~/eutopos-data/maps
# peta hasil spike/run.py, misalnya peta data contoh dari salinan Windows:
cp -r /mnt/c/Users/<user>/eutopos-vps/outputs/demo ~/eutopos-data/maps/demo

cd ~/eutopos-vps/deploy
cp .env.example .env
nano .env        # isi POSTGRES_PASSWORD dan EUTOPOS_MAPS_DIR=/home/<user>/eutopos-data/maps
docker compose up -d --build
docker compose logs -f api    # tunggu "Application startup complete"
```

Pertama kali menyala, `/health` menjawab `"status": "no_map"` karena belum ada versi peta aktif.
Daftarkan dan terbitkan peta, lalu muat ulang layanan:

```bash
docker compose exec api python -m server.manage register demo "Data contoh" /maps/demo --publish
docker compose restart api
curl localhost:8000/health
```

Varian GPU (pengembangan saja, bukan untuk angka klaim):

```bash
docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
```

Bobot model (MegaLoc 915 MB, ALIKED, LightGlue) diunduh saat pertama menyala dan disimpan di volume
`cache`, jadi tidak diunduh ulang saat container dibuat ulang.

## 3. Jebakan saat pertama menjalankan layanan (PC lab, 2026-09-30)

Semua sudah diperbaiki di kode atau konfigurasi. Dicatat supaya tidak diulang saat memindah server.

| Gejala | Penyebab | Perbaikan |
|---|---|---|
| Container API terus restart, log kosong di awal | `alembic` tidak menemukan paket `server` (folder kerja tidak masuk `sys.path`). Uji pytest tidak menangkap karena pytest menambah path sendiri | `prepend_sys_path = %(here)s/..` dan `path_separator = os` di `server/alembic.ini`. Uji `test_migration_cli_runs_like_the_container` menjalankan perintah `alembic` persis seperti container |
| `RuntimeError: Missing dependencies: huggingface_hub, safetensors` | Kode MegaLoc di torch hub mensyaratkan keduanya. Di lingkungan spike keduanya dipasang manual, tidak pernah tercatat di `pyproject.toml` | Dideklarasikan di `pyproject.toml` dan `uv.lock` |
| (Tidak sempat terjadi) layanan macet menunggu jawaban y/N | `torch.hub.load` bawaan bertanya "percaya repo ini?" untuk MegaLoc | `server/localizer.py` menandai `gmberton_MegaLoc` tepercaya secara eksplisit |
| `files do not exist at "/maps/demo/kp1024-r1024/sfm"` | `EUTOPOS_MAPS_DIR` di `.env` masih contoh `/home/USER/...`. Bind bentuk pendek diam-diam membuat folder kosong milik root sebagai `/maps` | `compose.yaml` memakai bind panjang dengan `create_host_path: false` (compose menolak menyala). `server.manage register` dan `Localizer` memeriksa berkas peta lebih dulu dan menyebut berkas yang tidak ada |
| Build GPU gagal: `Failed to download nvidia-nvtx ... operation timed out` (2026-10-01) | Roda CUDA ±3 GB lewat jaringan lab. Batas baca uv 30 s dan puluhan unduhan paralel | `Dockerfile`: `UV_HTTP_TIMEOUT=300`, `UV_CONCURRENT_DOWNLOADS=4`, dan cache mount uv di setiap `uv pip install`, jadi build ulang melanjutkan unduhan yang sudah selesai |
| Pekerjaan gagal di tahap `build`: `unable to allocate shared memory(shm) ... No space left on device` (2026-10-01) | `DataLoader` PyTorch di hloc memakai `/dev/shm`, bawaannya hanya 64 MB di container | `shm_size: "2gb"` di layanan `worker` (`compose.yaml`) |

**Cara memeriksa isi yang terlihat dari dalam container** tanpa menjalankan layanan:

```bash
docker compose run --rm --no-deps --entrypoint ls api -la /maps
```

## 4. Antrean bangun peta (pekerja)

Pekerja (`worker`) mengambil pekerjaan dari tabel `map_job`, mengekstrak frame, membangun peta
dengan GPU (`run.py --seq 10`), membuat laporan dan tampilan 3D (`inspect_map.py`), lalu mendaftarkan
versi kandidat. Masukan berupa video atau folder frame di dalam `EUTOPOS_DATA_DIR`, terlihat sebagai
`/data` di container pekerja (perintah `job` dijalankan di `worker`, bukan `api`, karena hanya
pekerja yang memasang `/data`). Isi `EUTOPOS_DATA_DIR` di `deploy/.env` dulu (lihat `.env.example`).

```bash
mkdir -p ~/eutopos-data/work/inbox
cp -r /mnt/c/Users/<user>/eutopos-vps/data/floor10-v1 ~/eutopos-data/work/inbox/
docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
docker compose exec worker python -m server.manage job floor10 "Lantai 10" \
  --map /data/inbox/floor10-v1/mapping --query /data/inbox/floor10-v1/query
docker compose exec worker python -m server.manage jobs        # pantau status dan tahap
docker compose logs -f worker                                # log pekerja
docker compose exec api python -m server.manage publish <versi id>
docker compose restart api                                   # muat peta baru
```

Hasil per pekerjaan: peta di `/maps/<area>/job-<id>/` (berisi `report.html` tampilan 3D dan
`inspect.json`), log di `/data/jobs/<id>/log.txt`. Video di folder `uploads/` (unggahan website)
dihapus setelah diekstrak. Berkas yang diberikan lewat perintah di atas tidak pernah dihapus.

Kalau pekerja mati di tengah pekerjaan (misalnya `docker compose restart worker`), pekerjaan itu
ditandai `failed` saat pekerja menyala lagi. Antrekan ulang dengan perintah yang sama.

## 5. Unggahan video (tusd)

Unggahan memakai protokol tus lewat container `tusd`, dengan hook ke `api` yang memeriksa identitas
Cloudflare Access dan mencatat video ke pekerjaan. Tanpa `CF_ACCESS_TEAM_DOMAIN` dan `CF_ACCESS_AUD`,
`/api/*` dan unggahan menjawab 503, sedangkan `/localize` dan `/health` tetap jalan. Sebelum Tunnel
(PR 4) ada, uji dari dalam PC lab dengan `EUTOPOS_DEV_NO_AUTH=1` di `deploy/.env`, lalu kembalikan ke
`0`.

```bash
mkdir -p ~/eutopos-data/work/uploads
docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
docker compose exec worker python -m server.upload_client floor10 "Lantai 10" \
  peta:/data/inbox/floor10-20261001-loop/loop-inward.mp4
docker compose exec worker python -m server.manage jobs
```

Klien mengunggah dalam potongan 50 MiB, sama dengan dashboard nanti (batas Cloudflare Free 100 MB
per permintaan). Video unggahan dihapus pekerja setelah frame diekstrak. Pekerjaan `uploading` lebih
dari 24 jam ditandai gagal dan sisa unggahannya dihapus.
