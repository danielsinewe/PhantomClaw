const fs = require('fs');
const path = require('path');

const serverPath = '/opt/openclaw-wrapper/server.js';
const source = fs.readFileSync(serverPath, 'utf8');

const marker = "require('next')\nconst { startServer } = require('next/dist/server/lib/start-server')\n";
const markerIndex = source.indexOf(marker);

if (markerIndex === -1) {
  throw new Error('Could not find Next standalone server startup marker');
}

const replacement = `const http = require('http')
const net = require('net')
const next = require('next')

const gatewayHost = process.env.OPENCLAW_GATEWAY_HOST || '127.0.0.1'
const gatewayPort = parseInt(process.env.OPENCLAW_GATEWAY_PORT || '18789', 10)

function isGatewayPath(url) {
  return url === '/openclaw' || url.startsWith('/openclaw/')
}

function proxyGatewayRequest(req, res) {
  const options = {
    host: gatewayHost,
    port: gatewayPort,
    method: req.method,
    path: req.url,
    headers: {
      ...req.headers,
      host: \`\${gatewayHost}:\${gatewayPort}\`,
      'x-forwarded-host': req.headers.host || '',
      'x-forwarded-proto': 'https',
    },
  }

  const upstream = http.request(options, (upstreamRes) => {
    res.writeHead(upstreamRes.statusCode || 502, upstreamRes.headers)
    upstreamRes.pipe(res)
  })

  upstream.on('error', (err) => {
    console.error('[openclaw-wrapper] gateway proxy error:', err.message)
    if (!res.headersSent) {
      res.writeHead(502, { 'content-type': 'text/plain; charset=utf-8' })
    }
    res.end('OpenClaw gateway unavailable')
  })

  req.pipe(upstream)
}

function proxyGatewayUpgrade(req, socket, head) {
  const upstream = net.connect(gatewayPort, gatewayHost, () => {
    const headers = [
      \`\${req.method} \${req.url} HTTP/\${req.httpVersion}\`,
      ...Object.entries(req.headers).map(([key, value]) => {
        const normalized = Array.isArray(value) ? value.join(', ') : value
        if (key.toLowerCase() === 'host') {
          return \`host: \${gatewayHost}:\${gatewayPort}\`
        }
        return \`\${key}: \${normalized}\`
      }),
      '',
      '',
    ].join('\\r\\n')

    upstream.write(headers)
    if (head && head.length) {
      upstream.write(head)
    }
    socket.pipe(upstream).pipe(socket)
  })

  upstream.on('error', (err) => {
    console.error('[openclaw-wrapper] gateway upgrade proxy error:', err.message)
    socket.destroy()
  })
}

const app = next({ dev: false, dir, conf: nextConfig })
const handle = app.getRequestHandler()

app.prepare().then(() => {
  const server = http.createServer((req, res) => {
    if (isGatewayPath(req.url || '/')) {
      proxyGatewayRequest(req, res)
      return
    }

    handle(req, res)
  })

  server.on('upgrade', proxyGatewayUpgrade)

  if (keepAliveTimeout !== undefined) {
    server.keepAliveTimeout = keepAliveTimeout
  }

  server.listen(currentPort, hostname, () => {
    console.log(\`[openclaw-wrapper] listening on \${hostname}:\${currentPort}; proxying /openclaw to \${gatewayHost}:\${gatewayPort}\`)
  })
}).catch((err) => {
  console.error(err)
  process.exit(1)
})
`;

fs.writeFileSync(serverPath, `${source.slice(0, markerIndex)}${replacement}`);
console.log('Patched OpenClaw wrapper WebSocket proxy support');
