import { FitAddon } from "@xterm/addon-fit";
import { Terminal as XTerm } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { useEffect, useRef } from "react";

type Props = {
  websocketUrl: string;
  onDisconnect: () => void;
};

export function Terminal({ websocketUrl, onDisconnect }: Props) {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!container.current) return;
    const terminal = new XTerm({
      cursorBlink: true,
      convertEol: true,
      fontFamily: '"SFMono-Regular", Consolas, monospace',
      fontSize: 13,
      theme: { background: "#080b10", foreground: "#d4d9e2" },
    });
    const fit = new FitAddon();
    terminal.loadAddon(fit);
    const socket = new WebSocket(websocketUrl);
    let disposed = false;
    socket.binaryType = "arraybuffer";
    terminal.open(container.current);
    fit.fit();
    terminal.writeln("Connecting to sandbox…");

    const input = terminal.onData((data) => {
      if (socket.readyState === WebSocket.OPEN) socket.send(data);
    });
    socket.onopen = () => terminal.writeln("Connected.\r\n");
    socket.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        terminal.write(new Uint8Array(event.data));
      } else {
        terminal.write(String(event.data));
      }
    };
    socket.onerror = () => terminal.writeln("\r\nTerminal connection failed.");
    socket.onclose = () => {
      terminal.writeln("\r\nDisconnected. Request a fresh terminal ticket to reconnect.");
      if (!disposed) onDisconnect();
    };
    const resize = () => fit.fit();
    window.addEventListener("resize", resize);

    return () => {
      disposed = true;
      window.removeEventListener("resize", resize);
      input.dispose();
      socket.close();
      terminal.dispose();
    };
  }, [onDisconnect, websocketUrl]);

  return <div className="terminal" ref={container} />;
}
