//+------------------------------------------------------------------+
//| ForexAutoWebBridge.mq5                                           |
//| Read-only market snapshot publisher. NO TRADE FUNCTIONS.         |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property description "Publishes read-only MT5 snapshots to Forex Auto."

input string BridgeUrl = "https://79.137.125.61/api/mt5/bridge/ingest";
input string BridgeToken = "";
input string PublishSymbol = "";
input ENUM_TIMEFRAMES PublishTimeframe = PERIOD_M15;
input int BarsToPublish = 100;
input int PublishEverySeconds = 10;

string JsonEscape(string value)
{
   StringReplace(value, "\\", "\\\\");
   StringReplace(value, "\"", "\\\"");
   return value;
}
string Num(double value, int digits=8) { return DoubleToString(value, digits); }

int OnInit()
{
   if(StringLen(BridgeToken) < 32 || BarsToPublish < 20 || BarsToPublish > 300)
      return INIT_PARAMETERS_INCORRECT;
   EventSetTimer(MathMax(5, PublishEverySeconds));
   PublishSnapshot();
   return INIT_SUCCEEDED;
}
void OnDeinit(const int reason) { EventKillTimer(); }
void OnTimer() { PublishSnapshot(); }

void PublishSnapshot()
{
   string symbol = PublishSymbol == "" ? _Symbol : PublishSymbol;
   if(!SymbolSelect(symbol, true)) return;
   MqlTick tick;
   if(!SymbolInfoTick(symbol, tick) || tick.bid <= 0 || tick.ask < tick.bid) return;

   MqlRates rates[];
   ArraySetAsSeries(rates, false);
   int copied = CopyRates(symbol, PublishTimeframe, 1, BarsToPublish, rates);
   if(copied < 20) return;

   long mode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   string accountMode = mode == ACCOUNT_TRADE_MODE_DEMO ? "demo" :
                        mode == ACCOUNT_TRADE_MODE_CONTEST ? "contest" : "live";
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   double tickSize = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValueLoss = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   if(tickValueLoss <= 0) tickValueLoss = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);

   string bars = "[";
   for(int i=0; i<copied; i++)
   {
      if(i > 0) bars += ",";
      bars += "{\"time\":" + IntegerToString((long)rates[i].time) +
              ",\"open\":" + Num(rates[i].open, digits) +
              ",\"high\":" + Num(rates[i].high, digits) +
              ",\"low\":" + Num(rates[i].low, digits) +
              ",\"close\":" + Num(rates[i].close, digits) +
              ",\"tick_volume\":" + IntegerToString((long)rates[i].tick_volume) + "}";
   }
   bars += "]";
   double spreadPoints = point > 0 ? (tick.ask-tick.bid)/point : 0;
   string timeframe = EnumToString(PublishTimeframe);
   StringReplace(timeframe, "PERIOD_", "");

   string body = "{";
   body += "\"timestamp\":" + IntegerToString((long)TimeGMT()) + ",";
   body += "\"server_name\":\"" + JsonEscape(AccountInfoString(ACCOUNT_SERVER)) + "\",";
   body += "\"account_mode\":\"" + accountMode + "\",";
   body += "\"currency\":\"" + JsonEscape(AccountInfoString(ACCOUNT_CURRENCY)) + "\",";
   body += "\"balance\":" + Num(AccountInfoDouble(ACCOUNT_BALANCE), 2) + ",";
   body += "\"equity\":" + Num(AccountInfoDouble(ACCOUNT_EQUITY), 2) + ",";
   body += "\"symbol\":\"" + JsonEscape(symbol) + "\",";
   body += "\"timeframe\":\"" + timeframe + "\",";
   body += "\"bid\":" + Num(tick.bid, digits) + ",";
   body += "\"ask\":" + Num(tick.ask, digits) + ",";
   body += "\"spread_points\":" + Num(spreadPoints, 2) + ",";
   body += "\"point\":" + Num(point, 10) + ",";
   body += "\"digits\":" + IntegerToString(digits) + ",";
   body += "\"tick_size\":" + Num(tickSize, 10) + ",";
   body += "\"tick_value_loss\":" + Num(tickValueLoss, 8) + ",";
   body += "\"stops_level_points\":" + IntegerToString((int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL)) + ",";
   body += "\"freeze_level_points\":" + IntegerToString((int)SymbolInfoInteger(symbol, SYMBOL_TRADE_FREEZE_LEVEL)) + ",";
   body += "\"volume_min\":" + Num(SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN), 4) + ",";
   body += "\"volume_max\":" + Num(SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX), 4) + ",";
   body += "\"volume_step\":" + Num(SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP), 4) + ",";
   body += "\"bars\":" + bars + "}";

   char data[];
   StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);
   if(ArraySize(data)>0) ArrayResize(data, ArraySize(data)-1);
   char result[];
   string resultHeaders;
   string headers = "Content-Type: application/json\r\nAuthorization: Bearer " + BridgeToken + "\r\n";
   ResetLastError();
   int code = WebRequest("POST", BridgeUrl, headers, 10000, data, result, resultHeaders);
   if(code == -1)
      Print("ForexAuto bridge WebRequest error=", GetLastError(),
            ". Allow the HTTPS host in MT5 Expert Advisors WebRequest settings.");
   else if(code < 200 || code >= 300)
      Print("ForexAuto bridge HTTP=", code, " response=", CharArrayToString(result));
}
