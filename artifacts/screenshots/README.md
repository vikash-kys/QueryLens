# QueryLens screenshots

These desktop screenshots were captured from the running application and its local PostgreSQL sample database. The AI result used one live Gemini 3.1 Flash-Lite request; the other query screenshots used SQL mode. No screenshot uses intercepted or fabricated API responses.

| Screen | Image |
| --- | --- |
| Natural language to SQL and live results | [ai-query-desktop.png](ai-query-desktop.png) |
| Home workspace | [home-desktop.png](home-desktop.png) |
| Direct SQL result | [query-desktop.png](query-desktop.png) |
| Database schema | [schema-desktop.png](schema-desktop.png) |
| Query history | [history-desktop.png](history-desktop.png) |
| Blocked write attempt | [blocked-desktop.png](blocked-desktop.png) |
| Evaluations disabled by default | [evaluations-desktop.png](evaluations-desktop.png) |

The evaluation image shows the disabled state; it does not claim an evaluation run. The AI result used single-call mode, so additional AI reviews and confidence scoring were disabled. Running `frontend/tests/capture-ai.mjs` again requires a working provider key and consumes quota.
