import unittest
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from downloader import DownloadProgress, VideoDownloader, is_douyin_profile_url


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

    @patch("downloader.subprocess.Popen")
    def test_profile_download_invokes_f2_post_mode(self, popen):
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
                cookies_from_browser="chrome",
            )

        command = popen.call_args.args[0]
        self.assertIn("post", command)
        self.assertIn("--auto-cookie", command)
        self.assertIn("chrome", command)
        self.assertEqual(progress.status, "done")


if __name__ == "__main__":
    unittest.main()
