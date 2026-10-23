"""Storage backends for the Student Record Management System.

Two explicit backends are supported:
    * SQLiteStorage   - local development (STORAGE_BACKEND=sqlite)
    * DynamoDBStorage - AWS deployment   (STORAGE_BACKEND=dynamodb)

The backend is chosen explicitly. There is NO silent fallback from
DynamoDB to SQLite: if DynamoDB fails, a StorageError is raised.
"""

import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class StorageError(Exception):
    """Raised when the storage backend cannot complete an operation."""


def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_student_id():
    return str(uuid.uuid4())


# --------------------------------------------------------------------------
# SQLite backend (local mode)
# --------------------------------------------------------------------------
class SQLiteStorage:
    def __init__(self, db_path):
        self.db_path = db_path
        directory = os.path.dirname(os.path.abspath(db_path))
        os.makedirs(directory, exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS students (
                    student_id TEXT PRIMARY KEY,
                    name       TEXT NOT NULL,
                    email      TEXT NOT NULL,
                    course     TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def describe(self):
        return f"SQLite ({os.path.basename(self.db_path)})"

    def create_student(self, name, email, course):
        student = {
            "student_id": new_student_id(),
            "name": name,
            "email": email,
            "course": course,
            "created_at": _now_iso(),
        }
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO students (student_id, name, email, course, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (student["student_id"], name, email, course, student["created_at"]),
                )
        except sqlite3.Error as exc:
            logger.exception("SQLite insert failed")
            raise StorageError("Could not save the student record.") from exc
        return student

    def get_student(self, student_id):
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM students WHERE student_id = ?", (student_id,)
                ).fetchone()
        except sqlite3.Error as exc:
            logger.exception("SQLite get failed")
            raise StorageError("Could not read the student record.") from exc
        return dict(row) if row else None

    def list_students(self):
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM students ORDER BY created_at DESC"
                ).fetchall()
        except sqlite3.Error as exc:
            logger.exception("SQLite list failed")
            raise StorageError("Could not load student records.") from exc
        return [dict(r) for r in rows]

    def update_student(self, student_id, name, email, course):
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE students SET name = ?, email = ?, course = ? "
                    "WHERE student_id = ?",
                    (name, email, course, student_id),
                )
                return cur.rowcount > 0
        except sqlite3.Error as exc:
            logger.exception("SQLite update failed")
            raise StorageError("Could not update the student record.") from exc

    def delete_student(self, student_id):
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "DELETE FROM students WHERE student_id = ?", (student_id,)
                )
                return cur.rowcount > 0
        except sqlite3.Error as exc:
            logger.exception("SQLite delete failed")
            raise StorageError("Could not delete the student record.") from exc


# --------------------------------------------------------------------------
# DynamoDB backend (AWS mode)
# --------------------------------------------------------------------------
class DynamoDBStorage:
    """DynamoDB table with partition key `student_id` (String).

    Credentials come from Boto3's default provider chain. On EC2 this is
    the attached IAM role (instance profile). No keys are stored in code.
    """

    def __init__(self, table_name, region):
        import boto3  # imported lazily so local mode needs no AWS setup
        from botocore.exceptions import BotoCoreError, ClientError

        self._errors = (BotoCoreError, ClientError)
        self._client_error = ClientError
        if not table_name:
            raise StorageError("DYNAMODB_TABLE_NAME is not set.")
        if not region:
            raise StorageError("AWS_DEFAULT_REGION / AWS_REGION is not set.")
        self.table_name = table_name
        self.region = region
        self.table = boto3.resource("dynamodb", region_name=region).Table(table_name)

    def describe(self):
        return f"DynamoDB ({self.table_name}, {self.region})"

    def check_table(self):
        """Call DescribeTable to confirm access (used on startup)."""
        try:
            self.table.load()
            return True
        except self._errors:
            logger.exception("DynamoDB DescribeTable failed for %s", self.table_name)
            return False

    def create_student(self, name, email, course):
        student = {
            "student_id": new_student_id(),
            "name": name,
            "email": email,
            "course": course,
            "created_at": _now_iso(),
        }
        try:
            self.table.put_item(
                Item=student,
                ConditionExpression="attribute_not_exists(student_id)",
            )
        except self._errors as exc:
            logger.exception("DynamoDB PutItem failed")
            raise StorageError("Could not save the student record.") from exc
        return student

    def get_student(self, student_id):
        try:
            resp = self.table.get_item(Key={"student_id": student_id})
        except self._errors as exc:
            logger.exception("DynamoDB GetItem failed")
            raise StorageError("Could not read the student record.") from exc
        return resp.get("Item")

    def list_students(self):
        items = []
        kwargs = {}
        try:
            while True:
                resp = self.table.scan(**kwargs)
                items.extend(resp.get("Items", []))
                if "LastEvaluatedKey" not in resp:
                    break
                kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        except self._errors as exc:
            logger.exception("DynamoDB Scan failed")
            raise StorageError("Could not load student records.") from exc
        items.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        return items

    def update_student(self, student_id, name, email, course):
        try:
            self.table.update_item(
                Key={"student_id": student_id},
                UpdateExpression="SET #n = :n, email = :e, course = :c",
                ConditionExpression="attribute_exists(student_id)",
                ExpressionAttributeNames={"#n": "name"},  # 'name' is reserved
                ExpressionAttributeValues={":n": name, ":e": email, ":c": course},
            )
            return True
        except self._client_error as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            logger.exception("DynamoDB UpdateItem failed")
            raise StorageError("Could not update the student record.") from exc
        except self._errors as exc:
            logger.exception("DynamoDB UpdateItem failed")
            raise StorageError("Could not update the student record.") from exc

    def delete_student(self, student_id):
        try:
            self.table.delete_item(
                Key={"student_id": student_id},
                ConditionExpression="attribute_exists(student_id)",
            )
            return True
        except self._client_error as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            logger.exception("DynamoDB DeleteItem failed")
            raise StorageError("Could not delete the student record.") from exc
        except self._errors as exc:
            logger.exception("DynamoDB DeleteItem failed")
            raise StorageError("Could not delete the student record.") from exc


# --------------------------------------------------------------------------
# Factory
# --------------------------------------------------------------------------
def get_storage(config=None):
    """Build the storage backend from a config dict (defaults to os.environ)."""
    config = config if config is not None else os.environ
    backend = (config.get("STORAGE_BACKEND") or "sqlite").strip().lower()

    if backend == "sqlite":
        path = config.get("SQLITE_PATH") or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), ".data", "students.db"
        )
        return SQLiteStorage(path)

    if backend == "dynamodb":
        region = config.get("AWS_DEFAULT_REGION") or config.get("AWS_REGION")
        storage = DynamoDBStorage(config.get("DYNAMODB_TABLE_NAME"), region)
        if not storage.check_table():
            logger.error(
                "Cannot access DynamoDB table '%s' in %s. Check the table name, "
                "region and the EC2 IAM role permissions. NOT falling back to SQLite.",
                storage.table_name, storage.region,
            )
        return storage

    raise StorageError(
        f"Unknown STORAGE_BACKEND '{backend}'. Use 'sqlite' or 'dynamodb'."
    )
