"""学マス资源变更检测脚本（改进版）。

特点：
 - 从 `.env` 或环境变量读取配置（包含版本号），CLI 可覆盖。
 - 使用 requests 的重试机制提高稳定性。
 - 将哈希存放到 `.gkm_hashes/` 目录以避免目录污染。
 - 在检测到更新时发送 Telegram 通知（需配置 TG_TOKEN/TG_CHAT_ID）。
"""
from __future__ import annotations

import hashlib
import os
import pathlib
from typing import Dict, Tuple

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from rich import print


ROOT = pathlib.Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def make_session(retries: int = 3, backoff_factor: float = 0.5) -> requests.Session:
    session = requests.Session()
    retry = Retry(total=retries, backoff_factor=backoff_factor, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET", "POST"))
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def get_config_from_env() -> Dict[str, str]:
    cfg = {
        "GKMAS_APPID": os.getenv("GKMAS_APPID", "400"),
        "GKMAS_VERSION": os.getenv("GKMAS_VERSION", "205000"),
        "GKMAS_VERSION_PC": os.getenv("GKMAS_VERSION_PC", "705000"),
        "GKMAS_API_SERVER": os.getenv("GKMAS_API_SERVER", "https://api.asset.game-gakuen-idolmaster.jp/"),
        "GKMAS_API_KEY": os.getenv("GKMAS_API_KEY", "0jv0wsohnnsigttbfigushbtl3a8m7l5"),
        "TG_TOKEN": os.getenv("TG_TOKEN"),
        "TG_CHAT_ID": os.getenv("TG_CHAT_ID"),
    }
    return cfg


def notify_telegram(token: str, chat_id: str, text: str, parse_mode: str = "Markdown") -> Tuple[bool, str]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try:
        r = requests.post(url, json=payload, timeout=15)
        try:
            j = r.json()
        except Exception:
            return False, f"非 JSON 响应，HTTP {r.status_code}: {r.text}"
        if r.ok and j.get("ok"):
            return True, "ok"
        return False, str(j)
    except Exception as e:
        return False, str(e)


def build_targets(cfg: Dict[str, str]) -> Dict[str, str]:
    s = cfg["GKMAS_API_SERVER"].rstrip("/")
    appid = cfg["GKMAS_APPID"]
    v_mobile = cfg["GKMAS_VERSION"]
    v_pc = cfg["GKMAS_VERSION_PC"]
    latest_version = 0
    # 构造两个目标 URL，确保包含最新版本号
    return {
        "Mobile Manifest": f"{s}/v2/pub/a/{appid}/v/{v_mobile}/list/{latest_version}",
        "PC Manifest": f"{s}/v2/pub/a/{appid}/v/{v_pc}/list/{latest_version}",
    }


def ensure_hash_dir() -> pathlib.Path:
    d = ROOT / ".gkm_hashes"
    d.mkdir(exist_ok=True)
    return d


def md5_of_bytes(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def check_update() -> None:
    cfg = get_config_from_env()
    targets = build_targets(cfg)
    session = make_session()
    headers = {
        "Accept": f"application/x-protobuf,x-octo-app/{cfg['GKMAS_APPID']}",
        "X-OCTO-KEY": cfg["GKMAS_API_KEY"],
        "User-Agent": "UnityPlayer/2022.3.21f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
    }

    hash_dir = ensure_hash_dir()
    update_detected = False
    messages = ["【学マス 资源更新通知】"]

    for name, url in targets.items():
        try:
            r = session.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                cur_hash = md5_of_bytes(r.content)
                hash_file = hash_dir / f"{name.replace(' ', '_').lower()}_hash.txt"
                last_hash = ""
                if hash_file.exists():
                    last_hash = hash_file.read_text(encoding='utf-8').strip()
                if cur_hash != last_hash:
                    update_detected = True
                    messages.append(f"🔔 *{name}* 检测到更新！\n新 MD5: `{cur_hash}`")
                    hash_file.write_text(cur_hash, encoding='utf-8')
                    print(f"[green]{name} 更新，MD5:{cur_hash}[/green]")
                else:
                    print(f"{name} 无变化")
            else:
                print(f"[red]{name} 请求失败，状态码: {r.status_code}，URL: {url}[/red]")
                try:
                    print(f"响应正文: {r.text}")
                except Exception:
                    pass
        except Exception as e:
            print(f"[red]检查 {name} 时出错: {e}[/red]")

    if update_detected:
        token = cfg.get("TG_TOKEN")
        chat_id = cfg.get("TG_CHAT_ID")
        body = "\n\n".join(messages)
        if token and chat_id:
            ok, info = notify_telegram(token, chat_id, body)
            if ok:
                print("[green]已发送 Telegram 通知[/green]")
            else:
                print(f"[red]发送 Telegram 失败:[/red] {info}")
        else:
            print("[yellow]检测到更新但未配置 Telegram，详情: [/yellow]\n", body)


if __name__ == "__main__":
    check_update()