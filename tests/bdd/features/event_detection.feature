Feature: 事件检测与冷却管理
  作为事件驱动交易系统
  我需要根据策略配置检测市场事件并管理冷却
  以避免重复触发和无关事件干扰决策

  # ── 策略过滤 ──────────────────────────────────

  Scenario: 仅检测已启用策略关注的事件类型
    Given 启用策略为 trend_following
    When 执行事件扫描
    Then 活跃事件类型应包含 "price_surge"
    And 活跃事件类型应包含 "macd_cross"
    And 活跃事件类型不应包含 "rsi_extreme"
    And 活跃事件类型不应包含 "volume_spike"

  Scenario: 多策略事件类型取并集
    Given 启用策略为 trend_following,breakout
    When 执行事件扫描
    Then 活跃事件类型应包含 "price_surge"
    And 活跃事件类型应包含 "macd_cross"
    And 活跃事件类型应包含 "volume_spike"
    And 活跃事件类型应包含 "bollinger_break"

  Scenario: 无启用策略时不检测任何事件
    Given 启用策略为空
    When 对市场数据执行扫描
    Then 触发事件列表应为空

  # ── 全局开关 ──────────────────────────────────

  Scenario: 全局禁用时不检测事件
    Given 启用策略为 trend_following
    And 事件检测全局禁用
    When 对市场数据执行扫描
    Then 触发事件列表应为空

  # ── 单事件禁用 ──────────────────────────────────

  Scenario: 单个事件类型禁用时跳过该检测器
    Given 启用策略为 trend_following
    And price_surge 事件被禁用
    When 对市场数据执行扫描
    Then 触发事件不应包含 "price_surge"

  # ── 冷却机制 ──────────────────────────────────

  Scenario: 全局冷却期内所有事件被阻止
    Given 冷却管理器全局冷却为 300 秒，事件冷却为 600 秒
    And price_surge 事件刚刚触发
    When 检查 rsi_extreme 是否可触发
    Then 该事件不可触发

  Scenario: 事件级冷却期内同类事件被阻止
    Given 冷却管理器全局冷却为 1 秒，事件冷却为 600 秒
    And price_surge 事件在 2 秒前触发
    When 检查 price_surge 是否可触发
    Then 该事件不可触发

  Scenario: 冷却期过后事件可以再次触发
    Given 冷却管理器全局冷却为 1 秒，事件冷却为 1 秒
    And price_surge 事件在 2 秒前触发
    When 检查 price_surge 是否可触发
    Then 该事件可以触发

  Scenario: 重置冷却后所有事件可触发
    Given 冷却管理器全局冷却为 300 秒，事件冷却为 600 秒
    And price_surge 事件刚刚触发
    When 重置冷却管理器
    Then price_surge 应可以触发
