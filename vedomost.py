"""Формирование ведомости учёта пеленгаторов в Word."""

from io import BytesIO
from datetime import datetime

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

import storage

_NA = "н/д"
_FONT = "Times New Roman"
_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
_BLACK = RGBColor(0x00, 0x00, 0x00)
_HEADER_FILL = "000000"
_BORDER = "000000"

_LOCATION_ALIASES = {
    "лаба": "Лаборатория",
    "лаборатория": "Лаборатория",
}

_KIND_WORDS = {
    "hardware": "железо",
    "soft": "софт",
}

_FLAG_SPEC = [
    (
        "Связь: LoRa / Ethernet / LTE",
        ("comm_lora", "comm_ethernet", "comm_lte"),
    ),
    (
        "Модули: камера / акселерометр",
        ("module_camera", "module_accelerometer"),
    ),
    (
        "Питание: 5 В / 220 В / оптоволокно",
        ("power_5v", "power_220v", "power_fiber"),
    ),
]

_DEVICE_COLUMNS = [
    ("№", 18),
    ("Место", 20),
    ("Бронь / ответственное лицо", 26),
    ("Дата проверки", 20),
    ("Проверяющий (ФИО)", 22),
    ("Ош.", 9),
    ("Между микр.", 15),
    ("Между осями", 15),
    ("Вычислитель", 18),
    ("Агрегатор", 16),
    ("Микр., шт.", 12),
    ("Носитель", 14),
    ("ОС", 16),
    ("LoRa / Eth / LTE", 18),
    ("Кам. / акс.", 13),
    ("5 В / 220 В / оптика", 20),
]


def export_vedomost() -> tuple[BytesIO, str]:
    """Один вход из основного кода: снимок БД и готовый .docx."""
    snapshot = storage.get_vedomost_snapshot()
    return build_document(snapshot)


def build_document(snapshot: dict) -> tuple[BytesIO, str]:
    generated = _parse_when(snapshot.get("generated_at"))
    document = Document()
    _setup_page(document)

    _add_title(document, "ВЕДОМОСТЬ УЧЁТА ПЕЛЕНГАТОРОВ")
    _add_subtitle(
        document,
        "Состав оборудования по сериям и партиям · по состоянию на "
        + generated.strftime("%d.%m.%Y"),
    )
    _add_heading(document, "Легенда серий и общий учёт")
    types = list(snapshot.get("types") or [])
    _add_legend(document, types)

    total = sum(len(item.get("devices") or []) for item in types)
    empty_codes = [
        f"{item['id']:02d}"
        for item in types
        if not item.get("devices")
    ]
    note = f"Всего учтено: {total} {_devices_word(total)}."
    if empty_codes:
        note += f" Серии {', '.join(empty_codes)} в актуальном перечне отсутствуют."
    note += (
        " Обозначения: «н/д» — сведения отсутствуют; "
        "«0» в графе замечаний — активных ошибок нет. "
        "ФИО проверяющего в базе не хранится."
    )
    _add_body(document, note)

    for item in types:
        devices = list(item.get("devices") or [])
        if not devices:
            continue
        _add_series(document, item, devices)

    _add_body(
        document,
        "Основание: актуальные записи базы данных PelengatorsMonitor. "
        "Архивные устройства в ведомость не включены.",
        italic=True,
        size=12,
    )

    buffer = BytesIO()
    document.save(buffer)
    buffer.seek(0)
    filename = f"vedomost_{generated.strftime('%Y-%m-%d')}.docx"
    return buffer, filename


def _setup_page(document: Document) -> None:
    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width = Mm(297)
    section.page_height = Mm(210)
    section.left_margin = Mm(12)
    section.right_margin = Mm(12)
    section.top_margin = Mm(12)
    section.bottom_margin = Mm(12)


def _add_title(document: Document, text: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_spacing(paragraph, after=40)
    run = paragraph.add_run(text)
    _style_run(run, size=22, bold=True, color=_BLACK)


def _add_subtitle(document: Document, text: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_spacing(paragraph, after=160)
    run = paragraph.add_run(text)
    _style_run(run, size=14, color=_BLACK)


def _add_heading(document: Document, text: str, *, size: int = 16) -> None:
    paragraph = document.add_paragraph()
    _set_spacing(paragraph, before=160, after=80)
    run = paragraph.add_run(text)
    _style_run(run, size=size, bold=True, color=_BLACK)


def _add_body(
    document: Document,
    text: str,
    *,
    italic: bool = False,
    size: int = 13,
) -> None:
    paragraph = document.add_paragraph()
    _set_spacing(paragraph, after=80)
    run = paragraph.add_run(text)
    _style_run(run, size=size, italic=italic, color=_BLACK)


def _add_legend(document: Document, types: list[dict]) -> None:
    table = document.add_table(rows=1 + len(types), cols=3)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ("Код серии", "Полное наименование", "Учтено, шт.")
    widths = (28, 170, 28)
    _set_table_widths(table, widths)
    for index, title in enumerate(headers):
        _fill_cell(
            table.cell(0, index),
            title,
            bold=True,
            fill=_HEADER_FILL,
            color=_WHITE,
            size=12,
        )
    for row_index, item in enumerate(types, start=1):
        count = len(item.get("devices") or [])
        _fill_cell(table.cell(row_index, 0), f"{item['id']:02d}", center=True, size=12)
        _fill_cell(table.cell(row_index, 1), item.get("name") or _NA, size=12)
        _fill_cell(table.cell(row_index, 2), str(count), center=True, size=12)


def _add_series(document: Document, item: dict, devices: list[dict]) -> None:
    code = f"{item['id']:02d}"
    _add_heading(document, f"СЕРИЯ {code} — {item.get('name') or 'без названия'}", size=18)
    _add_heading(document, "Технические характеристики серии", size=14)
    spec, source_number = _series_spec(item, devices)
    if source_number:
        _add_body(
            document,
            f"Ниже приведены известные параметры устройства № {source_number}. "
            "Подтверждение применимости ко всей серии требуется.",
            italic=True,
            size=12,
        )
    elif _spec_empty(spec):
        _add_body(
            document,
            "Типовые технические характеристики серии не предоставлены.",
            italic=True,
            size=12,
        )
    _add_spec_table(document, spec, empty=_spec_empty(spec) and not source_number)

    batches: dict[str, list[dict]] = {}
    batch_order: list[str] = []
    for device in devices:
        batch = str(device.get("batch") or "")
        if batch not in batches:
            batches[batch] = []
            batch_order.append(batch)
        batches[batch].append(device)
    for batch in batch_order:
        title = (
            f"Партия {batch}"
            if batch
            else "Партия Не установлена (старая нумерация)"
        )
        _add_heading(document, title, size=14)
        _add_body(document, "Таблица устройств и фактических характеристик", size=13)
        _add_device_table(document, batches[batch])
        _add_batch_notes(document, batches[batch])


def _add_spec_table(document: Document, values: dict, *, empty: bool = False) -> None:
    rows: list[tuple[str, str]] = []
    for field, label in storage.TEXT_FIELDS.items():
        rows.append((label, _text_value(values.get(field))))
    for label, keys in _FLAG_SPEC:
        rows.append((label, _NA if empty else _flags_value(values, keys)))
    table = document.add_table(rows=1 + len(rows), cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    _set_table_widths(table, (90, 136))
    _fill_cell(
        table.cell(0, 0),
        "Характеристика",
        bold=True,
        fill=_HEADER_FILL,
        color=_WHITE,
        size=12,
    )
    _fill_cell(
        table.cell(0, 1),
        "Значение",
        bold=True,
        fill=_HEADER_FILL,
        color=_WHITE,
        size=12,
    )
    for index, (label, value) in enumerate(rows, start=1):
        _fill_cell(table.cell(index, 0), label, size=12)
        _fill_cell(table.cell(index, 1), value, size=12)


def _add_device_table(document: Document, devices: list[dict]) -> None:
    cols = len(_DEVICE_COLUMNS)
    table = document.add_table(rows=1 + len(devices), cols=cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_widths(table, [width for _title, width in _DEVICE_COLUMNS])
    for index, (title, _width) in enumerate(_DEVICE_COLUMNS):
        _fill_cell(
            table.cell(0, index),
            title,
            bold=True,
            fill=_HEADER_FILL,
            color=_WHITE,
            size=10,
            center=True,
        )
    for row_index, device in enumerate(devices, start=1):
        values = list(_device_row(device))
        for col, value in enumerate(values):
            _fill_cell(
                table.cell(row_index, col),
                value,
                size=10,
                center=col not in (1, 2, 4, 8, 9, 11, 12),
            )


def _add_batch_notes(document: Document, devices: list[dict]) -> None:
    notes: list[str] = []
    for device in devices:
        errors = list(device.get("errors") or [])
        if not errors:
            continue
        number = device.get("number") or str(device.get("id"))
        lines = [
            f"Устройство № {number}: зарегистрировано замечаний — {len(errors)}."
        ]
        for error in errors:
            lines.append("• " + _error_line(error))
        notes.append("\n".join(lines))
    if not notes:
        return
    _add_heading(document, "Примечания к партии", size=14)
    for note in notes:
        for line in note.split("\n"):
            paragraph = document.add_paragraph()
            _set_spacing(paragraph, after=40)
            run = paragraph.add_run(line)
            _style_run(run, size=12, color=_BLACK)


def _device_row(device: dict) -> tuple[str, ...]:
    values = device.get("values") or {}
    errors = device.get("errors") or []
    empty = _spec_empty(values)
    check_time = storage.format_check_time(
        device.get("insp_finished_at") or device.get("insp_started_at")
    )
    if check_time == "—":
        check_time = _NA
    return (
        str(device.get("number") or device.get("id") or _NA),
        _location_value(device.get("location")),
        _booking_value(device.get("reserved")),
        check_time,
        _NA,
        str(len(errors)),
        _text_value(values.get("mic_distance")),
        _text_value(values.get("axis_distance")),
        _text_value(values.get("computer")),
        _text_value(values.get("aggregator")),
        _text_value(values.get("mic_count")),
        _text_value(values.get("mic_carrier")),
        _text_value(values.get("os")),
        _NA if empty else _flags_value(values, ("comm_lora", "comm_ethernet", "comm_lte")),
        _NA if empty else _flags_value(values, ("module_camera", "module_accelerometer")),
        _NA if empty else _flags_value(values, ("power_5v", "power_220v", "power_fiber")),
    )


def _series_spec(item: dict, devices: list[dict]) -> tuple[dict, str]:
    values = dict(item.get("values") or {})
    if not _spec_empty(values):
        return values, ""
    for device in devices:
        candidate = dict(device.get("values") or {})
        if not _spec_empty(candidate):
            return candidate, str(device.get("number") or device.get("id") or "")
    return values, ""


def _spec_empty(values: dict) -> bool:
    for field in storage.TEXT_FIELDS:
        if str(values.get(field) or "").strip():
            return False
    return not any(bool(values.get(field)) for field in storage.FLAG_FIELDS)


def _text_value(raw) -> str:
    text = " ".join(str(raw or "").split())
    return text or _NA


def _booking_value(raw) -> str:
    text = " ".join(str(raw or "").split())
    return text or "Свободен"


def _location_value(raw) -> str:
    text = " ".join(str(raw or "").split())
    if not text:
        return _NA
    return _LOCATION_ALIASES.get(text.casefold(), text)


def _flags_value(values: dict, keys: tuple[str, ...]) -> str:
    return " / ".join("Да" if values.get(key) else "Нет" for key in keys)


def _error_line(error: dict) -> str:
    kind = error.get("kind") or "soft"
    if kind == "hardware":
        class_label = storage.HW_CLASS_LABELS.get(error.get("hw_class") or "")
        part_label = storage.HW_PART_LABELS.get(error.get("hw_part") or "")
    else:
        class_label = storage.SW_CLASS_LABELS.get(error.get("hw_class") or "")
        part_label = storage.SW_PART_LABELS.get(error.get("hw_part") or "")
    parts = [_KIND_WORDS.get(kind, kind)]
    if class_label:
        parts.append(class_label)
    if part_label:
        parts.append(part_label)
    priority = storage.PRIORITY_LABELS.get(
        error.get("priority") or storage.DEFAULT_PRIORITY,
        error.get("priority") or "",
    )
    if priority:
        parts.append(priority)
    description = " ".join(str(error.get("description") or "").split()) or "текст не указан"
    return " · ".join(parts) + ": " + description


def _devices_word(count: int) -> str:
    value = abs(count) % 100
    if 11 <= value <= 14:
        return "устройств"
    last = value % 10
    if last == 1:
        return "устройство"
    if 2 <= last <= 4:
        return "устройства"
    return "устройств"


def _parse_when(raw) -> datetime:
    text = str(raw or "").strip()
    if text:
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            pass
    return datetime.now()


def _style_run(
    run,
    *,
    size: int,
    bold: bool = False,
    italic: bool = False,
    color: RGBColor | None = None,
) -> None:
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(size)
    run.font.name = _FONT
    run.font.color.rgb = color or _BLACK
    r_pr = run._element.get_or_add_rPr()
    r_fonts = r_pr.find(qn("w:rFonts"))
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.append(r_fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        r_fonts.set(qn(attr), _FONT)


def _set_spacing(paragraph, *, before: int = 0, after: int = 0) -> None:
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(before / 20)
    fmt.space_after = Pt(after / 20)
    fmt.line_spacing_rule = WD_LINE_SPACING.SINGLE
    fmt.line_spacing = 1.0


def _fill_cell(
    cell,
    text: str,
    *,
    bold: bool = False,
    fill: str | None = None,
    color: RGBColor | None = None,
    size: int = 12,
    center: bool = False,
) -> None:
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    _set_cell_margins(cell)
    _set_cell_borders(cell)
    if fill:
        _shade_cell(cell, fill)
    paragraph = cell.paragraphs[0]
    paragraph.alignment = (
        WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT
    )
    _set_spacing(paragraph)
    for extra in paragraph.runs:
        extra.text = ""
    run = paragraph.add_run(text)
    _style_run(run, size=size, bold=bold, color=color)


def _shade_cell(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)


def _set_cell_margins(cell) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.find(qn("w:tcMar"))
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for name, value in (("top", 40), ("left", 60), ("bottom", 40), ("right", 60)):
        node = tc_mar.find(qn(f"w:{name}"))
        if node is None:
            node = OxmlElement(f"w:{name}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def _set_cell_borders(cell) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_borders = tc_pr.find(qn("w:tcBorders"))
    if tc_borders is None:
        tc_borders = OxmlElement("w:tcBorders")
        tc_pr.append(tc_borders)
    for edge in ("top", "left", "bottom", "right"):
        node = tc_borders.find(qn(f"w:{edge}"))
        if node is None:
            node = OxmlElement(f"w:{edge}")
            tc_borders.append(node)
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), "4")
        node.set(qn("w:space"), "0")
        node.set(qn("w:color"), _BORDER)


def _set_table_widths(table, widths_mm: tuple[int, ...] | list[int]) -> None:
    table.autofit = False
    table.allow_autofit = False
    total = int(sum(widths_mm) * 56.7)
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(total))
    tbl_w.set(qn("w:type"), "dxa")
    grid = tbl.find(qn("w:tblGrid"))
    if grid is not None:
        cols = grid.findall(qn("w:gridCol"))
        for col, width in zip(cols, widths_mm):
            col.set(qn("w:w"), str(int(width * 56.7)))
    for row in table.rows:
        for cell, width in zip(row.cells, widths_mm):
            cell.width = Mm(width)
        tr = row._tr
        tr_pr = tr.get_or_add_trPr()
        if tr_pr.find(qn("w:cantSplit")) is None:
            tr_pr.append(OxmlElement("w:cantSplit"))
    first = table.rows[0]._tr.get_or_add_trPr()
    if first.find(qn("w:tblHeader")) is None:
        first.append(OxmlElement("w:tblHeader"))
