import os
import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes,MessageHandler,ConversationHandler ,filters
from dotenv import load_dotenv
import sqlite3
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import yfinance as yf
import re
import textwrap
import pyshorteners
import random
import time
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error
from langchain.prompts import PromptTemplate
from langchain.llms import CTransformers
import logging

# Connect to database
conn = sqlite3.connect('users.db')
cursor = conn.cursor()

# Create table if it doesn't exist
conn.execute('''
             CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                email TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                is_verified INTEGER DEFAULT 0,
                is_logged_in INTEGER DEFAULT 0
             )        
''')
# conn.execute('''
#              ALTER TABLE users ADD COLUMN is_logged_in INTEGER DEFAULT 0
# ''')

conn.commit()

# Hash password
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Load token from .env file
load_dotenv()
TOKEN = os.getenv("TOKEN")

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Define command functions
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("""
Hii!! Welcome to DeFiSensei. 
Thank you for choosing this bot.
Let's get you registered to experience all 
features of the bot.
Type /register to start registration process.
Type /help to view available commands.
PS: info...
                                    """)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        """
Available commands with their usage:

Enter the commands without <>

To interact with AI Finance assistant ChatBot simply type the prompt without any slash or command.... 

/start - Welcome message
/help - List available commands
/coin <coin name> - Know the current price of a coin. Eg: /price bitcoin
/market - Get live market updates including top stocks worldwide, top stocks in India, and forex prices.
/register <username> <password> <email> - Register a new account
/login <username> <password> - Login to your account
/logout - Logout from your account
/delete <username> <password> <email> - Delete your account
/forex <from> <to> - Get live price for a specific forex
/stock <stock symbol (i.e., stockname.BO For Indian stock or stocksymbol for global)> - Get live price for a specific stock
/budget_highlights - Highlights for 2024 India Budget
/finance_news - Get the latest finance news
/recover_username <email> - Recover your username using your email
/reset_password <email> <new_password> - Reset your account password
/predict <stock symbol (i.e., stockname.BO For Indian stock or stocksymbol for global)> - Predict investment return using AI
/search <stockname> - Search for stocks and financial information Eg: /search infosys
        """
    )


async def coin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.message.from_user.id
    cursor.execute('SELECT is_logged_in FROM users WHERE telegram_id = ?', (telegram_id,))
    result = cursor.fetchone()
    
    if result and result[0] == 1:
        if context.args:
            coin = context.args[0].lower()
            response = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=inr")
            if response.status_code == 200:
                data = response.json()
                if coin in data:
                    price = data[coin]['inr']
                    await update.message.reply_text(f"The current price of {coin} is ₹{price}")
                else:
                    await update.message.reply_text(f"Coin '{coin}' not found.")
            else:
                await update.message.reply_text("Failed to fetch price data.")
        else:
            await update.message.reply_text("Usage: /coin <coin name>")
    else:
        await update.message.reply_text("You need to be logged in to use this command. Please log in using /login.")

# Register
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 3:
        await update.message.reply_text("Usage: /register <username> <password> <email>")
        return
    username = context.args[0]
    password = context.args[1]
    email = context.args[2]
    password_hash = hash_password(password)

    telegram_id = update.message.from_user.id

    try:
        cursor.execute('INSERT INTO users (telegram_id, username, email, password_hash) VALUES (?, ?, ?, ?)', (telegram_id, username, email, password_hash))
        conn.commit()
        
        # Send confirmation email
        email_sent = send_mail(email)
        
        if email_sent:
            await update.message.reply_text(""" 
                            Registration successful!!
                            Please check your email for confirmation.  
                              """)
        else:
            await update.message.reply_text("Failed to send confirmation email. Please check the email address and try again.")
    except sqlite3.IntegrityError:
        await update.message.reply_text("This user already exists. Please try logging in.")

# Login
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 2:
        await update.message.reply_text('Usage: /login <username> <password>')
        return

    username = context.args[0]
    password = context.args[1]
    password_hash = hash_password(password)
    telegram_id = update.message.from_user.id

    cursor.execute('SELECT email, is_verified FROM users WHERE telegram_id = ? AND username = ? AND password_hash = ?', (telegram_id, username, password_hash))
    user = cursor.fetchone()

    if user:
        email, is_verified = user
        if is_verified:
            cursor.execute('UPDATE users SET is_logged_in = 1 WHERE telegram_id = ?', (telegram_id,))
            conn.commit()
            await update.message.reply_text('Login successful!')
        else:
            await update.message.reply_text('Please verify your OTP to complete the login process.')
            # Generate and send OTP
            otp = generate_otp()
            store_otp(email, otp)
            otp_sent = send_otp_email(email, otp)
            if otp_sent:
                await update.message.reply_text('An OTP has been sent to your email. Please verify to complete the login process by using /verify_otp.')
            else:
                await update.message.reply_text('Failed to send OTP. Please try again later.')
    else:
        await update.message.reply_text('Invalid username or password')

# Logout
async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.message.from_user.id
    cursor.execute('UPDATE users SET is_logged_in = 0 WHERE telegram_id = ?', (telegram_id,))
    conn.commit()
    await update.message.reply_text('Logout successful!')

def is_user_logged_in(telegram_id):
    cursor.execute('SELECT is_logged_in FROM users WHERE telegram_id = ?', (telegram_id,))
    result = cursor.fetchone()
    return result and result[0] == 1

# Delete account
async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 3:
        await update.message.reply_text('Usage: /delete <username> <password> <email>')
        return

    username = context.args[0]
    password = context.args[1]
    email = context.args[2]
    password_hash = hash_password(password)
    telegram_id = update.message.from_user.id

    try:
        # Verify user credentials
        cursor.execute('SELECT * FROM users WHERE telegram_id = ? AND username = ? AND email = ? AND password_hash = ?', (telegram_id, username, email, password_hash))
        user = cursor.fetchone()

        if user:
            # Delete user record based on all provided credentials
            cursor.execute('DELETE FROM users WHERE telegram_id = ? AND username = ? AND email = ? AND password_hash = ?', (telegram_id, username, email, password_hash))
            conn.commit()
            
            # Send confirmation email
            email_sent = send_delete_mail(username, email)  # Ensure send_delete_mail sends the correct email
            
            if email_sent:
                await update.message.reply_text('Your account has been successfully deleted. A confirmation email has been sent.')
            else:
                await update.message.reply_text('Failed to send confirmation email. Please try again later. You may recieve it shortly.')
        else:
            await update.message.reply_text('Invalid credentials. Please check your username, password, and email.')

    except sqlite3.Error as e:
        await update.message.reply_text(f'An error occurred: {e}')

# Send Delete email
def send_delete_mail(username: str, email: str) -> bool:
    try:
        # Email server configuration
        smtp_server = 'smtp.example.com'
        smtp_port = 587
        smtp_username = 'your_email@example.com'
        smtp_password = 'your_email_password'

        # Create the email content
        msg = MIMEMultipart()
        msg['From'] = smtp_username
        msg['To'] = email
        msg['Subject'] = 'Account Deletion Confirmation'

        body = f'Dear {username},\n\nYour account has been successfully deleted.\n\nBest regards,\nYour Team'
        msg.attach(MIMEText(body, 'plain'))

        # Send the email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(smtp_username, email, msg.as_string())

        return True

    except Exception as e:
        print(f'Error sending email: {e}')
        return False

# Send email
def send_mail(email):
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    smtp_server = "smtp-mail.outlook.com"
    smtp_port = 587

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = email
    msg['Subject'] = "Registration Confirmation"

    body = "You have successfully registered for DeFiSensei. Thank you!"
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        text = msg.as_string()
        server.sendmail(sender_email, email, text)
        server.quit()
        print("Email sent successfully!")
        return True
    except Exception as e:
        print(f"Failed to send email. Error: {str(e)}")
        return False

# Top stocks worlwide
def get_top_stocks_worldwide():
    try:
        # Example symbols for top worldwide stocks
        symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
        stocks = []
        for symbol in symbols:
            stock = yf.Ticker(symbol)
            data = stock.history(period="1d")
            if data.empty:
                logging.error(f"No price data found for {symbol}")
                continue
            current_price = data['Close'].iloc[0]
            stocks.append({'name': symbol, 'current_price': current_price})
        return stocks
    except Exception as e:
        logging.error(f"Unexpected error in get_top_stocks_worldwide: {str(e)}")
        return []

# Top stocks India
def get_top_stocks_india():
    try:
        # symbols for top Indian stocks
        symbols = ["RELIANCE.BO", "TCS.BO", "INFY.BO", "HDFCBANK.BO", "HINDUNILVR.BO"]
        stocks = []
        for symbol in symbols:
            stock = yf.Ticker(symbol)
            data = stock.history(period="1d")
            if data.empty:
                logging.error(f"No price data found for {symbol}")
                continue
            current_price = data['Close'].iloc[0]
            stocks.append({'name': symbol, 'current_price': current_price})
        return stocks
    except Exception as e:
        logging.error(f"Unexpected error in get_top_stocks_india: {str(e)}")
        return []
# Specific Stock
async def stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.message.from_user.id
    cursor.execute('SELECT is_logged_in FROM users WHERE telegram_id = ?', (telegram_id,))
    result = cursor.fetchone()

    if result and result[0] == 1:
        if len(context.args) != 1:
            await update.message.reply_text('Usage: /stock <stock symbol (i.e., stockname.BO For Indian stock or stocksymbol for global)>')
            return

        symbol = context.args[0]

        try:
            stock = yf.Ticker(symbol)
            data = stock.history(period="1d")
        
            if data.empty:
                await update.message.reply_text(f"No price data found for {symbol}")
                return
        
            current_price = data['Close'].iloc[0]
            await update.message.reply_text(f"The current price of {symbol} is ₹{current_price}")

        except Exception as e:
            logging.error(f"Unexpected error in stock function: {str(e)}")
            await update.message.reply_text(f"Unexpected error in stock function: {str(e)}")
    else:
        await update.message.reply_text("You need to be logged in to use this command. Please log in using /login.")
# Realtime Forex
def get_forex_prices():
    try:
        api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
        base_url = "https://www.alphavantage.co/query"
        forex_pairs = {"USD/INR": None, "EUR/INR": None, "GBP/INR": None}
        
        for pair in forex_pairs:
            from_currency, to_currency = pair.split('/')
            params = {
                "function": "CURRENCY_EXCHANGE_RATE",
                "from_currency": from_currency,
                "to_currency": to_currency,
                "apikey": api_key
            }
            response = requests.get(base_url, params=params)
            if response.status_code == 200:
                data = response.json()
                if "Realtime Currency Exchange Rate" in data:
                    rate = data["Realtime Currency Exchange Rate"]["5. Exchange Rate"]
                    forex_pairs[pair] = float(rate)
                else:
                    logging.error(f"No data available for {pair}")
            else:
                logging.error(f"Failed to fetch data for {pair}: {response.status_code}")

        return forex_pairs
    except Exception as e:
        logging.error(f"Unexpected error in get_forex_prices: {str(e)}")
        return {}
# Specific forex 
async def forex(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.message.from_user.id
    cursor.execute('SELECT is_logged_in FROM users WHERE telegram_id = ?', (telegram_id,))
    result = cursor.fetchone()
    
    if result and result[0] == 1:
        if len(context.args) != 2:
            await update.message.reply_text('Usage: /forex <from> <to>')
        else:
            pair_from = context.args[0]
            pair_to = context.args[1]
            try:
                api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
                base_url = "https://www.alphavantage.co/query"
                params = {
                    "function": "CURRENCY_EXCHANGE_RATE",
                    "from_currency": pair_from,
                    "to_currency": pair_to,
                    "apikey": api_key
                }
                response = requests.get(base_url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    if "Realtime Currency Exchange Rate" in data:
                        rate = data["Realtime Currency Exchange Rate"]["5. Exchange Rate"]
                        await update.message.reply_text(f"The current exchange rate from {pair_from} to {pair_to} is ₹{rate}")
                    else:
                        await update.message.reply_text(f"No data available for the currency pair {pair_from}/{pair_to}.")
                else:
                    await update.message.reply_text(f"Failed to fetch data for the currency pair {pair_from}/{pair_to}.")
            except Exception as e:
                logging.error(f"Unexpected error in forex function: {str(e)}")
                await update.message.reply_text("An unexpected error occurred. Please try again later.")
    else:
        await update.message.reply_text("You need to be logged in to use this command. Please log in using /login.")

# Market Updates
async def market(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.message.from_user.id
    cursor.execute('SELECT is_logged_in FROM users WHERE telegram_id = ?', (telegram_id,))
    result = cursor.fetchone()
    
    if result and result[0] == 1:
        message = "Live Market Updates:\n\n"

        try:
        # Fetch market data
            stocks_worldwide = get_top_stocks_worldwide()
            stocks_india = get_top_stocks_india()
            forex_prices = get_forex_prices()

            if not stocks_worldwide:
                message += "No data available for top worldwide stocks.\n\n"
            else:
                # Top 10 stocks worldwide
                message += "Top Stocks Worldwide:\n"
                for stock in stocks_worldwide:
                    message += f"{stock['name']}: ₹{stock['current_price']}\n"

            if not stocks_india:
                message += "No data available for top Indian stocks.\n\n"
            else:
            # Top 10 stocks in India
                message += "\nTop Stocks in India:\n"
                for stock in stocks_india:
                    message += f"{stock['name']}: ₹{stock['current_price']}\n"

            if not forex_prices:
                message += "No data available for forex prices.\n\n"
            else:
            # Forex Prices
                message += "\nForex Prices:\n"
                for pair, price in forex_prices.items():
                    message += f"{pair}: ₹{price}\n"

        except Exception as e:
            message = "An unexpected error occurred. Please try again later."
            logging.error(f"Unexpected error in market function: {str(e)}")

        await update.message.reply_text(message)
    else:
        await update.message.reply_text("You need to be logged in to use this command. Please log in using /login.")


# Highlights 2024
BUDGET_HIGHLIGHTS = [
    "*Income Tax:* There are no changes in the income tax slabs or rates. The new regime tax slabs remain as follows: no tax up to ₹3 lakh, 5% for income between ₹3-6 lakh, 10% for ₹6-9 lakh, 15% for ₹9-12 lakh, and 20% for ₹12-15 lakh. Income above ₹15 lakh is taxed at 30%.",
    "*Fiscal Deficit:* The fiscal deficit target for FY25 is set at 5.1% of GDP. This is part of a continued effort to reduce the fiscal deficit to 4.5% by FY26.",
    "*Economic Growth:* The budget continues to focus on macroeconomic stability and growth, with increased investments in infrastructure, agriculture, and domestic tourism.",
    "*Capital Expenditure:* Capital expenditure is increased by 11.1% to ₹11.11 lakh crore, which is 3.4% of GDP. This includes significant allocations for infrastructure projects.",
    "*Railways:* 40,000 normal rail bogies will be converted to Vande Bharat to enhance passenger safety and comfort. Three major railway corridors have also been announced.",
    "*Women's Empowerment:* The 'Lakhpati Didi' scheme aims to empower women in rural areas, with the target increased from 2 crore to 3 crore women benefiting from the program.",
    "*Defense:* The budget includes a significant allocation for defense to ensure national security and modernization of the armed forces.",
    "*Customs Duty:* No changes have been made to the customs duties, maintaining the status quo to provide stability for businesses.",
    "*Digital Infrastructure:* Continued investment in digital infrastructure is emphasized, with a focus on Global Capability Centres (GCCs) and digital transformation.",
    "*Green Energy:* Support for green energy initiatives continues, with significant investments in renewable energy projects.",
    "*Healthcare:* The budget allocates funds for the improvement of healthcare infrastructure and services, aiming to make healthcare more accessible and affordable.",
    "*Education:* Increased funding for educational initiatives, including skill development and vocational training programs.",
    "*Stock Market:* The budget is expected to positively impact the stock market with its focus on fiscal discipline and growth-oriented measures.",
    "*Middle Class:* Despite no changes in tax rates, the budget includes measures to simplify tax laws and improve compliance, which could benefit the middle class by making tax filing easier.",
    "*Lower Class:* Programs aimed at poverty alleviation and social welfare continue to receive funding, ensuring support for the lower class.",
    "*Upper Middle Class:* Initiatives to boost housing, infrastructure, and digital services benefit the upper middle class by improving the overall quality of life and economic opportunities.",
    "*Agriculture:* Significant investment in the agriculture sector, including subsidies and support for farmers to boost productivity and income.",
    "*Tourism:* Increased funding for domestic tourism to promote cultural heritage and boost local economies.",
    "*Government Expenditure:* The budget maintains a focus on prudent government expenditure to ensure long-term economic stability.",
    "*Economic Corridors:* Development of commodity-specific economic rail corridors to reduce logistics costs and improve competitiveness in manufacturing."
]

# Define the command handler for budget highlights
async def budget_highlights(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    highlights = "\n\n".join(BUDGET_HIGHLIGHTS)
    await update.message.reply_text(f"Here are the highlights of the 2024 India Budget:\n\n{highlights}", parse_mode="Markdown")


# Get API keys from environment variables
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
NEWS_API_URL = "https://newsapi.org/v2/top-headlines"
def escape_markdown_v2(text):
    """Escape characters reserved in MarkdownV2."""
    if text is None:
        return ""
    escape_chars = r'[_*\[\]()~`>#+-=|{}.!]'
    return re.sub(escape_chars, r'\\\g<0>', text)

async def send_message_in_chunks(bot, chat_id, text, parse_mode="MarkdownV2"):
    """Send a message in chunks to handle length limits."""
    chunk_size = 4096  # Maximum length for a single message
    chunks = textwrap.wrap(text, chunk_size)
    for chunk in chunks:
        await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=parse_mode)
# Initialize the URL shortener (using TinyURL in this example)
s = pyshorteners.Shortener()


async def finance_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.message.from_user.id
    cursor.execute('SELECT is_logged_in FROM users WHERE telegram_id = ?', (telegram_id,))
    result = cursor.fetchone()
    
    if result and result[0] == 1:
    # Fetch top finance news
        params = {
            'category': 'business',
            'country': 'in',
            'apiKey': NEWS_API_KEY
        }
        response = requests.get(NEWS_API_URL, params=params)
        data = response.json()

        if data.get('status') == 'ok':
            articles = data.get('articles', [])
            if articles:
            # Create a list of formatted news articles
                news_list = []
                for article in articles:
                    title = escape_markdown_v2(article.get('title', 'No Title'))
                    description = escape_markdown_v2(article.get('description', 'No Description'))
                    url = s.tinyurl.short(article.get('url', 'No URL'))
                
                # Format article with heading, subheading, and body
                    formatted_article = (
                        f"**{title}**\n"
                        f"*{description}*\n"  # Added a newline here for spacing
                        f"[Read more]({url})\n"  # Ensuring new line after "Read more" link
                    )
                    news_list.append(formatted_article)
            
            # Send each news article as a separate message
                for article in news_list:
                    await context.bot.send_message(chat_id=update.message.chat_id, text=article, parse_mode="MarkdownV2")
            else:
                await update.message.reply_text("No news articles found.")
        else:
            await update.message.reply_text("Failed to fetch news. Please try again later.")
    else:
        await update.message.reply_text("You need to be logged in to use this command. Please log in using /login.")

# Store OTPs in-memory or in the database (with expiry time)
otp_storage = {}

# Generate OTP
def generate_otp():
    return random.randint(100000, 999999)

# Send OTP Email
def send_otp_email(email, otp):
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    smtp_server = "smtp-mail.outlook.com"
    smtp_port = 587

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = email
    msg['Subject'] = "Your OTP Code"

    body = f"Your OTP code is {otp}. It is valid for 5 minutes."
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        logging.error(f"Failed to send OTP email. Error: {str(e)}")
        return False

# Store OTP with expiry time (e.g., 5 minutes)
def store_otp(email, otp):
    otp_storage[email] = {'otp': otp, 'expiry': time.time() + 300}  # 300 seconds = 5 minutes

# Verify OTP
def verify_otp(email, otp):
    stored = otp_storage.get(email)
    if not stored:
        return False
    if time.time() > stored['expiry']:
        return False
    return stored['otp'] == otp


async def request_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 1:
        await update.message.reply_text('Usage: /request_otp <email>')
        return

    email = context.args[0]

    # Generate OTP and send email
    otp = generate_otp()
    if send_otp_email(email, otp):
        store_otp(email, otp)
        await update.message.reply_text('An OTP has been sent to your email. Please use /verify_otp to verify it.')
    else:
        await update.message.reply_text('Failed to send OTP. Please try again later.')


async def verify_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 2:
        await update.message.reply_text('Usage: /verify_otp <email> <otp>')
        return

    email = context.args[0]
    otp = context.args[1]

    if verify_otp(email, otp):
        await update.message.reply_text('OTP verified successfully. You can now use /recover_username or /reset_password.')

        telegram_id = update.message.from_user.id
        
        try:
            # Connect to the database
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()

            # Update the user's status
            cursor.execute('UPDATE users SET is_logged_in = 1 WHERE telegram_id = ?', (telegram_id,))
            conn.commit()

        except sqlite3.Error as e:
            await update.message.reply_text(f'An error occurred while updating the database: {e}')
        
        finally:
            # Close the connection
            conn.close()

    else:
        await update.message.reply_text('Invalid or expired OTP. Please try again.')

async def recover_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 1:
        await update.message.reply_text('Usage: /recover_username <email>')
        return
    
    email = context.args[0]

    try:
        # Connect to the database
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()

        # Check if the user is logged in
        cursor.execute('SELECT is_logged_in FROM users WHERE email = ?', (email,))
        log = cursor.fetchone()

        if log and log[0] == 1:
            # If logged in, retrieve the username
            cursor.execute('SELECT username FROM users WHERE email = ?', (email,))
            user = cursor.fetchone()

            if user:
                username = user[0]
                await update.message.reply_text(f'Your username is {username}.')
            else:
                await update.message.reply_text('No account found with this email.')
        else:
            await update.message.reply_text('Please verify your email by using /request_otp.')

    except sqlite3.Error as e:
        await update.message.reply_text(f'An error occurred while accessing the database: {e}')
    
    finally:
        # Ensure the database connection is closed
        conn.close()

async def reset_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 2:
        await update.message.reply_text('Usage: /reset_password <email> <new_password>')
        return
    
    email = context.args[0]
    new_password = context.args[1]
    new_password_hash = hash_password(new_password)

    try:
        # Connect to the database
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()

        # Check if the user is logged in
        cursor.execute('SELECT is_logged_in FROM users WHERE email = ?', (email,))
        log = cursor.fetchone()

        if log and log[0] == 1:
            # Update the password
            cursor.execute('UPDATE users SET password_hash = ? WHERE email = ?', (new_password_hash, email))
            conn.commit()
            await update.message.reply_text('Your password has been reset successfully.')
        else:
            await update.message.reply_text('Please verify your email by using /request_otp.')

    except sqlite3.Error as e:
        await update.message.reply_text(f'An error occurred while accessing the database: {e}')
    
    finally:
        # Ensure the database connection is closed
        conn.close()


# Download and preprocess data
def download_and_preprocess_data(ticker):
    stock_data = yf.download(ticker, start='2020-01-01', end='2023-01-01')
    stock_data.fillna(method='ffill', inplace=True)
    stock_data['Return'] = stock_data['Close'].pct_change()
    stock_data.dropna(inplace=True)
    features = stock_data[['Open', 'High', 'Low', 'Close', 'Volume']].values
    labels = stock_data['Return'].values
    return features, labels

# Train model
def train_model(features, labels):
    X_train, X_test, y_train, y_test = train_test_split(features, labels, test_size=0.2, random_state=42)
    model = LinearRegression()
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)
    mse = mean_squared_error(y_test, predictions)
    print(f'Mean Squared Error: {mse}')
    return model

# Predict return
def predict_return(model, open_price, high_price, low_price, close_price, volume):
    input_features = np.array([[open_price, high_price, low_price, close_price, volume]])
    predicted_return = model.predict(input_features)
    return predicted_return[0]

# Function to get the latest stock prices (example function, to be implemented)
def get_latest_stock_prices(ticker):
    stock_data = yf.download(ticker, period='1d')
    latest_prices = stock_data.iloc[-1][['Open', 'High', 'Low', 'Close', 'Volume']].values
    return latest_prices
async def predict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 1:
        await update.message.reply_text('Usage: /predict <stock symbol (i.e., stockname.BO For Indian stock or stocksymbol for global)>')
        return

    ticker = context.args[0].upper()
    latest_prices = get_latest_stock_prices(ticker)
    predicted_return = predict_return(model, *latest_prices)
    await update.message.reply_text(f'The predicted return for {ticker} is {predicted_return:.2%}')
df = pd.read_csv('stocks.csv')
# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Function to get stock details from yfinance
def get_stock_details(symbol: str):
    try:
        stock = yf.Ticker(symbol)
        info = stock.info
        return {
            'Name': info.get('longName', 'N/A'),
            'Symbol': info.get('symbol', 'N/A'),
            'Exchange': info.get('exchange', 'N/A'),
            'Current Price': info.get('currentPrice', 'N/A'),
            'Market Cap': info.get('marketCap', 'N/A'),
            'PE Ratio': info.get('trailingPE', 'N/A'),
            '52 Week High': info.get('fiftyTwoWeekHigh', 'N/A'),
            '52 Week Low': info.get('fiftyTwoWeekLow', 'N/A'),
            'Dividend Yield': info.get('dividendYield', 'N/A'),
            'Description': info.get('description', 'N/A')
        }
    except Exception as e:
        logger.error(f"Error fetching stock details: {e}")
        return {}

# Function to handle the /search command
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        name = ' '.join(context.args).lower()
        result = df[df['name'].str.lower().str.contains(name)]
        if not result.empty:
            stocks = []
            for _, stock_info in result.iterrows():
                details = get_stock_details(stock_info['symbol'])
                stock_details = '\n'.join([f"{key}: {value}" for key, value in details.items()])
                stocks.append(stock_details)
            message = "\n\n".join(stocks)
        else:
            message = "Stock not found by that name."
    else:
        message = "Please provide a stock name after the command."
    await update.message.reply_text(message)




# Llama Model
# Initialize the LLaMA 2 model globally
llm = CTransformers(model='models/llama-2-7b-chat.ggmlv3.q8_0.bin',
                    model_type='llama',
                    config={'max_new_tokens': 256,
                            'temperature': 0.01})

# Function to get response from LLaMA 2 model
def getLLamaresponse(input_text, blog_style='Common People'):
    # Prompt Template
    template = """
    Write a response in the style of a {blog_style} for the topic "{input_text}".
    """
    
    prompt = PromptTemplate(input_variables=["blog_style", "input_text"],
                            template=template)
    
    # Generate the response from the LLaMA 2 model
    response = llm(prompt.format(blog_style=blog_style, input_text=input_text))
    return response
# Message handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_message = update.message.text
    user_id = update.message.from_user.id
    telegram_id = update.message.from_user.id
    try:
        # Connect to the database
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()

        # Check if the user is logged in
        cursor.execute('SELECT is_logged_in FROM users WHERE telegram_id = ?', (telegram_id,))
        log = cursor.fetchone()

        if log and log[0] == 1:
            # If logged in, generate a response using the LLaMA model
            response = getLLamaresponse(user_message)
            await update.message.reply_text(response)
        else:
            await update.message.reply_text('Please log in by using /login.')

    except sqlite3.Error as e:
        await update.message.reply_text(f'An error occurred while accessing the database: {e}')
    
    finally:
        # Ensure the database connection is closed
        conn.close()

# Initialize application
def main():
    
    application = Application.builder().token(TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('coin', coin))
    application.add_handler(CommandHandler('market', market))
    application.add_handler(CommandHandler('register', register))
    application.add_handler(CommandHandler('login', login))
    application.add_handler(CommandHandler('logout', logout))
    application.add_handler(CommandHandler('delete', delete))
    application.add_handler(CommandHandler('forex', forex))
    application.add_handler(CommandHandler('stock', stock))
    application.add_handler(CommandHandler('budget_highlights', budget_highlights))
    application.add_handler(CommandHandler('finance_news', finance_news))
    application.add_handler(CommandHandler('request_otp', request_otp))
    application.add_handler(CommandHandler('verify_otp', verify_otp))
    application.add_handler(CommandHandler('recover_username', recover_username))
    application.add_handler(CommandHandler('reset_password', reset_password))
    application.add_handler(CommandHandler('predict', predict))
    application.add_handler(CommandHandler('search', search))

     # Message handler for text messages
    message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    application.add_handler(message_handler)

    # Start the bot
    application.run_polling()

if __name__ == '__main__':
    ticker = 'AAPL'
    features, labels = download_and_preprocess_data(ticker)
    model = train_model(features, labels)
    # Enable logging
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logger = logging.getLogger(__name__)
    main()