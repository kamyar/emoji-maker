# Emoji Maker
A web application that allows you to generate custom emojis from text with various customization options.

## Features

- Generate emojis from multi-line text
- Customize margin settings
- Create animated GIFs with adjustable frame delay and loop settings
- HDR mode (use at your own risk! 😉)

## Prerequisites

- Node.js (v14 or higher)
- npm or yarn package manager
- Python 3.7 or higher
- pip (Python package manager)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/emoji_maker.git
cd emoji_maker
```

2. Install frontend dependencies:
```bash
cd webapp
npm install
# or if using yarn
yarn install
```

3. Install backend dependencies:
```bash
cd ../backend
pip install -r requirements.txt
```

## Running the Application

1. Start the FastAPI backend server:
```bash
cd backend
uvicorn main:app --reload --port 8000
```

2. In a new terminal, start the frontend development server:
```bash
cd webapp
npm run dev
# or if using yarn
yarn dev
```

3. Open your browser and navigate to `http://localhost:3000` (or the port shown in your terminal)

## Usage

1. Enter your desired text in the text area
2. Adjust the settings:
   - Margin: Add spacing around your text
   - HDR: Enable HDR mode (requires confirmation)
   - GIF: Create an animated GIF with customizable loop and frame delay
3. Click "Generate" to create your emoji
4. Use the "Download" button to save your emoji

## API Endpoints

The application uses a single endpoint:

- POST `/api/generate`: Generates the emoji based on the provided parameters

The FastAPI backend server runs on `http://localhost:8000` by default.

## Production deployment

Application changes pushed to `main` run `.github/workflows/container.yml`.
The workflow builds the images, runs the tests, and publishes the images to GHCR.
After publication succeeds, it sends an `emoji-maker-image` event to `kamyar/kamyme`.
The event contains the application image digest, not the moving `main` tag.
Manual workflow runs on `main` also request deployment.
Other branches and repository forks do not request deployment.

The `Production deployment` workflow in `kamyar/kamyme` runs on the DigitalOcean server.
It replaces only the Emoji Maker container.
It tests `emoji.kamyar.eu` and `api.kamy.me`.
If a health check fails, it restores the previous image.
A successful dispatch means that GitHub accepted the event.
Check the production workflow for the deployment result:

<https://github.com/kamyar/kamyme/actions/workflows/production.yml>

### One-time credential setup

The source repository's `GITHUB_TOKEN` cannot send events to the private deployment repository.
Use a separate fine-grained personal access token:

1. Set the resource owner to `kamyar`.
2. Limit repository access to `kamyar/kamyme`.
3. Set the repository permission `Contents` to `Read and write`.
4. Set an expiration date.
5. Store the token as the `KAMYME_DEPLOY_TOKEN` Actions secret in `kamyar/emoji-maker`.

To enter the secret from a terminal, run:

```bash
gh secret set KAMYME_DEPLOY_TOKEN --repo kamyar/emoji-maker
```

Do not put the token in Git or chat.
Renew the secret before the token expires.
A missing or invalid token fails the workflow without changing production.
The workflow change must be on `main` before automatic deployment can start.

### Deployment dispatch tests

The dispatch tests use test programs in place of Docker and the GitHub CLI.
They do not publish images or send deployment events.
Run them with:

```bash
python3 -m unittest discover --start-directory tests/workflows --verbose
```

## License

MIT 
