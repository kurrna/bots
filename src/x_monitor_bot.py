#!/usr/bin/env python3
"""X/Twitter 监控机器人入口点。

使用 RSSHub JSON Feed 获取推文并转发到 Telegram。
"""

import sys
import pathlib

# 添加 src 目录到路径
src_dir = pathlib.Path(__file__).resolve().parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from x_monitor import cli_main

if __name__ == "__main__":
    cli_main()
