import csv
import io
import os
import re

from .models import Contacto, CampoPersonalizado, ValorCampo


def _slugify(text: str) -> str:
    return re.sub(r'[^\w]', '_', text.lower().strip())[:100] or 'campo'


def parse_file(file_obj, ext: str):
    """Parse uploaded file. Returns (headers, rows, error_str_or_None)."""
    if ext in ('xlsx', 'xls'):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
            ws = wb.active
            all_rows = list(ws.iter_rows(values_only=True))
        except Exception as e:
            return [], [], f'Error al leer Excel: {e}'
    elif ext == 'csv':
        try:
            content = file_obj.read()
            try:
                text = content.decode('utf-8-sig')
            except UnicodeDecodeError:
                text = content.decode('latin-1')
            reader = csv.reader(io.StringIO(text))
            all_rows = list(reader)
        except Exception as e:
            return [], [], f'Error al leer CSV: {e}'
    else:
        return [], [], 'Formato no soportado. Usá .xlsx o .csv'

    if not all_rows:
        return [], [], 'El archivo está vacío'

    headers = [str(h).strip() if h is not None else f'Col{i + 1}' for i, h in enumerate(all_rows[0])]
    rows = []
    for row in all_rows[1:]:
        cells = [str(c).strip() if c is not None else '' for c in row]
        while len(cells) < len(headers):
            cells.append('')
        if any(cells):
            rows.append(cells[:len(headers)])
    return headers, rows, None


def detect_tipo(values: list) -> str:
    BOOL_VALUES = {'true', 'false', 'si', 'sí', 'no', 'yes', '1', '0', 'verdadero', 'falso'}
    non_empty = [v.lower().strip() for v in values if v.strip()]
    if not non_empty:
        return 'text'
    if all(v in BOOL_VALUES for v in non_empty):
        return 'boolean'
    try:
        for v in non_empty:
            float(v.replace(',', '.'))
        return 'number'
    except ValueError:
        pass
    return 'text'


def auto_detect_mapping(headers: list) -> dict:
    """Returns {col_idx: role} where role ∈ nombre|telefono|email|grupo|notas|campo|ignorar."""
    NOMBRE = {'nombre', 'name', 'contacto', 'full name', 'fullname', 'apellido y nombre', 'client'}
    TELEFONO = {'telefono', 'teléfono', 'phone', 'tel', 'celular', 'móvil', 'movil', 'whatsapp', 'número', 'numero', 'cell'}
    EMAIL = {'email', 'correo', 'e-mail', 'mail', 'correo electronico', 'correo electrónico'}
    GRUPO = {'grupo', 'group', 'etiqueta', 'tag', 'categoria', 'categoría', 'lista', 'list', 'segmento'}
    NOTAS = {'notas', 'nota', 'notes', 'note', 'comentario', 'observacion', 'observación'}

    mapping = {}
    nombre_found = tel_found = False

    for i, h in enumerate(headers):
        hl = h.lower().strip()
        if not nombre_found and hl in NOMBRE:
            mapping[i] = 'nombre'
            nombre_found = True
        elif not tel_found and hl in TELEFONO:
            mapping[i] = 'telefono'
            tel_found = True
        elif hl in EMAIL:
            mapping[i] = 'email'
        elif hl in GRUPO:
            mapping[i] = 'grupo'
        elif hl in NOTAS:
            mapping[i] = 'notas'
        else:
            mapping[i] = 'campo'

    # Fallback: first unassigned → nombre, second → telefono
    assigned_roles = list(mapping.values())
    if 'nombre' not in assigned_roles:
        for i in range(len(headers)):
            if mapping.get(i) == 'campo':
                mapping[i] = 'nombre'
                break
    if 'telefono' not in mapping.values():
        for i in range(len(headers)):
            if mapping.get(i) == 'campo':
                mapping[i] = 'telefono'
                break

    return mapping


def normalizar_telefono(telefono: str, agregar_prefijo_ar: bool = True) -> str:
    """Normaliza teléfono al formato WhatsApp. Si agregar_prefijo_ar=True, añade +549 a números locales."""
    t = re.sub(r'[\s\-().]+', '', telefono.strip())
    if t.startswith('+'):
        return t
    if t.startswith('00'):
        return '+' + t[2:]
    t = re.sub(r'\D', '', t)
    if not t:
        return telefono
    # Ya tiene prefijo completo
    if t.startswith('549'):
        return '+' + t
    if t.startswith('54'):
        return '+' + t
    if not agregar_prefijo_ar:
        return '+' + t
    # Eliminar 0 inicial (formato local argentino: 011..., 0351...)
    if t.startswith('0'):
        t = t[1:]
    return '+549' + t


def import_from_rows(headers, rows, col_roles, col_tipos, update_existing=True, agregar_prefijo_ar=True):
    """
    col_roles: {str(col_idx): role}
    col_tipos: {str(col_idx): tipo}  (for role='campo')
    Returns: (created, updated, skipped, errors)
    """
    created = updated = skipped = 0
    errors = []

    # Resolve / create CampoPersonalizado for campo-role columns
    campo_map = {}  # col_idx (int) → CampoPersonalizado
    for idx_str, role in col_roles.items():
        if role != 'campo':
            continue
        col_idx = int(idx_str)
        if col_idx >= len(headers):
            continue
        header = headers[col_idx].strip()
        if not header:
            continue
        tipo = col_tipos.get(idx_str, 'text')
        nombre = _slugify(header)
        base = nombre
        counter = 1
        while True:
            campo, created_campo = CampoPersonalizado.objects.get_or_create(
                nombre=nombre,
                defaults={'etiqueta': header, 'tipo': tipo},
            )
            if created_campo or campo.etiqueta == header:
                break
            nombre = f'{base}_{counter}'
            counter += 1
        campo_map[col_idx] = campo

    def col_for_role(role):
        for idx_str, r in col_roles.items():
            if r == role:
                return int(idx_str)
        return None

    nombre_idx = col_for_role('nombre')
    tel_idx = col_for_role('telefono')

    if nombre_idx is None or tel_idx is None:
        return 0, 0, 0, ['Debés asignar las columnas Nombre y Teléfono.']

    email_idx = col_for_role('email')
    grupo_idx = col_for_role('grupo')
    notas_idx = col_for_role('notas')

    for row_num, row in enumerate(rows, start=2):
        try:
            nombre = row[nombre_idx] if nombre_idx < len(row) else ''
            telefono = row[tel_idx] if tel_idx < len(row) else ''

            if not nombre or not telefono:
                skipped += 1
                continue

            telefono = normalizar_telefono(telefono, agregar_prefijo_ar=agregar_prefijo_ar)

            defaults = {'nombre': nombre}
            if email_idx is not None and email_idx < len(row):
                defaults['email'] = row[email_idx]
            if grupo_idx is not None and grupo_idx < len(row):
                defaults['grupo'] = row[grupo_idx]
            if notas_idx is not None and notas_idx < len(row):
                defaults['notas'] = row[notas_idx]

            if update_existing:
                contacto, was_created = Contacto.objects.update_or_create(
                    telefono=telefono, defaults=defaults,
                )
            else:
                contacto, was_created = Contacto.objects.get_or_create(
                    telefono=telefono, defaults=defaults,
                )

            if was_created:
                created += 1
            else:
                updated += 1

            for col_idx, campo in campo_map.items():
                if col_idx < len(row) and row[col_idx]:
                    ValorCampo.objects.update_or_create(
                        contacto=contacto, campo=campo,
                        defaults={'valor': row[col_idx]},
                    )

            # Auto-link existing Conversacion with same phone
            try:
                from apps.whatsapp.models import Conversacion
                Conversacion.objects.filter(
                    telefono=telefono, contacto__isnull=True
                ).update(contacto=contacto, nombre_contacto=nombre)
            except Exception:
                pass

        except Exception as e:
            errors.append(f'Fila {row_num}: {e}')

    return created, updated, skipped, errors
