Redesign the daily digest email to closely match design/Apple_News_reference.jpeg, especially its different shades of black and gray. Work through these steps, verify the result, then commit and push.

1. DESIGN
   - Use the supplied screenshot as the visual reference: charcoal outer canvas, near-black reading column, bright headlines, softer gray summaries, muted source names, fine gray rules, and pink Top Stories label.
   - Match its compact sans-serif masthead, bold uppercase section headings, serif story headlines, bullet-style top-story briefs, and right-aligned thumbnails in other sections. Preserve readable line spacing instead of reproducing the screenshot's overlapping text.
   - Keep AI Daily News Digest branding, original article links, summaries, alternate coverage, and plain-text email. Do not add Apple logos, Apple branding, promotional modules, or subscriptions.
   - Use a dark default palette that remains consistent in both system appearance modes, email-safe tables, inline critical styles, system fonts, and a responsive 600px maximum reading column. Omit missing images cleanly.
   - Change presentation only; preserve fetching, model calls, delivery, scheduling, and deadlines.

2. VERIFY
   - Render an offline preview with representative multi-section content and image/no-image cases. Check desktop and phone widths, including horizontal overflow and readable colors. Do not send a real email or spend Gemini quota.
   - Run the existing regression suite, Python compilation, and whitespace checks.

3. DOCUMENT AND PUBLISH
   - Update README with the reference, palette, layout, preview workflow, and email-client limitations.
   - Include this prompt and the supplied reference image. Review staged changes for secrets, commit with a specific design-focused message, and push to the current main branch without overwriting remote changes.
