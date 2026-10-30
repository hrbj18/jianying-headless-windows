// JSONL transport for the reviewed official Bun. Each request owns a new pipe connection.
import net from 'node:net';
import fs from 'node:fs';
import crypto from 'node:crypto';
import readline from 'node:readline';

const MAX_RESPONSE = 16 * 1024 * 1024;
const operations = new Set(['system.health', 'system.shutdown', 'player.create', 'player.load',
  'player.getState', 'player.seek', 'player.captureFrame', 'player.destroy']);

async function invoke(input) {
  const { endpoint, request, packetPath, timeoutMs = 15000 } = input;
  if (typeof endpoint !== 'string' || !endpoint.startsWith('\\\\.\\pipe\\') ||
      !request || !operations.has(request.domain + '.' + request.operation) ||
      request.protocolVersion !== 1 || typeof request.id !== 'string' ||
      !Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 30000) {
    throw new Error('Invalid native preview transport input');
  }
  const response = await new Promise((resolve, reject) => {
    const socket = net.createConnection(endpoint);
    let buffer = '';
    let done = false;
    const finish = (error, value) => {
      if (done) return;
      done = true;
      socket.destroy();
      if (error) reject(error); else resolve(value);
    };
    socket.setEncoding('utf8');
    socket.setTimeout(timeoutMs, () => finish(new Error('Native preview request timed out')));
    socket.once('error', error => finish(error));
    socket.once('end', () => { if (!done) finish(new Error('Native preview pipe closed before response')); });
    socket.once('connect', () => socket.write(JSON.stringify(request) + '\n'));
    socket.on('data', chunk => {
      buffer += chunk;
      if (buffer.length > MAX_RESPONSE) return finish(new Error('Native preview response exceeds size limit'));
      const newline = buffer.indexOf('\n');
      if (newline < 0) return;
      try { finish(undefined, JSON.parse(buffer.slice(0, newline))); }
      catch { finish(new Error('Native preview response is not valid JSON')); }
    });
  });
  if (!response || response.id !== request.id || response.protocolVersion !== 1) {
    throw new Error('Native preview response identity mismatch');
  }
  const packetBase64 = response.result?.packetBase64;
  if (packetBase64 !== undefined) {
    if (request.operation !== 'captureFrame' || typeof packetPath !== 'string' ||
        typeof packetBase64 !== 'string' || packetBase64.length % 4 !== 0 ||
        !/^[A-Za-z0-9+/]*={0,2}$/.test(packetBase64)) {
      throw new Error('Invalid native preview frame response');
    }
    const packet = Buffer.from(packetBase64, 'base64');
    if (packet.toString('base64') !== packetBase64 || packet.length < 40 || packet.length > 12 * 1024 * 1024) {
      throw new Error('Invalid native preview frame packet size or base64');
    }
    fs.writeFileSync(packetPath, packet, { flag: 'wx' });
    delete response.result.packetBase64;
    response.result.packet = { path: packetPath, bytes: packet.length,
      sha256: crypto.createHash('sha256').update(packet).digest('hex') };
  }
  return response;
}

for await (const line of readline.createInterface({ input: process.stdin, crlfDelay: Infinity })) {
  if (!line.trim()) continue;
  let input;
  try {
    input = JSON.parse(line);
    console.log(JSON.stringify(await invoke(input)));
  } catch (error) {
    console.log(JSON.stringify({ id: input?.request?.id, protocolVersion: 1, ok: false,
      transportError: String(error.message ?? error).slice(0, 500) }));
    process.exitCode = 1;
  }
}
