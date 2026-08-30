# Combined daily store and Night Market

Status: awaiting live Night Market verification. Do not merge or deploy until
an active event has been checked against the game. Mock fixtures and screenshots
are not proof that the current v3 storefront uses the documented structure.

## Behavior

There is still only `/shop`. Daily offers always appear first (two columns,
four slots). A nonempty, unexpired Night Market appends up to six offers below,
with a separate ending countdown. Riot ID and the footer are shared. Without
an event, the section disappears and the image shrinks to the daily-only layout.
Public visibility and private login/logout/errors are unchanged.

`BonusStore` is optional. Its reward ItemID identifies each skin; the enclosing
OfferID is not assumed to be a skin ID. Original VP cost, DiscountPercent, and
DiscountCosts are shown from the response, without calculating a replacement
price. Missing prices remain unavailable. Missing/expired/empty BonusStore is
normal; malformed optional data preserves the daily shop and adds a short
unavailable notice rather than claiming the event is closed.

No purchase, reveal, or mark-seen endpoint is called. Only normalized display
fields reach the renderer; raw account/token payloads are not logged or saved.
The normal owner-bound authorization, refresh, and logout behavior is reused.

The combined per-user cache expires after at most five minutes, bounded by both
section deadlines. Artwork is deduplicated across sections and restricted to the
existing public host, with three concurrent downloads, eight seconds per image,
8 MB encoded and four million decoded pixels per image. Decoded artwork is
reduced to 512x256 before retention. Card work has a 40-second deadline and falls
back to the same combined text output. Fetching does not create a new schedule.

## Required checks when the event opens

- [ ] Run `/shop` using a consenting TEST account during an active event.
- [ ] Confirm v3 BonusStore structure; inspect only necessary sanitized fields.
- [ ] Compare all returned skins, original VP prices, discounts, and final prices
      against the in-game store, including rounding and missing/sold offers.
- [ ] Confirm unseen offers do not trigger a reveal/mark-seen mutation.
- [ ] Compare daily rotation and Night Market end times separately.
- [ ] Verify the public Discord attachment is readable on mobile and desktop.
- [ ] Verify missing artwork and rendering failure preserve daily + night text.
- [ ] Confirm expired/absent events remove the section and newly opened events
      appear after cache expiry; logout must clear the whole cached result.
- [ ] Re-run all tests, review the diff, and get approval before merge/deployment.

Reference schema: https://valapidocs.techchrism.me/endpoint/storefront
This is a community-maintained v2 schema, not a Riot guarantee for v3.
