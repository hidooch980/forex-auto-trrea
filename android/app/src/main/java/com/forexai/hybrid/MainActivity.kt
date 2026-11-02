package com.forexai.hybrid

import android.app.Activity
import android.app.AlertDialog
import android.app.DownloadManager
import android.content.*
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.provider.Settings
import android.webkit.*
import android.widget.*
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : Activity() {
    private lateinit var web: WebView
    private lateinit var status: TextView
    private val prefs by lazy { getSharedPreferences("forexai", MODE_PRIVATE) }
    private val owner = "hidooch980"
    private val repo = "forex-auto-trrea"
    private var pendingDownload = -1L

    private val downloadReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID, -1L) != pendingDownload) return
            val manager = getSystemService(DOWNLOAD_SERVICE) as DownloadManager
            val uri = manager.getUriForDownloadedFile(pendingDownload)
            if (uri == null) { status.text = "دریافت APK ناموفق بود؛ دوباره تلاش کن."; return }
            installDownloaded(uri)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        buildScreen()
        val filter = IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE)
        if (android.os.Build.VERSION.SDK_INT >= 33) registerReceiver(downloadReceiver, filter, Context.RECEIVER_EXPORTED)
        else registerReceiver(downloadReceiver, filter)
        val base = prefs.getString("base_url", null)
        if (base.isNullOrBlank()) showServerDialog() else loadServer(base)
        checkForUpdate()
    }

    private fun buildScreen() {
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(0xFF0B1020.toInt()) }
        val bar = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(14, 12, 14, 12); gravity = android.view.Gravity.CENTER_VERTICAL }
        val title = TextView(this).apply { text = "FOREX AI"; textSize = 18f; setTextColor(0xFF54DDB0.toInt()) }
        val settings = Button(this).apply { text = "تنظیم سرور"; setOnClickListener { showServerDialog() } }
        val update = Button(this).apply { text = "بررسی آپدیت"; setOnClickListener { checkForUpdate() } }
        bar.addView(title, LinearLayout.LayoutParams(0, -2, 1f)); bar.addView(settings); bar.addView(update)
        status = TextView(this).apply { text = "آماده"; textSize = 12f; setTextColor(0xFFB9C5D8.toInt()); setPadding(16, 4, 16, 8) }
        web = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.allowFileAccess = false
            settings.allowContentAccess = false
            settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            settings.javaScriptCanOpenWindowsAutomatically = false
            settings.setSupportMultipleWindows(false)
            if (android.os.Build.VERSION.SDK_INT >= 26) settings.safeBrowsingEnabled = true
            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                    val uri = request?.url ?: return false
                    val current = Uri.parse(prefs.getString("base_url", "") ?: "")
                    if (uri.scheme != "https") {
                        status.text = "برای امنیت، فقط پیوند HTTPS باز می‌شود."
                        return true
                    }
                    if (uri.host == current.host && uri.scheme == current.scheme) return false
                    startActivity(Intent(Intent.ACTION_VIEW, uri)); return true
                }
                override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: WebResourceError?) {
                    if (request?.isForMainFrame == true) status.text = "اتصال به سایت برقرار نشد؛ آدرس سرور را بررسی کن."
                }
                override fun onPageFinished(view: WebView?, url: String?) { status.text = "اتصال وب برقرار است" }
            }
        }
        root.addView(bar); root.addView(status); root.addView(web, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(root)
    }

    private fun showServerDialog() {
        val input = EditText(this).apply {
            hint = "https://your-domain.example"; setSingleLine(true)
            setText(prefs.getString("base_url", ""))
            inputType = android.text.InputType.TYPE_TEXT_VARIATION_URI
        }
        AlertDialog.Builder(this).setTitle("آدرس امن وب‌سایت")
            .setMessage("آدرس HTTPS وب‌سایت Forex AI را وارد کن. رمز MT5 را اینجا وارد نکن.")
            .setView(input).setPositiveButton("ذخیره و اتصال") { _, _ ->
                val value = input.text.toString().trim().trimEnd('/')
                val uri = runCatching { Uri.parse(value) }.getOrNull()
                if (uri?.scheme != "https" || uri.host.isNullOrBlank()) status.text = "فقط آدرس معتبر HTTPS پذیرفته می‌شود."
                else { prefs.edit().putString("base_url", value).apply(); loadServer(value) }
            }.setNegativeButton("بعداً", null).show()
    }

    private fun loadServer(base: String) { web.loadUrl("$base/app") }

    private fun checkForUpdate() {
        status.text = "در حال بررسی نسخه جدید…"
        Thread {
            try {
                val connection = (URL("https://api.github.com/repos/$owner/$repo/releases/latest").openConnection() as HttpURLConnection).apply {
                    connectTimeout = 10000; readTimeout = 10000
                    setRequestProperty("Accept", "application/vnd.github+json")
                    setRequestProperty("User-Agent", "ForexAI-Android")
                }
                val body = connection.inputStream.bufferedReader().use { it.readText() }; connection.disconnect()
                val release = JSONObject(body)
                val tag = release.optString("tag_name").removePrefix("v")
                val assets = release.optJSONArray("assets")
                var apkUrl: String? = null
                if (assets != null) for (i in 0 until assets.length()) {
                    val asset = assets.getJSONObject(i)
                    val candidate = Uri.parse(asset.optString("browser_download_url"))
                    if (asset.optString("name") == "forex-ai-release.apk" &&
                        candidate.scheme == "https" && candidate.host == "github.com") {
                        apkUrl = candidate.toString()
                    }
                }
                val latest = tag.split(".").mapNotNull { it.toIntOrNull() }
                val current = BuildConfig.VERSION_NAME.removeSuffix("-debug").split(".").mapNotNull { it.toIntOrNull() }
                val newer = compareVersions(latest, current) > 0
                runOnUiThread {
                    if (newer && !apkUrl.isNullOrBlank()) {
                        status.text = "نسخه $tag آماده است."
                        AlertDialog.Builder(this).setTitle("به‌روزرسانی Forex AI")
                            .setMessage("نسخه $tag منتشر شده است. فایل APK رسمی دریافت شود؟")
                            .setPositiveButton("دریافت") { _, _ -> downloadUpdate(apkUrl!!) }
                            .setNegativeButton("بعداً", null).show()
                    } else status.text = "برنامه به‌روز است."
                }
            } catch (_: Exception) { runOnUiThread { status.text = "بررسی آپدیت انجام نشد؛ اینترنت را بررسی کن." } }
        }.start()
    }

    private fun compareVersions(a: List<Int>, b: List<Int>): Int {
        for (i in 0 until maxOf(a.size, b.size)) {
            val x = a.getOrElse(i) { 0 }; val y = b.getOrElse(i) { 0 }
            if (x != y) return x.compareTo(y)
        }
        return 0
    }

    private fun downloadUpdate(url: String) {
        try {
            val request = DownloadManager.Request(Uri.parse(url)).setTitle("Forex AI update")
                .setDescription("دریافت نسخه امضاشده برنامه")
                .setMimeType("application/vnd.android.package-archive")
                .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                .setDestinationInExternalFilesDir(this, Environment.DIRECTORY_DOWNLOADS, "forex-ai-update.apk")
            pendingDownload = (getSystemService(DOWNLOAD_SERVICE) as DownloadManager).enqueue(request)
            status.text = "دریافت نسخه جدید آغاز شد…"
        } catch (_: Exception) { status.text = "امکان دریافت فایل به‌روزرسانی وجود ندارد." }
    }

    private fun installDownloaded(uri: Uri) {
        if (android.os.Build.VERSION.SDK_INT >= 26 && !packageManager.canRequestPackageInstalls()) {
            startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName")))
            status.text = "اجازه نصب از این منبع را فعال کن و دوباره آپدیت را بررسی کن."; return
        }
        startActivity(Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        })
    }

    override fun onDestroy() {
        runCatching { unregisterReceiver(downloadReceiver) }; web.destroy(); super.onDestroy()
    }
}
