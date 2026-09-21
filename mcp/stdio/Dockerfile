# sparfenyuk/mcp-proxy ships without uv; add it so servers.json can use uvx.
# Python-only on purpose: no node/npx, so any server listed must be on PyPI.
FROM ghcr.io/sparfenyuk/mcp-proxy:v0.12.0

RUN python3 -m ensurepip && pip install --no-cache-dir uv

ENV PATH="/usr/local/bin:$PATH" \
    UV_PYTHON_PREFERENCE=only-system

ENTRYPOINT ["catatonit", "--", "mcp-proxy"]
