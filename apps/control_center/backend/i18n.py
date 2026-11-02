"""Shared localization catalog and locale helpers for the control center."""
from __future__ import annotations

from copy import deepcopy

SUPPORTED_LOCALES = ("fa", "en", "ar", "tr")
DEFAULT_LOCALE = "fa"
LOCALE_NAMES = {"fa": "فارسی", "en": "English", "ar": "العربية", "tr": "Türkçe"}
RTL_LOCALES = {"fa", "ar"}

# Keys are the stable Persian source strings already used by the first dashboard.
# Keep trading symbols, API identifiers and numerical values locale-neutral.
CATALOG = {
    "به مرکز معاملات خوش آمدید": {"en": "Welcome to the Trading Center", "ar": "مرحباً بك في مركز التداول", "tr": "İşlem Merkezi'ne Hoş Geldiniz"},
    "برای ورود به فضای کاری امن، اطلاعات حساب خود را وارد کنید.": {"en": "Enter your account details to access the secure workspace.", "ar": "أدخل بيانات حسابك للوصول إلى مساحة العمل الآمنة.", "tr": "Güvenli çalışma alanına erişmek için hesap bilgilerinizi girin."},
    "نام کاربری": {"en": "Username", "ar": "اسم المستخدم", "tr": "Kullanıcı adı"},
    "رمز عبور": {"en": "Password", "ar": "كلمة المرور", "tr": "Şifre"},
    "ورود به پنل": {"en": "Sign in", "ar": "تسجيل الدخول", "tr": "Giriş yap"},
    "حساب کاربری خود را وارد کنید.": {"en": "Enter your account credentials.", "ar": "أدخل بيانات حسابك.", "tr": "Hesap bilgilerinizi girin."},
    "فضای کاری": {"en": "Workspace", "ar": "مساحة العمل", "tr": "Çalışma alanı"},
    "نمای کلی": {"en": "Overview", "ar": "نظرة عامة", "tr": "Genel Bakış"},
    "سیگنال‌ها": {"en": "Signals", "ar": "الإشارات", "tr": "Sinyaller"},
    "تحلیل بازار": {"en": "Market Analysis", "ar": "تحليل السوق", "tr": "Piyasa Analizi"},
    "شبیه‌ساز": {"en": "Simulator", "ar": "المحاكي", "tr": "Simülatör"},
    "ماژول‌های AI": {"en": "AI Modules", "ar": "وحدات الذكاء الاصطناعي", "tr": "Yapay Zekâ Modülleri"},
    "مدیریت کاربران": {"en": "User Management", "ar": "إدارة المستخدمين", "tr": "Kullanıcı Yönetimi"},
    "● حالت امن فعال": {"en": "● Safe mode active", "ar": "● الوضع الآمن مفعّل", "tr": "● Güvenli mod etkin"},
    "معاملات واقعی غیرفعال هستند.": {"en": "Live trading is disabled.", "ar": "التداول الحقيقي معطّل.", "tr": "Canlı işlem devre dışı."},
    "مرکز کنترل / ": {"en": "Control Center / ", "ar": "مركز التحكم / ", "tr": "Kontrol Merkezi / "},
    "داشبورد معاملاتی": {"en": "Trading Dashboard", "ar": "لوحة التداول", "tr": "İşlem Paneli"},
    "نمای کلی": {"en": "Overview", "ar": "نظرة عامة", "tr": "Genel Bakış"},
    "تغییر پوسته": {"en": "Change theme", "ar": "تغيير المظهر", "tr": "Temayı değiştir"},
    "خروج": {"en": "Sign out", "ar": "تسجيل الخروج", "tr": "Çıkış yap"},
    "کاربر": {"en": "User", "ar": "مستخدم", "tr": "Kullanıcı"},
    "عضو": {"en": "Member", "ar": "عضو", "tr": "Üye"},
    "داده زنده متصل نیست": {"en": "Live data not connected", "ar": "البيانات المباشرة غير متصلة", "tr": "Canlı veri bağlı değil"},
    "تصمیم‌گیری هوشمند، با کنترل کامل ریسک": {"en": "Intelligent decisions with full risk control", "ar": "قرارات ذكية مع تحكم كامل بالمخاطر", "tr": "Tam risk kontrolüyle akıllı kararlar"},
    "تحلیل چندلایه بازار و مدیریت سرمایه در یک فضای کاری یکپارچه": {"en": "Multi-layer market analysis and capital management in one workspace", "ar": "تحليل متعدد الطبقات للسوق وإدارة رأس المال في مساحة عمل موحدة", "tr": "Tek bir çalışma alanında çok katmanlı piyasa analizi ve sermaye yönetimi"},
    "● محیط آزمایشی · بدون اجرای سفارش": {"en": "● Demo environment · No order execution", "ar": "● بيئة تجريبية · لا يتم تنفيذ الأوامر", "tr": "● Demo ortamı · Emir yürütme yok"},
    "سرمایه فرضی": {"en": "Assumed balance", "ar": "الرصيد الافتراضي", "tr": "Varsayılan bakiye"},
    "برای محاسبات آزمایشی": {"en": "For simulation calculations", "ar": "لحسابات المحاكاة", "tr": "Simülasyon hesaplamaları için"},
    "ریسک هر معامله FX": {"en": "Risk per FX trade", "ar": "المخاطر لكل صفقة فوركس", "tr": "İşlem başına FX riski"},
    "طلا: 0.10%": {"en": "Gold: 0.10%", "ar": "الذهب: 0.10%", "tr": "Altın: %0,10"},
    "حد توقف زیان روزانه": {"en": "Daily loss limit", "ar": "حد الخسارة اليومي", "tr": "Günlük zarar limiti"},
    "محدودیت پیکربندی‌شده": {"en": "Configured limit", "ar": "الحد المحدد", "tr": "Yapılandırılmış sınır"},
    "اجرای معاملات": {"en": "Trade execution", "ar": "تنفيذ الصفقات", "tr": "İşlem yürütme"},
    "خاموش": {"en": "Off", "ar": "متوقف", "tr": "Kapalı"},
    "اتصال بروکر برقرار نیست": {"en": "Broker not connected", "ar": "الوسيط غير متصل", "tr": "Aracı kurum bağlı değil"},
    "نمای تحلیلی بازار": {"en": "Market analysis overview", "ar": "نظرة تحليلية على السوق", "tr": "Piyasa analiz görünümü"},
    "نمونه نمایشی": {"en": "Illustrative sample", "ar": "نموذج توضيحي", "tr": "Örnek görünüm"},
    "این نمودار صرفاً نمونه رابط کاربری است و از قیمت یا داده بازار دریافت نشده است.": {"en": "This chart is a UI illustration and is not based on live prices or market data.", "ar": "هذا الرسم توضيحي للواجهة ولا يعتمد على أسعار أو بيانات سوق مباشرة.", "tr": "Bu grafik yalnızca arayüz örneğidir; canlı fiyat veya piyasa verisi kullanmaz."},
    "وضعیت سیستم": {"en": "System status", "ar": "حالة النظام", "tr": "Sistem durumu"},
    "محیط امن": {"en": "Safe environment", "ar": "بيئة آمنة", "tr": "Güvenli ortam"},
    "موتور تحلیل": {"en": "Analysis engine", "ar": "محرك التحليل", "tr": "Analiz motoru"},
    "قابل استفاده در حالت آزمایشی": {"en": "Available in demo mode", "ar": "متاح في الوضع التجريبي", "tr": "Demo modunda kullanılabilir"},
    "آماده": {"en": "Ready", "ar": "جاهز", "tr": "Hazır"},
    "فیلتر اخبار": {"en": "News filter", "ar": "مرشح الأخبار", "tr": "Haber filtresi"},
    "منبع زنده متصل نیست": {"en": "No live source connected", "ar": "لا يوجد مصدر مباشر متصل", "tr": "Canlı kaynak bağlı değil"},
    "محدود": {"en": "Limited", "ar": "محدود", "tr": "Sınırlı"},
    "اتصال MT5": {"en": "MT5 connection", "ar": "اتصال MT5", "tr": "MT5 bağlantısı"},
    "اتصال برقرار نشده": {"en": "Not connected", "ar": "غير متصل", "tr": "Bağlı değil"},
    "قطع": {"en": "Offline", "ar": "غير متصل", "tr": "Çevrimdışı"},
    "اجرای سفارش": {"en": "Order execution", "ar": "تنفيذ الأوامر", "tr": "Emir yürütme"},
    "در این نسخه خاموش است": {"en": "Disabled in this version", "ar": "معطّل في هذا الإصدار", "tr": "Bu sürümde devre dışı"},
    "غیرفعال": {"en": "Disabled", "ar": "معطّل", "tr": "Devre dışı"},
    "در حال دریافت وضعیت...": {"en": "Loading system status...", "ar": "جارٍ تحميل حالة النظام...", "tr": "Sistem durumu yükleniyor..."},
    "کنترل اضطراری": {"en": "Emergency control", "ar": "التحكم في الطوارئ", "tr": "Acil durum kontrolü"},
    "دسترسی محدود به مدیر و معامله‌گر": {"en": "Restricted to admins and traders", "ar": "متاح للمسؤولين والمتداولين فقط", "tr": "Yalnızca yöneticiler ve yatırımcılar erişebilir"},
    "فعال‌سازی توقف اضطراری": {"en": "Activate emergency stop", "ar": "تفعيل الإيقاف الطارئ", "tr": "Acil durdurmayı etkinleştir"},
    "به‌روزرسانی وضعیت": {"en": "Refresh status", "ar": "تحديث الحالة", "tr": "Durumu yenile"},
    "سیگنال‌های معاملاتی": {"en": "Trading signals", "ar": "إشارات التداول", "tr": "İşlem sinyalleri"},
    "اتصال زنده موجود نیست": {"en": "Live connection unavailable", "ar": "الاتصال المباشر غير متاح", "tr": "Canlı bağlantı mevcut değil"},
    "پس از اتصال منبع داده و موتور تولید سیگنال، نقاط ورود، حد ضرر، اهداف سود و نسبت ریسک به بازده در این بخش نمایش داده می‌شوند.": {"en": "Entry, stop-loss, take-profit and risk/reward details will appear here once data and signal services are connected.", "ar": "ستظهر نقاط الدخول ووقف الخسارة وأهداف الربح ونسبة المخاطرة إلى العائد هنا بعد ربط البيانات ومحرك الإشارات.", "tr": "Veri kaynağı ve sinyal motoru bağlandığında giriş, zarar durdurma, kâr hedefleri ve risk/getiri oranı burada gösterilir."},
    "نمونه نمایشی، نه سیگنال واقعی": {"en": "Illustrative sample, not a live signal", "ar": "نموذج توضيحي وليس إشارة مباشرة", "tr": "Örnek gösterim; canlı sinyal değildir"},
    "بدون سیگنال زنده": {"en": "No live signal", "ar": "لا توجد إشارة مباشرة", "tr": "Canlı sinyal yok"},
    "منتظر اتصال بازار": {"en": "Waiting for market connection", "ar": "بانتظار اتصال السوق", "tr": "Piyasa bağlantısı bekleniyor"},
    "تحلیل چندتایم‌فریمی": {"en": "Multi-timeframe analysis", "ar": "تحليل متعدد الأطر الزمنية", "tr": "Çoklu zaman dilimi analizi"},
    "در انتظار داده بازار": {"en": "Awaiting market data", "ar": "بانتظار بيانات السوق", "tr": "Piyasa verisi bekleniyor"},
    "ساختار قیمت": {"en": "Price structure", "ar": "هيكل السعر", "tr": "Fiyat yapısı"},
    "مفاهیم نقدینگی و نواحی": {"en": "Liquidity and key zones", "ar": "مفاهيم السيولة والمناطق", "tr": "Likidite ve önemli bölgeler"},
    "رژیم بازار": {"en": "Market regime", "ar": "حالة السوق", "tr": "Piyasa rejimi"},
    "تشخیص روند و نوسان": {"en": "Trend and volatility detection", "ar": "تحديد الاتجاه والتقلب", "tr": "Trend ve oynaklık tespiti"},
    "تا زمان اتصال فید معتبر قیمت، هیچ تحلیل یا جهت بازار به‌عنوان نتیجه زنده ارائه نمی‌شود.": {"en": "No analysis or market direction is presented as live until a verified price feed is connected.", "ar": "لن يتم تقديم أي تحليل أو اتجاه للسوق على أنه مباشر قبل ربط مصدر أسعار موثوق.", "tr": "Doğrulanmış fiyat akışı bağlanana kadar hiçbir analiz veya piyasa yönü canlı sonuç olarak sunulmaz."},
    "شبیه‌ساز تصمیم": {"en": "Decision simulator", "ar": "محاكي القرار", "tr": "Karar simülatörü"},
    "آزمایشی": {"en": "Demo", "ar": "تجريبي", "tr": "Deneme"},
    "این ابزار صرفاً منطق محافظتی را در شرایط نمونه نشان می‌دهد.": {"en": "This tool demonstrates protective logic under illustrative conditions only.", "ar": "تعرض هذه الأداة منطق الحماية في ظروف افتراضية فقط.", "tr": "Bu araç yalnızca örnek koşullarda koruma mantığını gösterir."},
    "اجرای پیش‌نمایش": {"en": "Run preview", "ar": "تشغيل المعاينة", "tr": "Önizlemeyi çalıştır"},
    "برای شروع، نماد را انتخاب کنید.": {"en": "Select a symbol to begin.", "ar": "اختر رمزاً للبدء.", "tr": "Başlamak için bir sembol seçin."},
    "ماژول‌های هوش مصنوعی": {"en": "AI modules", "ar": "وحدات الذكاء الاصطناعي", "tr": "Yapay zekâ modülleri"},
    "نمای معماری": {"en": "Architecture overview", "ar": "نظرة على البنية", "tr": "Mimari görünüm"},
    "اسکن نمادها و شرایط بازار": {"en": "Scan symbols and market conditions", "ar": "مسح الرموز وظروف السوق", "tr": "Sembolleri ve piyasa koşullarını tarar"},
    "فیلتر رویدادهای خبری": {"en": "Filter news events", "ar": "تصفية الأحداث الإخبارية", "tr": "Haber olaylarını filtreler"},
    "انتخاب رژیم و استراتژی": {"en": "Regime and strategy selection", "ar": "اختيار حالة السوق والاستراتيجية", "tr": "Rejim ve strateji seçimi"},
    "ترکیب مدل‌های تحلیلی": {"en": "Combine analytical models", "ar": "دمج النماذج التحليلية", "tr": "Analiz modellerini birleştirir"},
    "مدیریت خروج و اهداف": {"en": "Exit and target management", "ar": "إدارة الخروج والأهداف", "tr": "Çıkış ve hedef yönetimi"},
    "کنترل سرمایه و محدودیت‌ها": {"en": "Capital and risk controls", "ar": "ضوابط رأس المال والمخاطر", "tr": "Sermaye ve risk kontrolleri"},
    "مدیر سیستم": {"en": "System administrator", "ar": "مسؤول النظام", "tr": "Sistem yöneticisi"},
    "رمز حداقل ۱۴ نویسه": {"en": "Password (at least 14 characters)", "ar": "كلمة مرور (14 حرفاً على الأقل)", "tr": "Şifre (en az 14 karakter)"},
    "معامله‌گر": {"en": "Trader", "ar": "متداول", "tr": "Yatırımcı"},
    "تحلیل‌گر": {"en": "Analyst", "ar": "محلل", "tr": "Analist"},
    "فقط مشاهده": {"en": "Viewer", "ar": "مشاهدة فقط", "tr": "Yalnızca görüntüleme"},
    "ایجاد کاربر": {"en": "Create user", "ar": "إنشاء مستخدم", "tr": "Kullanıcı oluştur"},
    "Forex AI Hybrid Scalper · ابزار تحلیلی و آموزشی. داده زنده، تقویم اقتصادی معتبر، اتصال بروکر و ارسال سفارش در این نسخه فعال نیست. نمودارها و مقادیر نمونه صرفاً برای نمایش رابط کاربری هستند. معامله‌گری ریسک بالایی دارد.": {"en": "Forex AI Hybrid Scalper · Analytical and educational tool. Live data, a verified economic calendar, broker connection and order submission are not enabled in this version. Charts and sample values are illustrative only. Trading involves substantial risk.", "ar": "Forex AI Hybrid Scalper · أداة تحليلية وتعليمية. البيانات المباشرة والتقويم الاقتصادي الموثوق والاتصال بالوسيط وإرسال الأوامر غير مفعّلة في هذا الإصدار. الرسوم والقيم المعروضة توضيحية فقط. التداول ينطوي على مخاطر كبيرة.", "tr": "Forex AI Hybrid Scalper · Analitik ve eğitim amaçlı araç. Canlı veri, doğrulanmış ekonomik takvim, aracı kurum bağlantısı ve emir gönderimi bu sürümde etkin değildir. Grafikler ve örnek değerler yalnızca gösterim amaçlıdır. İşlem yapmak yüksek risk içerir."},
    "ورود ناموفق بود": {"en": "Sign-in failed", "ar": "فشل تسجيل الدخول", "tr": "Giriş başarısız"},
    "حساب مدیر را وارد کنید.": {"en": "Enter administrator credentials.", "ar": "أدخل بيانات المسؤول.", "tr": "Yönetici bilgilerini girin."},
    "نقش: ": {"en": "Role: ", "ar": "الدور: ", "tr": "Rol: "},
    "توقف اضطراری: ": {"en": "Emergency stop: ", "ar": "الإيقاف الطارئ: ", "tr": "Acil durdurma: "},
    "فعال": {"en": "Active", "ar": "نشط", "tr": "Etkin"},
    "غیرفعال": {"en": "Inactive", "ar": "غير نشط", "tr": "Etkin değil"},
    "فیلتر خبر: ": {"en": "News filter: ", "ar": "مرشح الأخبار: ", "tr": "Haber filtresi: "},
    "روشن": {"en": "On", "ar": "مفعّل", "tr": "Açık"},
    "خاموش": {"en": "Off", "ar": "متوقف", "tr": "Kapalı"},
    "متصل نیست": {"en": "Not connected", "ar": "غير متصل", "tr": "Bağlı değil"},
    "اجرای واقعی: غیرفعال": {"en": "Live execution: Disabled", "ar": "التنفيذ الحقيقي: معطّل", "tr": "Canlı işlem: Devre dışı"},
    "وضعیت سرویس دریافت نشد: ": {"en": "Could not retrieve service status: ", "ar": "تعذّر جلب حالة الخدمة: ", "tr": "Hizmet durumu alınamadı: "},
    "قفل توقف اضطراری فعال شد.": {"en": "Emergency stop latch activated.", "ar": "تم تفعيل قفل الإيقاف الطارئ.", "tr": "Acil durdurma kilidi etkinleştirildi."},
    "خطا: ": {"en": "Error: ", "ar": "خطأ: ", "tr": "Hata: "},
    "رژیم: ": {"en": "Regime: ", "ar": "حالة السوق: ", "tr": "Rejim: "},
    "استراتژی: ": {"en": "Strategy: ", "ar": "الاستراتيجية: ", "tr": "Strateji: "},
    "مجوز اجرا: خیر": {"en": "Execution allowed: No", "ar": "السماح بالتنفيذ: لا", "tr": "İşleme izin verildi: Hayır"},
    "پیش‌نمایش غیرزنده": {"en": "Non-live preview", "ar": "معاينة غير مباشرة", "tr": "Canlı olmayan önizleme"},
    "پیش‌نمایش در دسترس نیست: ": {"en": "Preview unavailable: ", "ar": "المعاينة غير متاحة: ", "tr": "Önizleme kullanılamıyor: "},

    "admin": {"en": "Administrator", "ar": "مسؤول", "tr": "Yönetici"},
    "trader": {"en": "Trader", "ar": "متداول", "tr": "Yatırımcı"},
    "analyst": {"en": "Analyst", "ar": "محلل", "tr": "Analist"},
    "viewer": {"en": "Viewer", "ar": "مشاهد", "tr": "Görüntüleyici"},
    "Authentication required.": {"en": "Authentication required.", "ar": "يلزم تسجيل الدخول.", "tr": "Kimlik doğrulaması gerekli."},
    "Insufficient role permissions.": {"en": "Your role does not have permission.", "ar": "لا تملك صلاحية كافية.", "tr": "Rolünüzün gerekli izni yok."},
    "Invalid CSRF token.": {"en": "Invalid security token. Refresh and try again.", "ar": "رمز الأمان غير صالح. حدّث الصفحة وحاول مجدداً.", "tr": "Güvenlik belirteci geçersiz. Yenileyip tekrar deneyin."},
    "Invalid username or password.": {"en": "Invalid username or password.", "ar": "اسم المستخدم أو كلمة المرور غير صحيحة.", "tr": "Kullanıcı adı veya şifre hatalı."},
    "User not found.": {"en": "User not found.", "ar": "المستخدم غير موجود.", "tr": "Kullanıcı bulunamadı."},
    "Administrators cannot deactivate their own account.": {"en": "Administrators cannot deactivate their own account.", "ar": "لا يمكن للمسؤول تعطيل حسابه بنفسه.", "tr": "Yöneticiler kendi hesaplarını devre dışı bırakamaz."},
    "The last active administrator cannot be deactivated.": {"en": "The last active administrator cannot be deactivated.", "ar": "لا يمكن تعطيل آخر مسؤول نشط.", "tr": "Son etkin yönetici devre dışı bırakılamaz."},
    "نامعتبر": {"en": "Invalid", "ar": "غير صالح", "tr": "Geçersiz"},
    "خبر": {"en": "News", "ar": "الأخبار", "tr": "Haberler"},
    "اخبار": {"en": "News", "ar": "الأخبار", "tr": "Haberler"},
    "منبع": {"en": "Source", "ar": "المصدر", "tr": "Kaynak"},
    "اهمیت": {"en": "Impact", "ar": "الأهمية", "tr": "Etki"},
    "احساسات بازار": {"en": "Market sentiment", "ar": "معنويات السوق", "tr": "Piyasa duyarlılığı"},
    "خلاصه": {"en": "Summary", "ar": "الملخص", "tr": "Özet"},
    "تحلیل خبر": {"en": "News analysis", "ar": "تحليل الخبر", "tr": "Haber analizi"},
    "زمان انتشار": {"en": "Published", "ar": "وقت النشر", "tr": "Yayın zamanı"},
    "دسته‌بندی": {"en": "Category", "ar": "الفئة", "tr": "Kategori"},
    "همه اخبار": {"en": "All news", "ar": "كل الأخبار", "tr": "Tüm haberler"},
    "تازه‌ترین اخبار بازار": {"en": "Latest market news", "ar": "أحدث أخبار السوق", "tr": "En son piyasa haberleri"},
    "نبض خبری بازار": {"en": "Market news pulse", "ar": "نبض أخبار السوق", "tr": "Piyasa haber akışı"},
    "مثبت": {"en": "Positive", "ar": "إيجابي", "tr": "Pozitif"},
    "خنثی": {"en": "Neutral", "ar": "محايد", "tr": "Nötr"},
    "منفی": {"en": "Negative", "ar": "سلبي", "tr": "Negatif"},

    "خبرها": {"en": "News", "ar": "الأخبار", "tr": "Haberler"},
    "اخبار بازار": {"en": "Market News", "ar": "أخبار السوق", "tr": "Piyasa Haberleri"},
    "جستجو در خبرها": {"en": "Search news", "ar": "ابحث في الأخبار", "tr": "Haberlerde ara"},
    "همه دسته‌ها": {"en": "All categories", "ar": "كل الفئات", "tr": "Tüm kategoriler"},
    "همه اهمیت‌ها": {"en": "All impact levels", "ar": "كل مستويات الأهمية", "tr": "Tüm etki düzeyleri"},
    "زیاد": {"en": "High", "ar": "مرتفع", "tr": "Yüksek"},
    "متوسط": {"en": "Medium", "ar": "متوسط", "tr": "Orta"},
    "کم": {"en": "Low", "ar": "منخفض", "tr": "Düşük"},
    "هنوز منبع خبری متصل نشده است.": {"en": "No news provider is connected yet.", "ar": "لم يتم ربط مزود أخبار بعد.", "tr": "Henüz bir haber sağlayıcısı bağlanmadı."},
    "پس از اتصال منبع معتبر، خبرها همراه با تیتر، خلاصه، تحلیل، زمان انتشار، منبع و احساسات بازار نمایش داده می‌شوند.": {"en": "After a verified provider is connected, articles will appear with headline, summary, analysis, publication time, source and market sentiment.", "ar": "بعد ربط مزود موثوق، ستظهر الأخبار مع العنوان والملخص والتحليل ووقت النشر والمصدر ومعنويات السوق.", "tr": "Doğrulanmış bir sağlayıcı bağlandığında haberler başlık, özet, analiz, yayın zamanı, kaynak ve piyasa duyarlılığıyla gösterilecektir."},
    "تعداد خبرهای در دسترس": {"en": "Available articles", "ar": "الأخبار المتاحة", "tr": "Mevcut haberler"},
    "فید خبری": {"en": "News feed", "ar": "موجز الأخبار", "tr": "Haber akışı"},
    "متصل نیست": {"en": "Not connected", "ar": "غير متصل", "tr": "Bağlı değil"},
    "مشاهده منبع": {"en": "View source", "ar": "عرض المصدر", "tr": "Kaynağı görüntüle"},
    "غیرفعال‌کردن": {"en": "Deactivate", "ar": "تعطيل", "tr": "Devre dışı bırak"},
    "فعال‌کردن": {"en": "Activate", "ar": "تفعيل", "tr": "Etkinleştir"},
    "مشاهده منبع": {"en": "View source", "ar": "عرض المصدر", "tr": "Kaynağı görüntüle"},
    "استراتژی: ": {"en": "Strategy: ", "ar": "الاستراتيجية: ", "tr": "Strateji: "},
    "Username must be 3-64 letters, digits, '_' or '-'.": {"en": "Username must be 3-64 letters, digits, '_' or '-'.", "ar": "يجب أن يتكون اسم المستخدم من 3 إلى 64 حرفاً أو رقماً أو _ أو -.", "tr": "Kullanıcı adı 3-64 harf, rakam, '_' veya '-' içermelidir."},
    "New accounts may be trader, analyst or viewer. Bootstrap admin separately.": {"en": "New accounts may be trader, analyst or viewer. Bootstrap admin separately.", "ar": "يمكن أن تكون الحسابات الجديدة متداولاً أو محللاً أو مشاهداً. أنشئ المسؤول الأول بشكل منفصل.", "tr": "Yeni hesaplar yatırımcı, analist veya görüntüleyici olabilir. Yönetici hesabını ayrı oluşturun."},
    "Password must contain at least 14 characters.": {"en": "Password must contain at least 14 characters.", "ar": "يجب ألا تقل كلمة المرور عن 14 حرفاً.", "tr": "Şifre en az 14 karakter içermelidir."},
    "Username already exists.": {"en": "Username already exists.", "ar": "اسم المستخدم موجود بالفعل.", "tr": "Kullanıcı adı zaten mevcut."},
    "Symbol is not in the configured universe.": {"en": "Symbol is not in the configured universe.", "ar": "الرمز غير مدرج ضمن قائمة الأدوات المحددة.", "tr": "Sembol yapılandırılmış enstrüman listesinde değil."},
    "خبرهای تأییدشده": {"en": "Verified articles", "ar": "الأخبار الموثوقة", "tr": "Doğrulanmış haberler"},
    "تیتر": {"en": "Headline", "ar": "العنوان", "tr": "Başlık"},
    "تحلیل": {"en": "Analysis", "ar": "التحليل", "tr": "Analiz"},
    "منبع خبری": {"en": "News provider", "ar": "مزود الأخبار", "tr": "Haber sağlayıcısı"},
}
ALIASES = {"fa": {}, "en": {}, "ar": {}, "tr": {}}
for _source, _translations in CATALOG.items():
    for _locale, _translated in _translations.items():
        ALIASES[_locale][_translated] = _source


def normalize_locale(value: str | None) -> str:
    candidate = (value or "").strip().lower().replace("_", "-").split("-", 1)[0]
    return candidate if candidate in SUPPORTED_LOCALES else DEFAULT_LOCALE


def is_rtl(locale: str) -> bool:
    return normalize_locale(locale) in RTL_LOCALES


def catalog_for_frontend() -> dict:
    return deepcopy(CATALOG)


def translate(text: str, locale: str | None = None) -> str:
    lang = normalize_locale(locale)
    if lang == DEFAULT_LOCALE:
        return text
    if text in CATALOG:
        return CATALOG[text].get(lang, text)
    source = ALIASES.get(lang, {}).get(text)
    return CATALOG[source][lang] if source else text
