# Release checklist

1. Run Linux `pytest`, `ruff check` and `ruff format --check`.
2. Run the opt-in hardware test on a safe panel; record firmware if available.
3. Review documented limitations. Distinguish synthetic tests from hardware evidence.
4. Set the manifest version, update README and CHANGELOG, and check the HACS minimum HA version.
5. Run `python tools/build_release.py` and inspect the manual-install archive.
6. Push reviewed changes and require GitHub tests, hassfest and HACS validation to
   pass. The brands check is excluded for this custom repository; default HACS
   catalogue inclusion is separate.
7. Publish a GitHub release/tag matching the manifest version. Attach the manual
   archive if useful. The build tool does not publish, tag or push anything.

Repository: https://github.com/Oak-Leaf-Technical-Services/AudacNWP220_HomeAssistant

## GitHub repository metadata

HACS also validates settings stored on GitHub, outside the Git checkout. Keep the
repository description populated, Issues enabled, and relevant topics configured
in the repository's About section. Suggested metadata:

- Description: Home Assistant custom integration for AUDAC NWP220 network input panels, using native UDP control.
- Topics: `home-assistant`, `hacs`, `custom-integration`, `audac`, `nwp220`, `udp`.

The HACS job fetches files from GitHub at the triggering commit SHA. If it reports
an invalid `hacs.json` or a manifest value of `None`, inspect the download logs and
confirm that those files are accessible at that revision before changing their
contents. After correcting repository metadata, rerun the failed HACS job.
