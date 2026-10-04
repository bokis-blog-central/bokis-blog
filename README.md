# Boki.blog

A small multi-user blog built with Flask and SQLite.

## Features

- Accounts with a username and password. Email addresses are not collected.
- Account settings for profile pictures, a short bio, username and password changes,
  account deletion and custom profile colors.
- The sign-up page is locked behind a signup password that only the admin knows.
- Home page: the featured post, an interactive weekly Bokword crossword, the
  4 most liked posts of the last 7 days, and the latest post by an admin.
- Explore page: search posts (title, text, author) and users, or browse every post,
  sorted by newest or most liked.
- Write, edit and delete your own posts. Posts support an image, custom text and
  background colors, and comments. Admins can also delete posts.
- Choose colors with a color wheel or enter a six-digit hex code; color previews
  update as you edit.
- Admin page: search for the featured post, create and reset the 15x15 crossword,
  and change the signup password. Crossword Across clues are numbered top to
  bottom and Down clues left to right, with separate numbering for each direction.
  Resetting the crossword saves an all-blocked grid, unpublishes the puzzle, and
  clears solver stars.
  Crossword solvers earn a star by their username
  until the puzzle is changed or reset. Crossword answers accept Latin and Greek
  letters, including accented Greek vowels.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Choose the signup password (optional; a random one is printed on first run if you skip this)
export SIGNUP_PASSWORD="pick-something-long"     # Windows PowerShell: $env:SIGNUP_PASSWORD="..."

# Create your admin account
flask --app app create-admin yourname

# Start the site
flask --app app run
```

Open http://127.0.0.1:5000.

When `SECRET_KEY` is not set, the app generates a persistent key in the user's
configuration directory, outside the project (on Windows:
`%LOCALAPPDATA%\Boki.blog\secret_key`). Keep this file when moving or backing up a
local installation. For a hosted deployment, configure `SECRET_KEY` in the
deployment environment or secret manager; `python generate_secret_key.py` can
generate a value for this purpose. Do not commit the key to the codebase.
Changing it invalidates existing login sessions. User passwords are stored as salted,
one-way hashes and do not use `SECRET_KEY` for encryption.
Email addresses are no longer collected; upgrading an existing database removes
its email column and the values it contained.

To try it with sample content first, run `flask --app app seed-demo`. It adds users
(admin, mara, jonas, priya, tomas, all with the password `demo-password`) and posts.
Do not use it on a real site.

## Settings (environment variables)

| Variable | What it does |
| --- | --- |
| `SIGNUP_PASSWORD` | Initial signup password. Only read the first time the database is created. Change it later on the Admin page. |
| `SECRET_KEY` | Optional locally; if unset, a 256-bit key is generated in the user's configuration directory outside the project. For hosted deployments, set a stable value of at least 32 bytes using the runtime environment or a secret manager. |
| `SITE_NAME` | Name shown in the header. Default: Boki.blog. |
| `BLOG_DB` | Path to the SQLite file. Default: `instance/blog.db`. |
| `BLOG_HTTPS` | Set to `1` when serving over HTTPS so cookies are marked secure. |

## Putting it online

`flask run` is for development. For a real site, serve it with a production server
such as gunicorn (`pip install gunicorn`, then `gunicorn app:app`) behind HTTPS, and set
`BLOG_HTTPS=1`. Back up the database and uploads in `instance/`; keep `SECRET_KEY`
separately in your deployment's secret manager.

The log-in and signup-password throttling is kept in memory and per process, which is
fine for a small site on one process.

## Where things live

- `app.py`: all routes, the database schema and the command-line tools
- `templates/`: the HTML pages
- `static/style.css`: colors and fonts are at the top
- `static/app.js`: synchronizes color pickers, avatar framing, and crossword editing/solving

User-uploaded profile and post images are stored in `instance/uploads/`. Supported
formats are PNG, JPEG, GIF and WebP, with a 5 MB limit per image. Back up this
directory along with the database.
