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
- Write, edit and delete your own posts. Posts support an image, custom title,
  text, background, accent and surface colors, and comments. The site header and
  footer keep their fixed site colors. Admins can also delete posts.
- Choose colors with a color wheel or enter a six-digit hex code; color previews
  update as you edit.
- Admin page: search for the featured post, create and reset the 15x15 crossword,
  and change the signup password. Crossword Across clues are numbered top to
  bottom and Down clues left to right, with separate numbering for each direction.
  Resetting the crossword saves an all-blocked grid, unpublishes the puzzle, and
  clears solver stars.
  Crossword solvers earn a star by their username
  until the puzzle is changed or reset, and each earned star adds to their
  cumulative Bokword victories on their profile. Crossword answers accept Latin
  and Greek letters, including accented Greek vowels.
- Boknections, Wild Card: an admin-togglable monthly game on the home page. Drag
  13 words into four 3-word categories plus the one wild card that fits all of
  them. Each user has 10 checks and can check categories one at a time; correct categories lock and reveal their titles.
  Solvers earn a flower by their username and a win on their profile. Saving a new
  puzzle in the admin page resets attempts and flowers but keeps win counts.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Optional: override the initial signup password configured in .env
export SIGNUP_PASSWORD="pick-something-long"     # Windows PowerShell: $env:SIGNUP_PASSWORD="..."

# Create your admin account
flask --app app create-admin yourname

# Start the site
flask --app app run
```

Open http://127.0.0.1:5000.

Flask's CLI loads variables from `.env` when `python-dotenv` is installed.
`SECRET_KEY` is required and must be at least 32 bytes; keep it out of Git.
Changing it invalidates existing login sessions. User passwords are stored as
salted, one-way hashes and do not use `SECRET_KEY` for encryption.
Email addresses are no longer collected; upgrading an existing database removes
its email column and the values it contained.

To try it with sample content first, run `flask --app app seed-demo`. It adds users
(admin, mara, jonas, priya, tomas, all with the password `demo-password`) and posts.
Do not use it on a real site.

## Settings (environment variables)

| Variable | What it does |
| --- | --- |
| `SIGNUP_PASSWORD` | Initial signup password. Only read the first time the database is created. Change it later on the Admin page. |
| `SECRET_KEY` | Required, stable cookie-signing key of at least 32 bytes. Set locally in `.env` and in Render's environment settings. |
| `SITE_NAME` | Name shown in the header. Default: Boki.blog. |
| `BLOG_DATA_DIR` | Directory for the database and uploads. Default: `instance/`; set to `/opt/render/project/src/instance` when deploying with the included Render disk. |
| `BLOG_DB` | Optional explicit path to the SQLite file. Default: `<BLOG_DATA_DIR>/blog.db`. |
| `BLOG_HTTPS` | Set to `1` when serving over HTTPS so cookies are marked secure. |

## Putting it online

The included `render.yaml` configures a paid Render web service, Gunicorn, HTTPS
cookies, and a persistent disk at `/opt/render/project/src/instance` for the SQLite database and uploaded
images. Connect the repository to Render as a Blueprint. When prompted, enter the
`SECRET_KEY` and `SIGNUP_PASSWORD` values from your local `.env`; Render stores
these as service environment variables. Do not commit `.env`.

After the first deploy, open the service Shell and run
`flask --app app create-admin yourname` to create the admin account. The service
starts with a new database on its persistent disk. If you need to bring over
existing local posts or images, copy the local database and `instance/uploads/`
into the mounted instance directory before creating the admin account.

The log-in and signup-password throttling is kept in memory and per process, which is
fine for a small site on one process.

## Where things live

- `app.py`: all routes, the database schema and the command-line tools
- `templates/`: the HTML pages
- `static/style.css`: colors and fonts are at the top
- `static/app.js`: synchronizes color pickers, avatar framing, and crossword editing/solving

User-uploaded profile and post images are stored in
`<BLOG_DATA_DIR>/uploads/`. Supported formats are PNG, JPEG, GIF and WebP, with
a 5 MB limit per image. Back up this directory along with the database.
