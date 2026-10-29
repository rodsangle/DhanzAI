package ai.dhanz.dhanz_ai

import android.app.PendingIntent
import android.content.Intent
import android.os.Handler
import android.os.Looper
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

/**
 * Receives FCM messages. In the background Android shows the notification itself (and a tap opens
 * MainActivity with the data as extras); in the foreground it arrives here and is shown by us.
 */
class DhanzMessagingService : FirebaseMessagingService() {
    override fun onNewToken(token: String) {
        Handler(Looper.getMainLooper()).post { MainActivity.channel?.invokeMethod("onToken", token) }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val notification = message.notification ?: return
        val key = message.data[MainActivity.EXTRA_CONVERSATION] ?: message.data[MainActivity.EXTRA_REMINDER]
        val intent = Intent(this, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            for (name in MainActivity.NOTIFICATION_KEYS) {
                message.data[name]?.let { putExtra(name, it) }
            }
        }
        val pending = PendingIntent.getActivity(
            this,
            key.hashCode(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val built = NotificationCompat.Builder(this, MainActivity.REPLIES_CHANNEL)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(notification.title)
            .setContentText(notification.body)
            .setAutoCancel(true)
            .setContentIntent(pending)
            .build()
        if (NotificationManagerCompat.from(this).areNotificationsEnabled()) {
            try {
                NotificationManagerCompat.from(this).notify(key.hashCode(), built)
            } catch (_: SecurityException) {
                // permission revoked between the check and the call
            }
        }
    }
}
