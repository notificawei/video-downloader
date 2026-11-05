"""Read a Douyin profile's posts by letting a real Chrome load the page.

Douyin signs its list API (a_bogus) inside the page's own JavaScript, and that
signature changes often enough that third-party signers such as F2 return empty
bodies. Loading the profile in a real browser sidesteps this: the page signs its
own requests, and we only read the JSON responses it receives.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger(__name__)

POST_API_FRAGMENT = "/aweme/v1/web/aweme/post/"
DEFAULT_BASE_URL = "https://www.douyin.com"

# The first batch can take a while when Douyin shows a slider check, which the
# visible window lets the user solve by hand.
FIRST_BATCH_TIMEOUT = 120
IDLE_TIMEOUT = 25
TOTAL_TIMEOUT = 60 * 60


class BrowserUnavailable(RuntimeError):
    """Playwright or Chrome is missing or could not be started."""


class LoginRequired(RuntimeError):
    """Douyin showed its login wall, so the saved cookies are not accepted."""


LOGIN_WALL_TEXT = "登录后免费畅享高清视频"


@dataclass
class DouyinPost:
    aweme_id: str
    desc: str = ""
    create_time: int = 0
    nickname: str = ""
    video_urls: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)


def _absolute(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return url.replace("http://", "https://", 1) if url.startswith("http://") else url


def _unmarked(url: str) -> str:
    """Prefer the watermark-free variant of a play URL."""
    return _absolute(url).replace("/playwm/", "/play/")


def parse_post(raw: dict) -> Optional[DouyinPost]:
    """Turn one aweme_list entry into a post, or None when it has nothing to save."""
    aweme_id = str(raw.get("aweme_id") or "").strip()
    if not aweme_id:
        return None

    post = DouyinPost(
        aweme_id=aweme_id,
        desc=(raw.get("desc") or "").strip(),
        create_time=int(raw.get("create_time") or 0),
        nickname=((raw.get("author") or {}).get("nickname") or "").strip(),
    )

    images = raw.get("images") or []
    for image in images:
        urls = image.get("url_list") or []
        if urls:
            post.image_urls.append(_absolute(urls[0]))

    video = raw.get("video") or {}
    candidates: list[tuple[int, list[str]]] = []
    for item in video.get("bit_rate") or []:
        urls = (item.get("play_addr") or {}).get("url_list") or []
        if urls:
            candidates.append((int(item.get("bit_rate") or 0), urls))
    play_urls = (video.get("play_addr") or {}).get("url_list") or []
    if play_urls:
        candidates.append((0, play_urls))

    # Highest bit rate first, then every alternate host for that rendition.
    seen: set[str] = set()
    for _rate, urls in sorted(candidates, key=lambda c: c[0], reverse=True):
        for url in urls:
            clean = _unmarked(url)
            if clean not in seen:
                seen.add(clean)
                post.video_urls.append(clean)

    if not post.video_urls and not post.image_urls:
        return None
    return post


def parse_post_response(payload: dict) -> tuple[list[DouyinPost], bool]:
    """Return (posts, has_more) from one aweme/post response body."""
    posts = []
    for raw in payload.get("aweme_list") or []:
        post = parse_post(raw)
        if post:
            posts.append(post)
    return posts, bool(payload.get("has_more"))


def cookies_for_browser(path: Path) -> list[dict]:
    """Read a Netscape cookie file into Playwright's cookie format."""
    cookies = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        http_only = line.startswith("#HttpOnly_")
        if http_only:
            line = line[len("#HttpOnly_"):]
        elif line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) < 7:
            continue
        domain, _flag, cookie_path, secure, expires, name, value = fields[:7]
        if "douyin.com" not in domain.lower() or not name:
            continue
        cookie = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": cookie_path or "/",
            "secure": secure.upper() == "TRUE",
            "httpOnly": http_only,
        }
        try:
            stamp = int(float(expires))
        except ValueError:
            stamp = 0
        cookie["expires"] = stamp if stamp > 0 else -1
        cookies.append(cookie)
    return cookies


def ensure_playwright(log_line: Callable[[str], None] = lambda _m: None) -> None:
    """Import Playwright, installing it for this Python the first time."""
    try:
        import playwright.sync_api  # noqa: F401
        return
    except ImportError:
        pass

    log_line("首次使用：正在安装浏览器控制组件（约 1 分钟）…")
    command = [sys.executable, "-m", "pip", "install", "-U", "playwright"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=600)
    if result.returncode != 0 and "externally-managed" in (result.stderr or "").lower():
        result = subprocess.run(
            command + ["--break-system-packages"],
            capture_output=True, text=True, timeout=600,
        )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-1:]
        raise BrowserUnavailable(
            "无法自动安装 playwright：" + (tail[0] if tail else "未知错误")
        )
    import importlib
    importlib.invalidate_caches()
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError as error:
        raise BrowserUnavailable(f"playwright 安装后仍无法使用：{error}") from error


def collect_profile_posts(
    sec_user_id: str,
    cookie_file: Path,
    on_progress: Callable[[int, str], None],
    *,
    base_url: str = DEFAULT_BASE_URL,
    channel: Optional[str] = "chrome",
    headless: Optional[bool] = None,
    first_batch_timeout: float = FIRST_BATCH_TIMEOUT,
    idle_timeout: float = IDLE_TIMEOUT,
    total_timeout: float = TOTAL_TIMEOUT,
) -> list[DouyinPost]:
    """Open the profile in Chrome, scroll to the end, and return every post found."""
    ensure_playwright(lambda message: on_progress(0, message))
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    if headless is None:
        headless = os.environ.get("VIDEOGET_BROWSER_HEADLESS") == "1"

    cookies = cookies_for_browser(cookie_file) if cookie_file.is_file() else []
    posts: dict[str, DouyinPost] = {}
    pending: list = []
    state = {"has_more": True, "responses": 0}

    with sync_playwright() as pw:
        launch_args = {"headless": headless, "args": ["--disable-blink-features=AutomationControlled"]}
        try:
            browser = pw.chromium.launch(channel=channel, **launch_args)
        except PlaywrightError as error:
            if channel:
                log.warning("Chrome launch failed (%s); trying bundled Chromium", error)
                try:
                    browser = pw.chromium.launch(**launch_args)
                except PlaywrightError as inner:
                    raise BrowserUnavailable(
                        "无法启动浏览器。请确认已安装 Google Chrome。\n" + str(inner).splitlines()[0]
                    ) from inner
            else:
                raise BrowserUnavailable(str(error).splitlines()[0]) from error

        try:
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="zh-CN",
            )
            if cookies:
                context.add_cookies(cookies)
            page = context.new_page()
            page.on(
                "response",
                lambda response: pending.append(response)
                if POST_API_FRAGMENT in response.url else None,
            )

            def drain() -> int:
                added = 0
                while pending:
                    response = pending.pop(0)
                    try:
                        payload = response.json()
                    except Exception:
                        continue
                    state["responses"] += 1
                    batch, has_more = parse_post_response(payload)
                    state["has_more"] = has_more
                    for post in batch:
                        if post.aweme_id not in posts:
                            posts[post.aweme_id] = post
                            added += 1
                return added

            on_progress(0, "正在用 Chrome 打开抖音主页…")
            page.goto(f"{base_url}/user/{sec_user_id}", wait_until="domcontentloaded", timeout=60_000)

            started = time.monotonic()
            last_growth = started
            login_wall = False
            ticks = 0
            while True:
                page.wait_for_timeout(1000)
                ticks += 1
                if drain():
                    last_growth = time.monotonic()
                    on_progress(len(posts), f"正在读取作品列表…已找到 {len(posts)} 个作品")

                if not posts and ticks % 4 == 0:
                    try:
                        login_wall = page.get_by_text(LOGIN_WALL_TEXT).count() > 0
                    except PlaywrightError:
                        login_wall = False
                    if login_wall:
                        on_progress(0, "抖音要求登录。可以直接在弹出的 Chrome 窗口里扫码登录，或稍等…")

                now = time.monotonic()
                if not posts and now - started > first_batch_timeout:
                    if login_wall:
                        raise LoginRequired("抖音页面要求登录，保存的登录已失效。")
                    break
                if posts and not state["has_more"]:
                    drain()
                    break
                if posts and now - last_growth > idle_timeout:
                    break
                if now - started > total_timeout:
                    break

                try:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.mouse.wheel(0, 4000)
                except PlaywrightError:
                    pass
        finally:
            browser.close()

    log.info(
        "Douyin browser read: %d posts from %d responses (has_more=%s)",
        len(posts), state["responses"], state["has_more"],
    )
    return sorted(posts.values(), key=lambda p: p.create_time, reverse=True)


_UNSAFE = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def safe_name(text: str, limit: int = 40) -> str:
    cleaned = _UNSAFE.sub(" ", text).strip(" .")
    return cleaned[:limit].strip(" .") or "untitled"
