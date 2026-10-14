from datetime import date

import pytest

from nexo.academic.store import CampuslandTaskStore


def test_lists_uncompleted_tasks_due_within_window(tmp_path):
    store = CampuslandTaskStore(tmp_path / "campusland.db")
    try:
        store.add_task("Informe", "Bases de datos", "2026-10-02")
        store.add_task("Quiz", "Inglés", date(2026, 10, 5), status="in_progress")
        store.add_task("Entregado", "Backend", "2026-10-01", status="completed")

        due = store.list_due(within_days=3, today=date(2026, 10, 1))
    finally:
        store.close()

    assert [task["title"] for task in due] == ["Informe"]


def test_rejects_invalid_task_data(tmp_path):
    store = CampuslandTaskStore(tmp_path / "campusland.db")
    try:
        with pytest.raises(ValueError):
            store.add_task("", "Inglés", "2026-10-01")
        with pytest.raises(ValueError):
            store.add_task("Tarea", "Inglés", "no-es-fecha")
    finally:
        store.close()


def test_imports_csv_with_campusland_headers(tmp_path):
    source = tmp_path / "campusland.csv"
    source.write_text(
        "Tarea,Materia,Fecha límite,Estado\n"
        "Proyecto SQL,Bases de datos,10/10/2026,pendiente\n",
        encoding="utf-8",
    )
    store = CampuslandTaskStore(tmp_path / "tasks.db")
    try:
        imported = store.import_file(source)
        tasks = store.list_due(within_days=20, today=date(2026, 10, 1))
    finally:
        store.close()

    assert imported == 1
    assert tasks[0]["title"] == "Proyecto SQL"
    assert tasks[0]["due_date"] == "2026-10-10"
    assert tasks[0]["status"] == "pending"


def test_imports_json_and_rolls_back_invalid_batch(tmp_path):
    source = tmp_path / "moodle.json"
    source.write_text(
        '[{"title":"Quiz","subject":"Inglés","due_date":"2026-10-02"}]',
        encoding="utf-8",
    )
    store = CampuslandTaskStore(tmp_path / "tasks.db")
    try:
        assert store.import_file(source) == 1
        source.write_text(
            '[{"title":"Otra","subject":"SQL","due_date":"2026-10-03"},'
            '{"title":"Inválida","subject":"SQL","due_date":"mañana"}]',
            encoding="utf-8",
        )
        with pytest.raises(ValueError):
            store.import_file(source)
        assert store.count_tasks() == 1
    finally:
        store.close()


def test_parses_moodle_english_due_date_with_time():
    parsed = CampuslandTaskStore._parse_import_date("Friday, October 16, 2026, 11:59 PM")

    assert parsed == date(2026, 10, 16)