package com.a67.pslauncher;

import android.app.Activity;
import android.os.UserHandle;
import android.os.SystemClock;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewTreeObserver;

import java.lang.reflect.Method;
import java.util.WeakHashMap;

public final class PrivateProfileViewFilter implements ViewTreeObserver.OnGlobalLayoutListener {
    private final Activity activity;
    private final View root;
    private final int privateUserId;
    private final Class<?> itemInfoClass;
    private final Method getUserMethod;
    private final WeakHashMap<View, Boolean> hiddenByUs = new WeakHashMap<>();
    private long lastRun;

    private PrivateProfileViewFilter(Activity activity, int privateUserId) throws Exception {
        this.activity = activity;
        this.privateUserId = privateUserId;
        this.root = activity.getWindow().getDecorView();
        ClassLoader cl = activity.getClassLoader();
        this.itemInfoClass = Class.forName(
                "com.android.launcher3.model.data.ItemInfo", false, cl);
        this.getUserMethod = itemInfoClass.getMethod("getUser");
    }

    public static void install(Activity activity, int privateUserId) {
        if (activity == null) return;
        activity.runOnUiThread(() -> {
            try {
                PrivateProfileViewFilter filter =
                        new PrivateProfileViewFilter(activity, privateUserId);
                filter.root.getViewTreeObserver().addOnGlobalLayoutListener(filter);
                filter.applyNow();
                // Keep a strong reference for the Activity lifetime.
                filter.root.setTag(
                        android.R.id.custom, filter);
            } catch (Throwable t) {
                android.util.Log.e("A67PrivateSpace",
                        "launcher filter install failed", t);
            }
        });
    }

    @Override
    public void onGlobalLayout() {
        long now = SystemClock.uptimeMillis();
        if (now - lastRun < 80) return;
        lastRun = now;
        applyNow();
    }

    private void applyNow() {
        try {
            filterRecursive(root);
        } catch (Throwable t) {
            android.util.Log.e("A67PrivateSpace",
                    "launcher filter pass failed", t);
        }
    }

    private void filterRecursive(View view) throws Exception {
        Object tag = view.getTag();

        if (tag != null && itemInfoClass.isInstance(tag)) {
            UserHandle user = (UserHandle) getUserMethod.invoke(tag);
            int id = user != null ? user.hashCode() : -1;

            if (id == privateUserId) {
                if (view.getVisibility() != View.GONE) {
                    view.setVisibility(View.GONE);
                }
                hiddenByUs.put(view, Boolean.TRUE);
            } else if (hiddenByUs.remove(view) != null) {
                view.setVisibility(View.VISIBLE);
            }
        }

        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int i = 0; i < group.getChildCount(); i++) {
                filterRecursive(group.getChildAt(i));
            }
        }
    }
}
