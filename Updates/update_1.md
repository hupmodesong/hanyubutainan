# Update 1

## Bugs

- [x] Fix infinite point accumulation: when spamming **Easy**, points keep adding up even after the flashcard session has ended.
- [x] Flashcards dictation: remove the bottom-right notification that appears when pressing **Listen**, since it gives away the answer. Also change its hint to what is described in the Flashcards section below.
- [x] Fix the UI error on the definition after flipping a word (a raw `<strong>` tag is showing).
- [x] Fix scrolling: while inside a word's tab, the main page behind it can't be scrolled up/down.
- [x] Make the whole word box clickable to inspect the word, not just the upper part.
- [x] Fix UI overflow: when a word is too long for its box, truncate it with "…" instead of trying to fit everything.
- [x] Official Textbooks: fix the PDF page number indicator (remove the arrows).

## Additional Features

### Flashcards

- **Type pinyin mode:** show the word, and the user types its meaning and pinyin (both traditional and simplified should be accepted).
- **Definition mode:** show the definition, and the user types the equivalent word.
- **Pinyin input flexibility:** accept any of these when typing pinyin:
  - tone numbers (e.g. `ni3 hao3`)
  - full letters without tone numbers
  - full tone marks
  - the original characters
- **Flip restriction:** the card must only be flippable in **Flip card** mode, not in other modes.
- **Cleanup:** remove the *meaning* and *component clue* from the Type pinyin and Flip card sections, respectively.

> **Note:** there are 3 options in these modes:
>
> - **Check**: if wrong, lose 1 heart (out of 3). Running out of hearts forces the user to click 不知道.
> - **Hint**: show an example with clear context.
> - **不知道**: reveal the answer.

### My Vocab List

- Let the user type in pinyin when using **Analyze & Add Word**, then show options of what they might have meant.
- Add the meaning/story behind a word's creation where one exists (e.g. 百货).
  - ⚠️ **Verify the origin of EVERY story before using it.** A friend said some of them are made up, so every word needs to be double-checked.
- Add instructions on the expected format for Import JSON/CSV (optional; remove if redundant).

### Radical Lab

- Make sound root (phonetic) and meaning radical (topic) selection work **both ways**: besides showing combinations through the sound root, also show them through the meaning radicals.
- Show the traditional radical shape alongside the simplified one, separated by "/".
- Remove the plus sign when choosing suitable radicals.

### Official Textbooks

- Combine the book's language settings into a single picker.

## Changes

- Move the **ancient script** out of the word inspection view and into its own section of Radical Lab.
- Make the **confidence level** and **source** bigger and more comprehensive.
- Make examples fit the learner's level. For example, HSK 2 examples shouldn't use higher-level words unless learners are already comfortable with them.
- Rework **Export PDF**: it currently just takes a picture. Export to **Excel** instead, with these columns:

  | Order | Words | Pinyin | Definition | Breakdown | Example |
  | ----- | ----- | ------ | ---------- | --------- | ------- |
