# Known projects and distinctions

This file captures project-specific distinctions that prevent incorrect merging or payload classification. These notes are historical; recheck upstream sources before publishing current versions or compatibility claims.

| Project | Canonical repository | Role | Distribution previously verified | Catalog treatment |
|---|---|---|---|---|
| PC5 | https://github.com/bornaradusin/PC5 | Game launcher/library and settings UI | `PPSA11018.zip` | Repository entry; not a direct ELF payload |
| prospero-win | https://github.com/mpereiraesaa/prospero-win | Experimental Wine-based Windows runtime used by PC5 | PS5 application ZIP | Separate repository entry; not a direct ELF payload |
| PS5 Bazzite Deck | https://github.com/VivaLaVent/ps5-bazzite-deck | Bazzite Linux image with Steam Gaming Mode and KDE | Split `.img.7z.00*` image archives | Repository entry; not a direct ELF payload |

## Relationship rules
- PC5 and prospero-win are related but not interchangeable. PC5 is the launcher; prospero-win supplies the Windows compatibility runtime. Keep separate canonical records.
- PS5 Bazzite Deck is a bootable Linux image project, not an ELF payload. Do not classify its image archives as payload files.
- Similar names, shared dependencies, forks, ports, and shared mirrors are not sufficient grounds to merge distinct projects.
