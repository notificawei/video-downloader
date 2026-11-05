import csv
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import yt_dlp

from douyin_browser import DouyinPost
from downloader import (
    DownloadProgress,
    _download_first_working,
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

    @patch.dict("sys.modules", {"yt_dlp_ejs": None})
    def test_missing_challenge_solver_is_fetched_remotely(self):
        with TemporaryDirectory() as output_dir:
            downloader = VideoDownloader(output_dir=output_dir)
            opts = downloader._build_ydl_opts("best", DownloadProgress(), "youtube")

        self.assertEqual(opts.get("remote_components"), ["ejs:github"])
        with yt_dlp.YoutubeDL(opts):
            pass

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

    def test_logged_in_cookie_points_to_the_browser_window(self):
        message = _douyin_failure_message(0, 0, [], "sessionid=abc; ttwid=def")
        self.assertIn("Chrome 窗口", message)
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
    @patch("downloader._load_douyin_cookie_string", return_value="sessionid=abc")
    def test_profile_download_saves_every_post(self, _cookie, _codec):
        posts = [
            DouyinPost("1", desc="第一条", create_time=1_700_000_000, nickname="作者",
                       video_urls=["https://v.example/1.mp4"]),
            DouyinPost("2", desc="图文", create_time=1_700_000_100, nickname="作者",
                       image_urls=["https://i.example/a.jpg", "https://i.example/b.jpg"]),
        ]

        def fake_download(urls, target, headers):
            target.write_bytes(b"data")
            return True

        with TemporaryDirectory() as output_dir:
            downloader = VideoDownloader(output_dir=output_dir)
            progress = DownloadProgress()
            with patch.object(VideoDownloader, "_collect_douyin_posts", return_value=posts), \
                 patch("downloader._download_first_working", side_effect=fake_download):
                downloader._run_douyin_profile_download(
                    "https://www.douyin.com/user/MS4wLjABAAAA_example", progress,
                )
            saved = sorted(p.name for p in (Path(output_dir) / "抖音" / "作者").iterdir())

        self.assertEqual(progress.status, "done")
        self.assertEqual(progress.completed_items, 2)
        self.assertEqual(progress.total_items, 2)
        self.assertEqual(len(saved), 3)
        self.assertTrue(any(name.endswith(".mp4") for name in saved))

    @patch("downloader._load_douyin_cookie_string", return_value="sessionid=abc")
    def test_empty_post_list_reports_actionable_error(self, _cookie):
        with TemporaryDirectory() as output_dir:
            downloader = VideoDownloader(output_dir=output_dir)
            progress = DownloadProgress()
            with patch.object(VideoDownloader, "_collect_douyin_posts", return_value=[]):
                downloader._run_douyin_profile_download(
                    "https://www.douyin.com/user/MS4wLjABAAAA_example", progress,
                )

        self.assertEqual(progress.status, "error")
        self.assertIn("Chrome", progress.error)

    @patch("downloader._load_douyin_cookie_string", return_value="sessionid=abc")
    def test_existing_files_are_not_downloaded_again(self, _cookie):
        post = DouyinPost("9", desc="已有", create_time=1_700_000_000, nickname="作者",
                          video_urls=["https://v.example/9.mp4"])
        with TemporaryDirectory() as output_dir:
            folder = Path(output_dir) / "抖音" / "作者"
            folder.mkdir(parents=True)
            stamp = datetime.fromtimestamp(1_700_000_000).strftime("%Y%m%d")
            (folder / f"{stamp}_9_已有.mp4").write_bytes(b"old")
            downloader = VideoDownloader(output_dir=output_dir)
            progress = DownloadProgress()
            with patch.object(VideoDownloader, "_collect_douyin_posts", return_value=[post]), \
                 patch("downloader._download_first_working") as fetch:
                downloader._run_douyin_profile_download(
                    "https://www.douyin.com/user/MS4wLjABAAAA_example", progress,
                )

        fetch.assert_not_called()
        self.assertEqual(progress.completed_items, 1)

    @patch("downloader._load_douyin_cookie_string", return_value=None)
    def test_missing_login_is_refused_before_opening_chrome(self, _cookie):
        with TemporaryDirectory() as output_dir:
            downloader = VideoDownloader(output_dir=output_dir)
            progress = DownloadProgress()
            with patch.object(VideoDownloader, "_collect_douyin_posts") as collect:
                downloader._run_douyin_profile_download(
                    "https://www.douyin.com/user/MS4wLjABAAAA_example", progress,
                )

        collect.assert_not_called()
        self.assertEqual(progress.status, "error")
        self.assertIn("从浏览器读取登录", progress.error)

    def test_download_tries_next_url_when_first_fails(self):
        class Response:
            def __init__(self, status, body=b""):
                self.status_code = status
                self._body = body

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def iter_content(self, chunk_size):
                yield self._body

        responses = [Response(403), Response(200, b"video-bytes")]
        with TemporaryDirectory() as tmp, patch("downloader.requests.get", side_effect=responses):
            target = Path(tmp) / "clip.mp4"
            ok = _download_first_working(["https://a/x", "https://b/x"], target, {})
            data = target.read_bytes() if target.exists() else b""
            leftovers = [p.name for p in Path(tmp).iterdir() if p.name.endswith(".part")]

        self.assertTrue(ok)
        self.assertEqual(data, b"video-bytes")
        self.assertEqual(leftovers, [])

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
