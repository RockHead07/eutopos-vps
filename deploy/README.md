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
