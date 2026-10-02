package com.a67.psflag;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public final class FlagHandler implements InvocationHandler {
    private final Object original;

    public FlagHandler(Object original) {
        this.original = original;
    }

    @Override
    public Object invoke(Object proxy, Method method, Object[] args) throws Throwable {
        if ("enablePrivateSpaceFeatures".equals(method.getName())
                && method.getParameterCount() == 0) {
            return Boolean.TRUE;
        }

        try {
            return method.invoke(original, args);
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            throw cause != null ? cause : e;
        }
    }
}
