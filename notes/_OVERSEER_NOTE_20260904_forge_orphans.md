# Overseer stagnation note

- **2026-09-04 stagnation dispatch (auth-deferred / forge orphans)**
  - **Found:** deferred + auth-not-ready theater; root cause = 15–19 orphan CaaS cursor-agents after inactive product-forge starving verify quiet-cap; queue_fp flat; factory dipped then recovered. Mac rsync clobbered scrub hooks on run_peer_tasks/improve and deleted new modules.
  - **Fixed:** Live scrub of CaaS orphans; peer_product_forge uses CAAS_ROOT+/~/CaaS; scrub wired into dgx_ram_budget.trim_unittest_storm (every verify-lane prep); vault+restore needles for dgx_ram_budget; compact Done orphans. Non-noop delivery restored; factory ~82%.
  - **Still broken:** cursor-agent auth (human login); Mac rsync races; dirty tree Dispatch ~85%; Active re-inflation.
  - **Needs human:** cursor-agent login; commit WIP; keep hub-protect timer enabled.
