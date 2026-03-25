Dokis is a modular Telegram bot ecosystem built around multiple interactive personas, each responsible for a specific domain of functionality.

Core architecture:
The system is designed as a modular, asynchronous backend where each "character" acts as an independent service layer, interacting through shared state and APIs.

Main modules:

Monika - Chat Manager & Moderation System
- Full moderation toolkit (ban, mute, warn, kick, role management)
- Automated warning system with escalation logic (auto-ban after threshold)
- User statistics tracking and activity monitoring
- Utility features (weather, daily predictions, memory system)
- Admin hierarchy management and permissions

Sayori - Game & Interaction System
- Mini-games (hangman with difficulty scaling and reward system)
- Daily-limited reward mechanics to prevent abuse
- Duel system with probabilistic outcomes
- Fully dynamic RP system:
  - Users can create custom interaction commands
  - Flexible action logic with participant ordering
- Economy integration (currency rewards and sinks)

Yuri - Card & Progression System
- Dynamic user card generation based on activity
- Rarity system (common → legendary → legacy)
- Drop system with probability and guarantees (pity system)
- Collection tracking and progression mechanics
- Integration with chat statistics and economy

Key features:
- Modular multi-entity architecture
- Shared economy system (virtual currency)
- Event-driven interaction model
- Dynamic user-generated content (RP system)
- Scalable backend (FastAPI + PostgreSQL)
- Real-time interaction via Telegram API (webhooks)

Technical stack:
- Python
- FastAPI
- Aiogram
- PostgreSQL
- Docker (deployment)
