const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');
const child_process = require('child_process');

const host = '127.0.0.1';
const port = process.env.PORT || 3000;
const root = path.resolve(__dirname);

const mime = {
  '.html': 'text/html',
  '.htm': 'text/html',
  '.js': 'application/javascript',
  '.mjs': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.wav': 'audio/wav',
  '.mp3': 'audio/mpeg',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2'
};

const server = http.createServer((req, res) => {
  let reqUrl = decodeURIComponent(url.parse(req.url).pathname || '/');

  // Redirect root to /src
  if (reqUrl === '/') {
    res.writeHead(302, { Location: '/src' });
    res.end();
    return;
  }

  // Normalize and prevent path traversal
  reqUrl = reqUrl.replace(/\/+$/, '');
  const safeSuffix = path.normalize(reqUrl).replace(/^\.+/, '');
  let filePath = path.join(root, safeSuffix);

  fs.stat(filePath, (err, stats) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('404 Not Found');
      return;
    }

    if (stats.isDirectory()) {
      filePath = path.join(filePath, 'index.html');
    }

    fs.readFile(filePath, (err, data) => {
      if (err) {
        res.writeHead(404, { 'Content-Type': 'text/plain' });
        res.end('404 Not Found');
        return;
      }

      const ext = path.extname(filePath).toLowerCase();
      const type = mime[ext] || 'application/octet-stream';
      res.writeHead(200, { 'Content-Type': type });
      res.end(data);
    });
  });
});

server.listen(port, host, () => {
  const address = `http://${host}:${port}/src`;
  console.log(`Serving ${root} at http://${host}:${port}`);

  // Try to open default browser (Windows, macOS, Linux)
  try {
    const opener = process.platform === 'win32' ? 'start ""' : process.platform === 'darwin' ? 'open' : 'xdg-open';
    // child_process.exec will use the default shell; on Windows this runs via cmd and 'start' will work
    child_process.exec(`${opener} "${address}"`, (err) => {
      if (err) console.log('Could not open browser automatically:', err.message);
    });
  } catch (e) {
    console.log('Could not open browser automatically:', e.message);
  }
});

// Graceful shutdown on SIGINT
process.on('SIGINT', () => {
  console.log('Stopping server...');
  server.close(() => process.exit(0));
});
