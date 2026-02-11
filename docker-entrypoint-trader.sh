#!/bin/bash
set -e

# 从只读挂载复制 CLI 认证到工作目录
cp -r /mnt/qwen /root/.qwen 2>/dev/null || true
cp -r /mnt/gemini /root/.gemini 2>/dev/null || true
cp -r /mnt/codex /root/.codex 2>/dev/null || true

# 清理 MCP 配置（宿主机配置含 MCP servers，容器内 npx 初始化会卡死）
# qwen
if [ -f /root/.qwen/settings.json ]; then
    python3 -c "
import json, sys
try:
    with open('/root/.qwen/settings.json') as f:
        cfg = json.load(f)
    cfg.pop('mcpServers', None)
    with open('/root/.qwen/settings.json', 'w') as f:
        json.dump(cfg, f, indent=2)
except Exception as e:
    print(f'Warning: qwen MCP cleanup failed: {e}', file=sys.stderr)
"
fi

# gemini
if [ -f /root/.gemini/settings.json ]; then
    python3 -c "
import json, sys
try:
    with open('/root/.gemini/settings.json') as f:
        cfg = json.load(f)
    cfg.pop('mcpServers', None)
    with open('/root/.gemini/settings.json', 'w') as f:
        json.dump(cfg, f, indent=2)
except Exception as e:
    print(f'Warning: gemini MCP cleanup failed: {e}', file=sys.stderr)
"
fi

# codex
if [ -f /root/.codex/config.toml ]; then
    python3 -c "
import sys
try:
    with open('/root/.codex/config.toml') as f:
        lines = f.readlines()
    out = []
    skip = False
    for line in lines:
        if line.strip().startswith('[mcp_servers'):
            skip = True
            continue
        if skip and line.strip().startswith('[') and not line.strip().startswith('[mcp_servers'):
            skip = False
        if not skip:
            out.append(line)
    with open('/root/.codex/config.toml', 'w') as f:
        f.writelines(out)
except Exception as e:
    print(f'Warning: codex MCP cleanup failed: {e}', file=sys.stderr)
"
fi

exec python -m ai_trader.main
