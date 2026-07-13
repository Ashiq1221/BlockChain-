// Stub for node:net — only needed by mtkruto's SOCKS5 transport which we don't use.
// WebSocket transport (default in CF Workers) does not require this module.
export class Socket {
  connect() { return this; }
  destroy() {}
  on() { return this; }
  write() {}
  end() {}
}
export const createConnection = () => new Socket();
export const createServer = () => ({});
export default { Socket, createConnection, createServer };
