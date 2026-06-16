"""
主程序入口
支持命令行运行回测，一键对比所有策略
"""

import sys
import argparse
from data_fetcher import get_fund_data, get_available_funds
from backtest import FundBacktest
from utils import print_backtest_result
from visualization import plot_all_results, plot_comparison_table


def main():
    parser = argparse.ArgumentParser(
        description="Fund DCA Backtest & AI Optimization System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --code 161725 --start 2021-01-01 --end 2026-06-09
  python main.py --code 161725,002610 --amount 500 --day 15
  python main.py --code 161725 --optimize
  python main.py --code 161725 --all --output
        """,
    )
    parser.add_argument(
        "--code", type=str, default="161725", help="Fund code(s), comma-separated (default: 161725)"
    )
    parser.add_argument("--start", type=str, default="2021-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument(
        "--end", type=str, default=None, help="End date YYYY-MM-DD (default: today)"
    )
    parser.add_argument(
        "--amount", type=float, default=1000, help="Monthly invest amount (default: 1000)"
    )
    parser.add_argument("--day", type=int, default=1, help="Invest day of month (default: 1)")
    parser.add_argument(
        "--fee", type=float, default=0.0015, help="Subscription fee rate (default: 0.0015)"
    )
    parser.add_argument(
        "--stop-profit", type=float, default=0.20, help="Stop-profit threshold (default: 0.20)"
    )
    parser.add_argument(
        "--value-growth",
        type=float,
        default=1000,
        help="Value average monthly growth target (default: 1000)",
    )
    parser.add_argument(
        "--ma-period", type=int, default=250, help="MA period for dynamic DCA (default: 250)"
    )
    parser.add_argument("--all", action="store_true", help="Run all strategies")
    parser.add_argument(
        "--optimize", action="store_true", help="Run parameter optimization for MA dynamic DCA"
    )
    parser.add_argument("--output", action="store_true", help="Save charts as HTML files")
    parser.add_argument("--search", type=str, default=None, help="Search for fund codes by keyword")

    args = parser.parse_args()

    # 搜索基金
    if args.search:
        funds = get_available_funds(args.search)
        if funds:
            print(f"\nSearch results for '{args.search}':")
            print(f"{'Code':<10} {'Name':<40} {'Type'}")
            print("-" * 70)
            for f in funds:
                print(f"{f['code']:<10} {f['name']:<40} {f['type']}")
        else:
            print(f"No funds found for '{args.search}'")
        return

    # 解析基金代码
    fund_codes = [c.strip() for c in args.code.split(",")]

    for fund_code in fund_codes:
        print(f"\n{'=' * 60}")
        print(f"  Fund: {fund_code}")
        print(f"  Period: {args.start} ~ {args.end or 'today'}")
        print(f"  Invest: {args.amount:.0f} yuan/month on day {args.day}")
        print(f"{'=' * 60}")

        # 获取数据
        try:
            df = get_fund_data(fund_code, args.start, args.end)
        except Exception as e:
            print(f"[ERROR] Failed to get data for {fund_code}: {e}")
            continue

        # 创建回测引擎
        bt = FundBacktest(
            df,
            invest_amount=args.amount,
            invest_day=args.day,
            fee_rate=args.fee,
        )

        # 运行策略
        results = []
        names = []

        # 始终运行普通定投作为基准
        print("\nRunning Normal DCA...")
        r1 = bt.run_normal_dca()
        results.append(r1)
        names.append("Normal DCA")
        print_backtest_result(r1, "Normal DCA")

        if args.all or args.stop_profit:
            print("\nRunning Stop-Profit DCA...")
            r2 = bt.run_stop_profit_dca(stop_profit=args.stop_profit)
            results.append(r2)
            names.append(f"Stop-Profit {args.stop_profit:.0%}")
            print_backtest_result(r2, names[-1])
            if r2.stop_profit_events:
                print(f"  Stop-profit events: {len(r2.stop_profit_events)}")
                for evt in r2.stop_profit_events:
                    print(
                        f"    {evt['日期'].strftime('%Y-%m-%d')}: "
                        f"profit={evt['收益']:.0f}, return={evt['收益率']:.2%}"
                    )

        if args.all:
            print("\nRunning Value Average...")
            try:
                r3 = bt.run_value_average(target_growth=args.value_growth)
                results.append(r3)
                names.append(f"Value Avg +{args.value_growth:.0f}/mth")
                print_backtest_result(r3, names[-1])
            except Exception as e:
                print(f"  [WARN] Value Average failed: {e}")

        if args.all:
            print("\nRunning MA Dynamic DCA...")
            r4 = bt.run_ma_dynamic_dca(
                ma_period=args.ma_period,
                low_multiplier=2.0,
                high_multiplier=0.5,
            )
            results.append(r4)
            names.append(f"MA{args.ma_period} Dynamic")
            print_backtest_result(r4, names[-1])

        # 参数优化
        if args.optimize:
            print("\n\n--- Parameter Optimization ---")
            print("Searching for optimal MA dynamic DCA parameters...")
            try:
                opt_result = bt.optimize_ma_bayesian(
                    n_trials=60,
                    train_start=args.start,
                    train_end="2020-12-31",
                )
                best = opt_result["best_params"]
                print(f"\nBest params (Optuna Bayesian): {best}")
                print(f"  Train Sharpe: {opt_result['train_sharpe']:.4f}")
                print(f"  Test Sharpe:  {opt_result['test_sharpe']:.4f}")
                print(f"  Train Annual: {opt_result['train_result'].annual_return:+.2%}")
                print(f"  Test Annual:  {opt_result['test_result'].annual_return:+.2%}")

                # 用最优参数再跑一次（测试集）
                print("\nRe-running with optimal parameters on full data...")
                r_opt = bt.run_ma_dynamic_dca(
                    ma_period=int(best["ma_period"]),
                    low_multiplier=float(best["low_multiplier"]),
                    high_multiplier=float(best["high_multiplier"]),
                    low_threshold=float(best["low_threshold"]),
                    high_threshold=float(best["high_threshold"]),
                )
                results.append(r_opt)
                names.append("Optimized MA Dynamic")
                print_backtest_result(r_opt, "Optimized MA Dynamic")
            except Exception as e:
                print(f"[WARN] Optimization failed: {e}")

        # 生成图表
        if args.output and len(results) > 1:
            print("\n\nGenerating charts...")
            plot_all_results(results, names, save_html=True)
            print("Charts saved to 'output/' folder.")

        # 最终对比表
        if len(results) > 1:
            print(f"\n{'=' * 60}")
            print("  FINAL COMPARISON")
            print(f"{'=' * 60}")
            print(f"{'Strategy':<22} {'Annual':>8} {'Sharpe':>8} {'MaxDD':>8} {'Vol':>8}")
            print("-" * 60)
            for name, r in zip(names, results):
                print(
                    f"{name:<22} {r.annual_return:>+7.2%} {r.sharpe_ratio:>8.4f} "
                    f"{r.max_drawdown:>7.2%} {r.volatility:>7.2%}"
                )


if __name__ == "__main__":
    main()
