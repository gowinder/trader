Feature: 策略选择与市场分类
  作为量化交易系统
  我需要根据市场状态动态选择策略和权重
  以在不同市场环境中使用最适合的策略组合

  # ── 市场状态驱动的策略权重 ──────────────────────

  Scenario: 强趋势市场主用趋势跟随策略
    Given 启用全部策略
    When 市场状态为 strong_trend
    Then trend_following 权重应为 0.7
    And breakout 权重应为 0.3
    And mean_reversion 权重应为 0.0

  Scenario: 弱趋势市场混用趋势和均值回归
    Given 启用全部策略
    When 市场状态为 weak_trend
    Then trend_following 权重应为 0.6
    And mean_reversion 权重应为 0.4

  Scenario: 震荡市场主用均值回归策略
    Given 启用全部策略
    When 市场状态为 sideways
    Then mean_reversion 权重应为 0.9
    And trend_following 权重应为 0.1

  Scenario: 区间震荡市场偏重均值回归
    Given 启用全部策略
    When 市场状态为 range_bound
    Then mean_reversion 权重应为 0.8
    And trend_following 权重应为 0.2

  Scenario: 突破市场主用突破策略
    Given 启用全部策略
    When 市场状态为 breakout
    Then breakout 权重应为 0.8
    And trend_following 权重应为 0.2

  # ── 策略部分启用 ──────────────────────────────

  Scenario: 仅启用部分策略时未启用策略权重为零
    Given 仅启用 trend_following 策略
    When 市场状态为 strong_trend
    Then trend_following 权重应为 0.7
    And 策略总数应为 1

  # ── 动态权重覆盖 ──────────────────────────────

  Scenario: 动态覆盖权重优先于默认值
    Given 启用全部策略
    And 覆盖 strong_trend 权重为 trend_following=0.5,mean_reversion=0.3,breakout=0.2
    When 市场状态为 strong_trend
    Then trend_following 权重应为 0.5
    And mean_reversion 权重应为 0.3
    And breakout 权重应为 0.2

  Scenario: 未覆盖的市场状态使用默认权重
    Given 启用全部策略
    And 覆盖 strong_trend 权重为 trend_following=0.5,mean_reversion=0.3,breakout=0.2
    When 市场状态为 sideways
    Then mean_reversion 权重应为 0.9
    And trend_following 权重应为 0.1

  # ── 信号冲突检测 ──────────────────────────────

  Scenario: 相反信号强度接近时返回 HOLD
    Given 启用全部策略
    When 策略产生冲突信号且反向分数超过 70%
    Then 聚合结果应为 HOLD
    And 原因应包含 "Conflicting signals"
