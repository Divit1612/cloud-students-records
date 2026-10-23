"""Student Record Management System - Flask application.

Run locally:   python app.py            (http://127.0.0.1:5000)
Production:    gunicorn app:app          (behind Nginx on EC2)
"""

import logging
import os
import re
import secrets

from flask import Flask, flash, redirect, render_template, request, url_for

from storage import StorageError, get_storage

try:  # optional: load .env during local development
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("student_app")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
MAX_LEN = {"name": 100, "email": 120, "course": 100}


def validate_form(form):
    """Return (clean_data, errors)."""
    data = {k: (form.get(k) or "").strip() for k in ("name", "email", "course")}
    errors = []
    for field, label in (("name", "Name"), ("email", "Email"), ("course", "Course")):
        if not data[field]:
            errors.append(f"{label} is required.")
        elif len(data[field]) > MAX_LEN[field]:
            errors.append(f"{label} must be at most {MAX_LEN[field]} characters.")
    if data["email"] and not EMAIL_RE.match(data["email"]):
        errors.append("Please enter a valid email address.")
    if data["email"]:
        data["email"] = data["email"].lower()
    return data, errors


def create_app(config=None):
    app = Flask(__name__)
    # SECRET_KEY signs flash-message cookies. Not an AWS secret; if unset a
    # random one is generated per process (fine for a single-instance demo).
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

    storage = get_storage(config)
    app.config["STORAGE"] = storage
    logger.info("Using storage backend: %s", storage.describe())

    def valid_id(student_id):
        return bool(UUID_RE.match(student_id or ""))

    @app.get("/")
    def index():
        students, edit_student = [], None
        try:
            students = storage.list_students()
            edit_id = request.args.get("edit")
            if edit_id:
                if valid_id(edit_id):
                    edit_student = storage.get_student(edit_id)
                if not edit_student:
                    flash("Student record not found.", "error")
        except StorageError as exc:
            flash(str(exc) + " Please try again later.", "error")
        return render_template(
            "index.html",
            students=students,
            edit_student=edit_student,
            form_data={},
            backend=storage.describe().split(" ")[0],
        )

    @app.post("/students")
    def add_student():
        data, errors = validate_form(request.form)
        if errors:
            for e in errors:
                flash(e, "error")
            try:
                students = storage.list_students()
            except StorageError:
                students = []
            return render_template(
                "index.html", students=students, edit_student=None,
                form_data=data, backend=storage.describe().split(" ")[0],
            ), 400
        try:
            student = storage.create_student(**data)
            flash(f"Student '{student['name']}' added successfully.", "success")
        except StorageError as exc:
            flash(str(exc), "error")
        return redirect(url_for("index"))

    @app.post("/students/<student_id>/update")
    def update_student(student_id):
        if not valid_id(student_id):
            flash("Invalid student ID.", "error")
            return redirect(url_for("index"))
        data, errors = validate_form(request.form)
        if errors:
            for e in errors:
                flash(e, "error")
            return redirect(url_for("index", edit=student_id))
        try:
            if storage.update_student(student_id, **data):
                flash(f"Student '{data['name']}' updated successfully.", "success")
            else:
                flash("Student record not found.", "error")
        except StorageError as exc:
            flash(str(exc), "error")
        return redirect(url_for("index"))

    @app.post("/students/<student_id>/delete")
    def delete_student(student_id):
        if not valid_id(student_id):
            flash("Invalid student ID.", "error")
            return redirect(url_for("index"))
        try:
            if storage.delete_student(student_id):
                flash("Student record deleted.", "success")
            else:
                flash("Student record not found.", "error")
        except StorageError as exc:
            flash(str(exc), "error")
        return redirect(url_for("index"))

    @app.get("/health")
    def health():
        return {"status": "ok"}, 200

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404,
                               message="The page you requested was not found."), 404

    @app.errorhandler(405)
    def method_not_allowed(_e):
        return render_template("error.html", code=405,
                               message="That action is not allowed."), 405

    @app.errorhandler(413)
    def too_large(_e):
        return render_template("error.html", code=413,
                               message="The submitted form is too large."), 413

    @app.errorhandler(Exception)
    def unhandled(e):
        from werkzeug.exceptions import HTTPException

        if isinstance(e, HTTPException):
            return e
        logger.exception("Unhandled application error")
        return render_template("error.html", code=500,
                               message="Something went wrong. Please try again later."), 500

    return app


app = create_app()

if __name__ == "__main__":
    # Local development only. Debug mode is never enabled here.
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)
