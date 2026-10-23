"""Tests using an isolated temporary SQLite database (no AWS needed)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from storage import SQLiteStorage, StorageError, get_storage  # noqa: E402


@pytest.fixture
def app(tmp_path):
    config = {"STORAGE_BACKEND": "sqlite", "SQLITE_PATH": str(tmp_path / "test.db")}
    application = create_app(config)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def storage(app):
    return app.config["STORAGE"]


def add(client, name="Asha Rao", email="asha@example.com", course="BSc IT"):
    return client.post("/students", data={"name": name, "email": email, "course": course},
                       follow_redirects=True)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_empty_state(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"No student records yet" in resp.data


def test_create_and_list(client, storage):
    resp = add(client)
    assert resp.status_code == 200
    assert b"added successfully" in resp.data
    assert b"Asha Rao" in resp.data
    students = storage.list_students()
    assert len(students) == 1
    assert len(students[0]["student_id"]) == 36
    assert students[0]["created_at"]


def test_create_invalid(client, storage):
    resp = client.post("/students", data={"name": "", "email": "bad", "course": ""})
    assert resp.status_code == 400
    assert b"Name is required" in resp.data
    assert b"valid email" in resp.data
    assert storage.list_students() == []


def test_update(client, storage):
    add(client)
    sid = storage.list_students()[0]["student_id"]
    edit_page = client.get(f"/?edit={sid}")
    assert b"Edit Student" in edit_page.data
    resp = client.post(f"/students/{sid}/update",
                       data={"name": "Asha R", "email": "a@example.com", "course": "MCA"},
                       follow_redirects=True)
    assert b"updated successfully" in resp.data
    s = storage.get_student(sid)
    assert (s["name"], s["email"], s["course"]) == ("Asha R", "a@example.com", "MCA")


def test_update_missing(client):
    resp = client.post("/students/00000000-0000-0000-0000-000000000000/update",
                       data={"name": "X", "email": "x@example.com", "course": "Y"},
                       follow_redirects=True)
    assert b"not found" in resp.data


def test_delete(client, storage):
    add(client)
    sid = storage.list_students()[0]["student_id"]
    resp = client.post(f"/students/{sid}/delete", follow_redirects=True)
    assert b"deleted" in resp.data
    assert storage.list_students() == []


def test_invalid_id_rejected(client):
    resp = client.post("/students/not-a-uuid/delete", follow_redirects=True)
    assert b"Invalid student ID" in resp.data


def test_get_not_allowed_on_delete(client):
    assert client.get("/students/abc/delete").status_code == 405


def test_404(client):
    resp = client.get("/does-not-exist")
    assert resp.status_code == 404
    assert b"Traceback" not in resp.data


def test_storage_crud_direct(tmp_path):
    s = SQLiteStorage(str(tmp_path / "d.db"))
    st = s.create_student("A", "a@b.co", "C")
    assert s.get_student(st["student_id"])["name"] == "A"
    assert s.update_student(st["student_id"], "B", "b@b.co", "D")
    assert s.delete_student(st["student_id"])
    assert s.get_student(st["student_id"]) is None


def test_unknown_backend():
    with pytest.raises(StorageError):
        get_storage({"STORAGE_BACKEND": "mongo"})
