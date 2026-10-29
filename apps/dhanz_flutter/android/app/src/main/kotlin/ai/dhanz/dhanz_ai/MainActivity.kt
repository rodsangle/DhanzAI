package ai.dhanz.dhanz_ai

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.core.app.ActivityCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * Push notifications bridge for `lib/core/platform/push.dart` (channel `ai.dhanz/push`).
 *
 * Firebase is only active when `android/app/google-services.json` was present at build time;
 * without it `getToken` returns null and the app simply works without notifications.
 */
class MainActivity : FlutterActivity() {
    private var pendingPermission: MethodChannel.Result? = null
    private var launchNotification: Map<String, String>? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        createNotificationChannel()
        launchNotification = intent?.let(::notificationData)
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        val ch = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)
        channel = ch
        ch.setMethodCallHandler { call, result ->
            when (call.method) {
                "requestPermission" -> requestPermission(result)
                "getToken" -> getToken(result)
                "initialNotification" -> {
                    result.success(launchNotification)
                    launchNotification = null
                }
                else -> result.notImplemented()
            }
        }
    }

    override fun cleanUpFlutterEngine(flutterEngine: FlutterEngine) {
        channel = null
        super.cleanUpFlutterEngine(flutterEngine)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        notificationData(intent)?.let { channel?.invokeMethod("onNotificationTap", it) }
    }

    /** The notification's data keys we route on (FCM puts message data in the launch intent's extras). */
    private fun notificationData(intent: Intent): Map<String, String>? {
        val data = NOTIFICATION_KEYS.mapNotNull { key -> intent.getStringExtra(key)?.let { key to it } }.toMap()
        return data.ifEmpty { null }
    }

    private fun getToken(result: MethodChannel.Result) {
        if (FirebaseApp.getApps(this).isEmpty()) {
            result.success(null) // built without google-services.json
            return
        }
        FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
            result.success(if (task.isSuccessful) task.result else null)
        }
    }

    private fun requestPermission(result: MethodChannel.Result) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            result.success(NotificationManagerCompat.from(this).areNotificationsEnabled())
            return
        }
        pendingPermission?.success(false)
        pendingPermission = result
        ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), PERMISSION_REQUEST)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != PERMISSION_REQUEST) return
        pendingPermission?.success(grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED)
        pendingPermission = null
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(REPLIES_CHANNEL, "Finished answers", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "Tells you when Dhanz finished an answer while the app was in the background"
            },
        )
    }

    companion object {
        const val CHANNEL = "ai.dhanz/push"
        const val REPLIES_CHANNEL = "dhanz_replies" // must match the backend (app/services/push.py)
        const val EXTRA_CONVERSATION = "conversation_id"
        const val EXTRA_REMINDER = "reminder_id"
        val NOTIFICATION_KEYS = listOf(EXTRA_CONVERSATION, EXTRA_REMINDER)
        private const val PERMISSION_REQUEST = 4242

        /** Set while the Flutter UI is running, so the messaging service can forward new tokens. */
        @Volatile
        var channel: MethodChannel? = null
    }
}
