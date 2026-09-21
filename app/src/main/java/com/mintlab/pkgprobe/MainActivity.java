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
import java.util.Enumeration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

public class MainActivity extends Activity {
    private static final String TARGET = "com.daily.notes";

    private static final String[] TERMS = new String[] {
            "ReSukiSU",
            "KernelSU",
            "kernelsu",
            "SUSFS",
            "susfs",
            "ksud",
            "com.resukisu",
            "/data/adb/ksu",
            "libkernelsu.so",
            "libksud.so",
            "libadbroot.so"
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
        scan.setText("开始扫描");
        scan.setOnClickListener(v -> startProbe());

        Button copy = new Button(this);
        copy.setText("复制报告");
        copy.setOnClickListener(v -> {
            ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            cm.setPrimaryClip(ClipData.newPlainText("APK Raw Read Probe", lastReport));
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
        startProbe();
    }

    private void startProbe() {
        scan.setEnabled(false);
        output.setText("Scanning as ordinary app UID...\n");
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
        }, "raw-apk-probe").start();
    }

    private String runProbe() {
        StringBuilder s = new StringBuilder();
        PackageManager pm = getPackageManager();

        line(s, "APK Raw Read Probe v1");
        line(s, "probe.package = " + getPackageName());
        line(s, "probe.uid     = " + Process.myUid());
        line(s, "android       = " + Build.VERSION.RELEASE + " / API " + Build.VERSION.SDK_INT);
        line(s, "target        = " + TARGET);
        line(s, "root/shizuku  = NOT USED");
        line(s, "");

        ApplicationInfo ai;
        try {
            ai = pm.getApplicationInfo(TARGET, 0);
            line(s, "=== A. Package visibility ===");
            line(s, "RESULT      = VISIBLE");
            line(s, "sourceDir   = " + ai.sourceDir);
            line(s, "publicDir   = " + ai.publicSourceDir);
            line(s, "dataDir     = " + ai.dataDir);
        } catch (Throwable t) {
            line(s, "=== A. Package visibility ===");
            line(s, "RESULT      = NOT AVAILABLE");
            line(s, shortErr(t));
            return s.toString();
        }
        line(s, "");

        File apk = new File(ai.sourceDir);
        line(s, "=== B. Raw base.apk file access ===");
        line(s, "exists      = " + apk.exists());
        line(s, "canRead     = " + apk.canRead());
        line(s, "length      = " + apk.length());
        try (FileInputStream in = new FileInputStream(apk)) {
            byte[] head = new byte[64];
            int n = in.read(head);
            line(s, "FileInputStream = SUCCESS, firstRead=" + n + " bytes");
            line(s, "zip.magic       = " + (n >= 4 && head[0] == 'P' && head[1] == 'K'));
        } catch (Throwable t) {
            line(s, "FileInputStream = FAILED");
            line(s, shortErr(t));
        }
        line(s, "");

        line(s, "=== C. ZipFile APK access ===");
        Map<String, Integer> totalHits = new LinkedHashMap<>();
        for (String term : TERMS) totalHits.put(term, 0);

        long scannedBytes = 0;
        int scannedEntries = 0;
        List<String> interestingNames = new ArrayList<>();

        try (ZipFile zip = new ZipFile(apk)) {
            line(s, "ZipFile.open = SUCCESS");
            line(s, "entry.count  = " + zip.size());

            Enumeration<? extends ZipEntry> en = zip.entries();
            while (en.hasMoreElements()) {
                ZipEntry e = en.nextElement();
                String name = e.getName();

                if (name.startsWith("classes") && name.endsWith(".dex")
                        || name.startsWith("lib/") && name.endsWith(".so")
                        || name.equals("resources.arsc")
                        || name.equals("AndroidManifest.xml")) {
                    interestingNames.add(name + " (" + e.getSize() + " bytes)");
                }
            }

            Collections.sort(interestingNames);
            line(s, "interesting entries:");
            for (String n : interestingNames) line(s, "  " + n);
            line(s, "");

            line(s, "=== D. In-process content scan ===");
            en = zip.entries();
            while (en.hasMoreElements()) {
                ZipEntry e = en.nextElement();
                String name = e.getName();
                boolean scanEntry =
                        (name.startsWith("classes") && name.endsWith(".dex"))
                        || (name.startsWith("lib/") && name.endsWith(".so"))
                        || name.equals("resources.arsc")
                        || name.equals("AndroidManifest.xml");

                if (!scanEntry || e.isDirectory()) continue;

                Map<String, Integer> entryHits;
                try (InputStream in = zip.getInputStream(e)) {
                    ScanResult rr = scanStream(in);
                    entryHits = rr.hits;
                    scannedBytes += rr.bytes;
                    scannedEntries++;
                }

                boolean any = false;
                for (String term : TERMS) {
                    int c = entryHits.get(term);
                    if (c > 0) {
                        if (!any) {
                            line(s, "[" + name + "]");
                            any = true;
                        }
                        line(s, "  " + term + " = " + c);
                        totalHits.put(term, totalHits.get(term) + c);
                    }
                }
            }

            line(s, "");
            line(s, "scan.entries = " + scannedEntries);
            line(s, "scan.bytes   = " + scannedBytes);
            line(s, "");
            line(s, "=== E. Aggregate fingerprints ===");
            boolean anyTotal = false;
            for (String term : TERMS) {
                int c = totalHits.get(term);
                line(s, term + " = " + c);
                if (c > 0) anyTotal = true;
            }
            line(s, "");
            line(s, "fingerprint.hit = " + anyTotal);

        } catch (Throwable t) {
            line(s, "ZipFile.open = FAILED");
            line(s, shortErr(t));
        }

        line(s, "");
        line(s, "=== Interpretation ===");
        line(s, "If FileInputStream/ZipFile = SUCCESS, an ordinary QUERY_ALL app");
        line(s, "can read the installed APK bytes on this ROM without root.");
        line(s, "If fingerprint counts > 0, it can also find those strings");
        line(s, "inside DEX/native libraries using only its own app process.");

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
