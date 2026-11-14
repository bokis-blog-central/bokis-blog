# Boki.blog

A small multi-user blog built with Flask and SQLite.

## Features

- Accounts with a username and password. Email addresses are not collected.
- Account settings for profile pictures, a short bio, username and password changes,
  account deletion and custom profile colors.
- The sign-up page is locked behind a signup password that only the admin knows.
- Home page: the featured post, an interactive weekly Bokword crossword, the
  4 most liked posts of the last 7 days, and the latest post by an admin.
- Explore page: search posts (title, text, author) and users, or browse posts and
  users with independent pagination. Posts can be sorted by newest or most liked.
- Write, edit and delete your own posts. Posts support an image, custom title,
  text, background, accent and surface colors, and comments. The site header and
  footer keep their fixed site colors. Admins can also delete posts.
- Comments support an optional image, threaded replies, and a per-post comment
  count. Authors and admins can edit or delete comments. Deleting a comment that
  has replies keeps the replies: the comment becomes "I deleted my comment" by the
  placeholder user "Coward", which cannot be used to log in.
- Choose colors with a color wheel or enter a six-digit hex code; color previews
  update as you edit.
- Admin page: search for the featured post, create and reset the 15x15 crossword,
  remove user accounts, and change the signup password. Deleting an account
  transfers its posts and comments to Coward, appends the original username to
  each post and comment, and deletes its likes and profile picture. Comments by
  other users on transferred posts keep their authors and content; they are
  transferred only if their own accounts are later deleted. Crossword Across clues are numbered top to
  bottom and Down clues left to right, with separate numbering for each direction.
  Resetting the crossword saves an all-blocked grid, unpublishes the puzzle, and
  clears solver stars.
  Crossword solvers earn a star by their username
  until the puzzle is changed or reset, and each earned star adds to their
  cumulative Bokword victories on their profile. Crossword answers accept Latin
  and Greek letters, including accented Greek vowels. Snake words may form
  chains: enter a `~!conn` tag in a connected answer's optional clue to continue
  it. Each target has at most one incoming connection; cycles are not allowed.
  A snake clue's length counts each shared grid cell only once.
- Wild Card Boknections: an admin-togglable monthly game on the home page. Drag
  13 words into four 3-word categories plus the one wild card that fits all of
  them. Each user has 10 checks and can check categories one at a time; correct categories lock and reveal their titles.
  Solvers earn a flower by their username and a win on their profile. Saving a new
  puzzle in the admin page resets attempts and flowers but keeps win counts.
- ΜΠΟΚΟΨΑΡΑΚΙΑ: an admin-togglable Greek word ladder. Change one letter at a
  time to reach the destination, with unlimited guesses and a reset button.
  Accents and case are ignored. Admins can add missing words, select the two
  endpoints, and toggle the game. A solver receives a red 🟘 until the
  puzzle changes, and earns a cumulative victory. The destination selected by
  the admin is accepted even if absent from the dictionary. Accepted words are
  saved as a ladder of letter cells; restarting clears the ladder but keeps an
  earned badge. Older progress can only show its last saved word.
- Scores page: logged-in users can view separate Bokword, Boknections and ΜΠΟΚΟΨΑΡΑΚΙΑ rankings
  for non-admin players with at least one victory in that game. Tabs for hidden games are hidden, while
  saved scores remain available. Admins can manually adjust cumulative victory counts
  from the Admin page.
- Game archives: cleared Bokwords and replaced Boknections puzzles are preserved
  with their original victors; admins can edit archived puzzles from the collapsed
  archive editor.

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
After upgrading, existing users must log in again. Changing a password also signs
out the account's other sessions.

To try it with sample content first, run `flask --app app seed-demo`. It adds users
(admin, mara, jonas, priya, tomas, all with the password `demo-password`) and posts.
Do not use it on a real site.

## Settings (environment variables)

| Variable | What it does |
| --- | --- |
| `SIGNUP_PASSWORD` | Initial signup password. Only read the first time the database is created. Change it later on the Admin page. |
| `SECRET_KEY` | Required, stable cookie-signing key of at least 32 bytes. Set locally in `.env` and in Render's environment settings. |
| `SITE_NAME` | Name shown in the header. Default: Boki.blog. |
| `BLOG_DATA_DIR` | Directory for the database and uploads. Default: `instance/`; set to `/var/data` when deploying with the included Render disk. |
| `BLOG_DB` | Optional explicit path to the SQLite file. Default: `<BLOG_DATA_DIR>/blog.db`. |
| `BLOG_HTTPS` | Set to `1` when serving over HTTPS so cookies are marked secure. |

## Putting it online

The included `render.yaml` configures a paid Render web service, Gunicorn, HTTPS
cookies, and a persistent disk at `/var/data` for the SQLite database and uploaded
images. Connect the repository to Render as a Blueprint. When prompted, enter the
`SECRET_KEY` and `SIGNUP_PASSWORD` values from your local `.env`; Render stores
these as service environment variables. Do not commit `.env`.

After the first deploy, open the service Shell and run
`flask --app app create-admin yourname` to create the admin account. The service
starts with a new database on its persistent disk. If you need to bring over
existing local posts or images, copy the local database and `instance/uploads/`
into the mounted `/var/data` directory before creating the admin account.

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

The Greek wordlist is the el_GR Hunspell dictionary by Evripidis Papakostas,
Steve Stavropulos and contributors, distributed under MPL 1.1/GPL 2.0/LGPL 2.1.
The pinned source is
https://github.com/elastic/hunspell/tree/cc1e74c4ca711f0625f6b73f883197794379aa97/dicts/el_GR.
The dictionary notice and MPL 1.1 license are included in `data/`.
