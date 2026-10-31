# PROJECT: DHANZ AI — Universal Artificial Intelligence Assistant

## 1. Project Overview

Act as a senior AI engineer, full-stack developer, software architect, mobile application developer, UI/UX designer, and cybersecurity specialist.

Build a fully functional, production-ready artificial intelligence assistant named **DHANZ AI**.

DHANZ AI must be a cross-platform application that can be installed on:

- Windows 10 and Windows 11 (.exe / .msi)
- Android smartphones and tablets (.apk / .aab)
- Apple iPhone and iPad (iOS / iPadOS)
- Future macOS compatibility

DHANZ AI must function as an intelligent conversational chatbot, web research assistant, voice assistant, personal productivity assistant, and knowledge management system.

Its primary purpose is to help users find information, solve problems, create content, analyze documents, perform authorized tasks, and conduct research using information available on the World Wide Web.

**Application Name:** DHANZ AI

**Assistant Name:** Dhanz

**Tagline:** "Your World. Your Knowledge. Your AI."

## 2. AI Intelligence Engine

Develop a modular AI architecture supporting multiple AI model providers.

Integrate support for:

- OpenAI API
- Anthropic Claude API
- Google Gemini API
- Locally hosted AI models through Ollama
- Additional compatible AI providers

Implement an AI orchestration engine that can select models based on the task, user preferences, capabilities, cost, and availability.

Features:

1. Natural language understanding.
2. Multi-turn conversations.
3. Context-aware responses.
4. Logical reasoning and problem-solving.
5. Programming and code generation.
6. Mathematical calculations.
7. Document analysis.
8. Image understanding.
9. Multilingual conversations.
10. Conversation summarization.
11. Optional long-term memory.
12. Personalized responses based on authorized user preferences.

Dhanz must clearly distinguish between verified facts, estimates, and uncertain information.

Never fabricate sources, research results, or completed actions.

## 3. Worldwide Web Knowledge and Research

Develop an integrated web research engine that allows DHANZ AI to retrieve information from publicly accessible websites.

Support:

- Search engine APIs.
- Website content retrieval.
- Webpage summarization.
- News research.
- Technical documentation research.
- Product and supplier searches.
- Academic and scientific research.
- Public knowledge databases.
- Government and educational resources.
- Real-time information retrieval when supported.

### Research Workflow

When a user asks a question requiring current information:

1. Understand the question.
2. Determine whether internet research is required.
3. Search relevant sources.
4. Retrieve accessible webpage content.
5. Extract useful information.
6. Compare multiple sources where appropriate.
7. Evaluate source reliability.
8. Generate a clear answer.
9. Display clickable source links.
10. Include publication or retrieval dates when available.

### Knowledge Collection

Implement a Retrieval-Augmented Generation (RAG) system.

Use:

- Web search APIs.
- Document ingestion.
- Text extraction.
- Embedding generation.
- Vector databases.
- Semantic search.
- Knowledge indexing.
- Source metadata and citations.

Support PostgreSQL with pgvector or another suitable vector database.

Dhanz should improve its searchable knowledge base by indexing authorized, relevant information.

Important requirements:

- Respect website robots.txt, applicable terms, copyright, and access controls.
- Do not bypass paywalls or restricted websites.
- Do not collect private information without permission.
- Avoid indiscriminate web crawling.
- Track information sources and freshness.
- Do not claim that storing documents automatically retrains the underlying AI model.

## 4. Intelligent Chatbot Interface

Build a modern chatbot interface similar in usability to leading AI assistant applications.

Required features:

- Chat conversation screen.
- Text message input.
- Streaming AI responses.
- Markdown rendering.
- Code syntax highlighting.
- Copy response button.
- Regenerate response button.
- Edit and resend messages.
- Search conversation history.
- Rename conversations.
- Delete conversations.
- Pin favorite conversations.
- Organize conversations into projects.
- Export conversations to PDF, TXT, or Markdown.
- Upload attachments.
- Light and dark modes.
- Responsive layouts.

The assistant must identify itself as:

"Hello! I'm Dhanz, your personal AI assistant. How can I help you today?"

## 5. Voice Assistant

Develop natural voice interaction.

Features:

- Speech-to-text.
- Text-to-speech.
- Voice conversations.
- Voice activity detection.
- Multiple voice selections.
- Adjustable speaking speed.
- Multiple language support.
- Optional wake phrase: "Hey Dhanz."

Example:

User: "Hey Dhanz, search the internet for the latest semiconductor technology."

Dhanz: "I'll search for recent semiconductor technology developments and summarize the findings."

Implement hands-free voice mode where supported by the operating system.

Respect Android and iOS restrictions on background microphone access and wake-word detection.

## 6. File and Document Intelligence

Allow users to upload and analyze:

- PDF documents.
- Microsoft Word documents.
- Excel spreadsheets.
- PowerPoint presentations.
- TXT and CSV files.
- Images.
- Source code.
- Other supported file formats.

Capabilities:

1. Summarize documents.
2. Extract tables and structured data.
3. Answer questions about uploaded documents.
4. Compare documents.
5. Generate reports.
6. Analyze spreadsheet data.
7. Extract information from technical drawings where supported.
8. Explain engineering documents.
9. Generate downloadable files.
10. Organize documents in project workspaces.

Ensure file content remains private and is not shared between users.

## 7. AI Personal Memory

Create an optional persistent memory system.

Dhanz should remember user-approved information such as:

- Preferred language.
- Writing style.
- Projects.
- Frequently used workflows.
- Preferred AI model.
- Relevant conversation context.
- User-approved knowledge documents.

Users must be able to:

- View saved memories.
- Edit memories.
- Delete memories.
- Disable memory.
- Export their personal data.

Store memory securely with appropriate access controls.

## 8. AI Tools and Productivity

Build a modular tool system supporting:

- Web research.
- Calculators.
- Unit conversion.
- Document generation.
- Code assistance.
- Email drafting.
- Calendar integration.
- Task reminders.
- Spreadsheet analysis.
- Project management.
- Technical research.
- Product comparison.
- Supplier searches.
- Optional image generation.

Integrations requiring external accounts must use secure authentication and explicit authorization.

Any action involving sending messages, deleting files, purchases, or changes to external services must require appropriate user permission.

## 9. Windows Desktop Application

Create a Windows desktop version using Flutter or another justified cross-platform framework.

Required:

- Windows 10/11 support.
- Installable .exe or .msi.
- Desktop shortcuts.
- Start Menu integration.
- System tray functionality.
- Minimize to tray.
- Native file picker.
- Drag-and-drop uploads.
- Optional desktop notifications.
- Automatic updates.
- Uninstaller.
- Secure credential storage.

Provide release builds suitable for normal Windows installation.

## 10. Android Application

Create a native-compatible Android application.

Required:

- Android APK for direct installation.
- Android App Bundle for Google Play submission.
- Responsive mobile interface.
- Android microphone permissions.
- Android file picker.
- Push notifications.
- Voice conversation support.
- Secure authentication.
- Background task handling within Android restrictions.

Ensure the application follows Google Play policies.

## 11. Apple iOS Application

Create an iPhone and iPad application.

Required:

- iOS-compatible application build.
- Xcode project and signing configuration.
- App Store distribution support.
- Apple microphone and privacy permissions.
- Secure Keychain storage.
- Responsive iPhone and iPad layouts.
- Push notifications.
- Voice assistant integration.
- File import and sharing.

Provide instructions for generating a signed .ipa using Xcode and an appropriate Apple developer account.

Do not claim that iOS applications can be distributed publicly without meeting Apple's signing and distribution requirements.

## 12. Recommended Technology Stack

Use the following architecture unless a better production-ready approach is justified.

**Frontend:**
- Flutter and Dart for Windows, Android, and iOS.
- Riverpod for state management.
- GoRouter for navigation.

**Backend:**
- Python.
- FastAPI.
- REST APIs.
- WebSockets for streaming chat.
- Background job processing.

**AI:**
- OpenAI API.
- Anthropic API.
- Gemini API.
- Ollama integration.
- LangGraph or a suitable orchestration framework.
- Retrieval-Augmented Generation.

**Database:**
- PostgreSQL.
- pgvector.
- Redis for caching and queues where needed.

**Authentication:**
- Email/password.
- Google login.
- Apple Sign In.
- Secure token management.

**Storage:**
- Secure cloud object storage.
- Local application cache.
- Encrypted sensitive information.

**Deployment:**
- Docker.
- GitHub Actions.
- Secure backend hosting.
- Automated testing.
- CI/CD pipelines.

Keep provider API keys on the backend rather than embedding secrets in mobile or desktop application binaries.

## 13. DHANZ AI User Interface

Create a premium, modern design.

Theme:

- Dark navy blue.
- Gold accents.
- White text.
- Black secondary backgrounds.
- Smooth animations.
- Rounded interface elements.
- Professional typography.

Create these application screens:

1. Welcome / onboarding.
2. Login and registration.
3. Main AI chat.
4. Conversation history.
5. Web research.
6. Voice assistant.
7. Document analysis.
8. Knowledge library.
9. Project workspaces.
10. AI model selection.
11. Settings and privacy.
12. User profile.

Include a distinctive DHANZ AI logo and application icon.

The design should work consistently across Windows, Android, and iOS.

## 14. Privacy and Security

Implement:

- HTTPS/TLS.
- Secure authentication.
- Encryption at rest where appropriate.
- Role-based access controls.
- Input validation.
- Rate limiting.
- API key protection.
- Secure file uploads.
- Malware scanning where feasible.
- Prompt-injection defenses.
- Audit logging.
- User data deletion.
- Data retention settings.

Treat webpages, uploaded documents, and tool outputs as untrusted content.

External information must not override application security rules or authorize actions.

## 15. Offline and Online Modes

Online mode:

- Cloud AI models.
- Web research.
- Account synchronization.
- Document processing.
- Voice services.

Optional offline mode:

- Local AI inference where hardware supports it.
- Previously downloaded knowledge.
- Local conversation history.
- Basic offline document search.

Explain that real-time web access and cloud AI models require an internet connection.

## 16. Application Build and Distribution

Create a GitHub repository structure containing:

- /apps/dhanz_flutter
- /backend
- /ai_engine
- /knowledge_engine
- /database
- /tests
- /scripts
- /.github/workflows
- /docs

Configure GitHub Actions to:

1. Analyze and test the Flutter application.
2. Test the backend.
3. Build Windows releases using Windows runners.
4. Build Android APK and AAB artifacts.
5. Build iOS artifacts using macOS runners.
6. Handle signing credentials securely.
7. Upload build artifacts.
8. Create versioned releases.

Provide installation instructions for every platform.

## 17. Required Deliverables

Generate:

1. Complete application source code.
2. Flutter frontend.
3. FastAPI backend.
4. AI provider integration.
5. Web research engine.
6. RAG knowledge management.
7. User authentication.
8. Database schema and migrations.
9. Voice assistant implementation.
10. Document upload and analysis.
11. GitHub Actions workflows.
12. Windows installer build configuration.
13. Android APK/AAB build configuration.
14. iOS build and signing instructions.
15. Docker deployment configuration.
16. Environment variable templates.
17. README documentation.
18. Testing instructions.
19. Security and privacy documentation.
20. Application release checklist.

Avoid mock implementations presented as completed features.

## 18. Development Instructions

Develop DHANZ AI in phases.

**Phase 1 — Working MVP**

Build the functional Flutter chatbot, FastAPI backend, AI integration, user authentication, and conversation history.

**Phase 2 — Internet Intelligence**

Add live web search, source citations, webpage summarization, and knowledge indexing.

**Phase 3 — Advanced Assistant**

Add voice conversations, file uploads, document intelligence, memory, and project workspaces.

**Phase 4 — Platform Distribution**

Configure Windows installers, Android APK/AAB builds, and iOS builds.

**Phase 5 — Production Readiness**

Implement automated tests, security hardening, performance improvements, monitoring, privacy controls, and release pipelines.

For every phase:

- Explain the architecture.
- Generate actual source files.
- Provide exact file paths.
- Provide commands to install dependencies.
- Explain how to run the application.
- Add tests.
- Identify incomplete features.
- Explain how to verify functionality.

Do not simply describe how the application could be built. Produce runnable implementation code.

If the complete project cannot fit in one response, divide it into manageable development milestones and continue systematically without skipping essential files.

## 19. Final Objective

The final product must be a real, installable AI assistant named **DHANZ AI**.

Users should be able to open Dhanz on their Windows PC, Android phone, or iPhone and communicate with it through text or voice.

Dhanz should answer questions, research the World Wide Web, explain technical information, analyze documents, and assist with daily tasks.

The assistant must be reliable, secure, extensible, and ready for future improvements.

**Begin by creating the system architecture and complete Phase 1 implementation.**
