# Firebase Project — Specification

**Status:** draft · **Last change:** 2026-09-28

Since the architecture change to "cloud + optional hub agent" (PROJECT D23), Firebase is used only for **managed services**: login, push delivery, and hosting the official web app. There is no own code in Firebase (no Cloud Functions, no Firestore). The cloud backend is the only server that receives users' Firebase ID tokens.

Context: [`PROJECT.md`](../PROJECT.md) §3.3, [`server/Server_Specs.md`](../server/Server_Specs.md) §5.

---

## 1. Services used

| Service | Used for | Plan |
|---|---|---|
| **Authentication** | The only login for users | Free tier (Spark) is enough: e-mail/password and social logins are free up to 50 000 monthly active users |
| **Cloud Messaging (FCM)** | Push notifications, sent by the cloud backend | Free |
| **Hosting** | Official web app, `/join` and `/hub` deep links, app-link files | Free tier: 10 GB storage, 360 MB/day transfer — ample for a Flutter web build |
| App Check (optional) | Makes scripted abuse of the login harder | Free |

Not used: Cloud Functions, Firestore, Realtime Database, Storage, KMS. The project can therefore stay on the free **Spark** plan.

Project region: `europe-west3` (Frankfurt) where a region applies.

---

## 2. Authentication

- **Providers:** e-mail/password (with **e-mail verification required** before creating or joining a household — enforced by the backend), Google, Apple (required on iOS when Google is offered).
- **Anonymous auth:** disabled.
- **Authorized domains:** only `app.<our-domain>` (+ `localhost` for development). The `authDomain` is set to the same custom domain, so the sign-in redirect handler lives there.
- **Sessions:** standard Firebase ID tokens (1 h, auto-refreshed by the SDK). The backend checks `auth_time` for sensitive actions and uses the Admin SDK's revocation check (Server_Specs §5.3).
- **Account security:** password policy (min. 10 characters), e-mail enumeration protection on, multi-factor auth (TOTP) available to users in the app settings.
- **Account deletion:** users delete their account in the app → the app calls the backend first (leave/transfer households, Server_Specs §17), then deletes the Firebase account.

---

## 3. Cloud Messaging

- The **cloud backend** is the only sender; it holds the service account (`MC_FIREBASE_CREDENTIALS`). Hubs and devices never talk to FCM.
- The app registers its FCM token with `PUT /api/v1/me/push-tokens/{token}` and removes it on logout.
- Web push: FCM web with a service worker on the official origin; iOS Safari only for installed web apps.

---

## 4. Hosting

- The Flutter web build is served **only** from `https://app.<our-domain>` — the only web origin where users sign in. Nothing else (no hub, no backend) serves web pages.
- Deep links:
  - `https://app.<our-domain>/join#c=<code>` — accept an invite (PROJECT §3.4).
  - `https://app.<our-domain>/hub#u=<user-code>` — add a hub; this is what the hub's console QR code contains ([contracts/hub.md §3.1](../contracts/hub.md)).
  - The part after `#` is never sent to any server, so codes don't end up in logs.
- Mobile: the same URLs open the installed app via Android App Links / iOS Universal Links (`/.well-known/assetlinks.json`, `/.well-known/apple-app-site-association`).
- Headers: strict `Content-Security-Policy` (scripts only from the own origin + Google sign-in; `connect-src` only the API origin and Firebase endpoints), HSTS, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.

---

## 5. Layout

```
firebase/
├── Firebase_Specs.md
├── firebase.json            # hosting: public dir = app/build/web, rewrites, headers
└── .firebaserc              # project alias(es): prod, dev
```

Deploy: `firebase deploy --only hosting` from CI after the Flutter web build. Auth settings are configured in the console and documented here.

---

## 6. Open points

- Separate Firebase projects for **dev** and **prod** (recommended) — decide when the backend gets a staging environment.
