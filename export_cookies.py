#!/usr/bin/env python3
"""Export Douyin / YouTube cookies from your browser into a file VideoGet can read.

Must be run in Terminal on your Mac (Cloud Agent cannot reach your Chrome).
macOS will prompt for Keychain access — click Allow. Quit Chrome first if the
cookie database is locked.

Usage:
    python3 export_cookies.py douyin
    python3 export_cookies.py youtube
    python3 export_cookies.py douyin --browser safari
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import time
from http.cookiejar import MozillaCookieJar
from pathlib import Path

class LoginCookieMissing(RuntimeError):
    """Browser cookies were read, but the login cookie is not among them."""


SITES = {
    "douyin": {
        "domains": ("douyin.com", "iesdouyin.com"),
        "output": Path.home() / "douyin_cookies.txt",
        "must_have": ("sessionid",),
        "login_url": "https://www.douyin.com/",
    },
    "youtube": {
        "domains": ("youtube.com", "google.com"),
        "output": Path.home() / "youtube_cookies.txt",
        "must_have": (),
        "login_url": "https://www.youtube.com/",
    },
}


def _browser_loader(browser: str):
    try:
        import browser_cookie3
    except ImportError as e:
        raise RuntimeError(
            "缺少 browser_cookie3。请先安装：\n"
            '  python3 -m pip install -U "yt-dlp[default]" browser_cookie3 --break-system-packages'
        ) from e

    loaders = {
        "chrome": browser_cookie3.chrome,
        "chromium": browser_cookie3.chromium,
        "edge": browser_cookie3.edge,
        "brave": browser_cookie3.brave,
        "firefox": browser_cookie3.firefox,
        "safari": browser_cookie3.safari,
    }
    if browser not in loaders:
        raise RuntimeError(f"不支持的浏览器: {browser}")
    return loaders[browser]


def _cookie_matches(cookie, domains: tuple[str, ...]) -> bool:
    host = (cookie.domain or "").lstrip(".").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def douyin_login_status(path: Path | None = None) -> dict:
    """Say whether the saved Douyin cookie file contains a login session.

    The cookie values stay on disk. Callers only learn whether ``sessionid``
    is present.
    """
    path = path or SITES["douyin"]["output"]
    if not path.is_file() or path.stat().st_size == 0:
        return {
            "logged_in": False,
            "path": str(path),
            "message": "还没有抖音登录。在 Chrome 打开并登录 douyin.com 后，点「从浏览器读取登录」，只需这一次。",
        }
    names = netscape_cookie_names(path.read_text(encoding="utf-8", errors="replace"))
    if "sessionid" in names:
        return {
            "logged_in": True,
            "path": str(path),
            "message": "抖音登录已保存在这台 Mac 上，可以直接下载主页。过期后再点一次按钮即可。",
        }
    return {
        "logged_in": False,
        "path": str(path),
        "message": "保存的抖音 Cookie 里没有登录状态。请先在 Chrome 登录 douyin.com，再点一次按钮。",
    }


def _apple_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _export_via_osascript(browser: str) -> str | None:
    """Run the exporter outside the background service so macOS can show a prompt.

    Returns an error string, or None when the command finishes.
    """
    if sys.platform != "darwin":
        return "当前系统不能弹出钥匙串授权"
    shell_cmd = (
        f"{shlex.quote(sys.executable)} {shlex.quote(str(Path(__file__).resolve()))} "
        f"douyin --browser {browser}"
    )
    apple = "do shell script " + _apple_string(shell_cmd)
    try:
        result = subprocess.run(
            ["osascript", "-e", apple],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except Exception as error:
        return str(error)
    if result.returncode != 0:
        return (result.stderr or result.stdout or "系统授权窗口被取消").strip()
    return None


def _open_terminal_export(browser: str) -> bool:
    """Open Terminal with the export command already running. No command to copy."""
    if sys.platform != "darwin":
        return False
    folder = Path.home() / "Library" / "Application Support" / "VideoGet"
    folder.mkdir(parents=True, exist_ok=True)
    command_file = folder / "export-douyin.command"
    command_file.write_text(
        "#!/bin/bash\n"
        f"{shlex.quote(sys.executable)} {shlex.quote(str(Path(__file__).resolve()))} "
        f"douyin --browser {browser}\n"
        "echo\n"
        "echo 可以关闭这个窗口了\n",
        encoding="utf-8",
    )
    command_file.chmod(0o755)
    subprocess.Popen(["open", "-a", "Terminal", str(command_file)])
    return True


def export_douyin_from_app(browser: str = "chrome") -> dict:
    """Export a Douyin login for the web UI.

    The background server often cannot read the macOS Keychain. This tries the
    direct read first, then a system prompt, then opens Terminal already running
    the export so the user only has to click Allow.
    """
    browser = (browser or "chrome").strip().lower()
    allowed = {"chrome", "safari", "firefox", "edge", "chromium", "brave"}
    if browser not in allowed:
        return {"ok": False, "logged_in": False, "error": "不支持的浏览器"}

    try:
        export_with_browser_cookie3("douyin", browser)
    except LoginCookieMissing as error:
        status = douyin_login_status()
        status.update({"ok": False, "error": str(error)})
        return status
    except Exception as error:
        dialog_error = _export_via_osascript(browser)
        status = douyin_login_status()
        if status["logged_in"]:
            status["ok"] = True
            return status
        if _open_terminal_export(browser):
            return {
                "ok": False,
                "pending": True,
                "logged_in": False,
                "message": "已打开一个窗口读取 Chrome。请点「允许」。成功后这里会变成已登录，不用复制命令。",
                "error": dialog_error or str(error),
            }
        status.update({"ok": False, "error": str(error)})
        return status

    status = douyin_login_status()
    status["ok"] = True
    return status


def netscape_cookie_names(text: str) -> set[str]:
    """Return cookie names from a Netscape file, including HttpOnly rows.

    MozillaCookieJar prefixes HttpOnly cookies with ``#HttpOnly_``. Those lines
    look like comments, but they are the login cookies (Douyin ``sessionid``).
    """
    names = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        elif line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) >= 7 and fields[5]:
            names.add(fields[5])
    return names


def _write_netscape(path: Path, cookies) -> int:
    jar = MozillaCookieJar(str(path))
    count = 0
    for cookie in cookies:
        # MozillaCookieJar rejects cookies without expires; give them a far future.
        if cookie.expires is None:
            cookie.expires = int(time.time()) + 365 * 24 * 3600
        try:
            jar.set_cookie(cookie)
            count += 1
        except Exception:
            continue
    jar.save(ignore_discard=True, ignore_expires=True)
    return count


SCRIPT_VERSION = "2026-11-05-httponly"


def export_with_browser_cookie3(site: str, browser: str) -> Path:
    config = SITES[site]
    output: Path = config["output"]
    loader = _browser_loader(browser)

    print(f"export_cookies 版本 {SCRIPT_VERSION}")
    print(f"正在从 {browser} 读取 {site} Cookie…")
    print("若系统弹出钥匙串权限，请点「允许」。")
    print("若提示 Cookie 数据库被锁定，请先完全退出 Chrome 再重试。\n")

    collected = []
    last_error = None
    for domain in config["domains"]:
        try:
            jar = loader(domain_name=domain)
            for cookie in jar:
                if _cookie_matches(cookie, config["domains"]):
                    collected.append(cookie)
        except Exception as e:
            last_error = e

    # Deduplicate by (domain, name, path)
    unique = {}
    for cookie in collected:
        key = (cookie.domain, cookie.name, cookie.path)
        unique[key] = cookie
    cookies = list(unique.values())

    if not cookies:
        tip = f"（{last_error}）" if last_error else ""
        raise RuntimeError(
            f"没有读到 {site} 相关 Cookie{tip}。\n"
            f"请先在 {browser} 打开并登录 {config['login_url']}，"
            "完全退出浏览器后重试。"
        )

    count = _write_netscape(output, cookies)
    if count == 0 or not output.exists() or output.stat().st_size == 0:
        raise RuntimeError(f"写入失败：{output}")

    # Names on the cookie objects are the source of truth. The file check
    # covers HttpOnly rows, which MozillaCookieJar saves as ``#HttpOnly_`` lines.
    names = {cookie.name for cookie in cookies}
    names |= netscape_cookie_names(output.read_text(encoding="utf-8", errors="replace"))
    missing = [name for name in config["must_have"] if name not in names]

    print(f"已保存 → {output}  （{count} 条，{output.stat().st_size} 字节）")
    if missing:
        raise LoginCookieMissing(
            f"文件里缺少登录关键（{', '.join(missing)}）。\n"
            f"请在 {browser} 打开并登录 {config['login_url']}，"
            "确认页面右上角是你的头像，完全退出浏览器后再运行本命令。"
        )
    if config["must_have"]:
        print(f"登录态已包含：{', '.join(config['must_have'])}")
    return output


def export_with_yt_dlp(site: str, browser: str) -> Path:
    """Fallback when browser_cookie3 cannot open the browser cookie database."""
    try:
        from yt_dlp.cookies import extract_cookies_from_browser
    except ImportError as e:
        raise RuntimeError("yt-dlp 不可用，无法改用第二种导出方式") from e

    config = SITES[site]
    output: Path = config["output"]
    print(f"改用 yt-dlp 从 {browser} 导出…")
    jar = extract_cookies_from_browser(browser)
    collected = [cookie for cookie in jar if _cookie_matches(cookie, config["domains"])]
    if not collected:
        raise RuntimeError(f"yt-dlp 没有读到 {site} Cookie")

    count = _write_netscape(output, collected)
    names = {cookie.name for cookie in collected}
    names |= netscape_cookie_names(output.read_text(encoding="utf-8", errors="replace"))
    missing = [name for name in config["must_have"] if name not in names]
    print(f"已保存 → {output}  （{count} 条，{output.stat().st_size} 字节）")
    if missing:
        raise LoginCookieMissing(
            f"文件里缺少登录关键（{', '.join(missing)}）。\n"
            f"请在 {browser} 登录 {config['login_url']} 后再运行本命令。"
        )
    if config["must_have"]:
        print(f"登录态已包含：{', '.join(config['must_have'])}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="一键导出浏览器 Cookie 给 VideoGet 使用")
    parser.add_argument("site", choices=sorted(SITES), help="要导出哪个网站的 Cookie")
    parser.add_argument(
        "--browser", "-b",
        default="chrome",
        choices=["chrome", "safari", "firefox", "edge", "chromium", "brave"],
        help="已登录该网站的浏览器（默认 chrome）",
    )
    args = parser.parse_args()

    try:
        path = export_with_browser_cookie3(args.site, args.browser)
    except LoginCookieMissing as login_error:
        print(f"导出失败：{login_error}")
        sys.exit(2)
    except Exception as first_error:
        print(f"browser_cookie3 方式失败：{first_error}\n")
        try:
            path = export_with_yt_dlp(args.site, args.browser)
        except LoginCookieMissing as login_error:
            print(f"导出失败：{login_error}")
            sys.exit(2)
        except Exception as second_error:
            print(f"导出失败：{second_error}")
            print("\n请按顺序试：")
            print("  1. 在 Chrome 打开并登录对应网站")
            print("  2. 菜单栏 Chrome → 退出 Google Chrome（必须完全退出）")
            print("  3. 再运行本命令；钥匙串弹窗点「允许」")
            sys.exit(1)

    print("完成。请重新启动 VideoGet，再粘贴主页链接下载。")
    print(f"Cookie 文件：{path}")


if __name__ == "__main__":
    main()
