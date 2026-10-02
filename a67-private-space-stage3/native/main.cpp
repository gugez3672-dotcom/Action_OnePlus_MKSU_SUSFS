#include <sys/types.h>
#include "zygisk.hpp"

#include <android/log.h>
#include <fcntl.h>
#include <pthread.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cstring>
#include <vector>

#define LOG_TAG "A67PrivateSpace"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

namespace {

constexpr const char *kTargetProcess = "com.android.launcher";
constexpr jint kPrivateUserId = 13;

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

class PrivateSpaceStage3 final : public zygisk::ModuleBase {
public:
    void onLoad(zygisk::Api *api, JNIEnv *env) override {
        api_ = api;
        env_ = env;
        env->GetJavaVM(&vm_);
        LOGI("stage3 loaded in zygote");
    }

    void preAppSpecialize(zygisk::AppSpecializeArgs *args) override {
        target_ = false;

        const char *name = envName(args->nice_name);
        if (name != nullptr) {
            target_ = std::strcmp(name, kTargetProcess) == 0;
            if (target_) {
                LOGI("launcher target matched: %s", name);
            }
            env_->ReleaseStringUTFChars(args->nice_name, name);
        }

        if (!target_) {
            api_->setOption(zygisk::DLCLOSE_MODULE_LIBRARY);
            return;
        }

        int module_dir = api_->getModuleDir();
        if (module_dir < 0) {
            LOGE("launcher: getModuleDir failed");
            return;
        }

        int fd = openat(module_dir, "payload.dex", O_RDONLY | O_CLOEXEC);
        close(module_dir);
        if (fd < 0) {
            LOGE("launcher: open payload.dex failed");
            return;
        }

        if (!read_all(fd, dex_)) {
            LOGE("launcher: read payload.dex failed");
            dex_.clear();
        }
        close(fd);
    }

    void postAppSpecialize(const zygisk::AppSpecializeArgs *) override {
        if (!target_) return;
        pthread_t t;
        if (pthread_create(&t, nullptr, &PrivateSpaceStage3::threadEntry, this) == 0) {
            pthread_detach(t);
        } else {
            LOGE("launcher: pthread_create failed");
        }
    }

private:
    const char *envName(jstring s) {
        if (!env_ || !s) return nullptr;
        return env_->GetStringUTFChars(s, nullptr);
    }

    static void *threadEntry(void *arg) {
        auto *self = static_cast<PrivateSpaceStage3 *>(arg);
        self->runWorker();
        return nullptr;
    }

    void runWorker() {
        if (!vm_) return;

        JNIEnv *env = nullptr;
        if (vm_->AttachCurrentThread(&env, nullptr) != JNI_OK || !env) {
            LOGE("launcher: AttachCurrentThread failed");
            return;
        }

        bool installed = false;
        for (int attempt = 0; attempt < 120 && !installed; ++attempt) {
            installed = tryInstall(env);
            if (!installed) usleep(250000);
        }

        if (installed) {
            LOGI("launcher: private-profile view filter installed for userId=%d",
                 kPrivateUserId);
        } else {
            LOGE("launcher: failed to install private-profile view filter");
        }

        vm_->DetachCurrentThread();
    }

    bool tryInstall(JNIEnv *env) {
        if (dex_.empty()) return false;

        jclass at_cls = env->FindClass("android/app/ActivityThread");
        if (clear_exception(env, "FindClass ActivityThread") || !at_cls) return false;

        jmethodID current_app = env->GetStaticMethodID(
                at_cls, "currentApplication", "()Landroid/app/Application;");
        if (clear_exception(env, "currentApplication method") || !current_app) return false;

        jobject app = env->CallStaticObjectMethod(at_cls, current_app);
        if (clear_exception(env, "currentApplication") || !app) return false;

        jclass context_cls = env->FindClass("android/content/Context");
        jmethodID get_cl = env->GetMethodID(
                context_cls, "getClassLoader", "()Ljava/lang/ClassLoader;");
        if (clear_exception(env, "Context.getClassLoader") || !get_cl) return false;

        jobject app_cl = env->CallObjectMethod(app, get_cl);
        if (clear_exception(env, "app classloader") || !app_cl) return false;

        jclass cl_cls = env->FindClass("java/lang/ClassLoader");
        jmethodID load_class = env->GetMethodID(
                cl_cls, "loadClass", "(Ljava/lang/String;)Ljava/lang/Class;");
        if (clear_exception(env, "ClassLoader.loadClass") || !load_class) return false;

        auto load = [&](const char *name) -> jclass {
            jstring n = env->NewStringUTF(name);
            jobject c = env->CallObjectMethod(app_cl, load_class, n);
            env->DeleteLocalRef(n);
            if (clear_exception(env, name) || !c) return nullptr;
            return static_cast<jclass>(c);
        };

        jclass launcher_cls = load("com.android.launcher3.Launcher");
        jclass tracker_cls = load("com.android.launcher3.util.ActivityTracker");
        if (!launcher_cls || !tracker_cls) return false;

        jfieldID tracker_field = env->GetStaticFieldID(
                launcher_cls,
                "ACTIVITY_TRACKER",
                "Lcom/android/launcher3/util/ActivityTracker;");
        if (clear_exception(env, "Launcher.ACTIVITY_TRACKER") || !tracker_field) return false;

        jobject tracker = env->GetStaticObjectField(launcher_cls, tracker_field);
        if (clear_exception(env, "get ACTIVITY_TRACKER") || !tracker) return false;

        jmethodID get_activity = env->GetMethodID(
                tracker_cls,
                "getCreatedActivity",
                "()Lcom/android/launcher3/BaseActivity;");
        if (clear_exception(env, "ActivityTracker.getCreatedActivity") || !get_activity) {
            return false;
        }

        jobject activity = env->CallObjectMethod(tracker, get_activity);
        if (clear_exception(env, "getCreatedActivity") || !activity) return false;

        jobject dex_buffer = env->NewDirectByteBuffer(
                dex_.data(), static_cast<jlong>(dex_.size()));
        if (!dex_buffer) return false;

        jclass imdcl_cls = env->FindClass("dalvik/system/InMemoryDexClassLoader");
        if (clear_exception(env, "FindClass InMemoryDexClassLoader") || !imdcl_cls) {
            return false;
        }

        jmethodID imdcl_ctor = env->GetMethodID(
                imdcl_cls,
                "<init>",
                "(Ljava/nio/ByteBuffer;Ljava/lang/ClassLoader;)V");
        if (clear_exception(env, "InMemoryDexClassLoader ctor") || !imdcl_ctor) {
            return false;
        }

        jobject helper_cl = env->NewObject(imdcl_cls, imdcl_ctor, dex_buffer, app_cl);
        if (clear_exception(env, "new InMemoryDexClassLoader") || !helper_cl) {
            return false;
        }

        jstring helper_name =
                env->NewStringUTF("com.a67.pslauncher.PrivateProfileViewFilter");
        jobject helper_class_obj =
                env->CallObjectMethod(helper_cl, load_class, helper_name);
        env->DeleteLocalRef(helper_name);
        if (clear_exception(env, "load helper class") || !helper_class_obj) return false;

        jclass helper_cls = static_cast<jclass>(helper_class_obj);
        jmethodID install = env->GetStaticMethodID(
                helper_cls,
                "install",
                "(Landroid/app/Activity;I)V");
        if (clear_exception(env, "helper install method") || !install) return false;

        env->CallStaticVoidMethod(helper_cls, install, activity, kPrivateUserId);
        if (clear_exception(env, "helper install call")) return false;

        return true;
    }

    zygisk::Api *api_ = nullptr;
    JNIEnv *env_ = nullptr;
    JavaVM *vm_ = nullptr;
    bool target_ = false;
    std::vector<unsigned char> dex_;
};

} // namespace

REGISTER_ZYGISK_MODULE(PrivateSpaceStage3)
