from urllib.parse import urljoin
from gkmas_utils.utils import sha256sum

# manifest request
GKMAS_APPID = 400
GKMAS_VERSION = 205000
GKMAS_VERSION_PC = 705000
GKMAS_API_SERVER = "https://api.asset.game-gakuen-idolmaster.jp/"
GKMAS_API_URL = urljoin(
    GKMAS_API_SERVER, f"v2/pub/a/{GKMAS_APPID}/v/{GKMAS_VERSION}/list/"
)
GKMAS_API_URL_PC = urljoin(
    GKMAS_API_SERVER, f"v2/pub/a/{GKMAS_APPID}/v/{GKMAS_VERSION_PC}/list/"
)
GKMAS_API_KEY = "0jv0wsohnnsigttbfigushbtl3a8m7l5"
GKMAS_API_HEADER = {
    "Accept": f"application/x-protobuf,x-octo-app/{GKMAS_APPID}",
    "X-OCTO-KEY": GKMAS_API_KEY,
}

# manifest decrypt
GKMAS_ONLINEPDB_KEY = sha256sum("eSquJySjayO5OLLVgdTd".encode("utf-8"))
GKMAS_ONLINEPDB_KEY_PC = sha256sum("x5HFaJCJywDyuButLM0f".encode("utf-8"))