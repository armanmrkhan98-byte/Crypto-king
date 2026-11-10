import time
import pandas as pd
import numpy as np
import talib
from pybit.unified_trading import HTTP

class BybitAutoBot:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        """
        Initializes the Bybit V5 REST Client.
        Set testnet=True when testing on Bybit Testnet.
        """
        self.session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret,
        )
        self.category = "linear"  # Linear USDT Perpetual Contracts

    def get_klines(self, symbol: str, interval: str = "1", limit: int = 100) -> pd.DataFrame:
        """Fetch historical Kline (candle) data from Bybit."""
        response = self.session.get_kline(
            category=self.category,
            symbol=symbol,
            interval=interval,
            limit=limit,
        )
        data = response["result"]["list"]
        
        # Bybit returns newest first, reverse to oldest first
        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df = df.iloc[::-1].reset_index(drop=True)
        
        # Convert numeric columns
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
            
        return df

    def check_open_positions(self, symbol: str) -> bool:
        """Checks if there is already an active position for the symbol."""
        res = self.session.get_positions(category=self.category, symbol=symbol)
        positions = res["result"]["list"]
        for pos in positions:
            if float(pos.get("size", 0)) > 0:
                return True
        return False

    def place_order_with_sl_tp(
        self,
        symbol: str,
        side: str,  # "Buy" or "Sell"
        qty: float,
        take_profit: float,
        stop_loss: float
    ):
        """Executes a Market Order with Take-Profit and Stop-Loss attached."""
        try:
            order = self.session.place_order(
                category=self.category,
                symbol=symbol,
                side=side,
                orderType="Market",
                qty=str(qty),
                takeProfit=str(round(take_profit, 4)),
                stopLoss=str(round(stop_loss, 4)),
                tpTriggerBy="LastPrice",
                slTriggerBy="LastPrice",
                tpslMode="Full",  # Entire position managed by TP/SL
                timeInForce="GTC",
            )
            print(f"[{side.upper()} ORDER PLACED] Symbol: {symbol} | Qty: {qty} | TP: {take_profit} | SL: {stop_loss}")
            return order
        except Exception as e:
            print(f"Error placing order: {e}")
            return None

    def generate_signal(self, df: pd.DataFrame):
        """
        Example Technical Analysis Strategy:
        - EMA 9 / EMA 21 Crossover + RSI (14) filter
        """
        close = df["close"].values
        ema_fast = talib.EMA(close, timeperiod=9)
        ema_slow = talib.EMA(close, timeperiod=21)
        rsi = talib.RSI(close, timeperiod=14)

        current_close = close[-1]
        
        # Signal conditions
        buy_cond = (ema_fast[-2] <= ema_slow[-2]) and (ema_fast[-1] > ema_slow[-1]) and (rsi[-1] > 45)
        sell_cond = (ema_fast[-2] >= ema_slow[-2]) and (ema_fast[-1] < ema_slow[-1]) and (rsi[-1] < 55)

        if buy_cond:
            return "Buy", current_close
        elif sell_cond:
            return "Sell", current_close
        
        return None, current_close

    def run(self, symbol: str, qty: float, sl_pct: float = 0.01, tp_pct: float = 0.02, interval_sec: int = 15):
        """Main Bot Execution Loop."""
        print(f"Starting bot monitoring on {symbol}...")
        
        while True:
            try:
                # 1. Skip if a position is already open
                if self.check_open_positions(symbol):
                    print(f"Active position exists for {symbol}. Waiting...")
                    time.sleep(interval_sec)
                    continue

                # 2. Fetch candle data and evaluate strategy
                df = self.get_klines(symbol, interval="1", limit=50)
                signal, last_price = self.generate_signal(df)

                # 3. Handle Trade Signals
                if signal == "Buy":
                    tp = last_price * (1 + tp_pct)
                    sl = last_price * (1 - sl_pct)
                    self.place_order_with_sl_tp(symbol, "Buy", qty, take_profit=tp, stop_loss=sl)

                elif signal == "Sell":
                    tp = last_price * (1 - tp_pct)
                    sl = last_price * (1 + sl_pct)
                    self.place_order_with_sl_tp(symbol, "Sell", qty, take_profit=tp, stop_loss=sl)
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] Monitoring {symbol}... No signal. Price: {last_price}")

            except Exception as e:
                print(f"Loop error: {e}")

            time.sleep(interval_sec)


# --- Execution Configuration ---
if __name__ == "__main__":
    API_KEY = "YOUR_BYBIT_API_KEY"
    API_SECRET = "YOUR_BYBIT_API_SECRET"
    
    # Initialize Bot (Set testnet=True for testing on Bybit Testnet first)
    bot = BybitAutoBot(api_key=API_KEY, api_secret=API_SECRET, testnet=True)
    
    # Run bot on BTCUSDT with 0.001 BTC order size, 1% SL, 2% TP
    bot.run(
        symbol="BTCUSDT",
        qty=0.001,
        sl_pct=0.01,   # 1% Stop-Loss
        tp_pct=0.02,   # 2% Take-Profit
        interval_sec=10
    )
