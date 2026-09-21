package com.mintlab.pkgprobe;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.content.pm.ApplicationInfo;
import android.content.pm.InstallSourceInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.ProviderInfo;
import android.content.pm.ResolveInfo;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.Bundle;
import android.text.method.ScrollingMovementMethod;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

public class MainActivity extends Activity {
    private static final String TARGET = "com.daily.notes";
    private TextView output;
    private String lastReport = "";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(12);
        root.setPadding(pad, pad, pad, pad);

        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);

        Button refresh = new Button(this);
        refresh.setText("刷新测试");
        refresh.setOnClickListener(v -> runProbe());

        Button copy = new Button(this);
        copy.setText("复制报告");
        copy.setOnClickListener(v -> {
            ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            cm.setPrimaryClip(ClipData.newPlainText("Package Visibility Probe", lastReport));
            Toast.makeText(this, "报告已复制", Toast.LENGTH_SHORT).show();
        });

        bar.addView(refresh, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        bar.addView(copy, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

        output = new TextView(this);
        output.setTextIsSelectable(true);
        output.setTextSize(13f);
        output.setTypeface(android.graphics.Typeface.MONOSPACE);
        output.setMovementMethod(new ScrollingMovementMethod());

        ScrollView scroll = new ScrollView(this);
        scroll.addView(output, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT,
                ScrollView.LayoutParams.WRAP_CONTENT));

        root.addView(bar);
        root.addView(scroll, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f));

        setContentView(root);
        runProbe();
    }

    private void runProbe() {
        PackageManager pm = getPackageManager();
        StringBuilder s = new StringBuilder();

        line(s, "Package Visibility Probe v1");
        line(s, "probe.package = " + getPackageName());
        line(s, "probe.flavor  = " + BuildConfig.FLAVOR);
        line(s, "probe.uid     = " + android.os.Process.myUid());
        line(s, "android       = " + Build.VERSION.RELEASE + " / API " + Build.VERSION.SDK_INT);
        line(s, "target        = " + TARGET);
        line(s, "");

        line(s, "=== A. 批量枚举 getInstalledPackages() ===");
        try {
            List<PackageInfo> list = pm.getInstalledPackages(0);
            boolean found = false;
            for (PackageInfo pi : list) {
                if (TARGET.equals(pi.packageName)) {
                    found = true;
                    break;
                }
            }
            line(s, "visible.count = " + list.size());
            line(s, "target.found  = " + found);
        } catch (Throwable t) {
            line(s, "ERROR: " + shortErr(t));
        }
        line(s, "");

        line(s, "=== B. 批量枚举 getInstalledApplications() ===");
        try {
            List<ApplicationInfo> list = pm.getInstalledApplications(0);
            boolean found = false;
            for (ApplicationInfo ai : list) {
                if (TARGET.equals(ai.packageName)) {
                    found = true;
                    break;
                }
            }
            line(s, "visible.count = " + list.size());
            line(s, "target.found  = " + found);
        } catch (Throwable t) {
            line(s, "ERROR: " + shortErr(t));
        }
        line(s, "");

        line(s, "=== C. 已知包名 getPackageInfo() ===");
        PackageInfo pi = null;
        int flags = PackageManager.GET_ACTIVITIES
                | PackageManager.GET_SERVICES
                | PackageManager.GET_RECEIVERS
                | PackageManager.GET_PROVIDERS
                | PackageManager.GET_PERMISSIONS
                | PackageManager.GET_SIGNING_CERTIFICATES;
        try {
            pi = pm.getPackageInfo(TARGET, flags);
            line(s, "RESULT = VISIBLE");
            dumpPackageInfo(s, pm, pi);
        } catch (PackageManager.NameNotFoundException e) {
            line(s, "RESULT = NOT_VISIBLE (NameNotFoundException)");
        } catch (Throwable t) {
            line(s, "RESULT = ERROR");
            line(s, shortErr(t));
        }
        line(s, "");

        line(s, "=== D. 已知包名 getApplicationInfo() ===");
        try {
            ApplicationInfo ai = pm.getApplicationInfo(TARGET, 0);
            line(s, "RESULT = VISIBLE");
            line(s, "label       = " + safeLabel(pm, ai));
            line(s, "uid         = " + ai.uid);
            line(s, "enabled     = " + ai.enabled);
            line(s, "sourceDir   = " + ai.sourceDir);
            line(s, "publicDir   = " + ai.publicSourceDir);
            line(s, "dataDir     = " + ai.dataDir);
        } catch (PackageManager.NameNotFoundException e) {
            line(s, "RESULT = NOT_VISIBLE (NameNotFoundException)");
        } catch (Throwable t) {
            line(s, "RESULT = ERROR");
            line(s, shortErr(t));
        }
        line(s, "");

        line(s, "=== E. Launcher / Intent 可见性 ===");
        try {
            Intent launch = pm.getLaunchIntentForPackage(TARGET);
            line(s, "getLaunchIntentForPackage = " + (launch == null ? "null" : launch.toString()));
        } catch (Throwable t) {
            line(s, "getLaunchIntentForPackage ERROR = " + shortErr(t));
        }
        try {
            Intent q = new Intent(Intent.ACTION_MAIN);
            q.addCategory(Intent.CATEGORY_LAUNCHER);
            q.setPackage(TARGET);
            List<ResolveInfo> ris = pm.queryIntentActivities(q, 0);
            line(s, "queryIntentActivities count = " + ris.size());
            for (ResolveInfo ri : ris) {
                ActivityInfo ai = ri.activityInfo;
                if (ai != null) {
                    line(s, "  " + ai.packageName + "/" + ai.name + " exported=" + ai.exported);
                }
            }
        } catch (Throwable t) {
            line(s, "queryIntentActivities ERROR = " + shortErr(t));
        }
        line(s, "");

        line(s, "=== F. 结论提示 ===");
        line(s, "plain:     不声明 <queries> / QUERY_ALL_PACKAGES");
        line(s, "targeted:  仅声明 <queries><package com.daily.notes>");
        line(s, "all:       声明 QUERY_ALL_PACKAGES");
        line(s, "比较三个 APK 的 C/D 项最关键。");

        lastReport = s.toString();
        output.setText(lastReport);
    }

    private void dumpPackageInfo(StringBuilder s, PackageManager pm, PackageInfo pi) {
        line(s, "packageName = " + pi.packageName);
        line(s, "versionName = " + pi.versionName);
        if (Build.VERSION.SDK_INT >= 28) {
            line(s, "versionCode = " + pi.getLongVersionCode());
        } else {
            line(s, "versionCode = " + pi.versionCode);
        }

        ApplicationInfo ai = pi.applicationInfo;
        if (ai != null) {
            line(s, "label       = " + safeLabel(pm, ai));
            line(s, "uid         = " + ai.uid);
            line(s, "enabled     = " + ai.enabled);
            line(s, "sourceDir   = " + ai.sourceDir);
            line(s, "publicDir   = " + ai.publicSourceDir);
            line(s, "dataDir     = " + ai.dataDir);
        }

        try {
            if (Build.VERSION.SDK_INT >= 30) {
                InstallSourceInfo isi = pm.getInstallSourceInfo(TARGET);
                line(s, "installer   = " + isi.getInstallingPackageName());
                line(s, "initiating  = " + isi.getInitiatingPackageName());
                line(s, "originating = " + isi.getOriginatingPackageName());
            } else {
                line(s, "installer   = " + pm.getInstallerPackageName(TARGET));
            }
        } catch (Throwable t) {
            line(s, "installer   = ERROR: " + shortErr(t));
        }

        if (Build.VERSION.SDK_INT >= 28 && pi.signingInfo != null) {
            try {
                android.content.pm.Signature[] sigs = pi.signingInfo.hasMultipleSigners()
                        ? pi.signingInfo.getApkContentsSigners()
                        : pi.signingInfo.getSigningCertificateHistory();
                if (sigs != null) {
                    for (int i = 0; i < sigs.length; i++) {
                        line(s, "signer[" + i + "].sha256 = " + sha256(sigs[i].toByteArray()));
                    }
                }
            } catch (Throwable t) {
                line(s, "signer = ERROR: " + shortErr(t));
            }
        }

        dumpActivities(s, "activities", pi.activities);
        dumpActivities(s, "receivers", pi.receivers);
        dumpServices(s, "services", pi.services);
        dumpProviders(s, "providers", pi.providers);

        if (pi.requestedPermissions != null) {
            line(s, "requestedPermissions.count = " + pi.requestedPermissions.length);
            for (String p : pi.requestedPermissions) {
                line(s, "  perm: " + p);
            }
        } else {
            line(s, "requestedPermissions.count = 0");
        }
    }

    private void dumpActivities(StringBuilder s, String name, ActivityInfo[] arr) {
        line(s, name + ".count = " + (arr == null ? 0 : arr.length));
        if (arr != null) {
            for (ActivityInfo x : arr) {
                line(s, "  " + x.name + " exported=" + x.exported + " enabled=" + x.enabled);
            }
        }
    }

    private void dumpServices(StringBuilder s, String name, ServiceInfo[] arr) {
        line(s, name + ".count = " + (arr == null ? 0 : arr.length));
        if (arr != null) {
            for (ServiceInfo x : arr) {
                line(s, "  " + x.name + " exported=" + x.exported + " enabled=" + x.enabled);
            }
        }
    }

    private void dumpProviders(StringBuilder s, String name, ProviderInfo[] arr) {
        line(s, name + ".count = " + (arr == null ? 0 : arr.length));
        if (arr != null) {
            for (ProviderInfo x : arr) {
                line(s, "  " + x.name + " exported=" + x.exported + " enabled=" + x.enabled
                        + " authority=" + x.authority);
            }
        }
    }

    private String safeLabel(PackageManager pm, ApplicationInfo ai) {
        try {
            CharSequence x = pm.getApplicationLabel(ai);
            return x == null ? "null" : x.toString();
        } catch (Throwable t) {
            return "ERROR:" + shortErr(t);
        }
    }

    private String sha256(byte[] data) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        byte[] d = md.digest(data);
        StringBuilder x = new StringBuilder();
        for (byte b : d) x.append(String.format(Locale.US, "%02X", b));
        return x.toString();
    }

    private static String shortErr(Throwable t) {
        String m = t.getMessage();
        return t.getClass().getSimpleName() + (m == null ? "" : ": " + m);
    }

    private static void line(StringBuilder s, String x) {
        s.append(x).append('\n');
    }

    private int dp(int x) {
        return Math.round(x * getResources().getDisplayMetrics().density);
    }
}
