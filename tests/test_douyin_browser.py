import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from douyin_browser import (
    cookies_for_browser,
    parse_post,
    parse_post_response,
    safe_name,
)

try:
    import playwright.sync_api  # noqa: F401
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


def _aweme(aweme_id: str, **extra) -> dict:
    base = {
        "aweme_id": aweme_id,
        "desc": f"作品 {aweme_id}",
        "create_time": 1_700_000_000 + int(aweme_id),
        "author": {"nickname": "测试作者"},
        "video": {
            "play_addr": {"url_list": [f"//v.example/playwm/{aweme_id}.mp4"]},
            "bit_rate": [
                {"bit_rate": 900, "play_addr": {"url_list": [f"http://v.example/hi/{aweme_id}.mp4"]}},
                {"bit_rate": 300, "play_addr": {"url_list": [f"http://v.example/lo/{aweme_id}.mp4"]}},
            ],
        },
    }
    base.update(extra)
    return base


class ParsePostTests(unittest.TestCase):
    def test_highest_bit_rate_comes_first_and_watermark_is_dropped(self):
        post = parse_post(_aweme("1"))
        self.assertEqual(post.video_urls[0], "https://v.example/hi/1.mp4")
        self.assertIn("https://v.example/play/1.mp4", post.video_urls)
        self.assertNotIn("playwm", " ".join(post.video_urls))

    def test_image_post_has_images_and_no_video(self):
        raw = _aweme("2", video={}, images=[{"url_list": ["https://i.example/a.jpg"]}])
        post = parse_post(raw)
        self.assertEqual(post.image_urls, ["https://i.example/a.jpg"])
        self.assertEqual(post.video_urls, [])

    def test_entry_without_media_is_skipped(self):
        self.assertIsNone(parse_post({"aweme_id": "3", "video": {}}))
        self.assertIsNone(parse_post({"video": {}}))

    def test_response_reports_has_more(self):
        posts, has_more = parse_post_response({"aweme_list": [_aweme("4")], "has_more": 1})
        self.assertEqual(len(posts), 1)
        self.assertTrue(has_more)
        self.assertEqual(parse_post_response({"aweme_list": None, "has_more": 0}), ([], False))

    def test_safe_name_strips_path_characters(self):
        self.assertEqual(safe_name('a/b:c*?"d'), "a b c d")
        self.assertEqual(safe_name("   "), "untitled")


class CookieConversionTests(unittest.TestCase):
    def test_httponly_and_session_cookies_are_converted(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "douyin_cookies.txt"
            path.write_text(
                "# Netscape HTTP Cookie File\n"
                "#HttpOnly_.douyin.com\tTRUE\t/\tTRUE\t2000000000\tsessionid\tabc\n"
                ".douyin.com\tTRUE\t/\tFALSE\t0\tttwid\tdef\n"
                ".example.com\tTRUE\t/\tFALSE\t0\tother\tx\n",
                encoding="utf-8",
            )
            cookies = {c["name"]: c for c in cookies_for_browser(path)}

        self.assertEqual(set(cookies), {"sessionid", "ttwid"})
        self.assertTrue(cookies["sessionid"]["httpOnly"])
        self.assertEqual(cookies["sessionid"]["expires"], 2_000_000_000)
        self.assertEqual(cookies["ttwid"]["expires"], -1)


PAGES = [
    {"aweme_list": [_aweme("1"), _aweme("2")], "has_more": 1},
    {"aweme_list": [_aweme("3"), _aweme("4")], "has_more": 1},
    {"aweme_list": [_aweme("5")], "has_more": 0},
]

PROFILE_HTML = """<!doctype html><html><body style="margin:0">
<div style="height:6000px">profile</div>
<script>
let page = 0, busy = false;
async function more() {
  if (busy || page >= 3) return;
  busy = true;
  await fetch('/aweme/v1/web/aweme/post/?cursor=' + page);
  page += 1; busy = false;
}
more();
window.addEventListener('scroll', more);
window.addEventListener('wheel', more);
</script></body></html>"""


WALL_HTML = "<!doctype html><html><body><h1>登录后免费畅享高清视频</h1></body></html>"


class _MockDouyin(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/user/WALL"):
            body = WALL_HTML.encode()
            content_type = "text/html; charset=utf-8"
        elif self.path.startswith("/aweme/v1/web/aweme/post/"):
            cursor = int(self.path.split("cursor=")[1])
            body = json.dumps(PAGES[cursor]).encode()
            content_type = "application/json"
        else:
            body = PROFILE_HTML.encode()
            content_type = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


@unittest.skipUnless(HAS_PLAYWRIGHT, "playwright is not installed")
class BrowserCollectionTests(unittest.TestCase):
    def test_scrolling_collects_every_page_until_has_more_is_false(self):
        from douyin_browser import collect_profile_posts

        server = ThreadingHTTPServer(("127.0.0.1", 0), _MockDouyin)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)

        messages = []
        posts = collect_profile_posts(
            "MS4wLjABAAAA_example",
            Path("/nonexistent"),
            lambda count, message: messages.append((count, message)),
            base_url=f"http://127.0.0.1:{server.server_address[1]}",
            channel="chrome",
            headless=True,
            first_batch_timeout=20,
            idle_timeout=10,
            total_timeout=60,
        )

        self.assertEqual(sorted(p.aweme_id for p in posts), ["1", "2", "3", "4", "5"])
        self.assertEqual(posts[0].aweme_id, "5")
        self.assertEqual(messages[-1][0], 5)

    def test_login_wall_raises_login_required(self):
        from douyin_browser import LoginRequired, collect_profile_posts

        server = ThreadingHTTPServer(("127.0.0.1", 0), _MockDouyin)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)

        with self.assertRaises(LoginRequired):
            collect_profile_posts(
                "WALL",
                Path("/nonexistent"),
                lambda *_a: None,
                base_url=f"http://127.0.0.1:{server.server_address[1]}",
                channel="chrome",
                headless=True,
                first_batch_timeout=6,
                idle_timeout=5,
                total_timeout=30,
            )


if __name__ == "__main__":
    unittest.main()
