// IDeviceCatalog.aidl
package com.daily.notes;

import android.content.pm.PackageInfo;
import rikka.parcelablelist.ParcelableListSlice;

interface IDeviceCatalog {
    ParcelableListSlice<PackageInfo> getPackages(int flags);

    int[] getUserIds();
}