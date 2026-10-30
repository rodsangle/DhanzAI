# DHANZ AI — IMAGE & VIDEO GENERATION UPGRADE

Update the existing DHANZ AI Public Edition application to include a complete AI-powered image and video generation studio.

Maintain compatibility with Windows, Android, iOS, and Web.

## 1. AI Image Generator

Create an integrated image generation system that allows users to generate original images from text descriptions.

Required features:

- Text-to-image generation.
- Image-to-image transformation.
- Image editing using natural language.
- Background removal and replacement.
- Object removal and replacement.
- Image enhancement and upscaling.
- Logo and graphic design generation.
- Social media graphics.
- Product mockups.
- AI artwork.
- Photorealistic image generation.
- Multiple aspect ratios.
- Image history and gallery.
- Downloadable PNG, JPEG, and WebP images.

Support configurable image-generation providers, including OpenAI image models and other compatible commercial APIs.

Only expose capabilities actually supported by the configured provider.

## 2. AI Video Generator

Create an AI video generation studio.

Required features:

- Text-to-video generation.
- Image-to-video generation.
- Video prompt editor.
- Video aspect ratio selection.
- Video duration selection.
- Resolution selection.
- Video preview player.
- Generation progress tracking.
- Video history.
- Downloadable MP4 videos.
- Optional audio generation where supported.
- Video regeneration and variations.

Implement a modular video-provider system supporting available commercial APIs, such as providers offering Sora, Runway, or other video generation services, subject to actual API availability and access.

Do not assume every provider supports every feature.

Video generation must run as asynchronous background jobs.

The user must be able to leave the generation screen and return to view the completed video.

## 3. DHANZ AI Creative Studio

Add a new main navigation section named:

**DHANZ Creative Studio**

Create three tabs:

1. AI Images
2. AI Videos
3. My Creations

Provide a modern creative workspace with:

- Prompt input field.
- Optional reference image upload.
- AI model selection.
- Aspect ratio selection.
- Quality settings.
- Generate button.
- Generation progress indicator.
- Preview screen.
- Download and share options.
- Saved creation history.

Users should be able to ask Dhanz to help write or improve their image and video prompts.

## 4. AI Subscription and Credits

Add a configurable credit system for image and video generation.

Track:

- User credit balance.
- Image generation credits.
- Video generation credits.
- Credits consumed.
- Failed generation refunds.
- Subscription allowances.
- Optional purchased credit packs.

Use server-side credit accounting.

Reserve credits when a generation job starts, settle them after successful completion, and release or refund them when a job fails according to the billing policy.

Prevent duplicate charges from repeated requests or webhook deliveries.

Allow administrators to configure credit costs and monthly allowances.

## 5. Public Safety and Copyright

Implement content moderation for generated images and videos.

Include:

- Provider safety checks.
- User reporting.
- Abuse prevention.
- Appropriate restrictions on impersonation and nonconsensual content.
- Copyright and intellectual property safeguards.
- Secure handling of uploaded reference images.
- Privacy controls for generated media.
- Disclosure or provenance metadata where supported.

Generated content must be private to the user's account unless explicitly shared.

## 6. Backend Architecture

Create dedicated backend modules:

- /backend/image_generation
- /backend/video_generation
- /backend/media_storage
- /backend/generation_jobs
- /backend/credit_billing
- /backend/content_moderation

Use secure cloud object storage for media files.

Implement background workers and job queues for long-running generation tasks.

Track job status as queued, processing, completed, failed, or canceled.

Use signed media URLs, authorization checks, expiration policies, and cleanup jobs.

## 7. Platform Integration

Integrate image and video generation into:

- Windows desktop application.
- Android application.
- iPhone and iPad application.
- Web application.

Support device-appropriate image and video previews, file downloads, and sharing.

## 8. Testing Requirements

Create tests for:

- Image generation requests.
- Video generation requests.
- Provider errors.
- Credit deductions and refunds.
- Generation cancellation.
- Concurrent requests.
- Account isolation.
- Media upload security.
- Download authorization.
- Job status synchronization.

## 9. Required Deliverables

Generate complete implementation code for:

1. AI image generator UI.
2. AI video generator UI.
3. Media generation API.
4. Provider adapters.
5. Background job processing.
6. Credit accounting.
7. Media gallery.
8. Secure cloud storage.
9. Content moderation.
10. Automated tests.
11. GitHub Actions integration.
12. Setup and deployment documentation.

Integrate these modules into the existing DHANZ AI application without removing or breaking existing chatbot, research, voice, document, or subscription features.

Build a working image generation workflow first, then implement asynchronous video generation.

Do not claim features work until they have been implemented and tested.
