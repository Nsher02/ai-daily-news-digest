Stage 1: Put these 10 feeds in config.yaml, each with a name, url and max_items:
- Hacker News (100+ points): https://hnrss.org/frontpage?points=100 (max 20)
- TechCrunch AI: https://techcrunch.com/category/artificial-intelligence/feed/ (15)
- The Verge AI: https://www.theverge.com/rss/ai-artificial-intelligence/index.xml (10)
- Ars Technica AI: https://arstechnica.com/ai/feed/ (10)
- MIT Technology Review AI: https://www.technologyreview.com/topic/artificial-intelligence/feed (10)
- OpenAI News: https://openai.com/news/rss.xml (10)
- Google DeepMind: https://deepmind.google/blog/rss.xml (10)
- Hugging Face Blog: https://huggingface.co/blog/feed.xml (10)
- arXiv cs.AI: https://rss.arxiv.org/rss/cs.AI (25)
- IEEE Spectrum Computing: https://spectrum.ieee.org/feeds/topic/computing.rss (10)

Fetch each feed (20s timeout, a normal User-Agent), keep items from the last 26 hours, cap each source at its max_items, and print the count and headlines per source.
If a feed fails, log it and skip it. One bad feed must not crash the run.