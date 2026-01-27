#!/bin/bash
# 启动长期端到端测试的便捷脚本

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo -e "${GREEN}===========================================================${NC}"
echo -e "${GREEN}启动长期端到端测试系统${NC}"
echo -e "${GREEN}===========================================================${NC}"
echo ""

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo -e "${RED}❌ 虚拟环境不存在${NC}"
    echo "请先运行: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# 检查配置文件
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ .env 配置文件不存在${NC}"
    exit 1
fi

# 检查 Testnet 配置
echo "🔍 检查配置..."
if ! grep -q "TRADING_MODE=testnet" .env; then
    echo -e "${RED}❌ 未配置为 Testnet 模式${NC}"
    echo "请在 .env 中设置: TRADING_MODE=testnet"
    exit 1
fi

if ! grep -q "TESTNET_API_KEY" .env; then
    echo -e "${RED}❌ 未配置 Testnet API 凭证${NC}"
    echo "请在 .env 中设置 TESTNET_API_KEY 和 TESTNET_API_SECRET"
    exit 1
fi

echo -e "${GREEN}✓ 配置检查通过${NC}"
echo ""

# 创建日志目录
mkdir -p logs data/trades

# 激活虚拟环境
source .venv/bin/activate

# 检查依赖
echo "🔍 检查依赖..."
python -c "import ccxt, pandas, numpy" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}⚠️  缺少依赖，正在安装...${NC}"
    pip install ccxt pandas numpy pydantic pydantic-settings loguru httpx python-dotenv scipy ta
fi

echo -e "${GREEN}✓ 依赖检查通过${NC}"
echo ""

# 显示运行信息
echo -e "${GREEN}===========================================================${NC}"
echo "📋 测试配置:"
echo "  - 模式: Testnet"
echo "  - 交易所: $(grep TESTNET_EXCHANGE .env | cut -d'=' -f2)"
echo "  - 分析间隔: 5分钟"
echo "  - 日志位置: logs/e2e_testnet.log"
echo ""
echo "💡 提示:"
echo "  - 按 Ctrl+C 停止测试"
echo "  - 使用 tmux/screen 保持后台运行"
echo "  - 另开终端查看日志: tail -f logs/e2e_testnet.log"
echo -e "${GREEN}===========================================================${NC}"
echo ""

# 询问是否继续
read -p "是否继续启动测试? [Y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]] && [[ ! -z $REPLY ]]; then
    echo "已取消"
    exit 0
fi

# 启动测试
echo ""
echo -e "${GREEN}🚀 启动测试...${NC}"
echo ""

python -u scripts/run_e2e_testnet.py

# 如果脚本被中断
echo ""
echo -e "${YELLOW}测试已停止${NC}"
echo "日志文件: logs/e2e_testnet.log"
