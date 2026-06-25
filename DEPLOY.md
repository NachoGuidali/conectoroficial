# Guía de despliegue — ConectorWP

**Dominio:** `sociosras.supregsolutions.com`

## Tabla de contenidos

- [Stack y puertos](#stack-y-puertos)
- [Parte 1 — Local (desarrollo)](#parte-1--local-desarrollo)
- [Parte 2 — Producción en servidor](#parte-2--producción-en-servidor)
- [Variables de entorno](#variables-de-entorno--referencia-completa)
- [Comandos útiles](#comandos-útiles)
- [Solución de problemas](#solución-de-problemas)

---

## Stack y puertos

| Servicio | Puerto interno (Docker) | Puerto host (producción) | Expuesto al host |
|---|---|---|---|
| web (Django + Gunicorn) | 8000 | **8005** | Solo `127.0.0.1` → Nginx |
| db (PostgreSQL 15) | 5432 | — | ❌ No expuesto |
| redis (Redis 7) | 6379 | — | ❌ No expuesto |
| celery / celery-beat | — | — | ❌ No aplica |

> WhatsApp se conecta vía la **Cloud API oficial de Meta** (Graph API externa) — no hay
> gateway propio que levantar ni exponer.

> DB y Redis no se exponen al host — solo se comunican dentro de la red Docker interna.  
> Nginx en el host actúa de único punto de entrada por el dominio.

---

## Parte 1 — Local (desarrollo)

### Requisitos previos

- Docker Desktop (Mac/Windows) o Docker Engine + Docker Compose v2 (Linux)
- Git

```bash
docker --version        # Docker version 24+
docker compose version  # Docker Compose version v2+
```

### 1. Clonar el repositorio

```bash
git clone <url-del-repo> sociosras
cd sociosras
```

### 2. Crear el archivo `.env`

```bash
cp .env.example .env
```

Para desarrollo local, editá estas líneas en `.env`:

```env
DEBUG=True
ALLOWED_HOSTS=*
```

El resto puede quedar igual que el ejemplo.

### 3. Levantar los servicios

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```

Primera vez tarda 2-3 minutos mientras baja imágenes y construye la app.

```bash
docker compose ps   # verificar que todo esté Up
```

### 4. Migraciones y superusuario

```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

### 5. Abrir la app

- **App:** http://localhost:8000
- **Admin:** http://localhost:8000/admin

### 6. Conectar WhatsApp (Cloud API de Meta)

1. Conseguí en [developers.facebook.com](https://developers.facebook.com/) el `Phone Number ID`,
   el `WABA ID`, un Access Token permanente y el App Secret (ver README para el detalle).
2. Ir a **Configuración** (ícono de engranaje) y completar esos datos + un Verify Token propio.
3. Exponé el puerto local con `ngrok http 8000` (Meta solo manda webhooks a HTTPS público).
4. En Meta for Developers → WhatsApp → Configuración → Webhook, pegá la URL de ngrok
   (`https://xxxx.ngrok.app/whatsapp/webhook/`) y el Verify Token, y suscribite al campo `messages`.

### 7. Detener / reiniciar

```bash
docker compose down                                                   # detiene (preserva datos)
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d   # levanta
docker compose logs -f web                                            # logs en vivo
```

---

## Parte 2 — Producción en servidor

### Requisitos del servidor

- **OS:** Ubuntu 22.04 LTS o Debian 12
- **RAM:** mínimo 2 GB (recomendado 4 GB)
- **Disco:** 20 GB mínimo
- **Red:** IP pública + dominio `sociosras.supregsolutions.com` apuntando al servidor

### 1. Preparar el servidor

```bash
apt update && apt upgrade -y
apt install -y git curl ufw

# Firewall
ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw --force enable
```

### 2. Instalar Docker

```bash
curl -fsSL https://get.docker.com | sh
usermod -aG docker $USER
# Cerrar y volver a abrir la sesión SSH, luego:
docker --version
docker compose version
```

### 3. Instalar Nginx y Certbot

```bash
apt install -y nginx certbot python3-certbot-nginx
systemctl enable nginx
systemctl start nginx
```

### 4. Clonar el proyecto

```bash
cd /opt
git clone <url-del-repo> sociosras
cd sociosras
```

### 5. Configurar el `.env` de producción

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Completar con valores reales:

```env
# Generá la clave con: python3 -c "import secrets; print(secrets.token_urlsafe(50))"
SECRET_KEY=<clave-larga-aleatoria>

DEBUG=False
ALLOWED_HOSTS=sociosras.supregsolutions.com,www.sociosras.supregsolutions.com

POSTGRES_DB=waply
POSTGRES_USER=waply
POSTGRES_PASSWORD=<contraseña-segura>
POSTGRES_HOST=db
POSTGRES_PORT=5432

REDIS_URL=redis://redis:6379/0

META_ACCESS_TOKEN=<access-token-permanente-de-meta>
META_PHONE_NUMBER_ID=<phone-number-id>
META_WABA_ID=<whatsapp-business-account-id>
META_APP_SECRET=<app-secret>
META_API_VERSION=v21.0

WHATSAPP_VERIFY_TOKEN=<token-secreto>
PUBLIC_URL=https://sociosras.supregsolutions.com
```

### 6. Levantar servicios con el override de producción

El archivo `docker-compose.prod.yml` ya está incluido en el repositorio con el puerto correcto (`8005`),
distinto al del otro proyecto (`ras.supregsolutions.com`, que sigue usando `8004` con Evolution API).

```bash
cd /opt/sociosras

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Verificar
docker compose ps
```

### 7. Migraciones y superusuario

```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

### 8. Configurar Nginx

```bash
nano /etc/nginx/sites-available/sociosras
```

Pegá esta configuración:

```nginx
server {
    listen 80;
    server_name sociosras.supregsolutions.com;

    # Para que Certbot pueda validar el dominio
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    # Redirigir todo lo demás a HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name sociosras.supregsolutions.com;

    # Certbot agrega las líneas ssl_certificate aquí automáticamente

    client_max_body_size 20M;

    location /static/ {
        alias /opt/sociosras/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /opt/sociosras/media/;
        expires 7d;
    }

    location / {
        proxy_pass         http://127.0.0.1:8005;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_connect_timeout 10s;
    }

    # SSE — sin buffering para que los eventos lleguen instantáneamente
    location /whatsapp/api/inbox/sse/ {
        proxy_pass         http://127.0.0.1:8005;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_buffering    off;
        proxy_cache        off;
        proxy_set_header   Connection        '';
        proxy_http_version 1.1;
        chunked_transfer_encoding on;
    }
}
```

Activar y verificar:

```bash
ln -s /etc/nginx/sites-available/sociosras /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

### 9. Obtener certificado SSL

```bash
certbot --nginx -d sociosras.supregsolutions.com
```

Certbot modifica Nginx automáticamente para agregar los certificados y la redirección HTTP→HTTPS.

Verificar renovación automática:

```bash
certbot renew --dry-run
```

### 10. Registrar el webhook de WhatsApp

1. Entrar a `https://sociosras.supregsolutions.com` con el superusuario
2. Ir a **Configuración** (ícono de engranaje en la barra lateral)
3. Completar `META_ACCESS_TOKEN`, `META_PHONE_NUMBER_ID`, `META_WABA_ID`, `META_APP_SECRET` y un
   Verify Token propio (mismo valor que `WHATSAPP_VERIFY_TOKEN`)
4. Guardar
5. En Meta for Developers → tu app → WhatsApp → Configuración → Webhook, pegá
   `https://sociosras.supregsolutions.com/whatsapp/webhook/` y el Verify Token, y suscribite al
   campo `messages`. Meta hace un GET de verificación que la app responde automáticamente.

### 11. Verificar que todo funciona

```bash
# Estado de servicios
docker compose ps

# Logs en vivo
docker compose logs -f web celery

# Probar que el webhook responde
curl -s -o /dev/null -w "%{http_code}" https://sociosras.supregsolutions.com/whatsapp/webhook/
# Debe devolver: 200

# Probar la app
curl -sI https://sociosras.supregsolutions.com/
# Debe devolver: HTTP/2 302 (redirige a login)
```

---

## Resumen de puertos — convivencia con otro proyecto en el servidor

```
Internet
    │
    ▼
Nginx :80 / :443
    │
    ├── crm.supregsolutions.com        → 127.0.0.1:8000   (CRM existente)
    ├── ras.supregsolutions.com        → 127.0.0.1:8004   (conector viejo, Evolution API)
    └── sociosras.supregsolutions.com  → 127.0.0.1:8005   (este proyecto, Meta Cloud API)

Carpetas separadas en el servidor:
  /opt/crm           → red Docker "crm_default"
  /opt/conectorwpp   → red Docker "conectorwpp_default"   (proyecto viejo, ras.supregsolutions.com)
  /opt/sociosras     → red Docker "sociosras_default"     (este proyecto, sociosras.supregsolutions.com)
```

Cada proyecto vive en su propia carpeta, con su propio `docker-compose` y su propia red Docker
interna — los puertos internos (`:8000`, `:5432`, `:6379`) se repiten sin problema porque no se
pisan entre redes; lo único que tiene que ser único por proyecto es el puerto que cada uno expone
al host (`127.0.0.1:8000`, `:8004`, `:8005`).

---

## Variables de entorno — referencia completa

| Variable | Descripción | Valor en producción |
|---|---|---|
| `SECRET_KEY` | Clave secreta Django | Cadena aleatoria 50+ chars |
| `DEBUG` | Modo debug | `False` |
| `ALLOWED_HOSTS` | Dominios permitidos | `sociosras.supregsolutions.com` |
| `POSTGRES_DB` | Nombre de la DB | `waply` |
| `POSTGRES_USER` | Usuario PostgreSQL | `waply` |
| `POSTGRES_PASSWORD` | Contraseña PostgreSQL | Contraseña segura |
| `POSTGRES_HOST` | Host DB (servicio Docker) | `db` |
| `POSTGRES_PORT` | Puerto PostgreSQL | `5432` |
| `REDIS_URL` | URL Redis | `redis://redis:6379/0` |
| `WHATSAPP_PROVIDER` | Proveedor activo de WhatsApp | `meta` o `twilio` |
| `META_ACCESS_TOKEN` | Token de acceso permanente de Meta | Cadena larga (System User) |
| `META_PHONE_NUMBER_ID` | ID del número en Meta | Numérico |
| `META_WABA_ID` | ID de la WhatsApp Business Account | Numérico |
| `META_APP_SECRET` | App Secret (firma del webhook) | Cadena de Meta |
| `META_API_VERSION` | Versión de la Graph API | `v21.0` |
| `WHATSAPP_VERIFY_TOKEN` | Verify Token del handshake del webhook | Cadena aleatoria |
| `TWILIO_ACCOUNT_SID` | Account SID de Twilio (si `WHATSAPP_PROVIDER=twilio`) | `AC...` |
| `TWILIO_AUTH_TOKEN` | Auth Token de Twilio (también valida el webhook) | Cadena de Twilio |
| `TWILIO_WHATSAPP_FROM` | Número de WhatsApp en Twilio | E.164 (`+1...`) |
| `PUBLIC_URL` | URL pública del servidor | `https://sociosras.supregsolutions.com` |
| `N8N_WEBHOOK_URL` | URL n8n (opcional) | `https://...` |
| `CRM_API_KEY` | API key para n8n (opcional) | Cadena aleatoria |

---

## Comandos útiles

```bash
# ── Servicios ──────────────────────────────────────────────────────────────
docker compose ps
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose down
docker compose restart web
docker compose logs -f web celery

# ── Migraciones ────────────────────────────────────────────────────────────
docker compose exec web python manage.py migrate
docker compose exec web python manage.py showmigrations

# ── Usuarios ───────────────────────────────────────────────────────────────
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py changepassword <username>

# ── Shell / debug ──────────────────────────────────────────────────────────
docker compose exec web python manage.py shell
docker compose exec db  psql -U waply waply

# ── Backup de base de datos ────────────────────────────────────────────────
docker compose exec db pg_dump -U waply waply > backup_$(date +%Y%m%d_%H%M).sql

# Restaurar
docker compose exec -T db psql -U waply waply < backup_20240601_1200.sql

# ── Actualizar el código ───────────────────────────────────────────────────
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build web celery celery-beat
docker compose exec web python manage.py migrate
docker compose logs --tail=30 web
```

---

## Solución de problemas

### Error 502 Bad Gateway desde Nginx

```bash
# 1. Verificar que el contenedor web corre
docker compose ps

# 2. Ver el error exacto
docker compose logs --tail=50 web

# 3. Verificar que Gunicorn escucha en el puerto 8005 del host
ss -tlnp | grep 8005
```

### Webhook no recibe mensajes

```bash
# Verificar el handshake de verificación (debe devolver "123")
curl "https://sociosras.supregsolutions.com/whatsapp/webhook/?hub.mode=subscribe&hub.verify_token=TU_VERIFY_TOKEN&hub.challenge=123"

# Ver logs del webhook
docker compose logs web | grep -i webhook
```

Si Meta marca el webhook como no verificado, revisá que `WHATSAPP_VERIFY_TOKEN` (o el campo
"Verify Token" en `/whatsapp/config/`) sea exactamente el mismo que pegaste en Meta for
Developers.

### La app corre pero ALLOWED_HOSTS da error 400

```bash
# Verificar el .env
grep ALLOWED_HOSTS /opt/sociosras/.env
# Debe tener: ALLOWED_HOSTS=sociosras.supregsolutions.com

# Reiniciar la app para que tome el cambio
docker compose restart web
```

### Celery no procesa tareas

```bash
docker compose logs --tail=50 celery
docker compose restart celery
```

### Importar archivo grande falla (413 Request Entity Too Large)

```bash
# Editar Nginx
nano /etc/nginx/sites-available/sociosras
# Cambiar: client_max_body_size 20M;  →  client_max_body_size 50M;

nginx -t && systemctl reload nginx
```
