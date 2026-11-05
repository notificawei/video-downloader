import unittest
from http.cookiejar import Cookie
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from export_cookies import (
    LoginCookieMissing,
    _write_netscape,
    douyin_login_status,
    export_douyin_from_app,
    netscape_cookie_names,
)


def _cookie(name: str, *, http_only: bool = False) -> Cookie:
    return Cookie(
        version=0,
        name=name,
        value="secret",
        port=None,
        port_specified=False,
        domain=".douyin.com",
        domain_specified=True,
        domain_initial_dot=True,
        path="/",
        path_specified=True,
        secure=True,
        expires=2_000_000_000,
        discard=False,
        comment=None,
        comment_url=None,
        rest={"HTTPOnly": ""} if http_only else {},
        rfc2109=False,
    )


class NetscapeCookieNamesTest(unittest.TestCase):
    def test_httponly_prefix_is_not_a_comment(self):
        text = (
            "# Netscape HTTP Cookie File\n"
            "#HttpOnly_.douyin.com\tTRUE\t/\tTRUE\t0\tsessionid\tsecret\n"
            ".douyin.com\tTRUE\t/\tFALSE\t0\tttwid\tabc\n"
        )
        self.assertEqual(netscape_cookie_names(text), {"sessionid", "ttwid"})

    def test_saved_httponly_sessionid_is_detected(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "douyin_cookies.txt"
            count = _write_netscape(path, [_cookie("sessionid", http_only=True)])
            text = path.read_text(encoding="utf-8")

        self.assertEqual(count, 1)
        self.assertIn("sessionid", netscape_cookie_names(text))
        self.assertIn("#HttpOnly_", text)

    def test_login_status_accepts_httponly_sessionid(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "douyin_cookies.txt"
            path.write_text(
                "#HttpOnly_.douyin.com\tTRUE\t/\tTRUE\t0\tsessionid\tsecret\n",
                encoding="utf-8",
            )
            status = douyin_login_status(path)

        self.assertTrue(status["logged_in"])

    def test_missing_file_is_logged_out(self):
        status = douyin_login_status(Path("/tmp/does-not-exist-videoget-cookie.txt"))
        self.assertFalse(status["logged_in"])

    @patch("export_cookies.douyin_login_status", return_value={"logged_in": True, "message": "ok"})
    @patch("export_cookies.export_with_browser_cookie3")
    def test_app_export_uses_direct_read(self, _export, _status):
        result = export_douyin_from_app("chrome")
        self.assertTrue(result["ok"])
        self.assertTrue(result["logged_in"])

    @patch("export_cookies._open_terminal_export", return_value=True)
    @patch("export_cookies._export_via_osascript", return_value="keychain")
    @patch("export_cookies.douyin_login_status", return_value={"logged_in": False, "message": "no"})
    @patch("export_cookies.export_with_browser_cookie3", side_effect=RuntimeError("keychain"))
    def test_app_export_opens_terminal_when_keychain_blocks(self, _export, _status, _dialog, opener):
        result = export_douyin_from_app("chrome")
        self.assertTrue(result["pending"])
        opener.assert_called_once()

    @patch("export_cookies.douyin_login_status", return_value={"logged_in": False, "message": "no"})
    @patch("export_cookies.export_with_browser_cookie3", side_effect=LoginCookieMissing("no session"))
    def test_missing_login_does_not_open_a_window(self, _export, _status):
        with patch("export_cookies._open_terminal_export") as opener:
            result = export_douyin_from_app("chrome")
        opener.assert_not_called()
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
