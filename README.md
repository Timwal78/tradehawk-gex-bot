# 🦅 TradeHawk GEX Bot

**FREE Gamma Exposure Scanner with Strike & DTE Recommendations**

Scrapes CBOE options data, calculates GEX levels, and recommends strikes/DTE.
Posts alerts to Discord automatically.

---

## 📊 What It Does

1. **Scrapes FREE CBOE data** (delayed 15 min)
2. **Calculates GEX** per strike
3. **Finds key levels:**
   - Zero Gamma (Flip Level)
   - Call Wall
   - Put Wall
4. **Recommends:**
   - CALL or PUT direction
   - Strike price (ATM/OTM)
   - DTE based on your style
   - Target & Stop levels
   - Risk/Reward ratio
5. **Posts to Discord** automatically

---

## 🚀 DEPLOY TO RENDER (Step-by-Step)

### Step 1: Create GitHub Repo

1. Go to **github.com**
2. Click **New Repository**
3. Name it: `tradehawk-gex-bot`
4. Make it **Public** or **Private**
5. Click **Create**

### Step 2: Upload Files

1. Click **Upload files**
2. Drag ALL these files into it:
   - `gex_bot.py`
   - `requirements.txt`
   - `render.yaml`
   - `.env.example`
3. Click **Commit changes**

### Step 3: Get Discord Webhook

1. Open your Discord server
2. Go to **Server Settings** → **Integrations** → **Webhooks**
3. Click **New Webhook**
4. Name it: `TradeHawk GEX`
5. Choose your alerts channel
6. Click **Copy Webhook URL**
7. **SAVE THIS URL** - you need it next!

### Step 4: Deploy to Render

1. Go to **render.com**
2. Sign up (free tier works!)
3. Click **New** → **Cron Job**
4. Connect your GitHub
5. Select your `tradehawk-gex-bot` repo
6. Fill in:
   - **Name:** `tradehawk-gex-bot`
   - **Schedule:** `30 9,12,15 * * 1-5` (runs at 9:30am, 12pm, 3pm on weekdays)
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python gex_bot.py`
7. Click **Advanced** → **Add Environment Variable**:
   - **Key:** `DISCORD_WEBHOOK`
   - **Value:** (paste your Discord webhook URL)
8. Add another:
   - **Key:** `SYMBOLS`
   - **Value:** `SPY,QQQ,GME,AMC,TSLA,NVDA`
9. Add another:
   - **Key:** `TRADING_STYLE`
   - **Value:** `swing` (or `scalp` or `position`)
10. Click **Create Cron Job**

### Step 5: Done! 🎉

Bot will run automatically at:
- **9:30 AM ET** - Market open
- **12:00 PM ET** - Midday
- **3:00 PM ET** - Power hour

---

## ⚙️ Settings

| Variable | Options | Description |
|----------|---------|-------------|
| `SYMBOLS` | Any tickers | Comma separated list |
| `TRADING_STYLE` | `scalp`, `swing`, `position` | Affects DTE recommendation |

### Trading Style DTE:

| Style | DTE Range | Ideal DTE |
|-------|-----------|-----------|
| Scalp | 0-3 days | 1 day |
| Swing | 7-21 days | 14 days |
| Position | 21-45 days | 30 days |

---

## 🧪 Test Locally (Optional)

```bash
# Clone your repo
git clone https://github.com/YOUR_USERNAME/tradehawk-gex-bot.git
cd tradehawk-gex-bot

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DISCORD_WEBHOOK="your_webhook_url"
export SYMBOLS="SPY,QQQ,GME"
export TRADING_STYLE="swing"

# Run it
python gex_bot.py
```

---

## 📱 Discord Output Example

```
🦅 TradeHawk GEX Alert: SPY

💰 Spot Price:    $595.50
📊 Gamma Flip:    $592.00
📍 Position:      ABOVE ⬆️
🟢 Call Wall:     $600.00
🔴 Put Wall:      $585.00
⚡ GEX Regime:    POSITIVE

═══════════════════════════
🎯 RECOMMENDATION:

🟢 Direction:     CALL
🎯 Strike (ATM):  $595
📅 DTE:           14 days (7-21)
🎯 Target:        $600.00
🛑 Stop Zone:     $592.00
📊 R:R:           1.5:1
💪 Confidence:    HIGH
📝 Bias:          BULLISH - Buy Dips
```

---

## 🔧 Troubleshooting

**Bot not running?**
- Check Render logs
- Make sure Discord webhook is correct

**No data for symbol?**
- CBOE only has options for US stocks
- Some small caps may not have data

**Wrong timezone?**
- Cron uses UTC, adjust schedule as needed
- `30 9` = 9:30 AM UTC = 4:30 AM ET
- `30 14` = 2:30 PM UTC = 9:30 AM ET

---

## 📜 Credits

Built for **TradeHawk Pro** Discord community.

GEX formulas from:
- SpotGamma methodology
- Perfiliev calculations
- SqueezeMetrics white paper

---

## ⚠️ Disclaimer

This is for educational purposes only. Not financial advice.
Always do your own research before trading.

---

**🦅 TradeHawk Pro - Stay Sharp!**
