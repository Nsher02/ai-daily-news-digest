Refine the digest layout to match the disclosure section at the bottom of design/Apple_News_reference.jpeg.

1. DESIGN
   - Put the existing AI disclosure in a separate lighter-gray footer band spanning the full reading column, beneath the near-black story area.
   - Match the reference's flat gray background, muted text, inset alignment, and comfortable padding. Remove the inset divider previously used above the disclosure.
   - Keep the existing disclosure wording and AI Daily News Digest identity. Do not add Apple logos, legal claims, subscription links, or nonfunctional controls.
   - Preserve the header fade, story layout, plain-text alternative, and all delivery behavior. Use inline email-safe colors with a bgcolor fallback and responsive padding.

2. VERIFY AND PUBLISH
   - Update the offline HTML preview and README. Inspect desktop and phone previews and check for horizontal overflow.
   - Run Python compilation and whitespace checks. Commit and push so future scheduled emails use the updated layout.
   - Do not send test emails or call Gemini.
