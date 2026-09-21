package com.mintlab.pkgprobe;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Process;
import android.os.SystemClock;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.Enumeration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

public class MainActivity extends Activity {
    private static final String[] TERMS = new String[] {
            "ReSukiSU",
            "KernelSU",
            "kernelsu",
            "SUKISU",
            "SukiSU",
            "SUSFS",
            "susfs",
            "ksud",
            "com.resukisu",
            "/data/adb/ksu",
            "libkernelsu.so",
            "libksud.so",
            "libadbroot.so",
            "magisk",
            "zygisk",
            "lsposed"
    };

    private TextView output;
    private Button scan;
    private String lastReport = "";

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(12);
        root.setPadding(pad, pad, pad, pad);

        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);

        scan = new Button(this);
        scan.setText("开始盲扫");
        scan.setOnClickListener(v -> startProbe());

        Button copy = new Button(this);
        copy.setText("复制报告");
        copy.setOnClickListener(v -> {
            ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            cm.setPrimaryClip(ClipData.newPlainText("Blind APK Scan", lastReport));
            Toast.makeText(this, "报告已复制", Toast.LENGTH_SHORT).show();
        });

        bar.addView(scan, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        bar.addView(copy, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));

        output = new TextView(this);
        output.setTextSize(12.5f);
        output.setTextIsSelectable(true);
        output.setTypeface(android.graphics.Typeface.MONOSPACE);

        ScrollView sv = new ScrollView(this);
        sv.addView(output);

        root.addView(bar);
        root.addView(sv, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1));

        setContentView(root);
        lineToUi("Blind APK Scanner ready.\nNo target package name is built into this probe.\n");
    }

    private void startProbe() {
        scan.setEnabled(false);
        output.setText("Scanning visible third-party APKs as ordinary app UID...\n");
        new Thread(() -> {
            String report;
            try {
                report = runProbe();
            } catch (Throwable t) {
                report = "FATAL: " + shortErr(t);
            }
            final String r = report;
            runOnUiThread(() -> {
                lastReport = r;
                output.setText(r);
                scan.setEnabled(true);
            });
        }, "blind-apk-scan").start();
    }

    private String runProbe() {
        PackageManager pm = getPackageManager();
        StringBuilder s = new StringBuilder();

        line(s, "Blind APK Scanner v1");
        line(s, "probe.package = " + getPackageName());
        line(s, "probe.uid     = " + Process.myUid());
        line(s, "android       = " + Build.VERSION.RELEASE + " / API " + Build.VERSION.SDK_INT);
        line(s, "root/shizuku  = NOT USED");
        line(s, "target.package= NONE");
        line(s, "scope         = visible non-system apps, excluding self");
        line(s, "");

        List<ApplicationInfo> all;
        try {
            all = pm.getInstalledApplications(0);
        } catch (Throwable t) {
            line(s, "getInstalledApplications FAILED: " + shortErr(t));
            return s.toString();
        }

        Collections.sort(all, Comparator.comparing(a -> a.packageName == null ? "" : a.packageName));

        List<ApplicationInfo> apps = new ArrayList<>();
        for (ApplicationInfo ai : all) {
            if (ai.packageName == null) continue;
            if (getPackageName().equals(ai.packageName)) continue;
            boolean system = (ai.flags & ApplicationInfo.FLAG_SYSTEM) != 0;
            if (system) continue;
            apps.add(ai);
        }

        line(s, "visible.apps      = " + all.size());
        line(s, "thirdparty.apps   = " + apps.size());
        line(s, "");

        long t0 = SystemClock.elapsedRealtime();
        long totalApkBytes = 0;
        long totalScannedBytes = 0;
        int readable = 0;
        int zipOpened = 0;
        int failed = 0;
        int hitPackages = 0;

        List<String> hitsSummary = new ArrayList<>();

        int index = 0;
        for (ApplicationInfo ai : apps) {
            index++;
            String pkg = ai.packageName;
            File apk = new File(ai.sourceDir == null ? "" : ai.sourceDir);
            long fileLen = apk.length();
            totalApkBytes += Math.max(0, fileLen);

            boolean canRead = apk.canRead();
            if (canRead) readable++;

            long pkgStart = SystemClock.elapsedRealtime();
            Map<String,Integer> totals = new LinkedHashMap<>();
            for (String term : TERMS) totals.put(term, 0);
            long scanned = 0;
            int entries = 0;

            try (FileInputStream ignored = new FileInputStream(apk);
                 ZipFile zip = new ZipFile(apk)) {
                zipOpened++;
                Enumeration<? extends ZipEntry> en = zip.entries();

                while (en.hasMoreElements()) {
                    ZipEntry e = en.nextElement();
                    String name = e.getName();

                    boolean scanEntry =
                            (name.startsWith("classes") && name.endsWith(".dex"))
                            || (name.startsWith("lib/") && name.endsWith(".so"))
                            || name.equals("resources.arsc")
                            || name.equals("AndroidManifest.xml");

                    if (!scanEntry || e.isDirectory()) continue;
                    entries++;

                    try (InputStream in = zip.getInputStream(e)) {
                        ScanResult rr = scanStream(in);
                        scanned += rr.bytes;
                        for (String term : TERMS) {
                            int c = rr.hits.get(term);
                            if (c > 0) totals.put(term, totals.get(term) + c);
                        }
                    }
                }
            } catch (Throwable t) {
                failed++;
            }

            totalScannedBytes += scanned;
            boolean hit = false;
            int totalHits = 0;
            StringBuilder detail = new StringBuilder();
            for (String term : TERMS) {
                int c = totals.get(term);
                if (c > 0) {
                    hit = true;
                    totalHits += c;
                    if (detail.length() > 0) detail.append(", ");
                    detail.append(term).append("=").append(c);
                }
            }

            long pkgMs = SystemClock.elapsedRealtime() - pkgStart;
            if (hit) {
                hitPackages++;
                hitsSummary.add(String.format("%03d/%03d  %s  hits=%d  scan=%.2fMB  time=%dms\n    %s",
                        index, apps.size(), pkg, totalHits, scanned / 1048576.0, pkgMs, detail));
            }

            final int done = index;
            if (done == 1 || done % 10 == 0 || done == apps.size()) {
                final long elapsed = SystemClock.elapsedRealtime() - t0;
                runOnUiThread(() -> output.setText(
                        "Blind scan running...\n" +
                        "apps " + done + "/" + apps.size() + "\n" +
                        "elapsed " + elapsed + " ms\n"));
            }
        }

        long elapsedMs = SystemClock.elapsedRealtime() - t0;

        line(s, "=== RESULTS ===");
        line(s, "thirdparty.apps   = " + apps.size());
        line(s, "readable.apks     = " + readable);
        line(s, "zip.opened        = " + zipOpened);
        line(s, "scan.failed       = " + failed);
        line(s, "hit.packages      = " + hitPackages);
        line(s, String.format("apk.bytes.total   = %d (%.2f MB)", totalApkBytes, totalApkBytes / 1048576.0));
        line(s, String.format("scan.bytes.total  = %d (%.2f MB)", totalScannedBytes, totalScannedBytes / 1048576.0));
        line(s, "elapsed.ms        = " + elapsedMs);
        line(s, String.format("elapsed.seconds   = %.3f", elapsedMs / 1000.0));
        line(s, "");

        line(s, "=== MATCHED PACKAGES ===");
        if (hitsSummary.isEmpty()) {
            line(s, "(none)");
        } else {
            for (String x : hitsSummary) line(s, x);
        }

        line(s, "");
        line(s, "=== INTERPRETATION ===");
        line(s, "This build contains no target package name.");
        line(s, "It enumerates every visible third-party package and scans its base APK.");
        line(s, "Only DEX, native .so, resources.arsc and AndroidManifest.xml are scanned.");
        line(s, "Package names in MATCHED PACKAGES were discovered only after enumeration.");

        return s.toString();
    }

    private ScanResult scanStream(InputStream in) throws Exception {
        Map<String, Integer> hits = new LinkedHashMap<>();
        byte[][] terms = new byte[TERMS.length][];
        int max = 0;
        for (int i = 0; i < TERMS.length; i++) {
            terms[i] = TERMS[i].getBytes(StandardCharsets.UTF_8);
            if (terms[i].length > max) max = terms[i].length;
            hits.put(TERMS[i], 0);
        }

        byte[] buf = new byte[64 * 1024];
        byte[] carry = new byte[Math.max(0, max - 1)];
        int carryLen = 0;
        long total = 0;

        int n;
        while ((n = in.read(buf)) != -1) {
            total += n;
            byte[] block = new byte[carryLen + n];
            if (carryLen > 0) System.arraycopy(carry, 0, block, 0, carryLen);
            System.arraycopy(buf, 0, block, carryLen, n);

            for (int i = 0; i < TERMS.length; i++) {
                int count = countOccurrences(block, terms[i]);
                if (count > 0) hits.put(TERMS[i], hits.get(TERMS[i]) + count);
            }

            carryLen = Math.min(carry.length, block.length);
            if (carryLen > 0) {
                System.arraycopy(block, block.length - carryLen, carry, 0, carryLen);
            }
        }

        return new ScanResult(total, hits);
    }

    private int countOccurrences(byte[] data, byte[] needle) {
        if (needle.length == 0 || data.length < needle.length) return 0;
        int count = 0;
        outer:
        for (int i = 0; i <= data.length - needle.length; i++) {
            for (int j = 0; j < needle.length; j++) {
                if (data[i + j] != needle[j]) continue outer;
            }
            count++;
            i += needle.length - 1;
        }
        return count;
    }

    private static class ScanResult {
        final long bytes;
        final Map<String, Integer> hits;
        ScanResult(long bytes, Map<String, Integer> hits) {
            this.bytes = bytes;
            this.hits = hits;
        }
    }

    private void lineToUi(String x) {
        output.setText(x);
    }

    private static void line(StringBuilder s, String x) {
        s.append(x).append('\n');
    }

    private static String shortErr(Throwable t) {
        String m = t.getMessage();
        return t.getClass().getSimpleName() + (m == null ? "" : ": " + m);
    }

    private int dp(int x) {
        return Math.round(x * getResources().getDisplayMetrics().density);
    }
}
