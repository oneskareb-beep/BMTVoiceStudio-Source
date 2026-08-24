# Swahili Future Plan — Daily BMT third language

**Status:** Planning document only. Swahili is **not** implemented in the current release.

Visible Daily BMT production remains **English + French only**.

Do not add Swahili UI panels, navigation, placeholders, or voice guesses until a controlled phase begins.

---

## Architecture preparation (already in place)

- `LanguageProductionConfig` binds display labels to a voice preset / pipeline.
- `DailyLanguagePanel` is a reusable script + validate panel.
- Daily BMT should instantiate enabled language configs rather than hard-coding only two unique widgets forever.

Future work can register a Swahili config without rewriting the entire Daily BMT engine.

---

## Future phases

### Phase 1 — Voice research
Research and select approved Swahili male and female neural voices suitable for BMT devotionals.

### Phase 2 — Locale / accent
Determine required locale or accent (for example East African or DRC-oriented Swahili) based on ministry production requirements.

### Phase 3 — Source pipeline configuration
Create a Swahili source-pipeline configuration in the same canonical config used by English/French (voices, rate, pitch, volume, pause, post-processing, export rules).

### Phase 4 — Pronunciation validation
Validate pronunciation of:

- Bible references
- personal and ministry names
- phone numbers
- dates
- ordinal numbering
- religious terminology

### Phase 5 — Live sample audio
Run live sample audio validation against reference scripts before enabling production.

### Phase 6 — Daily BMT panel
Add a third Daily BMT language panel using `DailyLanguagePanel` + Swahili `LanguageProductionConfig`.

### Phase 7 — Generation orchestration
Update generation orchestration to EN + FR + SW when Swahili is approved.

### Phase 8 — Outputs / history / reports
Update exports, filenames, history columns, and production reports for three languages.

---

## Explicit non-goals for this document

- Do not choose or hard-code Swahili voice IDs here.
- Do not claim Swahili production is supported.
- Do not ship Swahili UI until Phases 1–5 are complete.
