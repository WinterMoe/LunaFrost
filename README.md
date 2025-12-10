# LunaFrost Translator [BETA]

<img src="static/images/logo_with_mascot.png" width="512" alt="LunaFrost Logo">

> **Bringing Korean web novels to English readers with AI-powered translation.**

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Framework-Flask-green.svg)](https://flask.palletsprojects.com/)


## About

LunaFrost Translator is a free service that specializes in translating Korean Novelpia novels using the AI of your choice. Whether you prefer Claude, GPT, Gemini, or other AI models, you have the flexibility to select the one that works best for you.

This project is Open Source, believing in transparency and community contribution. While you can self-host your own instance, I provide a free public version for everyone to use.

### Live Site
**Try it now for free:** [https://lunafrost.moe](https://lunafrost.moe) you will just need to provide your own API keys for what ever service you desire to use. If you start to encounter slow down on the site do let me know as I may need to scale up the server.

---

## Features

LunaFrost comes packed with features designed for the best reading experience:

*   **Multi-Model AI Translation**: Support for Claude, Chat GPT, Gemini Pro, and DeepSeek via OpenRouter. As well as direct support for OpenAI, Google Gemini, and DeepL.
*   **Thinking Mode**: Advanced translation logic for complex narratives.
*   **Novel Management**: Organize your library, track reading progress, and manage chapters.
*   **Easy Import**: Seamlessly import chapters from Novelpia (requires browser extension). As well as import from  epub files.
*   **Share Novels**: Seamlessly share novels with other users on site. Allowing you to share your translations with others.
*   **Reader Mode**: Distraction free reading interface with customizable fonts, sizes, and themes (Light/Dark/Sepia).
*   **Glossary Support**: Define custom terms to ensure consistent translation of names and places.
*   **Export Options**: Download your novels as EPUB or PDF for offline reading.
*   **Privacy Focused**: No tracking cookies, no analytics. Your reading data stays private.
*   **Configurable Content Limits**: Novels default to 100 per user (unlimited for admins). Webtoon/Manga jobs default to 5 per user (unlimited for admins). Both have global defaults (Admin → Options) and per-user overrides (Admin → Users; set 0 for unlimited).
*   **Manga & Webtoon Scanlation**: A full-featured suite for translating comics:
    *   **Nano Banana Pro**: Performs OCR, Translation, Inpainting (Text Removal), and Typesetting in a single pass.
    *   **Smart Inpainting**: Automatically detects and wipes text from speech bubbles while preserving the underlying artwork.
    *   **Flexible OCR**: Support for **Google Cloud Vision** and **Azure Computer Vision** for high-precision text detection.
    *   **Visual Editor**: Interactive editor to correct OCR boxes, adjust text, and fine-tune translations before finalizing.
    *   **Dual Reader Modes**: tailored reading experience with **Vertical Scroll** (Webtoon) and **Paged** (Manga) viewers.
*   **Clean Image Uploads**: Webtoon/Manga uploads strip EXIF/ICC metadata on save to reduce bloat while preserving image quality.

---

## Roadmap

I am constantly working to improve LunaFrost. An internal roadmap is in place with new features planned in no particular order, including:

*   Mobile Device importing
*   Setup a free OCR service
*   Other websites support
*   Support Light Novels
*   Support translating to other languages

If you have any other features you would like to see reach out and let me know.

---

## Support & Issues

Encountered a bug? Have a feature request? I want to hear from you!

### Reporting Issues
If you find a bug, please open an issue on GitHub or email me at **[contact@lunafrost.moe](mailto:contact@lunafrost.moe)**.

**When reporting an issue, please include:**
1.  **Description**: What happened? What did you expect to happen?
2.  **Reproduction Steps**: detailed steps to reproduce the issue.
3.  **Screenshots/Logs**: Any relevant visual proof or error messages.

### Feature Requests
Have an idea to make LunaFrost better? Feel free to reach out via email or open a GitHub issue with the "Enhancement" label.

---

## Support the Project

LunaFrost is provided completely free of charge. However, server costs there are server costs afterall.

If you enjoy the service and would like to help keep it running, please consider donating. Every bit helps me keep the servers online and the translations flowing!

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?logo=buy-me-a-coffee&logoColor=000000&labelColor=ffdd00)](https://buymeacoffee.com/wintermoe)

---

## Self-Hosting

Interested in running your own instance? Check out our [Deployment Guide](deployment_guide.md) for detailed instructions on setting up LunaFrost on a VPS.

## License

This project is licensed under the **GNU AGPLv3 License** - see the [LICENSE](LICENSE) file for details.
