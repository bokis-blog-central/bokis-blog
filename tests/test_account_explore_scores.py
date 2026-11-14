import importlib
import json
import os
import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash


class AccountExploreScoresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.import_dir = tempfile.TemporaryDirectory()
        with patch.dict(os.environ, {
            "BLOG_DATA_DIR": cls.import_dir.name,
            "BLOG_DB": str(Path(cls.import_dir.name) / "import.db"),
            "SECRET_KEY": "test-secret-key-" * 3,
            "SIGNUP_PASSWORD": "test-signup-password",
        }):
            cls.blog = importlib.import_module("app")
        cls.blog.app.config.update(TESTING=True)
        cls.password_hash = generate_password_hash("test-password")

    @classmethod
    def tearDownClass(cls):
        cls.import_dir.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.blog.DB_PATH = str(Path(self.temp.name) / "test.db")
        self.blog.UPLOAD_DIR = str(Path(self.temp.name) / "uploads")
        Path(self.blog.UPLOAD_DIR).mkdir()
        self.blog._schema_checked.clear()
        with patch.dict(os.environ, {"SIGNUP_PASSWORD": "test-signup-password"}):
            self.blog.migrate_db()
        self.client = self.blog.app.test_client()
        self.admin_id = self.add_user("Admin", admin=1)
        self.login(self.client, self.admin_id)

    def execute(self, query, params=()):
        with closing(sqlite3.connect(self.blog.DB_PATH)) as conn:
            with conn:
                return conn.execute(query, params).fetchall()

    def add_user(self, username, admin=0, word=0, connections=0, avatar=None):
        with closing(sqlite3.connect(self.blog.DB_PATH)) as conn:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO users (username, password_hash, is_admin, "
                    "bokword_victories, boknections_victories, avatar) VALUES (?, ?, ?, ?, ?, ?)",
                    (username, self.password_hash, admin, word, connections, avatar))
                return cursor.lastrowid

    def login(self, client, user_id):
        with self.blog.app.app_context():
            user = self.blog.db().execute(
                "SELECT id, password_hash, session_nonce FROM users WHERE id = ?", (user_id,)).fetchone()
            binding = self.blog.user_auth_binding(user)
        with client.session_transaction() as session:
            session["user_id"] = user_id
            session["auth_binding"] = binding
            session["csrf"] = "test-csrf"

    def post(self, client, path, **data):
        return client.post(path, data={"csrf_token": "test-csrf", **data})

    def test_scores_only_include_winners_for_selected_game(self):
        self.add_user("Zero")
        self.add_user("WordWinner", word=2)
        self.add_user("ConnectionWinner", connections=1)
        self.add_user("HiddenAdmin", admin=1, word=9, connections=9)
        word = self.client.get("/scores?game=bokword").get_data(as_text=True)
        self.assertIn("WordWinner", word)
        self.assertNotIn("ConnectionWinner", word)
        self.assertNotIn("Zero", word)
        self.assertNotIn("HiddenAdmin", word)
        connections = self.client.get("/scores?game=boknections").get_data(as_text=True)
        self.assertIn("ConnectionWinner", connections)
        self.assertNotIn("WordWinner", connections)
        self.assertNotIn("Zero", connections)
        self.assertNotIn("HiddenAdmin", connections)

    def test_score_tabs_follow_game_toggles_without_changing_scores(self):
        self.add_user("Winner", connections=2)
        page = self.client.get("/scores").get_data(as_text=True)
        self.assertIn('href="/scores?game=bokword"', page)
        self.assertNotIn('href="/scores?game=boknections"', page)
        self.assertNotIn('href="/scores?game=bokopsaraki"', page)
        self.post(self.client, "/admin/boknections/toggle", enabled="1")
        page = self.client.get("/scores?game=boknections").get_data(as_text=True)
        self.assertIn('href="/scores?game=boknections" aria-current="page"', page)
        self.assertNotIn('href="/scores?game=bokopsaraki"', page)
        self.assertIn("Winner", page)
        self.post(self.client, "/admin/bokopsaraki/toggle", enabled="1")
        page = self.client.get("/scores?game=bokopsaraki").get_data(as_text=True)
        self.assertIn('href="/scores?game=boknections"', page)
        self.assertIn('href="/scores?game=bokopsaraki" aria-current="page"', page)
        self.post(self.client, "/admin/boknections/toggle", enabled="0")
        page = self.client.get("/scores").get_data(as_text=True)
        self.assertNotIn('href="/scores?game=boknections"', page)
        self.assertIn('href="/scores?game=bokopsaraki"', page)
        self.assertIn("Winner", self.client.get("/scores?game=boknections").get_data(as_text=True))
        self.post(self.client, "/admin/bokopsaraki/toggle", enabled="0")
        page = self.client.get("/scores").get_data(as_text=True)
        self.assertNotIn('href="/scores?game=boknections"', page)
        self.assertNotIn('href="/scores?game=bokopsaraki"', page)

    def test_replacing_boknections_archives_old_puzzle_and_victors(self):
        winner = self.add_user("Winner", connections=3)
        player = self.add_user("Player")
        form = {
            f"cat{i}_{field}": value
            for i in range(1, 5)
            for field, value in [
                ("title", f"Category {i}"),
                *[(f"word{j}", f"word{i}{j}") for j in range(1, 4)],
            ]
        }
        form["wild"] = "wildcard"
        self.assertEqual(self.post(self.client, "/admin/boknections", **form).status_code, 302)
        original = json.loads(self.execute("SELECT puzzle FROM boknections_state")[0][0])
        self.execute("INSERT INTO boknections_progress (user_id, puzzle_version, solved) VALUES (?, 1, 1)",
                     (winner,))
        self.execute("INSERT INTO boknections_progress (user_id, puzzle_version, solved) VALUES (?, 1, 0)",
                     (player,))
        form["wild"] = "newwildcard"
        self.assertEqual(self.post(self.client, "/admin/boknections", **form).status_code, 302)
        puzzle, version = self.execute("SELECT puzzle, version FROM boknections_state")[0]
        self.assertEqual(json.loads(puzzle)["wild"], "newwildcard")
        self.assertEqual(version, 2)
        archived, victors = self.execute("SELECT puzzle, victors FROM boknections_archive")[0]
        self.assertEqual(json.loads(archived), original)
        self.assertEqual(json.loads(victors), ["Winner"])
        self.assertFalse(self.execute("SELECT * FROM boknections_progress"))
        self.assertEqual(self.execute("SELECT boknections_victories FROM users WHERE id = ?", (winner,)), [(3,)])
        self.assertEqual(self.post(self.client, "/admin/boknections", **form).status_code, 302)
        self.assertEqual(self.execute("SELECT COUNT(*) FROM boknections_archive"), [(1,)])
        self.assertEqual(self.execute("SELECT version FROM boknections_state"), [(2,)])

    def test_explore_pages_users_independently_and_preserves_filters(self):
        for i in range(25):
            user_id = self.add_user(f"Player{i:02}")
            self.execute("INSERT INTO posts (user_id, title, body) VALUES (?, ?, ?)",
                         (user_id, f"Player post {i}", "body"))
        first = self.client.get("/explore?type=users").get_data(as_text=True)
        self.assertIn("Player00", first)
        self.assertNotIn("Player24", first)
        self.assertIn('aria-label="User pagination"', first)
        self.assertIn('<ul class="user-list" aria-label="User results">', first)
        self.assertIn('aria-labelledby="users-title" data-user-pagination', first)
        first_again = self.client.get("/explore?type=users&user_page=-4").get_data(as_text=True)
        self.assertIn("Player00", first_again)
        last = self.client.get("/explore?type=users&user_page=999").get_data(as_text=True)
        self.assertIn("Player24", last)
        self.assertIn("Page 3 of 3", last)
        searched = self.client.get(
            "/explore?q=Player&type=all&sort=liked&page=2&user_page=3").get_data(as_text=True)
        self.assertIn("Player24", searched)
        self.assertNotIn("/u/Player00", searched)
        self.assertIn('aria-labelledby="users-title" data-user-pagination', searched)
        self.assertIn("user_page=3", searched)
        self.assertIn("page=2", searched)
        self.assertIn("sort=liked", searched)
        self.assertIn("q=Player", searched)
        escaped = self.client.get("/explore?q=Player_&type=users").get_data(as_text=True)
        self.assertIn("No users match", escaped)
        profile = self.client.get("/u/Player00").get_data(as_text=True)
        self.assertIn("Player00", profile)

    def test_admin_deletion_transfers_content_and_invalidates_reused_id(self):
        target_id = self.add_user("Target", avatar="avatar.png")
        other_id = self.add_user("Other")
        # Make the target the highest id so SQLite can reuse it after deletion.
        self.execute("DELETE FROM users WHERE id = ?", (target_id,))
        target_id = self.add_user("Target", avatar="avatar.png")
        target_client = self.blog.app.test_client()
        self.login(target_client, target_id)
        for filename in ("avatar.png", "post.png", "comment.png", "other-comment.png"):
            (Path(self.blog.UPLOAD_DIR) / filename).write_bytes(b"image")
        self.execute("INSERT INTO posts (user_id, title, body, image) VALUES (?, 'title', 'body', 'post.png')",
                     (target_id,))
        post_id = self.execute("SELECT id FROM posts WHERE user_id = ?", (target_id,))[0][0]
        self.execute("INSERT INTO comments (user_id, post_id, body, image) VALUES (?, ?, 'body', 'comment.png')",
                     (target_id, post_id))
        target_comment = self.execute("SELECT id FROM comments WHERE user_id = ?", (target_id,))[0][0]
        self.execute("INSERT INTO comments (user_id, post_id, body, image) VALUES (?, ?, 'body', 'other-comment.png')",
                     (other_id, post_id))
        reply_id = self.execute("SELECT id FROM comments WHERE user_id = ?", (other_id,))[0][0]
        self.execute("UPDATE comments SET parent_id = ? WHERE id = ?", (target_comment, reply_id))
        self.execute("INSERT INTO posts (user_id, title, body) VALUES (?, 'Other post', 'text')", (other_id,))
        other_post = self.execute("SELECT id FROM posts WHERE user_id = ?", (other_id,))[0][0]
        self.execute("INSERT INTO comments (user_id, post_id, body) VALUES (?, ?, 'on another post')",
                     (target_id, other_post))
        self.execute("INSERT INTO likes (user_id, post_id) VALUES (?, ?)", (other_id, post_id))
        self.execute("INSERT INTO likes (user_id, post_id) VALUES (?, ?)", (target_id, post_id))
        self.execute("INSERT INTO settings (key, value) VALUES ('featured_post_id', ?)", (str(post_id),))
        self.execute("INSERT INTO settings (key, value) VALUES ('guest_author_bokword', ?)", (str(target_id),))
        self.execute("INSERT INTO settings (key, value) VALUES ('guest_author_boknections', ?)", (str(target_id),))
        response = self.post(self.client, "/admin/users/delete", user_id=str(target_id),
                             confirm_username="Target", current_password="test-password")
        self.assertEqual(response.status_code, 302)
        coward_id = self.execute("SELECT id FROM users WHERE username = 'Coward'")[0][0]
        self.assertEqual(self.execute("SELECT user_id, body, image FROM posts WHERE id = ?", (post_id,)),
                         [(coward_id, "body\n\nOriginally by Target", "post.png")])
        self.assertEqual(self.execute("SELECT user_id, body, image FROM comments WHERE id = ?", (target_comment,)),
                         [(coward_id, "body\n\nOriginally by Target", "comment.png")])
        self.assertEqual(self.execute("SELECT is_deleted FROM comments WHERE id = ?", (target_comment,)), [(0,)])
        self.assertEqual(self.execute("SELECT user_id FROM comments WHERE post_id = ?", (other_post,)),
                         [(coward_id,)])
        self.assertEqual(self.execute("SELECT body FROM comments WHERE post_id = ?", (other_post,)),
                         [("on another post\n\nOriginally by Target",)])
        self.assertEqual(self.execute("SELECT parent_id FROM comments WHERE id = ?", (reply_id,)),
                         [(target_comment,)])
        self.assertEqual(self.execute("SELECT user_id FROM likes WHERE post_id = ?", (post_id,)),
                         [(other_id,)])
        self.assertFalse(self.execute("SELECT id FROM users WHERE id = ?", (target_id,)))
        self.assertEqual(self.execute("SELECT value FROM settings WHERE key = 'featured_post_id'"), [(str(post_id),)])
        self.assertFalse(self.execute("SELECT key FROM settings WHERE key LIKE 'guest_author_%'"))
        self.assertEqual({p.name for p in Path(self.blog.UPLOAD_DIR).iterdir()},
                         {"post.png", "comment.png", "other-comment.png"})
        page = self.client.get(f"/post/{post_id}").get_data(as_text=True)
        self.assertIn("Originally by Target", page)
        self.assertIn("body", page)
        self.assertIn("post.png", page)
        self.assertIn("comment.png", page)
        self.assertIn("title", self.client.get("/explore?type=posts").get_data(as_text=True))
        self.assertIn("title", self.client.get("/explore?type=posts&q=title").get_data(as_text=True))
        self.assertIn("title", self.client.get("/u/Coward").get_data(as_text=True))
        self.assertEqual(self.post(self.client, f"/comment/{reply_id}/delete").status_code, 302)
        self.assertTrue(self.execute("SELECT id FROM comments WHERE id = ?", (target_comment,)))
        self.assertEqual(self.post(self.client, f"/comment/{target_comment}/edit", body="edited").status_code, 302)
        self.assertEqual(self.execute("SELECT body FROM comments WHERE id = ?", (target_comment,)), [("edited",)])
        replacement_id = self.add_user("Replacement")
        self.assertEqual(replacement_id, target_id)
        response = target_client.get("/explore")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)

    def test_deletion_rejects_unauthorized_and_unconfirmed_requests(self):
        target_id = self.add_user("Target")
        target_client = self.blog.app.test_client()
        self.login(target_client, target_id)
        form = {"user_id": str(target_id), "confirm_username": "Target",
                "current_password": "test-password"}
        self.assertEqual(self.post(target_client, "/admin/users/delete", **form).status_code, 403)
        self.assertEqual(self.client.post("/admin/users/delete", data=form).status_code, 400)
        for changes in ({"current_password": "wrong"}, {"confirm_username": "wrong"},
                        {"user_id": "invalid"}, {"user_id": str(self.admin_id)}):
            response = self.post(self.client, "/admin/users/delete", **{**form, **changes})
            self.assertEqual(response.status_code, 302)
            self.assertIn(b"error", self.client.get(response.location).data)
        coward_id = self.execute("SELECT id FROM users WHERE username = 'Coward'")[0][0]
        self.post(self.client, "/admin/users/delete", user_id=str(coward_id),
                  confirm_username="Coward", current_password="test-password")
        self.assertTrue(self.execute("SELECT id FROM users WHERE id = ?", (coward_id,)))
        self.assertTrue(self.execute("SELECT id FROM users WHERE id = ?", (target_id,)))

    def test_removing_post_and_comment_authors_separately(self):
        post_author = self.add_user("PostAuthor")
        comment_author = self.add_user("CommentAuthor")
        self.execute("INSERT INTO posts (user_id, title, body) VALUES (?, 'Post', 'post body')",
                     (post_author,))
        post_id = self.execute("SELECT id FROM posts WHERE user_id = ?", (post_author,))[0][0]
        self.execute(
            "INSERT INTO comments (user_id, post_id, body, image, edited_at) "
            "VALUES (?, ?, 'comment body', 'comment.png', datetime('now'))",
            (comment_author, post_id))
        comment_id = self.execute("SELECT id FROM comments WHERE user_id = ?", (comment_author,))[0][0]
        self.execute("INSERT INTO comments (user_id, post_id, body, parent_id) VALUES (?, ?, 'reply', ?)",
                     (self.admin_id, post_id, comment_id))
        original = self.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))[0]
        self.post(self.client, "/admin/users/delete", user_id=str(post_author),
                  confirm_username="PostAuthor", current_password="test-password")
        self.assertEqual(self.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))[0], original)
        page = self.client.get(f"/post/{post_id}").get_data(as_text=True)
        self.assertIn("CommentAuthor", page)
        self.assertIn("comment.png", page)
        self.post(self.client, "/admin/users/delete", user_id=str(comment_author),
                  confirm_username="CommentAuthor", current_password="test-password")
        coward = self.execute("SELECT id FROM users WHERE username = 'Coward'")[0][0]
        row = self.execute("SELECT user_id, body, image, edited_at FROM comments WHERE id = ?",
                           (comment_id,))[0]
        self.assertEqual(row[:3], (coward, "comment body\n\nOriginally by CommentAuthor", "comment.png"))
        self.assertIsNotNone(row[3])
        self.assertEqual(self.execute("SELECT parent_id FROM comments WHERE parent_id = ?", (comment_id,)),
                         [(comment_id,)])
        page = self.client.get(f"/post/{post_id}").get_data(as_text=True)
        self.assertIn("Originally by CommentAuthor", page)
        self.assertIn("comment.png", page)

    def test_password_change_keeps_current_session_and_revokes_other_sessions(self):
        other = self.blog.app.test_client()
        self.login(other, self.admin_id)
        response = self.post(self.client, "/settings/password", current_password="test-password",
                             new_password="new-password", confirm_password="new-password")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/explore").status_code, 200)
        self.assertEqual(other.get("/explore").status_code, 302)

    def test_snake_chains_reject_cycles_and_expose_both_neighbors(self):
        solution = "ΑΒ" + "#" * 13 + "ΓΔ" + "#" * 13 + "#" * (15 * 13)
        entries = self.blog.crossword_entries(solution)
        clues = {"A-0-0": "First ~!connD1", "D-0-0": "~!connA2", "A-1-0": "", "D-0-1": "Other"}
        connections, error = self.blog.crossword_connections(entries, clues)
        self.assertIsNone(error)
        self.assertEqual(connections, {"A-0-0": "D-0-0", "D-0-0": "A-1-0"})
        validated, _, error = self.blog.validate_crossword(
            "\n".join(solution[i:i + 15] for i in range(0, 225, 15)),
            json.dumps(clues, ensure_ascii=False))
        self.assertIsNone(error)
        view, _ = self.blog.crossword_view({"solution": validated, "clues": clues})
        by_key = {entry["key"]: entry for entry in view}
        self.assertEqual(by_key["A-0-0"]["lengths"], "4")
        self.assertEqual(by_key["D-0-0"]["lengths"], "3")
        self.assertEqual(by_key["D-0-1"]["lengths"], "2")
        self.assertEqual(by_key["D-0-0"]["previous"], "A-0-0")
        self.assertEqual(by_key["D-0-0"]["next"], "A-1-0")
        self.assertTrue(by_key["D-0-0"]["hidden"])
        clues["D-0-0"] = "~!connA1"
        self.assertIn("cycle", self.blog.crossword_connections(entries, clues)[1])
        clues["D-0-0"] = "~!connA2"
        clues["D-0-1"] = "~!connA2"
        self.assertIn("target", self.blog.crossword_connections(entries, clues)[1])

    def test_snake_lengths_count_nonadjacent_overlaps_and_disjoint_words(self):
        solution = "ΑΒ" + "#" * 13 + "ΓΔ" + "#" * 13 + "#" * (15 * 13)
        clues = {"A-0-0": "~!connD1", "D-0-0": "~!connA2", "A-1-0": "~!connD2"}
        view, cells = self.blog.crossword_view({"solution": solution, "clues": clues})
        by_key = {entry["key"]: entry for entry in view}
        self.assertEqual(by_key["A-0-0"]["lengths"], "4")
        self.assertEqual(cells, {0, 1, 15, 16})

        solution = "ΑΒ" + "#" * 13 + "#" * 15 + "##Γ" + "#" * 12 + "##Δ" + "#" * 12 + "#" * (15 * 11)
        clues = {"A-0-0": "~!connD1"}
        view, _ = self.blog.crossword_view({"solution": solution, "clues": clues})
        by_key = {entry["key"]: entry for entry in view}
        self.assertEqual(by_key["A-0-0"]["lengths"], "4")

    def test_bokopsaraki_game_and_score_lifecycle(self):
        player = self.add_user("Player")
        client = self.blog.app.test_client()
        self.login(client, player)
        self.assertNotIn("ΜΠΟΚΟΨΑΡΑΚΙΑ", client.get("/").get_data(as_text=True))
        self.assertEqual(self.post(client, "/admin/bokopsaraki", start_word="γάτα", end_word="καλά").status_code, 403)
        self.post(self.client, "/admin/bokopsaraki", start_word="γάτα", end_word="καλά")
        self.post(self.client, "/admin/bokopsaraki/toggle", enabled="1")
        self.assertIn("ΜΠΟΚΟΨΑΡΑΚΙΑ", client.get("/").get_data(as_text=True))
        page = client.get("/").get_data(as_text=True)
        self.assertIn('name="word_letter"', page)
        self.assertIn("Destination: <strong>ΚΑΛΑ</strong>", page)
        self.assertIn('aria-label="Γ">Γ</span>', page)
        cells = re.findall(r'<input[^>]*name="word_letter"[^>]*>', page)
        self.assertEqual(len(cells), 4)
        self.assertTrue(all('value=' not in cell for cell in cells))
        self.assertIn("Enter word", page)
        self.assertIn("Restart", page)
        self.assertIn("γαλα", self.blog.greek_dictionary())
        self.post(client, "/bokopsaraki/play", version="1", action="guess", word="ΓΆΛΑ")
        self.assertEqual(self.execute("SELECT current_word FROM bokopsaraki_progress WHERE user_id = ?", (player,)),
                         [("γαλα",)])
        page = client.get("/").get_data(as_text=True)
        cells = re.findall(r'<input[^>]*name="word_letter"[^>]*>', page)
        self.assertEqual(len(cells), 4)
        self.assertTrue(all('value=' not in cell for cell in cells))
        self.assertEqual(page.count('aria-label="Γ">Γ</span>'), 2)
        self.post(client, "/bokopsaraki/play", version="1", action="guess", word="γαλο")
        self.post(client, "/bokopsaraki/play", version="1", action="reset")
        self.assertEqual(self.execute("SELECT current_word FROM bokopsaraki_progress WHERE user_id = ?", (player,)),
                         [("γατα",)])
        page = client.get("/").get_data(as_text=True)
        self.assertEqual(page.count('aria-label="Γ">Γ</span>'), 1)
        self.assertEqual(len(re.findall(r'<input[^>]*name="word_letter"[^>]*>', page)), 4)
        self.post(client, "/bokopsaraki/play", version="1", action="guess", word="γαλα")
        self.post(client, "/bokopsaraki/play", version="1", action="guess", word="καλα")
        self.assertEqual(self.execute("SELECT solved FROM bokopsaraki_progress WHERE user_id = ?", (player,)), [(1,)])
        self.assertEqual(self.execute(
            "SELECT word FROM bokopsaraki_history WHERE user_id = ? ORDER BY id", (player,)),
            [("γαλα",), ("καλα",)])
        self.assertIn("red 🟘", client.get("/").get_data(as_text=True))
        self.assertIn(">🟘&#xFE0E;</span>", client.get("/u/Player").get_data(as_text=True))
        self.assertEqual(self.execute("SELECT bokopsaraki_victories FROM users WHERE id = ?", (player,)), [(1,)])
        self.assertIn("Solved the current ΜΠΟΚΟΨΑΡΑΚΙΑ", client.get("/u/Player").get_data(as_text=True))
        self.assertIn("Player", client.get("/scores?game=bokopsaraki").get_data(as_text=True))
        self.post(client, "/bokopsaraki/play", version="1", action="reset")
        self.assertFalse(self.execute("SELECT * FROM bokopsaraki_history WHERE user_id = ?", (player,)))
        self.post(client, "/bokopsaraki/play", version="1", action="guess", word="γαλα")
        self.post(client, "/bokopsaraki/play", version="1", action="guess", word="καλα")
        self.assertEqual(self.execute("SELECT bokopsaraki_victories FROM users WHERE id = ?", (player,)), [(1,)])
        self.post(self.client, "/admin/bokopsaraki", start_word="γάτα", end_word="καβά")
        self.assertNotIn("Solved the current ΜΠΟΚΟΨΑΡΑΚΙΑ", client.get("/u/Player").get_data(as_text=True))
        self.post(client, "/bokopsaraki/play", version="1", action="guess", word="γαλα")
        self.assertFalse(self.execute("SELECT * FROM bokopsaraki_progress WHERE user_id = ?", (player,)))
        self.assertFalse(self.execute("SELECT * FROM bokopsaraki_history WHERE user_id = ?", (player,)))
        self.assertEqual(self.execute("SELECT bokopsaraki_victories FROM users WHERE id = ?", (player,)), [(1,)])

    def test_bokopsaraki_custom_word_and_invalid_moves(self):
        player = self.add_user("Player")
        client = self.blog.app.test_client()
        self.login(client, player)
        self.post(self.client, "/admin/bokopsaraki", start_word="γατα", end_word="καβα")
        self.post(self.client, "/admin/bokopsaraki/toggle", enabled="1")
        self.post(client, "/bokopsaraki/play", version="1", action="guess", word="abc")
        self.post(client, "/bokopsaraki/play", version="1", action="guess", word="καβα")
        self.assertFalse(self.execute("SELECT * FROM bokopsaraki_progress WHERE user_id = ?", (player,)))
        self.post(self.client, "/admin/bokopsaraki/words", action="add", word="ΓΆΒΑ")
        self.post(client, "/bokopsaraki/play", version="1", action="guess", word="γαβα")
        self.assertEqual(self.execute("SELECT current_word FROM bokopsaraki_progress WHERE user_id = ?", (player,)),
                         [("γαβα",)])
        self.post(client, "/bokopsaraki/play", version="1", action="guess", word="καβα")
        self.assertEqual(self.execute("SELECT solved FROM bokopsaraki_progress WHERE user_id = ?", (player,)), [(1,)])
        self.post(self.client, "/admin/bokopsaraki/words", action="remove", word="γαβα")
        self.assertFalse(self.execute("SELECT word FROM bokopsaraki_words"))

    def test_bokopsaraki_unknown_words_hidden_game_and_score_editing(self):
        player = self.add_user("Player")
        client = self.blog.app.test_client()
        self.login(client, player)
        self.post(self.client, "/admin/bokopsaraki", start_word="αααααααα", end_word="ββαααααα")
        self.post(self.client, "/admin/bokopsaraki/toggle", enabled="1")
        self.assertNotIn("βααααααα", self.blog.greek_dictionary())
        response = self.post(client, "/bokopsaraki/play", version="1", action="guess", word="βααααααα")
        self.assertIn("not in the Greek wordlist", client.get(response.location).get_data(as_text=True))
        self.assertFalse(self.execute("SELECT * FROM bokopsaraki_progress WHERE user_id = ?", (player,)))
        self.post(self.client, "/admin/bokopsaraki/words", action="add", word="βααααααα")
        self.post(self.client, "/admin/bokopsaraki/toggle", enabled="0")
        self.post(client, "/bokopsaraki/play", version="1", action="guess", word="βααααααα")
        self.assertFalse(self.execute("SELECT * FROM bokopsaraki_progress WHERE user_id = ?", (player,)))
        self.post(self.client, "/admin/scores", user_id=str(player), bokword_victories="1",
                  boknections_victories="2", bokopsaraki_victories="3")
        self.assertEqual(self.execute(
            "SELECT bokword_victories, boknections_victories, bokopsaraki_victories FROM users WHERE id = ?",
            (player,)), [(1, 2, 3)])
        self.assertIn("3 victories", client.get("/scores?game=bokopsaraki").get_data(as_text=True))

    def test_letter_cell_submission_and_legacy_progress(self):
        player = self.add_user("Player")
        client = self.blog.app.test_client()
        self.login(client, player)
        self.post(self.client, "/admin/bokopsaraki",
                  start_word_letter=["γ", "ά", "τ", "α"], end_word_letter=["κ", "α", "λ", "ά"])
        self.post(self.client, "/admin/bokopsaraki/toggle", enabled="1")
        self.execute("INSERT INTO bokopsaraki_progress (user_id, puzzle_version, current_word) VALUES (?, 1, ?)",
                     (player, "γαλα"))
        page = client.get("/").get_data(as_text=True)
        self.assertEqual(page.count('name="word_letter"'), 4)
        self.assertEqual(page.count('class="crossword-square" aria-label='), 8)
        self.post(client, "/bokopsaraki/play", version="1", action="guess",
                  word_letter=["κ", "α", "", "α"])
        self.assertFalse(self.execute("SELECT * FROM bokopsaraki_history WHERE user_id = ?", (player,)))
        self.post(client, "/bokopsaraki/play", version="1", action="guess",
                  word_letter=["κ", "α", "λ", "ά"])
        self.assertEqual(self.execute("SELECT word FROM bokopsaraki_history WHERE user_id = ? ORDER BY id", (player,)),
                         [("γαλα",), ("καλα",)])
        self.post(self.client, "/admin/bokopsaraki/words", action="add",
                  word_letter=["γ", "ά", "β", "α"])
        self.assertEqual(self.execute("SELECT word FROM bokopsaraki_words"), [("γαβα",)])
        admin = self.client.get("/admin").get_data(as_text=True)
        self.assertEqual(admin.count('name="start_word_letter"'), 4)
        self.assertEqual(admin.count('name="end_word_letter"'), 4)
        self.assertIn('name="start_word_letter" type="text" maxlength="1" value="Γ"', admin)
        self.assertIn("<li>ΓΑΒΑ", admin)

    def test_home_game_order_with_both_games_enabled(self):
        self.post(self.client, "/admin/bokopsaraki", start_word="γάτα", end_word="καλά")
        self.post(self.client, "/admin/bokopsaraki/toggle", enabled="1")
        self.post(self.client, "/admin/boknections/toggle", enabled="1")
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn('>Wild Card Boknections</h2>', page)
        self.assertIn('>ΜΠΟΚΟΨΑΡΑΚΙΑ</h2>', page)
        self.assertIn("Reach the destination word by changing one letter at a time. Every step must be a real word, some slang included. All capitals, all accents are ignored. Solve for a red 🟘 by your name", page)
        self.assertIn('<section class="bokword" aria-labelledby="bokword-title">', page)
        self.assertIn('<section class="boknections" id="boknections"', page)
        self.assertIn('<section class="boknections" id="bokopsaraki"', page)
        self.assertLess(page.index('aria-labelledby="bokword-title"'), page.index('id="boknections"'))
        self.assertLess(page.index('id="boknections"'), page.index('id="bokopsaraki"'))

    def test_self_deletion_reuses_cleanup_and_real_login_works(self):
        target_id = self.add_user("Target", avatar="avatar.png")
        (Path(self.blog.UPLOAD_DIR) / "avatar.png").write_bytes(b"image")
        self.execute("INSERT INTO settings (key, value) VALUES ('guest_author_bokword', ?)",
                     (str(target_id),))
        self.execute("INSERT INTO posts (user_id, title, body) VALUES (?, 'Self post', 'self body')", (target_id,))
        post_id = self.execute("SELECT id FROM posts WHERE user_id = ?", (target_id,))[0][0]
        self.execute("INSERT INTO comments (user_id, post_id, body) VALUES (?, ?, 'self comment')",
                     (target_id, post_id))
        target_client = self.blog.app.test_client()
        target_client.get("/login")
        with target_client.session_transaction() as session:
            csrf = session["csrf"]
        response = target_client.post("/login", data={
            "csrf_token": csrf, "username": "Target", "password": "test-password"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(target_client.get("/explore").status_code, 200)
        with target_client.session_transaction() as session:
            csrf = session["csrf"]
        response = target_client.post("/settings/delete", data={
            "csrf_token": csrf, "current_password": "test-password"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.execute("SELECT id FROM users WHERE id = ?", (target_id,)))
        self.assertEqual(self.execute("SELECT body FROM posts WHERE id = ?", (post_id,)),
                         [("self body\n\nOriginally by Target",)])
        self.assertEqual(self.execute(
            "SELECT u.username FROM comments c JOIN users u ON u.id = c.user_id WHERE c.post_id = ?",
            (post_id,)), [("Coward",)])
        self.assertEqual(self.execute("SELECT body FROM comments WHERE post_id = ?", (post_id,)),
                         [("self comment\n\nOriginally by Target",)])
        self.assertFalse(self.execute("SELECT key FROM settings WHERE key = 'guest_author_bokword'"))
        self.assertFalse((Path(self.blog.UPLOAD_DIR) / "avatar.png").exists())
        self.assertEqual(target_client.get("/explore").status_code, 302)

    def test_coward_cannot_log_in_or_use_existing_session(self):
        coward_id = self.execute("SELECT id FROM users WHERE username = 'Coward'")[0][0]
        client = self.blog.app.test_client()
        client.get("/login")
        with client.session_transaction() as session:
            csrf = session["csrf"]
        response = client.post("/login", data={
            "csrf_token": csrf, "username": "Coward", "password": "IDELETECOMMENT"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.get("/explore").status_code, 302)
        self.login(client, coward_id)
        self.assertEqual(client.get("/explore").status_code, 302)

    def test_existing_deleted_comment_placeholders_remain_deleted_after_migration(self):
        coward_id = self.execute("SELECT id FROM users WHERE username = 'Coward'")[0][0]
        self.execute("INSERT INTO posts (user_id, title, body) VALUES (?, 'post', 'body')", (self.admin_id,))
        post_id = self.execute("SELECT id FROM posts")[0][0]
        self.execute("ALTER TABLE comments DROP COLUMN is_deleted")
        self.execute("INSERT INTO comments (user_id, post_id, body) VALUES (?, ?, 'I deleted my comment')",
                     (coward_id, post_id))
        comment_id = self.execute("SELECT id FROM comments")[0][0]
        self.execute("INSERT INTO comments (user_id, post_id, body, parent_id) VALUES (?, ?, 'reply', ?)",
                     (self.admin_id, post_id, comment_id))
        reply_id = self.execute("SELECT id FROM comments WHERE parent_id = ?", (comment_id,))[0][0]
        self.blog.migrate_db()
        self.assertEqual(self.execute("SELECT is_deleted FROM comments WHERE id = ?", (comment_id,)), [(1,)])
        self.assertEqual(self.post(self.client, f"/comment/{comment_id}/edit", body="changed").status_code, 403)
        self.assertEqual(self.post(self.client, f"/comment/{reply_id}/delete").status_code, 302)
        self.assertFalse(self.execute("SELECT id FROM comments WHERE id = ?", (comment_id,)))

    def test_transfer_rolls_back_if_account_deletion_fails(self):
        target_id = self.add_user("Target", avatar="avatar.png")
        (Path(self.blog.UPLOAD_DIR) / "avatar.png").write_bytes(b"image")
        self.execute("INSERT INTO posts (user_id, title, body) VALUES (?, 'title', 'body')", (target_id,))
        self.execute("INSERT INTO comments (user_id, post_id, body) SELECT ?, id, 'comment' FROM posts",
                     (target_id,))
        self.execute(
            "CREATE TRIGGER reject_user_deletion BEFORE DELETE ON users "
            "BEGIN SELECT RAISE(ABORT, 'delete failed'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.post(self.client, "/admin/users/delete", user_id=str(target_id),
                      confirm_username="Target", current_password="test-password")
        self.assertEqual(self.execute("SELECT user_id, body FROM posts"), [(target_id, "body")])
        self.assertEqual(self.execute("SELECT user_id, body FROM comments"), [(target_id, "comment")])
        self.assertTrue(self.execute("SELECT id FROM users WHERE id = ?", (target_id,)))
        self.assertTrue((Path(self.blog.UPLOAD_DIR) / "avatar.png").exists())


if __name__ == "__main__":
    unittest.main()
