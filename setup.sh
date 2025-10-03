#!/bin/bash

echo "🚀 Setting up Fitness Tracker Bot..."

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
echo "⬆️ Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "📚 Installing dependencies..."
pip install -r requirements.txt

# Copy environment file
if [ ! -f .env ]; then
    echo "📝 Creating .env file..."
    cp .env.example .env
    echo "⚠️ Please edit .env file with your configuration!"
fi

# Create necessary directories
mkdir -p logs
mkdir -p data
mkdir -p temp

echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your bot token and API settings"
echo "2. Run: source venv/bin/activate"
echo "3. Run: python -m bot.main"