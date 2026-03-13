const http = require("http");
const { settingsApiMiddleware } = require("./server-api.cjs");

const PORT = 5174;

const server = http.createServer((req, res) => {
  // CORS headers for local testing, though Nginx will handle domain
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    res.writeHead(204);
    res.end();
    return;
  }

  // Intercept settings API
  if (req.url.startsWith("/__api/settings/")) {
    settingsApiMiddleware(req, res, () => {
      res.writeHead(404);
      res.end('Not Found');
    });
    return;
  }

  res.writeHead(404);
  res.end('Not Found');
});

server.listen(PORT, () => {
  console.log(`Settings API bridge running on port ${PORT}`);
});
