Stage 3: Send the items to Gemini using the openai Python package pointed at Google's OpenAI-compatible endpoint:
base_url https://generativelanguage.googleapis.com/v1beta/openai/
Make the model name a setting (LLM_MODEL env var) with a current Gemini Flash model as the default. Verify the model name works; don't guess.

Give each item a numeric ID in the prompt. Ask the model to pick the 15 most important stories for a CS grad student / software engineer, merge duplicate stories, skip promos and fluff, and return ONLY JSON:
{"tldr": "...", "sections": [{"name": "...", "stories": [{"ids": [..], "headline": "...", "summary": "1-2 sentences"}]}]}
Sections: Top stories, AI models & labs, Industry & business, Research, Software & computing.
IMPORTANT: Attach links in code by mapping IDs back to the real items. Never use URLs written by the model. Ignore invalid IDs.
Print the result.