#!/usr/bin/env python3
"""E2E测试健康检查脚本

检查测试运行状态、错误率、延迟等指标
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import re
from collections import defaultdict


def parse_log_line(line):
    """解析日志行"""
    # Example: 2026-01-27 15:48:34 | INFO | ...
    match = re.match(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+\|\s+(\w+)\s+\|', line)
    if match:
        timestamp = datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S')
        level = match.group(2)
        return timestamp, level, line
    return None, None, line


def analyze_logs(log_file, days=1):
    """分析日志文件"""
    if not Path(log_file).exists():
        print(f"❌ 日志文件不存在: {log_file}")
        return None

    cutoff = datetime.now() - timedelta(days=days)

    stats = {
        'total_lines': 0,
        'errors': 0,
        'warnings': 0,
        'infos': 0,
        'decisions': 0,
        'api_calls': 0,
        'latencies': [],
        'error_messages': [],
    }

    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            timestamp, level, content = parse_log_line(line)

            if timestamp and timestamp < cutoff:
                continue

            stats['total_lines'] += 1

            if level == 'ERROR':
                stats['errors'] += 1
                stats['error_messages'].append(content.strip())
            elif level == 'WARNING':
                stats['warnings'] += 1
            elif level == 'INFO':
                stats['infos'] += 1

            # 检查决策
            if 'Trading Decision' in content or 'Decision:' in content:
                stats['decisions'] += 1

            # 检查API调用
            if 'fetch' in content.lower() or 'request' in content.lower():
                stats['api_calls'] += 1

            # 提取延迟（如果有）
            latency_match = re.search(r'latency[:\s]+(\d+)ms', content, re.IGNORECASE)
            if latency_match:
                stats['latencies'].append(int(latency_match.group(1)))

    return stats


def analyze_decisions(decision_log, days=1):
    """分析决策日志"""
    if not Path(decision_log).exists():
        print(f"❌ 决策日志不存在: {decision_log}")
        return None

    cutoff = datetime.now() - timedelta(days=days)

    decisions = {
        'HOLD': 0,
        'LONG': 0,
        'SHORT': 0,
        'total': 0,
        'confluences': [],
    }

    with open(decision_log, 'r', encoding='utf-8') as f:
        for line in f:
            timestamp, _, content = parse_log_line(line)

            if timestamp and timestamp < cutoff:
                continue

            # 提取决策类型
            if 'action=HOLD' in content:
                decisions['HOLD'] += 1
                decisions['total'] += 1
            elif 'action=LONG' in content:
                decisions['LONG'] += 1
                decisions['total'] += 1
            elif 'action=SHORT' in content:
                decisions['SHORT'] += 1
                decisions['total'] += 1

            # 提取 Confluence
            conf_match = re.search(r'confluence=([0-9.]+)', content)
            if conf_match:
                decisions['confluences'].append(float(conf_match.group(1)))

    return decisions


def print_health_report(stats, decisions, days):
    """打印健康报告"""
    print("=" * 60)
    print(f"📊 端到端测试健康报告 (最近 {days} 天)")
    print("=" * 60)
    print()

    # 基础统计
    print("### 日志统计")
    print(f"  总日志行数: {stats['total_lines']:,}")
    print(f"  INFO: {stats['infos']:,}")
    print(f"  WARNING: {stats['warnings']:,}")
    print(f"  ERROR: {stats['errors']:,}")
    print()

    # 运行状态
    uptime_pct = ((stats['total_lines'] - stats['errors']) / max(stats['total_lines'], 1)) * 100
    print("### 运行状态")
    print(f"  稳定性: {uptime_pct:.2f}%")

    if stats['errors'] > 0:
        print(f"  ⚠️  发现 {stats['errors']} 个错误")
        print(f"  最近错误:")
        for err in stats['error_messages'][-3:]:
            print(f"    - {err[:100]}...")
    else:
        print(f"  ✅ 无错误记录")
    print()

    # API调用
    print("### API 调用")
    print(f"  总调用次数: {stats['api_calls']:,}")

    if stats['latencies']:
        avg_latency = sum(stats['latencies']) / len(stats['latencies'])
        max_latency = max(stats['latencies'])
        print(f"  平均延迟: {avg_latency:.0f}ms")
        print(f"  最大延迟: {max_latency}ms")

        if avg_latency < 500:
            print(f"  ✅ 延迟正常 (<500ms)")
        else:
            print(f"  ⚠️  延迟较高 (>{avg_latency:.0f}ms)")
    else:
        print(f"  未检测到延迟数据")
    print()

    # 决策统计
    if decisions and decisions['total'] > 0:
        print("### 决策统计")
        print(f"  总决策次数: {decisions['total']:,}")
        print(f"  HOLD: {decisions['HOLD']:,} ({decisions['HOLD']/decisions['total']*100:.1f}%)")
        print(f"  LONG: {decisions['LONG']:,} ({decisions['LONG']/decisions['total']*100:.1f}%)")
        print(f"  SHORT: {decisions['SHORT']:,} ({decisions['SHORT']/decisions['total']*100:.1f}%)")

        if decisions['confluences']:
            avg_conf = sum(decisions['confluences']) / len(decisions['confluences'])
            print(f"  平均 Confluence: {avg_conf:.1f}%")

            if avg_conf >= 50:
                print(f"  ✅ Confluence 合理 (≥50%)")
            else:
                print(f"  ⚠️  Confluence 偏低 (<50%)")
        print()
    else:
        print("### 决策统计")
        print("  ⚠️  未检测到决策记录")
        print()

    # 总结
    print("=" * 60)
    critical_issues = 0
    warnings = 0

    if stats['errors'] > 10:
        print(f"❌ 严重: 错误数过多 ({stats['errors']})")
        critical_issues += 1

    if stats['warnings'] > 50:
        print(f"⚠️  警告: 警告数较多 ({stats['warnings']})")
        warnings += 1

    if stats['latencies'] and sum(stats['latencies']) / len(stats['latencies']) > 500:
        print(f"⚠️  警告: 平均延迟过高")
        warnings += 1

    if decisions and decisions['total'] == 0:
        print(f"⚠️  警告: 无决策记录")
        warnings += 1

    if critical_issues == 0 and warnings == 0:
        print("✅ 系统运行正常，无严重问题")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='E2E测试健康检查')
    parser.add_argument('--days', type=int, default=1, help='检查最近N天的日志 (默认: 1)')
    parser.add_argument('--log-file', default='logs/e2e_testnet.log', help='主日志文件路径')
    parser.add_argument('--decision-log', default='logs/e2e_testnet_decisions.log', help='决策日志文件路径')

    args = parser.parse_args()

    print(f"🔍 检查最近 {args.days} 天的测试运行状态...")
    print()

    # 分析主日志
    stats = analyze_logs(args.log_file, args.days)
    if not stats:
        print("❌ 无法分析主日志")
        return 1

    # 分析决策日志
    decisions = analyze_decisions(args.decision_log, args.days)

    # 打印报告
    print_health_report(stats, decisions, args.days)

    return 0


if __name__ == '__main__':
    sys.exit(main())
