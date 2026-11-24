#!/usr/bin/env bash
# Despliegue en la EC2. Lo ejecuta GitHub Actions por SSH SOLO cuando las pruebas pasaron:
#   ssh ubuntu@EC2 "APP_SHA=<commit> bash -s" < scripts/deploy.sh
# Actualiza el código al commit probado, reconstruye y reinicia los contenedores de la app
# y verifica que el sistema responda.
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/inventrack}"
APP_SHA="${APP_SHA:?Falta APP_SHA}"
cd "$APP_DIR"

echo "==> Actualizando código a ${APP_SHA:0:7}"
git fetch --quiet origin
git checkout --quiet --force "$APP_SHA"

export APP_VERSION="${APP_SHA:0:7}"
export APP_ENV=production

echo "==> Construyendo y actualizando contenedores de la aplicación"
docker compose --env-file .env -f docker-compose.yml up -d --build --remove-orphans

echo "==> Asegurando que la observabilidad esté arriba"
docker compose --env-file .env -f docker-compose.observability.yml up -d

echo "==> Verificando salud"
for i in $(seq 1 40); do
  if curl -fsS http://localhost/api/health >/dev/null; then
    curl -fsS http://localhost/api/health; echo
    docker image prune -f >/dev/null
    echo "==> Despliegue de ${APP_VERSION} completado"
    exit 0
  fi
  sleep 3
done
echo "La aplicación no respondió después del despliegue" >&2
docker compose -f docker-compose.yml ps
docker compose -f docker-compose.yml logs --tail=80 api web
exit 1
