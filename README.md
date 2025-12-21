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

## License

MIT 
