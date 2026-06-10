# Contract Migration Notes — RELEASE_MONTH YEAR

<!--
  Use this template for any release that contains contract-breaking changes to the
  DL Streamer Pipeline Server parameter binding contract.  Copy this file to
  docs/user-guide/release-notes/<month-year>.md (or add a section to the existing
  release notes file for that month) and fill in all sections below.

  A release is a contract-breaking release if it changes any item marked "Stable"
  in docs/user-guide/advanced-guide/detailed_usage/rest_api/parameter_contract.md.

  Before publishing the release:
    1. Complete all sections in this template.
    2. Update contract-version in parameter_contract.md YAML front matter.
    3. Run  python3 utils/generate_contract.py  and commit contract.json.
    4. Remove this comment block.
-->

## Contract Version

| Field | Value |
|-------|-------|
| Previous contract-version | `X.Y.Z` |
| New contract-version | `X.Y+1.0` |
| Breaking change | Yes |

---

## Changed Behavior

<!-- Describe what changed and why. Be precise: name the binding form or format value
     that changed, quote the old behavior, and quote the new behavior. -->

| Binding form / format | Old behavior | New behavior |
|-----------------------|-------------|-------------|
| _(e.g. `format: json`)_ | _(e.g. value passed as native object)_ | _(e.g. value JSON-serialized before set_property)_ |

---

## Removed Parameters or Binding Forms

<!-- List any parameter keys, element binding forms, or format values that have been
     removed. For each, state the replacement (if any). -->

- **Removed:** `_parameter-name_`
  - **Reason:** _(brief explanation)_
  - **Replacement:** _(new parameter name or approach, or "none")_

---

## New Required Fields

<!-- List any new fields that are now required in a pipeline definition or request.
     Integrators must update their pipeline definitions before deploying this release. -->

- **Field:** `_field-name_`
  - **Where required:** pipeline definition `parameters.properties.<name>.element`
  - **Default if absent:** _(none — will cause runtime error / fallback to X)_

---

## Upgrade Steps

Follow these steps to update any pipeline definition or downstream adapter that uses
the previous contract version.

1. **Update pipeline definitions.**
   In each `configs/<pipeline>/config.json`, change:
   ```json
   // Before
   "element": "old-element-name"

   // After
   "element": {"name": "new-element-name", "property": "explicit-property"}
   ```

2. **Update request construction.**
   If your adapter constructs pipeline requests programmatically, update the
   `parameters` dict to use the new field names or value formats.

3. **Verify with conformance tests.**
   Run the conformance suite against your updated definitions:
   ```bash
   pytest tests/test_parameter_contract.py -v
   ```

4. **Update `contract-version` references** in any downstream system that pins to
   a specific contract version.

---

## Verification

Before releasing, confirm:

- [ ] `parameter_contract.md` front matter `contract-version` updated.
- [ ] `contract.json` regenerated: `python3 utils/generate_contract.py`
- [ ] `contract.json` committed to the service root.
- [ ] `pytest tests/test_parameter_contract.py` passes.
- [ ] CI `check-contract` step passes: `python3 utils/generate_contract.py --check`
