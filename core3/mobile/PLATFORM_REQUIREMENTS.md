# NOVA Mobile — Android/iOS parity gate

Flutter is the shared application layer, but platform differences must never be hidden by pretending Android and iOS behave identically.

## Release parity

A mobile feature is incomplete until it passes on both Android and iOS real devices.

Required on both platforms:
- authenticated session and secure token storage
- room/assignment current-state read
- cleaning START/COMPLETE with idempotency key
- optimistic UI followed by authoritative DB reconciliation
- foreground Realtime updates
- background push notification
- foreground/resume DB reconciliation even when Realtime was suspended
- lock-screen notification, sound, vibration where allowed by OS/user settings
- deep link from notification to the exact room/order/task
- camera capture and direct signed Storage upload
- upload recovery and orphan lifecycle handling
- network offline/online transition
- timeout/ambiguous response recovery using the same request ID
- process termination and cold-start state recovery

## iOS-specific rule

iOS background execution is not treated as a continuously running socket environment. The application must remain correct when the OS suspends or kills its process. Push wakes/notifies the user; database reconciliation on resume is mandatory.

## Android-specific rule

Android background behavior varies by manufacturer and battery policy. Push delivery and app resume correctness must not depend on an always-alive foreground/background service.

## Push architecture

- Android delivery: FCM
- iOS delivery: APNs (normally via the push provider/FCM bridge chosen during implementation)
- notification database records are server-owned
- Telegram is an optional secondary channel only after NOVA Push is proven
- server records notification creation and processing state; client acknowledgment/read state is recorded separately

## Test device gate

At minimum, release candidates are tested on:
- Samsung Galaxy-class current Android device
- another representative Android configuration/emulator matrix
- current or near-current iPhone
- at least one older supported iPhone/iOS combination

Scenarios include foreground, background, screen locked, app terminated, Push tap, direct deep-link, poor network, network loss/recovery, duplicate tap/retry, photo capture/upload, token refresh and app update.