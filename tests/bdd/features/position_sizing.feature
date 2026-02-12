Feature: 初始仓位计算
  作为交易系统的风控模块
  我需要根据账户余额、风险比例和止损距离计算仓位大小
  以确保每笔交易的风险在可控范围内

  Scenario: 做多时计算仓位大小
    Given 风控参数默认风险比例为 1%
    And 账户余额为 10000 USDT
    When 计算初始仓位，入场价 60000，止损价 59000，风险比例 1%
    Then 风险金额应为 100.0 USDT
    And 仓位大小应为 0.1
    And 实际风险比例应为 1%

  Scenario: 做空时计算仓位大小
    Given 风控参数默认风险比例为 1%
    And 账户余额为 10000 USDT
    When 计算初始仓位，入场价 60000，止损价 61000，风险比例 2%
    Then 风险金额应为 200.0 USDT
    And 仓位大小应为 0.2

  Scenario: 风险比例超过上限时自动限制
    Given 风控参数最大单笔风险为 2%
    And 账户余额为 10000 USDT
    When 计算初始仓位，入场价 60000，止损价 59000，风险比例 5%
    Then 实际风险比例应为 2%
    And 风险金额应为 200.0 USDT

  Scenario Outline: 不同风险比例的仓位计算
    Given 风控参数默认风险比例为 1%
    And 账户余额为 <balance> USDT
    When 计算初始仓位，入场价 <entry>，止损价 <stop_loss>，风险比例 <risk>%
    Then 风险金额应为 <risk_amount> USDT
    And 仓位大小应为 <position_size>

    Examples:
      | balance | entry | stop_loss | risk | risk_amount | position_size |
      | 10000   | 60000 | 59000     | 0.5  | 50.0        | 0.05          |
      | 10000   | 60000 | 59000     | 1.5  | 150.0       | 0.15          |

  Scenario: 负余额返回空结果
    Given 风控参数默认风险比例为 1%
    And 账户余额为 -1000 USDT
    When 计算初始仓位，入场价 60000，止损价 59000
    Then 计算结果应为空

  Scenario: 入场价等于止损价返回空结果
    Given 风控参数默认风险比例为 1%
    And 账户余额为 10000 USDT
    When 计算初始仓位，入场价 60000，止损价 60000
    Then 计算结果应为空
