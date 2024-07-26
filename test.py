import yfinance as yf

symbol = "RELIANCE.BO"

try:
    stock = yf.Ticker(symbol)
    data = stock.history(period="1d")
    
    if data.empty:
        print(f"No price data found for {symbol}")
    else:
        current_price = data['Close'].iloc[0]
        print(f"The current price of {symbol} is ₹{current_price}")

except Exception as e:
    print(f"Unexpected error: {str(e)}")
