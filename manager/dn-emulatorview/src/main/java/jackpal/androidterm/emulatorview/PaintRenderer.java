/*
 * Copyright (C) 2007 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package jackpal.androidterm.emulatorview;

import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Typeface;


class PaintRenderer extends BaseTextRenderer {
    public PaintRenderer(int fontSize, ColorScheme scheme) {
        super(scheme);
        mTextPaint = new Paint();
        mTextPaint.setTypeface(Typeface.MONOSPACE);
        mTextPaint.setAntiAlias(true);
        mTextPaint.setTextSize(fontSize);

        mCharHeight = (int) Math.ceil(mTextPaint.getFontSpacing());
        mCharAscent = (int) Math.ceil(mTextPaint.ascent());
        mCharDescent = mCharHeight + mCharAscent;
        // Typeface.MONOSPACE is Droid Sans Mono (the same face MT bundles), so
        // one measured advance is the exact cell width for every ASCII glyph.
        mCharWidth = mTextPaint.measureText(WIDTH_SAMPLE) / WIDTH_SAMPLE.length();
    }

    public void drawTextRun(Canvas canvas, float x, float y, int lineOffset,
            int runWidth, char[] text, int index, int count,
            boolean selectionStyle, int textStyle,
            int cursorOffset, int cursorIndex, int cursorIncr, int cursorWidth, int cursorMode) {
        int foreColor = TextStyle.decodeForeColor(textStyle);
        int backColor = TextStyle.decodeBackColor(textStyle);
        int effect = TextStyle.decodeEffect(textStyle);

        boolean inverse =  mReverseVideo ^
                (effect & (TextStyle.fxInverse | TextStyle.fxItalic)) != 0;
        if (inverse) {
            int temp = foreColor;
            foreColor = backColor;
            backColor = temp;
        }

        if (selectionStyle) {
            backColor = TextStyle.ciCursorBackground;
        }

        boolean blink = (effect & TextStyle.fxBlink) != 0;
        if (blink && backColor < 8) {
            backColor += 8;
        }
        mTextPaint.setColor(mPalette[backColor]);

        float left = x + lineOffset * mCharWidth;
        canvas.drawRect(left, y + mCharAscent - mCharDescent,
                left + runWidth * mCharWidth, y,
                mTextPaint);

        boolean cursorVisible = lineOffset <= cursorOffset && cursorOffset < (lineOffset + runWidth);
        float cursorX = 0;
        if (cursorVisible) {
            cursorX = x + cursorOffset * mCharWidth;
            drawCursorImp(canvas, (int) cursorX, y, cursorWidth * mCharWidth, mCharHeight, cursorMode);
        }

        boolean invisible = (effect & TextStyle.fxInvisible) != 0;
        if (!invisible) {
            boolean bold = (effect & TextStyle.fxBold) != 0;
            boolean underline = (effect & TextStyle.fxUnderline) != 0;
            if (bold) {
                mTextPaint.setFakeBoldText(true);
            }
            if (underline) {
                mTextPaint.setUnderlineText(true);
            }
            int textPaintColor;
            if (foreColor < 8 && bold) {
                // In 16-color mode, bold also implies bright foreground colors
                textPaintColor = mPalette[foreColor+8];
            } else {
                textPaintColor = mPalette[foreColor];
            }
            mTextPaint.setColor(textPaintColor);

            float textOriginY = y - mCharDescent;
            float measured = mTextPaint.measureText(text, index, count);
            if (!cursorVisible && Math.abs(measured - runWidth * mCharWidth) < 0.5f) {
                // Plain monospace run: one draw call lands exactly on the grid.
                canvas.drawText(text, index, count, left, textOriginY, mTextPaint);
            } else {
                // Fallback glyphs (CJK, box drawing, symbols) have their own
                // advances, so place every code point on its own terminal cell.
                drawCells(canvas, text, index, count, left, textOriginY, lineOffset,
                        cursorVisible ? cursorOffset : -1, textPaintColor);
            }
            if (bold) {
                mTextPaint.setFakeBoldText(false);
            }
            if (underline) {
                mTextPaint.setUnderlineText(false);
            }
        }
    }

    private void drawCells(Canvas canvas, char[] text, int index, int count, float left,
            float baseline, int column, int cursorColumn, int textColor) {
        float cellX = left;
        float previousX = left;
        int end = index + count;
        for (int i = index; i < end;) {
            int codePoint = Character.codePointAt(text, i, end);
            int units = Character.charCount(codePoint);
            int width = UnicodeTranscript.charWidth(codePoint);
            mTextPaint.setColor(column == cursorColumn
                    ? mPalette[TextStyle.ciCursorForeground] : textColor);
            if (width <= 0) {
                // Combining mark: draw over the previous cell, no advance.
                canvas.drawText(text, i, units, previousX, baseline, mTextPaint);
                i += units;
                continue;
            }
            float cell = width * mCharWidth;
            float glyph = mTextPaint.measureText(text, i, units);
            boolean boxDrawing = codePoint >= 0x2500 && codePoint <= 0x259F;
            if (glyph > 0 && (glyph > cell || boxDrawing)) {
                // Squeeze oversized glyphs into their cells; stretch box and
                // block elements so table borders join like MT's.
                mTextPaint.setTextScaleX(cell / glyph);
                canvas.drawText(text, i, units, cellX, baseline, mTextPaint);
                mTextPaint.setTextScaleX(1.0f);
            } else {
                canvas.drawText(text, i, units, cellX + (cell - glyph) / 2f, baseline, mTextPaint);
            }
            previousX = cellX;
            cellX += cell;
            column += width;
            i += units;
        }
    }

    public int getCharacterHeight() {
        return mCharHeight;
    }

    public float getCharacterWidth() {
        return mCharWidth;
    }

    public int getTopMargin() {
        return mCharDescent;
    }

    private Paint mTextPaint;
    private float mCharWidth;
    private int mCharHeight;
    private int mCharAscent;
    private int mCharDescent;
    private static final String WIDTH_SAMPLE = "abcdefghijklmnopqrstuvwxyz0123456789#";
}
