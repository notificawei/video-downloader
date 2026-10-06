import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import yt_dlp

from downloader import (
    DownloadProgress,
    VideoDownloader,
    _douyin_failure_message,
    _parse_cookie_file,
    _read_netscape_cookie_string,
    _save_media_file,
    _youtube_attempts,
    _youtube_cookie_file,
    is_douyin_profile_url,
)


class DouyinProfileUrlTests(unittest.TestCase):
    def test_completed_download_is_listed_in_output_folder(self):
        with TemporaryDirectory() as output_dir:
            downloader = VideoDownloader(output_dir=output_dir)
            downloader._record_history(
                "https://v.douyin.com/xfQw7DwqGsc/",
                "clip.mp4",
            )
            downloader._record_history(
                "https://www.youtube.com/watch?v=abc",
                "video.mp4",
            )
            history = Path(output_dir) / "下载历史.csv"
            with history.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.reader(handle))

        self.assertEqual(rows[0], ["日期", "链接", "文件"])
        self.assertEqual(rows[1][1], "https://v.douyin.com/xfQw7DwqGsc/")
        self.assertEqual(rows[1][2], "clip.mp4")
        self.assertRegex(rows[1][0], r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")
        self.assertEqual(rows[2][1], "https://www.youtube.com/watch?v=abc")

    def test_youtube_runtime_option_is_a_dict(self):
        with TemporaryDirectory() as output_dir:
            downloader = VideoDownloader(output_dir=output_dir)
            opts = downloader._build_ydl_opts("best", DownloadProgress(), "youtube")
        runtime = opts.get("js_runtimes")
        if runtime is not None:
            self.assertIsInstance(runtime, dict)
            self.assertIn("path", next(iter(runtime.values())))
        self.assertIn(
            "-tv_downgraded",
            opts["extractor_args"]["youtube"]["player_client"],
        )
        with yt_dlp.YoutubeDL(opts):
            pass

    def test_youtube_tries_anonymous_before_browser_cookies(self):
        opts = {
            "format": "best",
            "cookiesfrombrowser": ("chrome",),
            "extractor_args": {"youtube": {"player_client": ["default"]}},
        }
        attempts = _youtube_attempts(opts)

        self.assertEqual(len(attempts), 2)
        self.assertNotIn("cookiesfrombrowser", attempts[0])
        self.assertNotIn("extractor_args", attempts[0])
        self.assertEqual(attempts[0]["format"], "best")
        self.assertIs(attempts[1], opts)

    def test_youtube_without_cookies_has_single_attempt(self):
        self.assertEqual(len(_youtube_attempts({"format": "best"})), 1)

    @patch("downloader.Path.home")
    def test_pasted_youtube_cookie_is_converted_for_yt_dlp(self, home):
        with TemporaryDirectory() as tmp:
            home.return_value = Path(tmp)
            (Path(tmp) / "youtube_cookies.txt").write_text(
                "VISITOR_INFO1_LIVE=abc; CONSENT=YES",
                encoding="utf-8",
            )
            dest = _youtube_cookie_file()
            text = Path(dest).read_text(encoding="utf-8")

        self.assertIn(".youtube.com\tTRUE\t/\tTRUE\t0\tVISITOR_INFO1_LIVE\tabc", text)

    def test_cookie_without_login_explains_missing_session(self):
        message = _douyin_failure_message(0, 0, [], "ttwid=abc")
        self.assertIn("sessionid", message)

    def test_logged_in_cookie_points_to_expiry_or_risk_control(self):
        message = _douyin_failure_message(0, 0, [], "sessionid=abc; ttwid=def")
        self.assertIn("风控", message)
        self.assertNotIn("缺少 sessionid", message)

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

    @patch("downloader.douyin_profile_name", return_value="中国人在朝鲜")
    def test_profile_info_does_not_use_single_video_extractor(self, _name):
        info = VideoDownloader().get_info(
            "https://www.douyin.com/user/MS4wLjABAAAA_example"
        )
        self.assertTrue(info["is_profile"])
        self.assertEqual(info["platform"], "douyin")
        self.assertEqual(info["uploader"], "中国人在朝鲜")

    @patch("downloader._video_codec", return_value="h264")
    @patch("downloader._load_douyin_cookie_string", return_value=None)
    @patch("downloader.subprocess.Popen")
    def test_profile_download_invokes_f2_post_mode(self, popen, _cookie, _codec):
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

        # subprocess.run() is built on Popen, so later ffprobe calls also land
        # in this mock; the F2 invocation is the first one.
        command = popen.call_args_list[0].args[0]
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

        command = popen.call_args_list[0].args[0]
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

    def test_pasted_cookie_header_is_accepted(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "douyin_cookies.txt"
            path.write_text("sessionid=abc123; ttwid=def456\n", encoding="utf-8")
            cookie = _parse_cookie_file(path, "douyin.com")

        self.assertEqual(cookie, "sessionid=abc123; ttwid=def456")

    @patch("downloader.subprocess.run")
    def test_failed_conversion_keeps_real_extension(self, run):
        run.return_value = Mock(returncode=1, stderr=b"Invalid data found")

        with TemporaryDirectory() as tmp, TemporaryDirectory() as out:
            src = Path(tmp) / "clip.webm"
            src.write_bytes(b"webm-bytes")
            saved = _save_media_file(src, Path(out))

            # A .webm renamed to .mp4 opens in nothing, so the real container
            # must survive a failed conversion.
            self.assertEqual(saved.suffix, ".webm")
            self.assertEqual(saved.read_bytes(), b"webm-bytes")
            self.assertFalse((Path(out) / "clip.mp4").exists())

    @patch("downloader.subprocess.run")
    def test_successful_conversion_produces_mp4(self, run):
        def fake_run(command, **kwargs):
            Path(command[-1]).write_bytes(b"converted")
            return Mock(returncode=0, stderr=b"")

        run.side_effect = fake_run

        with TemporaryDirectory() as tmp, TemporaryDirectory() as out:
            src = Path(tmp) / "clip.webm"
            src.write_bytes(b"webm-bytes")
            saved = _save_media_file(src, Path(out))

        self.assertEqual(saved.name, "clip.mp4")

    @patch("downloader.subprocess.run")
    def test_audio_download_is_not_renamed_to_mp4(self, run):
        with TemporaryDirectory() as tmp, TemporaryDirectory() as out:
            src = Path(tmp) / "song.m4a"
            src.write_bytes(b"audio")
            saved = _save_media_file(src, Path(out))

        self.assertEqual(saved.name, "song.m4a")
        run.assert_not_called()

    def test_netscape_file_still_parsed_by_generic_reader(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "douyin_cookies.txt"
            path.write_text(
                "# Netscape HTTP Cookie File\n"
                ".douyin.com\tTRUE\t/\tTRUE\t0\tsessionid\tabc123\n",
                encoding="utf-8",
            )
            cookie = _parse_cookie_file(path, "douyin.com")

        self.assertEqual(cookie, "sessionid=abc123")


if __name__ == "__main__":
    unittest.main()
