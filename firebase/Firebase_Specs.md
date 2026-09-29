# Firebase Project — Specification

**Status:** draft · **Last change:** 2026-09-29 (v2 architecture, D33)

Firebase is used only for **managed services**: login and user accounts, push delivery, and hosting the official web app. There is no own code in Firebase (no Cloud Functions, no Firestore). Households, memberships, roles and invites live in the API server's database (D9, D10); the API server is the only component that receives users' Firebase ID tokens. Gateways and devices never talk to Firebase.

Context: [`PROJECT.md`](../PROJECT.md) §3.3, [`api/Api_Specs.md`](../api/Api_Specs.md) §5.

---

## 1. Services used

| Service | Used for | Plan |
|---|---|---|
| **Authentication** | Login and user accounts (sign-up, e-mail verification, password reset, social logins, MFA) | Spark: free up to 50 000 monthly active users |
| **Cloud Messaging (FCM)** | Push notifications, sent by the API server | Free |
| **Hosting** | Official web app, `/join` and `/gateway` deep links, app-link files | Spark: 10 GB storage, 360 MB/day transfer — ample for a Flutter web build |
| App Check (optional) | Makes scripted abuse of the login harder | Free |

Not used: Cloud Functions, Firestore, Realtime Database, Storage. The project stays on the free **Spark** plan — the API server does everything that would otherwise need Functions (verifying tokens, sending pushes).

Project region: `europe-west3` (Frankfurt) where a region applies.

---

## 2. Authentication

- **Providers:** e-mail/password (with **e-mail verification required** before creating or joining a household — enforced by the API server), Google, Apple (required on iOS when Google is offered).
- **Anonymous auth:** disabled.
- **Authorized domains:** only `app.<our-domain>` (+ `localhost` for development). The `authDomain` is set to the same custom domain.
- **Sessions:** standard Firebase ID tokens (1 h, auto-refreshed by the SDK). The API server checks `auth_time` for sensitive actions and uses the Admin SDK's revocation check (Api_Specs §5.3).
- **Account security:** password policy (min. 10 characters), e-mail enumeration protection on, multi-factor auth (TOTP) available in the app settings.
- **User management split:** Firebase owns the *account* (credentials, e-mail, verification, MFA, disabling). Our database owns everything about *access* (which households, which role). No custom claims.
- **Account deletion:** the app calls the API first (leave/transfer households, Api_Specs §6.1 `DELETE /me`), then deletes the Firebase account.

---

## 3. Cloud Messaging

- The **API server** is the only sender; it holds the service account (`MC_FIREBASE_CREDENTIALS`). Gateways and devices never talk to FCM.
- The app registers its FCM token with `PUT /api/v1/me/push-tokens/{token}` and removes it on logout.
- Web push: FCM web with a service worker on the official origin; iOS Safari only for installed web apps.

---

## 4. Hosting

- The Flutter web build is served **only** from `https://app.<our-domain>` — the only web origin where users sign in.
- Deep links:
  - `https://app.<our-domain>/join#c=<code>` — accept an invite (PROJECT §3.4).
  - `https://app.<our-domain>/gateway#u=<user-code>` — add a gateway; this is what the gateway's console QR code contains ([contracts/gateway_api.md §3.1](../contracts/gateway_api.md)).
  - The part after `#` is never sent to any server.
- Mobile: the same URLs open the installed app via Android App Links / iOS Universal Links (`/.well-known/assetlinks.json`, `/.well-known/apple-app-site-association`).
- Headers: strict `Content-Security-Policy` (scripts only from the own origin + Google sign-in; `connect-src` only the API origin and Firebase endpoints), HSTS, `nosniff`, `Referrer-Policy: no-referrer`.

---

## 5. Layout

```
firebase/
├── Firebase_Specs.md
├── firebase.json            # hosting: public dir = app/build/web, rewrites, headers
└── .firebaserc              # project aliases: dev, prod
```

Deploy: `firebase deploy --only hosting` from CI after the Flutter web build. Auth settings are configured in the console and documented here.

---

## 6. Open points

- Separate Firebase projects for **dev** and **prod** (recommended) — one per API server environment.
