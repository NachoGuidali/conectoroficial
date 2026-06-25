# SPwap — Plataforma WhatsApp Multi-agente

Plataforma de WhatsApp tipo WATI, construida con Django + WhatsApp Cloud API (oficial de Meta).

## Stack

- **Backend:** Django 5.1 + Celery + Redis
- **DB:** PostgreSQL 15
- **WhatsApp:** WhatsApp Cloud API (Meta, oficial) o Twilio — proveedor intercambiable
- **Frontend:** Django Templates (sin frameworks JS)
- **Infra:** Docker + docker-compose

## Setup rápido

### 1. Crear la app de WhatsApp en Meta

1. Entrá a [developers.facebook.com](https://developers.facebook.com/) → crear una app tipo "Business".
2. Agregá el producto **WhatsApp** y, en "Configuración de la API", conseguí:
   - `Phone Number ID`
   - `WhatsApp Business Account ID` (WABA)
   - Un **Access Token permanente** (creá un System User en Business Manager y generale un token con permisos `whatsapp_business_messaging` y `whatsapp_business_management` — el token temporal de 24hs que aparece por defecto no sirve para producción).
3. En "Configuración → Básica" de la app, copiá el **App Secret**.

### 2. Clonar y configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con META_ACCESS_TOKEN, META_PHONE_NUMBER_ID, META_WABA_ID, META_APP_SECRET, etc.
```

### 3. Levantar servicios

```bash
docker-compose up --build
```

### 4. Crear superusuario (admin)

```bash
docker-compose exec web python manage.py createsuperuser
```

### 5. Configurar el webhook en Meta

1. Entrá a `/whatsapp/config/`, completá los datos de Meta y un **Verify Token** propio.
2. En Meta for Developers → WhatsApp → Configuración → Webhook, pegá la URL del webhook
   (`https://tu-dominio/whatsapp/webhook/`) y el mismo Verify Token. Meta hace un handshake GET
   que esta app responde automáticamente si el token coincide.
3. Suscribite al campo `messages`.

### 6. Acceder

- **App:** http://localhost:8000
- **Admin:** http://localhost:8000/admin

## Roles de usuario

| Rol | Permisos |
|---|---|
| `admin` | Todo, incluyendo gestión de usuarios |
| `supervisor` | Ve todas las conversaciones, puede reasignar agentes, configura WhatsApp Cloud API |
| `agente` | Solo sus conversaciones asignadas |

## Módulos

| Módulo | URL | Descripción |
|---|---|---|
| Inbox | `/whatsapp/inbox/` | Bandeja principal multi-agente |
| Plantillas | `/whatsapp/plantillas/` | Plantillas (HSM) aprobadas por Meta |
| Config | `/whatsapp/config/` | Credenciales de WhatsApp Cloud API |
| Usuarios | `/usuarios/` | ABM de usuarios y roles |

## Proveedores (Meta / Twilio)

El conector soporta dos proveedores de WhatsApp, intercambiables sin tocar código:

- **Meta Cloud API** (default, más barato): conexión directa con la Graph API.
- **Twilio** (intermediario / BSP): útil mientras se completa la verificación de Meta.

Se selecciona en **Configuración** (`/whatsapp/config/`) o con `WHATSAPP_PROVIDER` en el `.env`.
La app de Configuración muestra los campos del proveedor activo y la URL de webhook a pegar en cada
consola. Con Twilio, las Plantillas se crean en el *Content Template Builder* de Twilio y se vinculan
pegando su **ContentSid** (`HX…`) en la plantilla local. La ventana de 24hs y el bloqueo de envíos
libres fuera de ella aplican igual con ambos proveedores.

## Ventana de 24hs y Plantillas

Meta solo permite mensajes de **texto/media libres** dentro de las 24hs posteriores al último
mensaje del contacto. Fuera de esa ventana, **hay que usar una Plantilla (HSM) aprobada** por
Meta — el envío libre se rechaza.

- Las Plantillas se crean en `/whatsapp/plantillas/`. Podés enviarlas a revisión de Meta al
  crearlas, o crearlas directamente en Meta Business Manager y traerlas con el botón
  "Sincronizar desde Meta".
- El estado de aprobación (`local` / `PENDING` / `APPROVED` / `REJECTED`) se sincroniza
  automáticamente cada hora vía Celery, y se muestra en la lista de plantillas.
- Las Difusiones (`apps.difusiones`) que usan una Plantilla no aprobada se bloquean
  automáticamente; las que mandan texto libre solo llegan a contactos con la ventana de 24hs
  activa.

## API para n8n

```http
POST /whatsapp/api/enviar/
X-Api-Key: <CRM_API_KEY>
Content-Type: application/json

{"phone": "+5491112345678", "message": "Hola!"}
```

Si la ventana de 24hs está cerrada, esta API devuelve `409` con
`{"error": "ventana_24h_expirada"}` — hay que mandar una Plantilla en su lugar.

## Variables de entorno

| Variable | Descripción |
|---|---|
| `SECRET_KEY` | Clave secreta Django |
| `POSTGRES_*` | Credenciales PostgreSQL |
| `REDIS_URL` | URL de Redis |
| `WHATSAPP_PROVIDER` | Proveedor activo: `meta` (default) o `twilio` |
| `META_ACCESS_TOKEN` | Token de acceso permanente de Meta |
| `META_PHONE_NUMBER_ID` | ID del número de teléfono en Meta |
| `META_WABA_ID` | ID de la WhatsApp Business Account |
| `META_APP_SECRET` | App Secret, para verificar la firma del webhook |
| `META_API_VERSION` | Versión de la Graph API (default `v21.0`) |
| `WHATSAPP_VERIFY_TOKEN` | Verify Token del handshake del webhook |
| `TWILIO_ACCOUNT_SID` | Account SID de Twilio (solo si `WHATSAPP_PROVIDER=twilio`) |
| `TWILIO_AUTH_TOKEN` | Auth Token de Twilio; también valida la firma del webhook |
| `TWILIO_WHATSAPP_FROM` | Número de WhatsApp en Twilio, formato E.164 (ej. `+14155238886`) |
| `PUBLIC_URL` | URL pública del servidor (para que Meta descargue media saliente) |
| `N8N_WEBHOOK_URL` | URL de n8n (opcional) |
| `CRM_API_KEY` | API Key para envío externo desde n8n |
