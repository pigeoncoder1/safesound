Tools

Claude.ai chat - used for turning my ideas and plans into step-by-step build prompts, creating test data.
Claude Code - Generating much of the code and tests from those prompts, which I then ran, reviewed, debugged and changed.
Claude Haiku - Inside the product: analysing off-script requests and normalising them into a list of fixed intents. The product also runs optionally without them, from a large library of regex data.

How I worked

1. Worked on the idea, came up with different branches that I can take the product - originally I was thinking of an assistant that won't read private messages aloud in front of others, but then moved onto thinking more about how ai agents will be dealing with other people on my behalf according to their relationship with me, reachable from anywhere - upon reviewing this with Daren Palmer in our office hour, started working on it.
2. I used claude to generate a context.md, and started every claude code prompt with "read context.md first", to ensure that it kept in line with my goals for the project.
3. The build was split into around 14 steps (speaker model - enrolmet - threshold test - live audio - room state - permissions - commands - replies - introductions - digest - UI - demo mode - conclusions). After each step I ran it and checked it, and read through the code to make sure I understood it.
4. The assistant wrote the tests too, but I decided what had to be tested, especially "withheld information never reaches a stranger"

