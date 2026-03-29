"""Demo script to exercise the SignalComposer API.

Run the API server first:
    set JWT_SECRET=demo-secret-key && uvicorn src.api.main:app --reload

Then run this script:
    python scripts/demo_api.py
"""

import requests
from solders.keypair import Keypair
from solders.signature import Signature

BASE_URL = "http://127.0.0.1:8000"


def main():
    print("=" * 60)
    print("SignalComposer API Demo")
    print("=" * 60)

    # 1. Health check
    print("\n1. Health Check")
    print("-" * 40)
    resp = requests.get(f"{BASE_URL}/health")
    print(f"   GET /health -> {resp.status_code}")
    print(f"   Response: {resp.json()}")

    # 2. Generate a test wallet
    print("\n2. Generate Test Wallet")
    print("-" * 40)
    keypair = Keypair()
    wallet_address = str(keypair.pubkey())
    print(f"   Wallet: {wallet_address[:20]}...{wallet_address[-8:]}")

    # 3. Request authentication challenge
    print("\n3. Request Auth Challenge")
    print("-" * 40)
    resp = requests.post(
        f"{BASE_URL}/auth/challenge",
        json={"wallet_address": wallet_address},
    )
    print(f"   POST /auth/challenge -> {resp.status_code}")
    challenge = resp.json()["challenge"]
    print(f"   Challenge: {challenge[:40]}...")

    # 4. Sign the challenge and verify
    print("\n4. Sign & Verify Challenge")
    print("-" * 40)
    signature = keypair.sign_message(challenge.encode())
    sig_base58 = str(signature)  # solders uses base58 encoding

    resp = requests.post(
        f"{BASE_URL}/auth/verify",
        json={
            "wallet_address": wallet_address,
            "signature": sig_base58,
            "challenge": challenge,
        },
    )
    print(f"   POST /auth/verify -> {resp.status_code}")
    token = resp.json()["access_token"]
    print(f"   JWT Token: {token[:50]}...")

    # Set up auth headers for subsequent requests
    headers = {"Authorization": f"Bearer {token}"}

    # 5. List strategies (should be empty)
    print("\n5. List Strategies (empty)")
    print("-" * 40)
    resp = requests.get(f"{BASE_URL}/strategies", headers=headers)
    print(f"   GET /strategies -> {resp.status_code}")
    print(f"   Response: {resp.json()}")

    # 6. Create a strategy
    print("\n6. Create Strategy")
    print("-" * 40)
    strategy_dsl = {
        "id": "demo_momentum",
        "name": "Demo Momentum Strategy",
        "version": 1,
        "tokens": ["SOL"],
        "derived_streams": [
            {
                "id": "sol_sma",
                "name": "SOL 20-period SMA",
                "type": "moving_average",
                "token": "SOL",
                "metric": "price",
                "window": "1h",
            }
        ],
        "triggers": [
            {
                "id": "buy_signal",
                "when": {
                    "metric": "price",
                    "token": "SOL",
                    "op": ">",
                    "compare_to": "sol_sma",
                },
                "action": {
                    "type": "buy",
                    "token": "SOL",
                    "amount_pct": 10,
                },
            }
        ],
        "risk_rules": {
            "stop_loss_pct": -5,
            "max_position_pct": 25,
            "max_trades_per_day": 5,
            "slippage_limit_bps": 50,
        },
    }

    resp = requests.post(
        f"{BASE_URL}/strategies",
        json={
            "name": "Demo Momentum",
            "description": "A simple momentum strategy for demonstration",
            "dsl": strategy_dsl,
        },
        headers=headers,
    )
    print(f"   POST /strategies -> {resp.status_code}")
    if resp.status_code != 201:
        print(f"   Error: {resp.json()}")
        return
    strategy = resp.json()
    strategy_id = strategy["id"]
    print(f"   Created strategy ID: {strategy_id}")
    print(f"   External ID: {strategy['external_id']}")
    print(f"   Status: {strategy['status']}")

    # 7. Get the strategy
    print("\n7. Get Strategy Details")
    print("-" * 40)
    resp = requests.get(f"{BASE_URL}/strategies/{strategy_id}", headers=headers)
    print(f"   GET /strategies/{strategy_id} -> {resp.status_code}")
    print(f"   Name: {resp.json()['name']}")
    print(f"   Tokens: {resp.json()['dsl']['tokens']}")

    # 8. Run a backtest with REAL Birdeye data
    print("\n8. Run Backtest (Real Birdeye Data)")
    print("-" * 40)
    resp = requests.post(
        f"{BASE_URL}/strategies/{strategy_id}/backtest",
        json={
            "days": 7,  # 7 days to conserve API credits
            "initial_capital": 10000.0,
            "slippage_bps": 50,
            "use_real_data": True,
        },
        headers=headers,
    )
    print(f"   POST /strategies/{strategy_id}/backtest -> {resp.status_code}")
    if resp.status_code == 200:
        result = resp.json()
        print(f"   Data Source: {result.get('data_source', 'unknown')}")
        print(f"   Total Return: {result['total_return_pct']:.2f}%")
        print(f"   Max Drawdown: {result['max_drawdown_pct']:.2f}%")
        print(f"   Trade Count: {result['trade_count']}")
        print(f"   Sharpe Ratio: {result.get('sharpe_ratio', 'N/A')}")
        print(f"   Win Rate: {result.get('win_rate', 'N/A')}")
        print(f"   Equity Curve Points: {len(result['equity_curve'])}")
    else:
        print(f"   Error: {resp.text}")

    # 9. List strategies again
    print("\n9. List Strategies (with our new one)")
    print("-" * 40)
    resp = requests.get(f"{BASE_URL}/strategies", headers=headers)
    print(f"   GET /strategies -> {resp.status_code}")
    strategies = resp.json()
    print(f"   Found {len(strategies)} strategy(ies)")
    for s in strategies:
        print(f"     - {s['name']} ({s['external_id']})")

    # 10. Delete the strategy
    print("\n10. Delete Strategy")
    print("-" * 40)
    resp = requests.delete(f"{BASE_URL}/strategies/{strategy_id}", headers=headers)
    print(f"   DELETE /strategies/{strategy_id} -> {resp.status_code}")

    # Verify deletion
    resp = requests.get(f"{BASE_URL}/strategies", headers=headers)
    print(f"   Remaining strategies: {len(resp.json())}")

    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)
    print("\nTry the interactive docs at: http://127.0.0.1:8000/docs")


if __name__ == "__main__":
    main()
