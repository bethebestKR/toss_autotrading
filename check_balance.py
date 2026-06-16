import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from core.toss_client import TossClient

client = TossClient()

# 계좌 목록
print("=== 계좌 정보 ===")
accounts = client.get_accounts()
for acc in accounts:
    print(f"  계좌번호: {acc.get('accountNo', '')}")
    print(f"  계좌Seq : {acc.get('accountSeq', '')}")
    print(f"  계좌유형: {acc.get('accountType', '')}")
print()

# 매수 가능 금액
print("=== 매수 가능 금액 (예수금) ===")
bp_krw = client.get_buying_power(currency="KRW")
bp_usd = client.get_buying_power(currency="USD")
print(f"  KRW: {int(bp_krw.get('cashBuyingPower', 0)):,} 원")
print(f"  USD: $ {float(bp_usd.get('cashBuyingPower', 0)):,.2f}")
print()

# 보유 주식 및 자산 요약
print("=== 보유 자산 요약 ===")
h = client.get_holdings()
total_purchase = int(h["totalPurchaseAmount"]["krw"] or 0)
market_value   = int(h["marketValue"]["amount"]["krw"] or 0)
pl_amount      = int(h["profitLoss"]["amount"]["krw"] or 0)
pl_rate        = float(h["profitLoss"]["rate"] or 0)
daily_pl       = int(h["dailyProfitLoss"]["amount"]["krw"] or 0)
daily_rate     = float(h["dailyProfitLoss"]["rate"] or 0)

print(f"  매입금액   : {total_purchase:,} 원")
print(f"  평가금액   : {market_value:,} 원")
print(f"  평가손익   : {pl_amount:+,} 원  ({pl_rate:+.2f}%)")
print(f"  일일손익   : {daily_pl:+,} 원  ({daily_rate:+.2f}%)")
print(f"  총자산(추정): {market_value + int(bp_krw.get('cashBuyingPower', 0)):,} 원")
print()

# 보유 종목 상세
print("=== 보유 종목 ===")
items = h.get("items", [])
if not items:
    print("  보유 종목 없음")
else:
    for item in items:
        symbol  = item.get("symbol", "")
        name    = item.get("name", "")
        qty     = int(item.get("quantity", 0))
        avg     = float(item.get("averagePrice", 0))
        cur     = float(item.get("currentPrice", 0))
        pl_r    = float(item.get("profitLossRate", 0))
        pl_a    = float(item.get("profitLossAmount", 0))
        print(f"  [{symbol}] {name}")
        print(f"    수량: {qty}주  평균단가: {avg:,.0f}  현재가: {cur:,.0f}")
        print(f"    손익: {pl_a:+,.0f} 원  ({pl_r:+.2f}%)")
