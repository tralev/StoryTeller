# StoryTeller

> Generate interactive, multimedia "Choose Your Own Adventure" books with AI — complete with original lore, branching narratives, illustrations, music, and an AI Game Master.

**Status:** Active implementation — rewrite Phases 1–7 and Phase 8 model lifecycle are complete; remaining work is tracked in the consolidated roadmap.

## Quick Links

| Document | Purpose |
|---|---|
| [Documentation Index](docs/index.md) | Authority order, reading order, and all documents |
| [Goal](docs/goal.md) | Product scope and non-goals |
| [Architecture](docs/arch.md) | Technical architecture, data schemas, coding patterns |
| [Design](docs/design.md) | Behavioral design, pipeline flows, UX flows |
| [Roadmap](docs/roadmap.md) | Remaining actionable work and release evidence gates |
| [Tests](docs/test.md) | Test strategy for all phases |
| [API Reference](docs/api.md) | Interface definitions, config spec, CLI reference |
| [Usage Guide](docs/readme.md) | How to use both applications |
| [Compliance](docs/compliance.md) | Model licenses, app store policy, privacy |

## The Two Applications

- **App B — The Forge** (`src/`): Python pipeline that generates .story files. Runs on CPU-only, 10 GB RAM.
- **App A — The Player** (`droid/`, `ios/`): Mobile apps that read .story files with an interactive AI Game Master.

## License

[MIT](LICENSE)
