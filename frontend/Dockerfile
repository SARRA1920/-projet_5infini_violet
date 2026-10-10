FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 3000

# Serveur de développement (Vite), exposé hors du conteneur sur le port 3000
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]
