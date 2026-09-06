"""Preset service templates for supply onboarding."""

from __future__ import annotations

SERVICE_TEMPLATES: tuple[dict, ...] = (
    {
        "id": "dj-standard",
        "category_code": "dj",
        "title": "DJ-сет",
        "description": "Музыкальное сопровождение мероприятия, базовый райдер в Deal Room.",
    },
    {
        "id": "host-wedding",
        "category_code": "host",
        "title": "Ведущий",
        "description": "Сценарий, интерактив с гостями, координация тайминга.",
    },
    {
        "id": "photo-report",
        "category_code": "photo",
        "title": "Фотоотчёт",
        "description": "Репортажная съёмка, срок передачи материалов — в оффере.",
    },
    {
        "id": "decor-basic",
        "category_code": "decor",
        "title": "Декор зоны",
        "description": "Оформление ключевой зоны, монтаж по согласованному ТЗ.",
    },
    {
        "id": "venue-rent",
        "category_code": "venue",
        "title": "Аренда зала",
        "description": "Площадка с базовой инфраструктурой, детали — в каталоге залов.",
    },
)


def get_template(template_id: str) -> dict | None:
    for row in SERVICE_TEMPLATES:
        if row["id"] == template_id:
            return row
    return None
