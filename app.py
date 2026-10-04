"""Boki.blog: a small multi-user blog.

Run it with:   flask --app app run
Full setup steps are in README.md.
"""
import json
import os
import re
import secrets
import sqlite3
import time
import uuid
import unicodedata
from datetime import datetime
from functools import wraps

import click
from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, send_from_directory, session, url_for)
from markupsafe import Markup, escape
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
UPLOAD_DIR = os.path.join(INSTANCE_DIR, "uploads")
os.makedirs(INSTANCE_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
DB_PATH = os.environ.get("BLOG_DB", os.path.join(INSTANCE_DIR, "blog.db"))

PER_PAGE = 10
MAX_IMAGE_BYTES = 5 * 1024 * 1024
UNLOCK_SECONDS = 30 * 60          # how long the signup page stays unlocked
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,24}$")
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
IMAGE_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
)


# ----------------------------------------------------------------------
# App setup
# ----------------------------------------------------------------------

def load_secret_key():
    """Load the cookie-signing key or create a persistent key outside the project."""
    key = os.environ.get("SECRET_KEY")
    if key is not None:
        if len(key.encode("utf-8")) < 32:
            raise RuntimeError("SECRET_KEY must be at least 32 bytes.")
        return key

    if os.name == "nt":
        config_dir = os.environ.get("LOCALAPPDATA")
        if not config_dir:
            config_dir = os.path.join(
                os.path.expanduser("~"), "AppData", "Local")
    else:
        config_dir = os.environ.get(
            "XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
    key_path = os.path.join(config_dir, "Boki.blog", "secret_key")
    os.makedirs(os.path.dirname(key_path), mode=0o700, exist_ok=True)

    try:
        with open(key_path, encoding="ascii") as key_file:
            key = key_file.read().strip()
    except FileNotFoundError:
        key = secrets.token_hex(32)
        try:
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            with open(key_path, encoding="ascii") as key_file:
                key = key_file.read().strip()
        else:
            with os.fdopen(fd, "w", encoding="ascii") as key_file:
                key_file.write(key)
                key_file.flush()
                os.fsync(key_file.fileno())

    if len(key.encode("utf-8")) < 32:
        raise RuntimeError(f"The signing key in {key_path} is invalid.")
    return key


app = Flask(__name__)
app.config.update(
    SECRET_KEY=load_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("BLOG_HTTPS") == "1",
    PERMANENT_SESSION_LIFETIME=14 * 24 * 3600,
    MAX_CONTENT_LENGTH=6 * 1024 * 1024,
    TEMPLATES_AUTO_RELOAD=True,
    SITE_NAME=os.environ.get("SITE_NAME", "Boki.blog"),
)


# ----------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    bio           TEXT NOT NULL DEFAULT '',
    avatar        TEXT,
    profile_bg    TEXT NOT NULL DEFAULT '#D9DD92',
    profile_text  TEXT NOT NULL DEFAULT '#2E2836'
);

CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT,
    image      TEXT,
    text_color TEXT NOT NULL DEFAULT '#2E2836',
    title_color TEXT NOT NULL DEFAULT '#2E2836',
    background_color TEXT NOT NULL DEFAULT '#D9DD92'
);
CREATE INDEX IF NOT EXISTS posts_created ON posts(created_at);
CREATE INDEX IF NOT EXISTS posts_user ON posts(user_id, created_at);

CREATE TABLE IF NOT EXISTS likes (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    post_id    INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, post_id)
);
CREATE INDEX IF NOT EXISTS likes_post_time ON likes(post_id, created_at);

CREATE TABLE IF NOT EXISTS comments (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    post_id    INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS comments_post_time ON comments(post_id, created_at);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS crossword_state (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    solution   TEXT NOT NULL,
    clues      TEXT NOT NULL,
    version    INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS crossword_completions (
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    puzzle_version INTEGER NOT NULL,
    guess        TEXT,
    completed_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, puzzle_version)
);
"""


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    conn.execute("DELETE FROM settings WHERE key = 'spotlight_user_id'")
    user_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    if "email" in user_columns:
        conn.execute("DROP INDEX IF EXISTS users_email_unique")
        conn.execute("ALTER TABLE users DROP COLUMN email")
    migrations = {
        "users": {
            "bio": "TEXT NOT NULL DEFAULT ''",
            "avatar": "TEXT",
            "avatar_position_x": "INTEGER NOT NULL DEFAULT 50",
            "avatar_position_y": "INTEGER NOT NULL DEFAULT 50",
            "profile_bg": "TEXT NOT NULL DEFAULT '#D9DD92'",
            "profile_text": "TEXT NOT NULL DEFAULT '#2E2836'",
        },
        "posts": {
            "image": "TEXT",
            "text_color": "TEXT NOT NULL DEFAULT '#2E2836'",
            "title_color": "TEXT NOT NULL DEFAULT '#2E2836'",
            "background_color": "TEXT NOT NULL DEFAULT '#D9DD92'",
        },
        "crossword_completions": {
            "guess": "TEXT",
        },
    }
    for table, columns in migrations.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column, definition in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    has_pw = conn.execute(
        "SELECT 1 FROM settings WHERE key = 'signup_password_hash'").fetchone()
    if not has_pw:
        password = os.environ.get("SIGNUP_PASSWORD")
        generated = password is None
        if generated:
            password = secrets.token_urlsafe(9)
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)",
                     ("signup_password_hash", generate_password_hash(password)))
        if generated:
            print("\n  Signup password (share it with people you invite):\n"
                  f"    {password}\n"
                  "  You can change it later on the Admin page.\n")
    conn.commit()
    conn.close()


init_db()


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def get_setting(key):
    row = db().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(key, value):
    db().execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    db().commit()


# ----------------------------------------------------------------------
# Post queries
# ----------------------------------------------------------------------

POST_COLS = """
    p.id, p.title, p.body, p.created_at, p.updated_at, p.user_id, u.username,
    EXISTS(
      SELECT 1 FROM crossword_completions c
      JOIN crossword_state s ON s.id = 1
      WHERE c.user_id = u.id AND c.puzzle_version = s.version
    ) AS crossword_star,
    u.avatar AS author_avatar, u.avatar_position_x AS author_avatar_x,
    u.avatar_position_y AS author_avatar_y, p.image, p.text_color, p.title_color,
    p.background_color,
    (SELECT COUNT(*) FROM likes l WHERE l.post_id = p.id) AS like_count,
    EXISTS(SELECT 1 FROM likes l WHERE l.post_id = p.id AND l.user_id = ?) AS liked
"""
POST_FROM = "FROM posts p JOIN users u ON u.id = p.user_id"
SORTS = {
    "new": "p.created_at DESC, p.id DESC",
    "liked": "like_count DESC, p.created_at DESC, p.id DESC",
}


def viewer_id():
    return g.user["id"] if g.user else -1


def get_crossword():
    row = db().execute(
        "SELECT solution, clues, version, updated_at FROM crossword_state WHERE id = 1"
    ).fetchone()
    if row is None or row["solution"] == "#" * 225:
        return None
    return {
        "solution": row["solution"],
        "clues": json.loads(row["clues"]),
        "version": row["version"],
        "updated_at": row["updated_at"],
    }


def crossword_entries(solution):
    across_entries = []
    down_entries = []
    covered = set()

    for row in range(15):
        for col in range(15):
            index = row * 15 + col
            if solution[index] == "#":
                continue
            across_start = col == 0 or solution[index - 1] == "#"
            if across_start:
                across_length = 0
                while (col + across_length < 15
                       and solution[index + across_length] != "#"):
                    across_length += 1
                if across_length >= 2:
                    covered.update(range(index, index + across_length))
                    across_entries.append({
                        "key": f"A-{row}-{col}", "direction": "across",
                        "number": len(across_entries) + 1, "row": row, "col": col,
                        "length": across_length,
                    })

    for col in range(15):
        for row in range(15):
            index = row * 15 + col
            if solution[index] == "#" or (row > 0 and solution[index - 15] != "#"):
                continue
            down_length = 0
            while (row + down_length < 15
                   and solution[index + down_length * 15] != "#"):
                down_length += 1
            if down_length >= 2:
                covered.update(index + length * 15 for length in range(down_length))
                down_entries.append({
                    "key": f"D-{row}-{col}", "direction": "down",
                    "number": len(down_entries) + 1, "row": row, "col": col,
                    "length": down_length,
                })

    active = {index for index, char in enumerate(solution) if char != "#"}
    if covered != active:
        return None
    return across_entries + down_entries


def normalize_crossword_text(text):
    uppercase = unicodedata.normalize("NFC", text).upper()
    return uppercase.replace("Ι\u0308\u0301", "Ϊ").replace("Υ\u0308\u0301", "Ϋ")


def validate_crossword(solution_text, clues_text):
    rows = [
        normalize_crossword_text(row)
        for row in solution_text.replace("\r", "").splitlines()
    ]
    if len(rows) != 15 or any(len(row) != 15 for row in rows):
        return None, None, "The crossword grid must have exactly 15 rows of 15 cells."
    solution = "".join(rows)
    if any(
        char != "#" and not (
            "A" <= char <= "Z"
            or "\u0391" <= char <= "\u03a9" and char.isalpha()
            or char in "\u0386\u0388\u0389\u038a\u038c\u038e\u038f\u03aa\u03ab"
        )
        for char in solution
    ):
        return None, None, "Fill every open square with a Latin or Greek letter; use # for blocked squares."
    entries = crossword_entries(solution)
    if not entries:
        return None, None, "Add at least one answer of two or more letters."
    try:
        clues = json.loads(clues_text)
    except (TypeError, json.JSONDecodeError):
        return None, None, "The clue data is invalid. Reload the admin page and try again."
    if not isinstance(clues, dict):
        return None, None, "The clue data is invalid."
    expected_keys = {entry["key"] for entry in entries}
    normalized_clues = {}
    for key in expected_keys:
        hint = clues.get(key)
        if not isinstance(hint, str) or not hint.strip() or len(hint.strip()) > 200:
            return None, None, "Provide a hint of at most 200 characters for every answer."
        normalized_clues[key] = hint.strip()
    if set(clues) != expected_keys:
        return None, None, "The grid changed; check the generated clues and try saving again."
    return solution, normalized_clues, None


def get_post(post_id):
    return db().execute(
        f"SELECT {POST_COLS} {POST_FROM} WHERE p.id = ?",
        (viewer_id(), post_id)).fetchone()


def fetch_posts(where="1 = 1", params=(), sort="new", page=1):
    total = db().execute(
        f"SELECT COUNT(*) {POST_FROM} WHERE {where}", params).fetchone()[0]
    pages = max(1, -(-total // PER_PAGE))
    page = min(max(page, 1), pages)
    rows = db().execute(
        f"SELECT {POST_COLS} {POST_FROM} WHERE {where} "
        f"ORDER BY {SORTS[sort]} LIMIT ? OFFSET ?",
        (viewer_id(), *params, PER_PAGE, (page - 1) * PER_PAGE)).fetchall()
    return rows, total, page, pages


def like_pattern(text):
    """Escape LIKE wildcards so searches match literally."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def normalize_color(value):
    value = value.strip()
    if re.fullmatch(r"[0-9A-Fa-f]{6}", value):
        value = "#" + value
    return value.upper() if HEX_COLOR_RE.fullmatch(value) else None


def normalize_avatar_position(value):
    try:
        position = int(value)
    except (TypeError, ValueError):
        return None
    return position if 0 <= position <= 100 else None


def read_uploaded_image(upload):
    if upload is None or not upload.filename:
        return None
    data = upload.stream.read(MAX_IMAGE_BYTES + 1)
    upload.stream.seek(0)
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Images must be 5 MB or smaller.")
    extension = None
    for signature, supported_extension in IMAGE_SIGNATURES:
        if data.startswith(signature):
            extension = supported_extension
            break
    if extension is None and len(data) >= 12 and data[:4] == b"RIFF" \
            and data[8:12] == b"WEBP":
        extension = "webp"
    if extension is None:
        raise ValueError("Upload a PNG, JPEG, GIF or WebP image.")
    return data, extension


def store_uploaded_image(image):
    if image is None:
        return None
    data, extension = image
    filename = f"{uuid.uuid4().hex}.{extension}"
    with open(os.path.join(UPLOAD_DIR, filename), "xb") as saved:
        saved.write(data)
    return filename


def remove_uploaded_image(filename):
    if filename:
        path = os.path.join(UPLOAD_DIR, os.path.basename(filename))
        if os.path.isfile(path):
            os.remove(path)


# ----------------------------------------------------------------------
# Request hooks, helpers, template filters
# ----------------------------------------------------------------------

@app.before_request
def load_user_and_check_csrf():
    g.user = None
    user_id = session.get("user_id")
    if user_id:
        g.user = db().execute(
            """SELECT u.id, u.username, u.is_admin,
                      EXISTS(
                        SELECT 1 FROM crossword_completions c
                        JOIN crossword_state s ON s.id = 1
                        WHERE c.user_id = u.id AND c.puzzle_version = s.version
                      ) AS crossword_star
               FROM users u WHERE u.id = ?""",
            (user_id,)).fetchone()
        if g.user is None:
            session.clear()
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    if request.method == "POST":
        sent = request.form.get("csrf_token", "")
        if not secrets.compare_digest(sent.encode(), session["csrf"].encode()):
            abort(400, "Your session expired. Go back, reload the page and try again.")


@app.after_request
def security_headers(resp):
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; img-src 'self' data:; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'self'")
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "same-origin"
    return resp


app.jinja_env.globals["csrf_token"] = lambda: session.get("csrf", "")


@app.context_processor
def inject_site():
    return {"site_name": app.config["SITE_NAME"]}


def parse_ts(value):
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


@app.template_filter("date")
def date_filter(value):
    dt = parse_ts(value)
    return f"{dt.day} {dt:%b %Y}"


@app.template_filter("iso")
def iso_filter(value):
    return parse_ts(value).strftime("%Y-%m-%d")


@app.template_filter("wordcount")
def wordcount_filter(text):
    return len(text.split())


@app.template_filter("readtime")
def readtime_filter(text):
    return wordcount_filter(text)


@app.template_filter("excerpt")
def excerpt_filter(text, length=190):
    flat = " ".join(text.split())
    if len(flat) <= length:
        return flat
    return flat[:length].rsplit(" ", 1)[0].rstrip(".,;:!? ") + "..."


@app.template_filter("paragraphs")
def paragraphs_filter(text):
    """Turn plain text into safe HTML paragraphs (all HTML is escaped)."""
    parts = re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip())
    html = "".join(
        "<p>%s</p>" % escape(part.strip()).replace("\n", Markup("<br>"))
        for part in parts if part.strip())
    return Markup(html)


def safe_next(target):
    """Only allow redirects to paths on this site."""
    if target and target.startswith("/") and not target.startswith("//") \
            and "\\" not in target:
        return target
    return None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Log in to continue.", "info")
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not g.user["is_admin"]:
            abort(403, "Only the site admin can do that.")
        return view(*args, **kwargs)
    return wrapped


_attempts = {}


def throttled(bucket, limit, window):
    """Return True when this client has made too many attempts recently."""
    now = time.time()
    key = (bucket, request.remote_addr)
    recent = [t for t in _attempts.get(key, []) if now - t < window]
    if len(recent) >= limit:
        _attempts[key] = recent
        return True
    recent.append(now)
    _attempts[key] = recent
    return False


def log_in(user_id):
    session.clear()
    session["user_id"] = user_id
    session["csrf"] = secrets.token_urlsafe(32)
    session.permanent = True


# ----------------------------------------------------------------------
# Public pages
# ----------------------------------------------------------------------

@app.get("/")
def home():
    top_week = db().execute(
        f"""SELECT * FROM (
                SELECT {POST_COLS},
                  (SELECT COUNT(*) FROM likes w
                    WHERE w.post_id = p.id
                      AND w.created_at >= datetime('now', '-7 days')) AS week_likes
                {POST_FROM})
            WHERE week_likes > 0
            ORDER BY week_likes DESC, like_count DESC, created_at DESC
            LIMIT 4""", (viewer_id(),)).fetchall()

    featured = None
    featured_id = get_setting("featured_post_id")
    if featured_id:
        featured = get_post(int(featured_id))

    latest_admin_post = db().execute(
        f"SELECT {POST_COLS} {POST_FROM} WHERE u.is_admin = 1 "
        "ORDER BY p.created_at DESC, p.id DESC LIMIT 1",
        (viewer_id(),)).fetchone()

    crossword = get_crossword()
    crossword_entries_list = []
    crossword_completed = False
    crossword_answers = ""
    if crossword:
        crossword_entries_list = crossword_entries(crossword["solution"]) or []
        if g.user:
            completion = db().execute(
                "SELECT guess FROM crossword_completions "
                "WHERE user_id = ? AND puzzle_version = ?",
                (g.user["id"], crossword["version"])).fetchone()
            crossword_completed = completion is not None
            if completion:
                crossword_answers = completion["guess"] or crossword["solution"]
    if crossword:
        for entry in crossword_entries_list:
            entry["hint"] = crossword["clues"].get(entry["key"], "")

    return render_template("home.html", top_week=top_week, featured=featured,
                           latest_admin_post=latest_admin_post,
                           crossword=crossword,
                           crossword_entries=crossword_entries_list,
                           crossword_completed=crossword_completed,
                           crossword_answers=crossword_answers)


@app.get("/explore")
def explore():
    q = request.args.get("q", "").strip()[:100]
    kind = request.args.get("type", "all")
    sort = request.args.get("sort", "new")
    if kind not in ("all", "posts", "users"):
        kind = "all"
    if sort not in SORTS:
        sort = "new"
    page = request.args.get("page", 1, type=int)

    users, posts, total, pages = [], [], 0, 1
    if q:
        pattern = like_pattern(q)
        if kind in ("all", "users"):
            users = db().execute(
                """SELECT u.username, u.created_at,
                          EXISTS(
                            SELECT 1 FROM crossword_completions c
                            JOIN crossword_state s ON s.id = 1
                            WHERE c.user_id = u.id AND c.puzzle_version = s.version
                          ) AS crossword_star,
                          (SELECT COUNT(*) FROM posts WHERE user_id = u.id) AS post_count
                   FROM users u WHERE u.username LIKE ? ESCAPE '\\'
                   ORDER BY u.username LIMIT 20""", (pattern,)).fetchall()
        if kind in ("all", "posts"):
            posts, total, page, pages = fetch_posts(
                "(p.title LIKE ? ESCAPE '\\' OR p.body LIKE ? ESCAPE '\\' "
                "OR u.username LIKE ? ESCAPE '\\')",
                (pattern, pattern, pattern), sort, page)
    else:
        # Show users when search is empty
        if kind in ("all", "users"):
            users = db().execute(
                """SELECT u.username, u.created_at,
                          EXISTS(
                            SELECT 1 FROM crossword_completions c
                            JOIN crossword_state s ON s.id = 1
                            WHERE c.user_id = u.id AND c.puzzle_version = s.version
                          ) AS crossword_star,
                          (SELECT COUNT(*) FROM posts WHERE user_id = u.id) AS post_count
                   FROM users u
                   ORDER BY u.username LIMIT 20""").fetchall()
        if kind in ("all", "posts"):
            posts, total, page, pages = fetch_posts(sort=sort, page=page)

    return render_template("explore.html", q=q, kind=kind, sort=sort, users=users,
                           posts=posts, total=total, page=page, pages=pages)


@app.get("/post/<int:post_id>")
def post(post_id):
    row = get_post(post_id)
    if row is None:
        abort(404)
    is_featured = get_setting("featured_post_id") == str(post_id)
    comments = db().execute(
        """SELECT c.id, c.body, c.created_at, u.username, u.avatar,
                  u.avatar_position_x, u.avatar_position_y,
                  EXISTS(
                    SELECT 1 FROM crossword_completions x
                    JOIN crossword_state s ON s.id = 1
                    WHERE x.user_id = u.id AND x.puzzle_version = s.version
                  ) AS crossword_star
           FROM comments c JOIN users u ON u.id = c.user_id
           WHERE c.post_id = ? ORDER BY c.created_at, c.id""", (post_id,)).fetchall()
    return render_template("post.html", post=row, is_featured=is_featured,
                           comments=comments)


@app.get("/u/<username>")
def profile(username):
    user = db().execute(
        """SELECT u.id, u.username, u.created_at, u.bio, u.avatar,
                  u.avatar_position_x, u.avatar_position_y, u.profile_bg, u.profile_text,
                  EXISTS(
                    SELECT 1 FROM crossword_completions c
                    JOIN crossword_state s ON s.id = 1
                    WHERE c.user_id = u.id AND c.puzzle_version = s.version
                  ) AS crossword_star
           FROM users u WHERE u.username = ?""",
        (username,)).fetchone()
    if user is None:
        abort(404)
    page = request.args.get("page", 1, type=int)
    posts, total, page, pages = fetch_posts("p.user_id = ?", (user["id"],), "new", page)
    total_likes = db().execute(
        "SELECT COUNT(*) FROM likes l JOIN posts p ON p.id = l.post_id "
        "WHERE p.user_id = ?", (user["id"],)).fetchone()[0]
    return render_template("profile.html", profile_user=user, posts=posts,
                           total=total, total_likes=total_likes, page=page, pages=pages)


@app.get("/uploads/<path:filename>")
def uploaded_file(filename):
    if os.path.basename(filename) != filename:
        abort(404)
    return send_from_directory(UPLOAD_DIR, filename)


# ----------------------------------------------------------------------
# Writing and liking posts
# ----------------------------------------------------------------------

def validate_post_form():
    title = request.form.get("title", "").strip()
    body = request.form.get("body", "").strip()
    text_color = normalize_color(request.form.get("text_color", ""))
    title_color = normalize_color(request.form.get("title_color", ""))
    background_color = normalize_color(request.form.get("background_color", ""))
    errors = []
    if not title:
        errors.append("Give your post a title.")
    elif len(title) > 120:
        errors.append("The title can be at most 120 characters.")
    if not body:
        errors.append("The post body cannot be empty.")
    elif len(body) > 20000:
        errors.append("The post body can be at most 20,000 characters.")
    if text_color is None:
        errors.append("Enter a valid body text color in #RRGGBB format.")
    if title_color is None:
        errors.append("Enter a valid title color in #RRGGBB format.")
    if background_color is None:
        errors.append("Enter a valid background color in #RRGGBB format.")
    try:
        image = read_uploaded_image(request.files.get("image"))
    except ValueError as exc:
        errors.append(str(exc))
        image = None
    return title, body, text_color, title_color, background_color, image, errors


@app.route("/new", methods=["GET", "POST"])
@login_required
def new_post():
    if request.method == "POST":
        title, body, text_color, title_color, background_color, image_data, errors = validate_post_form()
        if not errors:
            image = store_uploaded_image(image_data)
            cur = db().execute(
                "INSERT INTO posts (user_id, title, body, image, text_color, title_color, "
                "background_color) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (g.user["id"], title, body, image, text_color, title_color, background_color))
            db().commit()
            flash("Post published.", "ok")
            return redirect(url_for("post", post_id=cur.lastrowid))
        for e in errors:
            flash(e, "error")
        return render_template("post_form.html", mode="new", title=title, body=body,
                               text_color=text_color or "#2E2836",
                               title_color=title_color or "#2E2836",
                               background_color=background_color or "#D9DD92",
                               post=None)
    return render_template("post_form.html", mode="new", title="", body="",
                           text_color="#2E2836", title_color="#2E2836",
                           background_color="#D9DD92", post=None)


@app.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def edit_post(post_id):
    row = get_post(post_id)
    if row is None:
        abort(404)
    if row["user_id"] != g.user["id"]:
        abort(403, "You can only edit your own posts.")
    if request.method == "POST":
        title, body, text_color, title_color, background_color, image_data, errors = validate_post_form()
        if not errors:
            old_image = row["image"]
            image = old_image
            if image_data:
                image = store_uploaded_image(image_data)
            elif request.form.get("remove_image") == "1":
                image = None
            db().execute(
                "UPDATE posts SET title = ?, body = ?, image = ?, text_color = ?, "
                "title_color = ?, background_color = ?, updated_at = datetime('now') "
                "WHERE id = ?",
                (title, body, image, text_color, title_color, background_color, post_id))
            db().commit()
            if image != old_image:
                remove_uploaded_image(old_image)
            flash("Changes saved.", "ok")
            return redirect(url_for("post", post_id=post_id))
        for e in errors:
            flash(e, "error")
        return render_template("post_form.html", mode="edit", post=row,
                               title=title, body=body,
                               text_color=text_color or "#2E2836",
                               title_color=title_color or "#2E2836",
                               background_color=background_color or "#D9DD92")
    return render_template("post_form.html", mode="edit", post=row,
                           title=row["title"], body=row["body"],
                           text_color=row["text_color"],
                           title_color=row["title_color"],
                           background_color=row["background_color"])


@app.post("/post/<int:post_id>/delete")
@login_required
def delete_post(post_id):
    row = get_post(post_id)
    if row is None:
        abort(404)
    if row["user_id"] != g.user["id"] and not g.user["is_admin"]:
        abort(403, "You can only delete your own posts.")
    image = row["image"]
    db().execute("DELETE FROM posts WHERE id = ?", (post_id,))
    if get_setting("featured_post_id") == str(post_id):
        db().execute("DELETE FROM settings WHERE key = 'featured_post_id'")
    db().commit()
    remove_uploaded_image(image)
    flash("Post deleted.", "ok")
    return redirect(url_for("profile", username=row["username"]))


@app.post("/post/<int:post_id>/like")
@login_required
def toggle_like(post_id):
    if get_post(post_id) is None:
        abort(404)
    existing = db().execute(
        "SELECT 1 FROM likes WHERE user_id = ? AND post_id = ?",
        (g.user["id"], post_id)).fetchone()
    if existing:
        db().execute("DELETE FROM likes WHERE user_id = ? AND post_id = ?",
                     (g.user["id"], post_id))
        liked = False
    else:
        db().execute("INSERT INTO likes (user_id, post_id) VALUES (?, ?)",
                     (g.user["id"], post_id))
        liked = True
    db().commit()

    # Return JSON if requested via AJAX, otherwise redirect
    if request.headers.get("Accept") == "application/json":
        like_count = db().execute(
            "SELECT COUNT(*) FROM likes WHERE post_id = ?",
            (post_id,)).fetchone()[0]
        return jsonify({"liked": liked, "like_count": like_count})

    return redirect(safe_next(request.form.get("next"))
                    or url_for("post", post_id=post_id))


@app.post("/post/<int:post_id>/comments")
@login_required
def add_comment(post_id):
    if get_post(post_id) is None:
        abort(404)
    body = request.form.get("body", "").strip()
    if not body:
        flash("Write a comment before submitting.", "error")
    elif len(body) > 3000:
        flash("Comments can be at most 3,000 characters.", "error")
    else:
        db().execute(
            "INSERT INTO comments (user_id, post_id, body) VALUES (?, ?, ?)",
            (g.user["id"], post_id, body))
        db().commit()
        flash("Comment added.", "ok")
    return redirect(url_for("post", post_id=post_id) + "#comments")


# ----------------------------------------------------------------------
# Accounts: log in, log out, protected sign up
# ----------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("home"))
    next_url = safe_next(request.values.get("next"))
    if request.method == "POST":
        if throttled("login", 10, 300):
            abort(429, "Too many log-in attempts. Wait a few minutes and try again.")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db().execute(
            "SELECT id, password_hash FROM users WHERE username = ?",
            (username,)).fetchone()
        # Always run a hash check so response time does not reveal valid usernames.
        stored = user["password_hash"] if user else generate_password_hash("x")
        if check_password_hash(stored, password) and user:
            log_in(user["id"])
            return redirect(next_url or url_for("home"))
        flash("Wrong username or password.", "error")
    return render_template("login.html", next_url=next_url)


@app.post("/logout")
def logout():
    session.clear()
    flash("You are logged out.", "ok")
    return redirect(url_for("home"))


@app.route("/settings", methods=["GET", "POST"])
@login_required
def account_settings():
    settings = db().execute(
        "SELECT username, bio, avatar, avatar_position_x, avatar_position_y, "
        "profile_bg, profile_text "
        "FROM users WHERE id = ?", (g.user["id"],)).fetchone()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        bio = request.form.get("bio", "").strip()
        profile_bg = normalize_color(request.form.get("profile_bg", ""))
        profile_text = normalize_color(request.form.get("profile_text", ""))
        avatar_position_x = normalize_avatar_position(
            request.form.get("avatar_position_x", "50"))
        avatar_position_y = normalize_avatar_position(
            request.form.get("avatar_position_y", "50"))
        errors = []
        if not USERNAME_RE.fullmatch(username):
            errors.append("Usernames are 3 to 24 characters: letters, numbers and underscores.")
        if len(bio) > 500:
            errors.append("Your bio can be at most 500 characters.")
        if profile_bg is None:
            errors.append("Enter a valid profile background color in #RRGGBB format.")
        if profile_text is None:
            errors.append("Enter a valid profile text color in #RRGGBB format.")
        if avatar_position_x is None or avatar_position_y is None:
            errors.append("Choose valid profile picture framing positions.")
        try:
            image_data = read_uploaded_image(request.files.get("avatar"))
        except ValueError as exc:
            errors.append(str(exc))
            image_data = None

        new_avatar = None
        if not errors:
            if image_data:
                new_avatar = store_uploaded_image(image_data)
            avatar = new_avatar or settings["avatar"]
            if request.form.get("remove_avatar") == "1" and not new_avatar:
                avatar = None
            try:
                db().execute(
                    "UPDATE users SET username = ?, bio = ?, avatar = ?, "
                    "avatar_position_x = ?, avatar_position_y = ?, "
                    "profile_bg = ?, profile_text = ? WHERE id = ?",
                    (username, bio, avatar, avatar_position_x, avatar_position_y,
                     profile_bg, profile_text, g.user["id"]))
                db().commit()
            except sqlite3.IntegrityError:
                if new_avatar:
                    remove_uploaded_image(new_avatar)
                errors.append("That username is already taken.")
            else:
                if avatar != settings["avatar"]:
                    remove_uploaded_image(settings["avatar"])
                flash("Account settings saved.", "ok")
                return redirect(url_for("account_settings"))

        for error in errors:
            flash(error, "error")
        return render_template("settings.html", settings={
            "username": username, "bio": bio, "avatar": settings["avatar"],
            "avatar_position_x": avatar_position_x if avatar_position_x is not None
            else settings["avatar_position_x"],
            "avatar_position_y": avatar_position_y if avatar_position_y is not None
            else settings["avatar_position_y"],
            "profile_bg": profile_bg or "#D9DD92",
            "profile_text": profile_text or "#2E2836",
        })
    return render_template("settings.html", settings=settings)


@app.post("/settings/password")
@login_required
def change_password():
    current = request.form.get("current_password", "")
    new = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")
    password_hash = db().execute(
        "SELECT password_hash FROM users WHERE id = ?", (g.user["id"],)).fetchone()[0]
    if not check_password_hash(password_hash, current):
        flash("Your current password is incorrect.", "error")
    elif len(new) < 8 or len(new) > 128:
        flash("Passwords must be between 8 and 128 characters.", "error")
    elif new != confirm:
        flash("The new passwords do not match.", "error")
    else:
        db().execute("UPDATE users SET password_hash = ? WHERE id = ?",
                     (generate_password_hash(new), g.user["id"]))
        db().commit()
        flash("Password changed.", "ok")
    return redirect(url_for("account_settings"))


@app.post("/settings/delete")
@login_required
def delete_account():
    current = request.form.get("current_password", "")
    row = db().execute(
        "SELECT password_hash, avatar FROM users WHERE id = ?", (g.user["id"],)).fetchone()
    if not check_password_hash(row["password_hash"], current):
        flash("Your current password is incorrect; your account was not deleted.", "error")
        return redirect(url_for("account_settings"))

    post_rows = db().execute(
        "SELECT id, image FROM posts WHERE user_id = ?", (g.user["id"],)).fetchall()
    filenames = [row["avatar"]] + [post["image"] for post in post_rows]
    post_ids = [str(post["id"]) for post in post_rows]
    if post_ids:
        placeholders = ",".join("?" for _ in post_ids)
        db().execute(
            f"DELETE FROM settings WHERE key = 'featured_post_id' "
            f"AND value IN ({placeholders})", post_ids)
    db().execute("DELETE FROM users WHERE id = ?", (g.user["id"],))
    db().commit()
    for filename in filenames:
        remove_uploaded_image(filename)
    session.clear()
    flash("Your account and its posts have been deleted.", "ok")
    return redirect(url_for("home"))


def signup_unlocked():
    return time.time() - session.get("signup_unlocked_at", 0) < UNLOCK_SECONDS


@app.get("/signup")
def signup():
    if g.user:
        return redirect(url_for("home"))
    return render_template("signup.html", unlocked=signup_unlocked(),
                           form={}, errors=[])


@app.post("/signup/unlock")
def signup_unlock():
    if throttled("signup-gate", 8, 600):
        abort(429, "Too many attempts. Wait ten minutes and try again.")
    attempt = request.form.get("signup_password", "")
    if check_password_hash(get_setting("signup_password_hash"), attempt):
        session["signup_unlocked_at"] = time.time()
        return redirect(url_for("signup"))
    flash("That is not the signup password.", "error")
    return redirect(url_for("signup"))


@app.post("/signup")
def signup_create():
    if g.user:
        return redirect(url_for("home"))
    if not signup_unlocked():
        flash("Enter the signup password first.", "error")
        return redirect(url_for("signup"))

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm", "")
    errors = []
    if not USERNAME_RE.match(username):
        errors.append("Usernames are 3 to 24 characters: letters, numbers and underscores.")
    if len(password) < 8:
        errors.append("Passwords need at least 8 characters.")
    elif len(password) > 128:
        errors.append("Passwords can be at most 128 characters.")
    elif password != confirm:
        errors.append("The two passwords do not match.")

    if not errors:
        try:
            cur = db().execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, generate_password_hash(password)))
            db().commit()
        except sqlite3.IntegrityError as exc:
            errors.append("That username is taken.")
        else:
            log_in(cur.lastrowid)
            flash(f"Welcome, {username}.", "ok")
            return redirect(url_for("home"))

    return render_template("signup.html", unlocked=True,
                           form={"username": username}, errors=errors)


# ----------------------------------------------------------------------
# Admin
# ----------------------------------------------------------------------

@app.get("/admin")
@admin_required
def admin():
    featured_id = get_setting("featured_post_id")
    featured_post = None
    if featured_id and featured_id.isdigit():
        featured_post = db().execute(
            """SELECT p.id, p.title, u.username,
                      EXISTS(
                        SELECT 1 FROM crossword_completions c
                        JOIN crossword_state s ON s.id = 1
                        WHERE c.user_id = u.id AND c.puzzle_version = s.version
                      ) AS crossword_star
               FROM posts p
               JOIN users u ON u.id = p.user_id
               WHERE p.id = ?""", (featured_id,)
        ).fetchone()
    stats = {
        "users": db().execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "posts": db().execute("SELECT COUNT(*) FROM posts").fetchone()[0],
        "likes": db().execute("SELECT COUNT(*) FROM likes").fetchone()[0],
    }
    crossword = get_crossword()
    crossword_rows = []
    crossword_clues = {}
    if crossword:
        crossword_rows = [
            crossword["solution"][row * 15:(row + 1) * 15]
            for row in range(15)
        ]
        crossword_clues = crossword["clues"]
    return render_template("admin.html", stats=stats, featured_post=featured_post,
                           crossword=crossword, crossword_rows=crossword_rows,
                           crossword_clues=crossword_clues)


@app.post("/admin/crossword")
@admin_required
def admin_save_crossword():
    raw_grid = request.form.get("grid", "")
    raw_clues = request.form.get("clues", "")
    if len(raw_grid) > 1000 or len(raw_clues) > 60000:
        flash("The crossword grid or clues are too large.", "error")
        return redirect(url_for("admin") + "#crossword")
    solution, clues, error = validate_crossword(raw_grid, raw_clues)
    if error:
        flash(error, "error")
        return redirect(url_for("admin") + "#crossword")

    serialized_clues = json.dumps(clues, ensure_ascii=False, sort_keys=True)
    state = db().execute(
        "SELECT solution, clues, version FROM crossword_state WHERE id = 1"
    ).fetchone()
    if state is None:
        db().execute(
            "INSERT INTO crossword_state (id, solution, clues, version) "
            "VALUES (1, ?, ?, 1)", (solution, serialized_clues))
        flash("Weekly Bokword puzzle published.", "ok")
    elif state["solution"] != solution or state["clues"] != serialized_clues:
        db().execute(
            "UPDATE crossword_state SET solution = ?, clues = ?, version = version + 1, "
            "updated_at = datetime('now') WHERE id = 1",
            (solution, serialized_clues))
        db().execute("DELETE FROM crossword_completions")
        flash("Weekly Bokword puzzle updated; previous stars were reset.", "ok")
    else:
        flash("No crossword changes to save.", "info")
    db().commit()
    return redirect(url_for("admin") + "#crossword")


@app.post("/admin/crossword/reset")
@admin_required
def admin_reset_crossword():
    state = db().execute(
        "SELECT version FROM crossword_state WHERE id = 1"
    ).fetchone()
    if state is None:
        db().execute(
            "INSERT INTO crossword_state (id, solution, clues, version) "
            "VALUES (1, ?, '{}', 1)", ("#" * 225,))
    else:
        db().execute(
            "UPDATE crossword_state SET solution = ?, clues = '{}', version = version + 1, "
            "updated_at = datetime('now') WHERE id = 1", ("#" * 225,))
    db().execute("DELETE FROM crossword_completions")
    db().commit()
    flash(
        "The crossword was reset to an empty grid and unpublished; "
        "all solver stars were cleared.", "ok")
    return redirect(url_for("admin") + "#crossword")


@app.post("/crossword/solve")
@login_required
def solve_crossword():
    crossword = get_crossword()
    if crossword is None:
        abort(404)
    guess = normalize_crossword_text(request.form.get("guess", ""))
    solved = len(guess) == 225 and guess == crossword["solution"]
    if solved:
        db().execute(
            "INSERT OR IGNORE INTO crossword_completions "
            "(user_id, puzzle_version, guess) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, puzzle_version) DO UPDATE SET guess = excluded.guess",
            (g.user["id"], crossword["version"], guess))
        db().commit()
    if request.accept_mimetypes.best == "application/json":
        return jsonify(solved=solved)
    if solved:
        flash("Crossword solved! You earned a star by your name.", "ok")
    else:
        flash("Not quite yet. Keep trying!", "info")
    return redirect(url_for("home") + "#bokword")


@app.get("/admin/search/posts")
@admin_required
def search_admin_posts():
    query = request.args.get("q", "").strip()[:100]
    if len(query) < 2:
        return jsonify(results=[])
    pattern = like_pattern(query)
    rows = db().execute(
        """SELECT p.id, p.title, u.username
           FROM posts p JOIN users u ON u.id = p.user_id
           WHERE p.title LIKE ? ESCAPE '\\' OR u.username LIKE ? ESCAPE '\\'
           ORDER BY p.created_at DESC, p.id DESC LIMIT 12""",
        (pattern, pattern)).fetchall()
    return jsonify(results=[
        {"id": row["id"], "label": f'{row["title"]} (by {row["username"]})'}
        for row in rows
    ])


@app.post("/admin/featured")
@admin_required
def admin_featured():
    post_id = request.form.get("post_id", "").strip()
    if not post_id:
        db().execute("DELETE FROM settings WHERE key = 'featured_post_id'")
        db().commit()
        flash("Featured post cleared.", "ok")
    elif post_id.isdigit() and db().execute(
            "SELECT 1 FROM posts WHERE id = ?", (post_id,)).fetchone():
        set_setting("featured_post_id", post_id)
        flash("Featured post updated.", "ok")
    else:
        flash("That post does not exist.", "error")
    return redirect(safe_next(request.form.get("next")) or url_for("admin"))


@app.post("/admin/signup-password")
@admin_required
def admin_signup_password():
    new = request.form.get("new_password", "")
    confirm = request.form.get("confirm", "")
    if len(new) < 8:
        flash("The signup password needs at least 8 characters.", "error")
    elif new != confirm:
        flash("The two passwords do not match.", "error")
    else:
        set_setting("signup_password_hash", generate_password_hash(new))
        flash("Signup password changed.", "ok")
    return redirect(url_for("admin"))


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------

@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(413)
@app.errorhandler(429)
def error_page(err):
    messages = {404: "We could not find that page."}
    message = getattr(err, "description", None)
    if err.code == 404 or not message:
        message = messages.get(err.code, "Something went wrong.")
    return render_template("error.html", code=err.code, message=message), err.code


# ----------------------------------------------------------------------
# Command line tools
# ----------------------------------------------------------------------

@app.cli.command("create-admin")
@click.argument("username")
@click.password_option()
def create_admin(username, password):
    """Create an admin account (or make an existing user an admin)."""
    if not USERNAME_RE.match(username):
        raise click.ClickException("Usernames are 3-24 letters, numbers or underscores.")
    if len(password) < 8:
        raise click.ClickException("Passwords need at least 8 characters.")
    conn = sqlite3.connect(DB_PATH)
    existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        conn.execute("UPDATE users SET is_admin = 1, password_hash = ? WHERE id = ?",
                     (generate_password_hash(password), existing[0]))
        click.echo(f"{username} is now an admin and the password was updated.")
    else:
        conn.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)",
            (username, generate_password_hash(password)))
        click.echo(f"Admin account {username} created.")
    conn.commit()
    conn.close()


@app.cli.command("seed-demo")
def seed_demo():
    """Fill the database with demo users and posts (for trying things out)."""
    import random
    random.seed(7)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    pw = generate_password_hash("demo-password")
    names = ["admin", "mara", "jonas", "priya", "tomas"]
    for i, name in enumerate(names):
        conn.execute(
            "INSERT OR IGNORE INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
            (name, pw, 1 if name == "admin" else 0))
    ids = {n: conn.execute("SELECT id FROM users WHERE username = ?", (n,)).fetchone()[0]
           for n in names}
    topics = [
        ("Why I stopped fighting my build tools", "mara"),
        ("A beginner's guide to reading a stack trace", "jonas"),
        ("Notes from a week of offline-first coding", "priya"),
        ("What a hash table really costs", "tomas"),
        ("The case for boring technology", "mara"),
        ("Debugging a race condition at 2 a.m.", "jonas"),
        ("Small habits that made my code reviews better", "priya"),
        ("How I organize a growing side project", "tomas"),
        ("Learning functional programming the slow way", "mara"),
        ("Parsing ASCII maps for fun", "jonas"),
        ("Welcome to Boki.blog", "admin"),
        ("Three lessons from teaching a study group", "admin"),
    ]
    body = ("This is demo text for a sample post.\n\nIt has a few paragraphs so you can "
            "see how longer writing looks on the page. Replace it by writing your own.\n\n"
            "Posts are plain text. A blank line starts a new paragraph.")
    post_ids = []
    for i, (title, author) in enumerate(topics):
        days_ago = len(topics) - i
        cur = conn.execute(
            "INSERT INTO posts (user_id, title, body, created_at) "
            "VALUES (?, ?, ?, datetime('now', ?))",
            (ids[author], title, body, f"-{days_ago} days"))
        post_ids.append(cur.lastrowid)
    for pid in post_ids:
        for name in random.sample(names, random.randint(0, len(names))):
            conn.execute(
                "INSERT OR IGNORE INTO likes (user_id, post_id, created_at) "
                "VALUES (?, ?, datetime('now', ?))",
                (ids[name], pid, f"-{random.randint(0, 9)} days"))
    conn.execute("INSERT OR REPLACE INTO settings VALUES ('featured_post_id', ?)",
                 (str(post_ids[4]),))
    conn.commit()
    conn.close()
    click.echo("Demo data added. Log in as any of "
               f"{', '.join(names)} with the password: demo-password")


if __name__ == "__main__":
    app.run(debug=False)
