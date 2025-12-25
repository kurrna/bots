import requests, pathlib, os, re, datetime
from dotenv import load_dotenv
from gkmas_utils.const import (
    GKMAS_APPID, GKMAS_VERSION, GKMAS_VERSION_PC,
    GKMAS_API_SERVER,
    GKMAS_API_HEADER,
    GKMAS_ONLINEPDB_KEY, GKMAS_ONLINEPDB_KEY_PC
)
from gkmas_utils.utils import AESCBCDecryptor, pdbytes2dict

load_dotenv()

TARGETS = {
    "Mobile": f"{GKMAS_API_SERVER}v2/pub/a/{GKMAS_APPID}/v/{GKMAS_VERSION}/list/114514",
    "PC": f"{GKMAS_API_SERVER}v2/pub/a/{GKMAS_APPID}/v/{GKMAS_VERSION_PC}/list/114514"
}

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

def fetch_json(url=TARGETS["Mobile"], pc=False) -> dict:
    req = requests.get(url, headers=GKMAS_API_HEADER, timeout=10)
    req.raise_for_status()  # Raise an error for bad responses
    enc = req.content
    dec = AESCBCDecryptor(
        GKMAS_ONLINEPDB_KEY_PC if pc else GKMAS_ONLINEPDB_KEY, enc[:16]
    ).process(enc[16:])
    return pdbytes2dict(dec)

def send_tg_message(text):
    if not TG_TOKEN or not TG_CHAT_ID:
        print("未配置 Telegram Token 或 Chat ID")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    params = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=params)
    except Exception as e:
        print(f"发送通知失败: {e}")

def check_update():
    update_detected = False
    if pathlib.Path("messages").exists() is False:
        pathlib.Path("messages").mkdir()
    notification_file = pathlib.Path("messages/gkmas_notification.md")
    messages = "*学マス* 资源更新🤯！？\n"
    beijing_time = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    update_time = beijing_time.strftime("%Y-%m-%d %H:%M:%S")
    pattern = r'v(\d+)'
    last_revision_list = re.findall(pattern, notification_file.read_text()) if notification_file.exists() else []
    last_revisions = {
        "Mobile": last_revision_list[-2] if len(last_revision_list) >= 2 else 0,
        "PC": last_revision_list[-1] if len(last_revision_list) >= 1 else 0
    }
    last_update_time_list = re.findall(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', notification_file.read_text()) if notification_file.exists() else []
    last_update_times = {
        "Mobile": last_update_time_list[-2] if len(last_update_time_list) >= 2 else "N/A",
        "PC": last_update_time_list[-1] if len(last_update_time_list) >= 1 else "N/A"
    }

    for name, url in TARGETS.items():
        data = fetch_json(url, pc=(name == "PC"))
        latest_revision = data.get("revision")
        if latest_revision and str(latest_revision) != str(last_revisions[name]):
            update_detected = True
            messages += f"\n🔔 *{name}* 检测到更新！"
            messages += f"\n最新版本：*v{latest_revision}*\n更新时间：*{update_time}*\n"
        else:
            messages += f"\n🤔 *{name}* 暂无更新。"
            messages += f"\n最新版本：*v{last_revisions[name]}*\n更新时间：*{last_update_times[name]}*\n"

    print(messages)
    if update_detected:
        send_tg_message(messages)
        notification_file.write_text(messages)
        print("\n更新已检测并通知😋！")
    else:
        print("\n未检测到更新😭！")

if __name__ == "__main__":
    check_update()