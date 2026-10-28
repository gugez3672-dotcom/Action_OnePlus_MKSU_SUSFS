package com.daily.notes.runtime;

import static com.daily.notes.runtime.StartupPreload.TAG;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

import com.daily.notes.ui.util.RuntimeCliKt;

public class BootReceiver extends BroadcastReceiver {

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null) {
            return;
        }
        var action = intent.getAction();
        if (!Intent.ACTION_LOCKED_BOOT_COMPLETED.equals(action)
                && !Intent.ACTION_BOOT_COMPLETED.equals(action)
                && !"com.daily.notes.runtime.START".equals(action)) {
            return;
        }
        if (RuntimeCliKt.rootAvailable()) return;
        try {
            context.startService(new Intent(context, BootstrapService.class));
            Log.i(TAG, "BootstrapService started from boot action: " + action);
        } catch (Throwable e) {

            Log.e(TAG, "Failed to start BootstrapService from boot action: " + action, e);
        }
    }
}
