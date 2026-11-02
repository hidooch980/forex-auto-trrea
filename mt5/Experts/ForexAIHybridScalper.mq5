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
input string InpJournalFile             = "ForexAI_TradeJournal_v2.csv";
input string InpBridgeSecret            = "";      // Must match Python publisher secret (32+ chars)

CTrade trade;
datetime g_last_signal_timestamp = 0;
string g_signal_prefix;

// Signed signal file published atomically by modules.master_brain.signal_bridge.
// File location: Terminal Common\Files\ForexAI_Bridge\<SYMBOL>.signal
// The HMAC-SHA256 is verified locally before any directional signal is accepted.
// FAI.GLOBAL.EMERGENCY_STOP remains a terminal Global Variable kill switch.

string ConsumedSignalKey()
{
   return StringFormat("FAI.%I64d.%s.%I64d.LAST_SIGNAL",
                       AccountInfoInteger(ACCOUNT_LOGIN), _Symbol, InpMagicNumber);
}

string DayEquityKey()
{
   // One shared baseline per trading account and broker-server day.
   // Deliberately excludes symbol so every EA chart observes the same account stop.
   string day = TimeToString(TimeCurrent(), TIME_DATE);
   StringReplace(day, ".", "");
   return StringFormat("FAI.%I64d.ACCOUNT.%s", AccountInfoInteger(ACCOUNT_LOGIN), day);
}

double EffectiveRiskPct()
{
   double cap = MathMin(InpRiskPerTradePct, 0.25);
   string symbol = _Symbol;
   StringToUpper(symbol);
   if(StringFind(symbol, "XAU") >= 0)
      cap = MathMin(cap, MathMin(InpXauRiskCapPct, 0.10));
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



bool Sha256(const uchar &data[], uchar &digest[])
{
   uchar empty_key[];
   ArrayResize(empty_key, 0);
   return CryptEncode(CRYPT_HASH_SHA256, data, empty_key, digest) == 32;
}

string HmacSha256Hex(const string message, const string secret)
{
   uchar key[], msg[];
   if(StringToCharArray(secret, key, 0, WHOLE_ARRAY, CP_UTF8) <= 1)
      return "";
   if(ArraySize(key) > 0 && key[ArraySize(key)-1] == 0)
      ArrayResize(key, ArraySize(key)-1);
   if(StringToCharArray(message, msg, 0, WHOLE_ARRAY, CP_UTF8) <= 1)
      return "";
   if(ArraySize(msg) > 0 && msg[ArraySize(msg)-1] == 0)
      ArrayResize(msg, ArraySize(msg)-1);

   uchar key_hash[];
   if(ArraySize(key) > 64)
   {
      if(!Sha256(key, key_hash))
         return "";
      ArrayCopy(key, key_hash);
   }
   uchar ipad[], opad[];
   ArrayResize(ipad, 64);
   ArrayResize(opad, 64);
   for(int i=0; i<64; i++)
   {
      uchar value = (i < ArraySize(key) ? key[i] : 0);
      ipad[i] = (uchar)(value ^ 0x36);
      opad[i] = (uchar)(value ^ 0x5c);
   }

   uchar inner[];
   ArrayResize(inner, 64 + ArraySize(msg));
   ArrayCopy(inner, ipad, 0, 0, 64);
   if(ArraySize(msg) > 0)
      ArrayCopy(inner, msg, 64, 0, ArraySize(msg));
   uchar inner_hash[];
   if(!Sha256(inner, inner_hash))
      return "";

   uchar outer[];
   ArrayResize(outer, 64 + ArraySize(inner_hash));
   ArrayCopy(outer, opad, 0, 0, 64);
   ArrayCopy(outer, inner_hash, 64, 0, ArraySize(inner_hash));
   uchar digest[];
   if(!Sha256(outer, digest))
      return "";

   string hex = "";
   for(int j=0; j<ArraySize(digest); j++)
      hex += StringFormat("%02x", (int)digest[j]);
   return hex;
}

bool ReadBridgeSignal(double &action, double &confidence,
                      double &sl_points, datetime &signal_time)
{
   string filename = "ForexAI_Bridge\\" + _Symbol + ".signal";
   int handle = FileOpen(filename, FILE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON, '|');
   if(handle == INVALID_HANDLE)
      return false;

   string version = FileReadString(handle);
   string symbol = FileReadString(handle);
   string action_text = FileReadString(handle);
   string confidence_text = FileReadString(handle);
   string sl_text = FileReadString(handle);
   string timestamp_text = FileReadString(handle);
   string approved_text = FileReadString(handle);
   string nonce = FileReadString(handle);
   string signature = FileReadString(handle);
   FileClose(handle);

   if(version != "FAI1" || symbol != _Symbol ||
      (action_text != "BUY" && action_text != "SELL" && action_text != "HOLD") ||
      (approved_text != "0" && approved_text != "1") ||
      StringLen(nonce) != 32 || StringLen(signature) != 64)
      return false;

   string canonical = version + "|" + symbol + "|" + action_text + "|" +
                      confidence_text + "|" + sl_text + "|" + timestamp_text +
                      "|" + approved_text + "|" + nonce;
   string expected = HmacSha256Hex(canonical, InpBridgeSecret);
   if(expected == "" || expected != signature)
   {
      Print("ForexAI bridge: signature verification failed.");
      return false;
   }

   confidence = StringToDouble(confidence_text);
   sl_points = StringToDouble(sl_text);
   long timestamp = StringToInteger(timestamp_text);
   if(confidence < 0.0 || confidence > 1.0 || timestamp <= 0)
      return false;

   if(action_text == "HOLD")
   {
      if(approved_text != "0")
         return false;
      action = 0.0;
      signal_time = (datetime)timestamp;
      return true;
   }

   if(approved_text != "1" || sl_points <= 0.0)
      return false;
   action = (action_text == "BUY" ? 1.0 : -1.0);
   signal_time = (datetime)timestamp;
   return true;
}


string DealTypeText(const long value)
{
   if(value == DEAL_TYPE_BUY) return "BUY";
   if(value == DEAL_TYPE_SELL) return "SELL";
   if(value == DEAL_TYPE_BALANCE) return "BALANCE";
   if(value == DEAL_TYPE_CREDIT) return "CREDIT";
   if(value == DEAL_TYPE_CHARGE) return "CHARGE";
   if(value == DEAL_TYPE_CORRECTION) return "CORRECTION";
   if(value == DEAL_TYPE_BONUS) return "BONUS";
   if(value == DEAL_TYPE_COMMISSION) return "COMMISSION";
   if(value == DEAL_TYPE_INTEREST) return "INTEREST";
   if(value == DEAL_TYPE_BUY_CANCELED) return "BUY_CANCELED";
   if(value == DEAL_TYPE_SELL_CANCELED) return "SELL_CANCELED";
   return "OTHER";
}

string DealEntryText(const long value)
{
   if(value == DEAL_ENTRY_IN) return "ENTRY_IN";
   if(value == DEAL_ENTRY_OUT) return "ENTRY_OUT";
   if(value == DEAL_ENTRY_INOUT) return "ENTRY_INOUT";
   if(value == DEAL_ENTRY_OUT_BY) return "ENTRY_OUT_BY";
   return "OTHER";
}


string DealReasonText(const long value)
{
   if(value == DEAL_REASON_CLIENT) return "CLIENT_MANUAL";
   if(value == DEAL_REASON_MOBILE) return "MOBILE_MANUAL";
   if(value == DEAL_REASON_WEB) return "WEB_MANUAL";
   if(value == DEAL_REASON_EXPERT) return "EXPERT_ADVISOR";
   if(value == DEAL_REASON_SL) return "STOP_LOSS";
   if(value == DEAL_REASON_TP) return "TAKE_PROFIT";
   if(value == DEAL_REASON_SO) return "STOP_OUT_MARGIN";
   if(value == DEAL_REASON_ROLLOVER) return "ROLLOVER";
   if(value == DEAL_REASON_VMARGIN) return "VARIATION_MARGIN";
   if(value == DEAL_REASON_SPLIT) return "CORPORATE_SPLIT";
   return "OTHER_OR_UNKNOWN";
}

string LossReasonText(const long reason, const double net_result, const long entry)
{
   if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_OUT_BY && entry != DEAL_ENTRY_INOUT)
      return "NOT_AN_EXIT";
   if(net_result >= 0.0) return "NOT_A_LOSS";
   if(reason == DEAL_REASON_SL) return "STOP_LOSS_TRIGGERED";
   if(reason == DEAL_REASON_SO) return "MARGIN_STOP_OUT";
   if(reason == DEAL_REASON_CLIENT || reason == DEAL_REASON_MOBILE || reason == DEAL_REASON_WEB)
      return "MANUAL_CLOSE_AT_LOSS";
   if(reason == DEAL_REASON_EXPERT) return "EA_CLOSED_AT_LOSS";
   if(reason == DEAL_REASON_ROLLOVER) return "ROLLOVER_ADJUSTMENT";
   return "LOSS_OTHER_OR_UNATTRIBUTED";
}

string PositionMetaKey(const ulong position_id, const string field)
{
   return StringFormat("FAI.POS.%I64u.%s", position_id, field);
}

void SaveEntryMeta(const ulong position_id, const string symbol)
{
   string prefix = "FAI." + symbol + ".";
   double value = 0.0;
   if(ReadGV(prefix + "CONFIDENCE", value))
      GlobalVariableSet(PositionMetaKey(position_id, "CONF"), value);
   if(ReadGV(prefix + "ACTION", value))
      GlobalVariableSet(PositionMetaKey(position_id, "ACTION"), value);
   if(ReadGV(prefix + "SL_POINTS", value))
      GlobalVariableSet(PositionMetaKey(position_id, "SLPTS"), value);
   MqlTick tick;
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   if(point > 0.0 && SymbolInfoTick(symbol, tick) && tick.ask > tick.bid)
      GlobalVariableSet(PositionMetaKey(position_id, "SPREAD"), (tick.ask-tick.bid)/point);
}

double PositionMeta(const ulong position_id, const string field)
{
   double value = 0.0;
   if(GlobalVariableCheck(PositionMetaKey(position_id, field)))
      value = GlobalVariableGet(PositionMetaKey(position_id, field));
   else
      value = -1.0;
   return value;
}

void JournalDeal(const ulong deal_ticket)
{
   if(deal_ticket == 0 || !HistoryDealSelect(deal_ticket))
      return;
   long magic = HistoryDealGetInteger(deal_ticket, DEAL_MAGIC);
   if(magic != InpMagicNumber)
      return;

   datetime deal_time = (datetime)HistoryDealGetInteger(deal_ticket, DEAL_TIME);
   string symbol = HistoryDealGetString(deal_ticket, DEAL_SYMBOL);
   long deal_type = HistoryDealGetInteger(deal_ticket, DEAL_TYPE);
   long deal_entry = HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);
   ulong position_id = (ulong)HistoryDealGetInteger(deal_ticket, DEAL_POSITION_ID);
   double volume = HistoryDealGetDouble(deal_ticket, DEAL_VOLUME);
   double price = HistoryDealGetDouble(deal_ticket, DEAL_PRICE);
   double profit = HistoryDealGetDouble(deal_ticket, DEAL_PROFIT);
   double commission = HistoryDealGetDouble(deal_ticket, DEAL_COMMISSION);
   double swap = HistoryDealGetDouble(deal_ticket, DEAL_SWAP);
   double fee = HistoryDealGetDouble(deal_ticket, DEAL_FEE);
   string comment = HistoryDealGetString(deal_ticket, DEAL_COMMENT);
   long deal_reason = HistoryDealGetInteger(deal_ticket, DEAL_REASON);
   double net_result = profit + commission + swap + fee;
   double entry_confidence = -1.0, entry_action = -1.0, entry_sl_points = -1.0, entry_spread = -1.0;

   if(deal_entry == DEAL_ENTRY_IN)
      SaveEntryMeta(position_id, symbol);
   entry_confidence = PositionMeta(position_id, "CONF");
   entry_action = PositionMeta(position_id, "ACTION");
   entry_sl_points = PositionMeta(position_id, "SLPTS");
   entry_spread = PositionMeta(position_id, "SPREAD");

   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   int handle = FileOpen(InpJournalFile,
                         FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_SHARE_READ,
                         ',');
   if(handle == INVALID_HANDLE)
   {
      PrintFormat("Trade journal open failed (%s): %d", InpJournalFile, GetLastError());
      return;
   }
   if(FileSize(handle) == 0)
      FileWrite(handle, "time_server", "deal_ticket", "position_id", "symbol",
                "deal_type", "deal_entry", "volume", "price", "profit",
                "commission", "swap", "fee", "net_result", "balance",
                "equity", "magic", "deal_reason", "loss_reason",
                "entry_confidence", "entry_action", "entry_sl_points",
                "entry_spread_points", "comment");

   FileSeek(handle, 0, SEEK_END);
   FileWrite(handle, TimeToString(deal_time, TIME_DATE|TIME_SECONDS),
             (string)deal_ticket, (string)position_id, symbol,
             DealTypeText(deal_type), DealEntryText(deal_entry),
             DoubleToString(volume, 4), DoubleToString(price, digits),
             DoubleToString(profit, 2), DoubleToString(commission, 2),
             DoubleToString(swap, 2), DoubleToString(fee, 2),
             DoubleToString(net_result, 2),
             DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2),
             DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2),
             (string)magic, DealReasonText(deal_reason),
             LossReasonText(deal_reason, net_result, deal_entry),
             DoubleToString(entry_confidence, 4),
             (entry_action < 0.0 ? "NA" : (entry_action > 0.0 ? "BUY" : "SELL")),
             DoubleToString(entry_sl_points, 1),
             DoubleToString(entry_spread, 1), comment);
   FileClose(handle);
   PrintFormat("Trade journal: recorded deal %I64u (%s %s)",
               deal_ticket, symbol, DealEntryText(deal_entry));
}

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
      JournalDeal(trans.deal);
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
   datetime signal_time = 0;
   if(!ReadBridgeSignal(action, confidence, sl_points, signal_time))
      return;
   // A signed HOLD message explicitly clears any older directional intent.
   if(action == 0.0)
      return;
   if(InpRequireBrainApproval && !InpRequireBrainApproval) // approval is mandatory in the signed bridge
      return;
   if(confidence < InpMinConfidence || confidence > 1.0 || sl_points <= 0.0)
      return;

   datetime now = TimeGMT();
   if(signal_time > now || (now - signal_time) > InpMaxSignalAgeSeconds)
      return;
   double consumed_timestamp = 0.0;
   if(ReadGV(ConsumedSignalKey(), consumed_timestamp) &&
      (double)signal_time <= consumed_timestamp)
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
   {
      g_last_signal_timestamp = signal_time;
      GlobalVariableSet(ConsumedSignalKey(), (double)signal_time);
   }
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

   if(InpEnableLiveTrading && StringLen(InpBridgeSecret) < 32)
   {
      Print("ForexAI bridge: live trading requires a 32+ character shared secret.");
      return INIT_PARAMETERS_INCORRECT;
   }
   g_signal_prefix = "FAI." + _Symbol + ".";
   trade.SetExpertMagicNumber(InpMagicNumber);
   Print("Forex AI Hybrid Scalper initialized. Live trading: ",
         (InpEnableLiveTrading ? "ENABLED" : "DISABLED"));
   return INIT_SUCCEEDED;
}
