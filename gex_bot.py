"""
🦅 TradeHawk GEX Bot
====================
Scrapes CBOE options data, calculates Gamma Exposure (GEX),
finds key levels, recommends strikes/DTE, posts to Discord.

Deploy to Render.com as a Cron Job or Background Worker.
"""

import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from io import StringIO
import json

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
SYMBOLS = os.environ.get("SYMBOLS", "SPY,QQQ,IWM,AAPL,TSLA,NVDA,AMD,GME,AMC").split(",")

# Trading style: "scalp", "swing", "position"
TRADING_STYLE = os.environ.get("TRADING_STYLE", "swing")

# ══════════════════════════════════════════════════════════════════════════════
# CBOE DATA SCRAPER
# ══════════════════════════════════════════════════════════════════════════════

def get_cboe_options_data(symbol):
    """
    Fetch options chain data from CBOE (delayed, free).
    Returns DataFrame with calls and puts.
    """
    try:
        # CBOE delayed quotes URL
        url = f"https://cdn.cboe.com/api/global/delayed_quotes/options/{symbol}.json"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            print(f"❌ Failed to fetch {symbol}: {response.status_code}")
            return None, None
        
        data = response.json()
        
        # Extract spot price
        spot_price = data.get("data", {}).get("close", 0)
        if spot_price == 0:
            spot_price = data.get("data", {}).get("current_price", 0)
        
        # Extract options
        options = data.get("data", {}).get("options", [])
        
        if not options:
            print(f"❌ No options data for {symbol}")
            return None, None
        
        # Convert to DataFrame
        df = pd.DataFrame(options)
        
        return df, spot_price
        
    except Exception as e:
        print(f"❌ Error fetching {symbol}: {e}")
        return None, None


def parse_options_chain(df, spot_price):
    """
    Parse CBOE options data into clean format with Greeks.
    """
    try:
        # Columns we need
        required_cols = ['option', 'bid', 'ask', 'delta', 'gamma', 'open_interest', 'volume']
        
        # Check if columns exist
        for col in required_cols:
            if col not in df.columns:
                df[col] = 0
        
        # Parse option symbol to extract strike and type
        def parse_option_symbol(sym):
            try:
                # Format: SPY240102C00450000 or similar
                if 'C' in sym:
                    parts = sym.split('C')
                    opt_type = 'call'
                elif 'P' in sym:
                    parts = sym.split('P')
                    opt_type = 'put'
                else:
                    return None, None, None
                
                # Extract expiration (YYMMDD)
                exp_str = parts[0][-6:]
                
                # Extract strike (last 8 digits, divide by 1000)
                strike_str = parts[1][:8]
                strike = float(strike_str) / 1000
                
                return opt_type, strike, exp_str
            except:
                return None, None, None
        
        # Apply parsing
        parsed = df['option'].apply(parse_option_symbol)
        df['opt_type'] = [p[0] for p in parsed]
        df['strike'] = [p[1] for p in parsed]
        df['expiration'] = [p[2] for p in parsed]
        
        # Remove rows with no type
        df = df[df['opt_type'].notna()]
        
        # Convert columns to numeric
        numeric_cols = ['delta', 'gamma', 'open_interest', 'volume', 'bid', 'ask']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        return df
        
    except Exception as e:
        print(f"❌ Error parsing options: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# GEX CALCULATIONS
# ══════════════════════════════════════════════════════════════════════════════

def calculate_gex(df, spot_price):
    """
    Calculate Gamma Exposure (GEX) per strike.
    
    Formula (SpotGamma/Perfiliev):
    Call GEX = gamma * OI * 100 * spot^2 * 0.01
    Put GEX = -1 * gamma * OI * 100 * spot^2 * 0.01
    """
    try:
        # Separate calls and puts
        calls = df[df['opt_type'] == 'call'].copy()
        puts = df[df['opt_type'] == 'put'].copy()
        
        # Calculate GEX
        calls['gex'] = calls['gamma'] * calls['open_interest'] * 100 * (spot_price ** 2) * 0.01
        puts['gex'] = -1 * puts['gamma'] * puts['open_interest'] * 100 * (spot_price ** 2) * 0.01
        
        # Group by strike
        call_gex = calls.groupby('strike')['gex'].sum().reset_index()
        call_gex.columns = ['strike', 'call_gex']
        
        put_gex = puts.groupby('strike')['gex'].sum().reset_index()
        put_gex.columns = ['strike', 'put_gex']
        
        # Merge
        gex_df = pd.merge(call_gex, put_gex, on='strike', how='outer').fillna(0)
        gex_df['net_gex'] = gex_df['call_gex'] + gex_df['put_gex']
        gex_df['total_gex'] = gex_df['call_gex'].abs() + gex_df['put_gex'].abs()
        
        return gex_df.sort_values('strike')
        
    except Exception as e:
        print(f"❌ Error calculating GEX: {e}")
        return None


def find_key_levels(gex_df, spot_price):
    """
    Find key GEX levels:
    - Zero Gamma (Gamma Flip)
    - Call Wall (highest call GEX)
    - Put Wall (highest put GEX)
    - Max Pain approximation
    """
    try:
        results = {}
        
        # Zero Gamma Level (where net GEX crosses zero)
        gex_df_sorted = gex_df.sort_values('strike')
        
        # Find strikes around spot price
        below_spot = gex_df_sorted[gex_df_sorted['strike'] <= spot_price]
        above_spot = gex_df_sorted[gex_df_sorted['strike'] > spot_price]
        
        # Simple zero gamma: weighted average where GEX changes sign
        positive_gex = gex_df_sorted[gex_df_sorted['net_gex'] > 0]
        negative_gex = gex_df_sorted[gex_df_sorted['net_gex'] < 0]
        
        if len(positive_gex) > 0 and len(negative_gex) > 0:
            # Find transition point
            for i in range(len(gex_df_sorted) - 1):
                if gex_df_sorted.iloc[i]['net_gex'] * gex_df_sorted.iloc[i+1]['net_gex'] < 0:
                    # Sign change - interpolate
                    s1 = gex_df_sorted.iloc[i]['strike']
                    s2 = gex_df_sorted.iloc[i+1]['strike']
                    g1 = gex_df_sorted.iloc[i]['net_gex']
                    g2 = gex_df_sorted.iloc[i+1]['net_gex']
                    
                    # Linear interpolation
                    zero_gamma = s1 - g1 * (s2 - s1) / (g2 - g1)
                    results['zero_gamma'] = round(zero_gamma, 2)
                    break
        
        if 'zero_gamma' not in results:
            results['zero_gamma'] = spot_price  # Default to spot
        
        # Call Wall (highest positive call GEX near money)
        near_money = gex_df_sorted[
            (gex_df_sorted['strike'] >= spot_price * 0.95) & 
            (gex_df_sorted['strike'] <= spot_price * 1.10)
        ]
        
        if len(near_money) > 0:
            call_wall_idx = near_money['call_gex'].idxmax()
            results['call_wall'] = near_money.loc[call_wall_idx, 'strike']
            results['call_wall_gex'] = near_money.loc[call_wall_idx, 'call_gex']
        else:
            results['call_wall'] = spot_price * 1.02
            results['call_wall_gex'] = 0
        
        # Put Wall (highest negative put GEX near money)
        if len(near_money) > 0:
            put_wall_idx = near_money['put_gex'].idxmin()  # Most negative
            results['put_wall'] = near_money.loc[put_wall_idx, 'strike']
            results['put_wall_gex'] = near_money.loc[put_wall_idx, 'put_gex']
        else:
            results['put_wall'] = spot_price * 0.98
            results['put_wall_gex'] = 0
        
        # Above/Below Gamma Flip
        results['above_flip'] = spot_price > results['zero_gamma']
        
        # Total Market GEX
        results['total_gex'] = gex_df['net_gex'].sum()
        results['gex_regime'] = "POSITIVE" if results['total_gex'] > 0 else "NEGATIVE"
        
        return results
        
    except Exception as e:
        print(f"❌ Error finding key levels: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# STRIKE & DTE RECOMMENDATIONS
# ══════════════════════════════════════════════════════════════════════════════

def recommend_strike_dte(spot_price, levels, trading_style="swing"):
    """
    Recommend optimal strike and DTE based on GEX levels.
    
    Logic:
    - ABOVE gamma flip = CALLS (buy dips)
    - BELOW gamma flip = PUTS (fade rallies)
    - Strike near high GEX walls
    - DTE based on trading style
    """
    try:
        rec = {}
        
        # Direction based on gamma regime
        if levels['above_flip']:
            rec['direction'] = "CALL"
            rec['bias'] = "BULLISH - Buy Dips"
            rec['target'] = levels['call_wall']
            rec['stop_zone'] = levels['zero_gamma']
        else:
            rec['direction'] = "PUT"
            rec['bias'] = "BEARISH - Fade Rallies"
            rec['target'] = levels['put_wall']
            rec['stop_zone'] = levels['zero_gamma']
        
        # Strike Selection
        if rec['direction'] == "CALL":
            # ATM or slightly OTM call
            atm = round(spot_price)
            rec['strike_atm'] = atm
            rec['strike_otm'] = atm + (1 if spot_price < 50 else 5 if spot_price < 200 else 10)
            rec['strike_itm'] = atm - (1 if spot_price < 50 else 5 if spot_price < 200 else 10)
        else:
            # ATM or slightly OTM put
            atm = round(spot_price)
            rec['strike_atm'] = atm
            rec['strike_otm'] = atm - (1 if spot_price < 50 else 5 if spot_price < 200 else 10)
            rec['strike_itm'] = atm + (1 if spot_price < 50 else 5 if spot_price < 200 else 10)
        
        # DTE based on style
        dte_map = {
            "scalp": {"min": 0, "max": 3, "ideal": 1},
            "swing": {"min": 7, "max": 21, "ideal": 14},
            "position": {"min": 21, "max": 45, "ideal": 30}
        }
        
        style = trading_style.lower()
        if style in dte_map:
            rec['dte'] = dte_map[style]
        else:
            rec['dte'] = dte_map['swing']
        
        # Risk/Reward estimate
        if rec['direction'] == "CALL":
            upside = abs(levels['call_wall'] - spot_price)
            downside = abs(spot_price - levels['zero_gamma'])
        else:
            upside = abs(spot_price - levels['put_wall'])
            downside = abs(levels['zero_gamma'] - spot_price)
        
        rec['rr_ratio'] = round(upside / downside, 2) if downside > 0 else 0
        
        # Confidence
        if levels['gex_regime'] == "POSITIVE" and levels['above_flip']:
            rec['confidence'] = "HIGH"
        elif levels['gex_regime'] == "NEGATIVE" and not levels['above_flip']:
            rec['confidence'] = "HIGH"
        else:
            rec['confidence'] = "MEDIUM"
        
        return rec
        
    except Exception as e:
        print(f"❌ Error recommending strike: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# DISCORD OUTPUT
# ══════════════════════════════════════════════════════════════════════════════

def format_discord_message(symbol, spot_price, levels, rec):
    """
    Format results as Discord embed message.
    """
    
    # Emoji based on direction
    dir_emoji = "🟢" if rec['direction'] == "CALL" else "🔴"
    regime_emoji = "📈" if levels['above_flip'] else "📉"
    
    # Build message
    message = {
        "embeds": [{
            "title": f"🦅 TradeHawk GEX Alert: {symbol}",
            "color": 0x00FF88 if rec['direction'] == "CALL" else 0xFF3366,
            "fields": [
                {
                    "name": "💰 Spot Price",
                    "value": f"${spot_price:.2f}",
                    "inline": True
                },
                {
                    "name": f"{regime_emoji} Gamma Flip",
                    "value": f"${levels['zero_gamma']:.2f}",
                    "inline": True
                },
                {
                    "name": "📊 Position",
                    "value": "ABOVE ⬆️" if levels['above_flip'] else "BELOW ⬇️",
                    "inline": True
                },
                {
                    "name": "🟢 Call Wall",
                    "value": f"${levels['call_wall']:.2f}",
                    "inline": True
                },
                {
                    "name": "🔴 Put Wall",
                    "value": f"${levels['put_wall']:.2f}",
                    "inline": True
                },
                {
                    "name": "⚡ GEX Regime",
                    "value": levels['gex_regime'],
                    "inline": True
                },
                {
                    "name": "═══════════════",
                    "value": "**RECOMMENDATION**",
                    "inline": False
                },
                {
                    "name": f"{dir_emoji} Direction",
                    "value": f"**{rec['direction']}**",
                    "inline": True
                },
                {
                    "name": "🎯 Strike (ATM)",
                    "value": f"${rec['strike_atm']}",
                    "inline": True
                },
                {
                    "name": "📅 DTE",
                    "value": f"{rec['dte']['ideal']} days ({rec['dte']['min']}-{rec['dte']['max']})",
                    "inline": True
                },
                {
                    "name": "🎯 Target",
                    "value": f"${rec['target']:.2f}",
                    "inline": True
                },
                {
                    "name": "🛑 Stop Zone",
                    "value": f"${rec['stop_zone']:.2f}",
                    "inline": True
                },
                {
                    "name": "📊 R:R",
                    "value": f"{rec['rr_ratio']}:1",
                    "inline": True
                },
                {
                    "name": "💪 Confidence",
                    "value": rec['confidence'],
                    "inline": True
                },
                {
                    "name": "📝 Bias",
                    "value": rec['bias'],
                    "inline": False
                }
            ],
            "footer": {
                "text": f"TradeHawk GEX Bot • {datetime.now().strftime('%Y-%m-%d %H:%M ET')}"
            }
        }]
    }
    
    return message


def send_discord_alert(message):
    """
    Send message to Discord webhook.
    """
    if not DISCORD_WEBHOOK:
        print("⚠️ No Discord webhook configured")
        return False
    
    try:
        response = requests.post(
            DISCORD_WEBHOOK,
            json=message,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 204:
            print("✅ Discord alert sent!")
            return True
        else:
            print(f"❌ Discord error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Discord error: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# CONSOLE OUTPUT (for testing)
# ══════════════════════════════════════════════════════════════════════════════

def print_results(symbol, spot_price, levels, rec):
    """
    Print results to console.
    """
    print("\n" + "="*60)
    print(f"🦅 TradeHawk GEX Report: {symbol}")
    print("="*60)
    print(f"💰 Spot Price:    ${spot_price:.2f}")
    print(f"📊 Gamma Flip:    ${levels['zero_gamma']:.2f}")
    print(f"📍 Position:      {'ABOVE ⬆️' if levels['above_flip'] else 'BELOW ⬇️'}")
    print(f"🟢 Call Wall:     ${levels['call_wall']:.2f}")
    print(f"🔴 Put Wall:      ${levels['put_wall']:.2f}")
    print(f"⚡ GEX Regime:    {levels['gex_regime']}")
    print("-"*60)
    print("🎯 RECOMMENDATION:")
    print(f"   Direction:     {rec['direction']}")
    print(f"   Strike (ATM):  ${rec['strike_atm']}")
    print(f"   Strike (OTM):  ${rec['strike_otm']}")
    print(f"   DTE:           {rec['dte']['ideal']} days")
    print(f"   Target:        ${rec['target']:.2f}")
    print(f"   Stop Zone:     ${rec['stop_zone']:.2f}")
    print(f"   R:R Ratio:     {rec['rr_ratio']}:1")
    print(f"   Confidence:    {rec['confidence']}")
    print(f"   Bias:          {rec['bias']}")
    print("="*60 + "\n")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def analyze_symbol(symbol):
    """
    Full analysis pipeline for a single symbol.
    """
    print(f"\n🔍 Analyzing {symbol}...")
    
    # 1. Fetch data
    df, spot_price = get_cboe_options_data(symbol)
    
    if df is None or spot_price is None or spot_price == 0:
        print(f"❌ Could not get data for {symbol}")
        return None
    
    print(f"   Spot: ${spot_price:.2f}, Options: {len(df)}")
    
    # 2. Parse options chain
    df = parse_options_chain(df, spot_price)
    
    if df is None or len(df) == 0:
        print(f"❌ Could not parse options for {symbol}")
        return None
    
    # 3. Calculate GEX
    gex_df = calculate_gex(df, spot_price)
    
    if gex_df is None:
        print(f"❌ Could not calculate GEX for {symbol}")
        return None
    
    # 4. Find key levels
    levels = find_key_levels(gex_df, spot_price)
    
    if levels is None:
        print(f"❌ Could not find levels for {symbol}")
        return None
    
    # 5. Get recommendations
    rec = recommend_strike_dte(spot_price, levels, TRADING_STYLE)
    
    if rec is None:
        print(f"❌ Could not generate recommendations for {symbol}")
        return None
    
    # 6. Output results
    print_results(symbol, spot_price, levels, rec)
    
    # 7. Send to Discord
    if DISCORD_WEBHOOK:
        message = format_discord_message(symbol, spot_price, levels, rec)
        send_discord_alert(message)
    
    return {
        "symbol": symbol,
        "spot_price": spot_price,
        "levels": levels,
        "recommendation": rec
    }


def main():
    """
    Main entry point - analyze all symbols.
    """
    print("\n" + "🦅"*20)
    print("   TradeHawk GEX Bot Starting...")
    print("🦅"*20)
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S ET')}")
    print(f"📊 Symbols: {', '.join(SYMBOLS)}")
    print(f"🎯 Trading Style: {TRADING_STYLE}")
    print(f"📡 Discord: {'Enabled' if DISCORD_WEBHOOK else 'Disabled'}")
    
    results = []
    
    for symbol in SYMBOLS:
        result = analyze_symbol(symbol.strip().upper())
        if result:
            results.append(result)
    
    print(f"\n✅ Completed! Analyzed {len(results)}/{len(SYMBOLS)} symbols.")
    
    return results


if __name__ == "__main__":
    main()
