Feature: 每日亏损限额
  作为交易系统的风控模块
  我需要在当日亏损达到限额时停止交易
  以防止情绪化交易导致的重大损失

  Scenario: 亏损在限额内允许继续交易
    Given 每日亏损限额为 3%
    And 账户余额为 10000 USDT
    When 当日亏损为 200 USDT
    Then 不应触发亏损限额
    And 限额消息包含 "Remaining loss allowance"

  Scenario: 亏损超过限额停止交易
    Given 每日亏损限额为 3%
    And 账户余额为 10000 USDT
    When 当日亏损为 350 USDT
    Then 应触发亏损限额
    And 限额消息包含 "STOP TRADING"

  Scenario: 亏损恰好等于限额时停止交易
    Given 每日亏损限额为 3%
    And 账户余额为 10000 USDT
    When 当日亏损为 300 USDT
    Then 应触发亏损限额

  Scenario: 盈利时不触发限额
    Given 每日亏损限额为 3%
    And 账户余额为 10000 USDT
    When 当日盈利为 500 USDT
    Then 不应触发亏损限额
