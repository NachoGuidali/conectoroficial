# SPwap — Documentación de API para n8n

**Base URL:** `https://sociosras.supregsolutions.com`

---

## Índice

- [Autenticación](#autenticación)
- [Webhook entrante (trigger)](#webhook-entrante-trigger)
- [Enviar mensajes](#enviar-mensajes)
- [Guardar datos del contacto](#guardar-datos-del-contacto)
- [Activar / desactivar bot](#activar--desactivar-bot)
- [Handoff bot → agente](#handoff-bot--agente)
- [Flujo típico en n8n](#flujo-típico-en-n8n)
- [Configuración en n8n](#configuración-en-n8n)
- [Errores comunes](#errores-comunes)

---

## Autenticación

Todos los endpoints de API requieren el header:

```
X-Api-Key: TU_CRM_API_KEY
Content-Type: application/json
```

El valor de `CRM_API_KEY` está configurado en el `.env` del servidor.  
Generarlo con: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`

---

## Webhook entrante (trigger)

Cuando llega un mensaje de WhatsApp, Meta lo manda al webhook del CRM
(`/whatsapp/webhook/`) y el CRM, si tiene `bot_n8n_activo`, lo reenvía a la URL configurada en
`N8N_WEBHOOK_URL`. Configurá esa URL en n8n como nodo **Webhook** de tipo trigger.

### URL del webhook
Es la URL de tu workflow de n8n (la que ponés en `N8N_WEBHOOK_URL` del `.env` del CRM), no una
URL de WhatsApp.

---

### Payload — Mensaje de texto entrante

```json
{
  "event": "message_received",
  "phone": "+5491122334455",
  "contact_name": "Juan García",
  "message": "Hola, necesito información",
  "message_type": "text",
  "message_id": "3AB0DF989633B9AF",
  "conversation_id": 42,
  "timestamp": "2026-06-04T10:30:00",
  "crm_reply_url": "https://sociosras.supregsolutions.com/whatsapp/api/enviar/",
  "crm_api_key": "TU_CRM_API_KEY"
}
```

### Payload — Imagen / audio / documento entrante

```json
{
  "event": "message_received",
  "phone": "+5491122334455",
  "contact_name": "Juan García",
  "message": "caption del archivo (si tiene)",
  "message_type": "image",
  "message_id": "3AB0DF989633B9AF",
  "conversation_id": 42,
  "timestamp": "2026-06-04T10:30:00",
  "crm_reply_url": "https://sociosras.supregsolutions.com/whatsapp/api/enviar/",
  "crm_api_key": "TU_CRM_API_KEY"
}
```

`message_type` puede ser: `text` | `image` | `audio` | `video` | `document` | `sticker`

### Campos importantes del payload

| Campo | Tipo | Descripción |
|---|---|---|
| `conversation_id` | number | ID de la conversación en el CRM — guardar para usar en handoff |
| `phone` | string | Teléfono con código de país |
| `contact_name` | string | Nombre del contacto si existe en la base |
| `message` | string | Texto del mensaje o caption del archivo |
| `message_type` | string | Tipo de mensaje |
| `crm_reply_url` | string | URL para responder (siempre `/whatsapp/api/enviar/`) |
| `crm_api_key` | string | La misma key del CRM, incluida para comodidad |

---

## Enviar mensajes

### Enviar texto
```
POST /whatsapp/api/enviar/
```

**Body:**
```json
{
  "phone": "+5491122334455",
  "message": "Hola, ¿cómo te puedo ayudar?"
}
```

**Respuesta exitosa:**
```json
{
  "ok": true,
  "message_id": "3AB0DF989633B9AF",
  "conversacion_id": 42
}
```

**Respuesta de error:**
```json
{
  "ok": false,
  "error": "descripción del error"
}
```

---

### Enviar imagen
```
POST /whatsapp/api/enviar/
```

```json
{
  "phone": "+5491122334455",
  "message": "Mirá esta imagen",
  "media_url": "https://ejemplo.com/imagen.jpg",
  "media_type": "image"
}
```

---

### Enviar documento / PDF
```
POST /whatsapp/api/enviar/
```

```json
{
  "phone": "+5491122334455",
  "message": "Adjunto tu presupuesto",
  "media_url": "https://ejemplo.com/presupuesto.pdf",
  "media_type": "document"
}
```

---

### Enviar audio
```
POST /whatsapp/api/enviar/
```

```json
{
  "phone": "+5491122334455",
  "media_url": "https://ejemplo.com/audio.mp3",
  "media_type": "audio"
}
```

---

### Enviar video
```
POST /whatsapp/api/enviar/
```

```json
{
  "phone": "+5491122334455",
  "message": "Mirá este video",
  "media_url": "https://ejemplo.com/video.mp4",
  "media_type": "video"
}
```

### Valores de `media_type`

| Valor | Descripción |
|---|---|
| `image` | Imagen (jpg, png, gif, webp) |
| `document` | Documento (pdf, docx, xlsx, etc.) |
| `audio` | Audio (mp3, ogg, wav) |
| `video` | Video (mp4, 3gp) |

---

## Guardar datos del contacto

Crea o actualiza la ficha del contacto en el CRM. Los campos extra se guardan como
campos personalizados visibles en la tarjeta del contacto. Si el campo no existe, se crea automáticamente.

```
POST /whatsapp/api/contacto/
```

**Body completo:**
```json
{
  "phone": "+5491163589975",
  "nombre": "Juan García",
  "email": "juan@mail.com",
  "notas": "Obra social: UP | Recibo sueldo: sí | Grupo familiar: Individual",
  "campos": {
    "localidad": "Canning",
    "origen": "whatsapp",
    "obra_social": "UP",
    "recibo_sueldo": "si",
    "grupo_familiar": "Individual",
    "edades": "29"
  }
}
```

**Campos del body:**

| Campo | Requerido | Descripción |
|---|---|---|
| `phone` | ✅ | Teléfono con código de país. También acepta `telefono` |
| `nombre` | ❌ | Nombre completo. También acepta `nombre_completo` |
| `email` | ❌ | Email del contacto |
| `notas` | ❌ | Notas visibles en la ficha del contacto |
| `campos` | ❌ | Objeto con campos extra (clave → valor). Se crean automáticamente si no existen |

**Respuesta exitosa:**
```json
{
  "ok": true,
  "contacto_id": 42,
  "created": true,
  "campos_guardados": ["localidad", "origen", "obra_social", "recibo_sueldo"]
}
```

`created: true` → contacto nuevo. `created: false` → contacto existente actualizado.

**Notas:**
- Si el contacto ya existe (mismo teléfono), se actualizan los campos provistos
- Los `campos` extras son visibles en la ficha del contacto dentro de SPwap
- La conversación de WhatsApp se vincula automáticamente al contacto si no lo estaba
- No es necesario llamar este endpoint antes de enviar mensajes — es complementario

---

## Activar / desactivar bot

Prender o apagar el bot n8n para una conversación.

```
POST /whatsapp/api/bot/
```

**Apagar bot** (agente toma la conversación):
```json
{"conversation_id": 42, "activo": false}
```

**Prender bot** (reactivar para esa conversación):
```json
{"conversation_id": 42, "activo": true}
```

> **Nota:** `/api/handoff/` hace lo mismo que apagar el bot pero además cambia el estado a "Pendiente de agente" y notifica al agente. Para un handoff completo usá `/api/handoff/`. Para simplemente apagar/prender el bot sin cambiar estado, usá `/api/bot/`.

### Notificación CRM → n8n al reactivar el bot desde el chat

Cuando el **asesor** reactiva el bot n8n manualmente desde la conversación (botón en el chat, no vía `/api/bot/`), el CRM llama automáticamente a:

```
POST https://n8n.supregsolutions.com/webhook/liberar-asesor
Content-Type: application/json

{ "phone": "5491130125525" }
```

Esto le avisa a n8n que el asesor liberó la conversación para que el bot retome la atención de ese número. La URL se configura con la variable de entorno `N8N_LIBERAR_ASESOR_URL`.

---

## Handoff bot → agente

Llamar cuando el bot termina la atención y quiere que un agente humano tome la conversación.

```
POST /whatsapp/api/handoff/
```

**Por conversation_id (recomendado):**
```json
{
  "conversation_id": 42
}
```

**Por teléfono (alternativo):**
```json
{
  "phone": "+5491122334455"
}
```

**Respuesta exitosa:**
```json
{
  "ok": true,
  "conversation_id": 42,
  "estado": "pendiente"
}
```

**Respuesta si no se encuentra la conversación:**
```json
{
  "ok": false,
  "error": "Conversación no encontrada"
}
```

### Qué hace el handoff en el CRM

1. Desactiva el bot (`bot_n8n_activo = false`)
2. Cambia el estado de la conversación a **Pendiente de agente**
3. El agente asignado recibe una notificación en tiempo real con badge **LISTO** y sonido
4. La conversación sube al tope de la lista del agente
5. El título del tab del navegador parpadea con el nombre del contacto
6. Cuando el agente abre la conversación, el estado cambia a **Abierta**

---

## Flujo típico en n8n

```
┌─────────────────────────────────────────────────────┐
│  Webhook trigger                                     │
│  Recibe payload con conversation_id, phone, message  │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  Set node                                            │
│  Guardar: conversation_id, phone, contact_name       │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  Switch / IF                                         │
│  Según el contenido del mensaje, decidir qué hacer   │
└──────────┬──────────────────────┬───────────────────┘
           │                      │
           ▼                      ▼
    [Respuesta 1]           [Respuesta 2]
           │                      │
           └──────────┬───────────┘
                      ▼
┌─────────────────────────────────────────────────────┐
│  HTTP Request — Enviar mensaje                       │
│  POST /whatsapp/api/enviar/                          │
│  Body: { phone, message }                            │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  [Bot recopila datos del usuario]                    │
│  HTTP Request — Guardar contacto (opcional)          │
│  POST /whatsapp/api/contacto/                        │
│  Body: { phone, nombre, email, campos: {...} }       │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  [Cuando el bot termina]                             │
│  HTTP Request — Mensaje de cierre                    │
│  Body: { phone, message: "Un asesor te contacta..." }│
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  HTTP Request — Handoff                              │
│  POST /whatsapp/api/handoff/                         │
│  Body: { conversation_id }                           │
└─────────────────────────────────────────────────────┘
```

---

## Configuración en n8n

### Credencial reutilizable (recomendado)

Crear una credencial de tipo **Header Auth**:
- **Name:** `X-Api-Key`
- **Value:** `TU_CRM_API_KEY`

Usar esta credencial en todos los nodos HTTP Request que llamen al CRM.

### Nodo HTTP Request — configuración base

| Campo | Valor |
|---|---|
| Method | `POST` |
| URL | `https://sociosras.supregsolutions.com/whatsapp/api/enviar/` |
| Authentication | Header Auth → credencial creada arriba |
| Body Content Type | `JSON` |
| Send Body | ✅ |

### Webhook trigger — configuración

| Campo | Valor |
|---|---|
| HTTP Method | `POST` |
| Path | `/webhook-waply` (o el que elijas en n8n) |

> **Importante:** la URL que se registra en Meta for Developers (WhatsApp → Configuración →
> Webhook) es la del CRM (`/whatsapp/webhook/`), no la de n8n.
> El flujo es: `WhatsApp → Meta Cloud API → CRM → n8n`
> El CRM llama a n8n usando la `N8N_WEBHOOK_URL` del `.env`.

---

## Variables de entorno del CRM relacionadas

```env
# n8n
N8N_WEBHOOK_URL=https://tu-n8n.com/webhook/tu-trigger-id
N8N_LIBERAR_ASESOR_URL=https://tu-n8n.com/webhook/liberar-asesor

# Clave para que n8n llame al CRM
CRM_API_KEY=un-token-largo-y-secreto

# Verify Token del handshake del webhook con Meta
WHATSAPP_VERIFY_TOKEN=otro-token-secreto
```

---

## Errores comunes

| Error | Causa | Solución |
|---|---|---|
| `401 Unauthorized` | `X-Api-Key` incorrecto o faltante | Verificar que `CRM_API_KEY` en `.env` coincide con el header |
| `404 Not Found` | `conversation_id` no existe | Verificar que se guardó el ID del webhook inicial |
| `400 Bad Request` | JSON malformado o campo faltante | Verificar que `phone` tiene código de país (+549...) |
| `409 Conflict` | `ventana_24h_expirada` | La ventana de 24hs está cerrada; hay que usar una Plantilla aprobada |
| `500 Internal Server Error` | Error en la Cloud API de Meta | Verificar credenciales y estado del número en Configuración |

---

## Referencia rápida

```
# Enviar texto
POST /whatsapp/api/enviar/
{ "phone": "+549...", "message": "..." }

# Enviar archivo
POST /whatsapp/api/enviar/
{ "phone": "+549...", "message": "caption", "media_url": "https://...", "media_type": "document" }

# Guardar / actualizar contacto
POST /whatsapp/api/contacto/
{ "phone": "+549...", "nombre": "Juan", "email": "...", "notas": "...", "campos": { "localidad": "...", "origen": "whatsapp" } }

# Activar o desactivar bot
POST /whatsapp/api/bot/
{ "conversation_id": 42, "activo": false }

# Handoff al agente
POST /whatsapp/api/handoff/
{ "conversation_id": 42 }
```
