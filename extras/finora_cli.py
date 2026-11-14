#!/usr/bin/env python3
"""Finora - personal finance tracker with budgeting, savings goals,
financial literacy lessons and an AI advisor. Run: python finora.py
Optional: set ANTHROPIC_API_KEY for Claude-powered advice (offline rules work without it)."""
import sqlite3, os, json, random, urllib.request
import datetime as dt

CUR = "₹"
DB = os.path.join(os.path.expanduser("~"), ".finora.db")
con = sqlite3.connect(DB)
con.executescript("""
CREATE TABLE IF NOT EXISTS tx(id INTEGER PRIMARY KEY, date TEXT, kind TEXT, category TEXT, amount REAL, note TEXT);
CREATE TABLE IF NOT EXISTS budgets(category TEXT PRIMARY KEY, limit_amt REAL);
CREATE TABLE IF NOT EXISTS goals(id INTEGER PRIMARY KEY, name TEXT, target REAL, saved REAL DEFAULT 0, deadline TEXT);
""")
NEEDS = {"rent", "food", "groceries", "bills", "transport", "health", "education", "emi", "utilities"}


def ask(prompt, cast=str, default=None):
    while True:
        raw = input(f"{prompt}{f' [{default}]' if default is not None else ''}: ").strip()
        if not raw and default is not None:
            return default
        try:
            val = cast(raw)
            if cast in (float, int) and val < 0:
                raise ValueError
            if cast is str and not val:
                raise ValueError
            return val
        except ValueError:
            print("  Invalid input, try again.")


def money(x): return f"{CUR}{x:,.0f}"
def month(): return dt.date.today().strftime("%Y-%m")


def bar(frac, w=20):
    f = max(0, min(1, frac))
    return "█" * int(f * w) + "░" * (w - int(f * w))


def stats(m=None):
    m = m or month()
    rows = con.execute("SELECT kind, category, SUM(amount) FROM tx WHERE date LIKE ? GROUP BY kind, category", (m + "%",)).fetchall()
    inc = sum(r[2] for r in rows if r[0] == "income")
    cats = {r[1]: r[2] for r in rows if r[0] == "expense"}
    return inc, sum(cats.values()), cats


# ---------- Transactions ----------
def add_tx():
    kind = "income" if ask("Type (i = income, e = expense)", str, "e").lower().startswith("i") else "expense"
    amt = ask("Amount", float)
    cat = ask("Category (e.g. salary, food, rent, transport, fun)").lower()
    note = ask("Note (optional)", str, "-")
    date = ask("Date YYYY-MM-DD", str, dt.date.today().isoformat())
    con.execute("INSERT INTO tx(date,kind,category,amount,note) VALUES(?,?,?,?,?)", (date, kind, cat, amt, note))
    con.commit()
    print(f"  Saved {kind} of {money(amt)}.")
    if kind == "expense":
        b = con.execute("SELECT limit_amt FROM budgets WHERE category=?", (cat,)).fetchone()
        spent = stats()[2].get(cat, 0)
        if b and spent > b[0]:
            print(f"  ⚠ Over budget on '{cat}': {money(spent)} / {money(b[0])}")


def list_tx():
    for r in con.execute("SELECT id,date,kind,category,amount,note FROM tx ORDER BY date DESC, id DESC LIMIT 15"):
        sign = "+" if r[2] == "income" else "-"
        print(f"  #{r[0]:<4}{r[1]}  {sign}{money(r[4]):>10}  {r[3]:<12}{r[5]}")
    d = input("Delete a transaction? Enter id or press Enter to skip: ").strip()
    if d.isdigit():
        con.execute("DELETE FROM tx WHERE id=?", (int(d),)); con.commit(); print("  Deleted.")


# ---------- Budgets ----------
def budgets():
    if input("Set/update a budget? (y/n) [n]: ").strip().lower() == "y":
        cat = ask("Category").lower()
        con.execute("INSERT OR REPLACE INTO budgets VALUES(?,?)", (cat, ask("Monthly limit", float)))
        con.commit()
    _, _, cats = stats()
    print(f"\n  Budget status for {month()}")
    rows = con.execute("SELECT category, limit_amt FROM budgets").fetchall()
    if not rows:
        print("  No budgets yet.")
    for c, lim in rows:
        s = cats.get(c, 0)
        flag = " ⚠ OVER" if s > lim else ""
        print(f"  {c:<12}{bar(s / lim)} {money(s)} / {money(lim)}{flag}")


# ---------- Savings goals ----------
def goals():
    print("  1) New goal  2) Add money to goal  3) View goals")
    ch = ask("Choose", str, "3")
    if ch == "1":
        dl = ask("Deadline YYYY-MM-DD (or 'none')", str, "none")
        con.execute("INSERT INTO goals(name,target,deadline) VALUES(?,?,?)", (ask("Goal name"), ask("Target amount", float), dl))
        con.commit()
    elif ch == "2":
        gid = ask("Goal id", int)
        amt = ask("Amount to add", float)
        con.execute("UPDATE goals SET saved = saved + ? WHERE id=?", (amt, gid)); con.commit()
    for gid, name, target, saved, dl in con.execute("SELECT * FROM goals"):
        line = f"  #{gid} {name:<18}{bar(saved / target)} {money(saved)} / {money(target)}"
        if dl != "none" and saved < target:
            try:
                left = max(1, (dt.date.fromisoformat(dl) - dt.date.today()).days / 30)
                line += f"  → save {money((target - saved) / left)}/month to hit {dl}"
            except ValueError:
                pass
        print(line)


# ---------- Dashboard ----------
def dashboard():
    inc, exp, cats = stats()
    rate = (inc - exp) / inc * 100 if inc else 0
    total_saved = con.execute("SELECT COALESCE(SUM(saved),0) FROM goals").fetchone()[0]
    print(f"\n  ===== Finora Dashboard · {month()} =====")
    print(f"  Income:        {money(inc)}\n  Expenses:      {money(exp)}\n  Net:           {money(inc - exp)}")
    print(f"  Savings rate:  {rate:.0f}%\n  In goals:      {money(total_saved)}")
    for c, v in sorted(cats.items(), key=lambda x: -x[1])[:5]:
        print(f"    {c:<12}{bar(v / exp)} {v / exp * 100:.0f}%")


# ---------- AI advisor ----------
def rule_tips():
    inc, exp, cats = stats()
    tips = []
    if not inc:
        return ["Add your income this month so Finora can analyse your finances."]
    rate = (inc - exp) / inc
    if rate < 0:
        tips.append(f"🔴 You're spending {money(exp - inc)} more than you earn. Cut your top wants first.")
    elif rate < 0.10:
        tips.append(f"🟠 Savings rate is {rate:.0%}. Aim for 20%: automate a transfer on payday.")
    elif rate < 0.20:
        tips.append(f"🟡 Savings rate is {rate:.0%}, decent. Push toward 20%.")
    else:
        tips.append(f"🟢 Savings rate is {rate:.0%}, excellent. Consider investing the surplus.")
    needs = sum(v for c, v in cats.items() if c in NEEDS)
    wants = exp - needs
    if needs / inc > 0.5:
        tips.append(f"Needs are {needs / inc:.0%} of income (50/30/20 suggests ≤50%). Review rent, bills, EMIs.")
    if wants / inc > 0.3:
        tips.append(f"Wants are {wants / inc:.0%} of income (guideline ≤30%). Set budgets on fun/shopping.")
    for c, lim in con.execute("SELECT category, limit_amt FROM budgets"):
        if cats.get(c, 0) > lim:
            tips.append(f"Over budget on '{c}' by {money(cats[c] - lim)}.")
    if cats:
        top = max(cats, key=cats.get)
        tips.append(f"Biggest spend: '{top}' ({money(cats[top])}). Small cuts here matter most.")
    efund = con.execute("SELECT COALESCE(SUM(saved),0) FROM goals WHERE lower(name) LIKE '%emergency%'").fetchone()[0]
    if efund < 3 * exp:
        tips.append(f"Emergency fund is {money(efund)}; target 3-6 months of expenses ({money(3 * exp)}-{money(6 * exp)}). Make this goal #1.")
    return tips


def advisor():
    print("\n  === Finora Advisor ===")
    tips = rule_tips()
    for t in tips:
        print("  •", t)
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("\n  (Set ANTHROPIC_API_KEY for deeper, personalised Claude advice.)")
        return
    inc, exp, cats = stats()
    prompt = (f"I earn {inc} and spend {exp} per month ({CUR}). Spending by category: {cats}. "
              f"Observations: {tips}. Give 4 short, concrete, beginner-friendly next steps. Not professional advice.")
    try:
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", method="POST",
            data=json.dumps({"model": "claude-sonnet-5-5", "max_tokens": 500,
                             "messages": [{"role": "user", "content": prompt}]}).encode(),
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        out = json.load(urllib.request.urlopen(req, timeout=30))
        print("\n  🤖 AI suggestions:\n  " + out["content"][0]["text"].replace("\n", "\n  "))
    except Exception as e:
        print(f"  AI unavailable ({e}). Showing rule-based advice only.")


# ---------- Literacy ----------
LESSONS = {
    "50/30/20 rule": "Split take-home pay: 50% needs, 30% wants, 20% savings/debt repayment.",
    "Emergency fund": "Keep 3-6 months of expenses in a liquid, safe account before investing.",
    "Compound interest": "Returns earn returns. Starting early matters more than investing big.",
    "Inflation": "Prices rise over time, so idle cash loses buying power. Savings should beat inflation.",
    "Good vs bad debt": "Debt that builds assets/income can help; high-interest card debt should be cleared first.",
    "Diversification": "Don't put everything in one asset. Spread across equity, debt, gold, etc.",
    "SIP": "A Systematic Investment Plan invests a fixed amount monthly, averaging out market ups and downs.",
}


def learn():
    names = list(LESSONS)
    for i, n in enumerate(names, 1):
        print(f"  {i}) {n}")
    print("  C) Compound interest / SIP calculator")
    ch = input("Pick a lesson: ").strip().lower()
    if ch == "c":
        p = ask("Monthly investment", float)
        r = ask("Expected annual return %", float, 12) / 100 / 12
        n = ask("Years", int, 10) * 12
        fv = p * (((1 + r) ** n - 1) / r) * (1 + r) if r else p * n
        print(f"  Invested {money(p * n)} → grows to about {money(fv)} (illustrative, not guaranteed).")
    elif ch.isdigit() and 1 <= int(ch) <= len(names):
        print(f"\n  {names[int(ch) - 1]}: {LESSONS[names[int(ch) - 1]]}")


def main():
    menu = {"1": ("Dashboard", dashboard), "2": ("Add transaction", add_tx), "3": ("Transactions", list_tx),
            "4": ("Budgets", budgets), "5": ("Savings goals", goals), "6": ("AI Advisor", advisor),
            "7": ("Learn finance", learn)}
    print("\n  💰 Welcome to Finora - your finance companion")
    n, t = random.choice(list(LESSONS.items()))
    print(f"  Tip: {n} - {t}")
    while True:
        print("\n" + "\n".join(f"  {k}) {v[0]}" for k, v in menu.items()) + "\n  0) Exit")
        ch = input("> ").strip()
        if ch == "0":
            print("  Stay financially fit! 👋"); break
        if ch in menu:
            menu[ch][1]()
        else:
            print("  Choose a number from the menu.")


if __name__ == "__main__":
    main()
