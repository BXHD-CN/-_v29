# 涉外急诊语言服务台 —— 容器镜像
# 适用：Render / Fly.io / Railway / 腾讯云容器 等按容器部署的平台。
#
# 关键点：
# 1. 启动命令用 run_server.py：它读取平台注入的 PORT 环境变量（Render 默认 10000，
#    Fly/Railway 也会注入），未设置时回退 3000，并绑定 0.0.0.0 + --proxy-headers，
#    保证在反向代理后面拿到的客户端 IP / 协议正确。
# 2. 仓库未提交 data/app.db 时（.gitignore 默认忽略），构建期自动从 data/*.jsonl
#    播种 + 向量化，保证镜像开箱即有完整术语 / 语料 / 切片数据；已带 app.db 则跳过。
# 3. 密钥不进镜像：SECRET_KEY 等一律通过平台环境变量注入（见 render.yaml / README 第 21 节）。

FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# 海外平台默认用官方 PyPI；在国内构建可加
# --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_INDEX_URL=https://pypi.org/simple
COPY requirements.txt .
RUN pip install --no-cache-dir -i "${PIP_INDEX_URL}" -r requirements.txt

COPY app ./app
COPY static ./static
COPY scripts ./scripts
COPY data ./data
COPY run_server.py .

RUN if [ ! -f data/app.db ]; then \
        python scripts/seed_public.py && \
        python scripts/build_slices.py && \
        python scripts/embed_chunks.py --force && \
        python scripts/embed_corpus.py ; \
    fi

EXPOSE 3000
CMD ["python", "run_server.py"]
