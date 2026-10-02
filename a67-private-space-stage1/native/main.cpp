#include "zygisk.hpp"

#include <android/log.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cstring>
#include <string>
#include <vector>

#define LOG_TAG "A67PrivateSpace"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

namespace {

constexpr uid_t kTargetUid = 1000;
constexpr const char *kTargetProcess = "com.android.settings";

bool clear_exception(JNIEnv *env, const char *where) {
    if (!env->ExceptionCheck()) return false;
    LOGE("JNI exception at %s", where);
    env->ExceptionDescribe();
    env->ExceptionClear();
    return true;
}

bool read_all(int fd, std::vector<unsigned char> &out) {
    struct stat st {};
    if (fstat(fd, &st) != 0 || st.st_size <= 0) return false;
    out.resize(static_cast<size_t>(st.st_size));

    size_t done = 0;
    while (done < out.size()) {
        ssize_t n = read(fd, out.data() + done, out.size() - done);
        if (n <= 0) return false;
        done += static_cast<size_t>(n);
    }
    return true;
}

class PrivateSpaceStage1 final : public zygisk::ModuleBase {
public:
    void onLoad(zygisk::Api *api, JNIEnv *env) override {
        api_ = api;
        env_ = env;
    }

    void preAppSpecialize(zygisk::AppSpecializeArgs *args) override {
        target_ = false;

        const char *name = env_->GetStringUTFChars(args->nice_name, nullptr);
        if (name != nullptr) {
            target_ = (args->uid == static_cast<jint>(kTargetUid))
                    && (std::strcmp(name, kTargetProcess) == 0);
            env_->ReleaseStringUTFChars(args->nice_name, name);
        }

        if (!target_) {
            api_->setOption(zygisk::DLCLOSE_MODULE_LIBRARY);
            return;
        }

        int module_dir = api_->getModuleDir();
        if (module_dir < 0) {
            LOGE("getModuleDir failed");
            return;
        }

        int dex_fd = openat(module_dir, "payload.dex", O_RDONLY | O_CLOEXEC);
        close(module_dir);
        if (dex_fd < 0) {
            LOGE("open payload.dex failed");
            return;
        }

        if (!read_all(dex_fd, dex_)) {
            LOGE("read payload.dex failed");
            dex_.clear();
        }
        close(dex_fd);
    }

    void postAppSpecialize(const zygisk::AppSpecializeArgs *) override {
        if (!target_) return;
        if (dex_.empty()) {
            LOGE("payload is empty; no change applied");
            return;
        }

        if (install_proxy()) {
            LOGI("stage1 installed: android.multiuser.Flags.enablePrivateSpaceFeatures() => true");
        } else {
            LOGE("stage1 install failed");
        }
    }

private:
    bool install_proxy() {
        JNIEnv *env = env_;

        jclass thread_cls = env->FindClass("java/lang/Thread");
        if (clear_exception(env, "FindClass Thread") || !thread_cls) return false;
        jmethodID current_thread = env->GetStaticMethodID(
                thread_cls, "currentThread", "()Ljava/lang/Thread;");
        jmethodID get_ccl = env->GetMethodID(
                thread_cls, "getContextClassLoader", "()Ljava/lang/ClassLoader;");
        if (clear_exception(env, "Thread methods") || !current_thread || !get_ccl) return false;

        jobject thread = env->CallStaticObjectMethod(thread_cls, current_thread);
        jobject parent_loader = env->CallObjectMethod(thread, get_ccl);
        if (clear_exception(env, "context classloader")) return false;

        jobject buffer = env->NewDirectByteBuffer(dex_.data(), static_cast<jlong>(dex_.size()));
        if (!buffer) return false;

        jclass imdcl_cls = env->FindClass("dalvik/system/InMemoryDexClassLoader");
        if (clear_exception(env, "FindClass InMemoryDexClassLoader") || !imdcl_cls) return false;
        jmethodID imdcl_ctor = env->GetMethodID(
                imdcl_cls, "<init>",
                "(Ljava/nio/ByteBuffer;Ljava/lang/ClassLoader;)V");
        if (clear_exception(env, "InMemoryDexClassLoader ctor") || !imdcl_ctor) return false;

        jobject helper_loader = env->NewObject(imdcl_cls, imdcl_ctor, buffer, parent_loader);
        if (clear_exception(env, "new InMemoryDexClassLoader") || !helper_loader) return false;

        jclass classloader_cls = env->FindClass("java/lang/ClassLoader");
        jmethodID load_class = env->GetMethodID(
                classloader_cls, "loadClass", "(Ljava/lang/String;)Ljava/lang/Class;");
        if (clear_exception(env, "ClassLoader.loadClass") || !load_class) return false;

        jstring handler_name = env->NewStringUTF("com.a67.psflag.FlagHandler");
        jobject handler_class_obj = env->CallObjectMethod(helper_loader, load_class, handler_name);
        if (clear_exception(env, "load FlagHandler") || !handler_class_obj) return false;
        jclass handler_cls = static_cast<jclass>(handler_class_obj);

        jclass flags_cls = env->FindClass("android/multiuser/Flags");
        jclass feature_flags_cls = env->FindClass("android/multiuser/FeatureFlags");
        if (clear_exception(env, "FindClass android.multiuser") || !flags_cls || !feature_flags_cls) {
            return false;
        }

        jfieldID feature_flags_field = env->GetStaticFieldID(
                flags_cls, "FEATURE_FLAGS", "Landroid/multiuser/FeatureFlags;");
        if (clear_exception(env, "GetStaticFieldID FEATURE_FLAGS") || !feature_flags_field) {
            return false;
        }

        jobject original = env->GetStaticObjectField(flags_cls, feature_flags_field);
        if (clear_exception(env, "GetStaticObjectField FEATURE_FLAGS") || !original) return false;

        jmethodID handler_ctor = env->GetMethodID(
                handler_cls, "<init>", "(Ljava/lang/Object;)V");
        if (clear_exception(env, "FlagHandler ctor") || !handler_ctor) return false;
        jobject handler = env->NewObject(handler_cls, handler_ctor, original);
        if (clear_exception(env, "new FlagHandler") || !handler) return false;

        jclass class_cls = env->FindClass("java/lang/Class");
        jobjectArray interfaces = env->NewObjectArray(1, class_cls, feature_flags_cls);
        if (clear_exception(env, "interfaces array") || !interfaces) return false;

        jclass proxy_cls = env->FindClass("java/lang/reflect/Proxy");
        jmethodID new_proxy = env->GetStaticMethodID(
                proxy_cls, "newProxyInstance",
                "(Ljava/lang/ClassLoader;[Ljava/lang/Class;Ljava/lang/reflect/InvocationHandler;)Ljava/lang/Object;");
        if (clear_exception(env, "Proxy.newProxyInstance") || !new_proxy) return false;

        jobject proxy = env->CallStaticObjectMethod(
                proxy_cls, new_proxy, helper_loader, interfaces, handler);
        if (clear_exception(env, "create proxy") || !proxy) return false;

        env->SetStaticObjectField(flags_cls, feature_flags_field, proxy);
        if (clear_exception(env, "SetStaticObjectField FEATURE_FLAGS")) return false;

        jmethodID enabled_mid = env->GetStaticMethodID(
                flags_cls, "enablePrivateSpaceFeatures", "()Z");
        if (clear_exception(env, "GetStaticMethodID enablePrivateSpaceFeatures") || !enabled_mid) {
            return false;
        }

        jboolean enabled = env->CallStaticBooleanMethod(flags_cls, enabled_mid);
        if (clear_exception(env, "verify enablePrivateSpaceFeatures")) return false;

        LOGI("verification result=%s", enabled == JNI_TRUE ? "true" : "false");
        return enabled == JNI_TRUE;
    }

    zygisk::Api *api_ = nullptr;
    JNIEnv *env_ = nullptr;
    bool target_ = false;
    std::vector<unsigned char> dex_;
};

}  // namespace

REGISTER_ZYGISK_MODULE(PrivateSpaceStage1)
