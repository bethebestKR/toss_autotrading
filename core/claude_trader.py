"""
Claude AI 매매 판단 모듈.
ThreadPoolExecutor로 비동기 호출 — 폴링 루프를 막지 않는다.

- ask_trade_decision: 10종목 캔들 데이터 → 종목별 BUY/SELL/HOLD
- ask_analyze_trade:  거래 결과 분석 → 전략 규칙 추출
- load_strategy_rules / append_strategy_rule: 자가 학습 전략 파일 관리
"""
import json
import os
import re
from datetime import datetime

STRATEGY_FILE = "data/claude_strategy.md"

_STRATEGY_TEMPLATE = """# Claude 자가 학습 전략 규칙
마지막 업데이트: {date}

## 매수 규칙 (BUY)
(없음 — 거래 결과 분석 후 자동 추가)

## 매도 규칙 (SELL)
(없음)

## 회피 패턴 (AVOID)
(없음)
"""

_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client


# ── 전략 파일 관리 ────────────────────────────────────────────────────────────

def load_strategy_rules() -> str:
    if not os.path.exists(STRATEGY_FILE):
        os.makedirs("data", exist_ok=True)
        with open(STRATEGY_FILE, "w", encoding="utf-8") as f:
            f.write(_STRATEGY_TEMPLATE.format(date=datetime.now().strftime("%Y-%m-%d")))
    with open(STRATEGY_FILE, encoding="utf-8") as f:
        return f.read()


def append_strategy_rule(category: str, rule_text: str):
    """category: 'BUY' | 'SELL' | 'AVOID'. 해당 섹션 아래에 규칙 한 줄 추가."""
    content = load_strategy_rules()

    section_map = {
        "BUY":   "## 매수 규칙 (BUY)",
        "SELL":  "## 매도 규칙 (SELL)",
        "AVOID": "## 회피 패턴 (AVOID)",
    }
    header = section_map.get(category, "## 매수 규칙 (BUY)")

    if header in content:
        content = content.replace(header, f"{header}\n- {rule_text}", 1)
        content = content.replace("(없음 — 거래 결과 분석 후 자동 추가)", "")
        content = content.replace("(없음)", "")

    content = re.sub(
        r"마지막 업데이트: \d{4}-\d{2}-\d{2}",
        f"마지막 업데이트: {datetime.now().strftime('%Y-%m-%d')}",
        content,
    )

    with open(STRATEGY_FILE, "w", encoding="utf-8") as f:
        f.write(content)


# ── 캔들 포맷 ─────────────────────────────────────────────────────────────────

def fmt_candles(symbol: str, candle_data: dict) -> str:
    """캔들 dict → Claude용 텍스트 (최근 30봉). 토스 API 필드: openPrice/highPrice/lowPrice/closePrice."""
    candles = candle_data.get("candles", [])
    if not candles:
        return f"## {symbol}\n(데이터 없음)\n"
    lines = [f"## {symbol}", "시간 | 시가 | 고가 | 저가 | 종가 | 거래량"]
    for c in candles[-30:]:
        ts = str(c.get("timestamp", c.get("time", "")))[:16]
        lines.append(
            f"{ts} | {c.get('openPrice', 0)} | {c.get('highPrice', 0)} | "
            f"{c.get('lowPrice', 0)} | {c.get('closePrice', 0)} | {c.get('volume', 0)}"
        )
    last = candles[-1]
    lines.append(f"현재가(종가): {last.get('closePrice', last.get('close', 0))}")
    return "\n".join(lines)


def fmt_trades(symbol: str, trades: list[dict]) -> str:
    """최근 체결 데이터 → Claude용 텍스트 (거래량 상대값 + 체결 가격 추세).
    토스 API는 방향(매수/매도) 필드 없음 — 거래량 비율과 가격 방향으로 대체."""
    if not trades or len(trades) < 10:
        return f"[{symbol} 체결] 데이터 부족"

    recent_vol = sum(float(t.get("volume", 0)) for t in trades[:10])
    base_count = max(1, len(trades) - 10)
    base_vol   = sum(float(t.get("volume", 0)) for t in trades[10:]) / base_count * 10
    vol_ratio  = recent_vol / base_vol if base_vol > 0 else 1.0
    surge      = "급증" if vol_ratio >= 2.0 else ("증가" if vol_ratio >= 1.3 else "보통")

    prices = [float(t["price"]) for t in trades[:10] if t.get("price")]
    trend_str = "불명"
    if len(prices) >= 2:
        chg = (prices[0] - prices[-1]) / prices[-1] * 100  # 최신이 앞에 있음
        trend_str = f"상승({chg:+.2f}%)" if chg > 0.05 else (f"하락({chg:+.2f}%)" if chg < -0.05 else "횡보")

    return f"[{symbol} 체결] 거래량비율:{vol_ratio:.1f}x({surge}) 체결가추세:{trend_str}"


def fmt_orderbook(symbol: str, ob_data: dict) -> str:
    """호가 dict → Claude용 텍스트 (매수/매도 압력 요약)."""
    bids = ob_data.get("bids", [])
    asks = ob_data.get("asks", [])
    bid_vol = sum(float(b.get("volume", 0)) for b in bids)
    ask_vol = sum(float(a.get("volume", 0)) for a in asks)
    total   = bid_vol + ask_vol
    ratio   = bid_vol / total if total > 0 else 0.5
    pressure = "매수 우세" if ratio > 0.55 else ("매도 우세" if ratio < 0.45 else "중립")
    top_bids = " / ".join(f"{b['price']}({b['volume']})" for b in bids[:3])
    top_asks = " / ".join(f"{a['price']}({a['volume']})" for a in asks[:3])
    return (
        f"[{symbol} 호가] 매수잔량:{bid_vol:,.0f} 매도잔량:{ask_vol:,.0f} "
        f"비율:{ratio:.2f}({pressure})\n"
        f"  매도호가(상위3): {top_asks}\n"
        f"  매수호가(상위3): {top_bids}"
    )


# ── Claude 호출 ───────────────────────────────────────────────────────────────

_DECISION_SYSTEM = """당신은 주식 자동매매 시스템의 AI 트레이더입니다.
여러 종목의 1분봉 OHLCV 데이터, 호가 정보, 체결 정보, 시장 방향을 종합하여 각 종목에 대한 매매 결정을 내립니다.

응답은 반드시 다음 JSON 형식으로만 출력하세요 (다른 텍스트 없이):
{"decisions": [{"symbol": "종목코드", "action": "BUY" | "SELL" | "HOLD", "reason": "한 줄 근거", "confidence": 0.0~1.0, "stop_loss": 손절%(BUY시만), "take_profit": 익절%(BUY시만)}]}

판단 기준:
- BUY: 캔들 추세·거래량 급증·호가 매수 우세가 겹칠 때. 시장 하락 중이면 BUY 보수적으로
- SELL: 보유 종목의 하락 추세 확인 또는 목표가 도달 시
- HOLD: 신호 불분명하거나 호가·시장 방향이 반대일 때
- BUY 시 종목 변동성에 맞게 stop_loss(0.5~5.0%)와 take_profit(1.0~10.0%)을 설정. 변동성 큰 종목은 여유있게, 안정적 종목은 타이트하게.
모든 종목에 대한 결정을 decisions 배열에 포함하세요."""

_ANALYZE_SYSTEM = """당신은 주식 자동매매 시스템의 학습 분석가입니다.
완료된 거래 결과를 분석하여 미래 전략에 반영할 규칙 하나를 추출합니다.

응답은 반드시 다음 JSON 형식으로만 출력하세요 (다른 텍스트 없이):
{"category": "BUY" | "SELL" | "AVOID", "rule": "[규칙ID][신뢰도: 높음|중간|낮음] 규칙 내용. 근거: 이번 거래 요약"}

규칙 ID 형식: B/S/A + 3자리 숫자 (예: B001, S002, A003)
- BUY: 이 패턴에서 매수하면 수익이 남
- SELL: 이 시점에서 매도해야 했음
- AVOID: 이 상황에서 매수를 피해야 함 (손실 패턴)"""


def ask_trade_decision(candles_by_symbol: dict, strategy_rules: str,
                       model: str = "claude-sonnet-4-6",
                       orderbooks_by_symbol: dict = None,
                       market_context: dict = None,
                       trades_by_symbol: dict = None) -> list[dict]:
    """캔들 + 호가 + 체결 + 시장방향 → 각 종목 BUY/SELL/HOLD 결정 리스트."""
    try:
        client = _get_client()
        candle_text = "\n\n".join(
            fmt_candles(sym, data) for sym, data in candles_by_symbol.items()
        )

        ob_text = ""
        if orderbooks_by_symbol:
            ob_lines = [fmt_orderbook(sym, ob) for sym, ob in orderbooks_by_symbol.items()]
            ob_text  = "\n\n## 호가 정보\n" + "\n".join(ob_lines)

        trade_text = ""
        if trades_by_symbol:
            t_lines   = [fmt_trades(sym, t) for sym, t in trades_by_symbol.items()]
            trade_text = "\n\n## 체결 정보 (거래량·가격 추세)\n" + "\n".join(t_lines)

        market_text = ""
        if market_context:
            market_text = "\n\n## 현재 시장 방향\n" + "\n".join(
                f"- {k}: {v}" for k, v in market_context.items()
            )

        prompt = (
            f"현재 보유 전략 규칙:\n{strategy_rules}\n\n---\n"
            f"아래 종목들의 데이터를 분석하여 각 종목의 매매 결정을 내려주세요.\n\n"
            f"{candle_text}"
            f"{ob_text}"
            f"{trade_text}"
            f"{market_text}"
        )
        msg = client.messages.create(
            model=model,
            max_tokens=1000,
            system=[{"type": "text", "text": _DECISION_SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        match = re.search(r'\{[\s\S]+\}', text)
        if not match:
            raise ValueError("JSON 없음")
        return json.loads(match.group()).get("decisions", [])
    except Exception as e:
        print(f"[Claude] ask_trade_decision 오류: {e}")
        return []


def ask_analyze_trade(symbol: str, buy_price: float, sell_price: float,
                      pnl_pct: float, exit_reason: str, candle_snapshot: str,
                      strategy_rules: str, model: str = "claude-sonnet-4-6") -> tuple[str, str] | None:
    """거래 결과 분석 → (category, rule_text) 반환. 실패 시 None."""
    try:
        client = _get_client()
        result_str = f"{'수익' if pnl_pct >= 0 else '손실'} {pnl_pct:+.2f}%"
        prompt = (
            f"완료된 거래 분석:\n"
            f"종목: {symbol}\n"
            f"매수가: {buy_price:,.2f} → 매도가: {sell_price:,.2f} ({result_str})\n"
            f"매도 이유: {exit_reason}\n\n"
            f"매수 시점 캔들 데이터:\n{candle_snapshot}\n\n"
            f"현재 전략 규칙:\n{strategy_rules}\n\n"
            f"이 거래에서 학습할 수 있는 규칙 하나를 추출해주세요."
        )
        msg = client.messages.create(
            model=model,
            max_tokens=300,
            system=[{"type": "text", "text": _ANALYZE_SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        match = re.search(r'\{[\s\S]+?\}', text)
        if not match:
            raise ValueError("JSON 없음")
        data = json.loads(match.group())
        category = data.get("category", "AVOID")
        rule = data.get("rule", "").strip()
        return (category, rule) if rule else None
    except Exception as e:
        print(f"[Claude] ask_analyze_trade 오류: {e}")
        return None
