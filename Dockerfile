# Use the official lightweight Python image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy your requirements file first
COPY requirements.txt .

# Install your Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium and its required OS dependencies as root
RUN playwright install --with-deps chromium

# Copy the rest of your bot's code into the container
COPY . .

# Expose the port for your aiohttp keep-alive server
EXPOSE 8080

# Start the bot
CMD ["python", "bot.py"]

