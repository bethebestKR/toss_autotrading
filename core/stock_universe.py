"""
종목 검색 모듈.
- 국내: KRX에서 KOSPI/KOSDAQ 전종목 다운로드 (data/kr_stocks.csv 캐시)
- 미국: 인기 종목 정적 매핑
"""
import os
import io

import requests
import pandas as pd

_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
_KR_CSV = os.path.join(_DATA_DIR, 'kr_stocks.csv')

# 토스증권에서 거래 가능한 미국 인기 종목 (티커, 한글명)
_US_STOCKS = [
    # 우주/방산
    ("SPCX",  "스페이스X"),
    # 빅테크
    ("AAPL",  "애플"),
    ("MSFT",  "마이크로소프트"),
    ("GOOGL", "알파벳"),
    ("GOOG",  "알파벳C"),
    ("AMZN",  "아마존"),
    ("NVDA",  "엔비디아"),
    ("TSLA",  "테슬라"),
    ("META",  "메타"),
    ("NFLX",  "넷플릭스"),
    ("AMD",   "AMD"),
    ("INTC",  "인텔"),
    ("QCOM",  "퀄컴"),
    ("AVGO",  "브로드컴"),
    ("TSM",   "TSMC"),
    ("ASML",  "ASML"),
    ("MU",    "마이크론"),
    ("AMAT",  "어플라이드머티리얼즈"),
    ("LRCX",  "램리서치"),
    ("KLAC",  "KLA"),
    ("TXN",   "텍사스인스트루먼트"),
    ("ORCL",  "오라클"),
    ("IBM",   "IBM"),
    ("CSCO",  "시스코"),
    ("CRM",   "세일즈포스"),
    ("NOW",   "서비스나우"),
    ("SNOW",  "스노우플레이크"),
    ("PLTR",  "팔란티어"),
    ("ADBE",  "어도비"),
    # 금융
    ("JPM",   "JP모건"),
    ("BAC",   "뱅크오브아메리카"),
    ("GS",    "골드만삭스"),
    ("MS",    "모건스탠리"),
    ("WFC",   "웰스파고"),
    ("C",     "씨티그룹"),
    ("V",     "비자"),
    ("MA",    "마스터카드"),
    ("PYPL",  "페이팔"),
    ("BRK.B", "버크셔해서웨이B"),
    ("AXP",   "아메리칸익스프레스"),
    ("BX",    "블랙스톤"),
    # 헬스케어
    ("JNJ",   "존슨앤존슨"),
    ("PFE",   "화이자"),
    ("MRK",   "머크"),
    ("ABBV",  "애브비"),
    ("LLY",   "일라이릴리"),
    ("UNH",   "유나이티드헬스"),
    ("AMGN",  "암젠"),
    ("GILD",  "길리어드"),
    ("BMY",   "브리스톨마이어스"),
    ("MRNA",  "모더나"),
    # 에너지/소재
    ("CVX",   "쉐브론"),
    ("XOM",   "엑슨모빌"),
    ("COP",   "코노코필립스"),
    # 소비재/미디어
    ("DIS",   "월트디즈니"),
    ("CMCSA", "컴캐스트"),
    ("T",     "AT&T"),
    ("VZ",    "버라이즌"),
    ("NKE",   "나이키"),
    ("SBUX",  "스타벅스"),
    ("MCD",   "맥도날드"),
    ("KO",    "코카콜라"),
    ("PEP",   "펩시코"),
    ("WMT",   "월마트"),
    ("COST",  "코스트코"),
    ("TGT",   "타겟"),
    ("HD",    "홈디포"),
    ("AMZN",  "아마존"),
    # 모빌리티/전기차
    ("UBER",  "우버"),
    ("LYFT",  "리프트"),
    ("ABNB",  "에어비앤비"),
    ("RIVN",  "리비안"),
    ("LCID",  "루시드"),
    ("NIO",   "니오"),
    ("XPEV",  "샤오펑"),
    ("LI",    "리오토모빌"),
    # 중국 ADR
    ("BABA",  "알리바바"),
    ("JD",    "징둥닷컴"),
    ("PDD",   "핀둬둬"),
    ("BIDU",  "바이두"),
    ("NTES",  "넷이즈"),
    # 핀테크/크립토
    ("COIN",  "코인베이스"),
    ("HOOD",  "로빈후드"),
    ("SQ",    "블록"),
    ("SOFI",  "소파이"),
    # ETF
    ("SPY",   "S&P500 ETF"),
    ("QQQ",   "나스닥100 ETF"),
    ("IWM",   "러셀2000 ETF"),
    ("SOXX",  "반도체 ETF"),
    ("ARKK",  "ARK이노베이션 ETF"),
    ("GLD",   "금 ETF"),
    ("SLV",   "은 ETF"),
    ("TLT",   "장기국채 ETF"),
    ("SOXL",  "반도체 3배 ETF"),
    ("TQQQ",  "나스닥 3배 ETF"),
    ("SQQQ",  "나스닥 인버스 3배 ETF"),
    ("SOXS",  "반도체 인버스 3배 ETF"),
    ("SPXL",  "S&P500 3배 ETF"),
    ("SPXS",  "S&P500 인버스 3배 ETF"),
]


def update_kr_stocks() -> pd.DataFrame:
    """KRX에서 KOSPI/KOSDAQ 전종목 다운로드 후 캐시 저장."""
    print("[universe] KRX 종목 데이터 다운로드 중...")

    def _fetch(market_type: str) -> pd.DataFrame:
        url = 'https://kind.krx.co.kr/corpgeneral/corpList.do'
        r = requests.get(url, params={'method': 'download', 'searchType': '13', 'marketType': market_type}, timeout=15)
        df = pd.read_html(io.BytesIO(r.content), encoding='euc-kr')[0]
        return df[['회사명', '종목코드', '시장구분']].rename(columns={'회사명': 'name', '종목코드': 'symbol', '시장구분': 'market'})

    kospi  = _fetch('stockMkt')
    kosdaq = _fetch('kosdaqMkt')
    df = pd.concat([kospi, kosdaq], ignore_index=True)
    df['symbol'] = df['symbol'].astype(str).str.zfill(6)

    os.makedirs(_DATA_DIR, exist_ok=True)
    df.to_csv(_KR_CSV, index=False, encoding='utf-8-sig')
    print(f"[universe] 국내 종목 {len(df)}개 저장 완료 ({_KR_CSV})")
    return df


def _load_kr() -> pd.DataFrame:
    if not os.path.exists(_KR_CSV):
        return update_kr_stocks()
    return pd.read_csv(_KR_CSV, dtype={'symbol': str})


def _us_df() -> pd.DataFrame:
    seen = set()
    rows = []
    for symbol, name in _US_STOCKS:
        if symbol not in seen:
            rows.append({'symbol': symbol, 'name': name, 'market': 'US'})
            seen.add(symbol)
    return pd.DataFrame(rows)


def _looks_like_us_ticker(s: str) -> bool:
    """영문자·점·하이픈으로만 이루어진 1~6자 → 미국 티커 패턴."""
    import re
    return bool(re.fullmatch(r'[A-Za-z][A-Za-z0-9.\-]{0,5}', s))


def search(query: str) -> list[dict]:
    """
    한글 이름, 영문명, 또는 종목코드로 검색.
    목록에 없는 미국 티커 패턴 입력 시 그대로 추가 가능하도록 fallback 반환.
    Returns: [{'symbol': ..., 'name': ..., 'market': ...}, ...]  최대 10건
    """
    query = query.strip()
    if not query:
        return []

    kr  = _load_kr()
    us  = _us_df()
    all_df = pd.concat([kr, us], ignore_index=True)

    # 코드 완전 일치 (우선순위 최고)
    exact = all_df[all_df['symbol'].str.upper() == query.upper()]
    if not exact.empty:
        return exact.to_dict('records')

    # 이름 포함 검색
    matched = all_df[all_df['name'].str.contains(query, case=False, na=False)]
    if not matched.empty:
        return matched.head(10).to_dict('records')

    # 목록에 없는 미국 티커 패턴이면 그대로 반환 (토스 API에서 최종 검증)
    if _looks_like_us_ticker(query):
        symbol = query.upper()
        return [{'symbol': symbol, 'name': symbol, 'market': 'US (미확인)'}]

    return []


def name_to_symbol(name: str) -> str | None:
    """정확히 일치하는 이름의 심볼 반환. 없으면 None."""
    kr  = _load_kr()
    us  = _us_df()
    all_df = pd.concat([kr, us], ignore_index=True)
    row = all_df[all_df['name'] == name]
    if row.empty:
        return None
    return row.iloc[0]['symbol']
