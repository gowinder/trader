# CCXT 对 WEEX 的支持情况调研

## 调研日期
2026-01-26

## 调研结果

### 1. CCXT 官方支持情况

根据 CCXT 官方文档和代码库：
- **WEEX 交易所**: CCXT 库对 WEEX (weex.com) 的支持**有限**
- **交易所 ID**: `weex`
- **支持状态**: 部分支持，可能存在 API 不完整或未更新的情况

### 2. API 接口覆盖度

CCXT 对 WEEX 的支持可能包括：
- ✅ 公共 API (行情数据、K线、Ticker)
- ⚠️ 私有 API (账户、订单、持仓) - **需要测试验证**
- ⚠️ 合约交易 API - **可能不完整**

### 3. 技术风险评估

**风险点**:
1. **API 兼容性**: WEEX 自定义实现与 CCXT 标准可能存在差异
2. **数据格式**: WEEX 返回的数据格式可能与 CCXT 标准不一致
3. **更新滞后**: WEEX API 更新后，CCXT 可能未及时适配
4. **合约功能**: WEEX 合约交易的特殊功能（如双向持仓）可能不支持

**影响范围**:
- 如果 CCXT 对 WEEX 支持不完整，部分功能需要回退到原生实现
- 建议保留现有 `WeexClient` 作为 fallback

### 4. 实施建议

**策略**: **渐进式集成 + 双路并行**

1. **阶段 1**:
   - 实现 CCXT 适配器框架
   - 优先测试公共 API（K线、Ticker）
   - 保留原生 WeexClient 作为 fallback

2. **阶段 2**:
   - 在 Testnet 环境验证私有 API（账户、订单）
   - 对比 CCXT 与原生实现的数据一致性
   - 性能测试（延迟、吞吐量）

3. **阶段 3**:
   - 根据验证结果决定：
     - 如果 CCXT 完全可用 → 切换到 CCXT
     - 如果部分可用 → 混合模式（公共 API 用 CCXT，私有 API 用原生）
     - 如果不可用 → 保持原生实现，仅使用 CCXT 框架

### 5. 配置方案

在 `config.py` 中添加开关：
```python
use_ccxt: bool = Field(default=False, validation_alias="USE_CCXT")
```

- `use_ccxt=True`: 优先使用 CCXT，失败时回退到原生
- `use_ccxt=False`: 仅使用原生 WeexClient

### 6. 测试验证清单

- [ ] CCXT WEEX 实例化测试
- [ ] 公共 API 测试（K线、Ticker）
- [ ] 私有 API 测试（账户、持仓）
- [ ] 订单创建与管理测试
- [ ] 数据格式一致性验证
- [ ] 性能对比测试（延迟 <100ms）

### 7. 结论

**建议采用保守策略**:
- 实现 CCXT 适配器作为标准接口
- 保留原生 WeexClient 作为可靠的 fallback
- 通过配置开关控制使用哪种实现
- 在 Testnet 充分验证后再考虑完全切换

这种方案既能引入 CCXT 的多交易所支持能力，又不会因为 WEEX 支持不完整而影响现有功能。
