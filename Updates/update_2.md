# Update 2: Chinese Etymology & Story Guide

## 1. Fix the flashcard pinyin checking

**Problem:** The flashcard answer check is wrong. It must accept the pinyin as correct **regardless of how the tone is written**.

**Expected behavior:** For example, for 你好, all of these must be marked correct:

- `ni hao` (no tones)
- `ni3 hao3` (tone numbers)
- `nǐ hǎo` (tone marks)

**Notes for the fix:**

- Normalize both the user's input and the stored answer before comparing.
- Strip tone marks (ǎ → a, ǐ → i, ...), tone numbers (1-5), and extra spaces.
- Compare the normalized strings, so tone format never decides right or wrong.

## 2. Fix the HSK Level box (responsive)

**Problem:** This was requested before and is still not fixed. When the window is minimized to half the screen, the text in the HSK Level box does not fit.

**Expected behavior:**

- The words should fit inside the box when the window is half-screen.
- If they still cannot fit, truncate them with an ellipsis ("...") instead of overflowing or breaking the layout.

**Notes for the fix:**

- Use `min-width: 0` on the flex/grid children.
- Use `overflow: hidden; text-overflow: ellipsis; white-space: nowrap;` on the text.
- Test at about 50% screen width (around 700-960px) as well as full screen.
