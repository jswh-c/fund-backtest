"""
基金数据获取模块
从天天基金网（东方财富）获取基金历史净值、分红、拆分数据
支持自动复权计算、数据缓存、异常重试
"""

import requests
import pandas as pd
import numpy as np
import os
import time
import json
import asyncio
from datetime import datetime

try:
    import aiohttp
except ImportError:
    aiohttp = None  # Streamlit Cloud 可能无法安装此可选依赖
from typing import Optional

# 配置
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
MAX_RETRIES = 3
RETRY_DELAY = 1  # 秒
REQUEST_TIMEOUT = 15
PAGE_SIZE = 20  # API实际每页返回数量


def _ensure_data_dir():
    """确保数据目录存在"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)


def _make_request(url: str, headers: dict = None) -> requests.Response:
    """带重试机制的HTTP请求"""
    if headers is None:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://fundf10.eastmoney.com/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    last_exception = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            last_exception = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
                print(f"  [Retry {attempt + 1}/{MAX_RETRIES}] {url[:80]}...")
    raise last_exception


def _parse_fund_name(fund_code: str) -> str:
    """获取基金名称"""
    url = f"http://fund.eastmoney.com/pingzhongdata/{fund_code}.js"
    try:
        resp = _make_request(url)
        for line in resp.text.split("\n"):
            if "fS_name" in line:
                name = line.split('"')[1]
                return name
    except Exception:
        pass

    # 备选：从基金列表API获取
    try:
        list_url = (
            f"https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx"
            f"?m=1&key={fund_code}"
        )
        resp = _make_request(list_url)
        data = resp.json()
        if data.get("Datas"):
            return data["Datas"][0]["NAME"]
    except Exception:
        pass
    return f"Fund_{fund_code}"


def _get_cache_path(fund_code: str) -> str:
    """获取缓存文件路径"""
    return os.path.join(DATA_DIR, f"{fund_code}.csv")


def _read_cache(fund_code: str) -> pd.DataFrame | None:
    """读取缓存，返回 None 若不存在或损坏"""
    csv_path = _get_cache_path(fund_code)
    if not os.path.exists(csv_path):
        return None
    try:
        df = pd.read_csv(csv_path, parse_dates=["日期"])
        if len(df) == 0:
            return None
        return df
    except Exception:
        return None


def _is_cache_fresh(df_cache: pd.DataFrame, start_date: str, end_date: str) -> bool:
    """检查缓存是否覆盖请求的日期范围"""
    if len(df_cache) == 0:
        return False
    cache_start = df_cache["日期"].min().strftime("%Y-%m-%d")
    cache_end = df_cache["日期"].max().strftime("%Y-%m-%d")
    # 缓存必须覆盖请求范围
    if cache_start > start_date or cache_end < end_date:
        return False
    # 缓存最后一天必须是最近（如果是覆盖到 today 的请求，需要检查是否 stale）
    today_str = datetime.now().strftime("%Y-%m-%d")
    if end_date >= today_str:
        # 缓存 end 必须是今天或昨天（考虑非交易日）
        cache_end_dt = df_cache["日期"].max()
        days_stale = (datetime.now() - cache_end_dt).days
        if days_stale > 5:  # 超过5天未更新则认为过期
            return False
    return True


def get_fund_data(
    fund_code: str,
    start_date: str = "2021-01-01",
    end_date: str = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    从天天基金网获取基金历史净值数据，自动处理分红拆分并计算复权净值

    参数
    ----
    fund_code : str
        6位基金代码，如 "161725"
    start_date : str
        开始日期 "YYYY-MM-DD"，默认 "2021-01-01"
    end_date : str
        结束日期 "YYYY-MM-DD"，默认今天
    use_cache : bool
        是否使用本地缓存，默认 True

    返回
    ----
    pd.DataFrame
        包含列：日期、单位净值、累计净值、日增长率、复权净值
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    _ensure_data_dir()
    csv_path = _get_cache_path(fund_code)

    # ---- 读缓存（智能检测过期） ----
    if use_cache:
        df_cache = _read_cache(fund_code)
        if df_cache is not None and _is_cache_fresh(df_cache, start_date, end_date):
            mask = (df_cache["日期"] >= pd.Timestamp(start_date)) & (
                df_cache["日期"] <= pd.Timestamp(end_date)
            )
            n_records = mask.sum()
            print(f"[CACHE HIT] {fund_code}: {n_records} records ({start_date} ~ {end_date})")
            return df_cache[mask].reset_index(drop=True)
        elif df_cache is not None:
            cache_start = df_cache["日期"].min().strftime("%Y-%m-%d")
            cache_end = df_cache["日期"].max().strftime("%Y-%m-%d")
            print(f"  [CACHE STALE] {fund_code}: cached {cache_start}~{cache_end}, need refresh")
        else:
            print(f"  [CACHE MISS] {fund_code}: no cache found")

    # ---- 从API获取数据 ----
    print(f"[FETCH] Getting fund {fund_code} NAV data...")

    # 获取基金名称
    fund_name = _parse_fund_name(fund_code)
    print(f"  Fund name: {fund_name}")

    # 获取历史净值（分页获取）
    all_records = []
    page_index = 1

    while True:
        # 东方财富基金净值API (无需callback参数)
        url = (
            f"https://api.fund.eastmoney.com/f10/lsjz?"
            f"fundCode={fund_code}"
            f"&pageIndex={page_index}&pageSize={PAGE_SIZE}"
            f"&startDate={start_date}&endDate={end_date}&_={int(time.time() * 1000)}"
        )
        try:
            resp = _make_request(url)
        except requests.RequestException as e:
            print(f"  [ERROR] Network request failed: {e}")
            # 回退到缓存
            if os.path.exists(csv_path):
                print(f"  [FALLBACK] Using cached data...")
                try:
                    df_fallback = pd.read_csv(csv_path, parse_dates=["日期"])
                    return df_fallback[
                        (df_fallback["日期"] >= start_date) & (df_fallback["日期"] <= end_date)
                    ].reset_index(drop=True)
                except Exception as cache_err:
                    print(f"  [FALLBACK ERROR] Cache file corrupted: {cache_err}")
                    raise  # 缓存也坏了，抛出原始网络错误
            raise

        # 解析JSON
        raw_text = resp.text
        json_str = raw_text
        # 去掉可能的JSONP callback包装
        if "(" in raw_text and raw_text.endswith(")"):
            json_str = raw_text[raw_text.index("(") + 1 : -1]
        data = json.loads(json_str)

        records = data.get("Data", {}) or {}  # Data可能为null
        if isinstance(records, dict):
            records = records.get("LSJZList", [])
        else:
            records = []

        if not records:
            break

        for r in records:
            dwjz = r.get("DWJZ", "0") or "0"
            ljjz = r.get("LJJZ", "0") or "0"
            all_records.append(
                {
                    "日期": r.get("FSRQ", ""),
                    "单位净值": float(dwjz) if dwjz else 0.0,
                    "累计净值": float(ljjz) if ljjz else 0.0,
                    "日增长率": r.get("JZZZL", "0.00"),
                }
            )

        total_count = data.get("TotalCount", 0)
        if page_index * PAGE_SIZE >= total_count:
            break
        page_index += 1

    if not all_records:
        raise ValueError(
            f"No data found for fund {fund_code} between {start_date} and {end_date}. "
            f"Please check the fund code."
        )

    # ---- 构建DataFrame ----
    df = pd.DataFrame(all_records)
    df["日期"] = pd.to_datetime(df["日期"])
    df = df.sort_values("日期").reset_index(drop=True)

    # 过滤掉净值为0的无效数据
    df = df[(df["单位净值"] > 0) & (df["累计净值"] > 0)]

    # ---- 计算复权净值（考虑分红和拆分） ----
    # 基于累计净值计算复权因子
    # 复权因子 = 累计净值 / 单位净值 (反映历史分红拆分)
    df["复权因子"] = df["累计净值"] / df["单位净值"]

    # 以最新日期为基准，计算复权净值
    # 使得最新日期的复权净值 = 最新单位净值
    latest_factor = df.iloc[-1]["复权因子"]
    df["复权净值"] = df["单位净值"] * (df["复权因子"] / latest_factor)

    # ---- 处理日增长率 ----
    def _parse_growth(val):
        if isinstance(val, str):
            val = val.replace("%", "")
            try:
                return float(val) / 100
            except ValueError:
                return 0.0
        try:
            return float(val) if val else 0.0
        except (ValueError, TypeError):
            return 0.0

    df["日增长率"] = df["日增长率"].apply(_parse_growth)

    # 如果日增长率数值过大（百分比形式），转换为小数
    sample_val = abs(df["日增长率"].dropna().iloc[0]) if len(df) > 0 else 0
    if sample_val > 1:
        df["日增长率"] = df["日增长率"] / 100

    # ---- 保存缓存 ----
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"[OK] Data saved to {csv_path}")
    print(f"  {len(df)} NAV records")
    print(
        f"  Date range: {df['日期'].min().strftime('%Y-%m-%d')} ~ {df['日期'].max().strftime('%Y-%m-%d')}"
    )
    if len(df) > 1:
        print(
            f"  Cumulative NAV growth: {df['累计净值'].iloc[-1] / df['累计净值'].iloc[0] - 1:.2%}"
        )

    return df


def get_available_funds(keyword: str = "") -> list:
    """
    搜索基金代码/名称
    参数
    ----
    keyword : str
        搜索关键词，如 "白酒"、"沪深300"

    返回
    ----
    list[dict]
        每个元素包含 code, name, type
    """
    if not keyword:
        return []

    url = (
        f"https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx" f"?m=1&key={keyword}"
    )
    try:
        resp = _make_request(url)
        data = resp.json()
        if data.get("Datas"):
            return [
                {
                    "code": item["CODE"],
                    "name": item["NAME"],
                    "type": item.get("FundType", ""),
                }
                for item in data["Datas"][:20]
            ]
    except Exception as e:
        print(f"Search failed: {e}")
    return []


def batch_download(
    fund_codes: list,
    start_date: str = "2021-01-01",
    end_date: str = None,
) -> dict:
    """
    批量下载多只基金数据（顺序执行）。

    返回
    ----
    dict[str, pd.DataFrame | None] : {fund_code: df or None}
    """
    results = {}
    for i, code in enumerate(fund_codes):
        try:
            print(f"[{i + 1}/{len(fund_codes)}] Downloading {code}...")
            df = get_fund_data(code, start_date, end_date)
            results[code] = df
        except Exception as e:
            print(f"[ERROR] Fund {code} download failed: {e}")
            results[code] = None
    return results


# ================================================================
# 异步批量下载（aiohttp）
# ================================================================
async def _fetch_fund_async(
    session,
    fund_code: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame | None:
    """
    异步获取单只基金数据（aiohttp 实现）。
    仅用于首次下载；缓存命中时直接走同步读取。
    """
    _ensure_data_dir()

    # 先检查缓存
    df_cache = _read_cache(fund_code)
    if df_cache is not None and _is_cache_fresh(df_cache, start_date, end_date):
        mask = (df_cache["日期"] >= pd.Timestamp(start_date)) & (
            df_cache["日期"] <= pd.Timestamp(end_date)
        )
        print(f"  [ASYNC CACHE] {fund_code}: {mask.sum()} records")
        return df_cache[mask].reset_index(drop=True)

    # 获取基金名称
    name_url = f"http://fund.eastmoney.com/pingzhongdata/{fund_code}.js"
    try:
        async with session.get(name_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            text = await resp.text()
            fund_name = fund_code
            for line in text.split("\n"):
                if "fS_name" in line:
                    fund_name = line.split('"')[1]
                    break
    except Exception:
        fund_name = f"Fund_{fund_code}"

    print(f"  [ASYNC FETCH] {fund_code}: {fund_name}")

    # 分页获取净值
    all_records = []
    page_index = 1

    while True:
        url = (
            f"https://api.fund.eastmoney.com/f10/lsjz?"
            f"fundCode={fund_code}"
            f"&pageIndex={page_index}&pageSize={PAGE_SIZE}"
            f"&startDate={start_date}&endDate={end_date}&_={int(time.time() * 1000)}"
        )
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as resp:
                raw_text = await resp.text()
        except Exception as e:
            print(f"  [ASYNC ERROR] {fund_code} page {page_index}: {e}")
            break

        # 解析 JSON
        json_str = raw_text
        if "(" in raw_text and raw_text.endswith(")"):
            json_str = raw_text[raw_text.index("(") + 1 : -1]
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            break

        records = data.get("Data", {}) or {}
        if isinstance(records, dict):
            records = records.get("LSJZList", [])
        else:
            records = []

        if not records:
            break

        for r in records:
            dwjz = r.get("DWJZ", "0") or "0"
            ljjz = r.get("LJJZ", "0") or "0"
            all_records.append(
                {
                    "日期": r.get("FSRQ", ""),
                    "单位净值": float(dwjz) if dwjz else 0.0,
                    "累计净值": float(ljjz) if ljjz else 0.0,
                    "日增长率": r.get("JZZZL", "0.00"),
                }
            )

        total_count = data.get("TotalCount", 0)
        if page_index * PAGE_SIZE >= total_count:
            break
        page_index += 1

    if not all_records:
        print(f"  [ASYNC WARN] {fund_code}: no records fetched, trying cache fallback")
        if df_cache is not None:
            mask = (df_cache["日期"] >= pd.Timestamp(start_date)) & (
                df_cache["日期"] <= pd.Timestamp(end_date)
            )
            return df_cache[mask].reset_index(drop=True)
        return None

    # 构建 DataFrame（与同步版逻辑完全一致）
    df = pd.DataFrame(all_records)
    df["日期"] = pd.to_datetime(df["日期"])
    df = df.sort_values("日期").reset_index(drop=True)
    df = df[(df["单位净值"] > 0) & (df["累计净值"] > 0)]

    df["复权因子"] = df["累计净值"] / df["单位净值"]
    latest_factor = df.iloc[-1]["复权因子"]
    df["复权净值"] = df["单位净值"] * (df["复权因子"] / latest_factor)

    # 解析日增长率
    df["日增长率"] = df["日增长率"].apply(
        lambda v: (
            float(str(v).replace("%", "")) / 100 if isinstance(v, str) else (float(v) if v else 0.0)
        )
    )
    sample = abs(df["日增长率"].dropna().iloc[0]) if len(df) > 0 else 0
    if sample > 1:
        df["日增长率"] = df["日增长率"] / 100

    # 保存缓存
    df.to_csv(_get_cache_path(fund_code), index=False, encoding="utf-8-sig")
    print(f"  [ASYNC OK] {fund_code}: {len(df)} records, cached")
    return df


async def batch_download_async(
    fund_codes: list,
    start_date: str = "2021-01-01",
    end_date: str = None,
    max_concurrent: int = 5,
) -> dict:
    """
    异步批量下载多只基金数据（使用 aiohttp 并发请求）。

    参数
    ----
    fund_codes : list[str]
        基金代码列表
    start_date / end_date : str
        日期范围
    max_concurrent : int
        最大并发数

    返回
    ----
    dict[str, pd.DataFrame | None] : {fund_code: df or None}
    """
    import asyncio

    if aiohttp is None:
        raise ImportError("aiohttp is not installed. Use batch_download() for synchronous mode.")

    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    # 先用缓存过滤已命中的基金
    cached_results = {}
    to_fetch = []
    for code in fund_codes:
        df_cache = _read_cache(code)
        if df_cache is not None and _is_cache_fresh(df_cache, start_date, end_date):
            mask = (df_cache["日期"] >= pd.Timestamp(start_date)) & (
                df_cache["日期"] <= pd.Timestamp(end_date)
            )
            cached_results[code] = df_cache[mask].reset_index(drop=True)
            print(f"  [ASYNC CACHE] {code}: {mask.sum()} records (skip fetch)")
        else:
            to_fetch.append(code)

    if not to_fetch:
        print(f"[ASYNC BATCH] All {len(fund_codes)} fund(s) served from cache!")
        return cached_results

    print(f"[ASYNC BATCH] Fetching {len(to_fetch)} fund(s) concurrently (max {max_concurrent})...")

    semaphore = asyncio.Semaphore(max_concurrent)

    async def _fetch_with_limit(session, code):
        async with semaphore:
            return code, await _fetch_fund_async(session, code, start_date, end_date)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://fundf10.eastmoney.com/",
        "Accept": "application/json, text/plain, */*",
    }

    connector = aiohttp.TCPConnector(limit=max_concurrent, limit_per_host=2)
    timeout = aiohttp.ClientTimeout(total=60)

    async with aiohttp.ClientSession(headers=headers, connector=connector, timeout=timeout) as sess:
        tasks = [_fetch_with_limit(sess, code) for code in to_fetch]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

    for item in results_list:
        if isinstance(item, Exception):
            print(f"  [ASYNC ERROR] {item}")
        else:
            code, df = item
            cached_results[code] = df

    print(f"[ASYNC BATCH] Done: {len(cached_results)}/{len(fund_codes)} funds")
    return cached_results


def batch_download_async_sync(
    fund_codes: list,
    start_date: str = "2021-01-01",
    end_date: str = None,
    max_concurrent: int = 5,
) -> dict:
    """
    同步包装器：在同步代码中调用异步批量下载。
    用法同 batch_download_async，但可从普通 Python 代码直接调用。
    """
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 在已运行的事件循环中（如 Jupyter），使用 nest_asyncio
            try:
                import nest_asyncio
                nest_asyncio.apply()
            except ImportError:
                pass
    except RuntimeError:
        pass
    return asyncio.run(batch_download_async(fund_codes, start_date, end_date, max_concurrent))


if __name__ == "__main__":
    # 测试：获取招商中证白酒指数(161725)近5年数据
    print("=" * 60)
    print("Fund Data Fetcher Test")
    print("=" * 60)

    df = get_fund_data("161725", start_date="2021-01-01", end_date="2026-01-01")
    print("\n--- Data Preview ---")
    print(df.head(10))
    print(f"\nShape: {df.shape}")
    print(f"Columns: {df.columns.tolist()}")
    print(f"NAV range: {df['单位净值'].min():.4f} ~ {df['单位净值'].max():.4f}")
