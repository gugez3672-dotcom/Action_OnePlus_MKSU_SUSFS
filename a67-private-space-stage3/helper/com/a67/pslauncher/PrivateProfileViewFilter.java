package com.a67.pslauncher;

import android.app.Activity;
import android.app.Application;
import android.os.Bundle;
import android.os.SystemClock;
import android.os.UserHandle;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewTreeObserver;

import java.lang.reflect.Method;
import java.util.IdentityHashMap;
import java.util.Map;
import java.util.WeakHashMap;

public final class PrivateProfileViewFilter implements ViewTreeObserver.OnGlobalLayoutListener {
    private static final Map<Activity, PrivateProfileViewFilter> FILTERS =
            new IdentityHashMap<>();
    private static boolean lifecycleRegistered;
    private static int targetUserId;

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
                targetUserId = privateUserId;

                if (!lifecycleRegistered) {
                    activity.getApplication().registerActivityLifecycleCallbacks(
                            new Application.ActivityLifecycleCallbacks() {
                                @Override
                                public void onActivityCreated(Activity a, Bundle state) {
                                    attachIfLauncher(a);
                                }

                                @Override
                                public void onActivityResumed(Activity a) {
                                    attachIfLauncher(a);
                                    PrivateProfileViewFilter f = FILTERS.get(a);
                                    if (f != null) f.applyNow();
                                }

                                @Override
                                public void onActivityDestroyed(Activity a) {
                                    PrivateProfileViewFilter f = FILTERS.remove(a);
                                    if (f != null) f.detach();
                                }

                                @Override public void onActivityStarted(Activity a) {}
                                @Override public void onActivityPaused(Activity a) {}
                                @Override public void onActivityStopped(Activity a) {}
                                @Override public void onActivitySaveInstanceState(
                                        Activity a, Bundle state) {}
                            });
                    lifecycleRegistered = true;
                }

                attachIfLauncher(activity);
            } catch (Throwable t) {
                android.util.Log.e("A67PrivateSpace",
                        "launcher filter install failed", t);
            }
        });
    }

    private static void attachIfLauncher(Activity activity) {
        try {
            if (FILTERS.containsKey(activity)) return;

            ClassLoader cl = activity.getClassLoader();
            Class<?> launcherClass = Class.forName(
                    "com.android.launcher3.Launcher", false, cl);
            if (!launcherClass.isInstance(activity)) return;

            PrivateProfileViewFilter filter =
                    new PrivateProfileViewFilter(activity, targetUserId);
            FILTERS.put(activity, filter);
            filter.root.getViewTreeObserver().addOnGlobalLayoutListener(filter);
            filter.applyNow();

            android.util.Log.i("A67PrivateSpace",
                    "launcher visual filter attached: " + activity.getClass().getName());
        } catch (Throwable t) {
            android.util.Log.e("A67PrivateSpace",
                    "attach launcher visual filter failed", t);
        }
    }

    private void detach() {
        try {
            ViewTreeObserver observer = root.getViewTreeObserver();
            if (observer.isAlive()) {
                observer.removeOnGlobalLayoutListener(this);
            }
        } catch (Throwable ignored) {
        }
        hiddenByUs.clear();
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
            // On Android, UserHandle.hashCode() is the integer user identifier.
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
