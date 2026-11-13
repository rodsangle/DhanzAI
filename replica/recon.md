# Recon map: ChatGPT (web, with mobile notes)

Scope: the core assistant loop and what surrounds it: chats and history, projects, memory,
files, web search and deep research, image creation, voice, canvas or coding, custom
assistants, sharing, scheduled tasks, plans and settings.
For: DHANZ AI (rodsangle/DhanzAI, dhanzai.com). This is a parity study, not a new product.
The "clone" column in `features.csv` is DHANZ's current status, taken from `docs/ROADMAP.md`
and the code.
Date: 2026-11-13

**Method and limits.**
- Public sources only. OpenAI's terms restrict reverse engineering and using ChatGPT output to
  build competing models, so no account was used, no ChatGPT code or network traffic was read,
  and no text, branding or images are copied.
- The help center (help.openai.com) could not be opened from this session; it is blocked by the
  session's network settings. Facts come from search results that quote OpenAI's own pages,
  plus third-party guides. Where sources disagree, the row says so and is marked medium or guess.
- No screenshots were taken. `screens/` is empty.

## Sources

| # | source | URL | notes |
| --- | --- | --- | --- |
| 1 | release notes (OpenAI) | https://help.openai.com/en/articles/6825453-chatgpt-release-notes | Search snippets only. Pinned chats and projects, voice in projects, group-chat creation ended 9 July, app directory, shopping |
| 2 | Business release notes (OpenAI) | https://help.openai.com/en/articles/11391654-chatgpt-business-release-notes | Memory summary (25 June 2026), workspace agents, guided agent setup |
| 3 | changelog (OpenAI) | https://learn.chatgpt.com/docs/changelog | Listed only, not read |
| 4 | Wikipedia | https://en.wikipedia.org/wiki/ChatGPT | Overview |
| 5 | Wikipedia, Deep Research | https://en.wikipedia.org/wiki/ChatGPT_Deep_Research | Deep Research limited on Free/Go, included on Plus and up |
| 6 | pricing guide | https://www.gradually.ai/en/chatgpt-pricing/ | Free, Go, Plus, Pro, Business |
| 7 | pricing guide | https://www.nocode.mba/articles/chatgpt-pricing | Business: per-seat pricing, two-seat minimum |
| 8 | pricing guide | https://geotoolbox.ai/blog/chatgpt-pricing | Pro tiers $100/$200/$500 |
| 9 | features guide | https://suprmind.ai/hub/chatgpt/features/ | Projects, memory, agent, Sora |
| 10 | features guide | https://digitalstrategyai.substack.com/p/what-i-learned-after-testing-every | Projects (40 files, sharing for free users), Work agent (9 July 2026), memory rebuild |
| 11 | features guide | https://www.makeuseof.com/3-chatgpt-new-features-you-missed/ | Lesser-known features |
| 12 | Branch in new chat | https://medium.com/@CherryZhouTech/chatgpt-launches-branched-chats-effortless-multi-threaded-conversations-d188b90bd78b | "Branch in new chat" from a reply's menu, also on mobile |
| 13 | temporary chat variant | https://aitopics.org/doc/news:68207AD7 | Temporary chat that keeps personalisation (in testing) |
| 14 | Codex | https://en.wikipedia.org/wiki/OpenAI_Codex_(AI_agent) | Coding agent alongside chat |
| 15 | review | https://theairankings.com/openai/chatgpt/ | Tiers and agent mode |

## Core loop

Type or speak a request in one box. The assistant answers in a stream, and on its own uses
search, files, image creation or tools. Everything is kept in a searchable history, grouped
into projects that remember their files and instructions.

## Screens

| ID | screen | route / how to reach | purpose | key components | states seen (from sources) |
| --- | --- | --- | --- | --- | --- |
| S01 | Logged-out home | / | try a chat without an account, sign up | composer, sign-up prompt | guest, limit reached |
| S02 | Sign up / log in | /auth | email, Google, Apple, Microsoft, phone | auth form, provider buttons | error, verification code |
| S03 | New chat (empty) | / signed in | start a conversation | composer, tool menu (+), model picker, suggestions | empty, loading |
| S04 | Conversation | /c/{id} | read and continue a chat | message list, streaming reply, reply actions (copy, read aloud, like, regenerate, branch, share), sources | streaming, stopped, error, rate-limited |
| S05 | Sidebar | always (collapsible) | history, search, pinned, projects, new chat, library, apps | list, search, pins, project folders | empty, many chats, collapsed |
| S06 | Search chats | sidebar search / shortcut | find old chats | search dialog, results | no results |
| S07 | Project | sidebar → project | chats, files and instructions together | project header, files, instructions, project chats, memory setting | empty, shared |
| S08 | Library / images | sidebar → Library | all created images | grid, preview | empty |
| S09 | Canvas / coding side view | from a reply | edit a document or code next to the chat | split editor, versions | (canvas dropped from GPT-5.5 models, per source 1) |
| S10 | Deep research | tool menu → deep research | long cited report | plan, progress, report with sources | running, done |
| S11 | Voice mode | mic button | spoken conversation | voice orb, mute, captions | listening, speaking |
| S12 | Image creation result | chat reply | create or edit an image in chat | image card, edit, download, share | generating, done, blocked |
| S13 | Custom assistants (GPTs) | sidebar → GPTs | browse, use and create custom assistants | store grid, builder (instructions, files, actions) | — |
| S14 | Apps / connectors | sidebar → apps | connect Drive, Outlook, Notion and others; in-chat apps | directory, connect flow | not available in some regions |
| S15 | Scheduled tasks | tool menu / settings | run a prompt on a schedule | task list, schedule editor | — |
| S16 | Share dialog | reply or chat menu | create a public read-only link | link, revoke | — |
| S17 | Shared chat (public) | /share/{id} | read a shared chat, continue it | read-only transcript | expired / deleted |
| S18 | Settings | profile menu | general, personalisation, memory, data controls, security, account | tabs, toggles | — |
| S19 | Personalisation | settings | custom instructions, personality, memory list | text fields, memory manager | memory full |
| S20 | Data controls | settings | export, delete, shared links, archived chats, improve-the-model toggle | buttons, lists | — |
| S21 | Plans / upgrade | profile → upgrade | compare and buy plans | plan cards, checkout | — |
| S22 | Work / agent | sidebar or desktop app | multi-step tasks using a browser and apps | task view, approvals, live browser | needs approval, done |

## Flows

```
F01 Ask and get a streamed answer
    S03 type -> send -> S04 reply streams
    happy path clicks: 1 (Enter)
    edge: stop mid-reply, regenerate, edit a sent message, rate limit, model error

F02 Answer with web search and citations
    S03 (tool menu: search, or automatic) -> S04 reply with numbered sources
    happy path clicks: 1 (automatic) or 3 (forced)
    edge: no results, paywalled page, conflicting sources

F03 Work with a file
    S03 + attach -> pick file -> ask -> S04 answer cites the file
    happy path clicks: 3
    edge: unsupported type, too large, scanned PDF, many files

F04 Create and edit an image
    S03 (tool menu: create image, or plain request) -> S12 image card -> edit by chatting
    happy path clicks: 1-2
    edge: blocked prompt, quota reached, aspect ratio, editing an uploaded photo

F05 Organise work in a project
    S05 new project -> S07 add files and instructions -> new chat in project -> S04
    happy path clicks: 4
    edge: project-only memory, sharing a project, moving a chat into a project

F06 Remember something across chats
    S04 "remember that ..." -> memory saved notice -> later chats use it -> S19 manage
    happy path clicks: 0 (automatic)
    edge: memory full, forget one item, temporary chat (no memory)

F07 Talk by voice
    S03 mic -> S11 speak -> spoken reply -> transcript saved in S04
    happy path clicks: 1
    edge: interruptions, background noise, voice in a project

F08 Share a chat
    S04 share -> S16 create link -> S17 others read and continue it
    happy path clicks: 2
    edge: revoke link, chat with images, deleted chat

F09 Deep research report
    S03 deep research -> plan check -> S10 progress -> report
    happy path clicks: 2
    edge: very long run, rate limits, citations to blocked pages

F10 Branch a conversation
    S04 reply menu -> "Branch in new chat" -> new chat starting from that point
    happy path clicks: 2

F11 Schedule a recurring task
    S03 / S15 "every morning at 8 ..." -> task created -> results arrive as chats and notifications
    happy path clicks: 2

F12 Use a custom assistant
    S13 pick a GPT (or @mention one) -> chat with its instructions, files and actions
    happy path clicks: 2
```

## Components

| component | variants | states | used on |
| --- | --- | --- | --- |
| Composer | chat, in project, voice entry | empty, typing, attachments, sending, disabled at limit | S03, S04, S07 |
| Tool menu (+) | files, image, search, deep research, canvas, apps | open, item unavailable on plan | S03, S04 |
| Model picker | auto, named models | locked on plan | S03, S04 |
| Message bubble | user, assistant, tool result | streaming, stopped, error | S04, S17 |
| Reply action bar | copy, read aloud, like/dislike, regenerate, branch, share | hover, done | S04 |
| Source cards | inline [n], source list | — | S04, S10 |
| Image card | generating, done | blocked, editable | S04, S08, S12 |
| Sidebar list | chats, pinned, projects | collapsed, search, empty | S05 |
| Dialogs | share, rename, delete, upgrade | — | many |
| Toast | memory updated, link copied, error | — | many |
| Settings tabs | — | — | S18–S20 |

## Inferred data model

```
User           id, email, name, plan, locale, created_at
               evidence: S02, S18, S21. confidence: high
Conversation   id, user_id, project_id?, title, pinned, archived, temporary, created_at, updated_at
               evidence: S04, S05, S20 (archived), temporary chat. confidence: high
Message        id, conversation_id, parent_id (branching/edits), role, content, model, attachments, sources
               evidence: S04 edit/regenerate/branch, F10. confidence: medium (tree shape inferred)
Project        id, user_id, name, instructions, memory_mode (default | project-only), shared
               evidence: S07, sources 1 and 10. confidence: high
File           id, owner_id, project_id?, name, type, size
               evidence: F03, S07 (40 files per project, source 10). confidence: high
Memory         id, user_id, text, created_at, summary
               evidence: S19, F06, memory summary (source 2). confidence: high
SharedLink     id, conversation_id, created_at, revoked
               evidence: S16, S17, S20. confidence: high
ScheduledTask  id, user_id, prompt, schedule, next_run, last_result
               evidence: S15, F11, pricing (Plus). confidence: medium
CustomAssistant (GPT)  id, owner_id, name, instructions, files, actions, visibility
               evidence: S13. confidence: high
Creation       id, user_id, kind (image|video), prompt, status, media
               evidence: S08, S12. confidence: high
Subscription   user_id, plan, status, renews_at
               evidence: S21, pricing pages. confidence: high
```

Relationships: User 1-n Conversation; Project 1-n Conversation; Conversation 1-n Message (a tree);
Project 1-n File; User 1-n Memory; Conversation 1-n SharedLink; User 1-n ScheduledTask;
User 1-n CustomAssistant; User 1-n Creation.

## Feature matrix

See `features.csv` (50 rows). Must: 20, should: 16, could: 9, skip: 5.
DHANZ today, from its roadmap and code: 19 yes, 15 partial, 11 no.
Musts not yet done: plans and payment (no), Google/Apple sign-in on web and desktop (partial),
image creation live verification (partial), store listings (partial).

## Out of scope (cannot or should not be cloned)

- OpenAI's own models and their quality. DHANZ routes to providers through their public APIs.
- The custom-GPT store's catalogue of third-party assistants (their creators' content and network).
- Partner apps inside chat (Canva, Spotify, Instacart and others): partner deals.
- Shopping results and merchant feeds: partner data.
- ChatGPT's user base, shared-chat links already published, and ads.

## Size

Screens 22, flows 12, entities 11.
Hard parts: a scheduled-task runner; an agent with browser control and approvals (DHANZ has
desktop actions and approvals to build on); payments and plans (DHANZ has none yet); public
share links with privacy controls; message branching in the data model.
Size: **L** for full parity (a quarter). Each "should" gap on its own is S or M, because DHANZ
already has the core loop.
