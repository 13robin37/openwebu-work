# Translating Secure Onboarding

Thank you for helping translate the onboarding guide.

Each locale is a UTF-8 JSON file. The English catalog is the translation template, and the French catalog is a completed example.

## Add a language

1. Copy `en.json` to a file named with the locale code, for example `es.json` or `ca.json`.
2. Update `_meta`:

   ```json
   {
     "_meta": {
       "code": "es",
       "name": "Spanish",
       "native_name": "Español"
     }
   }
   ```

3. Translate only the values inside `messages`.
4. Do not rename, add, or remove message IDs.
5. Keep interface names such as Open WebUI, Tool Permissions, Workspace, and Admin Panel unchanged when they refer to labels displayed by the product.
6. Preserve placeholders, punctuation, keyboard keys, `@`, `#`, `/`, `+`, and arrows when they are part of an instruction.
7. Run the checks:

   ```bash
   python sync_locales.py
   python sync_locales.py --check
   python -m unittest -v test_secure_onboarding.py
   ```

8. Commit the new locale file and the regenerated `secure_onboarding.py` together.

## How it works

Open WebUI Functions are normally installed as one Python file. `sync_locales.py` validates each JSON catalog and embeds translated languages into that self-contained file.

At runtime, the guide reads the user locale from `user.settings.ui.language`. It uses the exact locale when available, then tries the base language. For example, `es-ES` falls back to `es`. If neither exists, it uses the configured `default_language`.

The language buttons are generated from the embedded catalogs. A manual choice is stored in the browser for the next visit.

## Validation rules

- The filename must match `_meta.code`.
- Every source message must have a non-empty translation.
- Unknown or missing message IDs fail validation.
- JSON must be valid UTF-8.
- Admin-only translations are not sent to regular-user guide payloads.

The English and French catalogs are regenerated from the inline fallback pairs in `secure_onboarding.py`. Edit application copy there first, then run `python sync_locales.py` to refresh both base catalogs.
