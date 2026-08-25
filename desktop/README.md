# EMPIRE YouTube Studio for Mac

This desktop runner pulls the private Empire repository, starts its local Flask renderer, and opens the existing HTML studio in a native desktop window.

## Build on a Mac

Install Node.js, pnpm, Python 3, Homebrew, and FFmpeg first:

    brew install ffmpeg

Then run from this folder:

    pnpm install
    pnpm run build:mac

The `.dmg` installer is written to `release/`.

On first launch, the app clones the repository into Documents/Empire YouTube/empire-youtube-channel. Later launches pull the latest main branch. GitHub authentication is handled by the Mac's normal Git credentials; no password or access token is saved by the app.

If the renderer searches Pexels for footage, add PEXELS_API_KEY to the repository's local .env file. Keep it local and never commit it.
