# Notification translation review

Machine-generated ko/ja/th/vi strings for the localized-notifications feature, pending native review. English is authoritative and is the runtime fallback, so a wrong translation reads awkwardly but never breaks an alert.

One sheet per language — hand each to a native speaker:
- [Korean 한국어](review-ko.md)
- [Japanese 日本語](review-ja.md)
- [Thai ภาษาไทย](review-th.md)
- [Vietnamese Tiếng Việt](review-vi.md)

**Flagged uncertain terms** (translator-noted): `cover` (buy-to-close-short) and `armed` (a run waiting to start) — no clean trading equivalent in several languages.

**Applying corrections:** fill the *Your correction* column, return the sheet, and the catalogue (`service/server/notifications_i18n.py` / `email_i18n.py`) is updated — either edit those modules directly or update `.superpowers/sdd/translation-*.json` and re-run `assemble_catalogue.py` (which re-checks placeholder parity).