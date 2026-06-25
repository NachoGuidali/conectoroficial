"""
Filter logic shared between Contactos (grupos) and Difusiones.

filtros dict structure:
{
    "fecha_creacion": "today" | "yesterday" | "last7" | "last30" | "month" | "",
    "grupo": "<group name or ''>",
    "campos": [
        {"campo_id": <int>, "operador": "<op>", "valor": "<str>"},
        ...
    ]
}

Operators by field type:
  boolean  → es_verdadero | es_falso | tiene_valor
  text     → igual_a | contiene | no_contiene | tiene_valor
  email    → igual_a | contiene | no_contiene | tiene_valor
  url      → contiene | no_contiene | tiene_valor
  number   → igual_a | mayor_que | menor_que | tiene_valor
  date     → igual_a | mayor_que | menor_que | tiene_valor
"""

from datetime import timedelta

from django.utils import timezone

TRUE_VALUES = {'true', '1', 'si', 'sí', 'yes', 'verdadero'}

OPERADORES_POR_TIPO = {
    'boolean': [
        ('es_verdadero', 'es Sí / Verdadero'),
        ('es_falso', 'es No / Falso'),
        ('tiene_valor', 'tiene cualquier valor'),
    ],
    'text': [
        ('igual_a', 'igual a'),
        ('contiene', 'contiene'),
        ('no_contiene', 'no contiene'),
        ('tiene_valor', 'tiene cualquier valor'),
    ],
    'email': [
        ('igual_a', 'igual a'),
        ('contiene', 'contiene'),
        ('tiene_valor', 'tiene cualquier valor'),
    ],
    'url': [
        ('contiene', 'contiene'),
        ('tiene_valor', 'tiene cualquier valor'),
    ],
    'number': [
        ('igual_a', 'igual a'),
        ('mayor_que', 'mayor que'),
        ('menor_que', 'menor que'),
        ('tiene_valor', 'tiene cualquier valor'),
    ],
    'date': [
        ('igual_a', 'igual a'),
        ('mayor_que', 'después de'),
        ('menor_que', 'antes de'),
        ('tiene_valor', 'tiene cualquier valor'),
    ],
}

FECHA_OPCIONES = [
    ('', 'Todos (sin filtro)'),
    ('today', 'Creados hoy'),
    ('yesterday', 'Creados ayer'),
    ('last7', 'Últimos 7 días'),
    ('last30', 'Últimos 30 días'),
    ('month', 'Este mes'),
]

SIN_VALOR_OPS = {'es_verdadero', 'es_falso', 'tiene_valor'}


def apply_filters(filtros: dict):
    """Apply filter criteria dict and return a Contacto queryset."""
    from .models import Contacto, ValorCampo

    qs = Contacto.objects.all()

    # ── Fecha de creación ──────────────────────────────────────────────
    fecha = filtros.get('fecha_creacion', '')
    now = timezone.now()
    today = now.date()
    if fecha == 'today':
        qs = qs.filter(created_at__date=today)
    elif fecha == 'yesterday':
        qs = qs.filter(created_at__date=today - timedelta(days=1))
    elif fecha == 'last7':
        qs = qs.filter(created_at__gte=now - timedelta(days=7))
    elif fecha == 'last30':
        qs = qs.filter(created_at__gte=now - timedelta(days=30))
    elif fecha == 'month':
        qs = qs.filter(created_at__year=today.year, created_at__month=today.month)

    # ── Grupo ──────────────────────────────────────────────────────────
    grupo = filtros.get('grupo', '').strip()
    if grupo:
        qs = qs.filter(grupo=grupo)

    # ── Campos personalizados ──────────────────────────────────────────
    for cf in filtros.get('campos', []):
        campo_id = cf.get('campo_id')
        operador = cf.get('operador', 'igual_a')
        valor = str(cf.get('valor', '')).strip()

        if not campo_id:
            continue
        try:
            campo_id = int(campo_id)
        except (ValueError, TypeError):
            continue

        if operador == 'es_verdadero':
            qs = qs.filter(valores__campo_id=campo_id, valores__valor__in=list(TRUE_VALUES))

        elif operador == 'es_falso':
            has_ids = list(qs.filter(valores__campo_id=campo_id).values_list('pk', flat=True))
            true_ids = list(qs.filter(
                valores__campo_id=campo_id, valores__valor__in=list(TRUE_VALUES),
            ).values_list('pk', flat=True))
            qs = qs.filter(pk__in=set(has_ids) - set(true_ids))

        elif operador == 'tiene_valor':
            qs = qs.filter(valores__campo_id=campo_id).exclude(valores__valor='')

        elif operador == 'igual_a' and valor:
            qs = qs.filter(valores__campo_id=campo_id, valores__valor__iexact=valor)

        elif operador == 'contiene' and valor:
            qs = qs.filter(valores__campo_id=campo_id, valores__valor__icontains=valor)

        elif operador == 'no_contiene' and valor:
            qs = qs.exclude(valores__campo_id=campo_id, valores__valor__icontains=valor)

        elif operador in ('mayor_que', 'menor_que') and valor:
            try:
                umbral = float(valor.replace(',', '.'))
            except ValueError:
                continue
            pares = ValorCampo.objects.filter(campo_id=campo_id).values_list('contacto_id', 'valor')
            ids_ok = []
            for cid, v in pares:
                try:
                    num = float(str(v).replace(',', '.'))
                    if (operador == 'mayor_que' and num > umbral) or \
                       (operador == 'menor_que' and num < umbral):
                        ids_ok.append(cid)
                except (ValueError, TypeError):
                    pass
            qs = qs.filter(pk__in=ids_ok)

    return qs.distinct()


def parse_filtros_from_post(post_data: dict) -> dict:
    """Extract filtros dict from POST form data."""
    filtros = {
        'fecha_creacion': post_data.get('filtro_fecha', '').strip(),
        'grupo': post_data.get('filtro_grupo', '').strip(),
        'campos': [],
    }
    i = 0
    while i <= 50:
        campo_id = post_data.get(f'filtro_campo_id_{i}', '').strip()
        if campo_id:
            try:
                filtros['campos'].append({
                    'campo_id': int(campo_id),
                    'operador': post_data.get(f'filtro_campo_op_{i}', 'igual_a').strip(),
                    'valor': post_data.get(f'filtro_campo_val_{i}', '').strip(),
                })
            except ValueError:
                pass
        i += 1
    return filtros


def parse_filtros_from_json(data: dict) -> dict:
    """Extract filtros dict from JSON body (AJAX preview)."""
    return {
        'fecha_creacion': str(data.get('fecha_creacion', '')).strip(),
        'grupo': str(data.get('grupo', '')).strip(),
        'campos': [
            {
                'campo_id': int(c.get('campo_id', 0)),
                'operador': str(c.get('operador', 'igual_a')),
                'valor': str(c.get('valor', '')),
            }
            for c in data.get('campos', [])
            if c.get('campo_id')
        ],
    }
