import os, sys, tempfile, unittest
from pathlib import Path

_tmp = tempfile.TemporaryDirectory()
os.environ["ULEARN_DB"] = str(Path(_tmp.name) / "ulearn.db")
os.environ["COURSES_ROOT"] = str(Path(_tmp.name) / "courses")
os.environ["SECRET_KEY"] = "test-only-secret-key-that-is-long-enough"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
import db
import main

class SecurityHelpersTest(unittest.TestCase):
    def test_ranges(self):
        self.assertEqual(main._parse_single_range("bytes=0-99", 1000), (0, 99))
        self.assertEqual(main._parse_single_range("bytes=900-", 1000), (900, 999))
        self.assertEqual(main._parse_single_range("bytes=-100", 1000), (900, 999))
        self.assertIsNone(main._parse_single_range("bytes=1000-", 1000))
        self.assertIsNone(main._parse_single_range("bytes=20-10", 1000))
        self.assertIsNone(main._parse_single_range("bytes=0-1,4-5", 1000))
        self.assertIsNone(main._parse_single_range("bytes=" + "9" * 100 + "-", 1000))

    def test_acl_admin_and_member(self):
        db.init_db()
        with db.get_conn() as conn:
            admin = conn.execute("INSERT INTO users(username,is_admin) VALUES('admin',1)").lastrowid
            member = conn.execute("INSERT INTO users(username,is_admin) VALUES('member',0)").lastrowid
            course = conn.execute("INSERT INTO courses(folder_path,title) VALUES('c','Course')").lastrowid
            self.assertTrue(main._can_access_course(conn, {"sub": str(admin), "is_admin": True}, course))
            self.assertFalse(main._can_access_course(conn, {"sub": str(member), "is_admin": False}, course))
            conn.execute("INSERT INTO course_access(user_id,course_id,granted_by) VALUES(?,?,?)", (member, course, admin))
            self.assertTrue(main._can_access_course(conn, {"sub": str(member), "is_admin": False}, course))

    def test_safe_path_rejects_escape(self):
        Path(os.environ["COURSES_ROOT"]).mkdir()
        self.assertEqual(main._safe_course_path("folder/video.mp4"), str(Path(os.environ["COURSES_ROOT"]) / "folder/video.mp4"))
        with self.assertRaises(Exception):
            main._safe_course_path("../secret")

if __name__ == "__main__": unittest.main()
