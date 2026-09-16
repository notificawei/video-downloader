import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from downloader import (
    DownloadProgress,
    VideoDownloader,
    _read_netscape_cookie_string,
    is_douyin_profile_url,
)


class DouyinProfileUrlTests(unittest.TestCase):
    def test_direct_profile_url(self):
        self.assertTrue(is_douyin_profile_url(
            "https://www.douyin.com/user/MS4wLjABAAAA_example"
        ))

    def test_share_profile_url(self):
        self.assertTrue(is_douyin_profile_url(
            "https://www.iesdouyin.com/share/user/MS4wLjABAAAA_example"
        ))

    def test_single_video_url(self):
        self.assertFalse(is_douyin_profile_url(
            "https://www.douyin.com/video/1234567890"
        ))

    @patch("downloader.requests.get")
    def test_short_profile_url_is_resolved(self, get):
        get.return_value = Mock(
            url="https://www.douyin.com/user/MS4wLjABAAAA_example"
        )
        self.assertTrue(is_douyin_profile_url("https://v.douyin.com/abc123/"))

    def test_profile_info_does_not_use_single_video_extractor(self):
        info = VideoDownloader().get_info(
            "https://www.douyin.com/user/MS4wLjABAAAA_example"
        )
        self.assertTrue(info["is_profile"])
        self.assertEqual(info["platform"], "douyin")

    @patch("downloader._load_douyin_cookie_string", return_value=None)
    @patch("downloader.subprocess.Popen")
    def test_profile_download_invokes_f2_post_mode(self, popen, _cookie):
        saved_file = {}

        def fake_popen(command, **kwargs):
            # Simulate F2 writing one post into the output directory.
            (saved_file["dir"] / "clip.mp4").write_bytes(b"data")
            process = Mock()
            process.stdout = []
            process.wait.return_value = 0
            return process

        popen.side_effect = fake_popen

        with TemporaryDirectory() as output_dir:
            saved_file["dir"] = Path(output_dir)
            downloader = VideoDownloader(output_dir=output_dir)
            progress = DownloadProgress()
            downloader._run_douyin_profile_download(
                "https://www.douyin.com/user/MS4wLjABAAAA_example",
                progress,
                cookies_from_browser="chrome",
            )

        command = popen.call_args.args[0]
        self.assertIn("post", command)
        self.assertIn("--auto-cookie", command)
        self.assertIn("chrome", command)
        self.assertEqual(progress.status, "done")
        self.assertEqual(progress.completed_items, 1)

    @patch("downloader._load_douyin_cookie_string", return_value="sessionid=abc")
    @patch("downloader.subprocess.Popen")
    def test_cookie_file_is_passed_to_f2(self, popen, _cookie):
        process = Mock()
        process.stdout = []
        process.wait.return_value = 0
        popen.return_value = process

        with TemporaryDirectory() as output_dir:
            downloader = VideoDownloader(output_dir=output_dir)
            downloader._run_douyin_profile_download(
                "https://www.douyin.com/user/MS4wLjABAAAA_example",
                DownloadProgress(),
            )

        command = popen.call_args.args[0]
        self.assertIn("--cookie", command)
        self.assertIn("sessionid=abc", command)
        self.assertNotIn("--auto-cookie", command)

    @patch("downloader._load_douyin_cookie_string", return_value=None)
    @patch("downloader.subprocess.Popen")
    def test_zero_saved_items_reports_error(self, popen, _cookie):
        process = Mock()
        process.stdout = []
        process.wait.return_value = 0
        popen.return_value = process

        with TemporaryDirectory() as output_dir:
            downloader = VideoDownloader(output_dir=output_dir)
            progress = DownloadProgress()
            downloader._run_douyin_profile_download(
                "https://www.douyin.com/user/MS4wLjABAAAA_example",
                progress,
            )

        self.assertEqual(progress.status, "error")
        self.assertIn("douyin_cookies.txt", progress.error)

    def test_netscape_cookie_file_is_flattened(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "douyin_cookies.txt"
            path.write_text(
                "# Netscape HTTP Cookie File\n"
                ".douyin.com\tTRUE\t/\tTRUE\t0\tsessionid\tabc123\n"
                "#HttpOnly_.douyin.com\tTRUE\t/\tTRUE\t0\tttwid\tdef456\n"
                ".example.com\tTRUE\t/\tTRUE\t0\tother\tignored\n",
                encoding="utf-8",
            )
            cookie = _read_netscape_cookie_string(path, "douyin.com")

        self.assertIn("sessionid=abc123", cookie)
        self.assertIn("ttwid=def456", cookie)
        self.assertNotIn("ignored", cookie)


if __name__ == "__main__":
    unittest.main()
