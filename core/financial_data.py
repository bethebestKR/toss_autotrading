"""
재무 데이터 수집 모듈

KR 주식: dart-fss(corp_code 조회) + DART REST API(재무제표)
US 주식: yfinance
캐시: data/trading.db financial_cache 테이블 (기본 TTL 7일)

표준 출력 형식:
{
    symbol, name, market, currency,
    revenue, revenue_prev, revenue_growth,        # 억원(KR) / 백만USD(US)
    operating_income, net_income,
    total_equity, total_assets, total_liabilities,
    operating_margin, net_margin, roe, debt_ratio, # %
    per, pbr, market_cap,
    fiscal_year, as_of, source
}
"""
import os
import json
import requests
from datetime import datetime
from core import db

_DART_BASE = "https://opendart.fss.or.kr/api"
_corp_list_cache = None   # dart_fss CorpList — 최초 1회 로드 후 재사용


def _is_kr(symbol: str) -> bool:
    return symbol.isdigit()


# ── DART (KR) ─────────────────────────────────────────────────────────────────

def _get_dart_corp_list():
    global _corp_list_cache
    if _corp_list_cache is None:
        api_key = os.getenv("DART_API_KEY", "")
        if not api_key:
            raise EnvironmentError(
                "DART_API_KEY 없음. https://opendart.fss.or.kr 에서 무료 발급 후 .env에 추가하세요."
            )
        import dart_fss as dart
        dart.set_api_key(api_key)
        print("[financial_data] DART 기업 목록 로드 중 (최초 1회, 최대 30초)...")
        _corp_list_cache = dart.get_corp_list()
    return _corp_list_cache


def _dart_fetch_accounts(corp_code: str, year: str) -> list[dict]:
    """DART fnlttSinglAcntAll — 연결(CFS) 우선, 실패 시 개별(OFS)."""
    api_key = os.getenv("DART_API_KEY", "")
    for fs_div in ("CFS", "OFS"):
        params = {
            "crtfc_key": api_key,
            "corp_code":  corp_code,
            "bsns_year":  year,
            "reprt_code": "11011",   # 사업보고서(연간)
            "fs_div":     fs_div,
        }
        try:
            resp = requests.get(f"{_DART_BASE}/fnlttSinglAcntAll.json",
                                params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "000" and data.get("list"):
                return data["list"]
        except Exception:
            pass
    return []


def _extract(rows: list[dict], *names: str, prev: bool = False) -> float | None:
    key = "frmtrm_amount" if prev else "thstrm_amount"
    for row in rows:
        if row.get("account_nm", "").strip() in names:
            try:
                return float(row.get(key, "").replace(",", ""))
            except (ValueError, AttributeError):
                return None
    return None


def _get_kr_financials(stock_code: str) -> dict | None:
    try:
        corp_list = _get_dart_corp_list()
        corp = corp_list.find_by_stock_code(stock_code)
        if not corp:
            print(f"[financial_data] DART에서 {stock_code} 종목을 찾을 수 없음")
            return None
        corp_code = corp.corp_code
        name = corp.corp_name
    except Exception as e:
        print(f"[financial_data] DART corp 조회 실패 {stock_code}: {e}")
        return None

    # 전년도 우선, 실패 시 전전년도
    cur_year = datetime.now().year
    rows: list[dict] = []
    fiscal_year = ""
    for year in (str(cur_year - 1), str(cur_year - 2)):
        rows = _dart_fetch_accounts(corp_code, year)
        if rows:
            fiscal_year = year
            break

    if not rows:
        print(f"[financial_data] {stock_code}({name}) 재무제표 없음")
        return None

    REVENUE_NAMES = ("매출액", "영업수익", "수익(매출액)", "순매출액")
    OP_NAMES      = ("영업이익", "영업이익(손실)")
    NI_NAMES      = ("당기순이익", "당기순이익(손실)")
    EQUITY_NAMES  = ("자본총계",)
    ASSETS_NAMES  = ("자산총계",)
    LIAB_NAMES    = ("부채총계",)

    rev     = _extract(rows, *REVENUE_NAMES)
    rev_p   = _extract(rows, *REVENUE_NAMES, prev=True)
    op_inc  = _extract(rows, *OP_NAMES)
    net_inc = _extract(rows, *NI_NAMES)
    equity  = _extract(rows, *EQUITY_NAMES)
    assets  = _extract(rows, *ASSETS_NAMES)
    liab    = _extract(rows, *LIAB_NAMES)

    def eok(v): return round(v / 1e8, 1) if v is not None else None

    rev_eok, rev_p_eok = eok(rev), eok(rev_p)
    op_eok, ni_eok     = eok(op_inc), eok(net_inc)
    eq_eok, as_eok, lb_eok = eok(equity), eok(assets), eok(liab)

    rev_growth  = round((rev - rev_p) / abs(rev_p) * 100, 1) if rev and rev_p else None
    op_margin   = round(op_inc / rev * 100, 1)   if op_inc  and rev  and rev  != 0 else None
    net_margin  = round(net_inc / rev * 100, 1)  if net_inc and rev  and rev  != 0 else None
    roe         = round(net_inc / equity * 100, 1) if net_inc and equity and equity > 0 else None
    debt_ratio  = round(liab / equity * 100, 1)  if liab and equity and equity > 0 else None

    return {
        "symbol": stock_code, "name": name, "market": "KR", "currency": "KRW",
        "revenue": rev_eok, "revenue_prev": rev_p_eok, "revenue_growth": rev_growth,
        "operating_income": op_eok, "net_income": ni_eok,
        "total_equity": eq_eok, "total_assets": as_eok, "total_liabilities": lb_eok,
        "operating_margin": op_margin, "net_margin": net_margin,
        "roe": roe, "debt_ratio": debt_ratio,
        "per": None, "pbr": None, "market_cap": None,   # 주가 연계 — strategy2에서 보완
        "fiscal_year": fiscal_year,
        "as_of": datetime.now().strftime("%Y-%m-%d"),
        "source": "DART",
    }


# ── yfinance (US) ─────────────────────────────────────────────────────────────

def _get_us_financials(ticker: str) -> dict | None:
    try:
        import yfinance as yf
        t    = yf.Ticker(ticker)
        info = t.info or {}
        if not info.get("regularMarketPrice") and not info.get("currentPrice"):
            return None

        income = t.income_stmt
        bs     = t.balance_sheet

        def _row(df, *keys):
            for k in keys:
                if k in df.index:
                    try:
                        return float(df.loc[k].iloc[0])
                    except Exception:
                        pass
            return None

        def _row_prev(df, *keys):
            for k in keys:
                if k in df.index and len(df.columns) > 1:
                    try:
                        return float(df.loc[k].iloc[1])
                    except Exception:
                        pass
            return None

        rev     = _row(income, "Total Revenue")
        rev_p   = _row_prev(income, "Total Revenue")
        op_inc  = _row(income, "Operating Income", "Ebit")
        net_inc = _row(income, "Net Income")
        equity  = _row(bs, "Stockholders Equity", "Common Stock Equity")
        assets  = _row(bs, "Total Assets")
        liab    = _row(bs, "Total Liabilities Net Minority Interest", "Total Liabilities")

        def m(v): return round(v / 1e6, 1) if v is not None else None  # → million USD

        rev_m, rev_p_m   = m(rev), m(rev_p)
        op_m, ni_m       = m(op_inc), m(net_inc)
        eq_m, as_m, lb_m = m(equity), m(assets), m(liab)

        rev_growth = round((rev - rev_p) / abs(rev_p) * 100, 1) if rev and rev_p else None
        op_margin  = round(op_inc / rev * 100, 1) if op_inc and rev and rev != 0 else None
        net_margin = round(net_inc / rev * 100, 1) if net_inc and rev and rev != 0 else None
        roe_raw    = info.get("returnOnEquity")
        roe        = round(roe_raw * 100, 1) if roe_raw is not None else None
        debt_ratio = round(liab / equity * 100, 1) if liab and equity and equity != 0 else None
        mktcap     = round(info.get("marketCap", 0) / 1e6, 0) if info.get("marketCap") else None
        fiscal_year = str(datetime.now().year - 1)

        return {
            "symbol": ticker, "name": info.get("longName", ticker),
            "market": "US", "currency": "USD",
            "revenue": rev_m, "revenue_prev": rev_p_m, "revenue_growth": rev_growth,
            "operating_income": op_m, "net_income": ni_m,
            "total_equity": eq_m, "total_assets": as_m, "total_liabilities": lb_m,
            "operating_margin": op_margin, "net_margin": net_margin,
            "roe": roe, "debt_ratio": debt_ratio,
            "per": info.get("trailingPE"), "pbr": info.get("priceToBook"),
            "market_cap": mktcap,
            "fiscal_year": fiscal_year,
            "as_of": datetime.now().strftime("%Y-%m-%d"),
            "source": "yfinance",
        }
    except Exception as e:
        print(f"[financial_data] yfinance 조회 실패 {ticker}: {e}")
        return None


# ── 공개 API ──────────────────────────────────────────────────────────────────

def get_financials(symbol: str, cache_days: int = 7) -> dict | None:
    """재무 데이터 조회. 캐시 우선(TTL=cache_days), 만료/미존재 시 API 호출."""
    cached = db.get_financial_cache(symbol, max_age_days=cache_days)
    if cached:
        return cached
    data = _get_kr_financials(symbol) if _is_kr(symbol) else _get_us_financials(symbol)
    if data:
        db.set_financial_cache(symbol, data)
    return data


def get_financials_batch(symbols: list[str], cache_days: int = 7) -> dict[str, dict]:
    """여러 종목 재무 데이터 순차 조회. {symbol: data} 반환."""
    results: dict[str, dict] = {}
    for sym in symbols:
        data = get_financials(sym, cache_days=cache_days)
        if data:
            results[sym] = data
        else:
            print(f"[financial_data] {sym} 데이터 없음 — 건너뜀")
    return results


def fmt_financials(data: dict) -> str:
    """Claude 프롬프트용 재무 데이터 텍스트 포맷."""
    unit = "억원" if data.get("market") == "KR" else "백만USD"
    lines = [
        f"[{data['symbol']}] {data['name']} ({data['market']}, FY{data['fiscal_year']})",
        f"  매출: {data.get('revenue')} {unit} (전년 {data.get('revenue_prev')}, 성장률 {data.get('revenue_growth')}%)",
        f"  영업이익: {data.get('operating_income')} {unit} (이익률 {data.get('operating_margin')}%)",
        f"  순이익: {data.get('net_income')} {unit} (순이익률 {data.get('net_margin')}%)",
        f"  ROE: {data.get('roe')}% | 부채비율: {data.get('debt_ratio')}%",
        f"  PER: {data.get('per')} | PBR: {data.get('pbr')} | 시가총액: {data.get('market_cap')} {unit}",
    ]
    return "\n".join(lines)
