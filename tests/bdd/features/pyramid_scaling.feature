Feature: 金字塔加仓
  作为交易系统的风控模块
  我需要在趋势持续且盈利充足时逐步加仓
  并按照"先重后轻"的原则递减仓位大小

  # --- 加仓条件判断 ---

  Scenario: 满足所有条件时允许加仓
    Given 多头持仓，入场价 60000，止损价 59000
    And 当前价格为 63000
    And 当前盈利为 5%
    And 趋势保持强势
    When 判断是否应该加仓，最低盈利要求 5%
    Then 应该允许加仓

  Scenario: 盈利不足时拒绝加仓
    Given 多头持仓，入场价 60000，止损价 59000
    And 当前价格为 61500
    And 当前盈利为 2.5%
    And 趋势保持强势
    When 判断是否应该加仓，最低盈利要求 5%
    Then 应该拒绝加仓
    And 拒绝原因包含 "Profit"

  Scenario: 价格回落到入场价以下时拒绝加仓
    Given 多头持仓，入场价 60000，止损价 59000
    And 当前价格为 59500
    And 当前盈利为 5%
    And 趋势保持强势
    When 判断是否应该加仓，最低盈利要求 5%
    Then 应该拒绝加仓
    And 拒绝原因包含 "not above entry"

  Scenario: 趋势转弱时拒绝加仓
    Given 多头持仓，入场价 60000，止损价 59000
    And 当前价格为 63000
    And 当前盈利为 5%
    And 趋势已转弱
    When 判断是否应该加仓，最低盈利要求 5%
    Then 应该拒绝加仓
    And 拒绝原因包含 "Trend no longer strong"

  # --- 加仓仓位计算 ---

  Scenario Outline: 金字塔各层级仓位递减
    Given 初始仓位大小为 0.1
    When 计算第 <level> 层加仓仓位
    Then 加仓仓位应为 <expected_size>

    Examples:
      | level | expected_size |
      | 1     | 0.05          |
      | 2     | 0.025         |
      | 3     | 0.0125        |
