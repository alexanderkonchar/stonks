import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    user_id = session["user_id"]
    transactions = db.execute("SELECT stonk_symbol, SUM(number_of_shares) as number_of_shares FROM transactions WHERE user_id = ? GROUP BY stonk_symbol HAVING SUM(number_of_shares) > 0", user_id)
    stonks = []
    grand_total = 0

    for transaction in transactions:
        symbol = transaction["stonk_symbol"]
        shares = transaction["number_of_shares"]
        price = lookup(symbol)["price"]
        total = price * shares

        stonk = {"symbol": symbol, "shares": shares, "price": price, "total": total}
        stonks.append(stonk)

        grand_total += total

    cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]
    grand_total += cash

    return render_template("index.html", stonks=stonks, cash=cash, grand_total=grand_total)



@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    user_id = session["user_id"]

    if request.method == "POST":
        symbol = request.form.get("symbol")
        if not symbol:
            return apolgy("Please enter stock symbol.")

        stonk = lookup(symbol)
        if not stonk:
            return apology("Invalid stock symbol.")

        try:
            shares_to_buy = int(request.form.get("shares"))
        except:
            return apology("Invalid number of shares.")

        if shares_to_buy < 1:
            return apology("Must buy at least 1 share.")

        try:
            db.execute("BEGIN TRANSACTION")

            cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]
            transaction_amount = stonk["price"] * shares_to_buy
            if cash < transaction_amount:
                return apology("Not enough money to perform transaction.")

            db.execute("UPDATE users SET cash = ? WHERE id = ?", cash - transaction_amount, user_id)

            db.execute("INSERT INTO transactions (user_id, stonk_symbol, number_of_shares, amount) VALUES(?, ?, ?, ?)",
                    user_id, stonk["symbol"], shares_to_buy, -transaction_amount)

            db.execute("COMMIT")

        except Exception as e:
            return apology(f"Could not complete transaction.\nError: {e}")

        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    transactions = db.execute("SELECT id, stonk_symbol, number_of_shares, ABS(amount) as amount, time FROM transactions where user_id = ?", session["user_id"])
    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    if request.method == "POST":
        stonk = lookup(request.form.get("symbol"))
        if not stonk:
            return apology("Invalid stock symbol.")

        return render_template("quoted.html", stonk=stonk)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":
        username = request.form.get("username")
        if not username:
            return apology("Please input a username.")
        if len(db.execute("SELECT id FROM users WHERE username = ?", username)) != 0:
            return apology("Username taken.")

        password = request.form.get("password")
        if not password:
            return apology("Please enter a password.")

        confirmation = request.form.get("confirmation")
        if not confirmation:
            return apology("Please confirm your password.")

        if password != confirmation:
            return apology("Passwords don't match!")

        try:
            db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, generate_password_hash(password))
        except Exception as e:
            return apology(f"Could not register user.\nError: {e}")

        return login()

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    user_id = session["user_id"]

    if request.method == "POST":
        symbol = request.form.get("symbol")
        if not symbol:
            return apolgy("Please enter stock symbol.")

        stonk = lookup(symbol)
        if not stonk:
            return apology("Invalid stock symbol.")

        transactions = db.execute("SELECT stonk_symbol, SUM(number_of_shares) as number_of_shares FROM transactions WHERE stonk_symbol = ? GROUP BY stonk_symbol HAVING SUM(number_of_shares) > 0", symbol)
        if len(transactions) < 1:
            return apology("Stock not owned.")
        elif len(transactions) > 1:
            return apology("Error: Too many values returned.")

        try:
            shares_to_sell = int(request.form.get("shares"))
        except:
            return apology("Invalid number of shares.")
        
        if shares_to_sell < 1:
            return apology("Must sell at least 1 share.")

        if shares_to_sell > transactions[0]["number_of_shares"]:
            return apology("Not enough shares to sell.")

        try:
            db.execute("BEGIN TRANSACTION")

            cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]
            transaction_amount = stonk["price"] * shares_to_sell

            db.execute("UPDATE users SET cash = ? WHERE id = ?", cash + transaction_amount, user_id)

            db.execute("INSERT INTO transactions (user_id, stonk_symbol, number_of_shares, amount) VALUES(?, ?, ?, ?)",
                    user_id, stonk["symbol"], -shares_to_sell, transaction_amount)

            db.execute("COMMIT")

        except Exception as e:
            return apology(f"Could not complete transaction.\nError: {e}")

        return redirect("/")

    else:
        stonks = db.execute("SELECT stonk_symbol FROM transactions WHERE user_id = ? GROUP BY stonk_symbol HAVING SUM(number_of_shares) > 0", user_id)

        return render_template("sell.html", stonks=stonks)
