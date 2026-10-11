# 错误码契约 — BDD 试点（Gherkin）

> 功能：错误码契约（表 4-13 的错误码语义）
> 背景：审查报告「BDD 规格」维度两轮判不通过（零资产），报告结论为「低频可选，试点即可」。
> 本目录即**试点**：一个 feature 文件 ＋ 一个零依赖轻量执行器，证明 BDD 形态在本项目可行；
> 不引入 pytest-bdd 依赖、不进主套件（运行测试.ps1 不收集 bdd/——其文件不以 test_ 开头）。

Feature: A 股财经问答系统的错误码契约
  作为 API 使用方
  我需要每个接口在异常输入下返回明确且稳定的错误码
  以便客户端按契约处理异常而不是猜测

  Background:
    Given 后端服务运行于 8000 端口（离线模式下用 TestClient 进程内替代）

  Scenario: 提问输入为空
    When 提交 question 为空串
    Then 响应码为 1001 且 HTTP 状态为 400

  Scenario: 提交非法 JSON
    When 请求体不是合法 JSON
    Then 响应码为 1002 且 HTTP 状态为 400

  Scenario: 必填字段缺失
    When 提交的请求体缺 question 键
    Then 响应码为 1003 且 HTTP 状态为 400

  Scenario: 不存在的回答
    When 查询 answer_id 999999
    Then 响应码为 2001 且 HTTP 状态为 404

  Scenario: 查询结果为空不是错误
    When 按一个无记录的会话查询历史
    Then HTTP 状态为 200 且响应体不出现错误码
