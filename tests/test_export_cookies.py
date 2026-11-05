import unittest
from http.cookiejar import Cookie
from pathlib import Path
from tempfile import TemporaryDirectory

from export_cookies import _write_netscape, netscape_cookie_names


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


if __name__ == "__main__":
    unittest.main()
