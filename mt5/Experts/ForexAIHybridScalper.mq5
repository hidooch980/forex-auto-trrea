//+------------------------------------------------------------------+
//| Forex AI Hybrid Scalper - MT5 Expert Advisor                     |
//| Signal bridge: terminal Global Variables published by a trusted  |
//| local bridge connected to the Python Master Brain.               |
//| Live execution is OFF by default.                                 |
//+------------------------------------------------------------------+
#property strict
#property version   "0.1.0"
#property description "Risk-gated MT5 execution shell for Forex AI Hybrid Scalper"

#include <Trade/Trade.mqh>

input bool   InpEnableLiveTrading       = false;   // Explicit opt-in required
input long   InpMagicNumber             = 26110201;
input double InpRiskPerTradePct         = 0.25;    // FX ceiling; XAU ceiling is lower
input double InpXauRiskCapPct           = 0.10;
input double InpMaxDailyLossPct         = 1.00;
input double InpMinConfidence           = 0.60;
input double InpMaxSpreadPoints         = 30.0;
input int    InpMaxSignalAgeSeconds     = 60;
input double InpRewardRisk              = 1.50;
input int    InpDeviationPoints         = 10;
input bool   InpRequireBrainApproval    = true;

CTrade trade;
datetime g_last_signal_timestamp = 0;
string g_signal_prefix;

// Expected terminal Global Variables (set by a trusted bridge):
// FAI.<SYMBOL>.ACTION       = 1 (BUY), -1 (SELL), 0 (no signal)
// FAI.<SYMBOL>.CONFIDENCE   = [0..1]
// FAI.<SYMBOL>.SL_POINTS    = stop distance in points
// FAI.<SYMBOL>.TIMESTAMP    = Unix timestamp (TimeCurrent-compatible)
// FAI.<SYMBOL>.APPROVED     = 1 only when Master Brain approved
// FAI.GLOBAL.EMERGENCY_STOP = 1 to block new entries

string DayEquityKey()
{
   string day = TimeToString(TimeCurrent(), TIME_DATE);
   StringReplace(day, ".", "");
   return StringFormat("FAI.%I64d.%s.%s", AccountInfoInteger(ACCOUNT_LOGIN), _Symbol, day);
}

double EffectiveRiskPct()
{
   double cap = MathMin(InpRiskPerTradePct, 0.25);
   string symbol = _Symbol;
   StringToUpper(symbol);
   if(StringFind(symbol, "XAU") >= 0)
      cap = MathMin(cap, InpXauRiskCapPct);
   return cap;
}

bool ReadGV(const string name, double &value)
{
   if(!GlobalVariableCheck(name))
      return false;
   value = GlobalVariableGet(name);
   return MathIsValidNumber(value);
}

bool DailyLossAllowed()
{
   string key = DayEquityKey();
   double start_equity = 0.0;
   if(!GlobalVariableCheck(key))
   {
      start_equity = AccountInfoDouble(ACCOUNT_EQUITY);
      if(start_equity <= 0.0)
         return false;
      GlobalVariableSet(key, start_equity);
   }
   else
      start_equity = GlobalVariableGet(key);

   if(start_equity <= 0.0)
      return false;

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double loss_pct = (start_equity - equity) / start_equity * 100.0;
   double daily_limit = MathMin(InpMaxDailyLossPct, 1.00);
   return (loss_pct < daily_limit);
}

bool HasOpenPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; --i)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
         return true;
   }
   return false;
}

double NormalizeVolumeDown(double volume)
{
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minv = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxv = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(step <= 0.0 || minv <= 0.0 || maxv <= 0.0)
      return 0.0;

   volume = MathMin(volume, maxv);
   volume = MathFloor(volume / step + 1e-9) * step;
   int digits = 0;
   double s = step;
   while(digits < 8 && MathAbs(s - MathRound(s)) > 1e-8)
   {
      s *= 10.0;
      digits++;
   }
   volume = NormalizeDouble(volume, digits);
   // Never round up to broker minimum: that could violate the risk cap.
   if(volume < minv)
      return 0.0;
   return volume;
}

double CalculateRiskVolume(ENUM_ORDER_TYPE order_type, double entry, double stop)
{
   double risk_money = AccountInfoDouble(ACCOUNT_EQUITY) * EffectiveRiskPct() / 100.0;
   if(risk_money <= 0.0)
      return 0.0;

   double one_lot_pnl = 0.0;
   if(!OrderCalcProfit(order_type, _Symbol, 1.0, entry, stop, one_lot_pnl))
      return 0.0;
   double one_lot_loss = MathAbs(one_lot_pnl);
   if(one_lot_loss <= 0.0)
      return 0.0;

   double volume = NormalizeVolumeDown(risk_money / one_lot_loss);
   if(volume <= 0.0)
      return 0.0;

   double margin = 0.0;
   if(!OrderCalcMargin(order_type, _Symbol, volume, entry, margin))
      return 0.0;
   if(margin > AccountInfoDouble(ACCOUNT_MARGIN_FREE))
      return 0.0;
   return volume;
}

bool StopsAreValid(double entry, double stop, double target)
{
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   long stops_level = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   if(point <= 0.0)
      return false;
   double min_distance = (double)stops_level * point;
   if(MathAbs(entry - stop) < min_distance || MathAbs(target - entry) < min_distance)
      return false;
   return true;
}

void OnTick()
{
   if(!InpEnableLiveTrading)
      return;

   if(!TerminalInfoInteger(TERMINAL_CONNECTED) ||
      !MQLInfoInteger(MQL_TRADE_ALLOWED) ||
      !TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
      return;

   double emergency = 0.0;
   if(ReadGV("FAI.GLOBAL.EMERGENCY_STOP", emergency) && emergency >= 1.0)
      return;
   if(!DailyLossAllowed() || HasOpenPosition())
      return;

   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
      return;
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   if(point <= 0.0 || tick.ask <= tick.bid)
      return;

   double spread_points = (tick.ask - tick.bid) / point;
   if(spread_points > InpMaxSpreadPoints)
      return;

   double action = 0.0, confidence = 0.0, sl_points = 0.0;
   double timestamp_value = 0.0, approved = 0.0;
   string action_key = g_signal_prefix + "ACTION";
   if(!ReadGV(action_key, action) ||
      !ReadGV(g_signal_prefix + "CONFIDENCE", confidence) ||
      !ReadGV(g_signal_prefix + "SL_POINTS", sl_points) ||
      !ReadGV(g_signal_prefix + "TIMESTAMP", timestamp_value))
      return;

   if(InpRequireBrainApproval &&
      (!ReadGV(g_signal_prefix + "APPROVED", approved) || approved < 1.0))
      return;

   if(action != 1.0 && action != -1.0)
      return;
   if(confidence < InpMinConfidence || confidence > 1.0)
      return;
   if(sl_points <= 0.0 || timestamp_value <= 0.0)
      return;

   datetime signal_time = (datetime)timestamp_value;
   datetime now = TimeCurrent();
   if(signal_time > now || (now - signal_time) > InpMaxSignalAgeSeconds)
      return;
   if(signal_time == g_last_signal_timestamp)
      return;

   ENUM_ORDER_TYPE order_type = (action > 0.0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   double entry = (action > 0.0 ? tick.ask : tick.bid);
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double sl_distance = sl_points * point;
   double stop = (action > 0.0 ? entry - sl_distance : entry + sl_distance);
   double target = (action > 0.0 ? entry + sl_distance * InpRewardRisk
                                 : entry - sl_distance * InpRewardRisk);
   stop = NormalizeDouble(stop, digits);
   target = NormalizeDouble(target, digits);
   if(!StopsAreValid(entry, stop, target))
      return;

   double volume = CalculateRiskVolume(order_type, entry, stop);
   if(volume <= 0.0)
      return;

   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(InpDeviationPoints);
   trade.SetTypeFillingBySymbol(_Symbol);

   bool sent = false;
   if(action > 0.0)
      sent = trade.Buy(volume, _Symbol, 0.0, stop, target, "ForexAI Hybrid BUY");
   else
      sent = trade.Sell(volume, _Symbol, 0.0, stop, target, "ForexAI Hybrid SELL");

   if(sent && (trade.ResultRetcode() == TRADE_RETCODE_DONE ||
               trade.ResultRetcode() == TRADE_RETCODE_PLACED))
      g_last_signal_timestamp = signal_time;
   else
      PrintFormat("ForexAI order rejected: retcode=%u, %s",
                  trade.ResultRetcode(), trade.ResultRetcodeDescription());
}

int OnInit()
{
   if(InpRiskPerTradePct <= 0.0 || InpXauRiskCapPct <= 0.0 ||
      InpMaxDailyLossPct <= 0.0 || InpRewardRisk <= 0.0 ||
      InpMinConfidence < 0.0 || InpMinConfidence > 1.0 ||
      InpMaxSignalAgeSeconds <= 0 || InpMaxSpreadPoints <= 0.0)
      return INIT_PARAMETERS_INCORRECT;

   g_signal_prefix = "FAI." + _Symbol + ".";
   trade.SetExpertMagicNumber(InpMagicNumber);
   Print("Forex AI Hybrid Scalper initialized. Live trading: ",
         (InpEnableLiveTrading ? "ENABLED" : "DISABLED"));
   return INIT_SUCCEEDED;
}
