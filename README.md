# StoryTeller

> Generate interactive, multimedia "Choose Your Own Adventure" books with AI — complete with original lore, branching narratives, illustrations, music, and an AI Game Master.

**Status:** Pre-implementation — documentation and design complete. Phase 0.5 done.

## Quick Links

| Document | Purpose |
|---|---|
| [Goal](docs/goal.md) | Project vision, design principles, non-goals |
| [Architecture](docs/arch.md) | Technical architecture, data schemas, coding patterns |
| [Design](docs/design.md) | Behavioral design, pipeline flows, UX flows |
| [Roadmap](docs/roadmap.md) | Development phases and milestones |
| [Tests](docs/test.md) | Test strategy for all phases |
| [API Reference](docs/api.md) | Interface definitions, config spec, CLI reference |
| [Usage Guide](docs/readme.md) | How to use both applications |
| [Compliance](docs/compliance.md) | Model licenses, app store policy, privacy |

## The Two Applications

- **App B — The Forge** (`forge/`): Python pipeline that generates .story files. Runs on CPU-only, 10 GB RAM.
- **App A — The Player** (`droid/`, `ios/`): Mobile apps that read .story files with an interactive AI Game Master.

## License

[MIT](LICENSE)
