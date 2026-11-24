#!/usr/bin/env bash
# Prepara una instancia EC2 nueva (Ubuntu 24.04) para InvenTrack. Se ejecuta UNA sola vez:
#
#   curl -fsSL https://raw.githubusercontent.com/<usuario>/<repo>/main/scripts/setup-ec2.sh -o setup-ec2.sh
#   REPO_URL=https://github.com/<usuario>/<repo>.git bash setup-ec2.sh
#
# Variables opcionales (si no se dan, se generan contraseñas aleatorias):
#   ADMIN_EMAIL, ADMIN_PASSWORD           -> usuario administrador de InvenTrack
#   O2_EMAIL, O2_PASSWORD                 -> usuario raíz de OpenObserve
set -euo pipefail

REPO_URL="${REPO_URL:?Define REPO_URL=https://github.com/<usuario>/<repo>.git}"
APP_DIR="$HOME/inventrack"
rand() { openssl rand -base64 64 | tr -dc 'A-Za-z0-9' | cut -c1-"${1:-20}"; }

echo "==> 1/6 Paquetes base y Docker"
sudo apt-get update -qq
sudo apt-get install -y -qq git curl ca-certificates python3 >/dev/null
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$USER"
sudo systemctl enable --now docker

echo "==> 2/6 Memoria swap de 2 GB (ayuda a construir las imágenes en instancias pequeñas)"
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "==> 3/6 Código"
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

echo "==> 4/6 Archivo .env (secretos del servidor; no se sube a GitHub)"
if [ ! -f .env ]; then
  ADMIN_EMAIL="${ADMIN_EMAIL:-admin@inventrack.com}"
  ADMIN_PASSWORD="${ADMIN_PASSWORD:-Inv$(rand 10)!}"
  O2_EMAIL="${O2_EMAIL:-admin@inventrack.com}"
  O2_PASSWORD="${O2_PASSWORD:-O2$(rand 12)!}"
  PUBLIC_IP="$(curl -fsS --max-time 3 https://checkip.amazonaws.com || hostname -I | awk '{print $1}')"
  cat > .env <<EOF
APP_ENV=production
POSTGRES_PASSWORD=$(rand 24)
JWT_SECRET=$(rand 48)
ADMIN_EMAIL=${ADMIN_EMAIL}
ADMIN_PASSWORD=${ADMIN_PASSWORD}
ZO_ROOT_USER_EMAIL=${O2_EMAIL}
ZO_ROOT_USER_PASSWORD=${O2_PASSWORD}
O2_AUTH=$(printf '%s:%s' "$O2_EMAIL" "$O2_PASSWORD" | base64 -w0)
HOST_NAME=inventrack-ec2
PUBLIC_IP=${PUBLIC_IP}
EOF
  chmod 600 .env
fi
set -a; . ./.env; set +a

echo "==> 5/6 Contenedores (observabilidad y aplicación)"
# La aplicación crea la red inventrack_net; la observabilidad se conecta a ella.
export APP_VERSION="$(git rev-parse --short HEAD)"
sudo -E docker compose -f docker-compose.yml up -d --build
sudo docker compose -f docker-compose.observability.yml up -d

echo "==> 6/6 Tableros y alertas de OpenObserve"
O2_URL=http://localhost:5080 O2_USER="$ZO_ROOT_USER_EMAIL" O2_PASSWORD="$ZO_ROOT_USER_PASSWORD" python3 scripts/o2_setup.py

for i in $(seq 1 40); do curl -fsS http://localhost/api/health >/dev/null && break; sleep 3; done

cat <<EOF

================================================================
 InvenTrack quedó instalado. GUARDA estos datos para el reporte:

 Sistema:      http://${PUBLIC_IP}
   usuario:    ${ADMIN_EMAIL}
   contraseña: ${ADMIN_PASSWORD}

 OpenObserve:  http://${PUBLIC_IP}:5080
   usuario:    ${ZO_ROOT_USER_EMAIL}
   contraseña: ${ZO_ROOT_USER_PASSWORD}

 Secrets para GitHub Actions:
   O2_URL       = http://${PUBLIC_IP}:5080
   O2_USER      = ${ZO_ROOT_USER_EMAIL}
   O2_PASSWORD  = ${ZO_ROOT_USER_PASSWORD}
   EC2_HOST     = ${PUBLIC_IP}
   EC2_USER     = ${USER}
   EC2_SSH_KEY  = (contenido completo de tu archivo .pem)

 (Los datos también están en ~/inventrack/.env)
 Cierra la sesión SSH y vuelve a entrar para usar docker sin sudo.
================================================================
EOF
