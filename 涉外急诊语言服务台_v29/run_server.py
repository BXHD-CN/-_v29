# -*- coding: utf-8 -*-
"""生产/托管环境启动入口。

读取 PORT 环境变量（未设置时回退 3000），绑定 0.0.0.0，
供反向代理把公网请求转发到本服务。

用法：
    python run_server.py
"""
import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, proxy_headers=True)
