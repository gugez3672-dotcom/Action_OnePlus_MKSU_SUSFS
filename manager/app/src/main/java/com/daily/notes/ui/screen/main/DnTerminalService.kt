package com.daily.notes.ui.screen.main

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import android.os.Build
import android.os.PowerManager
import androidx.core.content.ContextCompat
import com.daily.notes.R
import com.daily.notes.ui.HomeActivity

/** Owns PTY streams across Activity recreation and removal from Recents. */
internal object DnTerminalLifetime {
    private var instance: DnPtyTerminalController? = null
    fun controller(context: Context, daemon: String): DnPtyTerminalController =
        instance ?: DnPtyTerminalController(context.applicationContext, daemon).also { instance = it }
    fun closeOrdinary() { instance?.closeOrdinary() }
}

class DnTerminalService : Service() {
    private var wakeLock: PowerManager.WakeLock? = null

    override fun onCreate() {
        super.onCreate()
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL, getString(R.string.dn_terminal_channel), NotificationManager.IMPORTANCE_LOW))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val count = intent?.getIntExtra(COUNT, 0) ?: 0
        val pending = PendingIntent.getActivity(this, 8401,
            Intent(this, HomeActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notification = Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(getString(R.string.dn_terminal_notification, count))
            .setContentText(getString(R.string.dn_terminal_notification_hint))
            .setContentIntent(pending).setOngoing(true).setOnlyAlertOnce(true).build()
        if (Build.VERSION.SDK_INT >= 34)
            startForeground(8401, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        else startForeground(8401, notification)
        if (intent?.getBooleanExtra(WAKE, false) == true) {
            if (wakeLock == null) wakeLock = getSystemService(PowerManager::class.java)
                .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "$packageName:terminal")
            if (wakeLock?.isHeld != true) wakeLock?.acquire(30 * 60 * 1000L)
        } else releaseWakeLock()
        return START_NOT_STICKY
    }

    private fun releaseWakeLock() { if (wakeLock?.isHeld == true) wakeLock?.release() }
    override fun onDestroy() { releaseWakeLock(); super.onDestroy() }
    override fun onBind(intent: Intent?): IBinder? = null
    override fun onTaskRemoved(rootIntent: Intent?) { DnTerminalLifetime.closeOrdinary() }

    companion object {
        private const val CHANNEL = "daily_notes_terminal"
        private const val COUNT = "session_count"
        private const val WAKE = "keep_awake"
        fun sync(context: Context, count: Int, wake: Boolean) {
            val intent = Intent(context, DnTerminalService::class.java)
            if (count == 0) context.stopService(intent)
            else ContextCompat.startForegroundService(context, intent.putExtra(COUNT, count).putExtra(WAKE, wake))
        }
    }
}
