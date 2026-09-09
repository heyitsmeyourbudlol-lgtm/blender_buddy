# Top 10 production power — task breakdown

Plan: [TOP10_PRODUCTION_POWER.md](TOP10_PRODUCTION_POWER.md) · Launch: `LAUNCH.md` Phase Top10

## Implementation order

1. [x] Lock docs + scoreboard + Newdrop-only Active policy  
2. [x] Free-desktop agent cap in config; CLEAN brain stay; Newdrop-scoped Active with verify→PR done definition  
3. [x] Cadence: ≥3 Newdrop merges this week (PRs #16/#17/#18); EXTERNAL_PROOF row hygiene; distribution wedge live  
4. [x] Public FACTORY_PROOF page + `/factory-proof`; freeze non-productive kit; streak clock started  

## Next Active slice (PM-scoped 2026-09-08)

5. [x] **Hard-Fix #66 Soft residual — kill switches env↔DB single path** (after #163 Staging Soft)  
   - **Needle:** Hard-Fix #66 — ops can miss a kill when env and DB diverge  
   - **Ship:** Soft `docs/ops/KILL_SWITCHES.md` + SECURITY_AUDIT §21.13; containment/health effective-kill report; pick one rule (DB wins **or** env mirrors) and document  
   - **AC:** one documented kill path; `npm test` + `check:controls` green; **UI untouched**; NO PAY; proof `notes/INTEGRATION_PROOF_NEWDROP_KILL_SWITCH_SOFT.md`  
   - **CLEAN Soft land:** `95c1a617` · rule=env mirrors DB · push deferred (empty git-credentials) · PR follow-on Remaining  
   - **Assignee:** `factory_engineer` (implement) · PM owns AC only  

6. [x] **Hard-Fix #69 Soft residual — secrets hygiene runbook** (after #66 Soft local)  
   - **Ship:** `docs/ops/SECRETS_HYGIENE.md` + SECURITY_AUDIT §21.14 + AGENT_WORKFLOW rotate checklist  
   - **AC:** quarterly rotate runbook linked from LONG_TERM; `npm test` + `check:controls`; **no UI**; proof `notes/INTEGRATION_PROOF_NEWDROP_SECRETS_HYGIENE_SOFT.md`  
   - **CLEAN Soft land:** `c9ef6ab7` · push deferred (empty git-credentials) · PR follow-on Remaining  
   - **Assignee:** `factory_engineer`  

7. [x] **Hard-Fix #71 Soft residual — CSP drop `'unsafe-eval'`** (CLEAN stale vs tip #117)  
   - **Ship:** omit `'unsafe-eval'` in `security-headers.ts`; keep `'unsafe-inline'` + Stripe.js  
   - **CLEAN Soft land:** `6b48e77a` · npm test 323 · check:controls 13ok · proof `notes/INTEGRATION_PROOF_NEWDROP_CSP_SOFT.md`  
   - **Assignee:** `factory_engineer`  

8. [x] **Hard-Fix #65 Soft residual — trusted proxy / XFF** (after #71 Soft local)  
   - **CLEAN Soft land:** `d7b90b0d` · `docs/ops/TRUSTED_PROXY.md` + §21.15 · proof `notes/INTEGRATION_PROOF_NEWDROP_TRUSTED_PROXY_SOFT.md`  
   - **Assignee:** `factory_engineer`  

9. [x] **Hard-Fix #75 Soft residual — cover image hotlink** (after #65 Soft local)  
   - **Ship:** `docs/ops/COVER_IMAGES.md` + SECURITY_AUDIT §21.16 (hotlink residual + deferred storage ACL)  
   - **AC:** `npm test` + `check:controls`; **no UI**; proof `notes/INTEGRATION_PROOF_NEWDROP_COVER_IMAGES_SOFT.md`  
   - **CLEAN Soft land:** `8f1acd5b` · push deferred (empty git-credentials) · PR follow-on Remaining  
   - **Assignee:** `factory_engineer`  

10. [x] **Hard-Fix #54 Soft residual — webhook SSRF DNS→connect TOCTOU** (after #75 Soft local)  
   - **Ship:** `docs/ops/WEBHOOK_SSRF.md` + SECURITY_AUDIT §21.17 (rebind residual + pin/recheck posture)  
   - **AC:** `npm test` + `check:controls`; **no UI**; proof `notes/INTEGRATION_PROOF_NEWDROP_WEBHOOK_SSRF_SOFT.md`  
   - **CLEAN Soft land:** `4865464e` · push deferred (empty git-credentials) · PR follow-on Remaining  
   - **Assignee:** `factory_engineer`  

11. [x] **Hard-Fix #62 Soft residual — versioned embed.js for breaking changes** (after #54 Soft local)  
   - **Ship:** `docs/ops/EMBED_VERSIONING.md` + SECURITY_AUDIT §21.18 (unversioned embed.js residual + dual-serve/cutover)  
   - **AC:** `npm test` + `check:controls`; **no UI**; proof `notes/INTEGRATION_PROOF_NEWDROP_EMBED_VERSIONING_SOFT.md`  
   - **CLEAN Soft land:** `33093631` · push deferred (empty git-credentials) · PR follow-on Remaining  
   - **Assignee:** `factory_engineer`  

12. [x] **Hard-Fix #88 Soft residual — embed.js hotfix purge path** (after #62 Soft local)  
   - **Ship:** `docs/ops/EMBED_HOTFIX.md` + SECURITY_AUDIT §21.19 (short TTL already shipped + CDN purge/redeploy checklist)  
   - **AC:** `npm test` + `check:controls`; **no UI**; proof `notes/INTEGRATION_PROOF_NEWDROP_EMBED_HOTFIX_SOFT.md`  
   - **CLEAN Soft land:** `059f7e2b` · push deferred (empty git-credentials) · PR follow-on Remaining  
   - **Assignee:** `factory_engineer`  

13. [x] **Hard-Fix #61 Soft residual — embed Shadow DOM / sanitize allowlist** (after #88 Soft local)  
   - **Ship:** `docs/ops/EMBED_SANITIZE.md` + SECURITY_AUDIT §21.20 (open Shadow DOM XSS residual + markdown allowlist posture)  
   - **AC:** `npm test` + `check:controls`; **no UI**; proof `notes/INTEGRATION_PROOF_NEWDROP_EMBED_SANITIZE_SOFT.md`  
   - **CLEAN Soft land:** `461cda53` · push deferred (empty git-credentials) · PR follow-on Remaining  
   - **Assignee:** `factory_engineer`  

14. [x] **Hard-Fix #63 Soft residual — CDN/WAF edge residual** (after #61 Soft local)  
   - **Ship:** `docs/ops/CDN_WAF.md` + SECURITY_AUDIT §21.21 (app-layer RL only residual + DNS/WAF cutover posture)  
   - **AC:** `npm test` + `check:controls`; **no UI**; proof `notes/INTEGRATION_PROOF_NEWDROP_CDN_WAF_SOFT.md`  
   - **CLEAN Soft land:** `25c0c11b` · push deferred (empty git-credentials) · PR follow-on Remaining  
   - **Assignee:** `factory_engineer`  

15. [x] **Hard-Fix #64 Soft residual — Postgres RL hot-path** (after #63 Soft local)  
   - **Ship:** `docs/ops/POSTGRES_RL.md` + SECURITY_AUDIT §21.22 (Postgres `consume_rate_limit` contention residual + Redis/Upstash deferred; keep PG failClosed backup)  
   - **AC:** `npm test` + `check:controls`; **no UI**; proof `notes/INTEGRATION_PROOF_NEWDROP_POSTGRES_RL_SOFT.md`  
   - **CLEAN Soft land:** `f05ce4e1` · push deferred (empty git-credentials) · PR follow-on Remaining  
   - **Assignee:** `factory_engineer`  

16. [x] **Hard-Fix #72 Soft residual — account erasure / GDPR path** (after #64 Soft local)  
   - **Ship:** `docs/ops/ACCOUNT_ERASURE.md` + SECURITY_AUDIT §21.23 (playbook-only / PITR lag residual + Soft checklist)  
   - **AC:** `npm test` + `check:controls`; **no UI**; proof `notes/INTEGRATION_PROOF_NEWDROP_ACCOUNT_ERASURE_SOFT.md`  
   - **CLEAN Soft land:** `cb86980a` · push deferred (empty git-credentials) · PR follow-on Remaining  
   - **Assignee:** `factory_engineer`  

17. [x] **Hard-Fix #73 Soft residual — subscriber PII export / legal hold** (after #72 Soft local)  
   - **Ship:** `docs/ops/SUBSCRIBER_PII_EXPORT.md` + SECURITY_AUDIT §21.24 (owner CSV exists; Soft residual = audit log + legal-hold freeze + Soft GDPR/hold checklists)  
   - **AC:** `npm test` + `check:controls`; **no UI**; proof `notes/INTEGRATION_PROOF_NEWDROP_SUBSCRIBER_PII_EXPORT_SOFT.md`  
   - **CLEAN Soft land:** `1d65b779` · push deferred (empty git-credentials) · PR follow-on Remaining/Creative  
   - **Assignee:** `factory_engineer`  

18. [x] **Hard-Fix #82 Soft residual — live privilege SQL not in CI** (after #73 Soft local)  
   - **Ship:** `docs/ops/PRIVILEGE_SQL_CI.md` + SECURITY_AUDIT §21.25 (RLS/EXECUTE privilege-SQL residual + Soft fixture/CI checklist)  
   - **AC:** `npm test` + `check:controls`; **no UI**; proof `notes/INTEGRATION_PROOF_NEWDROP_PRIVILEGE_SQL_CI_SOFT.md`  
   - **CLEAN Soft land:** `656b98cf` · push deferred (empty git-credentials) · PR follow-on Remaining/Creative  
   - **Assignee:** `factory_engineer`  

19. [x] **Hard-Fix #83 Soft residual — branch protection / required checks** (after #82 Soft local)  
   - **Ship:** `docs/ops/BRANCH_PROTECTION.md` + SECURITY_AUDIT §21.26 (soft PR gate + Pro residual for required checks / no force-push)  
   - **AC:** `npm test` + `check:controls`; **no UI**; proof `notes/INTEGRATION_PROOF_NEWDROP_BRANCH_PROTECTION_SOFT.md`  
   - **CLEAN Soft land:** `789b3281` · push deferred (empty git-credentials) · PR follow-on Remaining/Creative  
   - **Assignee:** `factory_engineer`  

20. [x] **Hard-Fix #85 Soft residual — external pentest still Residual** (after #83 Soft local)  
   - **Ship:** `docs/ops/PENTEST.md` + SECURITY_AUDIT §21.27 (ARR trigger Soft residual + Soft scope/checklist; no UI)  
   - **AC:** `npm test` + `check:controls`; **no UI**; proof `notes/INTEGRATION_PROOF_NEWDROP_PENTEST_SOFT.md`  
   - **CLEAN Soft land:** `0b0bbab6` · push deferred (empty git-credentials) · PR follow-on Remaining/Creative  
   - **Assignee:** `factory_engineer`  

21. [x] **Hard-Fix #86 Soft residual — migration expand-contract** (after #85 Soft local)  
   - **Ship:** `docs/ops/MIGRATION_EXPAND_CONTRACT.md` + SECURITY_AUDIT §21.28 (expand-contract Soft residual + Soft checklist for money/auth/public keys; no UI)  
   - **AC:** `npm test` + `check:controls`; **no UI**; proof `notes/INTEGRATION_PROOF_NEWDROP_MIGRATION_EXPAND_CONTRACT_SOFT.md`  
   - **CLEAN Soft land:** `da45029e` · push deferred (empty git-credentials) · PR follow-on Remaining/Creative  
   - **Assignee:** `factory_engineer`  

22. [x] **Hard-Fix #84 Soft residual — CodeQL / Semgrep / DAST** (after #86 Soft local)  
   - **Ship:** `docs/ops/SAST_DAST.md` + SECURITY_AUDIT §21.29 (Soft residual: tip CodeQL/Semgrep Soft-shipped; DAST/auth DAST Soft residual; Soft checklist; no UI)  
   - **AC:** `npm test` + `check:controls`; **no UI**; proof `notes/INTEGRATION_PROOF_NEWDROP_SAST_DAST_SOFT.md`  
   - **CLEAN Soft land:** `12b0034e` · push deferred (empty git-credentials) · PR follow-on Remaining/Creative  
   - **Assignee:** `factory_engineer`  

23. [x] **Hard-Fix #87 Soft residual — observability alerts** (after #84 Soft local)  
   - **Ship:** `docs/ops/OBSERVABILITY_ALERTS.md` + SECURITY_AUDIT §21.30 (Soft residual: tip Soft-shipped product alerts where present; Soft checklist / founder query; no UI)  
   - **AC:** `npm test` + `check:controls`; **no UI**; proof `notes/INTEGRATION_PROOF_NEWDROP_OBSERVABILITY_ALERTS_SOFT.md`  
   - **CLEAN Soft land:** `165d1c88` · push deferred (empty git-credentials) · PR follow-on Remaining/Creative  
   - **Assignee:** `factory_engineer`  


24. [x] **Hard-Fix #33 Soft residual — refund-abuse window app↔SQL** (after tip-cover #177 Soft Soft)
   - **Ship:** `REFUND_ABUSE_WINDOW_DAYS` + `docs/ops/REFUND_ABUSE.md` + SECURITY_AUDIT §21.38
   - **CLEAN Soft Soft land:** `24520321` · wt=`soft-hf33-refund-20260908T141451` · push deferred (empty git-credentials) · PR follow-on Creative
   - **Assignee:** `factory_engineer`

25. [x] **Hard-Fix #34 Soft Soft — user_account_ids SECURITY DEFINER** (after Soft Soft #33)
   - **Ship:** `docs/ops/SECURITY_DEFINER.md` + SECURITY_AUDIT §21.39 · `security-definer-soft.test.ts`
   - **CLEAN Soft Soft land:** `5a8596ee` · wt=`soft-hf34-secdef-20260908T142449` · push deferred · proof `notes/INTEGRATION_PROOF_NEWDROP_SECURITY_DEFINER_SOFT.md`
   - **Assignee:** `top10_implementer`


26. [x] **Hard-Fix #32 Soft Soft — Stripe customer idempotency** (after Soft Soft #34)
   - **Ship:** `docs/ops/STRIPE_CUSTOMER_IDEMPOTENCY.md` + SECURITY_AUDIT §21.40 · `stripe-customer-idempotency-soft.test.ts`
   - **CLEAN Soft Soft land:** `f500a21e` · wt=`soft-hf32-stripe-cust-20260908T143017`
   - **Soft Soft tip-stamp:** [#286](https://github.com/heyitsmeyourbudlol-lgtm/caas-changelog/pull/286) merge `4c822686` · product `fced0b9c` · Soft Soft pin 3ok · proof `notes/INTEGRATION_PROOF_NEWDROP_STRIPE_CUSTOMER_IDEMPOTENCY_SOFT.md`
   - **Assignee:** `top10_implementer`

27. [x] **Hard-Fix #30 Soft Soft — founding-member always-true** (after Soft Soft #32)
   - **Ship:** `docs/ops/FOUNDING_MEMBER.md` + SECURITY_AUDIT §21.41 · `founding-member-soft.test.ts`
   - **CLEAN Soft Soft land:** `7ce8d48d` · wt=`soft-hf30-founding-20260908T143521` · push deferred · proof `notes/INTEGRATION_PROOF_NEWDROP_FOUNDING_MEMBER_SOFT.md`
   - **Assignee:** `top10_implementer`

28. [x] **Hard-Fix #29 Soft Soft — unban plan_status** (hub writeback)
   - **Ship:** `docs/ops/UNBAN_PLAN_STATUS.md` + §21.42 · Soft Soft `4c9696e5` · unban-plan-status-soft.test 1ok · check:controls 12ok
   - **Proof:** `notes/INTEGRATION_PROOF_NEWDROP_UNBAN_PLAN_STATUS_SOFT.md`
   - **Assignee:** `top10_implementer`

29. [x] **Hard-Fix #45 Soft Soft — apex multi-label public suffix pin**
   - **Ship:** `MULTI_LABEL_PUBLIC_SUFFIXES` + `docs/ops/APEX_CUSTOM_DOMAINS.md` + §21.43 · Soft Soft `445a4512`
   - **Proof:** `notes/INTEGRATION_PROOF_NEWDROP_APEX_CUSTOM_DOMAINS_SOFT.md`
   - **Assignee:** `factory_engineer`

30. [x] **Hard-Fix #47 Soft Soft — verified before SSL ready**
   - **Ship:** Soft Soft `isSslReadyFromVercelDomainJson` + `docs/ops/VERIFIED_BEFORE_SSL.md` + §21.44 · Soft Soft `c0351803`
   - **Proof:** `notes/INTEGRATION_PROOF_NEWDROP_VERIFIED_BEFORE_SSL_SOFT.md`
   - **Assignee:** `top10_implementer`

31. [x] **Hard-Fix #48 Soft Soft — Vercel domain attach optional/fragile**
   - **Ship:** Soft Soft `isVercelDomainApiConfigured` + `vercelAttachVerifyError` + `docs/ops/VERCEL_DOMAIN_ATTACH.md` + §21.45 · Soft Soft `8f173fd0`
   - **Proof:** `notes/INTEGRATION_PROOF_NEWDROP_VERCEL_DOMAIN_ATTACH_SOFT.md`
   - **Assignee:** `top10_implementer`

32. [x] **Hard-Fix #50 Soft Soft — Orphan Vercel domains on delete/decommission**
   - **Ship:** Soft Soft `shouldDetachDomainOnDecommission` + `detachDomainBestEffort` + `docs/ops/ORPHAN_VERCEL_DOMAINS.md` + §21.46 · Soft Soft `bf9ef46d`
   - **Proof:** `notes/INTEGRATION_PROOF_NEWDROP_ORPHAN_VERCEL_DOMAINS_SOFT.md`
   - **Assignee:** `top10_implementer`

33. [x] **Hard-Fix #51 Soft Soft — Cookie/session quirks on custom domains**
   - **Ship:** Soft Soft `normalizeUnlockCookieHost` + `unlockCookieHmacPayload` + `docs/ops/COOKIE_SESSION_CUSTOM_DOMAINS.md` + §21.47 · Soft Soft `83f80b90`
   - **Proof:** `notes/INTEGRATION_PROOF_NEWDROP_COOKIE_SESSION_CUSTOM_DOMAINS_SOFT.md`
   - **Assignee:** `top10_implementer`

34. [x] **Hard-Fix #89 Soft Soft — Widget identity across partitioned storage**
   - **Ship:** Soft Soft `docs/ops/WIDGET_PARTITIONED_IDENTITY.md` + §21.49 · Soft Soft `f6c6a996`
   - **Proof:** `notes/INTEGRATION_PROOF_NEWDROP_WIDGET_PARTITIONED_IDENTITY_SOFT.md`
   - **Assignee:** `top10_implementer`

35. [x] **Hard-Fix #56 Soft Soft — Schedule timezone / DST**
   - **Ship:** Soft Soft `scheduleInputHasExplicitOffset` + `parseScheduleWhen` Z/offset gate + `docs/ops/SCHEDULE_TIMEZONE_DST.md` + §21.50 · Soft Soft land `0cf901f9` · Soft Soft tip-stamp [#258](https://github.com/heyitsmeyourbudlol-lgtm/caas-changelog/pull/258) `95368454` / product `157a6a2c`
   - **Proof:** `notes/INTEGRATION_PROOF_NEWDROP_SCHEDULE_TIMEZONE_DST_SOFT.md`
   - **Assignee:** `top10_implementer`

36. [x] **Hard-Fix #57 Soft Soft — Resend bounce/complaint Soft Soft tip stamp**
   - **Ship:** Soft Soft `docs/ops/RESEND_BOUNCE_COMPLAINT.md` + §21.51 · Soft Soft `28d78dad`
   - **Proof:** `notes/INTEGRATION_PROOF_NEWDROP_RESEND_BOUNCE_COMPLAINT_SOFT.md`
   - **Assignee:** `top10_implementer`

37. [x] **Hard-Fix #78 Soft Soft — OpenAI hard $ circuit breaker Soft Soft tip stamp**
   - **Ship:** Soft Soft `docs/ops/OPENAI_CIRCUIT_BREAKER.md` + §21.52 · Soft Soft `5b9b7c21`
   - **Proof:** `notes/INTEGRATION_PROOF_NEWDROP_OPENAI_CIRCUIT_BREAKER_SOFT.md`
   - **Assignee:** `top10_implementer`

38. [x] **Hard-Fix #79 Soft Soft — Support URL allowlist Soft Soft tip stamp**
   - **Ship:** Soft Soft `scrubSupportOutputUrls` + `docs/ops/SUPPORT_URL_ALLOWLIST.md` + §21.53 · Soft Soft `91b25d2c`
   - **Proof:** `notes/INTEGRATION_PROOF_NEWDROP_SUPPORT_URL_ALLOWLIST_SOFT.md`
   - **Assignee:** `top10_implementer`

39. [x] **Hard-Fix #77 Soft Soft — AI draft shared OpenAI cost Soft Soft tip stamp**
   - **Ship:** Soft Soft `docs/ops/AI_DRAFT_SHARED_COST.md` + §21.54 · Soft Soft `222ca1f0`
   - **Proof:** `notes/INTEGRATION_PROOF_NEWDROP_AI_DRAFT_SHARED_COST_SOFT.md`
   - **Assignee:** `top10_implementer`

40. [x] **Hard-Fix #100 Soft Soft — Session revoke-all Soft Soft tip stamp**
   - **Ship:** Soft Soft `docs/ops/SESSION_REVOKE_ALL.md` + §21.55 · Soft Soft `1c986e41`
   - **Proof:** `notes/INTEGRATION_PROOF_NEWDROP_SESSION_REVOKE_ALL_SOFT.md`
   - **Assignee:** `top10_implementer`

41. [x] **Hard-Fix #25 Soft Soft — Custom Auth domain Soft Soft tip stamp**
   - **Ship:** Soft Soft `docs/ops/CUSTOM_AUTH_DOMAIN.md` + §21.56 · Soft Soft `86a55ef5`
   - **Proof:** `notes/INTEGRATION_PROOF_NEWDROP_CUSTOM_AUTH_DOMAIN_SOFT.md`
   - **Assignee:** `top10_implementer`

42. [x] **Hard-Fix #97 Soft Soft — Service-role blast radius Soft Soft tip stamp**
   - **Ship:** Soft Soft `docs/ops/SERVICE_ROLE_BLAST.md` + §21.37 · Soft Soft `598f7b9b`
   - **Proof:** `notes/INTEGRATION_PROOF_NEWDROP_SERVICE_ROLE_BLAST_SOFT.md`
   - **Assignee:** `top10_implementer`

43. [x] **Hard-Fix #35 Soft Soft — Editor personal trial Soft Soft tip stamp**
   - **Ship:** Soft Soft `docs/ops/EDITOR_PERSONAL_TRIAL.md` + §21.57 · Soft Soft `d9fa3ca5`
   - **Proof:** `notes/INTEGRATION_PROOF_NEWDROP_EDITOR_PERSONAL_TRIAL_SOFT.md`
   - **Assignee:** `top10_implementer`

44. [x] **Hard-Fix #36 Soft Soft — Invite accept / token reuse Soft Soft tip stamp**
   - **Ship:** Soft Soft `docs/ops/INVITE_TOKEN_REUSE.md` + §21.29 · [#214](https://github.com/heyitsmeyourbudlol-lgtm/caas-changelog/pull/214) `471bf15`
   - **Proof:** `notes/INTEGRATION_PROOF_NEWDROP_INVITE_TOKEN_REUSE_SOFT.md`
   - **Assignee:** `top10_implementer`

45. [x] **Hard-Fix #37 Soft Soft — Seat-cap concurrency Soft Soft tip stamp**
   - **Ship:** Soft Soft `docs/ops/SEAT_CAP_CONCURRENCY.md` + §21.28 · [#211](https://github.com/heyitsmeyourbudlol-lgtm/caas-changelog/pull/211) `d2cf25b`
   - **Proof:** `notes/INTEGRATION_PROOF_NEWDROP_SEAT_CAP_CONCURRENCY_SOFT.md`
   - **Assignee:** `top10_implementer`


## Done when

- [ ] Scoreboard bars hit for 4 consecutive weeks  
- [x] FACTORY_PROOF.md lists verifiable merges + uptime claim  
- [x] Active theater share ≤10% sustained (Top10 Active = Newdrop-only open lines)  
