Feature: 信号过滤（反过度交易）
  作为交易系统的风控模块
  我需要限制交易频率和方向翻转
  以防止情绪化的频繁交易造成亏损

  Background:
    Given 信号过滤器最小间隔为 4 小时
    And 信号过滤器反转冷却为 12 小时

  # ── 核心用户流 ──────────────────────────────

  Scenario: 首次交易信号直接放行
    When 收到 LONG 信号
    Then 信号应被允许
    And 原因包含 "Signal allowed"

  Scenario: HOLD 信号总是放行
    Given 上次交易为 LONG，1 小时前
    When 收到 HOLD 信号
    Then 信号应被允许

  Scenario: 间隔充足时允许同方向交易
    Given 上次交易为 LONG，5 小时前
    When 收到 LONG 信号
    Then 信号应被允许

  # ── 异常流 ──────────────────────────────────

  Scenario: 间隔不足时拒绝交易
    Given 上次交易为 LONG，2 小时前
    When 收到 SHORT 信号
    Then 信号应被拒绝
    And 原因包含 "Too soon"

  Scenario: 方向翻转冷却期内拒绝反向信号
    Given 上次交易为 LONG，6 小时前
    When 收到 SHORT 信号
    Then 信号应被拒绝
    And 原因包含 "Action flip too quick"

  Scenario: 方向翻转冷却期后允许反向信号
    Given 上次交易为 LONG，13 小时前
    When 收到 SHORT 信号
    Then 信号应被允许

  # ── 边界行为 ──────────────────────────────────

  Scenario: 恰好在最小间隔时允许交易
    Given 上次交易为 LONG，4 小时前
    When 收到 LONG 信号
    Then 信号应被允许

  Scenario: 恰好在反转冷却时允许反向交易
    Given 上次交易为 SHORT，12 小时前
    When 收到 LONG 信号
    Then 信号应被允许
