# 日志自动翻译功能使用指南

## 功能简介

自动将英文日志消息翻译为中文（或其他语言），提升日志可读性。

## 快速开始

### 方式1：使用配置文件（推荐）

```bash
# .env 文件
ENABLE_LOG_TRANSLATION=true
LOG_TARGET_LANGUAGE=zh-CN
```

```python
from ai_trader.config import config
from ai_trader.utils.translator import setup_translated_logger
from loguru import logger

# 使用配置启用翻译
setup_translated_logger(
    level=config.log_level,
    target_lang=config.log_target_language,
    enabled=config.enable_log_translation,
)

logger.info("Trading system started")
# 输出：交易系统启动
```

### 方式2：直接启用中文翻译

```python
from ai_trader.utils.translator import enable_chinese_logs
from loguru import logger

# 快速启用中文翻译
enable_chinese_logs()

logger.info("Order executed successfully")
# 输出：订单执行成功
```

### 方式3：自定义配置

```python
from ai_trader.utils.translator import setup_translated_logger
from loguru import logger

# 自定义翻译配置
setup_translated_logger(
    level="INFO",           # 日志级别
    target_lang="ja",       # 目标语言（日语）
    enabled=True,           # 启用翻译
    log_file="logs/trading.log"  # 日志文件（不翻译）
)

logger.warning("High volatility detected")
# 输出：高いボラティリティが検出されました
```

## 支持的语言

基于 Google Translate API，支持100+种语言：

| 语言 | 代码 | 示例 |
|------|------|------|
| 简体中文 | zh-CN | 交易系统启动 |
| 繁体中文 | zh-TW | 交易系統啟動 |
| 日语 | ja | 取引システムが開始されました |
| 韩语 | ko | 거래 시스템이 시작되었습니다 |
| 西班牙语 | es | Sistema de trading iniciado |
| 法语 | fr | Système de trading démarré |
| 德语 | de | Handelssystem gestartet |
| 俄语 | ru | Торговая система запущена |

完整列表见：[deep-translator 支持语言](https://github.com/nidhaloff/deep-translator#supported-languages)

## 测试翻译

```bash
# 运行测试脚本
export UV_NO_CACHE=1
uv run python test_translation.py
```

## 示例输出

### 原始日志（英文）
```
2026-01-27 13:50:00 | INFO  | Trading system started
2026-01-27 13:50:01 | WARN  | High volatility detected
2026-01-27 13:50:02 | ERROR | Failed to connect to exchange
2026-01-27 13:50:03 | SUCCESS | Order executed successfully
```

### 翻译后日志（中文）
```
2026-01-27 13:50:00 | INFO  | 交易系统启动
2026-01-27 13:50:01 | WARN  | 检测到高波动性
2026-01-27 13:50:02 | ERROR | 无法连接到交换机
2026-01-27 13:50:03 | SUCCESS | 订单执行成功
```

## 配置项说明

### config.py 配置

```python
# 启用日志翻译
enable_log_translation: bool = False  # 默认禁用

# 目标语言
log_target_language: str = "zh-CN"    # 默认简体中文
```

### 环境变量

```bash
# .env 文件
ENABLE_LOG_TRANSLATION=true
LOG_TARGET_LANGUAGE=zh-CN
```

## 性能考虑

### 翻译缓存
- 使用 LRU 缓存（1000条）
- 相同消息只翻译一次
- 自动缓存管理

### 翻译跳过
自动跳过以下内容：
- 3个字符以下的消息
- 已包含中文的消息
- 空消息

### 网络要求
- 需要访问 Google Translate API
- 首次翻译可能有200-500ms延迟
- 缓存命中后延迟 <1ms

## 故障处理

### 翻译失败回退
```python
# 翻译失败时自动返回原文
logger.info("Original message")
# 网络异常时输出：Original message（不报错）
```

### 禁用翻译
```python
# 方式1：通过配置
setup_translated_logger(enabled=False)

# 方式2：环境变量
# ENABLE_LOG_TRANSLATION=false
```

## 实际使用场景

### 场景1：本地开发（禁用翻译）
```python
# 开发环境 - 英文日志便于调试
setup_translated_logger(enabled=False)
```

### 场景2：生产部署（启用翻译）
```python
# 生产环境 - 中文日志便于监控
enable_chinese_logs(log_file="logs/trading.log")
```

### 场景3：混合使用
```python
# 控制台翻译，文件保持英文
setup_translated_logger(
    enabled=True,              # 控制台翻译
    log_file="logs/en.log"     # 文件保持英文
)
```

## 集成到现有代码

### 方式1：在入口文件启用

```python
# main.py
from ai_trader.utils.translator import enable_chinese_logs
from loguru import logger

# 应用启动时启用翻译
enable_chinese_logs()

# 之后的所有日志都会翻译
logger.info("Application started")
```

### 方式2：使用配置系统

```python
# 在配置加载后
from ai_trader.config import config
from ai_trader.utils.translator import setup_translated_logger

setup_translated_logger(
    level=config.log_level,
    target_lang=config.log_target_language,
    enabled=config.enable_log_translation,
    log_file=config.log_file,
)
```

## 注意事项

1. **文件日志不翻译** - 日志文件保持英文便于解析
2. **代码日志仍用英文** - 代码中日志消息保持英文
3. **仅输出翻译** - 只在控制台输出时翻译
4. **网络依赖** - 需要能访问 Google Translate API

## 故障排查

### 问题1：翻译不生效
```bash
# 检查翻译服务是否初始化
# 查看日志：Logger initialized (translation=enabled)
```

### 问题2：网络错误
```bash
# 检查网络连接
curl -I https://translate.google.com
```

### 问题3：语言代码错误
```python
# 确保使用正确的代码
setup_translated_logger(target_lang="zh-CN")  # ✓ 正确
setup_translated_logger(target_lang="zh-cn")  # ✗ 错误
```

## API 文档

### TranslationService

```python
class TranslationService:
    def __init__(self, target_lang: str = "zh-CN", enabled: bool = True)
    def translate(self, text: str) -> str
    def clear_cache(self)
```

### setup_translated_logger

```python
def setup_translated_logger(
    level: str = "INFO",
    target_lang: str = "zh-CN",
    enabled: bool = True,
    log_file: Optional[str] = None,
)
```

### enable_chinese_logs

```python
def enable_chinese_logs(
    level: str = "INFO",
    log_file: Optional[str] = None,
)
```

## 卸载翻译功能

如不需要翻译功能：

```bash
# 移除依赖
uv remove deep-translator

# 删除翻译模块
rm src/ai_trader/utils/translator.py
```

## 总结

- ✅ **简单易用** - 一行代码启用
- ✅ **性能优化** - LRU缓存 + 智能跳过
- ✅ **故障安全** - 翻译失败自动回退
- ✅ **灵活配置** - 支持多种语言和配置方式

根据需要选择启用或禁用翻译功能即可。
