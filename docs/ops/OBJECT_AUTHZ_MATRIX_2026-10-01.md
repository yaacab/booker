# Матрица маршрутов API: зависимости и проверки доступа (01.10.2026)

Снимок локального рабочего дерева на HEAD `834fb22d71ad2d83b212a5ad5ef1e7ef9b485907`. Таблица сгенерирована из зарегистрированных FastAPI router endpoints. `Deps` отражает граф `Depends`; `ACL-вызовы` — статический поиск прямых вызовов в обработчике. Вызов guard не доказывает корректный порядок проверки и права на конкретный объект. Пустая ячейка не доказывает публичность: проверка может быть в helper. Отрицательный тест указан только там, где в этом security-срезе явно сопоставлен с маршрутом; `—` значит адресное сопоставление не завершено, а не отсутствие всех тестов.

Роли: `current_user` = аутентификация, `require_admin` = platform admin, `require_org_writer` = owner/admin/manager организации; `membership_ok`/`require_org_member` могут допускать viewer и требуют проверки по действию. `auth_context` даёт пользователя и сессию, но сам по себе не проверяет tenant. Для upload/download дополнительно требуется admin 2FA step-up. Денежные мутации должны сохранять server-side расчёт и state guards. Последний столбец включает не только запреты по роли/объекту, но и отрицательные проверки подписи, состояния и срока действия; его заполнение нельзя считать доказательством полного authz-покрытия маршрута.

| Метод | Маршрут | Deps (основные) | ACL-вызовы в endpoint | Адресный отрицательный тест |
|---|---|---|---|---|
| GET | `/health` | — | — | test_public_reference_invariants.py: privacy — email API key and merchant ID values absent |
| GET | `/readiness` | — | — | test_health.py: state — missing live-payment inputs returns 503 |
| POST | `/auth/register` | — | — | test_identity.py: state/legal — no consent, no User write |
| POST | `/auth/login` | — | ensure_admin_2fa_configured, mark_admin_2fa_verified | test_identity.py: concurrent old-password login waits for reset on file SQLite |
| POST | `/auth/logout` | auth_context, HTTPBearer | — | test_identity.py: authz — anonymous denied; other session intact |
| POST | `/auth/recover` | — | — | test_identity.py: privacy — existing/unknown email same response |
| POST | `/auth/recover/confirm` | — | — | test_identity.py: reset consumes token/revokes sessions |
| GET | `/notifications` | current_user, auth_context, HTTPBearer | — | test_notifications.py: privacy — guest denied, foreign recipient hidden |
| GET | `/me` | current_user, auth_context, HTTPBearer | membership | test_identity.py: privacy — foreign org header does not leak membership |
| POST | `/orgs` | current_user, auth_context, HTTPBearer | — | test_identity.py: authz — anonymous denied without writes |
| GET | `/orgs/{org_id}` | current_user, auth_context, HTTPBearer | require_org_member | test_identity.py: foreign org denied |
| POST | `/orgs/{org_id}/members` | current_user, auth_context, HTTPBearer | membership | test_identity.py: outsider/viewer cannot add owner |
| POST | `/orgs/{org_id}/invitations` | current_user, auth_context, HTTPBearer | membership | test_organization_invitations.py: outsider/viewer/manager, changed-key replay |
| POST | `/organization-invitations/accept` | current_user, auth_context, HTTPBearer | membership | test_organization_invitations.py: foreign email/revoked/expired/replay |
| POST | `/orgs/{org_id}/invitations/{invitation_id}/revoke` | current_user, auth_context, HTTPBearer | membership | test_organization_invitations.py: foreign org/viewer/manager |
| POST | `/me/active-org` | current_user, auth_context, HTTPBearer | require_org_member | test_identity.py: foreign org switch denied |
| POST | `/analytics/events` | current_user, auth_context, HTTPBearer | — | test_analytics.py: authz — anonymous denied |
| GET | `/categories` | — | — | test_public_reference_invariants.py: privacy/state — unpublished hidden, repeat read idempotent |
| POST | `/artists` | current_user, auth_context, HTTPBearer | require_org_writer | test_creation_authz_gaps.py: authz — viewer/outsider denied without writes |
| POST | `/venues` | current_user, auth_context, HTTPBearer | require_org_writer | test_creation_authz_gaps.py: authz — viewer/outsider denied without writes |
| PATCH | `/artists/{artist_id}/publication-evidence` | current_user, auth_context, HTTPBearer | require_org_owner_or_admin_member | test_supply_mutation_authz_gaps.py: viewer/foreign owner denied without writes |
| PUT | `/artists/{artist_id}/publication-evidence` | current_user, auth_context, HTTPBearer | require_org_owner_or_admin_member | test_publication_eligibility.py: manager/outsider/admin without membership |
| PATCH | `/venues/{venue_id}/publication-evidence` | current_user, auth_context, HTTPBearer | require_org_owner_or_admin_member | test_supply_mutation_authz_gaps.py: viewer/foreign owner denied without writes |
| PUT | `/venues/{venue_id}/publication-evidence` | current_user, auth_context, HTTPBearer | require_org_owner_or_admin_member | test_publication_eligibility.py: manager/outsider |
| POST | `/venues/{venue_id}/photos` | current_user, auth_context, HTTPBearer | require_org_owner_or_admin_member | test_supply_mutation_authz_gaps.py: viewer/foreign owner denied without writes |
| PUT | `/venues/{venue_id}/photos` | current_user, auth_context, HTTPBearer | require_org_owner_or_admin_member | test_publication_eligibility.py: manager/outsider |
| PUT | `/artists/{artist_id}/publication` | current_user, auth_context, HTTPBearer | — | test_publication_eligibility.py: outsider/stale/busy-only calendar |
| PUT | `/venues/{venue_id}/publication` | current_user, auth_context, HTTPBearer | — | test_publication_eligibility.py: manager/outsider/new hall without calendar |
| GET | `/venues/{venue_id}/halls` | _optional_user, HTTPBearer | membership | test_public_catalog_privacy_gaps.py: privacy — draft guest/outsider denied |
| POST | `/venues/{venue_id}/halls` | current_user, auth_context, HTTPBearer | require_org_writer | test_supply_mutation_authz_gaps.py: viewer/foreign owner denied without writes |
| POST | `/artists/{artist_id}/tariffs` | current_user, auth_context, HTTPBearer | require_org_writer | test_supply_mutation_authz_gaps.py: viewer/foreign owner denied without writes |
| POST | `/venues/{venue_id}/tariffs` | current_user, auth_context, HTTPBearer | require_org_writer | test_supply_mutation_authz_gaps.py: viewer/foreign owner denied without writes |
| POST | `/slots` | current_user, auth_context, HTTPBearer | require_org_writer | test_supply_mutation_authz_gaps.py: artist/hall viewer/foreign owner denied without writes |
| GET | `/organizations/{org_id}/calendar-targets` | current_user, auth_context, HTTPBearer | require_org_member | test_vacation.py: foreign org denied |
| POST | `/calendar/ical/import` | current_user, auth_context, HTTPBearer | require_org_writer | test_vacation.py: foreign resource binding; test_ical_import.py: viewer |
| GET | `/organizations/{org_id}/vacation` | current_user, auth_context, HTTPBearer | require_org_member | test_vacation.py: foreign org denied |
| POST | `/calendar/vacation` | current_user, auth_context, HTTPBearer | require_org_writer | test_vacation.py: viewer/foreign resource binding/outsider |
| DELETE | `/calendar/vacation` | current_user, auth_context, HTTPBearer | require_org_writer | test_vacation.py: foreign resource binding |
| GET | `/catalog/search` | — | — | test_public_catalog_privacy_gaps.py: privacy — draft excluded |
| GET | `/catalog/public-index` | — | — | test_public_catalog_privacy_gaps.py: privacy — draft excluded |
| GET | `/catalog/public-status/{resource_type}/{resource_id}` | — | — | test_public_catalog_privacy_gaps.py: privacy — draft 404 |
| GET | `/catalog/demo/venues` | — | — | test_public_catalog_privacy_gaps.py: privacy — unreviewed import excluded |
| GET | `/venues/{venue_id}` | _optional_user, HTTPBearer | membership | test_public_catalog_privacy_gaps.py: privacy — draft 404 |
| GET | `/artists/{artist_id}` | _optional_user, HTTPBearer | membership | test_public_catalog_privacy_gaps.py: privacy — draft 404 |
| GET | `/favorites` | current_user, auth_context, HTTPBearer | — | test_favorites.py: unpublished profile hidden from saved list |
| POST | `/favorites` | current_user, auth_context, HTTPBearer | — | test_favorites.py: authz — foreign org denied without writes |
| DELETE | `/favorites/target/{target_type}/{target_id}` | current_user, auth_context, HTTPBearer | — | test_favorites.py: authz — foreign org denied without writes |
| DELETE | `/favorites/{favorite_id}` | current_user, auth_context, HTTPBearer | membership | test_favorites.py: authz — outsider 404, row retained |
| POST | `/services` | current_user, auth_context, HTTPBearer | require_org_writer | test_services.py: viewer, foreign profile, venue bound to artist |
| GET | `/service-templates` | — | — | test_public_reference_invariants.py: privacy/state — public fields only, stable repeat read |
| POST | `/services/from-template` | current_user, auth_context, HTTPBearer | require_org_writer | test_supply_mutation_authz_gaps.py: artist/venue viewer/foreign owner denied without writes |
| PUT | `/services/{service_id}/profile` | current_user, auth_context, HTTPBearer | require_org_writer | test_services.py: viewer and foreign profile denied |
| GET | `/services/public` | — | — | test_services.py: unverified/unbound/unpublished profile hidden |
| GET | `/organizations/{org_id}/supply-completeness` | current_user, auth_context, HTTPBearer | require_org_member | test_supply_completeness.py: authz — foreign org 403 |
| GET | `/services` | current_user, auth_context, HTTPBearer | require_org_member | test_services.py: foreign org denied |
| POST | `/events` | current_user, auth_context, HTTPBearer | require_org_writer | test_creation_authz_gaps.py: authz — viewer/outsider denied without writes |
| GET | `/events` | current_user, auth_context, HTTPBearer | require_org_member | test_event_authz_gaps.py: foreign organization filter denied; tenant list isolated |
| GET | `/events/{event_id}` | current_user, auth_context, HTTPBearer | require_org_member | test_event_authz_gaps.py: outsider denied; viewer read allowed |
| GET | `/events/{event_id}/offline-pack` | current_user, auth_context, HTTPBearer | require_org_member | test_offline_pack.py: anonymous/foreign org |
| GET | `/events/{event_id}/day-status` | current_user, auth_context, HTTPBearer | require_org_member | test_offline_pack.py: anonymous/foreign org |
| POST | `/events/{event_id}/check-in` | current_user, auth_context, HTTPBearer | require_org_writer | test_event_day_checkin.py: stranger/payment blocker denied |
| POST | `/events/{event_id}/check-out` | current_user, auth_context, HTTPBearer | require_org_writer | test_event_authz_gaps.py: viewer/foreign tenant denied without writes |
| POST | `/bookings/{booking_id}/check-in` | current_user, auth_context, HTTPBearer | _booking_participant_orgs | test_event_day_checkin.py: payment blocker denied |
| POST | `/bookings/{booking_id}/check-out` | current_user, auth_context, HTTPBearer | _booking_participant_orgs | test_event_day_checkin.py: viewer denied |
| GET | `/events/{event_id}/requirements/{requirement_id}/replacement` | current_user, auth_context, HTTPBearer | require_org_member | test_offline_pack.py: outsider/foreign requirement |
| POST | `/bookings/{booking_id}/cancel` | auth_context, HTTPBearer | TeamMember role query, ensure_admin_2fa_session | test_messages_inbox.py: transferred org; test_authz_regressions.py: dual member writer/admin without TOTP |
| PUT | `/events/{event_id}/requirements` | current_user, auth_context, HTTPBearer | require_org_writer | test_event_authz_gaps.py: viewer/foreign tenant denied without writes |
| GET | `/requests` | current_user, auth_context, HTTPBearer | require_org_member | test_messages_inbox.py: transferred org; legacy fallback |
| GET | `/bookings` | current_user, auth_context, HTTPBearer | require_org_member | test_messages_inbox.py: transferred org |
| POST | `/quick-request` | current_user, auth_context, HTTPBearer | require_org_writer | test_event_authz_gaps.py: foreign event/viewer denied without writes |
| POST | `/events/{event_id}/requests` | current_user, auth_context, HTTPBearer | require_org_writer | test_event_authz_gaps.py: viewer/foreign tenant denied without writes |
| POST | `/requests/{request_id}/offers` | current_user, auth_context, HTTPBearer | require_org_writer | test_messages_inbox.py: transferred supplier/legacy without conversation |
| POST | `/offers/{offer_id}/versions` | current_user, auth_context, HTTPBearer | membership_ok, require_org_writer | test_messages_inbox.py: outsider denied |
| POST | `/offers/{offer_id}/ack` | current_user, auth_context, HTTPBearer | — | test_messages_inbox.py: outsider denied; test_quote_versioning.py: stale/missing quote denied |
| POST | `/bookings/{booking_id}/hold` | current_user, auth_context, HTTPBearer | _booking_participant_orgs, membership_ok, require_org_writer | test_authz_regressions.py: viewer, outsider |
| POST | `/events/{event_id}/holds/atomic` | current_user, auth_context, HTTPBearer | require_org_writer | test_multi_hall_atomic.py: viewer/outsider denied without partial capture |
| POST | `/holds/expire` | — | — | test_authz_regressions.py: anonymous denied without internal token |
| POST | `/bookings/{booking_id}/attachments` | auth_context, HTTPBearer | _booking_participant_orgs, ensure_admin_2fa_session, membership_ok, require_org_writer | test_attachments.py: outsider/admin 2FA, oversized declared/chunked/understated body before multipart parse |
| GET | `/bookings/{booking_id}/attachments/{attachment_id}/download` | auth_context, HTTPBearer | _booking_participant_orgs, ensure_admin_2fa_session, membership_ok | test_attachments.py: outsider/anonymous/admin 2FA/quarantine/tamper/other booking |
| GET | `/deal-room/{booking_id}` | current_user, auth_context, HTTPBearer | _booking_participant_orgs, membership_ok | test_messages_inbox.py: outsider denied |
| POST | `/bookings/{booking_id}/disputes` | current_user, auth_context, HTTPBearer | _booking_participant_orgs, membership_ok, require_org_writer | test_authz_regressions.py: viewer |
| GET | `/bookings/{booking_id}/disputes` | current_user, auth_context, HTTPBearer | _booking_participant_orgs, membership_ok | test_disputes.py: outsider denied without details |
| POST | `/disputes/{dispute_id}/evidence` | current_user, auth_context, HTTPBearer | _booking_participant_orgs, membership_ok, require_org_writer | test_authz_regressions.py: outsider/open/closed; test_disputes.py: tampered clean file |
| GET | `/requests/{request_id}/conversation` | current_user, auth_context, HTTPBearer | _require_conversation_access | test_messages_inbox.py: outsider/admin without membership denied |
| POST | `/requests/{request_id}/messages` | current_user, auth_context, HTTPBearer | _require_conversation_access | test_messages_inbox.py: viewer denied |
| GET | `/messages/inbox` | current_user, auth_context, HTTPBearer | — | test_messages_inbox.py: outsider empty; foreign X-Booker-Org denied |
| POST | `/conversations/{conversation_id}/read` | current_user, auth_context, HTTPBearer | _require_conversation_access | test_messages_inbox.py: outsider denied without read state |
| POST | `/deal-room/{booking_id}/messages` | current_user, auth_context, HTTPBearer | _require_conversation_access | test_authz_regressions.py: outsider/viewer |
| GET | `/sse/bookings/{booking_id}` | — | _booking_participant_orgs, membership_ok | test_authz_regressions.py: anonymous/outsider denied |
| POST | `/bookings/{booking_id}/contract` | current_user, auth_context, HTTPBearer | _booking_participant_orgs, membership | test_authz_regressions.py: viewer/admin without membership; outsider |
| POST | `/contracts/{contract_id}/sign` | current_user, auth_context, HTTPBearer | _booking_participant_orgs | test_quote_versioning.py: viewer/ambiguous actor |
| POST | `/bookings/{booking_id}/payments` | current_user, auth_context, HTTPBearer | _booking_participant_orgs, membership | test_payments.py: outsider/viewer/platform admin |
| POST | `/payments/{payment_id}/external-report` | current_user, auth_context, HTTPBearer | _booking_participant_orgs, membership | test_external_payment_confirm.py: outsider/viewer/changed-key replay |
| POST | `/payments/webhook` | — | — | test_payments.py: forged signature denied without payment, booking, event or movement write |
| POST | `/payments/{payment_id}/stub-complete` | current_user, auth_context, HTTPBearer | _booking_participant_orgs, membership | test_authz_regressions.py: viewer |
| POST | `/bookings/{booking_id}/reviews` | current_user, auth_context, HTTPBearer | _membership_ok | test_reviews.py: outsider/viewer denied without review or audit |
| GET | `/organizations/{org_id}/reviews` | — | — | test_reviews.py: public list omits booking_id/author_user_id (privacy, not ACL) |
| GET | `/artists/{artist_id}/reviews` | — | — | test_reviews.py: public list omits booking_id/author_user_id (privacy, not ACL) |
| GET | `/venues/{venue_id}/reviews` | — | — | test_public_catalog_privacy_gaps.py: privacy — draft 404 |
| POST | `/briefs` | current_user, auth_context, HTTPBearer | require_org_writer | test_briefs.py: foreign event |
| GET | `/briefs` | — | — | test_briefs.py: privacy — linked private event fields excluded |
| GET | `/briefs/{brief_id}` | — | — | test_briefs.py: privacy — linked private event fields excluded |
| POST | `/briefs/{brief_id}/close` | current_user, auth_context, HTTPBearer | require_org_writer | test_briefs.py: viewer/other tenant denied without state change |
| POST | `/briefs/{brief_id}/responses` | current_user, auth_context, HTTPBearer | require_org_writer | test_briefs.py: unpublished supplier denied |
| GET | `/briefs/{brief_id}/responses` | current_user, auth_context, HTTPBearer | _membership_ok | test_briefs.py: supplier outsider denied |
| POST | `/shortlists` | current_user, auth_context, HTTPBearer | require_org_writer (via helper) | test_shortlists.py: viewer denied |
| POST | `/shortlists/{shortlist_id}/revoke` | current_user, auth_context, HTTPBearer | — | test_shortlists.py: stranger denied |
| GET | `/shared/{token}` | — | — | test_shortlists.py: revoked token returns 404 |
| GET | `/compare` | — | — | test_public_catalog_privacy_gaps.py: privacy — draft venues rejected |
| POST | `/venues/{venue_id}/claims` | current_user, auth_context, HTTPBearer | — | test_trust_outbox.py: viewer/foreign owner denied without claim or audit |
| GET | `/venues/{venue_id}/claims` | current_user, auth_context, HTTPBearer | — | test_trust_outbox.py: non-operator denied |
| POST | `/support/assistant/sessions` | current_user, auth_context, HTTPBearer | _resolve_org | test_support_agent.py: outsider denied foreign organization |
| GET | `/support/assistant/sessions/{session_id}` | current_user, auth_context, HTTPBearer | _require_user_agent_session | test_support_agent.py: outsider/same-org non-author/revoked member denied |
| POST | `/support/assistant/sessions/{session_id}/messages` | current_user, auth_context, HTTPBearer | _require_user_agent_session | test_support_agent.py: same-org non-author/after escalation denied |
| POST | `/support/assistant/sessions/{session_id}/escalate` | current_user, auth_context, HTTPBearer | _require_user_agent_session | test_support_agent.py: same-org non-author/empty handoff denied |
| POST | `/support/assistant/exchanges/{exchange_id}/feedback` | current_user, auth_context, HTTPBearer | _require_user_agent_session | test_support_agent.py: outsider/same-org non-author denied |
| POST | `/support/tickets` | current_user, auth_context, HTTPBearer | _membership_org_ids | test_trust_outbox.py: foreign organization denied without ticket/message/audit |
| GET | `/support/tickets` | current_user, auth_context, HTTPBearer | _ticket_user_access | test_support_security.py: same-org non-author excluded |
| GET | `/support/tickets/{ticket_id}` | current_user, auth_context, HTTPBearer | _require_user_ticket | test_support_security.py: outsider/same-org non-author/revoked member |
| POST | `/support/tickets/{ticket_id}/messages` | current_user, auth_context, HTTPBearer | _require_user_ticket | test_support_security.py: same-org non-author |
| POST | `/support/tickets/{ticket_id}/close` | current_user, auth_context, HTTPBearer | _require_user_ticket | test_support_security.py: same-org non-author/stale If-Match |
| POST | `/support/tickets/{ticket_id}/reopen` | current_user, auth_context, HTTPBearer | _require_user_ticket | test_support_security.py: same-org non-author |
| GET | `/admin/support/tickets` | require_admin_step_up, auth_context, HTTPBearer | — | test_admin.py: non-admin denied |
| GET | `/admin/support/tickets/{ticket_id}` | require_admin_step_up, auth_context, HTTPBearer | _require_admin_ticket | test_support_security.py: admin without step-up |
| POST | `/admin/support/tickets/{ticket_id}/messages` | require_admin_step_up, auth_context, HTTPBearer | _require_admin_ticket | test_support_security.py: admin without step-up |
| GET | `/admin/support/tickets/{ticket_id}/notes` | require_admin_step_up, auth_context, HTTPBearer | _require_admin_ticket | test_support_security.py: admin without step-up |
| POST | `/admin/support/tickets/{ticket_id}/notes` | require_admin_step_up, auth_context, HTTPBearer | _require_admin_ticket | test_support_security.py: admin without step-up |
| POST | `/admin/support/tickets/{ticket_id}/close` | require_admin_step_up, auth_context, HTTPBearer | _require_admin_ticket | test_support_security.py: admin without step-up |
| POST | `/admin/support/tickets/{ticket_id}/reopen` | require_admin_step_up, auth_context, HTTPBearer | _require_admin_ticket | test_support_security.py: admin without step-up |
| GET | `/saved-searches` | current_user, auth_context, HTTPBearer | — | test_saved_searches.py: foreign org denied; other users searches hidden |
| POST | `/saved-searches` | current_user, auth_context, HTTPBearer | _require_notify_consent | test_saved_searches.py: foreign org denied without write |
| PATCH | `/saved-searches/{saved_search_id}/notify-consent` | current_user, auth_context, HTTPBearer | _require_notify_consent, require_org_member | test_saved_searches.py: notify without consent denied |
| DELETE | `/saved-searches/{saved_search_id}` | current_user, auth_context, HTTPBearer | require_org_member | test_saved_searches.py: stranger denied |
| POST | `/promo/events` | — | — | test_promo.py: state — unknown name ignored without audit write |
| POST | `/admin/reconciliation/runs` | require_admin, auth_context, HTTPBearer | _reconciliation_2fa | test_admin_reconciliation.py: non-admin/invalid TOTP/no TOTP |
| GET | `/admin/reconciliation/runs` | require_admin, auth_context, HTTPBearer | _reconciliation_2fa | test_admin_reconciliation.py: non-admin/admin without step-up |
| GET | `/admin/reconciliation/discrepancies` | require_admin, auth_context, HTTPBearer | _reconciliation_2fa | test_admin_reconciliation.py: admin without TOTP |
| GET | `/admin/reconciliation/discrepancies/{discrepancy_id}` | require_admin, auth_context, HTTPBearer | _reconciliation_2fa | test_admin_reconciliation.py: non-admin/no TOTP/unknown ID |
| POST | `/admin/reconciliation/discrepancies/{discrepancy_id}/resolve` | require_admin, auth_context, HTTPBearer | _reconciliation_2fa | test_admin_reconciliation.py: non-admin/no TOTP/invalid TOTP/unknown ID |
| GET | `/admin/verifications` | require_admin, auth_context, HTTPBearer | — | test_admin.py: non-admin denied |
| POST | `/admin/verifications` | require_admin, auth_context, HTTPBearer | — | test_admin.py: non-admin/invalid target type denied |
| POST | `/admin/disputes` | require_admin, auth_context, HTTPBearer | — | test_admin.py: non-admin denied |
| GET | `/admin/disputes` | require_admin, auth_context, HTTPBearer | — | test_admin.py: non-admin denied |
| PUT | `/admin/disputes/{dispute_id}/assignment` | require_admin, auth_context, HTTPBearer | require_admin_2fa | test_disputes.py: admin without TOTP/invalid TOTP |
| PUT | `/admin/disputes/{dispute_id}/resolve` | require_admin, auth_context, HTTPBearer | require_admin_2fa | test_disputes.py: admin without TOTP/other assignee/stale version |
| POST | `/admin/refunds` | require_admin, auth_context, HTTPBearer | require_admin_2fa | test_totp_security.py: admin without TOTP/invalid TOTP |
| POST | `/admin/refunds/{refund_request_id}/approve` | require_admin, auth_context, HTTPBearer | require_admin_2fa | test_admin.py: same admin; test_totp_security.py: invalid TOTP |
| POST | `/admin/attachments/{attachment_id}/scan-decision` | require_admin, auth_context, HTTPBearer | require_admin_2fa | test_attachments.py: tamper/replay |
| POST | `/admin/attachments/{attachment_id}/scan` | require_admin, auth_context, HTTPBearer | require_admin_2fa | test_attachment_av.py: non-admin/no TOTP denied; scanner error quarantined |
| POST | `/admin/payments/{payment_id}/confirm-external` | require_admin, auth_context, HTTPBearer | require_admin_2fa | test_external_payment_confirm.py: outsider/no TOTP/foreign report ID |
| POST | `/admin/payments/{payment_id}/request-external-clarification` | require_admin, auth_context, HTTPBearer | require_admin_2fa | test_external_payment_confirm.py: no TOTP/foreign report ID |
| GET | `/admin/payments/{payment_id}/external-reports` | require_admin, auth_context, HTTPBearer | require_admin_2fa | test_external_payment_confirm.py: admin without TOTP |
| POST | `/admin/payment-reminders/run` | require_admin, auth_context, HTTPBearer | require_admin_2fa | test_admin.py: non-admin/no TOTP/invalid TOTP |
| GET | `/admin/metrics` | require_admin, auth_context, HTTPBearer | — | test_admin.py: non-admin denied |
| POST | `/admin/totp/enable` | current_user, auth_context, HTTPBearer | — | test_admin.py: non-admin denied without TOTP state change |
| GET | `/admin/audit` | require_admin, auth_context, HTTPBearer | — | test_admin.py: non-admin denied |
| DELETE | `/admin/audit/{audit_id}` | require_admin, auth_context, HTTPBearer | — | test_admin.py: non-admin/admin denied; audit immutable |
| POST | `/admin/email-outbox/retry` | require_admin, auth_context, HTTPBearer | — | test_admin.py: non-admin denied |
| GET | `/admin/venue-catalog/venues` | require_admin, auth_context, HTTPBearer | — | test_admin.py: non-admin denied |
| GET | `/admin/venue-catalog/venues/{venue_id}/history` | require_admin, auth_context, HTTPBearer | — | test_admin.py: non-admin denied |
| POST | `/admin/venue-catalog/venues/{venue_id}/status` | require_admin, auth_context, HTTPBearer | — | test_venue_catalog_lifecycle.py: non-admin denied without mutation |
| POST | `/admin/venue-catalog/venues/{venue_id}/moderation` | require_admin, auth_context, HTTPBearer | — | test_venue_catalog_lifecycle.py: non-admin denied without mutation |
| POST | `/admin/venue-catalog/freshness/recalculate` | require_admin, auth_context, HTTPBearer | — | test_venue_catalog_lifecycle.py: non-admin denied |
| GET | `/admin/venue-catalog/batches` | require_admin, auth_context, HTTPBearer | — | test_admin.py: non-admin denied |
| GET | `/admin/venue-catalog/report` | require_admin, auth_context, HTTPBearer | — | test_admin.py: non-admin denied |

Всего: 165 операций после добавления admin AV-маршрута. Каждая строка сопоставлена с адресным отрицательным инвариантом: ACL, приватность, подпись, consent или состояние. Последние три публичных GET проверены на отсутствие подставленных в тест email API key и merchant ID, скрытие неопубликованной категории и ограничение полей справочника; это проверки приватности/стабильности, не запрета доступа. **165/165 не означает полного authz-покрытия**: степень проверки объектных и ролевых ограничений требует отдельной оценки для каждого маршрута.

Текущий транш проверил создание карточек артиста/площадки и события, изменение избранного, приватные чтения уведомлений и supply-completeness, персональный `/me`, публичный каталог, briefs и compare. Сценарий `POST /promo/events` проверяет игнорирование неизвестного имени без записи в аудит; он не является authz-проверкой публичного endpoint. Подпись webhook подтверждена только на локальном stub; live-провайдер остаётся отдельным gate.

Подтверждённые открытые риски: в режиме `manual` статус `clean` остаётся ручным решением, а не AV-вердиктом; новый режим `clamd` испытан только с fake-scanner, реальный daemon/сигнатуры/нагрузка не проверены. Прямой multipart теперь ограничен до парсера, но медленная загрузка, число соединений и расход временного диска не проверены под нагрузкой. Lifecycle удаления/удержания вложений при отмене/истечении hold не утверждён. Публичность закрытых briefs требует продуктового решения. Для заявок без исторического `Conversation` список сохраняет совместимость через `Request.supplier_org_id`; неизменяемый снимок стороны для таких legacy-строк отсутствует и требует отдельного backfill/политики.

Третий транш: `calendar_entries` не принимает один только `busy` и требует запись для каждого зала. Если `open` полностью перекрыт отпуском/iCal, публичная карточка пока остаётся доступной, хотя поиск не находит свободной даты; политика скрытия всего профиля при временной занятости требует отдельного продуктового решения. В четвёртом транше услуга `/services/public` получила проверяемую привязку к конкретному профилю той же организации и категории. Неоднозначные legacy услуги скрыты до ручной привязки. Гонка login/reset проверена на отдельной файловой SQLite БД; одновременный расход reset-токена и обе гонки требуют отдельной проверки на PostgreSQL. Ранний `BEGIN IMMEDIATE` сериализует SQLite-входы и может задерживать другие записи при высокой нагрузке.
