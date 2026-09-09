- **2026-09-04 System Overseer (event-triggered — tests FAIL=1 + noop fp)**
  - **Found:** critical `tests: FAIL (failures=1)` = `tests.test_peer_last_cycle_poison` — Mac rsync clobbered `peer_transcript.py` dropping `def _merge_preserve_cycle_memory` / `OVERSEER_SAVE_PRESERVE_LAST_CYCLE`; `beat-mac-clobber` OR-matched weak SCRUB/LOCK needles so heal skipped; scripts/beat thrash (mtime future) while Active already `[x]`.
  - **Fixed:** Permanent beat needle `def _merge_preserve_cycle_memory` (+ bin `heal_and` race); restore live_bad/vault_ok require merge+SAVE_PRESERVE for `peer_transcript`; pin vault/bin/EXPECTED; poison **10 OK**; test-quick **185 OK**; factory **95%**; last_cycle non-noop `OVERSEER_BEAT_TRANSCRIPT_SAVE_PRESERVE_2026_09_04`; Active **0**; critical flaw cleared.
  - **Still broken:** Mac→DGX can still rewrite unprotected `scripts/beat-mac-clobber.sh` within ~9s (bin timer SoT stays strong); dirty Dispatch ~85%; HEAD flat until human commit.
  - **Needs human:** Exclude Mac sender rsync from clobbering hub-protect scripts; commit WORKING scripts when safe.

